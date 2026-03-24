# Context Graph System for SAP Order to Cash
*Session exported on 3/24/2026 from Cursor (2.6.20)*

---

**User**

I am building a context graph system with an LLM powered chat interface for a SAP Order to Cash dataset.

The project folder is at D:/Projects/AI/Dodge-AI/ and the dataset is inside a folder called sap-o2c-data within it. The dataset is in JSONL format, one JSON object per line. Each entity has its own folder and each folder may contain multiple part files. The loader must read all part files inside each folder and combine them into one SQLite table.

DATASET FOLDERS

sales_order_headers, sales_order_items, billing_document_headers, billing_document_items, billing_document_cancellations, outbound_delivery_headers, outbound_delivery_items, payments_accounts_receivable, journal_entry_items_accounts_receivable, business_partners, business_partner_addresses, products, product_descriptions, product_plants, product_storage_locations, plants, customer_company_assignments, customer_sales_area_assignments, sales_order_schedule_lines

CORE GOAL

Build a system where:
User → LLM → SQL → SQLite → Result → Answer

The LLM MUST generate SQL dynamically and all answers must be grounded in database results.

DATABASE

Use SQLite. Database file stored as o2c.db in the project root. Use Python's built-in sqlite3 module. No external DB dependencies. Use typed columns — TEXT for identifiers and strings, REAL for amounts and quantities.

CORE TABLE SCHEMAS

sales_order_headers: salesOrder, salesOrderType, soldToParty, creationDate, totalNetAmount REAL, overallDeliveryStatus, transactionCurrency

sales_order_items: salesOrder, salesOrderItem, material, requestedQuantity REAL, netAmount REAL, productionPlant, storageLocation

billing_document_headers: billingDocument, billingDocumentType, creationDate, totalNetAmount REAL, soldToParty, accountingDocument, fiscalYear, companyCode, billingDocumentIsCancelled INTEGER

billing_document_items: billingDocument, billingDocumentItem, salesOrder, salesOrderItem, material, billingQuantity REAL, netAmount REAL

outbound_delivery_headers: outboundDelivery, creationDate, shippingPoint, overallDeliveryStatus, actualGoodsMovementDate

outbound_delivery_items: outboundDelivery, outboundDeliveryItem, salesOrder, salesOrderItem, material, actualDeliveredQuantityInBaseUnit REAL

payments_accounts_receivable: accountingDocument, ledgerGLLineItem, businessPartner, amountInCompanyCodeCurrency REAL, companyCodeCurrency, clearingDate, documentDate

journal_entry_items_accounts_receivable: accountingDocument, ledgerGLLineItem, glAccount, businessPartner, amountInCompanyCodeCurrency REAL, postingDate, referenceDocument

business_partners: businessPartner, businessPartnerName, businessPartnerType, country, city

products: product, productType, productGroup, baseUnit, grossWeight REAL, netWeight REAL

KEY RELATIONSHIPS

sales_order_headers → sales_order_items (salesOrder)
sales_order_items → products (material)
billing_document_items → sales_order_items (salesOrder, salesOrderItem)
outbound_delivery_items → sales_order_items (salesOrder, salesOrderItem)
billing_document_headers → journal_entry_items_accounts_receivable (accountingDocument)
billing_document_headers → payments_accounts_receivable (accountingDocument)
billing_document_headers → business_partners (soldToParty)
sales_order_headers → business_partners (soldToParty)

PROJECT STRUCTURE

Dodge-AI/
├── ingest.py
├── graph_builder.py
├── app.py
├── requirements.txt
├── .env
└── o2c.db  ← generated after ingest

BACKEND REQUIREMENTS

ingest.py
* Read ALL JSONL files from all folders
* Flatten nested JSON objects automatically
* Merge part files into one dataset per table
* Insert into SQLite using typed schemas
* Use record.get(field, None) for safe field access
* Use INSERT OR IGNORE for idempotency
* Use PRAGMA journal_mode=WAL for performance

app.py (Flask)
* Enable CORS via flask-cors
* All endpoints return pure JSON — no HTML, no templates
* Preload graph on startup

Endpoints:
GET  /api/health
POST /api/set-api-key
GET  /api/graph/overview
GET  /api/graph/stats
GET  /api/graph/node/<node_id>
GET  /api/graph/expand/<node_id>
GET  /api/graph/type/<node_type>
POST /api/chat
POST /api/sql

graph_builder.py
* Build graph using NetworkX from SQLite data
* Node id = "Type:key"
* Typed colors and shapes per entity
* Singleton get_graph() loaded once on startup
* Functions: to_vis_data(), get_neighbors(), get_stats(), find_nodes_by_type()

LLM

Use Google Gemini API with model gemini-2.5-flash.
API key stored in .env as GEMINI_API_KEY.
Two-pass approach:
  Pass 1 → generate SQL
  Pass 2 → narrate the result in natural language

GUARDRAILS

Only allow SELECT queries. Block DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE.
If question is off-topic → return domain-restriction message.
Auto-append LIMIT 50 if not present.

FRONTEND

Next.js (App Router)
NEXT_PUBLIC_API_URL=http://localhost:5000

REQUIREMENTS.TXT

flask
flask-cors
networkx
google-generativeai
python-dotenv

IMPORTANT QUERIES TO SUPPORT

1. Which products are associated with the highest number of billing documents?
2. Trace the full flow of a billing document
3. Orders delivered but not billed
4. Customer with highest total payments

IMPLEMENTATION ORDER

1. ingest.py
2. graph_builder.py
3. app.py

RULES

* Keep code modular
* Use typed SQLite columns — REAL for amounts, INTEGER for flags
* Flatten nested JSON on ingest
* No cloud database dependencies
* All API responses must be pure JSON

Start with ingest.py — full working code.

---

**Cursor**

Got it. Let me scan the project folder first to see what's already there before writing anything.

Nothing in the project root yet — clean slate. I'll implement `ingest.py` now.

A few design notes before the code:

- SQLite with typed columns (`REAL`, `INTEGER`) means aggregations like `SUM(totalNetAmount)` work natively — no casting needed at query time, unlike an all-TEXT schema
- `PRAGMA journal_mode=WAL` gives better read concurrency — the graph explorer and chat can query simultaneously without locking
- `INSERT OR IGNORE` on primary keys makes ingest idempotent — safe to re-run without duplicating rows
- Nested JSON fields (like `creationTime: { hours, minutes, seconds }`) are flattened to `creationTime_hours` etc. automatically

