#!/usr/bin/env python3
"""Generate MCP Agora tesina PDF in Italian and English."""

import os

from fpdf import FPDF

DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(DOCS_DIR)


ARCH_DIAGRAM = r"""
 +------------------------------------------------------------------+
 |                     TRANSPORT LAYER                              |
 |  STDIO (locale)  |  Streamable HTTP (remoto)                     |
 |  JSON-RPC 2.0 over stdin/stdout or HTTP POST/SSE                 |
 +------------------------------------------------------------------+
 |                     PROTOCOL LAYER                                |
 |  MCP Primitives: tools/list, tools/call                          |
 +------------------------------------------------------------------+
 |                     ROUTER LAYER                                  |
 |   +----------+  +----------+                                      |
 |   | Semantic |  |  Exact   |                                      |
 |   |  Router  |  |  Name    |                                      |
 |   +----+-----+  +----+-----+                                      |
 |        |             |                                            |
 |        +------+------+                                            |
 +---------------+----------------------------------------------------+
 |                     MEMORY LAYER                                  |
 |  +----------------------------------------------------------+    |
 |  |  VECTOR INDEX (ChromaDB)                                 |    |
 |  |  Collection: "knowledge"  |  384d embeddings              |    |
 |  |  Space: cosine                                           |    |
 |  +----------------------------------------------------------+    |
 |  +----------------------------------------------------------+    |
 |  |  RELATIONAL DB (SQLite3)                                 |    |
 |  |  Tables: agents | provenance | l2_cache                  |    |
 |  +----------------------------------------------------------+    |
 +------------------------------------------------------------------+
 |                     CACHE LAYER                                   |
 |  L1: TTLCache (memory, 5min TTL, 1000 max)                      |
 |  L2: SQLite    (disk,  24h TTL, 10000 max)                      |
 |  Cascade: L1 -> L2 -> ChromaDB                                   |
 +------------------------------------------------------------------+
 |                     BACKEND CONNECTOR LAYER                       |
 |  +----------+ +----------+ +----------+ +----------+             |
 |  |  STDIO   | |  HTTP    | | GitHub   | |Playwright|             |
 |  | Connector| | Connector| |  MCP     | |  MCP     |             |
 |  +----------+ +----------+ +----------+ +----------+             |
 |  Lazy connect | Read-only enforcement | Timeout: 30s             |
 +------------------------------------------------------------------+
 |                     EMBEDDING LAYER                               |
 |  sentence-transformers all-MiniLM-L6-v2 (384 dimensioni)         |
 |  Lazy loading | Cache: ~/.cache/agora/models/ | Warmup all'avvio |
 +------------------------------------------------------------------+
"""

TOOLS_TABLE = [
    ("Tool", "Parametri", "Comportamento", "Cache"),
    (
        "agora_save",
        "content, tags, agent, session, confidence",
        "Salva conoscenza in ChromaDB + provenance in SQLite. Registra agente.",
        "Clear L1+L2",
    ),
    ("agora_query", "query, top_k (=5)", "Ricerca semantica. Cascade: L1 -> L2 -> ChromaDB.", "Popola L1+L2 su miss"),
    ("agora_route", "target, tool, arguments", "Routing a backend MCP. Exact match -> semantic (>=0.5).", "No"),
    (
        "agora_broadcast",
        "tool, arguments",
        "Broadcast parallelo (asyncio.gather) a tutti i backend. Solo read-only.",
        "No",
    ),
    ("agora_backends", "(none)", "Lista backend configurati + stato connessione.", "No"),
    (
        "agora_crossref",
        "query, entry_id, top_k",
        "Correlazioni cross-agente. Per query: raggruppa per agente. Per ID: trova entry correlate.",
        "No",
    ),
    (
        "agora_forget",
        "entry_ids, tags, agent, dry_run",
        "Elimina memoria. Filtri compositi. dry_run preview. Clear L1+L2.",
        "Clear L1+L2",
    ),
    ("agora_status", "(none)", "Statistiche: entry, agenti, cache L1+L2, backend, db_size.", "No"),
]

DECISIONS_TABLE = [
    ("Decisione", "Razionale"),
    ("FastMCP (non low-level Server)", "Sviluppo piu rapido, codice piu pulito"),
    ("ChromaDB (non SQLite-VSS)", "Piu maturo, documentazione migliore"),
    ("Cache clear-all on save", "Semplice, sicuro, sufficiente per MVP"),
    ("Nessuna semantic cache", "Due query simili possono essere op. diverse"),
    ("all-MiniLM-L6-v2", "384d, leggero, sufficiente per MVP"),
    ("Lazy backend connect", "Nessun costo startup per backend idle"),
    ("Routing: exact -> semantic (>=0.5)", "Exact match tentato prima, fallback semantico"),
    ("Read-only prefix heuristic", "list_, get_, fetch_, read_, search_, find_..."),
    ("SQLite connection per-call", "Thread-safe, non ottimizzato per alta concorrenza"),
    ("Cosine similarity manuale (no numpy)", "Zero dipendenze esterne per routing"),
]

