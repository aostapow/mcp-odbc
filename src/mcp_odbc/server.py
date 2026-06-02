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
from mcp_odbc.query import run_query, run_stored_procedure

_conn_manager: ConnectionManager | None = None


def _get_manager() -> ConnectionManager:
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
# Tools
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

    Shows which connections are active, their DBMS type, read-only status,
    and whether stored procedures are enabled.
    """
    manager = _get_manager()
    conns = manager.list_connections()
    if not conns:
        return "*No connections configured.*"
    columns = ["Name", "Connected", "Read-Only", "Allow SP", "DBMS", "Adapter"]
    rows = [
        (
            c["name"],
            str(c["connected"]),
            str(c["readonly"]),
            str(c.get("allow_sp", False)),
            c["dbms"],
            c["adapter"],
        )
        for c in conns
    ]
    return format_as_markdown(columns, rows)


@mcp.tool()
def test_connection(connection: str | None = None) -> str:
    """Test an ODBC connection and report DBMS type and version.

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
    lines = ["**Connection successful**\n", "| Property | Value |", "| --- | --- |"]
    for key, value in info.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


@mcp.tool()
def list_tables(
    connection: str | None = None,
    schema: str | None = None,
    table_type: str | None = None,
    name_pattern: str | None = None,
) -> str:
    """List tables and views in the database.

    Use name_pattern to filter by table name with SQL LIKE wildcards (% and _).
    Examples: "%invoice%" finds all tables containing "invoice".

    Args:
        connection:   Connection name. Uses default if not specified.
        schema:       Filter by schema/owner name.
        table_type:   Filter by type — "TABLE", "VIEW", "SYSTEM TABLE".
        name_pattern: SQL LIKE pattern for the table name.
    """
    manager = _get_manager()
    try:
        tables = metadata.get_tables(
            manager,
            connection=connection,
            schema=schema,
            table_type=table_type,
            name_pattern=name_pattern,
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
    include: str = "columns",
) -> str:
    """Describe a table's structure — columns, primary keys, and/or foreign keys.

    Args:
        table:      Table name to describe.
        connection: Connection name. Uses default if not specified.
        schema:     Schema/owner of the table.
        include:    "columns" (default), "all", or comma-separated "columns,pks,fks".
    """
    manager = _get_manager()
    include_parts = {p.strip().lower() for p in include.split(",")}
    want_pks = "all" in include_parts or "pks" in include_parts
    want_fks = "all" in include_parts or "fks" in include_parts

    try:
        cols = metadata.get_columns(manager, table=table, connection=connection, schema=schema)
        pks = metadata.get_primary_keys(manager, table=table, connection=connection, schema=schema) if want_pks else []
        fks = metadata.get_foreign_keys(manager, table=table, connection=connection, schema=schema) if want_fks else []
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    parts: list[str] = []
    if cols:
        parts.append(f"### Columns — {table}\n")
        col_headers = list(cols[0].keys())
        parts.append(format_as_markdown(col_headers, [tuple(c.get(h, "") for h in col_headers) for c in cols]))
    else:
        parts.append(f"*No columns found for table '{table}'.*")

    if pks:
        parts.append("\n### Primary Keys\n")
        pk_headers = list(pks[0].keys())
        parts.append(format_as_markdown(pk_headers, [tuple(p.get(h, "") for h in pk_headers) for p in pks]))

    if fks:
        parts.append("\n### Foreign Keys\n")
        fk_headers = list(fks[0].keys())
        parts.append(format_as_markdown(fk_headers, [tuple(f.get(h, "") for h in fk_headers) for f in fks]))

    return "\n".join(parts)


@mcp.tool()
def execute_query(
    query: str,
    connection: str | None = None,
    max_rows: int = 100,
    format: str = "markdown",
) -> str:
    """Execute a read-only SQL SELECT query and return results.

    Only SELECT (and WITH for CTEs) are allowed — write operations are blocked.
    All executions are recorded in the audit log.

    Args:
        query:      SQL SELECT query to execute.
        connection: Connection name. Uses default if not specified.
        max_rows:   Maximum rows to return (default 100, max 10000).
        format:     Output format — "markdown" (default) or "json".
    """
    manager = _get_manager()
    resolved = manager._resolve_name(connection)
    conn_config = manager.config.connections.get(resolved)
    config_max = conn_config.max_rows if conn_config else manager.config.max_rows
    max_rows = min(max_rows, config_max)
    readonly = conn_config.readonly if conn_config else True

    cnxn = manager.get(connection)
    return run_query(
        cnxn,
        query,
        max_rows=max_rows,
        readonly=readonly,
        format=format,
        connection_name=resolved,
    )


@mcp.tool()
def execute_sp(
    sp_name: str,
    params: list[str] | None = None,
    connection: str | None = None,
    max_rows: int = 100,
    format: str = "markdown",
) -> str:
    """Execute a whitelisted stored procedure and return results.

    Stored procedure execution must be explicitly enabled per connection in
    config.ini (``allow_sp = true``). If ``sp_whitelist`` is configured, only
    procedures in that list are accepted.

    All executions are recorded in the audit log.

    Use this for COBIS stored procedures (e.g. sp_cobis_saldos) that cannot
    be expressed as a plain SELECT.

    Args:
        sp_name:    Name of the stored procedure (alphanumeric / _ / @ / # only).
        params:     Positional parameters as strings (cast by the driver).
        connection: Connection name. Uses default if not specified.
        max_rows:   Maximum rows to return (default 100).
        format:     Output format — "markdown" (default) or "json".
    """
    manager = _get_manager()
    resolved = manager._resolve_name(connection)
    conn_config = manager.config.connections.get(resolved)

    if conn_config is None:
        raise ToolError(
            f"Unknown connection '{resolved}'. "
            f"Available: {', '.join(manager.config.connections.keys()) or '(none)'}"
        )

    config_max = conn_config.max_rows
    max_rows = min(max_rows, config_max)
    cnxn = manager.get(connection)

    return run_stored_procedure(
        cnxn,
        sp_name=sp_name,
        params=params or [],
        max_rows=max_rows,
        allow_sp=conn_config.allow_sp,
        sp_whitelist=conn_config.sp_whitelist,
        format=format,
        connection_name=resolved,
    )


@mcp.tool()
def get_primary_keys(
    table: str,
    connection: str | None = None,
    schema: str | None = None,
) -> str:
    """Get primary key columns for a table.

    Args:
        table:      Table name.
        connection: Connection name. Uses default if not specified.
        schema:     Schema/owner of the table.
    """
    manager = _get_manager()
    try:
        pks = metadata.get_primary_keys(manager, table=table, connection=connection, schema=schema)
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    if not pks:
        return f"*No primary keys found for table '{table}'.*"
    columns = list(pks[0].keys())
    return format_as_markdown(columns, [tuple(p.get(c, "") for c in columns) for p in pks])


@mcp.tool()
def get_foreign_keys(
    table: str,
    connection: str | None = None,
    schema: str | None = None,
) -> str:
    """Get foreign key relationships for a table.

    Args:
        table:      Table name.
        connection: Connection name. Uses default if not specified.
        schema:     Schema/owner of the table.
    """
    manager = _get_manager()
    try:
        fks = metadata.get_foreign_keys(manager, table=table, connection=connection, schema=schema)
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    if not fks:
        return f"*No foreign keys found for table '{table}'.*"
    columns = list(fks[0].keys())
    return format_as_markdown(columns, [tuple(f.get(c, "") for c in columns) for f in fks])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
