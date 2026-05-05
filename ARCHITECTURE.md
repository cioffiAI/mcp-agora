# MCP Agora — Architettura e Obiettivi

## Posizionamento (onesto)

Agora **non è un prodotto originale**. Esistono già progetti che fanno parti di quello che Agora vuole fare:

| Cosa | Già esiste? | Progetti |
|------|------------|----------|
| MCP gateway unico | Sì | ContextForge (IBM), MetaMCP, MCP Aggregator, 1MCP, AgentGateway |
| Proxy multi-server | Sì | Tutti i sopra |
| Memoria persistente MCP | Sì | mcp-memory-service, mcp-local-memory, AutoMem |
| Memoria cross-agente | Sì | mcp-memory-service (esplicito), mcp-local-memory |

**Agora non compete con questi.** Agora è un **progetto portfolio/learning** che implementa una combinazione specifica di quei pattern in uno stack Python puro, zero Docker, zero cloud, pensato per l'uso personale di uno sviluppatore singolo.

> **Obiettivo**: non "essere il migliore gateway MCP", ma **dimostrare competenza su AI infrastructure, MCP protocol, vector search, semantic routing, system design**, e risolvere un problema reale nei propri workflow con agenti.

---

## Vision

Agora è un MCP Server che funge da **layer di memoria condivisa** per flotte di agenti personali. Gli agenti parlano con Agora via MCP; Agora instrada richieste a server backend MCP, mantiene memoria persistente tra sessioni, e permette il riuso di conoscenza tra agenti diversi.

> "Non si vende alle persone. Si va agli agenti."

**Non è un gateway enterprise.** È un **sistema locale, leggero, Python-only** per far sì che i tuoi agenti non dimentichino e non ripetano lavoro.

---

## Obiettivi del Progetto

### Obiettivi di apprendimento (portfolio)

1. **MCP Protocol deep dive**: implementare un MCP Server compliant da zero usando l'SDK ufficiale
2. **Vector search & embeddings**: integrare ChromaDB + sentence-transformers per ricerca semantica
3. **System design a layer**: architettura modulare con 7 layer separati, interfacce astratte, dependency injection
4. **Async Python**: asyncio + anyio per concorrenza su MCP transport
5. **SQLite avanzato**: schema relazionale per metadati, provenance, analytics
6. **Caching strategies**: LRU in-memory, persistent disk, semantic cache

### Obiettivi di prodotto (pratici)

1. Un agente può salvare conoscenza → un altro agente la recupera (zero duplicazione)
2. Una query già fatta → risposta cached (zero ricalcolo)
3. Un errore già fatto → non si ripete (memoria delle decisioni)
4. 4+ agenti che condividono contesto senza configurarli uno per uno

### Non-obiettivi (cosa Agora NON è)

- Non è un API gateway enterprise (non fa auth RBAC, non scale orizzontalmente)
- Non è un orchestrator agenti (non lancia agenti, non gestisce workflow)
- Non è un competitor di ContextForge, MetaMCP, AutoMem
- Non è un prodotto SaaS (è locale, file-based, personale)

---

## Perché ha senso come portfolio

1. **Stack 2026**: MCP protocol, vector search, semantic routing, embedding models
2. **Architettura pulita**: 7 layer, dipendenze astratte, testabile
3. **Problematica reale**: chiunque usi agenti AI ha memoria isolata e lavoro duplicato
4. **Dimostrabile**: `pip install mcp-agora && mcp-agora start` → funziona in 30 secondi
5. **Differenziante**: non è l'ennesima CRUD/web app — dimostra pensiero sistemico su AI infrastructure
6. **Integrazione con AI Vault**: Agora può diventare infrastruttura viva per memoria personale e procedure

---

## Token Savings — Il Vero Calcolo

### Premessa: prompt caching nei modelli moderni

I modelli 2025-2026 (Claude, GPT-4o, Gemini 2.0, DeepSeek) implementano **prompt caching**: se lo stesso contenuto appare in richieste consecutive, viene riusato senza ricalcolo del costo. In pratica:

> Il costo marginale di un contenuto già visto tende a zero.

Questo cambia il calcolo del risparmio:

| Tipo di risparmio | Cosa conta | Impatto reale |
|------------------|-----------|--------------|
| Token lordi risparmiati | Prompt caching | Basso (il modello già non li ricalcola) |
| **Token unici eliminati** | Chiamate backend evitate | **Alto** (nessun caching model-side evita la chiamata) |
| **Lavoro duplicato evitato** | Agente B non ripete ricerca di A | **Altissimo** (minuti di compute risparmiati) |

### Il vero valore di Agora

