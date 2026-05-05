# MCP Agora

**MCP Server with cross-agent persistent memory for AI agent fleets.**

Agora is a local, Python-only MCP server that gives your AI agents (Claude Code, Codex, ChatGPT, Gemini CLI) a **shared persistent memory**. Knowledge saved by one agent is immediately available to all others — no more repeating work, no more isolated sessions.

```bash
uv run agora
```

---

## Features

### Implemented (Phase 1)

### Phase 1 — Core Memory

- `agora_save` — Save knowledge with semantic embeddings (tags optional)
- `agora_query` — Semantic search across all saved knowledge (top-k results)
- `agora_status` — Server stats: memory count, cache hit rate, timestamp
- **Persistent ChromaDB storage** (data survives restarts)
- **L1 in-memory cache** (TTLCache, 1000 entries, 5min TTL, full-param cache key)
- **Cache invalidation** on save (clear-all, safe)
- **Fully local embeddings** (sentence-transformers all-MiniLM-L6-v2, 384d, no API key)
- **Lazy model loading** with warmup at server startup

### Phase 2 — Routing & Backend Connectors

- `agora_route` — Route tool calls to external MCP servers by name or semantic match
- `agora_backends` — List configured backends with connection status
- **Semantic router** — Routes to backends via cosine similarity on description embeddings (threshold ≥ 0.5)
- **Exact-name router** — Case-insensitive exact match tried first, falls back to semantic
- **STDIO connector** — Subprocess MCP client via `stdio_client` + `ClientSession`, lazy connection on first use
- **BackendRegistry** — Lifecycle management: register from config, lazy connect, disconnect_all on shutdown
- **Config-driven backends** — Declare external MCP servers in `config.yaml` with env var expansion (`${GITHUB_TOKEN}`)
- **GitHub MCP** — Pre-configured: issues, PRs, repos, code search, commits
- **Playwright MCP** — Pre-configured: browser automation (navigate, click, screenshot)
- **34 tests** (unit + integration + MCP smoke)
- **OpenCode integration** (configured in opencode.jsonc)

### Planned

| Phase | Features | Status |
|-------|----------|--------|
| **3** | Provenance tracking, L2 persistent cache (SQLite), `agora_crossref`, `agora_forget` | 📋 Planned |
| **4** | Health checks, retry/timeout, rate limiting, structured logging | 📋 Planned |
| **5** | Quickstart, examples, GitHub release, PyPI publication | 📋 Planned |

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

Default `config.yaml`:

```yaml
agora:
  name: "Agora"
  version: "0.2.0"

storage:
  chroma_path: "~/.agora/chroma"

cache:
  l1_max_entries: 1000
  l1_ttl_seconds: 300

embedding:
  provider: "sentence-transformers"
  model: "all-MiniLM-L6-v2"

backends:
  - name: "github"
    transport: "stdio"
    command: ["npx", "-y", "@modelcontextprotocol/server-github"]
    description: "GitHub API: issues, PRs, repos, code search, commits"
    read_only: false
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
  - name: "playwright"
    transport: "stdio"
    command: ["npx", "@playwright/mcp@latest"]
    description: "Browser automation: navigate, click, screenshot, forms"
    read_only: false
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

**34 tests** across 7 files:

| File | Count | Scope |
|------|-------|-------|
| `test_embedding.py` | 3 | Dimension, vector format, document retrieval order |
| `test_memory.py` | 5 | ChromaDB add, query, delete, multiple docs, integration |
| `test_cache.py` | 5 | TTLCache set, get, expiry, hit_count, clear |
| `test_protocol.py` | 4 | FastMCP tool wiring, save→query roundtrip, cache hit |
| `test_routing.py` | 8 | Cosine similarity, exact/semantic/no match, warmup |
| `test_connectors.py` | 4 | Properties, health, disconnect, double connect |
| `test_mcp_smoke.py` | 5 | Full smoke, multiple entries, stress, routing, status |

---

## Project Structure

```
mcp-agora/
├── pyproject.toml              # Dependencies, build config, entry point
├── config.yaml                 # Server configuration (incl. backends)
├── AGENTS.md                   # Agent-facing instructions
├── ARCHITECTURE.md             # Full architecture, rationale, risk analysis
├── agora/
│   ├── main.py                 # Entry point: `agora` command
│   ├── server.py               # FastMCP server + tool registration
│   ├── config.py               # YAML config loader (incl. BackendConfig)
│   ├── registry.py             # BackendRegistry (lifecycle, lazy connect)
│   ├── connectors/
│   │   ├── base.py             # BackendConnector ABC
│   │   └── stdio.py            # STDIO subprocess MCP client
│   ├── routing/
│   │   └── router.py           # Semantic + exact name router
│   ├── embedding/
│   │   ├── base.py             # Abstract EmbeddingProvider
│   │   └── sentence.py         # sentence-transformers wrapper
│   ├── memory/
│   │   └── vector_store.py     # ChromaDB PersistentClient wrapper
│   └── cache/
│       └── l1_memory.py        # TTLCache in-memory
├── tests/
│   ├── test_embedding.py
│   ├── test_memory.py
│   ├── test_cache.py
│   ├── test_protocol.py
│   ├── test_routing.py
│   ├── test_connectors.py
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
| Vector Store | ChromaDB (PersistentClient) |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 (384d) |
| Cache L1 | cachetools TTLCache (1k entries, 5min TTL) |
| Config | PyYAML |
| Testing | pytest, pytest-asyncio |

---

## License

MIT
