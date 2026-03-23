# SAP O2C Context Graph + LLM SQL Chat (Backend)

This project builds a backend for querying SAP Order-to-Cash (O2C) data using natural language.

Workflow:

`User Question -> LLM (Groq) -> SQL -> Safety Check -> PostgreSQL (Neon) -> Results -> Natural Language Answer`

It also exposes a relationship graph API for visualization in a frontend.

---

## 1) Project Overview

The backend supports two core capabilities:

- **Natural language analytics** on SAP O2C data.
- **Graph exploration** of entity relationships (orders, billing docs, deliveries, customers, products, payments, journal entries).

Data source is JSONL (one object per line), organized by entity folders under `sap-o2c-data/`.

---

## 2) Tech Stack

- Python
- Flask
- PostgreSQL (Neon)
- psycopg2
- Groq API (`llama3-70b-8192`)
- NetworkX
- python-dotenv

---

## 3) Folder Structure

```text
backend-v2/
├── app.py
├── db.py
├── create_tables.py
├── load_data.py
├── query.py
├── llm.py
├── graph.py
├── requirements.txt
├── .env
└── sap-o2c-data/
    └── .../
```

---

## 4) Environment Setup

Create `.env` in project root:

```env
DATABASE_URL=your_neon_postgres_connection_string
GROQ_API_KEY=your_groq_api_key
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Recommended: use a virtual environment.

---

## 5) Data Modeling Strategy

### Base columns
- All raw source columns are created as **TEXT** for schema flexibility.

### Shadow numeric columns (performance + clean SQL)
- For known amount/quantity fields, additional `NUMERIC` columns are created with suffix `_num`.
- Examples:
  - `"billing_document_items"."netAmount_num"`
  - `"payments_accounts_receivable"."amountInTransactionCurrency_num"`
  - `"sales_order_items"."requestedQuantity_num"`

These are populated during load and used for aggregation (`SUM`, `AVG`, etc.) so SQL stays clean and fast.

---

## 6) End-to-End Workflow

## Step A: Database connection (`db.py`)

- Loads `.env`
- Reads `DATABASE_URL`
- Returns psycopg2 connection via `get_connection()`

## Step B: Table creation (`create_tables.py`)

- Scans each dataset folder under `sap-o2c-data/`
- Infers columns from all JSONL part files
- Creates tables using `CREATE TABLE IF NOT EXISTS`
- Adds shadow numeric columns using:
  - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS "<field>_num" NUMERIC`

Run:

```bash
python create_tables.py
```

## Step C: Data loading (`load_data.py`)

- Reads all JSONL files for every entity folder
- Inserts rows in batches (fast path)
- Falls back to row-by-row insert on batch failure (robustness)
- Safely handles missing fields (`record.get(field, None)`)
- Converts numeric fields into `_num` columns via Decimal parsing
- Supports idempotent reloads:
  - default: `truncate_before_load=True`
  - append mode: `--append`

Run (idempotent):

```bash
python load_data.py
```

Run (append):

```bash
python load_data.py --append
```

## Step D: Safe SQL execution (`query.py`)

- Executes read-only SQL and returns `List[Dict]`
- Blocks unsafe keywords/operations
- Allows only queries starting with `SELECT` or `WITH`
- Blocks multi-statement SQL (`;`)

This prevents accidental DML/DDL operations against production-like data.

## Step E: LLM SQL generation (`llm.py`)

- Uses Groq model: `llama3-70b-8192`
- Prompt includes schema, relationships, and examples
- Rules enforced:
  - return SQL only (or `OFFTOPIC`)
  - quote case-sensitive identifiers
  - use `_num` columns for math
- Flow inside `answer_question(question)`:
  1. Generate SQL from question
  2. Handle `OFFTOPIC`
  3. Safety-check SQL using `query.is_safe_sql`
  4. Execute query
  5. Convert DB result to grounded natural language answer

## Step F: API layer (`app.py`)

Flask endpoints:

- `POST /query`
  - Input: `{ "question": "..." }`
  - Output:
    ```json
    {
      "sql": "...",
      "result": [...],
      "answer": "..."
    }
    ```
- `GET /graph`
  - Returns full graph for visualization.
- `GET /expand/<node_id>`
  - Returns neighbors of a selected node.

## Step G: Graph generation (`graph.py`)

- Builds graph from PostgreSQL using NetworkX.
- Node format:
  - `id`: `<type>:<primary_key>`
  - `type`: entity type
  - `metadata`: source attributes
- Edge format:
  - `source`, `target`, `relation`
- Implements key O2C relationships across sales, billing, delivery, payments, and journal entries.

---

## 7) API Examples

### Query

`POST /query`

```json
{
  "question": "Top 10 customers by total billing amount"
}
```

Expected behavior:
- LLM should generate SQL using `_num` columns for aggregation.
- SQL passes safety checks.
- API returns SQL + rows + grounded answer.

### Graph

`GET /graph`

Returns:

```json
{
  "nodes": [
    {
      "id": "sales_order:50000001",
      "type": "sales_order",
      "metadata": {}
    }
  ],
  "edges": [
    {
      "source": "sales_order:50000001",
      "target": "sales_order_item:50000001-10",
      "relation": "sales_order_to_items"
    }
  ]
}
```

---

## 8) Running the Backend

Start Flask server:

```bash
python app.py
```

Default URL:

- `http://localhost:5000`

---

## 9) Important Guardrails

- No DML/DDL execution through chat (`INSERT`, `UPDATE`, `DELETE`, `DROP`, etc. blocked).
- Multi-statement SQL blocked.
- Out-of-scope questions return controlled off-topic message.
- SQL is grounded to known schema + relationships.

---

## 10) Common Issues and Fixes

### 1) `column ... does not exist` with camelCase fields
Cause: unquoted identifiers in PostgreSQL are lowercased.
Fix: ensure SQL uses quoted identifiers, e.g. `"accountingDocument"`.

### 2) `sum(text) does not exist`
Cause: aggregating text columns directly.
Fix: use shadow numeric columns, e.g. `SUM("netAmount_num")`.

### 3) `Decimal is not JSON serializable`
Cause: Decimal values in response serialization.
Fix: convert Decimal safely to string/float before JSON response.

### 4) Duplicate rows after reloading
Fix: use default load mode (`python load_data.py`) which truncates first.

---

## 11) Suggested Next Improvements

- Add app-level JSON encoder to auto-handle Decimal globally.
- Add graph caching (TTL) for faster `/graph` and `/expand`.
- Add automated tests for:
  - SQL safety checker
  - loader numeric parsing
  - key LLM prompt examples
- Add pagination for large query results and large graph responses.

---

## 12) License / Usage

Use this project for internal analytics and prototyping.  
For production use, add authentication, stricter rate limiting, and full audit logging.