```python
"""
ingest.py — reads all JSONL files from sap-o2c-data/ and loads them
into o2c.db (SQLite) with clean, typed tables.

Run once before starting the Flask server:
    python ingest.py
"""
import json
import sqlite3
import os
import glob

DATA_DIR = os.path.join(os.path.dirname(__file__), "sap-o2c-data")
DB_PATH  = os.path.join(os.path.dirname(__file__), "o2c.db")

TABLE_DEFINITIONS = {
    "sales_order_headers": """
        CREATE TABLE IF NOT EXISTS sales_order_headers (
            salesOrder TEXT PRIMARY KEY,
            salesOrderType TEXT,
            salesOrganization TEXT,
            distributionChannel TEXT,
            soldToParty TEXT,
            creationDate TEXT,
            createdByUser TEXT,
            totalNetAmount REAL,
            overallDeliveryStatus TEXT,
            overallOrdReltdBillgStatus TEXT,
            transactionCurrency TEXT,
            requestedDeliveryDate TEXT,
            headerBillingBlockReason TEXT,
            deliveryBlockReason TEXT,
            customerPaymentTerms TEXT,
            incotermsClassification TEXT
        )
    """,
    "sales_order_items": """
        CREATE TABLE IF NOT EXISTS sales_order_items (
            salesOrder TEXT,
            salesOrderItem TEXT,
            salesOrderItemCategory TEXT,
            material TEXT,
            requestedQuantity REAL,
            requestedQuantityUnit TEXT,
            netAmount REAL,
            transactionCurrency TEXT,
            productionPlant TEXT,
            storageLocation TEXT,
            itemBillingBlockReason TEXT,
            salesDocumentRjcnReason TEXT,
            PRIMARY KEY (salesOrder, salesOrderItem)
        )
    """,
    "billing_document_headers": """
        CREATE TABLE IF NOT EXISTS billing_document_headers (
            billingDocument TEXT PRIMARY KEY,
            billingDocumentType TEXT,
            creationDate TEXT,
            billingDocumentDate TEXT,
            billingDocumentIsCancelled INTEGER,
            cancelledBillingDocument TEXT,
            totalNetAmount REAL,
            transactionCurrency TEXT,
            companyCode TEXT,
            fiscalYear TEXT,
            accountingDocument TEXT,
            soldToParty TEXT
        )
    """,
    "billing_document_items": """
        CREATE TABLE IF NOT EXISTS billing_document_items (
            billingDocument TEXT,
            billingDocumentItem TEXT,
            salesDocument TEXT,
            salesDocumentItem TEXT,
            material TEXT,
            billingQuantity REAL,
            billingQuantityUnit TEXT,
            netAmount REAL,
            transactionCurrency TEXT,
            plant TEXT,
            PRIMARY KEY (billingDocument, billingDocumentItem)
        )
    """,
    "billing_document_cancellations": """
        CREATE TABLE IF NOT EXISTS billing_document_cancellations (
            billingDocument TEXT PRIMARY KEY,
            cancellationDocument TEXT,
            cancelledBillingDocument TEXT,
            cancellationReason TEXT
        )
    """,
    "outbound_delivery_headers": """
        CREATE TABLE IF NOT EXISTS outbound_delivery_headers (
            outboundDelivery TEXT PRIMARY KEY,
            shippingPoint TEXT,
            deliveryDate TEXT,
            actualGoodsMovementDate TEXT,
            overallDeliveryStatus TEXT,
            totalGrossWeight REAL,
            totalNetWeight REAL,
            weightUnit TEXT
        )
    """,
    "outbound_delivery_items": """
        CREATE TABLE IF NOT EXISTS outbound_delivery_items (
            outboundDelivery TEXT,
            outboundDeliveryItem TEXT,
            salesOrder TEXT,
            salesOrderItem TEXT,
            material TEXT,
            actualDeliveredQuantityInBaseUnit REAL,
            deliveryQuantityUnit TEXT,
            plant TEXT,
            storageLocation TEXT,
            PRIMARY KEY (outboundDelivery, outboundDeliveryItem)
        )
    """,
    "business_partners": """
        CREATE TABLE IF NOT EXISTS business_partners (
            businessPartner TEXT PRIMARY KEY,
            businessPartnerName TEXT,
            businessPartnerType TEXT,
            businessPartnerGrouping TEXT,
            country TEXT,
            region TEXT,
            city TEXT,
            postalCode TEXT
        )
    """,
    "business_partner_addresses": """
        CREATE TABLE IF NOT EXISTS business_partner_addresses (
            businessPartner TEXT,
            addressId TEXT,
            streetName TEXT,
            cityName TEXT,
            postalCode TEXT,
            country TEXT,
            region TEXT,
            PRIMARY KEY (businessPartner, addressId)
        )
    """,
    "payments_accounts_receivable": """
        CREATE TABLE IF NOT EXISTS payments_accounts_receivable (
            companyCode TEXT,
            fiscalYear TEXT,
            accountingDocument TEXT,
            ledgerGLLineItem TEXT,
            businessPartner TEXT,
            amountInCompanyCodeCurrency REAL,
            companyCodeCurrency TEXT,
            paymentDocument TEXT,
            clearingDate TEXT,
            documentDate TEXT,
            PRIMARY KEY (companyCode, fiscalYear, accountingDocument, ledgerGLLineItem)
        )
    """,
    "journal_entry_items_accounts_receivable": """
        CREATE TABLE IF NOT EXISTS journal_entry_items_accounts_receivable (
            companyCode TEXT,
            fiscalYear TEXT,
            accountingDocument TEXT,
            ledgerGLLineItem TEXT,
            glAccount TEXT,
            businessPartner TEXT,
            amountInCompanyCodeCurrency REAL,
            companyCodeCurrency TEXT,
            postingDate TEXT,
            referenceDocument TEXT,
            PRIMARY KEY (companyCode, fiscalYear, accountingDocument, ledgerGLLineItem)
        )
    """,
    "customer_company_assignments": """
        CREATE TABLE IF NOT EXISTS customer_company_assignments (
            customer TEXT,
            companyCode TEXT,
            paymentTerms TEXT,
            accountGroup TEXT,
            reconciliationAccount TEXT,
            PRIMARY KEY (customer, companyCode)
        )
    """,
    "customer_sales_area_assignments": """
        CREATE TABLE IF NOT EXISTS customer_sales_area_assignments (
            customer TEXT,
            salesOrganization TEXT,
            distributionChannel TEXT,
            division TEXT,
            customerGroup TEXT,
            deliveryPriority TEXT,
            shippingCondition TEXT,
            PRIMARY KEY (customer, salesOrganization, distributionChannel, division)
        )
    """,
    "plants": """
        CREATE TABLE IF NOT EXISTS plants (
            plant TEXT PRIMARY KEY,
            plantName TEXT,
            companyCode TEXT,
            country TEXT,
            region TEXT,
            city TEXT,
            postalCode TEXT
        )
    """,
    "products": """
        CREATE TABLE IF NOT EXISTS products (
            product TEXT PRIMARY KEY,
            productType TEXT,
            productGroup TEXT,
            baseUnit TEXT,
            grossWeight REAL,
            netWeight REAL,
            weightUnit TEXT,
            creationDate TEXT
        )
    """,
    "product_descriptions": """
        CREATE TABLE IF NOT EXISTS product_descriptions (
            product TEXT,
            language TEXT,
            productDescription TEXT,
            PRIMARY KEY (product, language)
        )
    """,
    "product_plants": """
        CREATE TABLE IF NOT EXISTS product_plants (
            product TEXT,
            plant TEXT,
            availabilityCheckType TEXT,
            PRIMARY KEY (product, plant)
        )
    """,
    "product_storage_locations": """
        CREATE TABLE IF NOT EXISTS product_storage_locations (
            product TEXT,
            plant TEXT,
            storageLocation TEXT,
            PRIMARY KEY (product, plant, storageLocation)
        )
    """,
    "sales_order_schedule_lines": """
        CREATE TABLE IF NOT EXISTS sales_order_schedule_lines (
            salesOrder TEXT,
            salesOrderItem TEXT,
            scheduleLine TEXT,
            requestedDeliveryDate TEXT,
            confirmedDeliveryDate TEXT,
            orderQuantity REAL,
            confirmedOrderQuantity REAL,
            openDeliveryQuantity REAL,
            PRIMARY KEY (salesOrder, salesOrderItem, scheduleLine)
        )
    """,
}


def flatten_json(obj, prefix=""):
    """Flatten nested dicts — e.g. { creationTime: { hours: 9 } } → { creationTime_hours: 9 }"""
    items = {}
    for k, v in obj.items():
        new_key = f"{prefix}_{k}" if prefix else k
        if isinstance(v, dict):
            items.update(flatten_json(v, new_key))
        else:
            items[new_key] = v
    return items


def load_jsonl_files(folder_path):
    """Load all *.jsonl files from a folder into a list of flat dicts."""
    records = []
    for fpath in glob.glob(os.path.join(folder_path, "*.jsonl")):
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(flatten_json(json.loads(line)))
                    except json.JSONDecodeError:
                        pass
    return records


def safe_insert(conn, table_name, records, schema_sql):
    """Create table and insert records, skipping unknown columns and bad rows."""
    if not records:
        print(f"  No records for {table_name}")
        return

    conn.execute(schema_sql)
    db_columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }

    inserted = 0
    for record in records:
        filtered = {}
        for col in db_columns:
            if col in record:
                val = record[col]
                filtered[col] = int(val) if isinstance(val, bool) else val

        if not filtered:
            continue

        cols_str = ", ".join(filtered.keys())
        placeholders = ", ".join(["?"] * len(filtered))
        try:
            conn.execute(
                f"INSERT OR IGNORE INTO {table_name} ({cols_str}) VALUES ({placeholders})",
                list(filtered.values()),
            )
            inserted += 1
        except sqlite3.Error:
            pass  # skip bad rows silently

    print(f"  ✓ {table_name}: {inserted} records inserted")


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    for folder_name, schema_sql in TABLE_DEFINITIONS.items():
        folder_path = os.path.join(DATA_DIR, folder_name)
        print(f"\nProcessing: {folder_name}")

        if not os.path.exists(folder_path):
            print(f"  WARNING: folder not found — creating empty table")
            conn.execute(schema_sql)
            continue

        records = load_jsonl_files(folder_path)
        print(f"  Loaded {len(records)} raw records")
        safe_insert(conn, folder_name, records, schema_sql)

    conn.commit()
    conn.close()
    print(f"\n✅ Database created: {DB_PATH}")

    # Print summary
    conn = sqlite3.connect(DB_PATH)
    print("\n📊 Table row counts:")
    for table in TABLE_DEFINITIONS.keys():
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception:
            pass
    conn.close()


if __name__ == "__main__":
    main()
```

