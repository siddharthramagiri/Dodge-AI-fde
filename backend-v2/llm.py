import json
import os
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from groq import Groq

import query as query_module
from query import execute_query


load_dotenv()

GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")

# MODEL = "llama3-70b-8192"
MODEL = "llama-3.1-8b-instant"


_TRIPLE_BACKTICK_RE = re.compile(r"^```(?:sql)?\s*([\s\S]*?)\s*```$", re.IGNORECASE)


def _extract_sql_from_response(text: str) -> str:
    """
    Enforce "SQL only" contract by stripping common markdown wrappers.
    """
    if text is None:
        return ""

    t = text.strip()

    # Remove ```sql ... ``` wrappers if the model returns them anyway.
    m = _TRIPLE_BACKTICK_RE.match(t)
    if m:
        t = m.group(1).strip()

    # Remove stray backticks.
    t = t.replace("`", "").strip()

    # Remove trailing semicolons (we block semicolons anyway).
    if t.endswith(";"):
        t = t[:-1].strip()

    return t


def generate_sql(question: str) -> str:
    """
    Use Groq LLM to generate SQL for the given natural language question.

    Contract:
    - Return ONLY SQL (no markdown, no explanation)
    - If unrelated, return OFFTOPIC
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set in .env")

    client = Groq(api_key=GROQ_API_KEY)

    schema_and_relationships = """
TABLES

Base/source columns are TEXT. Numeric shadow columns are NUMERIC and suffixed with `_num`.

IMPORTANT IDENTIFIER RULE (PostgreSQL):
- All table names and columns in this database are case-sensitive (camelCase columns).
- You MUST double-quote ALL table names and ALL column names exactly as shown below.
- Example: "journal_entry_items_accounts_receivable"."accountingDocument"

"sales_order_headers"("salesOrder", "salesOrderType", "soldToParty", "creationDate", "totalNetAmount", "overallDeliveryStatus", "transactionCurrency")
"sales_order_items"("salesOrder", "salesOrderItem", "material", "requestedQuantity", "netAmount", "productionPlant", "storageLocation")
"billing_document_headers"("billingDocument", "billingDocumentType", "creationDate", "totalNetAmount", "soldToParty", "accountingDocument", "fiscalYear", "companyCode", "billingDocumentIsCancelled")
"billing_document_items"("billingDocument", "billingDocumentItem", "salesOrder", "salesOrderItem", "material", "billingQuantity", "netAmount")
"outbound_delivery_headers"("deliveryDocument", "creationDate", "shippingPoint", "overallGoodsMovementStatus", "overallPickingStatus")
"outbound_delivery_items"("deliveryDocument", "deliveryDocumentItem", "salesOrder", "salesOrderItem", "material", "actualDeliveryQuantity")
"payments_accounts_receivable"("accountingDocument", "accountingDocumentItem", "customer", "amountInTransactionCurrency", "transactionCurrency", "postingDate", "clearingDate", "clearingAccountingDocument")
"journal_entry_items_accounts_receivable"("accountingDocument", "accountingDocumentItem", "referenceDocument", "glAccount", "amountInTransactionCurrency", "transactionCurrency", "postingDate", "customer", "accountingDocumentType")
"business_partners"("businessPartner", "businessPartnerFullName", "businessPartnerType")
"products"("material", "baseUnit", "materialType", "materialGroup")

NUMERIC SHADOW COLUMNS (use these for math)
"sales_order_headers"."totalNetAmount_num"
"sales_order_items"."requestedQuantity_num", "sales_order_items"."netAmount_num"
"billing_document_headers"."totalNetAmount_num"
"billing_document_items"."billingQuantity_num", "billing_document_items"."netAmount_num"
"outbound_delivery_items"."actualDeliveryQuantity_num"
"payments_accounts_receivable"."amountInTransactionCurrency_num"
"journal_entry_items_accounts_receivable"."amountInTransactionCurrency_num"

KEY RELATIONSHIPS
"sales_order_headers" -> "sales_order_items" on "salesOrder"
"sales_order_items" -> "products" on "material"
"billing_document_items" -> "sales_order_items" on ("salesOrder", "salesOrderItem")
"outbound_delivery_items" -> "sales_order_items" on ("salesOrder", "salesOrderItem")
"billing_document_headers" -> "journal_entry_items_accounts_receivable" on "accountingDocument"
"billing_document_headers" -> "payments_accounts_receivable" on "accountingDocument"
"billing_document_headers" -> "business_partners" on "soldToParty"
"sales_order_headers" -> "business_partners" on "soldToParty"

IMPORTANT COLUMN NOTES
- "highest" should be interpreted as "ORDER BY ... DESC LIMIT 1" (or LIMIT 10 if the question asks for top N).
- For SUM/AVG/MIN/MAX on numeric business fields, ALWAYS use *_num columns.
- Prefer *_num over runtime casting for cleaner SQL and better performance.

