# MCP Agora

**MCP Server with cross-agent persistent memory for AI agent fleets.**

Agora is a local, Python-only MCP server that gives your AI agents (Claude Code, Codex, ChatGPT, Gemini CLI) a **shared persistent memory**. Knowledge saved by one agent is immediately available to all others — no more repeating work, no more isolated sessions.

```bash
uv run agora
```

---

## Features

## Features

### Phase 1 — Core Memory

- `agora_save` — Save knowledge with semantic embeddings (tags optional)
- `agora_query` — Semantic search across all saved knowledge (top-k results)
- `agora_status` — Server stats: memory count, agents, cache, backends, health, DB size
- **Persistent ChromaDB storage** (data survives restarts)
- **L1 in-memory cache** (TTLCache, 1000 entries, 5min TTL, full-param SHA-256 cache key)
- **Cache invalidation** on save (clear-all L1+L2, safe strategy)
- **Fully local embeddings** (sentence-transformers all-MiniLM-L6-v2, 384d, no API key)
- **Background warmup** (model loads in daemon thread, server starts instantly)
- **WarmingUpError grace** (tools return friendly message if model not yet loaded)

### Phase 2 — Routing & Backend Connectors

- `agora_route` — Route tool calls to external MCP servers by name or semantic match
- `agora_broadcast` — Call a tool on ALL backends in parallel via asyncio.gather
- `agora_backends` — List configured backends with connection status
- **Semantic router** — Routes to backends via cosine similarity on description embeddings (threshold >= 0.5)
- **Exact-name router** — Case-insensitive exact match tried first, falls back to semantic
- **STDIO connector** — Subprocess MCP client via `stdio_client` + `ClientSession`, lazy connection on first use
- **HTTP connector** — Streamable HTTP MCP client for remote servers
- **BackendRegistry** — Lifecycle management: register from config, lazy connect, disconnect_all on shutdown
- **Config-driven backends** — Declare external MCP servers in `config.yaml` with env var expansion (`${GITHUB_TOKEN}`)
- **GitHub MCP** — Pre-configured: issues, PRs, repos, code search, commits
- **Playwright MCP** — Pre-configured: browser automation (navigate, click, screenshot), read_only

### Phase 3 — Cross-agent Memory

- `agora_crossref` — Cross-reference entries by query or entry_id (groups by agent)
- `agora_forget` — Delete entries by ID, tags, or agent (supports dry_run)
- **SQLite provenance** — Who saved what, when, with what confidence
- **L2 persistent cache** — SQLite-backed, 24h TTL, survives restarts
- **3-tier cache cascade** — L1 (TTLCache) → L2 (SQLite) → ChromaDB

### Phase 4 — Robustness

- **Health check** — Backend health monitoring (healthy/unhealthy/dead with 3-failure threshold)
- **Configurable retry** — Per-backend `max_retries` + `retry_delay`
- **Rate limiting** — Per-backend `rate_limit_rps` to prevent API abuse
- **Structured logging** — File-based logging to `~/.agora/logs/agora.log` (configurable via `LOG_LEVEL`)
- **Non-blocking startup** — Background warmup thread + `WarmingUpError` grace on embedding-dependent tools
- **6 graceful degradation tests** — Backend failure, health cascade, retry, rate limit
- **61 tests** across 10 files, all passing

### Planned (Phase 5)

| Feature | Description |
|---------|-------------|
| Quickstart in 3 comandi | One-liner install + run |
| Config YAML fully commented | Every line explained |
| GitHub release | Tagged release, changelog |
| PyPI publication | `pip install mcp-agora` |
| PDF architecture diagram | Visual diagram replacing ASCII |

---

## Architecture