```
Senza Agora:
  Agente A: "cerca best practices PostgreSQL" → chiamata GitHub API → 5000 tok output
  Agente B: "cerca best practices PostgreSQL" → STESSA chiamata → 5000 tok output
  Totale: 2 chiamate API, 10000 tok unici

Con Agora:
  Agente A: "cerca best practices PostgreSQL" → chiamata → salva in memoria
  Agente B: "best practices DB?" → cache HIT → 200 tok (lettura memoria)
  Totale: 1 chiamata API, 5200 tok unici (48% risparmio)

E il risparmio reale:
  - Agente B ha risposta in 50ms invece di 5 secondi
  - Nessuna API call ripetuta
  - Nessun rate limiting consumato
  - Nessuna attesa
```

### Lo scenario flotta

| Metrica | Valore |
|---------|--------|
| 4 agenti (Codex, Claude Code, ChatGPT, Gemini CLI) | 5 sessioni/giorno × 22 giorni |
| Overhead mensile senza Agora | 3.960.000 tok |
| Overhead mensile con Agora | 792.000 tok |
| Token risparmiati/mese | **3.168.000 tok** (~$0.48 DeepSeek / $9.50 GPT-4o / $47.52 Opus) |

Il risparmio economico è piccolo per modelli cheap, **ma il risparmio di tempo e attenzione è enorme**: secondi per sessione, minuti per giornata, ore per mese.

### Regola empirica

> Più agenti hai e più MCP server usi, maggiore è il risparmio.
> Con 1 agente e 1 server: risparmio ~40% (cache + memoria).
> Con 4+ agenti e 5+ server: risparmio ~80% + conoscenza cross-agente non altrimenti possibile.

---

## Architettura a Layer

```
┌────────────────────────────────────────────────────────────┐
│                      TRANSPORT LAYER                       │
│  STDIO (locale)  │  Streamable HTTP (remoto)               │
│  JSON-RPC 2.0 over stdin/stdout or HTTP POST/SSE           │
├────────────────────────────────────────────────────────────┤
│                      PROTOCOL LAYER                         │
│  MCP Primitives: tools/list, tools/call, resources/list,    │
│  resources/read, prompts/get, notifications                 │
├────────────────────────────────────────────────────────────┤
│                      ROUTER LAYER                            │
│  ┌──────────┐  ┌──────────┐                                  │
│  │Semantic  │  │ Static   │                                  │
│  │Router    │  │ Router   │                                  │
│  └────┬─────┘  └────┬─────┘                                  │
│       │              │                                        │
│       └──────────────┘                                        │
│                       │                                       │
├───────────────────────┴──────────────────────────────────────┤
│                      MEMORY LAYER                             │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  VECTOR INDEX (ChromaDB)                             │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │    │
│  │  │Session  │ │Tool Call│ │Knowledge│ │Cross-   │   │    │
│  │  │Logs     │ │Results  │ │Entries  │ │Refs     │   │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  RELATIONAL DB (SQLite)                              │    │
│  │  agent_registry | server_config | cache_metadata     │    │
│  │  session_logs | token_usage | provenance             │    │
│  └──────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────┤
│                      CACHE LAYER                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  LRU Cache (in-memory)  │  Persistent Cache (disk)   │    │
│  │  TTL: 5min (frequenti)  │  TTL: 24h (lenti/costosi)  │    │
│  │  Max: 1000 entries      │  Max: 10000 entries         │    │
│  └──────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────┤
│                    BACKEND CONNECTOR LAYER                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ MCP Conn │ │ MCP Conn │ │ MCP Conn │ │ MCP Conn │       │
│  │ (GitHub) │ │ (DB)     │ │ (FS)     │ │ (Custom) │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                              │                               │
│  Ogni connettore: STDIO o HTTP, autenticazione, retry,       │
│  timeout, rate limiting                                      │
├──────────────────────────────────────────────────────────────┤
│                    EMBEDDING LAYER                            │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  sentence-transformers (locale, gratis)              │    │
│  │  oppure Ollama (locale, nomic-embed-text)            │    │
│  │  oppure OpenAI ADA (remoto, opzionale)               │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

---

## Descrizione dei Layer

### 1. Transport Layer

Gestisce la connessione con gli agenti. Agora è un MCP Server, quindi supporta:

- **STDIO Transport**: per agenti locali (Claude Code, Codex CLI). Usa stdin/stdout.
- **Streamable HTTP Transport**: per agenti remoti o multi-sessione. Usa HTTP POST + SSE.

Configurazione di default: STDIO (locale, zero configurazione).

### 2. Protocol Layer

Espone le primitive MCP standard che ogni agente si aspetta:

#### tools/list
```json
{
  "tools": [
    {
      "name": "agora.query",
      "description": "Query semantica su tutta la conoscenza memorizzata. Cerca nel vector index + cache, poi opzionalmente sui backend configurati."
    },
    {
      "name": "agora.save",
      "description": "Salva un risultato/contestualizzazione nella memoria persistente. Indicizzato automaticamente per ricerca futura."
    },
    {
      "name": "agora.route",
      "description": "Invia una richiesta a uno specifico MCP server backend, scelto per nome o per similarità semantica."
    },
    {
      "name": "agora.crossref",
      "description": "Trova correlazioni tra informazioni memorizzate da agenti diversi o sessioni diverse."
    },
    {
      "name": "agora.forget",
      "description": "Elimina specifiche voci di memoria (privacy, correzioni, dati obsoleti)."
    },
    {
      "name": "agora.status",
      "description": "Restituisce stato della flotta: server connessi, statistiche cache, agenti attivi."
    }
  ]
}
```

#### resources/list
- `agora://memory/session/{id}` — Log di una sessione
- `agora://memory/agent/{name}` — Memoria di un agente specifico
- `agora://knowledge/search?q={query}` — Risultati di ricerca semantica
- `agora://cache/stats` — Statistiche cache hit/miss
- `agora://servers/status` — Stato di tutti i backend MCP connessi