IDENTIFIER INTERPRETATION RULES
- If the question mentions a "billing document" number, it refers to: "billing_document_headers"."billingDocument".
- If the question mentions an "accounting document" number, it refers to: "journal_entry_items_accounts_receivable"."accountingDocument"
  and "payments_accounts_receivable"."accountingDocument".
- When linking billing documents to journal entry items, filter the billing document via
  "billing_document_headers"."billingDocument" and join to journal entries via "accountingDocument".
"""

    examples = """
EXAMPLES (output SQL only; do NOT include markdown)

1) Question: Which products are associated with the highest number of billing documents?
SQL:
SELECT
  bdi."material",
  p."materialGroup",
  COUNT(DISTINCT bdi."billingDocument") AS billingDocumentCount
FROM "billing_document_items" bdi
LEFT JOIN "products" p
  ON p."material" = bdi."material"
GROUP BY bdi."material", p."materialGroup"
ORDER BY billingDocumentCount DESC
LIMIT 1

2) Question: Customer with highest total payments
SQL:
SELECT
  par."customer",
  bp."businessPartnerFullName",
  SUM(COALESCE(par."amountInTransactionCurrency_num", 0)) AS totalPayments
FROM "payments_accounts_receivable" par
LEFT JOIN "business_partners" bp
  ON bp."businessPartner" = par."customer"
GROUP BY par."customer", bp."businessPartnerFullName"
ORDER BY totalPayments DESC
LIMIT 1

3) Question: Orders delivered but not billed
SQL:
SELECT DISTINCT
  soh."salesOrder",
  soh."soldToParty",
  bp."businessPartnerFullName",
  soh."creationDate" AS salesOrderCreationDate
FROM "sales_order_headers" soh
JOIN "outbound_delivery_items" odi
  ON odi."salesOrder" = soh."salesOrder"
JOIN "outbound_delivery_headers" odh
  ON odh."deliveryDocument" = odi."deliveryDocument"
LEFT JOIN "billing_document_items" bdi
  ON bdi."salesOrder" = soh."salesOrder"
  AND bdi."salesOrderItem" = odi."salesOrderItem"
LEFT JOIN "business_partners" bp
  ON bp."businessPartner" = soh."soldToParty"
WHERE bdi."billingDocument" IS NULL
ORDER BY soh."creationDate" DESC
LIMIT 50

4) Question: Trace the full flow of a billing document
SQL:
WITH target AS (
  SELECT
    "billingDocument",
    "soldToParty",
    "accountingDocument",
    "fiscalYear",
    "companyCode",
    "billingDocumentType",
    "creationDate"
  FROM "billing_document_headers"
  ORDER BY "creationDate" DESC
  LIMIT 1
),
bi AS (
  SELECT *
  FROM "billing_document_items"
  WHERE "billingDocument" IN (SELECT "billingDocument" FROM target)
),
soi AS (
  SELECT *
  FROM "sales_order_items"
  WHERE ("salesOrder", "salesOrderItem") IN (
    SELECT "salesOrder", "salesOrderItem" FROM bi
  )
),
soh AS (
  SELECT *
  FROM "sales_order_headers"
  WHERE "salesOrder" IN (SELECT "salesOrder" FROM soi)
),
del AS (
  SELECT *
  FROM "outbound_delivery_items"
  WHERE ("salesOrder", "salesOrderItem") IN (
    SELECT "salesOrder", "salesOrderItem" FROM soi
  )
)
SELECT
  t."billingDocument",
  t."billingDocumentType",
  t."creationDate" AS billingCreationDate,
  t."soldToParty",
  bp."businessPartnerFullName",
  t."accountingDocument",
  t."fiscalYear",
  t."companyCode",
  bi."billingDocumentItem",
  bi."salesOrder",
  bi."salesOrderItem",
  bi."material" AS billingMaterial,
  soi."requestedQuantity",
  soi."netAmount" AS salesOrderItemNetAmount,
  del."deliveryDocument",
  del."deliveryDocumentItem",
  del."actualDeliveryQuantity",
  bp2."businessPartnerType" AS soldToPartyType
FROM target t
LEFT JOIN "business_partners" bp
  ON bp."businessPartner" = t."soldToParty"
LEFT JOIN bi
  ON 1 = 1
LEFT JOIN soi
  ON soi."salesOrder" = bi."salesOrder"
  AND soi."salesOrderItem" = bi."salesOrderItem"
LEFT JOIN del
  ON del."salesOrder" = bi."salesOrder"
  AND del."salesOrderItem" = bi."salesOrderItem"
