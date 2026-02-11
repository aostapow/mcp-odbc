"""FastMCP server — tool registration + entry point."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

import pyodbc
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_odbc import metadata
from mcp_odbc.config import load_config
from mcp_odbc.connection import ConnectionManager
from mcp_odbc.errors import handle_odbc_error
from mcp_odbc.formatting import format_as_markdown
from mcp_odbc.query import run_query

_conn_manager: ConnectionManager | None = None


def _get_manager() -> ConnectionManager:
    """Return the ConnectionManager, raising if not initialized."""
    if _conn_manager is None:
        raise ToolError("Server not initialized. No connections configured.")
    return _conn_manager


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server: FastMCP):
    global _conn_manager
    config = load_config()
    _conn_manager = ConnectionManager(config)
    print("mcp-odbc: server started", file=sys.stderr)
    try:
        yield
    finally:
        if _conn_manager:
            _conn_manager.close_all()
            _conn_manager = None
        print("mcp-odbc: server stopped", file=sys.stderr)


mcp = FastMCP("mcp-odbc", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Tools — all sync (FastMCP auto-threads into threadpool)
# ---------------------------------------------------------------------------


@mcp.tool()
def list_dsns() -> str:
    """List all ODBC data sources (DSNs) configured on this system.

    Use this to discover available data sources before connecting.
    Returns a markdown table of DSN names and their drivers.
    """
    sources = pyodbc.dataSources()
    if not sources:
        return "*No ODBC data sources found.*"

    columns = ["DSN", "Driver"]
    rows = [(name, driver) for name, driver in sorted(sources.items())]
    return format_as_markdown(columns, rows)


@mcp.tool()
def list_connections() -> str:
    """List all configured connections and their status.

    Shows which connections are active, their DBMS type, and read-only status.
    Use this to see what connections are available.
    """
    manager = _get_manager()
    conns = manager.list_connections()
    if not conns:
        return "*No connections configured.*"

    columns = ["Name", "Connected", "Read-Only", "DBMS", "Adapter"]
    rows = [
        (c["name"], str(c["connected"]), str(c["readonly"]), c["dbms"], c["adapter"])
        for c in conns
    ]
    return format_as_markdown(columns, rows)


@mcp.tool()
def test_connection(connection: str | None = None) -> str:
    """Test an ODBC connection and report DBMS type and version.

    Use this to verify a connection is working before running queries.
    Connects (or reconnects) and reports driver information.

    Args:
        connection: Connection name. Uses default if not specified.
    """
    manager = _get_manager()
    try:
        manager.get(connection)
    except ToolError:
        raise
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    info = manager.get_dbms_info(connection)
    lines = [
        "**Connection successful**\n",
        "| Property | Value |",
        "| --- | --- |",
    ]
    for key, value in info.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


@mcp.tool()
def list_tables(
    connection: str | None = None,
    schema: str | None = None,
    table_type: str | None = None,
) -> str:
    """List tables and views in the database.

    Use this to discover what tables are available before querying.

    Args:
        connection: Connection name. Uses default if not specified.
        schema: Filter by schema/owner name.
        table_type: Filter by type — e.g. "TABLE", "VIEW", "SYSTEM TABLE".
    """
    manager = _get_manager()
    try:
        tables = metadata.get_tables(
            manager, connection=connection, schema=schema, table_type=table_type
        )
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    if not tables:
        return "*No tables found.*"

    columns = list(tables[0].keys())
    rows = [tuple(t.get(c, "") for c in columns) for t in tables]
    return format_as_markdown(columns, rows)


@mcp.tool()
def describe_table(
    table: str,
    connection: str | None = None,
    schema: str | None = None,
) -> str:
    """Describe a table's columns, primary keys, and foreign keys.

    Use this to understand a table's structure before writing queries.
    Returns column names, types, sizes, nullability, plus PK and FK info.

    Args:
        table: Table name to describe.
        connection: Connection name. Uses default if not specified.
        schema: Schema/owner of the table.
    """
    manager = _get_manager()

    try:
        cols = metadata.get_columns(manager, table=table, connection=connection, schema=schema)
        pks = metadata.get_primary_keys(manager, table=table, connection=connection, schema=schema)
        fks = metadata.get_foreign_keys(manager, table=table, connection=connection, schema=schema)
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    parts: list[str] = []

    # Columns
    if cols:
        parts.append(f"### Columns — {table}\n")
        col_headers = list(cols[0].keys())
        col_rows = [tuple(c.get(h, "") for h in col_headers) for c in cols]
        parts.append(format_as_markdown(col_headers, col_rows))
    else:
        parts.append(f"*No columns found for table '{table}'.*")

    # Primary keys
    if pks:
        parts.append(f"\n### Primary Keys\n")
        pk_headers = list(pks[0].keys())
        pk_rows = [tuple(p.get(h, "") for h in pk_headers) for p in pks]
        parts.append(format_as_markdown(pk_headers, pk_rows))

    # Foreign keys
    if fks:
        parts.append(f"\n### Foreign Keys\n")
        fk_headers = list(fks[0].keys())
        fk_rows = [tuple(f.get(h, "") for h in fk_headers) for f in fks]
        parts.append(format_as_markdown(fk_headers, fk_rows))

    return "\n".join(parts)


@mcp.tool()
def execute_query(
    query: str,
    connection: str | None = None,
    max_rows: int = 100,
    format: str = "markdown",
) -> str:
    """Execute a read-only SQL query and return results.

    Use this to run SELECT queries against the database. Only SELECT
    (and WITH for CTEs) are allowed — write operations are blocked.

    Args:
        query: SQL SELECT query to execute.
        connection: Connection name. Uses default if not specified.
        max_rows: Maximum rows to return (default 100, max 10000).
        format: Output format — "markdown" (default) or "json".
    """
    manager = _get_manager()
    conn_config = manager.config.connections.get(
        manager._resolve_name(connection)
    )

    # Clamp max_rows
    config_max = conn_config.max_rows if conn_config else manager.config.max_rows
    max_rows = min(max_rows, config_max)

    readonly = conn_config.readonly if conn_config else True

    cnxn = manager.get(connection)
    return run_query(cnxn, query, max_rows=max_rows, readonly=readonly, format=format)


@mcp.tool()
def get_primary_keys(
    table: str,
    connection: str | None = None,
    schema: str | None = None,
) -> str:
    """Get primary key columns for a table.

    Args:
        table: Table name.
        connection: Connection name. Uses default if not specified.
        schema: Schema/owner of the table.
    """
    manager = _get_manager()
    try:
        pks = metadata.get_primary_keys(
            manager, table=table, connection=connection, schema=schema
        )
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    if not pks:
        return f"*No primary keys found for table '{table}'.*"

    columns = list(pks[0].keys())
    rows = [tuple(p.get(c, "") for c in columns) for p in pks]
    return format_as_markdown(columns, rows)


@mcp.tool()
def get_foreign_keys(
    table: str,
    connection: str | None = None,
    schema: str | None = None,
) -> str:
    """Get foreign key relationships for a table.

    Args:
        table: Table name.
        connection: Connection name. Uses default if not specified.
        schema: Schema/owner of the table.
    """
    manager = _get_manager()
    try:
        fks = metadata.get_foreign_keys(
            manager, table=table, connection=connection, schema=schema
        )
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    if not fks:
        return f"*No foreign keys found for table '{table}'.*"

    columns = list(fks[0].keys())
    rows = [tuple(f.get(c, "") for c in columns) for f in fks]
    return format_as_markdown(columns, rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
