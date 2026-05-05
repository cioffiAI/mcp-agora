# MCP Agora — Agent Instructions

## Memory & Knowledge (Agora stesso)

Agora è un MCP server con memoria persistente cross-agente. Quando lavori in questo progetto:

1. **Prima di cercare soluzioni esterne** → chiama `agora_query` per vedere se informazioni utili sono già state salvate
2. **Dopo aver risolto un problema** → chiama `agora_save` per memorizzare la soluzione (con tags)
3. **Le informazioni sono condivise tra tutti gli agenti** — Claude Code, Codex, ChatGPT, Gemini CLI

La ricerca è semantica (embedding a 384 dimensioni), non per keyword. ChromaDB usa un indice ANN (HNSW) che trova le entry più simili in **O(log n)** — anche con 10.000 entry la risposta arriva in <50ms.

## Project Overview

MCP Agora is a **portfolio/learning project** implementing an MCP Server with cross-agent persistent memory. It is NOT a product — it is not competing with ContextForge (IBM), MetaMCP, AutoMem, or mcp-memory-service.

### Goal

Build an MCP Server that allows AI agents (Claude Code, Codex, ChatGPT, Gemini CLI) to:
- Save knowledge with `agora.save` → persistent vector memory (ChromaDB)
- Query knowledge with `agora.query` → semantic search across saved entries
- Share memory across agents and sessions
- Cache frequent queries in-memory (TTLCache)

### Non-goals (Phase 1-2; some implemented in Phase 3)

- Semantic broadcasting / fan-out
- **Phase 3: SQLite db layer (provenance, agent registry, L2 cache)**
- Chunking (save short entries only, ≤256 word pieces)
- **Phase 3: Cache L2 persistent disk (SQLite-backed, 24h TTL)**
- Docker, RBAC, auth, scaling

## Architecture Stack (Phase 3)

```
Python 3.13+  │  uv 0.11+
FastMCP       │  MCP SDK ≥1.0.0
ChromaDB      │  PersistentClient
sentence-transformers  │  all-MiniLM-L6-v2 (384d)
cachetools    │  TTLCache (1000 entries, 5min TTL)
pyyaml        │  config.yaml
pytest        │  pytest-asyncio
SQLite3       │  stdlib (provenance, agent registry, L2 cache)
```

## Directory Structure

```
mcp-agora/
├── pyproject.toml
├── config.yaml
├── AGAENTS.md
├── ARCHITECTURE.md
├── agora/
│   ├── __init__.py
│   ├── main.py              # Entry point: `agora` command
│   ├── server.py            # FastMCP server + tool registration
│   ├── config.py            # YAML config loader
│   ├── registry.py          # BackendRegistry (lifecycle, lazy connect)
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py          # BackendConnector ABC
│   │   └── stdio.py         # STDIO subprocess MCP client
│   ├── routing/
│   │   ├── __init__.py
│   │   └── router.py        # Semantic + exact name router
│   ├── embedding/
│   │   ├── __init__.py
│   │   ├── base.py          # Abstract EmbeddingProvider
│   │   └── sentence.py      # sentence-transformers wrapper
│   ├── memory/
│   │   ├── __init__.py
│   │   └── vector_store.py  # ChromaDB PersistentClient wrapper
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── l1_memory.py     # TTLCache in-memory
│   │   └── l2_cache.py      # SQLite-backed persistent cache (Phase 3)
│   └── db/
│       ├── __init__.py
│       └── database.py      # SQLite: agents, provenance, L2 cache (Phase 3)
├── tests/
│   ├── __init__.py
│   ├── test_embedding.py
│   ├── test_memory.py
│   ├── test_cache.py
│   ├── test_l2_cache.py     # L2 persistent cache tests (Phase 3)
│   ├── test_provenance.py   # Provenance + agent registry tests (Phase 3)
│   ├── test_protocol.py
│   ├── test_routing.py
│   ├── test_connectors.py
│   └── test_mcp_smoke.py
└── examples/
    └── config.yaml.example
```

## Implementation Constraints

### FastMCP (NOT low-level Server)

Use `FastMCP` from `mcp.server.fastmcp`. Do NOT use `mcp.server.Server` directly in Phase 1, 2, or 3.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Agora")

@mcp.tool()
def agora_save(content: str, tags: list[str] | None = None, agent: str | None = None, session: str | None = None, confidence: float = 0.5) -> dict:
    ...

@mcp.tool()
def agora_query(query: str, top_k: int = 5) -> dict:
    ...

@mcp.tool()
async def agora_route(target: str, tool: str, arguments: dict | None = None) -> dict:
    ...

@mcp.tool()
async def agora_broadcast(tool: str, arguments: dict | None = None) -> dict:
    ...