DIR_STRUCTURE = """
mcp-agora/
|-- pyproject.toml              # Dipendenze, build, entry point "agora"
|-- config.yaml                 # Configurazione server + backend
|-- agora/
|   |-- main.py                 # Entry point
|   |-- server.py               # FastMCP + 8 tools
|   |-- config.py               # YAML loader
|   |-- registry.py             # BackendRegistry
|   |-- connectors/
|   |   |-- base.py             # BackendConnector ABC
|   |   |-- stdio.py            # StdioConnector
|   |   +-- http.py             # HttpConnector
|   |-- routing/
|   |   +-- router.py           # Semantic + exact router
|   |-- embedding/
|   |   |-- base.py             # EmbeddingProvider ABC
|   |   +-- sentence.py         # sentence-transformers
|   |-- memory/
|   |   +-- vector_store.py     # ChromaDB wrapper
|   |-- cache/
|   |   |-- l1_memory.py        # TTLCache
|   |   +-- l2_cache.py         # SQLite cache
|   +-- db/
|       +-- database.py         # SQLite schema + ops
|-- tests/
|   |-- test_embedding.py       # 3 tests
|   |-- test_memory.py          # 5 tests
|   |-- test_cache.py           # 5 tests
|   |-- test_l2_cache.py        # 7 tests
|   |-- test_provenance.py      # 7 tests
|   |-- test_protocol.py        # 6 tests
|   |-- test_routing.py         # 8 tests
|   |-- test_connectors.py      # 9 tests
|   |-- test_mcp_smoke.py       # 8 tests
|   +-- _echo_server.py
|-- docs/
|   +-- generate_pdf.py
|-- README.md
+-- LICENSE (MIT)
"""

SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    agent_type      TEXT DEFAULT 'unknown',
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    sessions_count  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS provenance (
    entry_id        TEXT NOT NULL,
    source_agent    TEXT NOT NULL,
    source_session  TEXT NOT NULL,
    confidence      REAL DEFAULT 0.5,
    created_at      TEXT NOT NULL,
    PRIMARY KEY (entry_id, source_agent, source_session)
);

