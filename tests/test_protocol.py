import asyncio
import gc
import json
import tempfile
from datetime import UTC
from pathlib import Path

import pytest

from agora.cache.l1_memory import L1Cache
from agora.cache.l2_cache import L2Cache
from agora.config import Config
from agora.db.database import Database
from agora.embedding.sentence import SentenceTransformerProvider
from agora.memory.vector_store import VectorStore
from agora.server import create_server


@pytest.fixture
def fresh_server():
    tmp = tempfile.mkdtemp()
    cfg = Config(
        chroma_path=tmp,
        db_path=tmp + "/agora.db",
        l1_max_entries=100,
        l1_ttl_seconds=60,
    )
    embedding = SentenceTransformerProvider()
    vector_store = VectorStore(path=cfg.chroma_path, embedding_provider=embedding)
    l1_cache = L1Cache(maxsize=cfg.l1_max_entries, ttl=cfg.l1_ttl_seconds)
    db = Database(path=cfg.db_path)
    l2_cache = L2Cache(db=db, ttl_seconds=3600)
    yield cfg, embedding, vector_store, l1_cache, db, l2_cache
    del vector_store
    del l1_cache
    del db
    del l2_cache
    gc.collect()


def test_save_knowledge(fresh_server):
    _, embedding, vs, cache, db, l2_cache = fresh_server
    import uuid
    from datetime import datetime

    content = "PostgreSQL BRIN indexes are useful for very large tables"
    entry_id = f"mem_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    metadata = {"tags": "postgres,sql", "created_at": datetime.now(UTC).isoformat(), "agent": "test"}
    ids = vs.add(texts=[content], metadata=[metadata], ids=[entry_id])
    cache.clear()
    assert ids[0] == entry_id


def test_save_then_query(fresh_server):
    _, embedding, vs, cache, db, l2_cache = fresh_server

    content = "Agora is an MCP server for persistent cross-agent memory"
    import uuid
    from datetime import datetime

    entry_id = f"mem_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    vs.add(texts=[content], ids=[entry_id])

    results = vs.query(query_texts=["MCP server persistent memory"], n_results=5)
    assert len(results) >= 1
    assert "MCP" in results[0]["text"]
    assert results[0]["id"] == entry_id


def test_query_returns_correct_format(fresh_server):
    _, embedding, vs, cache, db, l2_cache = fresh_server

    vs.add(texts=["test knowledge entry"])

    results = vs.query(query_texts=["test"], n_results=5)
    assert isinstance(results, list)
    assert len(results) >= 1
    r = results[0]
    assert "id" in r
    assert "text" in r
    assert "score" in r
    assert isinstance(r["score"], float)


def test_cache_hit_after_query(fresh_server):
    _, embedding, vs, cache, db, l2_cache = fresh_server

    vs.add(texts=["cached knowledge"])
    query = "knowledge retrieval"
    cache.set(
        tool="agora.query",
        query=query,
        top_k=5,
        model="all-MiniLM-L6-v2",
        value={"query": query, "results": [{"text": "cached knowledge", "score": 0.95}], "cached": True},
    )
    result = cache.get(
        tool="agora.query",
        query=query,
        top_k=5,
        model="all-MiniLM-L6-v2",
    )
    assert result is not None
    stats = cache.stats()
    assert stats["hit_count"] >= 1


def test_l2_cache_fallback(fresh_server):
    """L2 cache stores and returns results when L1 misses and L2 hits."""
    _, embedding, vs, l1_cache, db, l2_cache = fresh_server

    vs.add(texts=["PostgreSQL BRIN indexes are useful for large tables"])

    query = "database indexing large tables"
    l2_cache.set(
        tool="agora.query",
        query=query,
        top_k=5,
        model="all-MiniLM-L6-v2",
        value={"query": query, "results": [{"text": "l2 cached result", "score": 0.9}], "cached": False},
    )

    result = l2_cache.get(
        tool="agora.query",
        query=query,
        top_k=5,
        model="all-MiniLM-L6-v2",
    )
    assert result is not None
    assert result["results"][0]["text"] == "l2 cached result"
    stats = l2_cache.stats()
    assert stats["total_hits"] >= 1


