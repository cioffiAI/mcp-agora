import asyncio
import uuid
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from agora.cache.l1_memory import L1Cache
from agora.config import Config
from agora.connectors.base import ReadOnlyBlockedError
from agora.embedding.sentence import SentenceTransformerProvider
from agora.memory.vector_store import VectorStore
from agora.registry import BackendRegistry
from agora.routing.router import Router


def create_server(config: Config | None = None) -> FastMCP:
    cfg = config or Config.load()

    embedding = SentenceTransformerProvider(model_name=cfg.embedding_model)
    embedding.warmup()

    vector_store = VectorStore(
        path=str(cfg.resolved_chroma_path),
        embedding_provider=embedding,
    )
    l1_cache = L1Cache(maxsize=cfg.l1_max_entries, ttl=cfg.l1_ttl_seconds)

    registry = BackendRegistry()
    for b in cfg.backends:
        registry.register(b)

    router = Router(registry, embedding)
    router.warmup()

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
    async def agora_route(target: str, tool: str, arguments: dict | None = None) -> dict:
        connector, method, score = router.route(target)
        if connector is None:
            return {
                "error": f"No backend matched '{target}'",
                "method": method,
                "score": round(score, 4),
            }
        try:
            result = await connector.call_tool(tool, arguments or {})
            return {
                "backend": connector.name,
                "tool": tool,
                "method": method,
                "score": round(score, 4),
                "content": result["content"],
                "isError": result.get("isError", False),
            }
        except ReadOnlyBlockedError as e:
            return {
                "error": str(e),
                "backend": connector.name,
                "tool": tool,
                "method": method,
                "blocked": True,
            }
        except Exception as e:
            return {
                "error": f"Tool '{tool}' on backend '{connector.name}' failed: {e}",
                "backend": connector.name,
                "tool": tool,
                "method": method,
            }

    @mcp.tool()
    async def agora_broadcast(tool: str, arguments: dict | None = None) -> dict:
        backends = registry.list_backends()
        args = arguments or {}

        async def call_one(b):
            connector = registry.get_connector(b.name)
            if connector is None:
                return b.name, {"error": "backend not found"}
            try:
                result = await connector.call_tool(tool, args)
                return b.name, {
                    "content": result["content"],
                    "isError": result.get("isError", False),
                }
            except ReadOnlyBlockedError as e:
                return b.name, {"blocked": True, "error": str(e)}
            except Exception as e:
                return b.name, {"error": str(e)}

        tasks = [call_one(b) for b in backends]
        gathered = await asyncio.gather(*tasks)
        return {"tool": tool, "results": dict(gathered)}

    @mcp.tool()
    def agora_backends() -> dict:
        backends = []
        for b in registry.list_backends():
            backends.append({
                "name": b.name,
                "description": b.description,
                "transport": b.transport,
                "read_only": b.read_only,
                "connected": registry.is_connected(b.name),
            })
        return {"backends": backends}

    @mcp.tool()
    def agora_status() -> dict:
        connected_count = len(registry.list_connected())
        return {
            "server": "Agora",
            "memory_entries": vector_store.count(),
            "cache_stats": l1_cache.stats(),
            "backends": {
                "total": len(registry.list_backends()),
                "connected": connected_count,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return mcp
