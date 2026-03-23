import json
import os
from typing import Dict, List, Set

from db import get_connection


CORE_SCHEMAS: Dict[str, List[str]] = {
    "sales_order_headers": [
        "salesOrder",
        "salesOrderType",
        "soldToParty",
        "creationDate",
        "totalNetAmount",
        "overallDeliveryStatus",
        "transactionCurrency",
    ],
    "sales_order_items": [
        "salesOrder",
        "salesOrderItem",
        "material",
        "requestedQuantity",
        "netAmount",
        "productionPlant",
        "storageLocation",
    ],
    "billing_document_headers": [
        "billingDocument",
        "billingDocumentType",
        "creationDate",
        "totalNetAmount",
        "soldToParty",
        "accountingDocument",
        "fiscalYear",
        "companyCode",
        "billingDocumentIsCancelled",
    ],
    "billing_document_items": [
        "billingDocument",
        "billingDocumentItem",
        "salesOrder",
        "salesOrderItem",
        "material",
        "billingQuantity",
        "netAmount",
    ],
    "outbound_delivery_headers": [
        "deliveryDocument",
        "creationDate",
        "shippingPoint",
        "overallGoodsMovementStatus",
        "overallPickingStatus",
    ],
    "outbound_delivery_items": [
        "deliveryDocument",
        "deliveryDocumentItem",
        "salesOrder",
        "salesOrderItem",
        "material",
        "actualDeliveryQuantity",
    ],
    "payments_accounts_receivable": [
        "accountingDocument",
        "accountingDocumentItem",
        "customer",
        "amountInTransactionCurrency",
        "transactionCurrency",
        "postingDate",
        "clearingDate",
        "clearingAccountingDocument",
    ],
    "journal_entry_items_accounts_receivable": [
        "accountingDocument",
        "accountingDocumentItem",
        "referenceDocument",
        "glAccount",
        "amountInTransactionCurrency",
        "transactionCurrency",
        "postingDate",
        "customer",
        "accountingDocumentType",
    ],
    "business_partners": [
        "businessPartner",
        "businessPartnerFullName",
        "businessPartnerType",
    ],
    "products": [
        "material",
        "baseUnit",
        "materialType",
        "materialGroup",
    ],
}

NUMERIC_SHADOW_COLUMNS: Dict[str, List[str]] = {
    "sales_order_headers": ["totalNetAmount"],
    "sales_order_items": ["requestedQuantity", "netAmount"],
    "billing_document_headers": ["totalNetAmount"],
    "billing_document_items": ["billingQuantity", "netAmount"],
    "outbound_delivery_items": ["actualDeliveryQuantity"],
    "payments_accounts_receivable": ["amountInTransactionCurrency"],
    "journal_entry_items_accounts_receivable": ["amountInTransactionCurrency"],
}


def _safe_union_keys_from_jsonl_file(jsonl_path: str, limit: int = -1) -> Set[str]:
    """
    Stream JSONL and union all keys found.

    limit=-1 means "no explicit limit".
    """
    keys: Set[str] = set()
    lines_read = 0
    with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            if limit >= 0 and lines_read >= limit:
                break

            lines_read += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if isinstance(obj, dict):
                keys.update(obj.keys())

    return keys


def infer_columns_for_table(table_folder: str) -> Set[str]:
    """
    Infer columns by scanning all *.jsonl files inside the entity folder.
    """
    inferred: Set[str] = set()

    # Typical pattern: multiple "part-*.jsonl" files.
    for name in os.listdir(table_folder):
        if not name.lower().endswith(".jsonl"):
            continue
        if name.startswith("."):
            continue

        jsonl_path = os.path.join(table_folder, name)
        if os.path.isfile(jsonl_path):
            inferred |= _safe_union_keys_from_jsonl_file(jsonl_path, limit=-1)

    return inferred


def create_tables(data_root: str = None) -> None:
    """
    Create ALL tables from entity folders under `sap-o2c-data/`.

    - Source columns are TEXT.
    - Known numeric fields also get shadow NUMERIC columns named `<field>_num`.
    - If core schema is known, those columns are always included.
    - Other columns are inferred from JSONL keys in the dataset.
    """
    if data_root is None:
        data_root = os.path.join(os.path.dirname(__file__), "sap-o2c-data")

    if not os.path.isdir(data_root):
        raise RuntimeError(f"Dataset root not found: {data_root}")

    table_names = [
        name
        for name in os.listdir(data_root)
        if os.path.isdir(os.path.join(data_root, name))
    ]

    conn = get_connection()
    cur = conn.cursor()
    try:
        for table_name in table_names:
            folder = os.path.join(data_root, table_name)

            inferred_cols = infer_columns_for_table(folder)
            core_cols = set(CORE_SCHEMAS.get(table_name, []))
            cols = sorted(core_cols | inferred_cols)

            # If a folder exists but contains no parsable JSON lines yet,
            # create a minimal table so later loads can fail loudly.
            if not cols:
                cols = [f"{table_name}_row_data"]

            cols_sql = ", ".join([f"\"{col}\" TEXT" for col in cols])
            ddl = f"CREATE TABLE IF NOT EXISTS \"{table_name}\" ({cols_sql});"
            cur.execute(ddl)

            # Add/ensure numeric shadow columns for faster and cleaner aggregations.
            for base_col in NUMERIC_SHADOW_COLUMNS.get(table_name, []):
                shadow_col = f"{base_col}_num"
                cur.execute(
                    f'ALTER TABLE "{table_name}" '
                    f'ADD COLUMN IF NOT EXISTS "{shadow_col}" NUMERIC;'
                )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    create_tables()