@mcp.tool()
def agora_backends() -> dict:
    ...

@mcp.tool()
def agora_crossref(query: str = "", entry_id: str = "", top_k: int = 5) -> dict:
    ...

@mcp.tool()
def agora_forget(entry_ids: list[str] | None = None, tags: list[str] | None = None, agent: str | None = None, dry_run: bool = False) -> dict:
    ...

@mcp.tool()
def agora_status() -> dict:
    ...
```

### Embedding

- Model: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- Lazy loading: load model on first call, not on import
- Input limit: 256 word pieces (no chunking in Phase 1)
- Store `~/.cache/agora/models/`

### ChromaDB

- Use `chromadb.PersistentClient(path=...)`
- Default path: `~/.agora/chroma`
- Single collection "knowledge" in Phase 1
- NO duckdb+parquet fallback — if ChromaDB fails, stop and debug
- Router creates its own collection "backends" on warmup for backend description embeddings

### Cache

- Use `cachetools.TTLCache` (NOT `LRUCache` — TTLCache already has TTL built-in)
- Cache key = SHA256 of JSON with ALL params:
  ```python
  cache_key = sha256(json.dumps({
      "tool": "agora.query",
      "collection": "knowledge",
      "query": query,
      "top_k": top_k,
      "model": "all-MiniLM-L6-v2"
  }, sort_keys=True))
  ```
- On `agora.save`: clear ALL query cache (L1 + L2) (simple, safe)

### Config

- `config.yaml` with `pyyaml`
- Use `Path.expanduser()` and `os.path.expandvars()` for all paths (Windows safety)
- Default config minimal:
  ```yaml
  agora:
    name: "Agora"
    version: "0.1.0"
  storage:
    chroma_path: "~/.agora/chroma"
  cache:
    l1_max_entries: 1000
    l1_ttl_seconds: 300
  embedding:
    provider: "sentence-transformers"
    model: "all-MiniLM-L6-v2"
  ```

## Testing Strategy (by priority)

1. **Unit tests** (pytest, no MCP, no subprocess):
   - `test_embedding.py`: dimension = 384, returns list[float], document retrieval order
   - `test_memory.py`: add → query → delete → verify
   - `test_cache.py`: set → get → expire → stats
   - `test_routing.py`: cosine similarity, exact/semantic/no match, warmup
   - `test_l2_cache.py`: L2 set/get/expiry/hit_count/stats/clear (Phase 3)
   - `test_provenance.py`: agent registry, provenance add/get/list/delete (Phase 3)

2. **Integration test** (same process, direct function calls):
   - `test_protocol.py`: call `save_knowledge()` then `query_knowledge()` directly
   - `test_connectors.py`: connector properties, health, disconnect, double connect

3. **MCP smoke test** (via `mcp.ClientSession`):
   - `test_protocol.py`: `tools/list` returns correct tool names, `tools/call` succeeds
   - `test_mcp_smoke.py`: smoke, multiple entries, stress, routing, status, crossref, forget

4. **Manual test** with Claude Code/Codex

Do NOT use timing as a metric in tests (flaky on Windows). Use `cache.stats()["hit_count"]`.

## Command Reference

```bash
# Run
uv run agora

# Test
uv run pytest tests/ -v

# Single test
uv run pytest tests/test_cache.py -v -k "test_hit_count"

# Lint (when added)
uv run ruff check .
```

## Key Decisions (do not change without discussion)

| Decision | Rationale |
|----------|-----------|
| FastMCP not low-level Server | Faster development, cleaner code |
| ChromaDB not SQLite-VSS | More established, better docs |
| no db/ layer in Phase 1 | Avoid premature abstractions |
| cache clear-all on save | Simple, safe, sufficient for Phase 1 |
| no semantic cache | Two similar queries can be semantically different |
| all-MiniLM-L6-v2 | 384d, lightweight, good enough for Phase 1 |
| STDIO only in Phase 1 | Streamable HTTP adds complexity without value yet |
| lazy backend connect | No startup cost for idle backends |
| semantic + exact name router | Exact match tried first, semantic fallback (≥0.5) |

## External MCP Servers

### GitHub MCP (configured in opencode)

The project uses `@modelcontextprotocol/server-github` for GitHub operations.
- Config location: `~/.config/opencode/opencode.jsonc`
- Auth: `GITHUB_TOKEN` env var (set in PowerShell profile via `gh auth token`)
- Profile: `C:\Users\antonio\Documents\WindowsPowerShell\profile.ps1`

### Playwright MCP (configured in opencode)

The `@playwright/mcp` server is available for browser automation.

## Related Documents

- `ARCHITECTURE.md` — Full architecture, rationale, risk analysis, flows
- `config.yaml` — Configuration file
- `pyproject.toml` — Dependencies and build system
