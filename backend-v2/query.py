import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from db import get_connection


_FORBIDDEN_KEYWORDS = [
    # DDL
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bTRUNCATE\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bCOMMENT\b",
    # DML
    r"\bDELETE\b",
    r"\bUPDATE\b",
    r"\bINSERT\b",
    r"\bMERGE\b",
    # Write-ish SELECT features
    r"\bFOR\s+UPDATE\b",
    r"\bRETURNING\b",
    # Functions that can mutate (best-effort block)
    r"\bCOPY\s+",
    r"\bEXECUTE\b",
    r"\bDO\b",
]

_ALLOWED_START = re.compile(r"^(select|with)\b", re.IGNORECASE)


def _is_safe_sql(sql: str) -> bool:
    sql_clean = sql.strip().strip(";").strip()
    if not sql_clean:
        return False

    # Disallow multi-statement SQL to reduce risk.
    # (PostgreSQL allows semicolons to chain statements.)
    if ";" in sql_clean:
        return False

    # Must start with SELECT or WITH.
    if not _ALLOWED_START.match(sql_clean):
        return False

    # Block forbidden keywords anywhere.
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(kw, sql_clean, flags=re.IGNORECASE):
            return False

    return True


def is_safe_sql(sql: str) -> bool:
    """
    Public wrapper for SQL safety checks.

    Used to validate LLM-generated SQL before execution.
    """
    return _is_safe_sql(sql)


def execute_query(
    sql: str,
    params: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Execute a read-only SQL query against Postgres and return rows as dictionaries.

    Safety rules:
    - Only allow queries that start with `SELECT` or `WITH`
    - Block DML/DDL keywords like INSERT/UPDATE/DELETE/DROP, etc.
    - Disallow semicolons to prevent multi-statement execution
    """
    if not _is_safe_sql(sql):
        raise ValueError("Unsafe SQL blocked. Only read-only SELECT queries are allowed.")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
            cols = [desc[0] for desc in cur.description] if cur.description else []

        results: List[Dict[str, Any]] = []
        for row in rows:
            results.append({cols[i]: row[i] for i in range(len(cols))})
        return results
    finally:
        conn.close()