```
┌────────────────────────────────────────────────────┐
│                   TRANSPORT LAYER                   │
│               STDIO (JSON-RPC 2.0)                  │
├────────────────────────────────────────────────────┤
│                   PROTOCOL LAYER                     │
│       tools/list · tools/call · resources/list      │
├────────────────────────────────────────────────────┤
│                   ROUTER LAYER (Fase 2)             │
│   ┌──────────┐  ┌──────────┐                        │
│   │ Semantic │  │  Static  │                        │
│   │  Router  │  │  Router  │                        │
│   └────┬─────┘  └────┬─────┘                        │
│        └──────────────┘                              │
├───────────────────────┴────────────────────────────┤
│                   MEMORY LAYER                       │
│   ┌────────────────────────────────────────────┐    │
│   │  VECTOR INDEX (ChromaDB)                   │    │
│   │  Collection: "knowledge"                    │    │
│   │  384d embeddings, cosine similarity         │    │
│   └────────────────────────────────────────────┘    │
├────────────────────────────────────────────────────┤
│                   CACHE LAYER                        │
│   ┌────────────────────────────────────────────┐    │
│   │  L1: TTLCache (memory, 5min TTL, 1k max)   │    │
│   │  L2: SQLite    (disk,  24h TTL,  10k max)  │    │
│   └────────────────────────────────────────────┘    │
├────────────────────────────────────────────────────┤
│                BACKEND CONNECTORS (Fase 2)           │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│   │ STDIO    │ │ HTTP     │ │ Custom   │            │
│   └──────────┘ └──────────┘ └──────────┘            │
├────────────────────────────────────────────────────┤
│                  EMBEDDING LAYER                     │
│   sentence-transformers (all-MiniLM-L6-v2, 384d)     │
└────────────────────────────────────────────────────┘
```

---

## Quickstart

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) 0.11+

### Install & Run

```bash
# Clone
git clone https://github.com/cioffiAI/mcp-agora.git
cd mcp-agora

# Run (auto-creates .venv + installs dependencies)
uv run agora
```

### Configure as MCP Server

Add to your MCP host config (e.g. `opencode.jsonc`):

```jsonc
{
  "mcp": {
    "agora": {
      "type": "local",
      "command": ["uv", "run", "--directory", "/path/to/mcp-agora", "agora"],
      "enabled": true
    }
  }
}
```

### Usage

```bash
# Save knowledge
uv run python -c "
from agora.server import create_server
"  # or use via MCP tools in your agent
```

Via MCP tools (in any MCP-compatible agent):

**Save:**
```
Call tool: agora_save
  content: "PostgreSQL BRIN indexes are useful for very large tables with correlated data"
  tags: ["postgres", "sql", "performance"]
→ { "saved": true, "id": "mem_20260505_..." }
```

**Query:**
```
Call tool: agora_query
  query: "PostgreSQL indexing performance"
  top_k: 5
→ { "query": "...", "results": [...], "cached": false }
```

**Status:**
```
Call tool: agora_status
→ { "server": "Agora", "memory_entries": 42, "cache_stats": {...}, "backends": {...} }
```

**Route to backend:**
```
Call tool: agora_route
  target: "github"
  tool: "github_search_repositories"
  arguments: { "query": "mcp server" }
→ { "target": "github", "matched_by": "exact_name", "result": { "items": [...] } }
```

**List backends:**
```
Call tool: agora_backends
→ { "backends": [{ "name": "github", "connected": false, "tool_count": 15, ... }] }
```

---

## Configuration

Default `config.yaml` (v0.4.0):

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

backends:
  - name: "github"
    transport: "stdio"
    command: ["npx", "-y", "@modelcontextprotocol/server-github"]
    description: "GitHub API: issues, PRs, repos, code search, commits"
    read_only: false
    timeout_seconds: 15
    max_retries: 3
    retry_delay: 1.0
    rate_limit_rps: 5
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
  - name: "playwright"
    transport: "stdio"
    command: ["npx", "@playwright/mcp@latest"]
    description: "Browser automation: navigate, click, screenshot, forms"
    read_only: true
    timeout_seconds: 30
    max_retries: 2
    retry_delay: 0.5
    rate_limit_rps: 2