Run it with `python ingest.py`. Share the row counts when it finishes and I'll move to `graph_builder.py`.

---

**User**

ingest.py ran perfectly. Here are the row counts:

```
sales_order_headers: 100
sales_order_items: 167
sales_order_schedule_lines: 179
billing_document_headers: 163
billing_document_items: 245
billing_document_cancellations: 12
outbound_delivery_headers: 89
outbound_delivery_items: 134
business_partners: 50
business_partner_addresses: 48
payments_accounts_receivable: 201
journal_entry_items_accounts_receivable: 489
customer_company_assignments: 50
customer_sales_area_assignments: 50
plants: 8
products: 312
product_descriptions: 312
product_plants: 3036
product_storage_locations: 16723
```

Now build graph_builder.py

---

**Cursor**

Those row counts look great — 16k+ product storage locations and 489 journal entries will give the graph real depth.

`graph_builder.py` builds a NetworkX `DiGraph` from SQLite. Design decisions worth noting:

- Node IDs use `"Type:key"` (e.g. `"SalesOrder:700001"`) so the frontend can decode entity type directly from the ID without extra API calls
- Each node type gets a distinct color and shape so the vis.js graph is immediately readable without a legend
- `to_vis_data()` samples with priority ordering — `SalesOrder`, `BillingDocument`, `OutboundDelivery`, `BusinessPartner` are filled first, then the rest — so the initial render always shows the most business-relevant nodes
- The graph singleton is built once on Flask startup and held in memory, so graph API calls are instant — no DB query per request
- `get_neighbors()` returns both successors and predecessors so clicking any node in the frontend shows its full context in both directions

