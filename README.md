# SAP O2C Context Graph + LLM SQL Chat (Backend)

This project builds a backend for querying SAP Order-to-Cash (O2C) data using natural language.

Workflow:

`User Question → Gemini LLM → SQL → Safety Check → SQLite → Results → Natural Language Answer`

It also exposes a relationship graph API for visualization in a Next.js frontend.



## 1) Project Overview

The backend supports two core capabilities:

- **Natural language analytics** on SAP O2C data — ask questions in plain English and get SQL-grounded answers.
- **Graph exploration** of entity relationships (orders, billing documents, deliveries, customers, products, payments, journal entries).

Data source is JSONL (one object per line), organized by entity folders under `sap-o2c-data/`.



## 2) Tech Stack

- Python
- Flask + flask-cors
- SQLite (local file - `o2c.db`)
- Google Gemini API (`gemini-2.5-flash`)
- NetworkX
- python-dotenv



## 3) Folder Structure

```text
sap-o2c-flask/
├── app.py               ← Flask JSON API (all endpoints)
├── graph_builder.py     ← NetworkX graph builder + singleton
├── ingest.py            ← JSONL → SQLite loader
├── requirements.txt
├── .env
├── o2c.db               ← generated after running ingest.py
└── sap-o2c-data/
    ├── sales_order_headers/
    ├── billing_document_headers/
    └── .../             ← 19 entity folders, each with *.jsonl part files
```



## 4) Environment Setup

Create `.env` in the project root:

```env
GEMINI_API_KEY=your_google_gemini_api_key
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Recommended: use a virtual environment.



## 5) Data Modeling Strategy

### Typed SQLite columns

Unlike an all-TEXT schema, this project uses native SQLite column types:

- `TEXT` — identifiers, codes, dates, status fields
- `REAL` — all amount and quantity fields (e.g. `totalNetAmount`, `requestedQuantity`, `billingQuantity`)
- `INTEGER` — boolean flags (e.g. `billingDocumentIsCancelled`)

This means SQL aggregations like `SUM(totalNetAmount)` and `AVG(requestedQuantity)` work natively — no runtime casting, no `_num` shadow columns needed. The LLM generates cleaner SQL as a result.

### Nested JSON flattening

JSONL records with nested objects are flattened automatically on ingest:

```
{ "creationTime": { "hours": 9, "minutes": 30 } }
→ { "creationTime_hours": 9, "creationTime_minutes": 30 }
```



## 6) End-to-End Workflow

### Step A: Data ingestion (`ingest.py`)

- Scans all 19 entity folders under `sap-o2c-data/`
- Reads every `*.jsonl` part file per folder
- Flattens nested JSON objects automatically
- Creates typed SQLite tables with `CREATE TABLE IF NOT EXISTS`
- Inserts records using `INSERT OR IGNORE` (idempotent — safe to re-run)
- Uses `PRAGMA journal_mode=WAL` for better read concurrency

Run once before starting the server:

```bash
python ingest.py
```

Re-running `ingest.py` drops and recreates `o2c.db` from scratch for a clean reload.

### Step B: Graph builder (`graph_builder.py`)

- Builds a NetworkX `DiGraph` from SQLite data on Flask startup
- Each entity becomes a typed node: `id = "Type:key"` (e.g. `"SalesOrder:700001"`)
- Edges are derived from FK relationships across all tables
- Held as a module-level singleton — all graph API calls are pure in-memory, no DB query per request
- Exposes: `to_vis_data()`, `get_neighbors()`, `get_stats()`, `find_nodes_by_type()`

### Step C: API layer (`app.py`)

- Flask app with CORS enabled globally via `flask-cors`
- Graph preloaded on startup inside `with app.app_context()`
- Gemini key loaded from `.env` — can also be overridden at runtime via `POST /api/set-api-key`
- **Two-pass Gemini approach** for chat:
  - Pass 1 → generate SQL from the question
  - Pass 2 → narrate the SQL result in natural language
- All endpoints return pure JSON — no HTML, no templates



## 7) API Reference

All responses are `Content-Type: application/json`.

### Health

`GET /api/health`

```json
{ "status": "ok", "nodes": 1240, "edges": 3800 }
```

---

### API Key (runtime override)

`POST /api/set-api-key`

```json
// Request
{ "api_key": "AIza..." }

// Response
{ "status": "ok" }
```

---

### Graph

`GET /api/graph/overview?max_nodes=150`

Returns sampled nodes + edges in vis.js format:

```json
{
  "nodes": [
    {
      "id": "SalesOrder:700001",
      "label": "SalesOrder\n700001",
      "color": "#4A90D9",
      "type": "SalesOrder",
      "key": "700001",
      "group": "SalesOrder"
    }
  ],
  "edges": [
    {
      "from": "SalesOrder:700001",
      "to": "BusinessPartner:10001",
      "label": "SOLD_TO",
      "arrows": "to"
    }
  ]
}
```

`GET /api/graph/stats`

```json
{
  "total_nodes": 1240,
  "total_edges": 3800,
  "node_types": { "SalesOrder": 100, "BillingDocument": 163, "..." : "..." },
  "relationship_types": { "HAS_ITEM": 167, "SOLD_TO": 100, "...": "..." }
}
```

`GET /api/graph/node/<node_id>`

Returns full attribute payload for a single node.

`GET /api/graph/expand/<node_id>`

Returns 1-hop neighbourhood (predecessors + successors) for drill-down:

```json
{ "nodes": [...], "edges": [...] }
```

`GET /api/graph/type/<node_type>?limit=50`

Lists all nodes of a given type. Types: `SalesOrder`, `SalesOrderItem`, `BillingDocument`, `OutboundDelivery`, `BusinessPartner`, `Product`, `Plant`, `JournalEntry`, `Payment`.



### Chat

`POST /api/chat`

```json
// Request
{
  "message": "Which customers have the highest total billed amount?",
  "history": [
    { "role": "user", "content": "How many sales orders are there?" },
    { "role": "assistant", "content": "There are 100 sales orders." }
  ],
  "api_key": "AIza..."
}

