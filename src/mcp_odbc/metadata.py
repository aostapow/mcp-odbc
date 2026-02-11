"""Schema discovery — thin delegation to adapters via ConnectionManager.

Phase 3 adds caching here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_odbc.connection import ConnectionManager


def get_tables(
    manager: ConnectionManager,
    connection: str | None = None,
    schema: str | None = None,
    table_type: str | None = None,
) -> list[dict]:
    """List tables for a connection."""
    cnxn = manager.get(connection)
    adapter = manager.get_adapter(connection)
    cursor = cnxn.cursor()
    try:
        return adapter.get_tables(cursor, schema=schema, table_type=table_type)
    finally:
        cursor.close()


def get_columns(
    manager: ConnectionManager,
    table: str,
    connection: str | None = None,
    schema: str | None = None,
) -> list[dict]:
    """List columns for a table."""
    cnxn = manager.get(connection)
    adapter = manager.get_adapter(connection)
    cursor = cnxn.cursor()
    try:
        return adapter.get_columns(cursor, table=table, schema=schema)
    finally:
        cursor.close()


def get_primary_keys(
    manager: ConnectionManager,
    table: str,
    connection: str | None = None,
    schema: str | None = None,
) -> list[dict]:
    """Get primary key columns for a table."""
    cnxn = manager.get(connection)
    adapter = manager.get_adapter(connection)
    cursor = cnxn.cursor()
    try:
        return adapter.get_primary_keys(cursor, table=table, schema=schema)
    finally:
        cursor.close()


def get_foreign_keys(
    manager: ConnectionManager,
    table: str,
    connection: str | None = None,
    schema: str | None = None,
) -> list[dict]:
    """Get foreign key relationships for a table."""
    cnxn = manager.get(connection)
    adapter = manager.get_adapter(connection)
    cursor = cnxn.cursor()
    try:
        return adapter.get_foreign_keys(cursor, table=table, schema=schema)
    finally:
        cursor.close()
