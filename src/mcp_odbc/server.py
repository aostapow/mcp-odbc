"""FastMCP server — tool registration + entry point."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager

import pyodbc
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from mcp_odbc import lockout, metadata
from mcp_odbc.config import load_config
from mcp_odbc.connection import ConnectionManager
from mcp_odbc.errors import handle_odbc_error
from mcp_odbc.formatting import format_as_markdown
from mcp_odbc.query import run_query, run_stored_procedure

_conn_manager: ConnectionManager | None = None


def _get_manager() -> ConnectionManager:
    if _conn_manager is None:
        raise ToolError("Servidor no inicializado.")
    return _conn_manager


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(server: FastMCP):
    global _conn_manager
    config = load_config()
    _conn_manager = ConnectionManager(config)
    print("mcp-odbc: servidor iniciado", file=sys.stderr)
    try:
        yield
    finally:
        if _conn_manager:
            _conn_manager.close_all()
            _conn_manager = None
        print("mcp-odbc: servidor detenido", file=sys.stderr)


mcp = FastMCP("mcp-odbc", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_dsns() -> str:
    """Lista todos los DSN ODBC configurados en el sistema."""
    sources = pyodbc.dataSources()
    if not sources:
        return "*No se encontraron origenes de datos ODBC.*"
    columns = ["DSN", "Driver"]
    rows = [(name, driver) for name, driver in sorted(sources.items())]
    return format_as_markdown(columns, rows)


@mcp.tool()
def list_connections() -> str:
    """Lista las conexiones configuradas, su estado y bloqueo de autenticacion.

    Muestra si una conexion esta bloqueada por intentos fallidos de login
    y cuantos intentos fallidos acumula.
    """
    manager = _get_manager()
    conns = manager.list_connections()
    if not conns:
        return "*No hay conexiones configuradas.*"
    columns = ["Nombre", "Conectado", "Solo-Lectura", "Bloqueada", "Intentos-Fallidos", "DBMS", "Adaptador"]
    rows = [
        (
            c["name"],
            str(c["connected"]),
            str(c["readonly"]),
            "SI" if c.get("locked") else "no",
            str(c.get("auth_attempts", 0)),
            c["dbms"],
            c["adapter"],
        )
        for c in conns
    ]
    return format_as_markdown(columns, rows)


@mcp.tool()
def test_connection(connection: str | None = None) -> str:
    """Verificar conectividad e informar tipo y version del DBMS.

    Args:
        connection: Nombre de la conexion. Usa la default si no se especifica.
    """
    manager = _get_manager()
    try:
        manager.get(connection)
    except ToolError:
        raise
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    info = manager.get_dbms_info(connection)
    lines = ["**Conexion exitosa**\n", "| Propiedad | Valor |", "| --- | --- |"]
    for key, value in info.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


@mcp.tool()
def reset_lockout(connection: str) -> str:
    """Desbloquear una conexion bloqueada por intentos fallidos de autenticacion.

    Usar este tool despues de corregir las credenciales en config.ini para
    volver a habilitar los intentos de conexion.

    Args:
        connection: Nombre de la conexion a desbloquear.
    """
    manager = _get_manager()
    if connection not in manager.config.connections:
        raise ToolError(
            f"Conexion desconocida '{connection}'. "
            f"Disponibles: {', '.join(manager.config.connections.keys()) or '(ninguna)'}"
        )

    prev = lockout.reset_manual(connection)

    if not prev:
        return f"La conexion '{connection}' no tenia intentos registrados."

    was_locked = prev.get("locked", False)
    attempts   = prev.get("attempts", 0)
    last       = prev.get("last_failure") or "nunca"

    if was_locked:
        return (
            f"Conexion '{connection}' DESBLOQUEADA.\n"
            f"- Intentos fallidos previos: {attempts}\n"
            f"- Ultimo fallo: {last}\n"
            "Ahora puede volver a intentar la conexion."
        )
    return (
        f"Conexion '{connection}' reseteada "
        f"(tenia {attempts} intento(s) fallido(s), no estaba bloqueada)."
    )


@mcp.tool()
def list_tables(
    connection: str | None = None,
    schema: str | None = None,
    table_type: str | None = None,
    name_pattern: str | None = None,
) -> str:
    """Listar tablas y vistas de la base de datos.

    Args:
        connection:   Nombre de la conexion.
        schema:       Filtrar por esquema/owner.
        table_type:   Filtrar por tipo: TABLE, VIEW, SYSTEM TABLE.
        name_pattern: Patron LIKE para el nombre de la tabla (% y _).
    """
    manager = _get_manager()
    try:
        tables = metadata.get_tables(
            manager, connection=connection, schema=schema,
            table_type=table_type, name_pattern=name_pattern,
        )
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc

    if not tables:
        return "*No se encontraron tablas.*"
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
    """Describir la estructura de una tabla: columnas, PKs y FKs.

    Args:
        table:      Nombre de la tabla.
        connection: Nombre de la conexion.
        schema:     Esquema/owner de la tabla.
        include:    columns (default), all, o combinacion: columns,pks,fks.
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
        parts.append(f"### Columnas — {table}\n")
        col_headers = list(cols[0].keys())
        parts.append(format_as_markdown(col_headers, [tuple(c.get(h, "") for h in col_headers) for c in cols]))
    else:
        parts.append(f"*No se encontraron columnas para '{table}'.*")

    if pks:
        parts.append("\n### Claves Primarias\n")
        pk_headers = list(pks[0].keys())
        parts.append(format_as_markdown(pk_headers, [tuple(p.get(h, "") for h in pk_headers) for p in pks]))
    if fks:
        parts.append("\n### Claves Foraneas\n")
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
    """Ejecutar una consulta SELECT de solo lectura y devolver resultados.

    Args:
        query:      Consulta SQL SELECT a ejecutar.
        connection: Nombre de la conexion.
        max_rows:   Maximo de filas a devolver (default 100, max 10000).
        format:     Formato de salida: markdown (default) o json.
    """
    manager = _get_manager()
    resolved = manager._resolve_name(connection)
    conn_config = manager.config.connections.get(resolved)
    config_max = conn_config.max_rows if conn_config else manager.config.max_rows
    max_rows = min(max_rows, config_max)
    readonly = conn_config.readonly if conn_config else True

    cnxn = manager.get(connection)
    return run_query(cnxn, query, max_rows=max_rows, readonly=readonly,
                     format=format, connection_name=resolved)