def test_save_with_provenance(fresh_server):
    _, embedding, vs, cache, db, l2_cache = fresh_server

    content = "MCP Agora is a cross-agent memory server"
    import uuid
    from datetime import datetime

    entry_id = f"mem_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    metadata = {"tags": "mcp,memory", "created_at": datetime.now(UTC).isoformat(), "agent": "codex"}
    vs.add(texts=[content], metadata=[metadata], ids=[entry_id])
    db.register_agent("codex")
    db.add_provenance(entry_id=entry_id, source_agent="codex", source_session="session-abc", confidence=0.9)
    cache.clear()

    prov = db.get_provenance(entry_id)
    assert prov is not None
    assert prov["source_agent"] == "codex"
    assert prov["source_session"] == "session-abc"
    assert prov["confidence"] == 0.9


def test_forget_clears_l1_and_l2_via_real_shipped_tool():
    """Drive the exact agora_save/query/forget code paths from create_server
    (shipped implementation) using call_tool. After forget, re-querying the
    same text that previously hit L2 must be a cache miss (not stale L2 hit
    containing the deleted entry's content).
    """
    tmp = tempfile.mkdtemp()
    try:
        cdir = Path(tmp) / "chroma"
        cdir.mkdir(parents=True, exist_ok=True)
        dbp = str(Path(tmp) / "agora.db")
        cfg = Config(
            chroma_path=str(cdir),
            db_path=dbp,
            l1_max_entries=10,
            l1_ttl_seconds=30,
            l2_max_entries=10,
            l2_ttl_seconds=3600,
        )
        mcp = create_server(config=cfg, preload=False)

        content = "Unique L2 invalidation test content 0xDEADBEEF for forget clear check"
        q = "Unique L2 invalidation test content"

        # save via real tool fn
        save_raw = asyncio.run(mcp.call_tool("agora_save", {"content": content, "agent": "testagent"}))
        saved = json.loads(save_raw[0].text)
        assert saved.get("saved") is True
        eid = saved["id"]

        # query to populate L1+L2
        q1_raw = asyncio.run(mcp.call_tool("agora_query", {"query": q, "top_k": 3}))
        q1 = json.loads(q1_raw[0].text)
        assert len(q1.get("results", [])) >= 1
        assert "0xDEADBEEF" in q1["results"][0]["text"]

        # Force L1 clear using attached (verification only) so next query hits real L2
        l1 = getattr(mcp, "_agora_l1_cache", None)
        if l1:
            l1.clear()
        q_l2_raw = asyncio.run(mcp.call_tool("agora_query", {"query": q, "top_k": 3}))
        q_l2 = json.loads(q_l2_raw[0].text)
        # Observe explicit L2 hit before forget (cached true / level l2)
        assert q_l2.get("cached") is True or q_l2.get("cache_level") == "l2"

        # forget (exercises the fixed path that now clears L2)
        f_raw = asyncio.run(mcp.call_tool("agora_forget", {"entry_ids": [eid]}))
        f = json.loads(f_raw[0].text)
        assert f.get("forgotten", 0) >= 1

        # re-query: must not be L2 hit with stale forgotten content (cached false or no stale text)
        q2_raw = asyncio.run(mcp.call_tool("agora_query", {"query": q, "top_k": 3}))
        q2 = json.loads(q2_raw[0].text)
        # After L2 clear, this must be a fresh (non-L2) result
        assert q2.get("cached") is False or q2.get("cache_level") != "l2"
        texts = [r.get("text", "") for r in q2.get("results", [])]
        assert not any("0xDEADBEEF" in t for t in texts), "stale forgotten content returned from (un-cleared) L2"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
