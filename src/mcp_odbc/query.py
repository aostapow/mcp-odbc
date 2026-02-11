"""Query execution, read-only enforcement, result formatting."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from fastmcp.exceptions import ToolError

from mcp_odbc.formatting import format_as_json, format_as_markdown

if TYPE_CHECKING:
    import pyodbc

WRITE_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "CREATE",
    "ALTER",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "MERGE",
    "EXEC",
    "EXECUTE",
    "CALL",
}

_LINE_COMMENT_RE = re.compile(r"--[^\r\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_WRITE_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(WRITE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments."""
    sql = _BLOCK_COMMENT_RE.sub("", sql)
    sql = _LINE_COMMENT_RE.sub("", sql)
    return sql.strip()


def validate_readonly(sql: str, supports_cte: bool = True) -> None:
    """Validate that SQL is a read-only SELECT (or WITH for CTEs).

    Raises ToolError if the statement appears to be a write operation.
    """
    cleaned = strip_sql_comments(sql)
    if not cleaned:
        raise ToolError("Empty query.")

    first_word = cleaned.split()[0].upper()
    allowed = {"SELECT"}
    if supports_cte:
        allowed.add("WITH")

    if first_word not in allowed:
        raise ToolError(
            f"Only SELECT queries are allowed (got '{first_word}'). "
            "This connection is read-only."
        )

    # Scan for write keywords anywhere in the statement
    match = _WRITE_KEYWORD_RE.search(cleaned)
    if match:
        keyword = match.group(1).upper()
        # Allow SELECT ... INTO detection but not standalone INSERT etc.
        # WITH ... SELECT is fine; WITH ... INSERT is not
        if keyword not in allowed:
            raise ToolError(
                f"Write operation '{keyword}' is not allowed. "
                "This connection is read-only."
            )


def run_query(
    connection: pyodbc.Connection,
    sql: str,
    max_rows: int = 100,
    readonly: bool = True,
    format: str = "markdown",
) -> str:
    """Execute a SQL query and return formatted results.

    Args:
        connection: Active pyodbc connection.
        sql: SQL query string.
        max_rows: Maximum rows to return.
        readonly: Whether to enforce read-only validation.
        format: Output format — "markdown" or "json".

    Returns:
        Formatted result string.
    """
    if readonly:
        validate_readonly(sql)

    from mcp_odbc.errors import handle_odbc_error

    try:
        cursor = connection.cursor()
        cursor.execute(sql)

        if not cursor.description:
            return "*Query executed successfully (no results returned).*"

        columns = [desc[0] for desc in cursor.description]

        # Fetch max_rows + 1 to detect if more rows exist
        rows = cursor.fetchmany(max_rows + 1)
        has_more = len(rows) > max_rows
        if has_more:
            rows = rows[:max_rows]

        cursor.close()
    except Exception as exc:
        import pyodbc as _pyodbc

        if isinstance(exc, _pyodbc.Error):
            raise handle_odbc_error(exc) from exc
        raise

    if format == "json":
        return format_as_json(columns, rows, has_more)
    return format_as_markdown(columns, rows, has_more)