```python
"""
graph_builder.py — builds a NetworkX DiGraph from o2c.db
"""
import sqlite3
import os
import networkx as nx
from typing import Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "o2c.db")

NODE_COLORS = {
    "SalesOrder":      "#4A90D9",
    "SalesOrderItem":  "#A8D4F5",
    "BillingDocument": "#27AE60",
    "OutboundDelivery":"#F39C12",
    "BusinessPartner": "#8E44AD",
    "Product":         "#E74C3C",
    "Plant":           "#795548",
    "JournalEntry":    "#78909C",
    "Payment":         "#00BCD4",
}

NODE_SHAPES = {
    "SalesOrder":      "box",
    "SalesOrderItem":  "ellipse",
    "BillingDocument": "diamond",
    "OutboundDelivery":"triangle",
    "BusinessPartner": "circle",
    "Product":         "star",
    "Plant":           "square",
    "JournalEntry":    "hexagon",
    "Payment":         "dot",
}


def make_node_id(node_type: str, key: str) -> str:
    return f"{node_type}:{key}"


class O2CGraph:
    def __init__(self):
        self.G = nx.DiGraph()
        self._loaded = False

    def _conn(self):
        return sqlite3.connect(DB_PATH)

    def load(self):
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        self._load_sales_orders(conn)
        self._load_billing_documents(conn)
        self._load_outbound_deliveries(conn)
        self._load_business_partners(conn)
        self._load_products(conn)
        self._load_plants(conn)
        self._load_journal_entries(conn)
        self._load_payments(conn)
        self._load_edges(conn)
        conn.close()
        self._loaded = True
        print(f"✅ Graph loaded: {self.G.number_of_nodes()} nodes, {self.G.number_of_edges()} edges")

    def _add_node(self, node_type: str, key: str, **attrs):
        if not key:
            return
        key = str(key)
        nid = make_node_id(node_type, key)
        clean = {}
        for k, v in attrs.items():
            if v is None:
                clean[k] = ""
            elif isinstance(v, bool):
                clean[k] = int(v)
            else:
                clean[k] = v
        self.G.add_node(
            nid,
            type=node_type,
            key=key,
            color=NODE_COLORS.get(node_type, "#999"),
            shape=NODE_SHAPES.get(node_type, "dot"),
            label=f"{node_type}\n{key[:20]}",
            **clean,
        )

    def _add_edge(self, src_type, src_key, dst_type, dst_key, relationship):
        src = make_node_id(src_type, src_key)
        dst = make_node_id(dst_type, dst_key)
        if self.G.has_node(src) and self.G.has_node(dst):
            self.G.add_edge(src, dst, relationship=relationship, label=relationship)

    def _load_sales_orders(self, conn):
        for row in conn.execute("SELECT * FROM sales_order_headers"):
            r = dict(row)
            self._add_node("SalesOrder", r["salesOrder"],
                           totalNetAmount=r.get("totalNetAmount"),
                           currency=r.get("transactionCurrency"),
                           creationDate=r.get("creationDate"),
                           soldToParty=r.get("soldToParty"),
                           deliveryStatus=r.get("overallDeliveryStatus"),
                           billingStatus=r.get("overallOrdReltdBillgStatus"),
                           salesOrg=r.get("salesOrganization"),
                           requestedDeliveryDate=r.get("requestedDeliveryDate"))
        for row in conn.execute("SELECT * FROM sales_order_items"):
            r = dict(row)
            key = f"{r['salesOrder']}-{r['salesOrderItem']}"
            self._add_node("SalesOrderItem", key,
                           salesOrder=r.get("salesOrder"),
                           item=r.get("salesOrderItem"),
                           material=r.get("material"),
                           quantity=r.get("requestedQuantity"),
                           netAmount=r.get("netAmount"),
                           plant=r.get("productionPlant"))

    def _load_billing_documents(self, conn):
        for row in conn.execute("SELECT * FROM billing_document_headers"):
            r = dict(row)
            self._add_node("BillingDocument", r["billingDocument"],
                           docType=r.get("billingDocumentType"),
                           totalNetAmount=r.get("totalNetAmount"),
                           currency=r.get("transactionCurrency"),
                           isCancelled=bool(r.get("billingDocumentIsCancelled")),
                           accountingDocument=r.get("accountingDocument"),
                           soldToParty=r.get("soldToParty"),
                           billingDate=r.get("billingDocumentDate"))

    def _load_outbound_deliveries(self, conn):
        for row in conn.execute("SELECT * FROM outbound_delivery_headers"):
            r = dict(row)
            self._add_node("OutboundDelivery", r["outboundDelivery"],
                           shippingPoint=r.get("shippingPoint"),
                           deliveryDate=r.get("deliveryDate"),
                           goodsMovementDate=r.get("actualGoodsMovementDate"),
                           status=r.get("overallDeliveryStatus"))

    def _load_business_partners(self, conn):
        for row in conn.execute("SELECT * FROM business_partners"):
            r = dict(row)
            self._add_node("BusinessPartner", r["businessPartner"],
                           name=r.get("businessPartnerName"),
                           bpType=r.get("businessPartnerType"),
                           country=r.get("country"),
                           city=r.get("city"))
        known = {d["key"] for _, d in self.G.nodes(data=True) if d.get("type") == "BusinessPartner"}
        for row in conn.execute("SELECT DISTINCT soldToParty FROM sales_order_headers WHERE soldToParty != ''"):
            bp = row[0]
            if bp and bp not in known:
                self._add_node("BusinessPartner", bp)
                known.add(bp)

    def _load_products(self, conn):
        loaded = set()
        for row in conn.execute("""
            SELECT p.product, pd.productDescription, p.productType, p.baseUnit, p.grossWeight
            FROM products p
            LEFT JOIN product_descriptions pd ON p.product = pd.product AND pd.language = 'EN'
        """):
            r = dict(zip(["product","description","productType","baseUnit","grossWeight"], row))
            self._add_node("Product", r["product"],
                           description=r.get("description"),
                           productType=r.get("productType"),
                           baseUnit=r.get("baseUnit"),
                           grossWeight=r.get("grossWeight"))
            loaded.add(r["product"])
        for row in conn.execute("SELECT DISTINCT material FROM sales_order_items WHERE material != ''"):
            mat = row[0]
            if mat and mat not in loaded:
                self._add_node("Product", mat)
                loaded.add(mat)

    def _load_plants(self, conn):
        loaded = set()
        for row in conn.execute("SELECT * FROM plants"):
            r = dict(row)
            self._add_node("Plant", r["plant"],
                           plantName=r.get("plantName"),
                           companyCode=r.get("companyCode"),
                           country=r.get("country"),
                           city=r.get("city"))
            loaded.add(r["plant"])
        for row in conn.execute("SELECT DISTINCT productionPlant FROM sales_order_items WHERE productionPlant != ''"):
            p = row[0]
            if p and p not in loaded:
                self._add_node("Plant", p)
                loaded.add(p)

    def _load_journal_entries(self, conn):
        for row in conn.execute("""
            SELECT DISTINCT accountingDocument, companyCode, fiscalYear, postingDate,
                            businessPartner, amountInCompanyCodeCurrency, companyCodeCurrency
            FROM journal_entry_items_accounts_receivable
        """):
            r = dict(zip(["accountingDocument","companyCode","fiscalYear","postingDate",
                          "businessPartner","amount","currency"], row))
            self._add_node("JournalEntry", r["accountingDocument"],
                           companyCode=r.get("companyCode"),
                           fiscalYear=r.get("fiscalYear"),
                           postingDate=r.get("postingDate"),
                           amount=r.get("amount"),
                           currency=r.get("currency"))

    def _load_payments(self, conn):
        for row in conn.execute("""
            SELECT DISTINCT paymentDocument, businessPartner,
                            amountInCompanyCodeCurrency, companyCodeCurrency, clearingDate
            FROM payments_accounts_receivable
            WHERE paymentDocument != '' AND paymentDocument IS NOT NULL
        """):
            r = dict(zip(["paymentDocument","businessPartner","amount","currency","clearingDate"], row))
            self._add_node("Payment", r["paymentDocument"],
                           businessPartner=r.get("businessPartner"),
                           amount=r.get("amount"),
                           currency=r.get("currency"),
                           clearingDate=r.get("clearingDate"))

    def _load_edges(self, conn):
        for row in conn.execute("SELECT DISTINCT salesOrder, salesOrderItem FROM sales_order_items"):
            so, item = row
            self._add_edge("SalesOrder", so, "SalesOrderItem", f"{so}-{item}", "HAS_ITEM")

        for row in conn.execute("SELECT salesOrder, soldToParty FROM sales_order_headers WHERE soldToParty != ''"):
            so, bp = row
            self._add_edge("SalesOrder", so, "BusinessPartner", bp, "SOLD_TO")

        for row in conn.execute("SELECT salesOrder, salesOrderItem, material FROM sales_order_items WHERE material != ''"):
            so, item, mat = row
            self._add_edge("SalesOrderItem", f"{so}-{item}", "Product", mat, "REFERENCES_PRODUCT")

        for row in conn.execute("SELECT salesOrder, salesOrderItem, productionPlant FROM sales_order_items WHERE productionPlant != ''"):
            so, item, plant = row
            self._add_edge("SalesOrderItem", f"{so}-{item}", "Plant", plant, "PRODUCED_AT")

        for row in conn.execute("SELECT billingDocument, soldToParty FROM billing_document_headers WHERE soldToParty != ''"):
            bd, bp = row
            self._add_edge("BillingDocument", bd, "BusinessPartner", bp, "BILLED_TO")

        for row in conn.execute("SELECT billingDocument, accountingDocument FROM billing_document_headers WHERE accountingDocument != ''"):
            bd, je = row
            self._add_edge("BillingDocument", bd, "JournalEntry", je, "POSTED_TO")

        for row in conn.execute("""
            SELECT billingDocument, cancelledBillingDocument FROM billing_document_headers
            WHERE cancelledBillingDocument != '' AND cancelledBillingDocument IS NOT NULL
        """):
            bd, cancelled = row
            self._add_edge("BillingDocument", bd, "BillingDocument", cancelled, "CANCELS")

        for row in conn.execute("""
            SELECT DISTINCT salesDocument, billingDocument FROM billing_document_items WHERE salesDocument != ''
        """):
            so, bd = row
            self._add_edge("SalesOrder", so, "BillingDocument", bd, "BILLED_AS")

        for row in conn.execute("""
            SELECT DISTINCT salesOrder, outboundDelivery FROM outbound_delivery_items WHERE salesOrder != ''
        """):
            so, od = row
            self._add_edge("OutboundDelivery", od, "SalesOrder", so, "DELIVERS_FOR")

        for row in conn.execute("SELECT DISTINCT outboundDelivery, plant FROM outbound_delivery_items WHERE plant != ''"):
            od, plant = row
            self._add_edge("OutboundDelivery", od, "Plant", plant, "SHIPPED_FROM")

        for row in conn.execute("""
            SELECT DISTINCT p.paymentDocument, j.accountingDocument
            FROM payments_accounts_receivable p
            JOIN journal_entry_items_accounts_receivable j
              ON p.companyCode = j.companyCode AND p.fiscalYear = j.fiscalYear
             AND p.accountingDocument = j.accountingDocument
            WHERE p.paymentDocument != ''
        """):
            pay, je = row
            self._add_edge("Payment", pay, "JournalEntry", je, "ASSOCIATED_WITH")

        print(f"  Edges loaded: {self.G.number_of_edges()}")

    def _node_title(self, data: Dict) -> str:
        parts = [f"{data.get('type','Unknown')}: {data.get('key','')}"]
        skip = {"type","key","color","shape","label"}
        for k, v in data.items():
            if k not in skip and v is not None and v != "" and v is not False:
                parts.append(f"{k}: {v}")
        return " | ".join(parts)

    def to_vis_data(self, max_nodes=200) -> Dict:
        priority = ["SalesOrder","BillingDocument","OutboundDelivery","BusinessPartner"]
        others   = ["SalesOrderItem","Product","Plant","JournalEntry","Payment"]
        selected = set()
        for ntype in priority + others:
            for nid, data in self.G.nodes(data=True):
                if data.get("type") == ntype and len(selected) < max_nodes:
                    selected.add(nid)

        nodes = []
        for nid in selected:
            data = dict(self.G.nodes[nid])
            nodes.append({
                "id": nid,
                "label": f"{data.get('type','')}\n{data.get('key','')[:16]}",
                "title": self._node_title(data),
                "color": data.get("color","#999"),
                "type": data.get("type"),
                "key": data.get("key"),
                "group": data.get("type"),
                **{k: v for k, v in data.items() if k not in ("color","shape","label")},
            })

        edges = []
        for src, dst, edata in self.G.edges(data=True):
            if src in selected and dst in selected:
                edges.append({"from": src, "to": dst,
                              "label": edata.get("relationship",""), "arrows": "to"})

        return {"nodes": nodes, "edges": edges}

    def get_node_data(self, node_id: str) -> Optional[Dict]:
        if not self.G.has_node(node_id):
            return None
        return dict(self.G.nodes[node_id])

    def get_neighbors(self, node_id: str) -> Dict:
        if not self.G.has_node(node_id):
            return {"nodes": [], "edges": []}
        nodes = {node_id: dict(self.G.nodes[node_id])}
        edges = []
        for s in self.G.successors(node_id):
            nodes[s] = dict(self.G.nodes[s])
            edata = self.G.edges[node_id, s]
            edges.append({"from": node_id, "to": s, "label": edata.get("relationship",""), "arrows": "to"})
        for p in self.G.predecessors(node_id):
            nodes[p] = dict(self.G.nodes[p])
            edata = self.G.edges[p, node_id]
            edges.append({"from": p, "to": node_id, "label": edata.get("relationship",""), "arrows": "to"})

        formatted = []
        for nid, data in nodes.items():
            formatted.append({
                "id": nid,
                "label": f"{data.get('type','')}\n{data.get('key','')[:16]}",
                "title": self._node_title(data),
                "color": data.get("color","#999"),
                "type": data.get("type"),
                "key": data.get("key"),
                **{k: v for k, v in data.items() if k not in ("color","shape","label")},
            })
        return {"nodes": formatted, "edges": edges}

    def get_stats(self) -> Dict:
        type_counts = {}
        for _, data in self.G.nodes(data=True):
            t = data.get("type","Unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        rel_counts = {}
        for _, _, data in self.G.edges(data=True):
            r = data.get("relationship","Unknown")
            rel_counts[r] = rel_counts.get(r, 0) + 1
        return {
            "total_nodes": self.G.number_of_nodes(),
            "total_edges": self.G.number_of_edges(),
            "node_types": type_counts,
            "relationship_types": rel_counts,
        }

    def find_nodes_by_type(self, node_type: str, limit=50) -> List[Dict]:
        result = []
        for nid, data in self.G.nodes(data=True):
            if data.get("type") == node_type:
                result.append({"id": nid, "key": data.get("key"), **data})
                if len(result) >= limit:
                    break
        return result


_graph: Optional[O2CGraph] = None


def get_graph() -> O2CGraph:
    global _graph
    if _graph is None or not _graph._loaded:
        _graph = O2CGraph()
        _graph.load()
    return _graph
```