### 3. Router Layer

Il cuore decisionale. Quando un agente chiama `agora.route` o `agora.query`:

```
                        ┌──────────────┐
                        │  Richiesta    │
                        │  agente       │
                        └──────┬───────┘
                               │
                    ┌──────────┴──────────┐
                    │   Semantic Router   │
                    │  (vector query su   │
                    │   descrizioni MCP)  │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    │  Score > 0.75?      │
                    ├─────────┬───────────┤
                    │   SI    │    NO     │
                    └────┬────┴─────┬─────┘
                         │          │
               ┌─────────┘          └──────────┐
               │                                │
     ┌─────────┴──────────┐          ┌─────────┴──────────┐
     │  Static Router     │          │  Fallback: query    │
     │  (regole definite  │          │  broadcasting a     │
     │  dall'umano)       │          │  TUTTI i backend    │
     └─────────┬──────────┘          │  read-only          │
               │                     │  (strumenti mutativi│
               │                     │   esclusi)          │
               │                     └─────────┬──────────┘
               │                               │
               └──────────┬────────────────────┘
                          │
                ┌─────────┴──────────┐
                │  Backend Connector │
                │  Layer             │
                └────────────────────┘
```

**Nota importante**: il fallback broadcasting è limitato ai tool read-only. I tool con effetti (scrittura DB, file system, API mutative) hanno routing esplicito o statico — mai broadcasting.

**Criteri di routing semantico:**
1. Ogni MCP server backend ha una descrizione testuale
2. La richiesta dell'agente viene convertita in embedding
3. Similarity coseno con tutti gli embedding delle descrizioni backend
4. Se score > 0.75 → routing diretto
5. Se score 0.5-0.75 → routing diretto + query broadcasting (solo read-only)
6. Se score < 0.5 → solo query broadcasting (solo read-only)

**Endpoint critico**: il routing semantico è euristico, non deterministico. Le soglie 0.75 e 0.5 sono valori iniziali configurabili, non verità assolute. La similarità embedding varia per modello, lingua, lunghezza descrizione. In produzione, le soglie vanno calibrate sul proprio set di backend.

### 4. Memory Layer

Il layer che rende Agora "intelligente". Non un semplice database, ma un sistema di memoria strutturato.

#### Sotto-layer Vector Index

Indicizza ciò che passa per Agora:

| Collezione | Cosa contiene | Dimensione chunk | Update strategy |
|---|---|---|---|
| `sessions` | Log completi delle sessioni agente | 512 tok | append-only |
| `tool_results` | Risultati di tutte le chiamate tool | 1024 tok | upsert su hash |
| `knowledge` | Informazioni salvate con `agora.save` | 256 tok | sovrascrittura su conflitto |
| `crossrefs` | Collegamenti tra informazioni correlate | 128 tok | generato da batch job |
| `decisions` | Decisioni e reasoning degli agenti | 512 tok | append-only |

**Strategia di chunking (prevista per Fasi 2+)**
- Split per boundary semantico (paragrafi, sezioni, code block)
- Overlap 10% tra chunk adiacenti per non perdere contesto ai bordi
- Ogni chunk mantiene: id, embedding (384d), metadata, timestamp, agent_source

