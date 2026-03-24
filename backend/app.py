import os
import re
import json
import sqlite3
from typing import Optional, List, Dict

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from util import notify

import google.generativeai as genai
from graph_builder import get_graph, make_node_id

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

load_dotenv()

app = Flask(__name__)

# Allow all origins by default — tighten this in production:
#   CORS(app, origins=["http://localhost:3000", "https://yourdomain.com"])
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "o2c.db")

# Runtime Gemini key (can be overridden per-request or via env)
_runtime_api_key: str = os.getenv("GEMINI_API_KEY", "")


# ---------------------------------------------------------------------------
# Preload graph on startup
# ---------------------------------------------------------------------------

with app.app_context():
    print("Loading O2C graph from database…")
    get_graph()
    print("Graph ready.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_error(message: str, status: int = 400):
    """Return a JSON error response."""
    return jsonify({"error": message}), status


def get_gemini_model(api_key: str = ""):
    """Return a configured Gemini model or None if no key available."""
    key = api_key or _runtime_api_key
    if not key:
        return None
    genai.configure(api_key=key)
    return genai.GenerativeModel("gemini-2.5-flash")


def get_db_schema() -> str:
    conn = sqlite3.connect(DB_PATH)
    parts = []
    for row in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
    ):
        _, sql = row
        if sql:
            parts.append(sql)
    conn.close()
    return "\n\n".join(parts)


def get_sample_rows(limit: int = 2) -> str:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    tables = [
        "sales_order_headers",
        "sales_order_items",
        "billing_document_headers",
        "billing_document_items",
        "outbound_delivery_headers",
        "outbound_delivery_items",
        "business_partners",
        "payments_accounts_receivable",
    ]
    samples = []
    for t in tables:
        try:
            rows = conn.execute(f"SELECT * FROM {t} LIMIT {limit}").fetchall()
            if rows:
                samples.append(f"-- {t} sample:")
                for row in rows:
                    samples.append(json.dumps(dict(row)))
        except Exception:
            pass
    conn.close()
    return "\n".join(samples)


def run_sql(sql: str) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        raise ValueError(f"SQL error: {e}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Off-topic guardrail
# ---------------------------------------------------------------------------

OFF_TOPIC_PATTERNS = [
    r"\b(who is|what is the capital|history of|write a|tell me a|recipe for|explain quantum|"
    r"weather|stock price|poem|story|joke|translate|movie|music|sport|celebrity|"
    r"president|prime minister|election|covid|covid-19|vaccine|python tutorial|"
    r"machine learning basics|define the word)\b",
]
DOMAIN_KEYWORDS = [
    "sales order", "billing", "invoice", "delivery", "payment", "product", "material",
    "customer", "business partner", "plant", "journal", "accounting", "shipment",
    "order", "document", "flow", "sap", "o2c", "outbound", "fiscal", "currency",
    "quantity", "amount", "status", "date", "billed", "delivered", "cancelled",
    "transaction", "reference", "schedule", "incoterms", "distribution",
]


def is_off_topic(query: str) -> bool:
    q_lower = query.lower()
    for pattern in OFF_TOPIC_PATTERNS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            if not any(kw in q_lower for kw in DOMAIN_KEYWORDS):
                return True
    if len(query) > 20 and not any(kw in q_lower for kw in DOMAIN_KEYWORDS):
        nonsense = [r"\b(love|hate|feel|opinion|think about|dream|wish)\b"]
        for np in nonsense:
            if re.search(np, q_lower):
                return True
    return False


# ---------------------------------------------------------------------------
# LLM system prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant for a SAP Order-to-Cash (O2C) data analysis system.
You ONLY answer questions about the following dataset. Refuse any off-topic queries.

DATABASE SCHEMA:
{schema}

SAMPLE DATA:
{samples}

RULES:
1. Only answer questions about the SAP O2C dataset (sales orders, billing documents, deliveries, payments, products, customers, plants, journal entries).
2. If asked anything unrelated, respond: "This system is designed to answer questions related to the provided SAP Order-to-Cash dataset only."
3. Always generate valid SQLite SQL queries when needed.
4. The billingDocument ID is the primary key for billing_document_headers.
5. SalesOrder links to BillingDocument via billing_document_items.salesDocument.
6. OutboundDelivery links to SalesOrder via outbound_delivery_items.salesOrder.
7. Delivery status: "C" = complete, "A" = in progress, "B" = partially delivered.
8. billingDocumentIsCancelled = 1 means the billing document is cancelled.
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        schema=get_db_schema(),
        samples=get_sample_rows(),
    )


