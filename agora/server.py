import asyncio
import uuid
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

from agora.cache.l1_memory import L1Cache
from agora.cache.l2_cache import L2Cache
from agora.config import Config
from agora.connectors.base import ReadOnlyBlockedError
from agora.db.database import Database
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
    db = Database(path=str(cfg.resolved_db_path))
    l2_cache = L2Cache(db=db, ttl_seconds=cfg.l2_ttl_seconds)
    l2_cache.prune_expired()

    registry = BackendRegistry()
    for b in cfg.backends:
        registry.register(b)

    router = Router(registry, embedding)
    router.warmup()

    mcp = FastMCP(cfg.name)

    @mcp.tool()
    def agora_save(
        content: str,
        tags: list[str] | None = None,
        agent: str | None = None,
        session: str | None = None,
        confidence: float = 0.5,
    ) -> dict:
        entry_id = f"mem_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        agent_name = agent or "unknown"
        session_id = session or str(uuid.uuid4())
        metadata = {
            "tags": ",".join(tags) if tags else "",
            "created_at": datetime.now(UTC).isoformat(),
            "agent": agent_name,
        }
        ids = vector_store.add(texts=[content], metadata=[metadata], ids=[entry_id])
        db.register_agent(agent_name)
        db.add_provenance(entry_id=entry_id, source_agent=agent_name, source_session=session_id, confidence=confidence)
        l1_cache.clear()
        l2_cache.clear()
        return {
            "saved": True,
            "id": ids[0],
            "agent": agent_name,
            "session": session_id,
            "confidence": confidence,
        }

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
            cached["cache_level"] = "l1"
            return cached

        l2_cached = l2_cache.get(
            tool="agora.query",
            query=query,
            top_k=top_k,
            model=cfg.embedding_model,
        )
        if l2_cached is not None:
            l1_cache.set(
                tool="agora.query",
                query=query,
                top_k=top_k,
                model=cfg.embedding_model,
                value=l2_cached,
            )
            l2_cached["cached"] = True
            l2_cached["cache_level"] = "l2"
            return l2_cached

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
        l2_cache.set(
            tool="agora.query",
            query=query,
            top_k=top_k,
            model=cfg.embedding_model,
            value=response,
        )
        return response

    @mcp.tool()
    def agora_crossref(query: str = "", entry_id: str = "", top_k: int = 5) -> dict:
        if not query and not entry_id:
            return {"error": "Provide either 'query' or 'entry_id'"}

        if entry_id:
            provenance = db.get_provenance(entry_id)
            if not provenance:
                return {"error": f"Entry '{entry_id}' not found in provenance", "mode": "entry_id"}
            single_result = vector_store.query(query_texts=[entry_id], n_results=1)
            source_agent = provenance["source_agent"]
            entry_text = single_result[0]["text"] if single_result else ""
            all_results = vector_store.query(query_texts=[entry_text or entry_id], n_results=top_k + 1)

            cross_entries = []
            for r in all_results:
                if r["id"] == entry_id:
                    continue
                p = db.get_provenance(r["id"])
                r["source_agent"] = p["source_agent"] if p else "unknown"
                cross_entries.append(r)

            return {
                "mode": "entry_id",
                "source_entry_id": entry_id,
                "source_agent": source_agent,
                "cross_agent_entries": cross_entries,
            }

        results = vector_store.query(query_texts=[query], n_results=top_k)
        agent_groups = {}
        for r in results:
            p = db.get_provenance(r["id"])
            agent_name = p["source_agent"] if p else "unknown"
            r["source_agent"] = agent_name
            if agent_name not in agent_groups:
                agent_groups[agent_name] = []
            agent_groups[agent_name].append(r)

        cross_agent_groups = []
        for agent_name, entries in agent_groups.items():
            cross_agent_groups.append({"agent": agent_name, "entries": entries})

        agent_count = len(cross_agent_groups)
        multiple_agents = agent_count > 1

        return {
            "mode": "query",
            "query": query,
            "total_entries": len(results),
            "unique_agents": agent_count,
            "multiple_agents": multiple_agents,
            "cross_agent_groups": cross_agent_groups,
        }

    @mcp.tool()
    def agora_forget(
        entry_ids: list[str] | None = None,
        tags: list[str] | None = None,
        agent: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        if not entry_ids and not tags and not agent:
            return {"error": "Provide at least one of: entry_ids, tags, agent"}

        to_delete = set()

        if entry_ids:
            to_delete.update(entry_ids)

        if tags:
            all_entries = vector_store.knowledge_collection.get()
            for i, meta in enumerate(all_entries["metadatas"]):
                if meta and meta.get("tags"):
                    entry_tags = meta["tags"].split(",")
                    if any(t in entry_tags for t in tags):
                        to_delete.add(all_entries["ids"][i])

        if agent:
            provenances = db.list_provenance(agent=agent)
            to_delete.update(p["entry_id"] for p in provenances)

        if not to_delete:
            return {"forgotten": 0, "dry_run": dry_run, "entry_ids": []}

        to_delete_list = list(to_delete)

        if dry_run:
            return {
                "forgotten": 0,
                "dry_run": True,
                "entry_ids": to_delete_list,
                "count": len(to_delete_list),
            }

        vector_store.delete(ids=to_delete_list)
        db.delete_provenance(to_delete_list)
        l1_cache.clear()

        return {"forgotten": len(to_delete_list), "dry_run": False, "entry_ids": to_delete_list}

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
            backends.append(
                {
                    "name": b.name,
                    "description": b.description,
                    "transport": b.transport,
                    "read_only": b.read_only,
                    "connected": registry.is_connected(b.name),
                }
            )
        return {"backends": backends}

    @mcp.tool()
    def agora_status() -> dict:
        connected_count = len(registry.list_connected())
        l2_stats = l2_cache.stats()
        agents_list = db.list_agents()
        return {
            "server": "Agora",
            "version": cfg.version,
            "memory_entries": vector_store.count(),
            "agents": {
                "total": len(agents_list),
                "names": [a["name"] for a in agents_list],
            },
            "cache_stats": {
                "l1": l1_cache.stats(),
                "l2": l2_stats,
            },
            "backends": {
                "total": len(registry.list_backends()),
                "connected": connected_count,
            },
            "db_size_bytes": db.db_size_bytes(),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    return mcp