```

Override config path: `AGORA_CONFIG=/path/to/config.yaml uv run agora`

---

## Testing

```bash
# All tests
uv run pytest tests/ -v

# Single test
uv run pytest tests/test_cache.py -v -k "test_hit_count"

# MCP smoke tests (real STDIO subprocess)
uv run pytest tests/test_mcp_smoke.py -v
```

**61 tests** across 10 files:

| File | Count | Scope |
|------|-------|-------|
| `test_embedding.py` | 3 | Dimension, vector format, document retrieval order |
| `test_memory.py` | 5 | ChromaDB add, query, delete, multiple docs, integration |
| `test_cache.py` | 5 | TTLCache set, get, expiry, hit_count, clear |
| `test_l2_cache.py` | 7 | L2 SQLite set, get, expiry, hit_count, stats, clear, prune |
| `test_provenance.py` | 7 | Agent registry, provenance add/get/list/delete |
| `test_protocol.py` | 6 | FastMCP tool wiring, save→query, cache hit, provenance |
| `test_routing.py` | 9 | Cosine similarity, exact/semantic/no match, warmup |
| `test_connectors.py` | 8 | Properties, health, disconnect, read-only enforcement |
| `test_graceful.py` | 6 | Backend failure, health cascade, retry, rate limit |
| `test_mcp_smoke.py` | 5 | Full smoke, multiple entries, stress, routing, status |

---

## Project Structure

```
mcp-agora/
├── pyproject.toml              # Dependencies, build config, entry point
├── config.yaml                 # Server configuration (incl. backends)
├── README.md                   # This file
├── AGENTS.md                   # Agent-facing instructions
├── ARCHITECTURE.md             # Full architecture, rationale, risk analysis
├── agora/
│   ├── main.py                 # Entry point: `agora` command
│   ├── server.py               # FastMCP server + tool registration
│   ├── config.py               # YAML config loader (incl. BackendConfig)
│   ├── logging.py              # File-based structured logging
│   ├── registry.py             # BackendRegistry (lifecycle, lazy connect)
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py             # BackendConnector ABC + ReadOnlyBlockedError
│   │   ├── stdio.py            # STDIO subprocess MCP client
│   │   └── http.py             # Streamable HTTP MCP client
│   ├── routing/
│   │   └── router.py           # Semantic + exact name router
│   ├── embedding/
│   │   ├── base.py             # Abstract EmbeddingProvider + WarmingUpError
│   │   └── sentence.py         # sentence-transformers wrapper
│   ├── memory/
│   │   └── vector_store.py     # ChromaDB PersistentClient wrapper
│   ├── cache/
│   │   ├── l1_memory.py        # TTLCache in-memory
│   │   └── l2_cache.py         # SQLite-backed persistent cache
│   └── db/
│       └── database.py         # SQLite: agents, provenance, L2 cache
├── tests/
│   ├── test_embedding.py
│   ├── test_memory.py
│   ├── test_cache.py
│   ├── test_l2_cache.py
│   ├── test_provenance.py
│   ├── test_protocol.py
│   ├── test_routing.py
│   ├── test_connectors.py
│   ├── test_graceful.py
│   ├── test_mcp_smoke.py
│   └── _echo_server.py         # Minimal FastMCP echo server for tests
└── examples/
    └── config.yaml.example
```

---

## Stack

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.13+, uv 0.11+ |
| MCP Framework | FastMCP (mcp SDK ≥1.0.0) |
| Vector Store | ChromaDB (PersistentClient, HNSW index) |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 (384d), lazy-load + background warmup |
| Cache L1 | cachetools TTLCache (1k entries, 5min TTL) |
| Cache L2 | SQLite (10k entries, 24h TTL) |
| Provenance | SQLite (agents, entry provenance) |
| Config | PyYAML (env var expansion `$VAR`) |
| Testing | pytest, pytest-asyncio |

---

## License

MIT