**Fase 1 — senza chunking**: `agora.save` accetta solo entry brevi (≤256 word pieces, limite del modello all-MiniLM-L6-v2). Non è ancora un indicizzatore di documenti lunghi. Il chunking sarà aggiunto quando serviranno documenti multi-paragrafo.

#### AVVERTENZE sulla memoria automatica

Agora indicizza automaticamente ciò che passa, ma con cautele:

| Problema | Mitigazione |
|----------|------------|
| Privacy (credenziali, path locali) | Filtro pre-salvataggio: regex pattern per escludere dati sensibili |
| Rumore (dati non utili) | Solo `agora.save` esplicito crea knowledge permanente. Session/tool results hanno retention breve |
| Errori persistenti | Provenance tracciata; `agora.forget` per rimozione esplicita |
| Dati obsoleti | Cache scade. Knowledge è permanente ma marcata con timestamp + source |
| Costo cognitivo del retrieval | similarity score minimo 0.7 per ritornare risultati; top-k = 5 |

**Regola**: la cache scade sempre. La knowledge è permanente solo se salvata esplicitamente con `agora.save`. I log di sessione e i tool results non diventano mai "knowledge" automaticamente.

#### Sotto-layer Relazionale

| Tabella | Colonne | Scopo |
|---|---|---|
| `agents` | id, name, type, first_seen, last_seen | Registry agenti conosciuti |
| `servers` | id, name, transport, config, healthy | Backend MCP configurati |
| `cache_index` | key, hash, ttl, size, hits, created_at, expires_at | Metadata cache |
| `provenance` | entry_id, source_agent, source_session, confidence | Tracciabilità informazioni |
| `token_usage` | agent, session, date, input_tok, output_tok | Analytics consumo |

#### Strategia di retention

| Tipo | Retention | Motivo |
|---|---|---|
| Session logs | 7 giorni | Debug recente |
| Tool results cached | 24 ore | Casi d'uso frequenti |
| Knowledge entries | Permanente (finché non cancellato) | Conoscenza accumulata |
| Decisioni e reasoning | 30 giorni | Pattern recognition |
| Cache L1 (memory) | 5 minuti (LRU, 1000 entry) | Performance |

### 5. Cache Layer

Evita chiamate ridondanti ai backend MCP.

```
Richiesta agente → check cache (hash richiesta)
├── HIT → restituisce risultato cached
│         (zero chiamate backend, zero token di calcolo backend)
└── MISS → inoltra al backend
         → salva risultato in cache
         → restituisce all'agente
```

**Nota**: "zero token" si riferisce ai token di computazione/risposta del backend MCP. L'agente che riceve il risultato cached deve comunque leggerlo nel suo contesto. Il risparmio è sulla **chiamata backend**, non sul totale dei token processati dall'agente.

**Tipi di cache:**
1. **L1: In-memory TTLCache** — 1000 entry, TTL 5 min. Per richieste frequenti identiche. Usa `cachetools.TTLCache` (non LRUCache diretto, già ha scadenza built-in).
2. **L2: Persistent disk** — 10000 entry, TTL 24h. Per risultati costosi (Fase 3+).

**Cache key**: include TUTTI i parametri della richiesta, non solo query e tool:
```
cache_key = sha256(json.dumps({
  "tool": "agora.query",
  "collection": "knowledge",
  "query": query,
  "top_k": top_k,
  "model": embedding_model
}, sort_keys=True))
```

**Invalidazione**: in Fase 1, quando si chiama `agora.save`, si fa **clear globale di tutte le cache query**. È meno elegante ma sicuro — evita di dover calcolare quali entry invalidare selettivamente.

**Semantic cache**: NON inclusa nel MVP. Richiede valutazione attenta: due richieste semanticamente simili possono essere operativamente diverse ("status progetto X" ≠ "issue aperte progetto X"). Se implementata in futuro, richiederà:
- Soglia di similarità configurabile (default 0.95, molto alta)
- Esclusione esplicita per tool mutativi o dati live
- Cache busting manuale per risultati che cambiano

**Statistiche:**
- Hit rate target: > 60%
- Warmup: prime richieste sono tutte miss (normale)
- Metriche tracciate: hit_count, miss_count, avg_response_time

### 6. Backend Connector Layer

Ogni MCP server backend è rappresentato da un connettore.