CREATE TABLE IF NOT EXISTS l2_cache (
    cache_key       TEXT PRIMARY KEY,
    result_json     TEXT NOT NULL,
    ttl_seconds     INTEGER NOT NULL DEFAULT 86400,
    hit_count       INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL
);
"""

CONFIG_YAML_EXAMPLE = r"""
agora:
  name: "Agora"
  version: "0.3.0"

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
    description: "GitHub API: issues, PRs, repos, code search"
    read_only: false
    timeout_seconds: 15
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
"""

COMMIT_LOG = """
14dbdc5  Initial commit: MCP Agora Phase 1 complete
e209f40  Add MIT License
005590b  Add agora usage instructions to AGENTS.md
5a64014  Phase 2: Routing + Backend Connectors
12e54ae  docs: update README and AGENTS.md for Phase 2
0c36648  feat: HTTP connector, read_only, broadcast, timeout
b03abbe  fix: ReadOnlyBlockedError public, parallel broadcast
dab75a2  feat: Phase 3 cross-agent memory
49cb34d  WIP on master: Phase 3
c2ee10c  index on master: Phase 3
"""

TEST_FILES = [
    ("test_embedding.py", 3, "Unit: dimensione 384, formato vettore, retrieval order"),
    ("test_memory.py", 5, "Unit: ChromaDB add/query/delete/multi/integration"),
    ("test_cache.py", 5, "Unit: L1 set/get/expiry/hit_count/clear"),
    ("test_l2_cache.py", 7, "Unit: L2 set/get/miss/expiry/hit_count/stats/clear/prune"),
    ("test_provenance.py", 7, "Unit: agent registry + provenance lifecycle"),
    ("test_protocol.py", 6, "Integration: FastMCP wiring, save->query, cache hit, L2 fallback"),
    ("test_routing.py", 8, "Unit: cosine similarity, exact/semantic/no match, warmup"),
    ("test_connectors.py", 9, "Unit: STDIO/HTTP properties, timeout, health, read-only"),
    ("test_mcp_smoke.py", 8, "Smoke: MCP ClientSession, full stack"),
]

STACK_TABLE = [
    ("Componente", "Tecnologia", "Versione"),
    ("Runtime", "Python", ">=3.13"),
    ("Package Manager", "uv", ">=0.11"),
    ("MCP Framework", "FastMCP (mcp SDK)", ">=1.0.0"),
    ("Vector Store", "ChromaDB (PersistentClient)", "latest"),
    ("Embeddings", "sentence-transformers", ">=3.0.0"),
    ("Modello Embedding", "all-MiniLM-L6-v2", "384d"),
    ("Cache L1", "cachetools TTLCache", "latest"),
    ("Cache L2 / DB", "SQLite3 (stdlib)", "built-in"),
    ("Config", "PyYAML", "latest"),
    ("HTTP Client", "httpx", "latest"),
    ("PDF Generation", "fpdf2", "2.8.7"),
    ("Testing", "pytest + pytest-asyncio", ">=9.0.3"),
]


class AgoraPDF(FPDF):
    def __init__(self, lang="it"):
        super().__init__()
        self.lang = lang
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() <= 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 6, "MCP Agora  --  " + ("Tesina" if self.lang == "it" else "Thesis"), align="L")
        self.cell(0, 6, f"Pagina {self.page_no()}/{{nb}}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(10, 14, 200, 14)
        self.ln(4)

    def footer(self):
        pass

    def title_page(self):
        self.add_page()
        self.ln(50)
        self.set_font("Helvetica", "B", 28)
        self.cell(0, 14, "MCP Agora", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 16)
        subtitle_it = "Server MCP con memoria persistente cross-agente per flotte di agenti AI"
        subtitle_en = "MCP Server with cross-agent persistent memory for AI agent fleets"
        self.cell(0, 10, subtitle_it if self.lang == "it" else subtitle_en, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(10)
        self.set_font("Helvetica", "I", 11)
        self.cell(
            0, 8, "Antonio Cioffi" if self.lang == "it" else "Antonio Cioffi", align="C", new_x="LMARGIN", new_y="NEXT"
        )
        self.cell(0, 8, "2025" if self.lang == "it" else "2025", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(15)
        self.set_font("Helvetica", "", 10)
        abstract_it = (
            "MCP Agora e' un progetto portfolio/learning che implementa un MCP Server "
            "(Model Context Protocol) con memoria persistente cross-agente per flotte di agenti AI personali. "
            "Utilizza ChromaDB per indicizzazione vettoriale, sentence-transformers per embedding semantici "
            "(modello all-MiniLM-L6-v2, 384 dimensioni), SQLite per metadati e cache persistente, "
            "e FastMCP per l'esposizione di 8 tool MCP. L'architettura e' organizzata in 7 layer "
            "(Transport, Protocol, Router, Memory, Cache, Backend Connector, Embedding) con routing "
            "semantico a backend MCP esterni (GitHub, Playwright). Il progetto conta 55 test automatici "
            "distribuiti su 9 file, zero mock, con ChromaDB e SQLite reali in directory isolate."
        )
        abstract_en = (
            "MCP Agora is a portfolio/learning project implementing an MCP Server "
            "(Model Context Protocol) with cross-agent persistent memory for personal AI agent fleets. "
            "It uses ChromaDB for vector indexing, sentence-transformers for semantic embeddings "
            "(all-MiniLM-L6-v2 model, 384 dimensions), SQLite for metadata and persistent cache, "
            "and FastMCP to expose 8 MCP tools. The architecture is organized into 7 layers "
            "(Transport, Protocol, Router, Memory, Cache, Backend Connector, Embedding) with semantic "
            "routing to external MCP backends (GitHub, Playwright). The project has 55 automated tests "
            "across 9 files, zero mocks, using real ChromaDB and SQLite in isolated temp directories."
        )
        self.multi_cell(0, 5, abstract_it if self.lang == "it" else abstract_en, align="C")
        self.ln(5)
        self.set_font("Helvetica", "I", 9)
        self.cell(0, 6, "Repository: https://github.com/cioffiAI/mcp-agora", align="C", new_x="LMARGIN", new_y="NEXT")

    def section(self, num, title):
        self.set_font("Helvetica", "B", 14)
        self.ln(4)
        self.cell(0, 8, f"{num}. {title}", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def subsection(self, num, title):
        self.set_font("Helvetica", "B", 11)
        self.ln(2)
        self.cell(0, 7, f"{num}  {title}", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def paragraph(self, text):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def bullet(self, text, indent=15):
        self.set_font("Helvetica", "", 10)
        x = self.get_x()
        self.set_x(x + indent)
        self.cell(4, 5, "-")
        self.multi_cell(0, 5, text)
        self.ln(0.5)

    def code(self, text):
        self.set_font("Courier", "", 8)
        self.ln(2)
        lines = text.strip("\n").split("\n")
        line_height = 4
        block_height = len(lines) * line_height + 6
        if self.get_y() + block_height > self.h - 25:
            self.add_page()
        y_start = self.get_y()
        self.rect(12, y_start, 186, block_height)
        self.set_xy(14, y_start + 3)
        for line in lines:
            display = line if line.strip() else " "
            self.cell(0, line_height, display, new_x="LMARGIN", new_y="NEXT")
            self.set_x(14)
        self.ln(4)

    def data_table(self, headers, rows, col_widths=None):
        if col_widths is None:
            col_widths = [190 / len(headers)] * len(headers)
        line_h = 5
        font_size = 8
        self.set_font("Helvetica", "B", font_size)
        y0 = self.get_y()
        col_x = [10]
        for w in col_widths[:-1]:
            col_x.append(col_x[-1] + w)
        for i, h in enumerate(headers):
            self.set_xy(col_x[i], y0)
            self.cell(col_widths[i], line_h, h, border=1)
        self.set_font("Helvetica", "", font_size)
        for row in rows:
            y0 = self.get_y()
            n_lines = 1
            for i, cell_txt in enumerate(row):
                lines_needed = max(1, len(cell_txt) * self.get_string_width("a") // col_widths[i] + 1)
                n_lines = max(n_lines, lines_needed)
            row_h = max(line_h, n_lines * line_h)
            if y0 + row_h > self.h - 25:
                self.add_page()
                y0 = self.get_y()
                self.set_font("Helvetica", "B", font_size)
                for i, h in enumerate(headers):
                    self.set_xy(col_x[i], y0)
                    self.cell(col_widths[i], line_h, h, border=1)
                self.set_font("Helvetica", "", font_size)
                self.set_xy(col_x[0], y0 + line_h)
            for i, cell_txt in enumerate(row):
                self.set_xy(col_x[i], y0)
                self.multi_cell(col_widths[i], line_h, cell_txt, border=1)
            self.set_y(y0 + row_h)
        self.ln(3)

    def simple_table(self, headers, rows, col_widths=None):
        if col_widths is None:
            col_widths = [190 / len(headers)] * len(headers)
        line_h = 5
        font_size = 8
        x_start = 10
        self.set_font("Helvetica", "B", font_size)
        y0 = self.get_y()
        if y0 + (len(rows) + 2) * line_h > self.h - 25:
            self.add_page()
            y0 = self.get_y()
        for i, h in enumerate(headers):
            self.set_xy(x_start + sum(col_widths[:i]), y0)
            self.cell(col_widths[i], line_h, h, border=1)
        self.set_font("Helvetica", "", font_size)
        for row in rows:
            y0 = self.get_y()
            for i, cell_txt in enumerate(row):
                self.set_xy(x_start + sum(col_widths[:i]), y0)
                self.cell(col_widths[i], line_h, cell_txt, border=1)
        self.ln(3)

    def write_document(self):
        is_it = self.lang == "it"

        def _(it, en):
            return it if is_it else en

        # --- Title ---
        self.title_page()

        # --- 1. Introduzione ---
        self.section(1, _("Introduzione e Obiettivi", "Introduction and Goals"))
        self.paragraph(
            _(
                "MCP Agora e' un progetto portfolio/learning che implementa un MCP Server "
                "(Model Context Protocol) con memoria persistente cross-agente per flotte di agenti AI personali. "
                "Nasce dall'esigenza reale di risolvere un problema concreto: gli agenti AI moderni (Claude Code, "
                "Codex CLI, ChatGPT, Gemini CLI) operano in sessioni isolate, senza memoria condivisa. "
                "Ogni agente ripete ricerche, ricontesta informazioni e duplica lavoro che "
                "un altro agente ha gia' fatto.",
                "MCP Agora is a portfolio/learning project implementing an MCP Server "
                "(Model Context Protocol) with cross-agent persistent memory for personal AI agent fleets. "
                "It stems from a real need to solve a concrete problem: modern AI agents (Claude Code, "
                "Codex CLI, ChatGPT, Gemini CLI) operate in isolated sessions with no shared memory. "
                "Each agent repeats searches, re-contextualizes information, and duplicates work "
                "that another agent has already done.",
            )
        )

        self.subsection("1.1", _("Obiettivi di Prodotto", "Product Goals"))
        for goal in [
            _(
                "Un agente salva conoscenza -> un altro agente la recupera (zero duplicazione)",
                "One agent saves knowledge -> another retrieves it (zero duplication)",
            ),
            _(
                "Una query gia' fatta -> risposta cached (zero ricalcolo)",
                "A query already made -> cached response (zero recomputation)",
            ),
            _(
                "Un errore gia' fatto -> non si ripete (memoria delle decisioni)",
                "A mistake already made -> not repeated (decision memory)",
            ),
            _(
                "4+ agenti condividono contesto senza configurazioni individuali",
                "4+ agents sharing context without individual configuration",
            ),
        ]:
            self.bullet(goal)

        self.subsection("1.2", _("Obiettivi di Apprendimento", "Learning Goals"))
        for goal in [
            _(
                "MCP Protocol deep dive: implementazione MCP Server compliant con SDK ufficiale",
                "MCP Protocol deep dive: compliant MCP Server implementation using official SDK",
            ),
            _(
                "Vector search & embeddings: integrazione ChromaDB + sentence-transformers",
                "Vector search & embeddings: ChromaDB + sentence-transformers integration",
            ),
            _(
                "System design a layer: architettura modulare con 7 layer separati e interfacce astratte",
                "Layered system design: modular architecture with 7 separate layers and abstract interfaces",
            ),
            _(
                "Async Python: asyncio per concorrenza su MCP transport",
                "Async Python: asyncio for MCP transport concurrency",
            ),
            _(
                "SQLite avanzato: schema relazionale per metadati, provenance, analytics",
                "Advanced SQLite: relational schema for metadata, provenance, analytics",
            ),
            _(
                "Caching strategies: TTLCache in-memory + SQLite persistente",
                "Caching strategies: in-memory TTLCache + persistent SQLite",
            ),
        ]:
            self.bullet(goal)

        self.subsection("1.3", _("Posizionamento", "Positioning"))
        self.paragraph(
            _(
                "Agora non compete con progetti enterprise come ContextForge (IBM), MetaMCP, AutoMem o "
                "mcp-memory-service. E' un progetto portfolio che dimostra competenza su AI infrastructure, "
                "MCP protocol, vector search, semantic routing e system design, risolvendo un problema reale "
                "nei workflow personali con agenti. Il suo valore non e' nell'originalita' del concetto, "
                "ma nella qualita' dell'esecuzione: stack 2026 (MCP, vettori, embedding), architettura pulita "
                "(7 layer, dipendenze astratte, testabile), e problematica reale (memoria isolata tra agenti).",
                "Agora does not compete with enterprise projects like ContextForge (IBM), MetaMCP, AutoMem, or "
                "mcp-memory-service. It is a portfolio project demonstrating competence in AI infrastructure, "
                "MCP protocol, vector search, semantic routing, and system design, solving a real problem "
                "in personal agent workflows. Its value lies not in concept originality, "
                "but in execution quality: 2026 stack (MCP, vectors, embedding), clean architecture "
                "(7 layers, abstract dependencies, testable), and a real problem (isolated agent memory).",
            )
        )

        # --- 2. Stack Tecnologico ---
        self.section(2, _("Stack Tecnologico", "Technology Stack"))
        self.paragraph(
            _(
                "Il progetto e' interamente sviluppato in Python 3.13+ con uv come package manager. "
                "La tabella seguente riassume i componenti principali dello stack.",
                "The project is entirely developed in Python 3.13+ with uv as package manager. "
                "The following table summarizes the main stack components.",
            )
        )
        self.simple_table(STACK_TABLE[0], STACK_TABLE[1:], col_widths=[50, 80, 60])

        self.subsection("2.1", _("Scelte Tecnologiche", "Technology Choices"))
        choices = [
            (
                "FastMCP",
                _(
                    "L'SDK ufficiale Anthropic offre FastMCP, un wrapper ad alto livello che semplifica "
                    "la creazione di server MCP. Rispetto al low-level Server, richiede meno boilerplate "
                    "e permette di focalizzarsi sulla logica applicativa.",
                    "The official Anthropic SDK offers FastMCP, a high-level wrapper that simplifies "
                    "MCP server creation. Compared to low-level Server, it requires less boilerplate "
                    "and allows focusing on application logic.",
                ),
            ),
            (
                "ChromaDB",
                _(
                    "Database vettoriale embedded, zero config, zero cloud. Supporta ANN index (HNSW) "
                    "per ricerca in O(log n) e cosine distance. La libreria PersistentClient garantisce "
                    "persistenza su disco senza server esterno.",
                    "Embedded vector database, zero config, zero cloud. Supports ANN index (HNSW) "
                    "for O(log n) search and cosine distance. PersistentClient ensures "
                    "disk persistence without external server.",
                ),
            ),
            (
                "sentence-transformers",
                _(
                    "Modello all-MiniLM-L6-v2: 384 dimensioni, ~80MB, sufficiente per MVP. "
                    "Viene caricato lazy (non all'import) e cachato in ~/.cache/agora/models/.",
                    "all-MiniLM-L6-v2 model: 384 dimensions, ~80MB, sufficient for MVP. "
                    "Lazy-loaded (not at import) and cached in ~/.cache/agora/models/.",
                ),
            ),
            (
                "SQLite",
                _(
                    "Per metadati, provenance e cache L2. Zero configurazione, file-based, "
                    "incluso nella libreria standard di Python. Ogni operazione apre e chiude "
                    "una connessione (thread-safe).",
                    "For metadata, provenance and L2 cache. Zero configuration, file-based, "
                    "included in Python standard library. Each operation opens and closes "
                    "a connection (thread-safe).",
                ),
            ),
        ]
        for title, desc in choices:
            self.set_font("Helvetica", "B", 10)
            self.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
            self.paragraph(desc)

        # --- 3. Architettura ---
        self.section(3, _("Architettura", "Architecture"))
        self.paragraph(
            _(
                "L'architettura di MCP Agora e' organizzata in 7 layer separati, ciascuno con "
                "responsabilita' ben definite e interfacce astratte. Questo approccio modulare permette "
                "di testare, sostituire e far evolvere ogni layer indipendentemente.",
                "MCP Agora's architecture is organized into 7 separate layers, each with "
                "well-defined responsibilities and abstract interfaces. This modular approach allows "
                "testing, replacing, and evolving each layer independently.",
            )
        )

        self.subsection("3.1", _("Diagramma dell'Architettura", "Architecture Diagram"))
        self.code(ARCH_DIAGRAM)

        self.subsection("3.2", _("Descrizione dei Layer", "Layer Description"))
        layers = [
            (
                "Transport Layer",
                _(
                    "Gestisce la comunicazione con gli agenti via JSON-RPC 2.0. Supporta due trasporti: "
                    "STDIO (locale, stdin/stdout, default) per agenti come Claude Code e Codex CLI; "
                    "Streamable HTTP (remoto, HTTP POST + SSE) per agenti remoti o multi-sessione.",
                    "Manages communication with agents via JSON-RPC 2.0. Supports two transports: "
                    "STDIO (local, stdin/stdout, default) for agents like Claude Code and Codex CLI; "
                    "Streamable HTTP (remote, HTTP POST + SSE) for remote or multi-session agents.",
                ),
            ),
            (
                "Protocol Layer",
                _(
                    "Espone le primitive MCP standard: tools/list per scoprire i tool disponibili, "
                    "tools/call per invocarli. Agora espone 8 tool (v. Sezione 4).",
                    "Exposes standard MCP primitives: tools/list to discover available tools, "
                    "tools/call to invoke them. Agora exposes 8 tools (see Section 4).",
                ),
            ),
            (
                "Router Layer",
                _(
                    "Cuore decisionale del sistema. Quando un agente chiama agora_route, il router "
                    "tenta prima un match esatto per nome (case-insensitive), poi un match semantico "
                    "via cosine similarity sulle descrizioni embedding dei backend (soglia >= 0.5). "
                    "Se nessun match, ritorna errore. Il routing broadcasting (agora_broadcast) invia "
                    "la richiesta in parallelo a tutti i backend, limitato ai soli tool read-only.",
                    "Decision-making core of the system. When an agent calls agora_route, the router "
                    "first attempts an exact name match (case-insensitive), then a semantic match "
                    "via cosine similarity on backend description embeddings (threshold >= 0.5). "
                    "If no match, returns error. Broadcast routing (agora_broadcast) sends "
                    "the request in parallel to all backends, limited to read-only tools only.",
                ),
            ),
            (
                "Memory Layer",
                _(
                    "Composto da due sotto-layer: Vector Index (ChromaDB, collezione 'knowledge', "
                    "spazio coseno, 384 dimensioni) per ricerca semantica, e Relational DB (SQLite3, "
                    "tabelle agents, provenance, l2_cache) per metadati strutturati. "
                    "La retention della knowledge e' permanente (finche' non cancellata con agora_forget). "
                    "La cache L2 ha TTL configurabile (default 24h).",
                    "Composed of two sub-layers: Vector Index (ChromaDB, 'knowledge' collection, "
                    "cosine space, 384 dimensions) for semantic search, and Relational DB (SQLite3, "
                    "tables agents, provenance, l2_cache) for structured metadata. "
                    "Knowledge retention is permanent (until deleted with agora_forget). "
                    "L2 cache has configurable TTL (default 24h).",
                ),
            ),
            (
                "Cache Layer",
                _(
                    "Due livelli di cache in cascata. L1: cachetools TTLCache in-memory (1000 entry, "
                    "5 minuti TTL). L2: SQLite-backed su disco (10000 entry, 24h TTL). "
                    "Cache key = SHA256 della richiesta completa JSON serializzata con sort_keys=True. "
                    "Su agora_save e agora_forget, entrambe le cache vengono invalidate (clear totale). "
                    "Cascade: L1 -> L2 -> ChromaDB. Su miss ChromaDB, entrambe le cache vengono popolate.",
                    "Two cascading cache levels. L1: cachetools TTLCache in-memory (1000 entries, "
                    "5 minutes TTL). L2: SQLite-backed on disk (10000 entries, 24h TTL). "
                    "Cache key = SHA256 of full JSON-serialized request with sort_keys=True. "
                    "On agora_save and agora_forget, both caches are invalidated (full clear). "
                    "Cascade: L1 -> L2 -> ChromaDB. On ChromaDB miss, both caches are populated.",
                ),
            ),
            (
                "Backend Connector Layer",
                _(
                    "Ogni backend MCP esterno e' rappresentato da un connettore che implementa "
                    "l'interfaccia astratta BackendConnector. Due implementazioni: StdioConnector "
                    "(subprocess MCP via stdio_client + ClientSession, lazy connect, asyncio.timeout) "
                    "e HttpConnector (streamable HTTP MCP via streamablehttp_client). "
                    "La connessione e' lazy: il connettore si connette al primo uso, non all'avvio. "
                    "Read-only enforcement: se un backend e' marcato read_only, solo i tool con prefissi "
                    "whitelist (list_, get_, fetch_, read_, search_, find_, query_, describe_, show_) "
                    "possono essere chiamati. I tool mutativi bloccati sollevano ReadOnlyBlockedError.",
                    "Each external MCP backend is represented by a connector implementing "
                    "the abstract BackendConnector interface. Two implementations: StdioConnector "
                    "(subprocess MCP via stdio_client + ClientSession, lazy connect, asyncio.timeout) "
                    "and HttpConnector (streamable HTTP MCP via streamablehttp_client). "
                    "Connection is lazy: the connector connects on first use, not at startup. "
                    "Read-only enforcement: if a backend is marked read_only, only tools with whitelisted "
                    "prefixes (list_, get_, fetch_, read_, search_, find_, query_, describe_, show_) "
                    "can be called. Mutative tools raise ReadOnlyBlockedError.",
                ),
            ),
            (
                "Embedding Layer",
                _(
                    "Provider astratto EmbeddingProvider con implementazione concreta "
                    "SentenceTransformerProvider che utilizza all-MiniLM-L6-v2 (384 dimensioni). "
                    "Lazy loading: il modello viene caricato al primo uso, non all'import del modulo. "
                    "Cache in ~/.cache/agora/models/. Prima chiamata ~17s (download modello + torch). "
                    "Chiamate successive <1s. Il metodo warmup() permette di pre-caricare il modello "
                    "all'avvio del server.",
                    "Abstract EmbeddingProvider with concrete SentenceTransformerProvider implementation "
                    "using all-MiniLM-L6-v2 (384 dimensions). "
                    "Lazy loading: model loads on first use, not on module import. "
                    "Cache in ~/.cache/agora/models/. First call ~17s (model download + torch). "
                    "Subsequent calls <1s. The warmup() method pre-loads the model at server startup.",
                ),
            ),
        ]
        for i, (title, desc) in enumerate(layers, 1):
            self.set_font("Helvetica", "B", 10)
            self.cell(0, 5, f"Layer {i}: {title}", new_x="LMARGIN", new_y="NEXT")
            self.paragraph(desc)

        # --- 4. API Tools ---
        self.section(4, _("API Tools", "API Tools"))
        self.paragraph(
            _(
                "Agora espone 8 tool MCP, registrati via decoratore @mcp.tool() su FastMCP. "
                "Tutti i tool accettano e restituiscono dizionari JSON serializzabili.",
                "Agora exposes 8 MCP tools, registered via @mcp.tool() decorator on FastMCP. "
                "All tools accept and return JSON-serializable dictionaries.",
            )
        )
        self.data_table(TOOLS_TABLE[0], TOOLS_TABLE[1:], col_widths=[25, 50, 80, 35])

        # --- 5. Schema Dati ---
        self.section(5, _("Schema Dati", "Data Schema"))
        self.subsection("5.1", _("ChromaDB: Vector Store", "ChromaDB: Vector Store"))
        self.paragraph(
            _(
                "Collezione unica 'knowledge' con spazio metrico coseno. I documenti sono i testi "
                "salvati, gli embedding sono vettori a 384 dimensioni generati da all-MiniLM-L6-v2, "
                "e i metadati includono tags (formato CSV), created_at (ISO 8601) e agent.",
                "Single 'knowledge' collection with cosine metric space. Documents are saved texts, "
                "embeddings are 384-dimensional vectors from all-MiniLM-L6-v2, "
                "and metadata includes tags (CSV format), created_at (ISO 8601), and agent.",
            )
        )
        self.paragraph(
            _(
                "Il wrapper VectorStore (agora/memory/vector_store.py) astrae l'API ChromaDB "
                "e gestisce automaticamente la creazione della collezione e la serializzazione.",
                "The VectorStore wrapper (agora/memory/vector_store.py) abstracts the ChromaDB API "
                "and handles collection creation and serialization automatically.",
            )
        )

        self.subsection("5.2", _("SQLite: Database Relazionale", "SQLite: Relational Database"))
        self.paragraph(
            _(
                "Tre tabelle per metadati strutturati: agents (registry agenti), provenance "
                "(tracciabilita' delle entry di conoscenza), l2_cache (cache persistente su disco).",
                "Three tables for structured metadata: agents (agent registry), provenance "
                "(knowledge entry traceability), l2_cache (persistent disk cache).",
            )
        )
        self.code(SQL_SCHEMA)

        # --- 6. Testing ---
        self.section(6, _("Testing", "Testing"))
        self.paragraph(
            _(
                "Il progetto adotta una strategia di test a 3 livelli: unit test (logica interna pura, "
                "nessun MCP/subprocess), integration test (stesso processo, chiamate dirette a funzioni), "
                "e MCP smoke test (via mcp.ClientSession reale su STDIO subprocess). "
                "55 test distribuiti su 9 file, zero mock - ChromaDB e SQLite reali in directory "
                "temporanee isolate per test (fixture pytest function-scoped con temp directory). "
                "Timing non usato come metrica (flaky su Windows); si usa cache.stats()['hit_count'].",
                "The project uses a 3-level testing strategy: unit tests (pure internal logic, "
                "no MCP/subprocess), integration tests (same process, direct function calls), "
                "and MCP smoke tests (via real mcp.ClientSession on STDIO subprocess). "
                "55 tests across 9 files, zero mocks - real ChromaDB and SQLite in isolated temp "
                "directories per test (pytest function-scoped fixtures with temp directory). "
                "Timing not used as metric (flaky on Windows); cache.stats()['hit_count'] is used instead.",
            )
        )
        test_headers = ["File", "N.", "Scopo"]
        self.simple_table(test_headers, [(f, str(n), d) for f, n, d in TEST_FILES], col_widths=[42, 10, 138])

        # --- 7. Key Design Decisions ---
        self.section(7, _("Decisioni Progettuali", "Design Decisions"))
        self.paragraph(
            _(
                "Le seguenti decisioni progettuali sono state prese consapevolmente, con rationale esplicito. "
                "Non devono essere modificate senza discussione.",
                "The following design decisions were made consciously, with explicit rationale. "
                "They should not be changed without discussion.",
            )
        )
        self.simple_table(DECISIONS_TABLE[0], DECISIONS_TABLE[1:], col_widths=[65, 125])

        # --- 8. Conclusioni ---
        self.section(8, _("Conclusioni e Roadmap", "Conclusions and Roadmap"))
        self.subsection("8.1", _("Roadmap Completata", "Completed Roadmap"))
        phases = [
            (
                "Fase 1 - Core Memory",
                _(
                    "save/query/status con ChromaDB, sentence-transformers, TTLCache L1, FastMCP.",
                    "save/query/status with ChromaDB, sentence-transformers, TTLCache L1, FastMCP.",
                ),
            ),
            (
                "Fase 2 - Routing + Connectors",
                _(
                    "Router semantico + esatto, StdioConnector, HttpConnector, BackendRegistry, "
                    "broadcast, read-only enforcement.",
                    "Semantic + exact Router, StdioConnector, HttpConnector, BackendRegistry, "
                    "broadcast, read-only enforcement.",
                ),
            ),
            (
                "Fase 3 - Cross-Agent Memory",
                _(
                    "Provenance tracking (SQLite), L2 cache persistente, crossref, forget, "
                    "parametri agent/session/confidence su save.",
                    "Provenance tracking (SQLite), persistent L2 cache, crossref, forget, "
                    "agent/session/confidence params on save.",
                ),
            ),
        ]
        for title, desc in phases:
            self.set_font("Helvetica", "B", 10)
            self.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
            self.paragraph(desc)

        self.subsection("8.2", _("Roadmap Futura", "Future Roadmap"))
        for item in [
            _(
                "Fase 4: Health check backend, retry/timeout configurabili, rate limiting, logging strutturato",
                "Phase 4: Backend health checks, configurable retry/timeout, rate limiting, structured logging",
            ),
            _(
                "Fase 5: README completo, esempi reali, pubblicazione GitHub + PyPI",
                "Phase 5: Full README, real examples, GitHub + PyPI publication",
            ),
            _(
                "Chunking: gestione documenti multi-paragrafo con split per boundary semantico",
                "Chunking: multi-paragraph document handling with semantic boundary split",
            ),
        ]:
            self.bullet(item)

        self.subsection("8.3", _("Metriche di Successo", "Success Metrics"))
        metrics = [
            ("Cache hit rate", "> 40% (MVP) / > 60% (target)"),
            ("Latenza media query", "< 1000ms"),
            ("Latenza cache hit", "< 50ms"),
            ("Copertura routing semantico", "> 70%"),
            ("Cross-agent knowledge reuse", "> 20%"),
            ("55 test, 0 mock", "Viola? No, e' un fatto."),
        ]
        self.simple_table([_("Metrica", "Metric"), _("Target", "Target")], metrics, col_widths=[75, 115])

        self.paragraph(
            _(
                "MCP Agora non e' un'invenzione. E' un esercizio di ingegneria su un problema reale "
                "(memoria isolata tra agenti) con strumenti moderni (MCP, vector search, embeddings). "
                "Se risolve il problema di 4 agenti che non condividono memoria, ha gia' vinto.",
                "MCP Agora is not an invention. It is an engineering exercise on a real problem "
                "(isolated agent memory) with modern tools (MCP, vector search, embeddings). "
                "If it solves the problem of 4 agents not sharing memory, it has already won.",
            )
        )

        # --- Appendice A ---
        if is_it:
            self.section("A", "Appendice A: config.yaml Completo")
        else:
            self.section("A", "Appendix A: Complete config.yaml")
        self.paragraph(
            _(
                "Il file config.yaml nella directory principale del progetto controlla "
                "la configurazione del server, dello storage, della cache, dell'embedding e dei backend.",
                "The config.yaml file in the project root directory controls "
                "server, storage, cache, embedding, and backend configuration.",
            )
        )
        self.code(CONFIG_YAML_EXAMPLE)

        # --- Appendice B ---
        if is_it:
            self.section("B", "Appendice B: Struttura del Progetto")
        else:
            self.section("B", "Appendix B: Project Structure")
        self.code(DIR_STRUCTURE)

        # --- Appendice C ---
        if is_it:
            self.section("C", "Appendice C: Cronologia Commit")
        else:
            self.section("C", "Appendix C: Commit History")
        self.paragraph(
            _(
                "Cronologia dei commit sul branch master del repository GitHub.",
                "Commit history on the master branch of the GitHub repository.",
            )
        )
        self.code(COMMIT_LOG)


def generate(output_path: str, lang: str = "it"):
    pdf = AgoraPDF(lang=lang)
    pdf.alias_nb_pages()
    pdf.write_document()
    pdf.output(output_path)
    return output_path


def main():
    it_path = os.path.join(DOCS_DIR, "tesina-mcp-agora-it.pdf")
    en_path = os.path.join(DOCS_DIR, "tesina-mcp-agora-en.pdf")
    generate(it_path, "it")
    print(f"[OK] ITA: {it_path}")
    generate(en_path, "en")
    print(f"[OK] EN: {en_path}")
    print("Done.")


if __name__ == "__main__":
    main()