// Success response
{
  "response": "The top customer is ACME Corp (BP 10001) with $450,000 billed.",
  "sql_used": "SELECT soldToParty, SUM(totalNetAmount) FROM billing_document_headers GROUP BY soldToParty ORDER BY SUM(totalNetAmount) DESC LIMIT 10",
  "results_count": 10,
  "query_results": [ { "soldToParty": "10001", "SUM(totalNetAmount)": 450000.0 } ],
  "referenced_nodes": ["BillingDocument:90000001"]
}

// Off-topic (400)
{
  "error": "off_topic",
  "response": "This system is designed to answer questions related to the provided SAP Order-to-Cash dataset only."
}

// No API key (503)
{
  "error": "llm_not_configured",
  "message": "Set GEMINI_API_KEY in .env or POST /api/set-api-key"
}
```



### Direct SQL

`POST /api/sql`

Executes a raw SELECT query. SELECT only — max 100 rows enforced.

```json
// Request
{ "sql": "SELECT * FROM sales_order_headers LIMIT 5" }

// Response
{ "rows": [...], "count": 5 }
```



## 8) Running the Backend

Ingest data (run once):

```bash
python ingest.py
```

Start Flask server:

```bash
python app.py
```

Default URL: `http://localhost:5000`

For production:

```bash
gunicorn app:app --bind 0.0.0.0:5000
```



## 9) Frontend Integration (Next.js)

Add to `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:5000
```

Example fetch utility (`lib/o2c.ts`):

```typescript
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5000";

export async function getGraphOverview(maxNodes = 150) {
  const res = await fetch(`${BASE}/api/graph/overview?max_nodes=${maxNodes}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { nodes, edges }
}

export async function sendChatMessage(message: string, history = []) {
  const res = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { response, sql_used, results_count, query_results, referenced_nodes }
}

export async function expandNode(nodeId: string) {
  const res = await fetch(`${BASE}/api/graph/expand/${encodeURIComponent(nodeId)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { nodes, edges }
}
```

Use `referenced_nodes` from chat responses to highlight graph nodes after each answer. Use `expandNode()` on node click to grow the graph progressively.



## 10) Node Types and Colors

| Type | Color | Description |
|---|---|---|
| SalesOrder | `#4A90D9` | SAP sales order header |
| SalesOrderItem | `#A8D4F5` | Line items within a sales order |
| BillingDocument | `#27AE60` | Invoice / billing document |
| OutboundDelivery | `#F39C12` | Shipment / outbound delivery |
| BusinessPartner | `#8E44AD` | Customer or partner |
| Product | `#E74C3C` | Material / product |
| Plant | `#795548` | Production or shipping plant |
| JournalEntry | `#78909C` | GL / accounting document |
| Payment | `#00BCD4` | Cleared payment record |

## 11) Edge / Relationship Types

| Relationship | From | To |
|---|---|---|
| `HAS_ITEM` | SalesOrder | SalesOrderItem |
| `SOLD_TO` | SalesOrder | BusinessPartner |
| `REFERENCES_PRODUCT` | SalesOrderItem | Product |
| `PRODUCED_AT` | SalesOrderItem | Plant |
| `BILLED_AS` | SalesOrder | BillingDocument |
| `BILLED_TO` | BillingDocument | BusinessPartner |
| `POSTED_TO` | BillingDocument | JournalEntry |
| `CANCELS` | BillingDocument | BillingDocument |
| `DELIVERS_FOR` | OutboundDelivery | SalesOrder |
| `SHIPPED_FROM` | OutboundDelivery | Plant |
| `ASSOCIATED_WITH` | Payment | JournalEntry |



## 12) Important Guardrails

- Only `SELECT` and `WITH` queries are executed — `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE` are all blocked.
- Multi-statement SQL (`;` mid-query) is blocked.
- Off-topic questions are detected and rejected before the LLM is called.
- Gemini API key is never exposed to the frontend — set server-side only.
- All SQL results are capped at 50 rows via auto-appended `LIMIT 50`.


## 13) Common Issues and Fixes

### 1) Graph loads 0 nodes
Cause: `o2c.db` does not exist yet.
Fix: run `python ingest.py` before starting the server.

### 2) Chat returns `llm_not_configured`
Cause: `GEMINI_API_KEY` not set.
Fix: add `GEMINI_API_KEY=...` to `.env` or call `POST /api/set-api-key` at runtime.

### 3) Ingest skips many rows
Cause: JSONL field names don't match table column names after flattening.
Fix: check the flatten output — nested keys become `parent_child` format. Verify the `PRAGMA table_info(<table>)` output matches your JSONL keys.

### 4) `OperationalError: no such column`
Cause: generated SQL references a column name that doesn't match the SQLite schema.
Fix: SQLite column names are case-sensitive. Check the exact column names in the schema via `GET /api/sql` with `SELECT * FROM <table> LIMIT 1`.

### 5) CORS errors from Next.js
Cause: Flask not returning CORS headers.
Fix: confirm `flask-cors` is installed and `CORS(app)` is called before any route definitions in `app.py`.


## 15) License / Usage

Use this project for internal analytics and prototyping.
For production use, add authentication, rate limiting, and full audit logging.