```
┌────────────────────────────────────────────────────────────┐
│  Backend Connector (interfaccia astratta)                  │
│                                                            │
│  + connect() → bool                                        │
│  + disconnect() → void                                     │
│  + list_tools() → Tool[]                                   │
│  + call_tool(name, args) → Result                          │
│  + health() → HealthStatus                                 │
│  + is_read_only() → bool   ← DISTINZIONE CRITICA          │
│  + description → str (per routing semantico)               │
│                                                            │
│  Proprietà:                                                │
│  - max_retries: 3                                          │
│  - timeout: 30s                                            │
│  - rate_limit: 10 req/s (configurabile)                    │
│  - auth_method: none | bearer | api_key                    │
└────────────────────────────────────────────────────────────┘
```

**DISTINZIONE READ-ONLY vs MUTATIVI**: ogni tool backend è marcato come `read_only` o `mutative`. Questo determina:
- Se può essere chiamato in broadcasting (solo read-only)
- Se i suoi risultati vanno cached (sì per read-only, no per mutativi)
- Se partecipa al routing semantico broadcast (solo read-only)

**Connettori built-in:**
- STDIO Connector: lancia processi locali (npx, uvx, python)
- HTTP Connector: Streamable HTTP per server remoti

**Health check:**
- Ping ogni 30 secondi
- 3 fallimenti consecutivi → segna come unhealthy
- Reconnect automatico ogni 60 secondi
- Notifica all'agente su `agora.status` se un backend è giù

### 7. Embedding Layer

Convertire testo in vettori per la ricerca semantica.

**Provider supportati (configurabili, pluggabili):**

| Provider | Dimensione | Costo | Qualità | Ideale per |
|---|---|---|---|---|
| sentence-transformers (all-MiniLM-L6-v2) | 384d | 0 | Buona | Locale, gratis, default MVP |
| nomic-embed-text (via Ollama) | 768d | 0 | Ottima | Locale, qualità superiore |
| OpenAI text-embedding-3-small | 1536d | $0.02/M tok | Eccellente | Produzione, se serve |

Default: sentence-transformers (zero costi, zero dipendenze cloud).

**Limitazioni note (Fase 1):**
- `all-MiniLM-L6-v2` tronca input > 256 word pieces — salvare solo entry brevi
- Modello non nativamente multilingua italiano; sufficiente per similarità semantica generica
- Prima chiamata lenta (download modello ~80MB); poi cached in `~/.cache/huggingface/`
- Installazione può richiedere download di `torch` (centinaia di MB)

**Test embedding (Fase 1):**
```python
# Buono: testa il comportamento utile, non similarità astratta
embed(["PostgreSQL BRIN indexes"])
# → verifica dimensione = 384
# → verifica che ritorni list[float]

doc_a = "PostgreSQL BRIN indexes are useful for very large tables"
doc_b = "SQLite is a lightweight embedded database"
# salva doc_a, salva doc_b
# query: "large PostgreSQL tables index"
# → verifica che il primo risultato sia doc_a (similarità > con doc_b)
```

---

## Schema Relazionale

```sql
-- Registry agenti che hanno interagito con Agora
CREATE TABLE agents (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    agent_type      TEXT NOT NULL,
    first_seen      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sessions_count  INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0
);

-- Backend MCP configurati
CREATE TABLE servers (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    transport     TEXT NOT NULL CHECK(transport IN ('stdio', 'http')),
    config_json   TEXT NOT NULL,
    description   TEXT NOT NULL,
    embedding     BLOB,
    is_healthy    BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Metadati cache
CREATE TABLE cache_index (
    cache_key    TEXT PRIMARY KEY,
    result_hash  TEXT NOT NULL,
    ttl_seconds  INTEGER NOT NULL DEFAULT 86400,
    size_bytes   INTEGER NOT NULL,
    hit_count    INTEGER DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at   TIMESTAMP DEFAULT (CURRENT_TIMESTAMP)
);

-- Tracciabilità della conoscenza
CREATE TABLE provenance (
    entry_id        TEXT NOT NULL,
    source_agent    TEXT NOT NULL REFERENCES agents(id),
    source_session  TEXT NOT NULL,
    confidence      REAL DEFAULT 0.5,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entry_id, source_agent, source_session)
);

-- Analytics consumo token
CREATE TABLE token_usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id      TEXT NOT NULL REFERENCES agents(id),
    session_id    TEXT NOT NULL,
    date          DATE NOT NULL DEFAULT CURRENT_DATE,
    input_tok     INTEGER NOT NULL,
    output_tok    INTEGER NOT NULL,
    cached_hit    BOOLEAN DEFAULT FALSE,
    tool_name     TEXT,
    backend_id    TEXT REFERENCES servers(id)
);
```

**Nota**: `cache_index.expires_at` è calcolato a livello applicativo (`created_at + ttl_seconds`), non con sintassi PostgreSQL. SQLite non supporta `INTERVAL` o `GENERATED ALWAYS AS` con espressioni temporali.

