import json
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from psycopg2.extras import execute_values

from db import get_connection


def _to_numeric_or_none(value: Any) -> Optional[Decimal]:
    """
    Convert value to Decimal when possible, otherwise return None.
    """
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return None

    text = str(value).strip()
    if not text:
        return None

    # Remove thousands separators if present (e.g., "1,234.56").
    text = text.replace(",", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _normalize_value(value: Any) -> Any:
    """
    Normalize values for TEXT columns.

    - None stays None (will become SQL NULL)
    - dict/list are stored as JSON strings
    - everything else becomes str
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _get_table_columns(conn, table_name: str) -> List[str]:
    """
    Read column names from Postgres so we insert in the correct order.
    """
    sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
    """
    with conn.cursor() as cur:
        cur.execute(sql, (table_name,))
        cols = [r[0] for r in cur.fetchall()]
    return cols


def _iter_jsonl_objects(jsonl_path: str) -> Iterable[Dict[str, Any]]:
    with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def _insert_rows(
    conn,
    table_name: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> None:
    if not rows:
        return

    # Quote identifiers defensively; everything is TEXT so only values vary.
    cols_sql = ", ".join([f"\"{c}\"" for c in columns])
    template = "(" + ", ".join(["%s"] * len(columns)) + ")"
    insert_sql = f'INSERT INTO "{table_name}" ({cols_sql}) VALUES %s'

    with conn.cursor() as cur:
        try:
            execute_values(cur, insert_sql, rows, template=template)
        except Exception:
            # Fallback: insert row-by-row so one bad record doesn't kill the batch.
            for row in rows:
                try:
                    execute_values(cur, insert_sql, [row], template=template)
                except Exception:
                    # Skip bad record as required.
                    continue


def load_data(
    data_root: Optional[str] = None,
    batch_size: int = 1000,
    truncate_before_load: bool = True,
) -> None:
    """
    Read ALL JSONL files from all entity folders under `sap-o2c-data/`
    and insert into corresponding PostgreSQL tables.

    When truncate_before_load=True, all target tables are truncated first
    so reloads stay clean and idempotent.
    """
    if data_root is None:
        data_root = os.path.join(os.path.dirname(__file__), "sap-o2c-data")

    if not os.path.isdir(data_root):
        raise RuntimeError(f"Dataset root not found: {data_root}")

    entity_folders = [
        name
        for name in os.listdir(data_root)
        if os.path.isdir(os.path.join(data_root, name))
    ]

    conn = get_connection()
    try:
        if truncate_before_load and entity_folders:
            table_list_sql = ", ".join([f'"{name}"' for name in sorted(entity_folders)])
            with conn.cursor() as cur:
                cur.execute(
                    f"TRUNCATE TABLE {table_list_sql} RESTART IDENTITY CASCADE"
                )

        for table_name in entity_folders:
            table_folder = os.path.join(data_root, table_name)
            columns = _get_table_columns(conn, table_name)
            if not columns:
                continue

            # Accumulate rows for batch insert.
            buffer: List[Tuple[Any, ...]] = []
            inserted = 0

            jsonl_files = [
                name
                for name in os.listdir(table_folder)
                if name.lower().endswith(".jsonl") and not name.startswith(".")
            ]

            for jsonl_file in sorted(jsonl_files):
                jsonl_path = os.path.join(table_folder, jsonl_file)
                for record in _iter_jsonl_objects(jsonl_path):
                    # Build row by column order; for *_num shadow columns,
                    # derive value from the corresponding text field.
                    row_values: List[Any] = []
                    for col in columns:
                        if col.endswith("_num"):
                            base_col = col[: -len("_num")]
                            row_values.append(_to_numeric_or_none(record.get(base_col, None)))
                        else:
                            row_values.append(_normalize_value(record.get(col, None)))
                    row = tuple(row_values)
                    buffer.append(row)
                    if len(buffer) >= batch_size:
                        _insert_rows(conn, table_name, columns, buffer)
                        inserted += len(buffer)
                        buffer.clear()

            # Flush remainder.
            if buffer:
                _insert_rows(conn, table_name, columns, buffer)
                inserted += len(buffer)
                buffer.clear()

            # Minimal visibility; caller can add more logging later.
            print(f"Loaded {inserted} rows into {table_name}")
    finally:
        conn.close()


if __name__ == "__main__":
    # Default keeps reloads idempotent. Pass --append to preserve existing rows.
    import sys

    append_mode = "--append" in sys.argv
    load_data(truncate_before_load=not append_mode)

