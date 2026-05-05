# MCP Agora

**MCP Server with cross-agent persistent memory for AI agent fleets.**

Agora is a local, Python-only MCP server that gives your AI agents (Claude Code, Codex, ChatGPT, Gemini CLI) a **shared persistent memory**. Knowledge saved by one agent is immediately available to all others — no more repeating work, no more isolated sessions.

```bash
uv run agora
```

---

## Features

### Implemented (Phase 1)

- `agora_save` — Save knowledge with semantic embeddings (tags optional)
- `agora_query` — Semantic search across all saved knowledge (top-k results)
- `agora_status` — Server stats: memory count, cache hit rate, timestamp
- **Persistent ChromaDB storage** (data survives restarts)
- **L1 in-memory cache** (TTLCache, 1000 entries, 5min TTL, full-param cache key)
- **Cache invalidation** on save (clear-all, safe)
- **Fully local embeddings** (sentence-transformers all-MiniLM-L6-v2, 384d, no API key)
- **Lazy model loading** with warmup at server startup (no blocking on first tool call)
- **MCP STDIO transport** (drop-in compatible with any MCP host)
- **20 tests** (unit + integration + MCP smoke)
- **OpenCode integration** (configured in opencode.jsonc)

### Planned

| Phase | Features | Status |
|-------|----------|--------|
| **2** | Semantic router, static router, STDIO connector, `agora_route`, `agora_backends`, read-only/mutative distinction | 🔜 Planned |
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
→ { "server": "Agora", "memory_entries": 42, "cache_stats": {...} }
```

---

## Configuration

Default `config.yaml`:

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

**20 tests** across 5 files:

| File | Count | Scope |
|------|-------|-------|
| `test_embedding.py` | 3 | Dimension, vector format, document retrieval order |
| `test_memory.py` | 5 | ChromaDB add, query, delete, multiple docs, integration |
| `test_cache.py` | 5 | TTLCache set, get, expiry, hit_count, clear |
| `test_protocol.py` | 4 | FastMCP tool wiring, save→query roundtrip, cache hit |
| `test_mcp_smoke.py` | 3 | MCP STDIO: full smoke, multiple entries, 15-entry stress |

---

## Project Structure

```
mcp-agora/
├── pyproject.toml           # Dependencies, build config, entry point
├── config.yaml              # Server configuration
├── AGENTS.md                # Agent-facing instructions
├── ARCHITECTURE.md          # Full architecture, rationale, risk analysis
├── agora/
│   ├── main.py              # Entry point: `agora` command
│   ├── server.py            # FastMCP server + tool registration
│   ├── config.py            # YAML config loader
│   ├── embedding/
│   │   ├── base.py          # Abstract EmbeddingProvider
│   │   └── sentence.py      # sentence-transformers wrapper
│   ├── memory/
│   │   └── vector_store.py  # ChromaDB PersistentClient wrapper
│   └── cache/
│       └── l1_memory.py     # TTLCache in-memory
├── tests/
│   ├── test_embedding.py
│   ├── test_memory.py
│   ├── test_cache.py
│   ├── test_protocol.py
│   └── test_mcp_smoke.py
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