---

## Flussi di Dati

### Flusso 1: Query → Backend → Memoria

```
Agente                    Agora                         Backend MCP
  │                         │                              │
  │  tools/call             │                              │
  │  {agora.query,          │                              │
  │   "status progetto X"}  │                              │
  │ ──────────────────────> │                              │
  │                         │  ┌─ Cache check (miss)       │
  │                         │  ┌─ Memory check (miss)      │
  │                         │  ┌─ Semantic routing         │
  │                         │  │  "progetto" → GitHub MCP  │
  │                         │  │  score: 0.89              │
  │                         │  └────────────────────────── │
  │                         │  tools/call                  │
  │                         │  {get_repo, "project-X"}     │
  │                         │ ───────────────────────────> │
  │                         │                              │
  │                         │  Result: PR #42, issues...   │
  │                         │ <─────────────────────────── │
  │                         │                              │
  │                         │  ┌─ Save to cache (L1 + L2)  │
  │                         │  └────────────────────────── │
  │                         │  ┌─ Save provenance          │
  │                         │  └────────────────────────── │
  │                         │                              │
  │  Result: "PR #42        │                              │
  │  merged ieri..."        │                              │
  │ <────────────────────── │                              │
```

### Flusso 2: Cross-agente — riuso conoscenza

```
Agente B (nuova sessione)     Agora
  │                              │
  │  tools/call                  │
  │  {agora.query,               │
  │   "best practices DB"}       │
  │ ────────────────────────────>│
  │                              │
  │  ┌─ Cache check (miss)       │
  │  ┌─ Memory layer check       │
  │  │  Vector search:           │
  │  │  "best practices DB"      │
  │  │                           │
  │  │  Found: entry from        │
  │  │  Agente A, 2h fa          │
  │  │  Score: 0.91              │
  │  │  → HIT! (zero backend     │
  │  │     calls)                │
  │  └────────────────────────── │
  │                              │
  │  Result: "PostgreSQL         │
  │  pattern: ..."               │
  │  + metadata: source_agent,   │
  │    confidence, timestamp     │
  │ <─────────────────────────── │
  │                              │
  │  ┌─ Save: "Agente B ha      │
  │  │  letto knowledge di A"    │
  │  │  (provenance chain)       │
  │  └────────────────────────── │
```

### Flusso 3: Cache hit

```
Agente                    Agora
  │                         │
  │  tools/call             │
  │  {agora.query,          │
  │   "status progetto X"}  │
  │ ──────────────────────> │
  │                         │
  │  ┌─ Cache check (HIT!)  │
  │  │  Stessa query, 3min  │
  │  │  fa, TTL valido      │
  │  └──────────────────────│
  │                         │
  │  Result: "PR #42        │
  │  merged ieri..."        │
  │  (0 backend calls,      │
  │   zero token di         │
  │   computazione backend) │
  │ <────────────────────── │
```

### Flusso 4: Salvataggio conoscenza

```
Agente                    Agora
  │                         │
  │  tools/call             │
  │  {agora.save,           │
  │   key: "db_pattern",    │
  │   value: "...",         │
  │   tags: ["postgres",    │
  │          "indexing"]}   │
  │ ──────────────────────> │
  │                         │
  │  ┌─ Vectorize value     │
  │  └──────────────────────│
  │  ┌─ Save to vector      │
  │  │  index (knowledge)   │
  │  └──────────────────────│
  │  ┌─ Save provenance:    │
  │  │  Agente A, sessione  │
  │  │  #42, timestamp      │
  │  └──────────────────────│
  │                         │
  │  Result: {saved: true,  │
  │  id: "mem_20260505_01", │
  │  tokens: 342}           │
  │ <────────────────────── │
```

---

## Limitazioni e Rischi (espliciti)