@mcp.tool()
def execute_sp(
    sp_name: str,
    params: list[str] | None = None,
    connection: str | None = None,
    max_rows: int = 100,
    format: str = "markdown",
) -> str:
    """Ejecutar un stored procedure habilitado en la whitelist.

    Args:
        sp_name:    Nombre del stored procedure.
        params:     Parametros posicionales como strings.
        connection: Nombre de la conexion.
        max_rows:   Maximo de filas a devolver.
        format:     markdown (default) o json.
    """
    manager = _get_manager()
    resolved = manager._resolve_name(connection)
    conn_config = manager.config.connections.get(resolved)
    if conn_config is None:
        raise ToolError(f"Conexion desconocida '{resolved}'.")

    cnxn = manager.get(connection)
    return run_stored_procedure(
        cnxn, sp_name=sp_name, params=params or [],
        max_rows=min(max_rows, conn_config.max_rows),
        allow_sp=conn_config.allow_sp,
        sp_whitelist=conn_config.sp_whitelist,
        format=format, connection_name=resolved,
    )


@mcp.tool()
def get_primary_keys(table: str, connection: str | None = None, schema: str | None = None) -> str:
    """Obtener columnas de clave primaria de una tabla."""
    manager = _get_manager()
    try:
        pks = metadata.get_primary_keys(manager, table=table, connection=connection, schema=schema)
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc
    if not pks:
        return f"*No se encontraron claves primarias para '{table}'.*"
    columns = list(pks[0].keys())
    return format_as_markdown(columns, [tuple(p.get(c, "") for c in columns) for p in pks])


@mcp.tool()
def get_foreign_keys(table: str, connection: str | None = None, schema: str | None = None) -> str:
    """Obtener relaciones de clave foranea de una tabla."""
    manager = _get_manager()
    try:
        fks = metadata.get_foreign_keys(manager, table=table, connection=connection, schema=schema)
    except pyodbc.Error as exc:
        raise handle_odbc_error(exc) from exc
    if not fks:
        return f"*No se encontraron claves foraneas para '{table}'.*"
    columns = list(fks[0].keys())
    return format_as_markdown(columns, [tuple(f.get(c, "") for c in columns) for f in fks])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
