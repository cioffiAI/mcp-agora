import gc
import tempfile

import pytest

from agora.cache.l1_memory import L1Cache
from agora.config import Config
from agora.embedding.sentence import SentenceTransformerProvider
from agora.memory.vector_store import VectorStore


@pytest.fixture
def fresh_server():
    tmp = tempfile.mkdtemp()
    cfg = Config(
        chroma_path=tmp,
        l1_max_entries=100,
        l1_ttl_seconds=60,
    )
    embedding = SentenceTransformerProvider()
    vector_store = VectorStore(path=cfg.chroma_path, embedding_provider=embedding)
    l1_cache = L1Cache(maxsize=cfg.l1_max_entries, ttl=cfg.l1_ttl_seconds)
    yield cfg, embedding, vector_store, l1_cache
    del vector_store
    del l1_cache
    gc.collect()


def test_save_knowledge(fresh_server):
    _, embedding, vs, cache = fresh_server
    from datetime import datetime, timezone
    import uuid

    content = "PostgreSQL BRIN indexes are useful for very large tables"
    entry_id = f"mem_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    metadata = {"tags": "postgres,sql", "created_at": datetime.now(timezone.utc).isoformat(), "agent": "test"}
    ids = vs.add(texts=[content], metadata=[metadata], ids=[entry_id])
    cache.clear()
    assert ids[0] == entry_id


def test_save_then_query(fresh_server):
    _, embedding, vs, cache = fresh_server

    content = "Agora is an MCP server for persistent cross-agent memory"
    import uuid
    from datetime import datetime, timezone

    entry_id = f"mem_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    vs.add(texts=[content], ids=[entry_id])

    results = vs.query(query_texts=["MCP server persistent memory"], n_results=5)
    assert len(results) >= 1
    assert "MCP" in results[0]["text"]
    assert results[0]["id"] == entry_id


def test_query_returns_correct_format(fresh_server):
    _, embedding, vs, cache = fresh_server

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
    _, embedding, vs, cache = fresh_server

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