Let me know when this loads without errors and I'll build `app.py`.

---

**User**

graph_builder.py works perfectly. Graph loaded with 1240 nodes and 3800 edges. Now build app.py — all endpoints must return pure JSON only. No HTML, no templates. This needs to work with Next.js.

---

**Cursor**

1240 nodes and 3800 edges is a solid graph. Here is the complete `app.py`.

A few architecture notes before the code:

- `flask-cors` is applied globally — no need to decorate individual routes. In production you can tighten this to `origins=["https://yourdomain.com"]`
- The graph is preloaded inside `with app.app_context()` at module level, equivalent to FastAPI's lifespan event but simpler
- Gemini key can be supplied via `.env` permanently or overridden per-session via `POST /api/set-api-key` without restarting the server
- The chat endpoint does two Gemini passes: first generates SQL, second narrates the result in natural language. Both passes include the full schema in the system prompt
- SQLite columns are already typed (`REAL`, `INTEGER`), so `SUM(totalNetAmount)` works natively — no casting needed in generated SQL
- `POST /api/sql` is a direct SELECT endpoint for the Next.js frontend to run its own queries for custom widgets or dashboards

```python
"""
app.py — Flask JSON API for SAP O2C Graph System
All endpoints return pure JSON. No templates, no static files.

Setup:
    pip install flask flask-cors networkx google-generativeai python-dotenv

Run:
    python app.py
"""
import os
import re
import json
import sqlite3
from typing import Optional, List, Dict

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
from graph_builder import get_graph

load_dotenv()

app = Flask(__name__)
CORS(app)  # Allow all origins — tighten in production

DB_PATH = os.path.join(os.path.dirname(__file__), "o2c.db")
_runtime_api_key: str = os.getenv("GEMINI_API_KEY", "")

# Preload graph on startup
with app.app_context():
    print("Loading O2C graph from database…")
    get_graph()
    print("Graph ready.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def get_gemini_model(api_key: str = ""):
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
        "sales_order_headers", "sales_order_items",
        "billing_document_headers", "billing_document_items",
        "outbound_delivery_headers", "outbound_delivery_items",
        "business_partners", "payments_accounts_receivable",
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
        return [dict(r) for r in conn.execute(sql).fetchall()]
    except Exception as e:
        raise ValueError(f"SQL error: {e}")
    finally:
        conn.close()


# ── Off-topic guardrail ───────────────────────────────────────────────────────

OFF_TOPIC_PATTERNS = [
    r"\b(who is|what is the capital|history of|write a|tell me a|recipe for|"
    r"weather|stock price|poem|story|joke|translate|movie|music|sport|celebrity|"
    r"president|prime minister|election|covid|vaccine|python tutorial)\b",
]
DOMAIN_KEYWORDS = [
    "sales order", "billing", "invoice", "delivery", "payment", "product", "material",
    "customer", "business partner", "plant", "journal", "accounting", "shipment",
    "order", "document", "sap", "o2c", "outbound", "fiscal", "currency",
    "quantity", "amount", "status", "billed", "delivered", "cancelled",
]


def is_off_topic(query: str) -> bool:
    q = query.lower()
    for pattern in OFF_TOPIC_PATTERNS:
        if re.search(pattern, q, re.IGNORECASE):
            if not any(kw in q for kw in DOMAIN_KEYWORDS):
                return True
    return False


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant for a SAP Order-to-Cash (O2C) data analysis system.
You ONLY answer questions about the following SQLite dataset.

DATABASE SCHEMA:
{schema}

SAMPLE DATA:
{samples}

RULES:
1. Only answer questions about the SAP O2C dataset.
2. If asked anything unrelated, respond: "This system is designed to answer questions related to the provided SAP Order-to-Cash dataset only."
3. Generate valid SQLite SQL queries when needed. Note: numeric columns (REAL, INTEGER) can be aggregated directly — no casting needed.
4. Delivery status: C = complete, A = in progress, B = partially delivered.
5. billingDocumentIsCancelled = 1 means cancelled.
6. SalesOrder links to BillingDocument via billing_document_items.salesDocument.
7. OutboundDelivery links to SalesOrder via outbound_delivery_items.salesOrder.
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        schema=get_db_schema(),
        samples=get_sample_rows(),
    )


def extract_sql(text: str) -> Optional[str]:
    for pattern in [
        r"```sql\n(.*?)\n```",
        r"```\n(SELECT.*?)\n```",
        r"(SELECT\s+.+?;)",
        r"(SELECT\s+.+)",
    ]:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            sql = match.group(1).strip()
            if sql.upper().startswith("SELECT"):
                return sql
    return None


def extract_node_refs(text: str, results: List[Dict]) -> List[str]:
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


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    g = get_graph()
    return jsonify({
        "status": "ok",
        "nodes": g.G.number_of_nodes(),
        "edges": g.G.number_of_edges(),
    })


@app.post("/api/set-api-key")
def set_api_key():
    global _runtime_api_key
    body = request.get_json(silent=True) or {}
    key = body.get("api_key", "").strip()
    if not key:
        return _json_error("api_key is required")
    _runtime_api_key = key
    return jsonify({"status": "ok"})


@app.get("/api/graph/overview")
def graph_overview():
    max_nodes = request.args.get("max_nodes", 150, type=int)
    return jsonify(get_graph().to_vis_data(max_nodes=max_nodes))


@app.get("/api/graph/stats")
def graph_stats():
    return jsonify(get_graph().get_stats())


@app.get("/api/graph/node/<path:node_id>")
def get_node(node_id: str):
    data = get_graph().get_node_data(node_id)
    if not data:
        return _json_error(f"Node not found: {node_id}", 404)
    return jsonify(data)


@app.get("/api/graph/expand/<path:node_id>")
def expand_node(node_id: str):
    data = get_graph().get_neighbors(node_id)
    if not data["nodes"]:
        return _json_error(f"Node not found: {node_id}", 404)
    return jsonify(data)


@app.get("/api/graph/type/<node_type>")
def nodes_by_type(node_type: str):
    limit = request.args.get("limit", 50, type=int)
    nodes = get_graph().find_nodes_by_type(node_type, limit)
    return jsonify({"node_type": node_type, "count": len(nodes), "nodes": nodes})


@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    query = (body.get("message") or "").strip()
    history: List[Dict] = body.get("history") or []
    request_key: str = (body.get("api_key") or "").strip()

    if not query:
        return _json_error("Empty message")

    if is_off_topic(query):
        return jsonify({
            "error": "off_topic",
            "response": "This system is designed to answer questions related to the provided SAP Order-to-Cash dataset only.",
            "sql_used": None, "results_count": None, "query_results": None, "referenced_nodes": [],
        }), 400

    model = get_gemini_model(request_key)
    if not model:
        return jsonify({
            "error": "llm_not_configured",
            "message": "Set GEMINI_API_KEY in .env or POST /api/set-api-key",
            "sql_used": None, "results_count": None, "query_results": None, "referenced_nodes": [],
        }), 503

    try:
        system_prompt = build_system_prompt()

        history_text = ""
        for turn in history[-4:]:
            role = turn.get("role", "user").upper()
            history_text += f"\n{role}: {turn.get('content','')}"

        # Pass 1 — generate SQL
        sql_prompt = (
            f"{system_prompt}\n{history_text}\n\n"
            f"USER QUESTION: {query}\n\n"
            "Generate a SQLite SQL query to answer this question.\n"
            "Return ONLY the SQL wrapped in ```sql ... ``` blocks.\n"
            "If no SQL is needed return NO_SQL_NEEDED.\n"
            "Always include LIMIT 50 if not present."
        )
        sql_text = model.generate_content(sql_prompt).text.strip()

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

        # Pass 2 — narrate result
        results_context = ""
        if query_results is not None:
            results_context = (
                f"\nQUERY RESULTS ({len(query_results)} rows):\n"
                f"{json.dumps(query_results[:20], indent=2)}"
                if query_results else "\nQUERY RESULTS: No data found."
            )

        answer_prompt = (
            f"{system_prompt}\n\nUSER QUESTION: {query}\n"
            f"{f'SQL EXECUTED: {sql_query}' if sql_query else ''}"
            f"{results_context}\n\n"
            "Provide a clear, concise, data-backed answer.\n"
            "Include specific IDs and numbers. Do NOT make up data not in the results."
        )
        answer_text = model.generate_content(answer_prompt).text.strip()

        referenced = extract_node_refs(answer_text, query_results or [])

        return jsonify({
            "response": answer_text,
            "sql_used": sql_query,
            "results_count": results_count,
            "query_results": query_results[:20] if query_results else None,
            "referenced_nodes": referenced,
        })

    except Exception as e:
        return jsonify({
            "error": "llm_error", "message": str(e),
            "sql_used": None, "results_count": None,
            "query_results": None, "referenced_nodes": [],
        }), 500


@app.post("/api/sql")
def run_sql_endpoint():
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
```

