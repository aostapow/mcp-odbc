"""Query execution, read-only enforcement, result formatting, audit logging."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from fastmcp.exceptions import ToolError

from mcp_odbc.audit import AuditContext
from mcp_odbc.formatting import format_as_json, format_as_markdown

if TYPE_CHECKING:
    import pyodbc

WRITE_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "MERGE", "EXEC", "EXECUTE", "CALL",
}

_LINE_COMMENT_RE = re.compile(r"--[^\r\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_WRITE_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(WRITE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
# SP name: letters, digits, underscore, at-sign, hash — no spaces
_SP_NAME_RE = re.compile(r"^[\w@#]+$")


def strip_sql_comments(sql: str) -> str:
    sql = _BLOCK_COMMENT_RE.sub("", sql)
    sql = _LINE_COMMENT_RE.sub("", sql)
    return sql.strip()


def validate_readonly(sql: str, supports_cte: bool = True) -> None:
    """Raise ToolError if the SQL is not a read-only SELECT/WITH."""
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

    match = _WRITE_KEYWORD_RE.search(cleaned)
    if match:
        keyword = match.group(1).upper()
        if keyword not in allowed:
            raise ToolError(
                f"Write operation '{keyword}' is not allowed. "
                "This connection is read-only."
            )


def validate_sp_allowed(
    sp_name: str,
    allow_sp: bool,
    sp_whitelist: list[str],
) -> None:
    """Validate that a stored procedure call is permitted for this connection.

    Raises ToolError if:
    - allow_sp is False
    - sp_name contains characters outside [\\w@#] (injection guard)
    - sp_whitelist is non-empty and sp_name is not in it
    """
    if not allow_sp:
        raise ToolError(
            "Stored procedure execution is disabled for this connection. "
            "Set allow_sp = true in config.ini to enable it."
        )

    if not _SP_NAME_RE.match(sp_name):
        raise ToolError(
            f"Invalid stored procedure name '{sp_name}'. "
            "Only alphanumeric characters, underscores, @ and # are allowed."
        )

    if sp_whitelist and sp_name not in sp_whitelist:
        raise ToolError(
            f"Stored procedure '{sp_name}' is not in the whitelist for this connection. "
            f"Allowed: {', '.join(sp_whitelist)}"
        )


def run_query(
    connection: pyodbc.Connection,
    sql: str,
    max_rows: int = 100,
    readonly: bool = True,
    format: str = "markdown",
    connection_name: str = "default",
) -> str:
    """Execute a SQL query and return formatted results.

    Args:
        connection:      Active pyodbc connection.
        sql:             SQL query string.
        max_rows:        Maximum rows to return.
        readonly:        Whether to enforce read-only validation.
        format:          Output format — "markdown" or "json".
        connection_name: Logical name for the audit log.
    """
    if readonly:
        validate_readonly(sql)

    from mcp_odbc.errors import handle_odbc_error

    with AuditContext(connection=connection_name, sql=sql) as ctx:
        try:
            cursor = connection.cursor()
            cursor.execute(sql)

            if not cursor.description:
                ctx.record(rows=0)
                return "*Query executed successfully (no results returned).*"

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchmany(max_rows + 1)
            has_more = len(rows) > max_rows
            if has_more:
                rows = rows[:max_rows]

            cursor.close()
            ctx.record(rows=len(rows), truncated=has_more)

        except Exception as exc:
            import pyodbc as _pyodbc
            if isinstance(exc, _pyodbc.Error):
                raise handle_odbc_error(exc) from exc
            raise

    if format == "json":
        return format_as_json(columns, rows, has_more)
    return format_as_markdown(columns, rows, has_more)


def run_stored_procedure(
    connection: pyodbc.Connection,
    sp_name: str,
    params: list,
    max_rows: int = 100,
    allow_sp: bool = False,
    sp_whitelist: list[str] | None = None,
    format: str = "markdown",
    connection_name: str = "default",
) -> str:
    """Execute a whitelisted stored procedure and return formatted results.

    Args:
        connection:      Active pyodbc connection.
        sp_name:         Name of the stored procedure.
        params:          Positional parameters to pass.
        max_rows:        Maximum rows to return.
        allow_sp:        Must be True or ToolError is raised.
        sp_whitelist:    If non-empty, sp_name must be in this list.
        format:          Output format — "markdown" or "json".
        connection_name: Logical name for the audit log.
    """
    validate_sp_allowed(sp_name, allow_sp, sp_whitelist or [])

    from mcp_odbc.errors import handle_odbc_error

    # Build the EXEC call — sp_name already validated as safe by validate_sp_allowed
    placeholders = ",".join("?" * len(params))
    sql_repr = f"EXEC {sp_name}({placeholders})" if params else f"EXEC {sp_name}"

    with AuditContext(connection=connection_name, sql=sql_repr) as ctx:
        try:
            cursor = connection.cursor()
            if params:
                cursor.execute(f"{{CALL {sp_name}({placeholders})}}", params)
            else:
                cursor.execute(f"{{CALL {sp_name}}}")

            if not cursor.description:
                ctx.record(rows=0)
                return "*Stored procedure executed successfully (no result set returned).*"

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchmany(max_rows + 1)
            has_more = len(rows) > max_rows
            if has_more:
                rows = rows[:max_rows]

            cursor.close()
            ctx.record(rows=len(rows), truncated=has_more)

        except Exception as exc:
            import pyodbc as _pyodbc
            if isinstance(exc, _pyodbc.Error):
                raise handle_odbc_error(exc) from exc
            raise

    if format == "json":
        return format_as_json(columns, rows, has_more)
    return format_as_markdown(columns, rows, has_more)