| Rischio | Impatto | Mitigazione |
|---------|---------|-------------|
| **Routing semantico imperfetto**: similarità embedding non è significato reale | Query instradate al backend sbagliato | Static router come override; fallback broadcast solo read-only |
| **Cache semantica pericolosa**: due query simili ma operativamente diverse | Risposta sbagliata ma apparentemente corretta | Semantic cache NON inclusa nel MVP. Se aggiunta: soglia 0.95 + esclusione tool live |
| **Memoria automatica rumorosa**: logging tutto = memorizzare spazzatura | Degrado qualità retrieval | Solo `agora.save` crea knowledge permanente. Session/tool results hanno retention breve |
| **Broadcasting moltiplica latenza/costi**: chiamare N backend per una query | Latenza N×, costo N×, side effects | Solo tool read-only; esclusione esplicita tool mutativi; timeout configurabile |
| **Dati obsoleti in memoria**: knowledge sopravvive al dato originale | Disinformazione silenziosa | Ogni entry ha timestamp + source_agent + confidence score; `agora.forget` disponibile |
| **Latenza target ottimistica**: 500ms media su Windows/laptop | Degrado UX se backend STDIO lenti | Target rivalutato a < 1000ms per MVP; metriche tracciate per calibrazione |
| **Embedding su CPU lentissimo**: sentence-transformers su laptop | Throughput < 100 req/s | Ottimizzazione: caching embedding delle descrizioni backend; batch processing |
| **API FastMCP diversa dagli esempi online**: SDK in evoluzione | Breaking changes | Fissare versione `mcp>=1.0.0` in pyproject.toml |
| **Test MCP via STDIO fragili**: subprocess + stdio su Windows | Test instabili | Test priority: logica interna > integration diretta > MCP smoke. Timing non usato come metrica |
| **Knowledge lunghe troncate**: modello tronca input > 256 word pieces | Perdita di contenuto | Documentare limite in Fase 1; chunking in Fase 2+ |
| **Cache invalidation difficile**: invalidare solo entry correlate | Cache sporca | In Fase 1: clear globale su `agora.save`. Semplice e sicuro |
| **Troppi file vuoti**: struttura sembra più complessa di quanto è | Percezione errata | In Fase 1 solo file necessari; niente db/, router/, connectors/ |
| **Config path Windows**: `~/.agora/` non sempre espanso correttamente | Path sbagliati | Usare `Path.expanduser()` + `os.path.expandvars()` sempre |

---

## Metriche di Successo

| Metrica | Target MVP | Target finale | Come si misura |
|---------|-----------|--------------|---------------|
| Cache hit rate | > 40% | > 60% | `hit_count / total_requests` |
| Token risparmiati/sessione | > 3.000 | > 5.000 | Confronto con baseline senza Agora |
| Latenza media query | < 1000ms | < 500ms | Tempo tools/call → response |
| Latenza cache hit | < 50ms | < 50ms | Cache L1 o L2 |
| Copertura routing semantico | > 70% | > 80% | Richieste instradate correttamente |
| Cross-agent knowledge reuse | > 20% | > 30% | Query che trovano knowledge salvata da altro agente |
| Uptime Agora | > 95% | > 99% | Health check ogni 30s |
| Embedding throughput | > 50 req/s | > 100 req/s | sentence-transformers su CPU moderna |

---

## Strategia di Test (Fase 1)

Gerarchia: logica interna pura → integration → MCP smoke → reale con Claude.

| Livello | Cosa testa | Priorità | Strumento |
|---------|-----------|----------|-----------|
| **Unit test** | Embedding dimensione/forma, Cache set/get/scadenza, ChromaDB add/query/delete | Alta | pytest |
| **Integration diretto** | `save_knowledge()` e `query_knowledge()` chiamati come funzioni Python (stesso processo) | Alta | pytest |
| **MCP smoke** | `tools/list` vede i tool giusti, `tools/call` risponde senza errori | Media | `mcp.ClientSession` + stdio |
| **Reale con Claude** | Claude Code / Codex salva e recupera conoscenza | Media (manuale) | Claude Desktop / Codex |

**Principio**: se il test di integrazione diretto passa, l'80% del sistema funziona. Il test MCP verifica solo che il protocollo trasporti correttamente.

**Metriche da NON usare in Fase 1**: timing di cache hit (troppo rumoroso su Windows). Usare invece `cache.stats()["hit_count"] == 1`.

---

## Stack Tecnologico

| Componente | Tecnologia | Perché |
|---|---|---|
| Linguaggio | Python 3.11+ | MCP SDK ufficiale, ecosistema AI maturo |
| MCP SDK | `mcp` (PyPI) | SDK ufficiale Anthropic — usare `FastMCP` per Fase 1 (non low-level Server) |
| Vector Store | ChromaDB | Zero config, zero cloud, perfetto per MVP |
| Embeddings | sentence-transformers (default) | Gratis, locale, 384d sufficiente per MVP |
| DB Relazionale | SQLite | Zero config, file-based, sufficiente per MVP |
| Cache L1 | `cachetools.TTLCache` | Libreria standard, TTL built-in |
| Cache L2 | SQLite (stessa istanza) | Evita dipendenze esterne |
| Async | asyncio + anyio | MCP SDK è async |
| Testing | pytest + pytest-asyncio | Testing MCP richiede async |
| HTTP Server | uvicorn + starlette | Per Streamable HTTP transport |

---

## Struttura del Progetto (Fase 1)