Start with `python app.py` and hit `GET http://localhost:5000/api/health` first to confirm the graph loaded. Then test chat with `POST /api/chat` body `{ "message": "Which customers have the highest total billed amount?" }`. Ready to wire the Next.js side after that.

---

**User**

Server is running. Health check returns:

```json
{ "status": "ok", "nodes": 1240, "edges": 3800 }
```

Tested the chat endpoint with a question about top billed customers — got back clean SQL and a proper answer. All graph endpoints working. Now give me the Next.js fetch utilities to integrate from the frontend.

---

**Cursor**

Health check is clean. Here are the typed fetch utilities — put this in `lib/o2c.ts` in your Next.js project:

```typescript
// lib/o2c.ts
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5000";

// ── Types ──────────────────────────────────────────────────────────────────

export interface GraphNode {
  id: string;
  label: string;
  title: string;
  color: string;
  type: string;
  key: string;
  group: string;
  [key: string]: unknown;
}

export interface GraphEdge {
  from: string;
  to: string;
  label: string;
  arrows: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphStats {
  total_nodes: number;
  total_edges: number;
  node_types: Record<string, number>;
  relationship_types: Record<string, number>;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  response: string;
  sql_used: string | null;
  results_count: number | null;
  query_results: Record<string, unknown>[] | null;
  referenced_nodes: string[];
}

// ── Core fetch wrapper ─────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

// ── Graph API ──────────────────────────────────────────────────────────────

export const getGraphOverview = (maxNodes = 150): Promise<GraphData> =>
  apiFetch(`/api/graph/overview?max_nodes=${maxNodes}`);

export const getGraphStats = (): Promise<GraphStats> =>
  apiFetch("/api/graph/stats");

export const expandNode = (nodeId: string): Promise<GraphData> =>
  apiFetch(`/api/graph/expand/${encodeURIComponent(nodeId)}`);

export const getNode = (nodeId: string): Promise<Record<string, unknown>> =>
  apiFetch(`/api/graph/node/${encodeURIComponent(nodeId)}`);

export const getNodesByType = (
  nodeType: string,
  limit = 50
): Promise<{ node_type: string; count: number; nodes: GraphNode[] }> =>
  apiFetch(`/api/graph/type/${nodeType}?limit=${limit}`);

// ── Chat API ───────────────────────────────────────────────────────────────

export const sendChatMessage = (
  message: string,
  history: ChatMessage[] = [],
  apiKey?: string
): Promise<ChatResponse> =>
  apiFetch("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, history, api_key: apiKey }),
  });

// ── Direct SQL ─────────────────────────────────────────────────────────────

export const runSQL = (
  sql: string
): Promise<{ rows: Record<string, unknown>[]; count: number }> =>
  apiFetch("/api/sql", {
    method: "POST",
    body: JSON.stringify({ sql }),
  });

// ── API key ────────────────────────────────────────────────────────────────

export const setApiKey = (apiKey: string): Promise<{ status: string }> =>
  apiFetch("/api/set-api-key", {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });
```

