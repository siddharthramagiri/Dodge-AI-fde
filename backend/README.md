# SAP O2C Flask Backend

Pure-JSON REST API for the SAP Order-to-Cash graph system.
Designed to be consumed by a Next.js (or any) frontend.

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Add your Gemini key
echo "GEMINI_API_KEY=AIza..." > .env

# 3. Ingest data (run once, or whenever data changes)
python ingest.py

# 4. Start the server
python app.py               # development
gunicorn app:app --bind 0.0.0.0:5000   # production
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | Yes (for chat) | Google Gemini API key |

---

## API Reference

All responses are `Content-Type: application/json`.

### `GET /api/health`
Liveness check.
```json
{ "status": "ok", "nodes": 1240, "edges": 3800 }
```

---

### `POST /api/set-api-key`
Override the Gemini API key at runtime without restarting.
```json
// Request
{ "api_key": "AIza..." }

// Response
{ "status": "ok" }
```

---

### `GET /api/graph/overview?max_nodes=150`
Sampled graph for initial render (vis.js format).
```json
{
  "nodes": [
    {
      "id": "SalesOrder:700001",
      "label": "SalesOrder\n700001",
      "title": "SalesOrder: 700001 | totalNetAmount: 1200.00 | ...",
      "color": "#4A90D9",
      "type": "SalesOrder",
      "key": "700001",
      "group": "SalesOrder"
    }
  ],
  "edges": [
    { "from": "SalesOrder:700001", "to": "BusinessPartner:10001", "label": "SOLD_TO", "arrows": "to" }
  ]
}
```

---

### `GET /api/graph/stats`
```json
{
  "total_nodes": 1240,
  "total_edges": 3800,
  "node_types": { "SalesOrder": 200, "BillingDocument": 180, ... },
  "relationship_types": { "HAS_ITEM": 600, "SOLD_TO": 200, ... }
}
```

---

### `GET /api/graph/node/:node_id`
Full node attributes.
- Path example: `/api/graph/node/SalesOrder:700001`
```json
{
  "type": "SalesOrder",
  "key": "700001",
  "color": "#4A90D9",
  "totalNetAmount": 1200.00,
  "currency": "USD",
  ...
}
```

---

### `GET /api/graph/expand/:node_id`
1-hop neighbourhood of a node (for drill-down).
```json
{
  "nodes": [...],
  "edges": [...]
}
```

---

### `GET /api/graph/type/:node_type?limit=50`
List nodes by type. Types: `SalesOrder`, `SalesOrderItem`, `BillingDocument`,
`OutboundDelivery`, `BusinessPartner`, `Product`, `Plant`, `JournalEntry`, `Payment`
```json
{
  "node_type": "SalesOrder",
  "count": 50,
  "nodes": [...]
}
```

---

### `POST /api/chat`
Natural-language query. LLM generates SQL, runs it, then explains the results.

```json
// Request
{
  "message": "Which customers have the highest total billed amount?",
  "history": [
    { "role": "user", "content": "How many sales orders are there?" },
    { "role": "assistant", "content": "There are 200 sales orders." }
  ],
  "api_key": "AIza..."   // optional per-request override
}

// Success response
{
  "response": "The top customer is ACME Corp (BP 10001) with $450,000 billed.",
  "sql_used": "SELECT soldToParty, SUM(totalNetAmount) AS total FROM billing_document_headers GROUP BY soldToParty ORDER BY total DESC LIMIT 10",
  "results_count": 10,
  "query_results": [ { "soldToParty": "10001", "total": 450000.0 }, ... ],
  "referenced_nodes": ["BillingDocument:90000001"]
}

// Off-topic (400)
{
  "error": "off_topic",
  "response": "This system is designed to answer questions related to ...",
  "sql_used": null,
  "results_count": null,
  "query_results": null,
  "referenced_nodes": []
}

// No API key (503)
{
  "error": "llm_not_configured",
  "message": "No Gemini API key configured. POST /api/set-api-key ..."
}
```

---

### `POST /api/sql`
Direct SQL execution (SELECT only). Max 100 rows.

```json
// Request
{ "sql": "SELECT * FROM sales_order_headers LIMIT 5" }

// Response
{ "rows": [...], "count": 5 }
```

---

## Next.js integration example

```ts
// lib/o2c.ts

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5000";

export async function getGraphOverview(maxNodes = 150) {
  const res = await fetch(`${BASE}/api/graph/overview?max_nodes=${maxNodes}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { nodes, edges }
}

export async function chatQuery(message: string, history = []) {
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

---

## Node types & colors

| Type | Color | Description |
|---|---|---|
| SalesOrder | `#4A90D9` | SAP sales order header |
| SalesOrderItem | `#A8D4F5` | Line items within a sales order |
| BillingDocument | `#27AE60` | Invoice / billing doc |
| OutboundDelivery | `#F39C12` | Shipment / delivery |
| BusinessPartner | `#8E44AD` | Customer / partner |
| Product | `#E74C3C` | Material / product |
| Plant | `#795548` | Production / shipping plant |
| JournalEntry | `#78909C` | GL / accounting document |
| Payment | `#00BCD4` | Cleared payment |

## Edge / relationship types

`HAS_ITEM` · `SOLD_TO` · `REFERENCES_PRODUCT` · `PRODUCED_AT` ·
`BILLED_TO` · `POSTED_TO` · `CANCELS` · `BILLED_AS` ·
`DELIVERS_FOR` · `SHIPPED_FROM` · `ASSOCIATED_WITH`
