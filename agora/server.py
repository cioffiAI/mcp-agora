import uuid
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from agora.cache.l1_memory import L1Cache
from agora.config import Config
from agora.embedding.sentence import SentenceTransformerProvider
from agora.memory.vector_store import VectorStore


def create_server(config: Config | None = None) -> FastMCP:
    cfg = config or Config.load()

    embedding = SentenceTransformerProvider(model_name=cfg.embedding_model)
    embedding.warmup()

    vector_store = VectorStore(
        path=str(cfg.resolved_chroma_path),
        embedding_provider=embedding,
    )
    l1_cache = L1Cache(maxsize=cfg.l1_max_entries, ttl=cfg.l1_ttl_seconds)

    mcp = FastMCP(cfg.name)

    @mcp.tool()
    def agora_save(content: str, tags: list[str] | None = None) -> dict:
        entry_id = f"mem_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        metadata = {
            "tags": ",".join(tags) if tags else "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "agent": "unknown",
        }
        ids = vector_store.add(texts=[content], metadata=[metadata], ids=[entry_id])
        l1_cache.clear()
        return {"saved": True, "id": ids[0]}

    @mcp.tool()
    def agora_query(query: str, top_k: int = 5) -> dict:
        cached = l1_cache.get(
            tool="agora.query",
            query=query,
            top_k=top_k,
            model=cfg.embedding_model,
        )
        if cached is not None:
            cached["cached"] = True
            return cached

        results = vector_store.query(query_texts=[query], n_results=top_k)
        response = {
            "query": query,
            "results": results,
            "cached": False,
        }
        l1_cache.set(
            tool="agora.query",
            query=query,
            top_k=top_k,
            model=cfg.embedding_model,
            value=response,
        )
        return response

    @mcp.tool()
    def agora_status() -> dict:
        return {
            "server": "Agora",
            "memory_entries": vector_store.count(),
            "cache_stats": l1_cache.stats(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return mcp