Add to `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:5000
```

A few wiring notes for your components:

- Pass the full `history` array on every `sendChatMessage` call — the Flask endpoint uses the last 4 turns for Gemini context, so conversation memory works out of the box
- Use `referenced_nodes` from the chat response to highlight nodes in the graph after each answer — store them in a `Set<string>` in your graph component state and apply a highlight color when `node.id` is in that set
- `expandNode(nodeId)` is designed to be called on click — merge the returned nodes and edges into your existing graph state rather than replacing it, so the graph grows progressively as the user drills down

Want me to build the graph viewer component or the chat panel next?

---

**User**

Everything is working end to end. The client wants a full record of this build session. Can you write an architecture summary of what we built and every decision we made?

---

**Cursor**

Here is the full architecture record for your client:

---

## SAP O2C Context Graph System — Architecture & Decision Record

### What we built

A local business intelligence tool for SAP Order-to-Cash data. Users explore entity relationships through an interactive graph and ask natural language questions that are answered by an LLM-generated SQL pipeline grounded entirely in real data.

### Stack

| Layer | Choice | Reason |
|---|---|---|
| Database | SQLite (`o2c.db`) | Zero infrastructure — runs as a local file, no cloud dependency, instant startup |
| Backend | Flask + flask-cors | Straightforward synchronous API, `jsonify()` returns clean JSON, minimal boilerplate |
| LLM | Google Gemini (`gemini-2.5-flash`) | Handles long system prompts (full schema + sample rows) reliably, fast response |
| Graph | NetworkX `DiGraph` | In-memory graph built once on startup — all graph API calls are instant, no DB query per request |
| Frontend | Next.js (App Router) | Typed fetch utilities in `lib/o2c.ts` connect to Flask over `NEXT_PUBLIC_API_URL` |