LEFT JOIN "business_partners" bp2
  ON bp2."businessPartner" = t."soldToParty"
ORDER BY t."creationDate" DESC
LIMIT 200

5) Question: Find the journal entry linked with billing document 91150187
SQL:
SELECT
  bdh."billingDocument",
  bdh."billingDocumentType",
  bdh."creationDate" AS "billingCreationDate",
  bdh."accountingDocument",
  jie."accountingDocumentItem",
  jie."referenceDocument",
  jie."glAccount",
  jie."amountInTransactionCurrency",
  jie."transactionCurrency",
  jie."postingDate",
  jie."customer",
  jie."accountingDocumentType"
FROM "billing_document_headers" bdh
JOIN "journal_entry_items_accounts_receivable" jie
  ON jie."accountingDocument" = bdh."accountingDocument"
WHERE bdh."billingDocument" = '91150187'
LIMIT 200
"""

    system_prompt = f"""
You are a SQL generator for the SAP Order-to-Cash dataset stored in PostgreSQL (Neon).
{schema_and_relationships}

RULES
- Return OFFTOPIC if the question is unrelated to this dataset.
- Return ONLY the SQL text. No markdown fences, no code blocks, no explanations.
- Do not include trailing semicolons.
- Prefer correct joins using the provided relationships.
- CRITICAL: Double-quote ALL table names and ALL column names exactly as in the schema.
- Use table aliases if you want, but still quote column names: alias."accountingDocument"
- For calculations, ALWAYS use *_num columns when available.
"""

    user_prompt = f"""
User question:
{question}

Your task:
Generate a single SQL query that answers the user question using the schema above.
If the question asks for "the highest", use ORDER BY ... DESC LIMIT 1.
"""

    completion = client.chat.completions.create(
        model=MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
    )

    content = completion.choices[0].message.content or ""
    sql = _extract_sql_from_response(content)

    # Enforce the OFFTOPIC contract.
    if sql.strip().upper().startswith("OFFTOPIC"):
        return "OFFTOPIC"

    return sql


def _format_answer_with_llm(question: str, sql: str, result: List[Dict[str, Any]]) -> str:
    """
    Turn query result into a grounded natural language answer.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set in .env")

    client = Groq(api_key=GROQ_API_KEY)

    result_json = json.dumps(result, ensure_ascii=False)

    system_prompt = """
You are an assistant that answers ONLY using the provided SQL result.
Be concise, factual, and grounded in the result.
"""
    user_prompt = f"""
Question:
{question}

SQL that was executed:
{sql}

SQL result (JSON array of objects):
{result_json}

Write a natural language answer. If result is empty, say no relevant records were found.
"""

    completion = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
    )

    content = completion.choices[0].message.content or ""
    return content.strip()


def answer_question(question: str) -> Dict[str, Any]:
    """
    End-to-end: NL question -> LLM SQL -> safety-validated execution -> natural language answer.
    """
    sql = generate_sql(question)

    if sql.strip().upper() == "OFFTOPIC":
        return {
            "sql": "",
            "result": [],
            "answer": "This system is designed to answer questions related to the provided dataset only.",
        }

    # Enforce safety BEFORE execution.
    sql_sanitized = _extract_sql_from_response(sql)

    # Post-process common identifier mixups from the LLM:
    # "billing document <id>" should filter billing_document_headers.billingDocument (not accountingDocument).
    if re.search(r"\bbilling document\b", question, flags=re.IGNORECASE):
        # Case 1: fully-qualified reference in WHERE.
        sql_sanitized = re.sub(
            r'WHERE\s+"billing_document_headers"\."accountingDocument"\s*=',
            'WHERE "billing_document_headers"."billingDocument" =',
            sql_sanitized,
            flags=re.IGNORECASE,
        )

        # Case 2: alias reference like WHERE bdh."accountingDocument" = ...
        m = re.search(
            r'FROM\s+"billing_document_headers"\s+([A-Za-z_][A-Za-z0-9_]*)',
            sql_sanitized,
            flags=re.IGNORECASE,
        )
        if m:
            alias = m.group(1)
            sql_sanitized = re.sub(
                rf'WHERE\s+{re.escape(alias)}\."accountingDocument"\s*=',
                rf'WHERE {alias}."billingDocument" =',
                sql_sanitized,
                flags=re.IGNORECASE,
            )

    if not query_module.is_safe_sql(sql_sanitized):
        return {
            "sql": sql_sanitized,
            "result": [],
            "answer": "Unsafe or unsupported SQL generated; only read-only SELECT queries are allowed.",
        }

    result = execute_query(sql_sanitized)
    answer = _format_answer_with_llm(question, sql_sanitized, result)

    return {
        "sql": sql_sanitized,
        "result": result,
        "answer": answer,
    }

