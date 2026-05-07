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

### Non-goals

- Semantic broadcasting / fan-out
- Chunking (save short entries only, ≤256 word pieces)
- Docker, RBAC, auth, scaling

## Architecture Stack (corrente)

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
├── README.md
├── AGENTS.md
├── ARCHITECTURE.md
├── agora/
│   ├── __init__.py
│   ├── main.py              # Entry point: `agora` command
│   ├── server.py            # FastMCP server + 8 tool registration
│   ├── config.py            # YAML config loader
│   ├── logging.py           # File-based structured logging
│   ├── registry.py          # BackendRegistry (lifecycle, lazy connect)
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py          # BackendConnector ABC + ReadOnlyBlockedError
│   │   ├── stdio.py         # STDIO subprocess MCP client
│   │   └── http.py          # Streamable HTTP MCP client
│   ├── routing/
│   │   ├── __init__.py
│   │   └── router.py        # Semantic + exact name router
│   ├── embedding/
│   │   ├── __init__.py
│   │   ├── base.py          # Abstract EmbeddingProvider + WarmingUpError
│   │   └── sentence.py      # sentence-transformers wrapper (sync preload, local_files_only, 60s timeout)
│   ├── memory/
│   │   ├── __init__.py
│   │   └── vector_store.py  # ChromaDB PersistentClient wrapper
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── l1_memory.py     # TTLCache in-memory
│   │   └── l2_cache.py      # SQLite-backed persistent cache
│   └── db/
│       ├── __init__.py
│       └── database.py      # SQLite: agents, provenance, L2 cache
├── tests/
│   ├── __init__.py
│   ├── test_embedding.py
│   ├── test_memory.py
│   ├── test_cache.py
│   ├── test_l2_cache.py     # L2 persistent cache tests
│   ├── test_provenance.py   # Provenance + agent registry tests
│   ├── test_protocol.py
│   ├── test_routing.py
│   ├── test_connectors.py
│   ├── test_graceful.py     # Health check, retry, rate limit tests
│   ├── test_mcp_smoke.py
│   └── _echo_server.py      # Minimal FastMCP echo server for tests
└── examples/
    └── config.yaml.example
```

## Implementation Constraints

### FastMCP (NOT low-level Server)

Use `FastMCP` from `mcp.server.fastmcp`. Do NOT use `mcp.server.Server` directly.

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
- **Synchronous preload**: model loaded in `create_server()` before `mcp.run()` — blocks startup ~13s, then all calls instant
- `local_files_only=True` — skips HuggingFace Hub HTTP requests (critical on Windows without `HF_TOKEN`: cuts load from 17-27s to ~13s, avoids rate-limiting)
- `_ensure_ready()` with 60s wait: safety net if model not ready (e.g. concurrent lazy load); raises `WarmingUpError` only after 60s timeout
- Non-blocking lock: `threading.Lock.acquire(blocking=False)` — no deadlock on concurrent loads
- Input limit: 256 word pieces (no chunking)
- Store `~/.cache/agora/models/`
- **DO NOT use daemon thread for warmup** — unreliable on Windows subprocess (thread never completes, causes permanent "warming up")

### ChromaDB

- Use `chromadb.PersistentClient(path=...)`
- Default path: `~/.agora/chroma`
- Single collection "knowledge"
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
- Default config:
  ```yaml
  agora:
    name: "Agora"
    version: "0.4.0"
  storage:
    chroma_path: "~/.agora/chroma"
    db_path: "~/.agora/agora.db"
  cache:
    l1_max_entries: 1000
    l1_ttl_seconds: 300
    l2_max_entries: 10000
    l2_ttl_seconds: 86400
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
   - `test_l2_cache.py`: L2 set/get/expiry/hit_count/stats/clear
   - `test_provenance.py`: agent registry, provenance add/get/list/delete

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
# Run (from source)
uv run agora

# Run (installed tool, recommended for MCP hosts)
agora

# Test
uv run pytest tests/ -v

# Single test
uv run pytest tests/test_cache.py -v -k "test_hit_count"

# Lint
uv run ruff check .
uv run ruff format --check .

# Format
uv run ruff format .
```

## Key Decisions (do not change without discussion)

| Decision | Rationale |
|----------|-----------|
| FastMCP not low-level Server | Faster development, cleaner code |
| ChromaDB not SQLite-VSS | More established, better docs |
| SQLite per provenance + L2 | Relational metadata separate from vector index |
| cache clear-all on save | Simple, safe, sufficient |
| no semantic cache | Two similar queries can be semantically different |
| all-MiniLM-L6-v2 | 384d, lightweight, good enough |
| STDIO + HTTP connectors | STDIO for local agents, Streamable HTTP for remote |
| lazy backend connect | No startup cost for idle backends |
| semantic + exact name router | Exact match tried first, semantic fallback (≥0.5) |
| sync preload, not daemon thread | Daemon threads unreliable on Windows under subprocess; sync preload guarantees model is ready before mcp.run() |
| local_files_only=True | Cuts model load from 17-27s to ~13s by skipping HF Hub HTTP; avoids rate-limiting without HF_TOKEN |

## External MCP Servers

### GitHub MCP (configured in opencode)

The project uses `@modelcontextprotocol/server-github` for GitHub operations.
- Config location: `~/.config/opencode/opencode.jsonc`
- Auth: `GITHUB_TOKEN` env var (set in PowerShell profile via `gh auth token`)
- Profile: `C:\Users\antonio\Documents\WindowsPowerShell\profile.ps1`

### Playwright MCP (configured in opencode)

The `@playwright/mcp` server is available for browser automation.

### Agora MCP (opencode)

Agora runs via `uv tool install mcp-agora` — the binary is at `~/.local/bin/agora.exe`.
- Config: `command: ["agora"]` in `opencode.jsonc`
- Config file: `~/.agora/config.yaml` (copied from project root on install)
- Override via: `AGORA_CONFIG=/path/to/config.yaml`

## Troubleshooting

### opencode "Not connected" error
Known **opencode MCP client bug** (#26128) on Windows. The Agora server itself works fine — verify with manual MCP protocol test:
```bash
uv run python -c "import subprocess,json,time;p=subprocess.Popen(['agora.exe'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);time.sleep(20);p.stdin.write(json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}})+'\n');p.stdin.flush();print(json.loads(p.stdout.readline()));p.terminate()"
```

### "Server is warming up" after timeout
The embedding model took >60s to load. Common causes:
1. HuggingFace Hub rate-limiting (no `HF_TOKEN`) → fix: ensure `local_files_only=True` in sentence.py
2. First run downloading model → wait longer (subsequent runs use cache at ~13s)

### UV tool install corruption
`uv tool install --reinstall` can corrupt packages if the uninstall phase times out (leaves packages in inconsistent state, e.g. `transformers.__version__` import error). Solution: always do `uv tool uninstall mcp-agora` first, then `uv tool install .`

### ChromaDB lock / zombie process
A stale `agora.exe` process holds the SQLite lock on `~/.agora/chroma/`. New instances fail silently. Check:
```powershell
Get-Process -Name "agora" -ErrorAction SilentlyContinue
# Kill if stale: Stop-Process -Name "agora" -Force
```

## Related Documents

- `ARCHITECTURE.md` — Full architecture, rationale, risk analysis, flows
- `config.yaml` — Configuration file
- `pyproject.toml` — Dependencies and build system
