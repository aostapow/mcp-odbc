"""GenericODBCAdapter — universal fallback using ODBC catalog functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_odbc.adapters.base import SystemAdapter

if TYPE_CHECKING:
    import pyodbc


class GenericODBCAdapter(SystemAdapter):
    """Universal fallback adapter using standard ODBC catalog functions."""

    name = "generic"
    display_name = "Generic ODBC"

    @staticmethod
    def detect(connection: pyodbc.Connection) -> bool:
        """Always matches — universal fallback (must be last in registry)."""
        return True

    def get_tables(
        self,
        cursor: pyodbc.Cursor,
        schema: str | None = None,
        table_type: str | None = None,
        name_pattern: str | None = None,
    ) -> list[dict]:
        """List tables via cursor.tables()."""
        kwargs: dict = {}
        if schema:
            kwargs["schema"] = schema
        if table_type:
            kwargs["tableType"] = table_type
        if name_pattern:
            kwargs["table"] = name_pattern
        cursor.tables(**kwargs)
        rows = cursor.fetchall()
        return [
            {
                "catalog": row.table_cat,
                "schema": row.table_schem,
                "table_name": row.table_name,
                "table_type": row.table_type,
                "remarks": row.remarks,
            }
            for row in rows
        ]

    def get_columns(
        self,
        cursor: pyodbc.Cursor,
        table: str,
        schema: str | None = None,
    ) -> list[dict]:
        """List columns via cursor.columns()."""
        kwargs: dict = {"table": table}
        if schema:
            kwargs["schema"] = schema
        cursor.columns(**kwargs)
        rows = cursor.fetchall()
        return [
            {
                "column_name": row.column_name,
                "type_name": row.type_name,
                "column_size": row.column_size,
                "nullable": row.nullable,
                "remarks": getattr(row, "remarks", None),
            }
            for row in rows
        ]