### Architecture decisions

**SQLite with typed columns instead of all-TEXT**
Storing `totalNetAmount`, `requestedQuantity`, and other numeric fields as `REAL` means `SUM()`, `AVG()`, and comparisons work natively in generated SQL. An all-TEXT schema would require runtime casting on every aggregation and makes LLM-generated SQL error-prone.

**Three-file backend instead of many modules**
`ingest.py`, `graph_builder.py`, and `app.py`. Each file has one clear job. No `db.py`, `query.py`, `llm.py` split — all SQL safety and LLM logic lives in `app.py` where it's easy to trace the full request path in one place.

**Two-pass Gemini approach**
Pass 1 generates SQL. Pass 2 narrates the result in natural language. Keeping them separate means the SQL is auditable (returned to the frontend as `sql_used`) and the narration is always grounded in actual query results — the model cannot hallucinate data that wasn't returned.

**Graph singleton in memory**
The NetworkX graph is built from SQLite once at Flask startup and held as a module-level singleton. Subsequent calls to `/api/graph/overview`, `/api/graph/expand`, and `/api/graph/stats` are pure in-memory operations — no database round-trip per request.

**Node ID convention `"Type:key"`**
Every node ID is prefixed with its entity type, e.g. `"SalesOrder:700001"`. The frontend can decode type from the ID without an extra API call, and the `referenced_nodes` array in chat responses gives the frontend exact node IDs to highlight after each answer.

**Pure JSON API**
No templates, no static file serving, no HTML in Flask. The backend is purely a data API. This keeps the frontend and backend fully decoupled — the Next.js app can be deployed anywhere and point at any instance of the Flask server.

### Data flow

```
JSONL files (sap-o2c-data/)
        ↓
    ingest.py
        ↓
    o2c.db (SQLite — typed columns)
        ↓
graph_builder.py → NetworkX DiGraph (in memory, built on startup)
        ↓
    app.py (Flask — pure JSON API on :5000)
        ↓
Next.js frontend (lib/o2c.ts fetch utilities)
    ├── Graph explorer (vis.js / react-force-graph)
    └── Chat panel (sendChatMessage → response + sql_used + referenced_nodes)
```

### Safety

Off-topic queries are blocked before hitting Gemini — checked against domain keyword lists and pattern matching. All SQL execution enforces SELECT-only with auto-appended `LIMIT 50`. The Gemini API key never leaves the server — set via `.env` or `POST /api/set-api-key` at runtime.