Solo i file necessari. Niente router, connectors, db/ o chunking in Fase 1.

```
mcp-agora/
├── pyproject.toml              # Metadati, dipendenze, scripts
├── README.md
├── LICENSE
├── config.yaml                 # Configurazione Agora
├── AGAENTS.md                  # Istruzioni per agenti AI
├── ARCHITECTURE.md
├── agora/
│   ├── __init__.py
│   ├── main.py                 # Entry point: `agora` command
│   ├── server.py               # FastMCP server + tool registration
│   ├── config.py               # Caricamento config YAML
│   ├── embedding/
│   │   ├── __init__.py
│   │   ├── base.py             # Interfaccia astratta EmbeddingProvider
│   │   └── sentence.py         # sentence-transformers (all-MiniLM-L6-v2)
│   ├── memory/
│   │   ├── __init__.py
│   │   └── vector_store.py     # ChromaDB PersistentClient wrapper
│   └── cache/
│       ├── __init__.py
│       └── l1_memory.py        # TTLCache in-memory
│
├── tests/
│   ├── __init__.py
│   ├── test_embedding.py       # Dimensione vettori, similarità documenti
│   ├── test_memory.py          # ChromaDB add/query/delete
│   ├── test_cache.py           # TTLCache set/get/scadenza/stats
│   └── test_protocol.py        # MCP smoke test (tools/list), integration save→query
│
└── examples/
    └── config.yaml.example
```

I moduli per router, connectors, db/, chunker, provenance, retention saranno aggiunti nelle fasi successive quando servono davvero.

---

## Roadmap MVP

### Fase 1 — Single-agent memory (1 settimana)

**Approccio**: prima la logica interna (embedding → ChromaDB → cache), poi FastMCP wrapper, poi test.

- [x] Struttura progetto, ARCHITECTURE.md
- [x] pyproject.toml, uv init, dipendenze (mcp, chromadb, sentence-transformers, cachetools, pyyaml)
- [ ] Config YAML + `config.py` (caricamento configurazione con pyyaml)
- [ ] Embedding layer: `base.py` (interfaccia) + `sentence.py` (all-MiniLM-L6-v2, lazy loading)
- [ ] ChromaDB wrapper: `vector_store.py` (PersistentClient, collection "knowledge")
- [ ] Cache L1: `l1_memory.py` (TTLCache con cache key completa)
- [ ] FastMCP server: `server.py` con due tool (`agora.save`, `agora.query`)
- [ ] Entry point: `main.py` → comando `agora`
- [ ] Test unitari: embedding, memory, cache (logica interna pura, senza MCP)
- [ ] Test integration: save → query via Python (stesso processo)
- [ ] Test MCP smoke: tools/list, tools/call via MCP client
- [ ] Test reale: Claude Code / Codex → salva e recupera conoscenza

### Fase 2 — Routing + Backend Connectors (1 settimana)
- [ ] Semantic Router (embedding descrizioni backend)
- [ ] Static Router (regole YAML)
- [ ] Connector STDIO (lancia processi npm/pip)
- [ ] Connector HTTP (server remoti)
- [ ] Distinzione read-only/mutative
- [ ] Test: Agora → route a GitHub MCP → risultato

### Fase 3 — Cross-agent memory (3-4 giorni)
- [ ] Provenance tracking
- [ ] Cache L2 persistente (SQLite)
- [ ] Tool `agora.crossref`
- [ ] Tool `agora.forget`
- [ ] Test: Agente A salva → Agente B recupera → provenance corretta

### Fase 4 — Robustezza (3-4 giorni)
- [ ] Health check backend
- [ ] Retry + timeout configurabili
- [ ] Rate limiting
- [ ] Logging strutturato
- [ ] `agora.status`
- [ ] Test: backend down → graceful degradation

### Fase 5 — Portfolio polish (2-3 giorni)
- [ ] README con architettura, esempi
- [ ] Config YAML commentato
- [ ] Quickstart in 3 comandi
- [ ] Pubblicazione GitHub + PyPI
- [ ] Esempi reali: "Collega 4 agenti in 5 minuti"

---

## Conclusione

Agora non è un'invenzione. È un **esercizio di ingegneria** su un problema reale (memoria isolata tra agenti) con strumenti moderni (MCP, vector search, embeddings).

Non cerca di competere con progetti IBM o startup. Cerca di:
1. **Funzionare** per i workflow personali dell'autore
2. **Dimostrare** competenza su AI infrastructure
3. **Essere** un pezzo di portfolio che mostra pensiero sistemico

Se risolve il problema di 4 agenti che non condividono memoria, ha già vinto.