def extract_sql(text: str) -> Optional[str]:
    patterns = [
        r"```sql\n(.*?)\n```",
        r"```\n(SELECT.*?)\n```",
        r"(SELECT\s+.+?;)",
        r"(SELECT\s+.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            sql = match.group(1).strip()
            if sql.upper().startswith("SELECT"):
                return sql
    return None


def extract_node_references(text: str, results: List[Dict]) -> List[str]:
    ids = set()
    for m in re.finditer(r'\b(7[0-9]{5})\b', text):
        ids.add(f"SalesOrder:{m.group(1)}")
    for m in re.finditer(r'\b(9[0-9]{7})\b', text):
        ids.add(f"BillingDocument:{m.group(1)}")
    for row in results[:10]:
        for v in row.values():
            if isinstance(v, str):
                if re.match(r'^7\d{5}$', v):
                    ids.add(f"SalesOrder:{v}")
                elif re.match(r'^9\d{7}$', v):
                    ids.add(f"BillingDocument:{v}")
    return list(ids)[:20]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    """Simple liveness check."""
    g = get_graph()
    return jsonify({
        "status": "ok",
        "nodes": g.G.number_of_nodes(),
        "edges": g.G.number_of_edges(),
    })


# ── API key (runtime override) ────────────────────────────────────────────────

@app.post("/api/set-api-key")
def set_api_key():
    """
    Override the Gemini API key at runtime without restarting.
    Body: { "api_key": "AIza..." }
    """
    global _runtime_api_key
    body = request.get_json(silent=True) or {}
    key = body.get("api_key", "").strip()
    if not key:
        return _json_error("api_key is required")
    _runtime_api_key = key
    return jsonify({"status": "ok"})


# ── Graph endpoints ───────────────────────────────────────────────────────────

@app.get("/api/graph/overview")
def graph_overview():
    """
    Returns a sampled view of the graph suitable for initial rendering.

    Query params:
        max_nodes (int, default 150) — cap on returned nodes

    Response:
    {
        "nodes": [ { "id", "label", "title", "color", "type", "key", "group", ...attrs } ],
        "edges": [ { "from", "to", "label", "arrows" } ]
    }
    """
    max_nodes = request.args.get("max_nodes", 2000, type=int)
    g = get_graph()
    return jsonify(g.to_vis_data(max_nodes=max_nodes))


@app.get("/api/graph/stats")
def graph_stats():
    """
    Graph-level statistics.

    Response:
    {
        "total_nodes": int,
        "total_edges": int,
        "node_types":  { "SalesOrder": int, ... },
        "relationship_types": { "HAS_ITEM": int, ... }
    }
    """
    g = get_graph()
    return jsonify(g.get_stats())


@app.get("/api/graph/node/<path:node_id>")
def get_node(node_id: str):
    """
    Full attribute payload for a single node.

    Path: /api/graph/node/SalesOrder:700001

    Response: { "type", "key", "color", "shape", "label", ...all attrs }
    404 if not found.
    """
    g = get_graph()
    data = g.get_node_data(node_id)
    if data is None:
        return _json_error(f"Node not found: {node_id}", 404)
    return jsonify(data)


@app.get("/api/graph/expand/<path:node_id>")
def expand_node(node_id: str):
    """
    Return the ego-graph (1-hop neighbourhood) of a node.

    Path: /api/graph/expand/SalesOrder:700001

    Response:
    {
        "nodes": [...],
        "edges": [...]
    }
    404 if node_id doesn't exist.
    """
    g = get_graph()
    data = g.get_neighbors(node_id)
    if not data["nodes"]:
        return _json_error(f"Node not found: {node_id}", 404)
    return jsonify(data)


@app.get("/api/graph/type/<node_type>")
def nodes_by_type(node_type: str):
    """
    List nodes of a given type.

    Path: /api/graph/type/SalesOrder
    Query params:
        limit (int, default 50)

    Response:
    {
        "node_type": "SalesOrder",
        "count": int,
        "nodes": [ { "id", "key", ...attrs } ]
    }
    """
    limit = request.args.get("limit", 50, type=int)
    g = get_graph()
    nodes = g.find_nodes_by_type(node_type, limit)
    return jsonify({
        "node_type": node_type,
        "count": len(nodes),
        "nodes": nodes,
    })


# ── Chat / NL query ───────────────────────────────────────────────────────────

@app.post("/api/chat")
def chat():
    """
    Natural-language query against the O2C dataset.

    Request body (JSON):
    {
        "message":  "Which sales orders have undelivered items?",
        "history":  [ { "role": "user"|"assistant", "content": "..." } ],  // optional
        "api_key":  "AIza..."   // optional — overrides env / runtime key
    }

    Response:
    {
        "response":          "string — human-readable answer",
        "sql_used":          "SELECT ... | null",
        "results_count":     42 | null,
        "query_results":     [ {...}, ... ] | null,   // raw SQL rows (max 20)
        "referenced_nodes":  ["SalesOrder:700001", ...]
    }

    Error shapes:
        400  { "error": "Empty message" }
        400  { "error": "off_topic" }
        503  { "error": "llm_not_configured", "message": "..." }
        500  { "error": "llm_error", "message": "..." }
    """
    body = request.get_json(silent=True) or {}
    query = (body.get("message") or "").strip()
    history: List[Dict] = body.get("history") or []
    request_key: str = (body.get("api_key") or "").strip()

    if not query:
        return _json_error("Empty message")

    # Guardrail
    if is_off_topic(query):
        return jsonify({
            "error": "off_topic",
            "response": (
                "This system is designed to answer questions related to "
                "the provided SAP Order-to-Cash dataset only."
            ),
            "sql_used": None,
            "results_count": None,
            "query_results": None,
            "referenced_nodes": [],
        }), 400

    model = get_gemini_model(request_key)
    if not model:
        return jsonify({
            "error": "llm_not_configured",
            "message": (
                "No Gemini API key configured. "
                "POST /api/set-api-key with { \"api_key\": \"...\" } "
                "or set GEMINI_API_KEY in your .env file."
            ),
            "sql_used": None,
            "results_count": None,
            "query_results": None,
            "referenced_nodes": [],
        }), 503

    notify(query)
    
    try:
        system_prompt = build_system_prompt()

        # Build conversation context from history (last 4 turns)
        history_text = ""
        for turn in history[-4:]:
            role = turn.get("role", "user").upper()
            content = turn.get("content", "")
            history_text += f"\n{role}: {content}"

        # ── Step 1: Generate SQL ──────────────────────────────────────────
        sql_prompt = (
            f"{system_prompt}\n"
            f"{history_text}\n\n"
            f"USER QUESTION: {query}\n\n"
            "Generate a SQLite SQL query to answer this question.\n"
            "Return ONLY the SQL query wrapped in ```sql ... ``` blocks.\n"
            "If no SQL is needed, return NO_SQL_NEEDED.\n"
            "Always add LIMIT 50 if not present."
        )

        sql_response = model.generate_content(sql_prompt)
        sql_text = sql_response.text.strip()

        sql_query: Optional[str] = None
        query_results: Optional[List[Dict]] = None
        results_count: Optional[int] = None

        if "NO_SQL_NEEDED" not in sql_text:
            sql_query = extract_sql(sql_text)
            if sql_query:
                if not re.match(r"^\s*SELECT\s", sql_query, re.IGNORECASE):
                    sql_query = None
                else:
                    if "LIMIT" not in sql_query.upper():
                        sql_query = sql_query.rstrip(";") + " LIMIT 50"
                    try:
                        query_results = run_sql(sql_query)
                        results_count = len(query_results)
                    except ValueError:
                        sql_query = None

        # ── Step 2: Natural-language answer ──────────────────────────────
        results_context = ""
        if query_results is not None:
            if query_results:
                results_context = (
                    f"\nQUERY RESULTS ({len(query_results)} rows):\n"
                    f"{json.dumps(query_results[:20], indent=2)}"
                )
            else:
                results_context = "\nQUERY RESULTS: No data found."

        answer_prompt = (
            f"{system_prompt}\n\n"
            f"USER QUESTION: {query}\n"
            f"{f'SQL EXECUTED: {sql_query}' if sql_query else ''}"
            f"{results_context}\n\n"
            "Provide a clear, concise, data-backed answer.\n"
            "- If results are empty, say no data was found.\n"
            "- Include specific IDs and numbers from the results.\n"
            "- Format numbers nicely.\n"
            "- For flow/trace questions, describe the full flow step by step.\n"
            "- Do NOT make up data that is not in the results.\n"
            "- Keep the answer focused and professional."
        )

        answer_response = model.generate_content(answer_prompt)
        answer_text = answer_response.text.strip()

        # ── Node references for graph highlighting ────────────────────────
        referenced = extract_node_references(answer_text, query_results or [])

        return jsonify({
            "response": answer_text,
            "sql_used": sql_query,
            "results_count": results_count,
            "query_results": query_results[:20] if query_results else None,
            "referenced_nodes": referenced,
        })

    except Exception as e:
        return jsonify({
            "error": "llm_error",
            "message": str(e),
            "sql_used": None,
            "results_count": None,
            "query_results": None,
            "referenced_nodes": [],
        }), 500


# ── Direct SQL endpoint (optional dev/debug use) ──────────────────────────────

@app.post("/api/sql")
def run_sql_endpoint():
    """
    Execute a raw SELECT query directly (no LLM).
    Useful for debugging or power-user integrations.

    Request body:
    { "sql": "SELECT * FROM sales_order_headers LIMIT 10" }

    Response:
    { "rows": [...], "count": int }

    Restrictions: only SELECT statements; enforces LIMIT 100 max.
    """
    body = request.get_json(silent=True) or {}
    sql = (body.get("sql") or "").strip()

    if not sql:
        return _json_error("sql is required")
    if not re.match(r"^\s*SELECT\s", sql, re.IGNORECASE):
        return _json_error("Only SELECT statements are allowed")
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 100"

    try:
        rows = run_sql(sql)
        return jsonify({"rows": rows, "count": len(rows)})
    except ValueError as e:
        return _json_error(str(e), 422)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)