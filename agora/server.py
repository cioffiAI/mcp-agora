import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP

from agora.cache.l1_memory import L1Cache
from agora.cache.l2_cache import L2Cache
from agora.config import Config
from agora.connectors.base import ReadOnlyBlockedError
from agora.db.database import Database
from agora.embedding.base import WarmingUpError
from agora.embedding.sentence import SentenceTransformerProvider
from agora.registry import BackendRegistry
from agora.routing.router import Router


def create_server(config: Config | None = None, logger: logging.Logger | None = None, preload: bool = True) -> FastMCP:
    # Lazy import: defers chromadb (and heavy transitive deps) until server creation.
    # This keeps bare `import agora.server` cheap; cost paid on first create_server (AC4 / startup priority).
    from agora.memory.vector_store import VectorStore

    cfg = config or Config.load()
    log = logger or logging.getLogger("agora.server")

    log.info("Initializing embedding provider: %s", cfg.embedding_model)
    embedding = SentenceTransformerProvider(model_name=cfg.embedding_model)

    vector_store = VectorStore(
        path=str(cfg.resolved_chroma_path),
        embedding_provider=embedding,
    )
    log.info("ChromaDB ready: path=%s", cfg.resolved_chroma_path)

    l1_cache = L1Cache(maxsize=cfg.l1_max_entries, ttl=cfg.l1_ttl_seconds)
    db = Database(path=str(cfg.resolved_db_path))
    l2_cache = L2Cache(db=db, ttl_seconds=cfg.l2_ttl_seconds)
    l2_cache.prune_expired()
    log.info(
        "Cache layers ready: L1=%d entries/%ds TTL, L2=%d entries/%ds TTL",
        cfg.l1_max_entries,
        cfg.l1_ttl_seconds,
        cfg.l2_max_entries,
        cfg.l2_ttl_seconds,
    )

    registry = BackendRegistry(logger=log)
    for b in cfg.backends:
        registry.register(b)
    log.info("Registered %d backends: %s", len(cfg.backends), [b.name for b in cfg.backends])

    router = Router(registry, embedding)
    log.info("Router ready (lazy warmup, %d backends)", len(cfg.backends))

    @asynccontextmanager
    async def _lifespan(_server: FastMCP):
        # Warm up the embedding model in the BACKGROUND. Importing torch +
        # sentence-transformers and loading the model can take tens of seconds;
        # doing it synchronously before mcp.run() blocked the MCP protocol
        # handshake past the host's ~32s timeout ("Not connected"). Running it in
        # a worker thread keeps the event loop free to answer initialize /
        # tools/list immediately. Tools called before the model is ready return
        # the existing "warming up" grace response.
        warmup_task: asyncio.Task | None = None
        if preload:

            async def _warmup() -> None:
                try:
                    log.info("Background warmup: loading embedding model (may take a moment on first run)...")
                    await asyncio.to_thread(embedding.warmup)
                    log.info("Embedding model loaded (dim=%d)", embedding.dimension())
                    await asyncio.to_thread(router.warmup)
                    log.info("Router warmed up (%d backend embeddings)", len(router._backend_embeddings))
                except Exception:
                    log.exception("Background warmup failed; tools will report 'warming up' until a retry succeeds")

            warmup_task = asyncio.create_task(_warmup())
        try:
            yield {}
        finally:
            if warmup_task is not None and not warmup_task.done():
                warmup_task.cancel()

    mcp = FastMCP(cfg.name, lifespan=_lifespan)

    @mcp.tool()
    def agora_save(
        content: str,
        tags: list[str] | None = None,
        agent: str | None = None,
        session: str | None = None,
        confidence: float = 0.5,
    ) -> dict:
        entry_id = "mem_{}_{}".format(datetime.now(UTC).strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:8])
        agent_name = agent or "unknown"
        session_id = session or str(uuid.uuid4())
        metadata = {
            "tags": ",".join(tags) if tags else "",
            "created_at": datetime.now(UTC).isoformat(),
            "agent": agent_name,
        }
        try:
            ids = vector_store.add(texts=[content], metadata=[metadata], ids=[entry_id])
        except WarmingUpError:
            return {
                "error": "Server is warming up. Embedding model is still loading. Please retry in a moment.",
                "status": "warming_up",
            }
        db.register_agent(agent_name)
        db.add_provenance(
            entry_id=entry_id,
            source_agent=agent_name,
            source_session=session_id,
            confidence=confidence,
        )
        l1_cache.clear()
        l2_cache.clear()
        log.info("agora_save: id=%s agent=%s tags=%s confidence=%.2f", entry_id, agent_name, tags, confidence)
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
            log.debug("agora_query L1 HIT: query=%s", query[:60])
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
            log.debug("agora_query L2 HIT: query=%s", query[:60])
            return l2_cached

        try:
            results = vector_store.query(query_texts=[query], n_results=top_k)
        except WarmingUpError:
            return {
                "error": "Server is warming up. Embedding model is still loading. Please retry in a moment.",
                "status": "warming_up",
            }
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
        result_count = len(results)
        log.info("agora_query: query=%s results=%d cached=MISS", query[:60], result_count)
        return response

    @mcp.tool()
    def agora_crossref(query: str = "", entry_id: str = "", top_k: int = 5) -> dict:
        if not query and not entry_id:
            return {"error": "Provide either 'query' or 'entry_id'"}

        try:
            return _crossref_impl(query, entry_id, top_k)
        except WarmingUpError:
            return {
                "error": "Server is warming up. Embedding model is still loading. Please retry in a moment.",
                "status": "warming_up",
            }

    def _crossref_impl(query: str, entry_id: str, top_k: int) -> dict:
        if entry_id:
            provenance = db.get_provenance(entry_id)
            if not provenance:
                return {"error": f"Entry '{entry_id}' not found in provenance", "mode": "entry_id"}
            # Direct ID retrieval from collection (not semantic query on the ID string)
            coll = vector_store.knowledge_collection
            got = coll.get(ids=[entry_id], include=["documents", "metadatas"])
            docs = got.get("documents") or []
            source_agent = provenance["source_agent"]
            entry_text = docs[0] if docs else ""
            all_results = vector_store.query(query_texts=[entry_text or entry_id], n_results=top_k + 1)

            cross_entries = []
            for r in all_results:
                if r["id"] == entry_id:
                    continue
                p = db.get_provenance(r["id"])
                r["source_agent"] = p["source_agent"] if p else "unknown"
                cross_entries.append(r)

            log.info("agora_crossref(entry_id): entry=%s agent=%s cross=%d", entry_id, source_agent, len(cross_entries))
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
        log.info(
            "agora_crossref(query): query=%s results=%d agents=%d multiple=%s",
            query[:60],
            len(results),
            agent_count,
            multiple_agents,
        )
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
            log.info("agora_forget(DRY_RUN): would delete %d entries", len(to_delete_list))
            return {
                "forgotten": 0,
                "dry_run": True,
                "entry_ids": to_delete_list,
                "count": len(to_delete_list),
            }

        vector_store.delete(ids=to_delete_list)
        db.delete_provenance(to_delete_list)
        l1_cache.clear()
        l2_cache.clear()
        log.info("agora_forget: deleted %d entries", len(to_delete_list))
        return {"forgotten": len(to_delete_list), "dry_run": False, "entry_ids": to_delete_list}

    @mcp.tool()
    async def agora_route(target: str, tool: str, arguments: dict | None = None) -> dict:
        try:
            connector, method, score = router.route(target)
        except WarmingUpError:
            return {
                "error": "Server is warming up. Embedding model is still loading. Please retry in a moment.",
                "status": "warming_up",
            }
        if connector is None:
            log.warning("agora_route: no backend matched target='%s' (method=%s, score=%.2f)", target, method, score)
            return {
                "error": f"No backend matched '{target}'",
                "method": method,
                "score": round(score, 4),
            }
        try:
            result = await connector.call_tool(tool, arguments or {})
            log.info(
                "agora_route: target=%s backend=%s tool=%s method=%s score=%.2f",
                target,
                connector.name,
                tool,
                method,
                score,
            )
            return {
                "backend": connector.name,
                "tool": tool,
                "method": method,
                "score": round(score, 4),
                "content": result["content"],
                "isError": result.get("isError", False),
            }
        except ReadOnlyBlockedError as e:
            log.warning("agora_route BLOCKED: backend=%s tool=%s - %s", connector.name, tool, e)
            return {
                "error": str(e),
                "backend": connector.name,
                "tool": tool,
                "method": method,
                "blocked": True,
            }
        except Exception as e:
            log.error("agora_route ERROR: backend=%s tool=%s - %s", connector.name, tool, e, exc_info=True)
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
        log.info("agora_broadcast: tool=%s backends=%d", tool, len(backends))

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
                log.warning("agora_broadcast BLOCKED: backend=%s tool=%s - %s", b.name, tool, e)
                return b.name, {"blocked": True, "error": str(e)}
            except Exception as e:
                log.error("agora_broadcast ERROR: backend=%s tool=%s - %s", b.name, tool, e, exc_info=True)
                return b.name, {"error": str(e)}

        tasks = [call_one(b) for b in backends]
        gathered = await asyncio.gather(*tasks)
        return {"tool": tool, "results": dict(gathered)}

    @mcp.tool()
    async def agora_backends() -> dict:
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
    async def agora_status() -> dict:
        agents_list = db.list_agents()
        l2_stats = l2_cache.stats()
        health_results = await registry.health_check_all()
        band = sum(1 for h in health_results.values() if h.get("status") == "dead")
        connected_count = len(registry.list_connected())
        log.debug(
            "agora_status: agents=%d backends=%d/%d connected dead=%d",
            len(agents_list),
            connected_count,
            len(registry.list_backends()),
            band,
        )
        return {
            "server": "Agora",
            "version": cfg.version,
            "embedding": {
                "model": cfg.embedding_model,
                "ready": embedding.is_ready(),
            },
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
            "backend_health": health_results,
            "db_size_bytes": db.db_size_bytes(),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    return mcp
