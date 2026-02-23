"""SystemAdapter ABC — base class for all DBMS-specific adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyodbc


def _row_to_dict(row, cursor_description) -> dict:
    """Convert a pyodbc Row to a dict using cursor.description column names."""
    return {desc[0]: getattr(row, desc[0], None) for desc in cursor_description}


class SystemAdapter(ABC):
    """Base for system-specific metadata operations."""

    name: str = "base"
    display_name: str = "Base Adapter"

    @staticmethod
    @abstractmethod
    def detect(connection: pyodbc.Connection) -> bool:
        """Return True if this adapter matches the connection."""

    @abstractmethod
    def get_tables(
        self,
        cursor: pyodbc.Cursor,
        schema: str | None = None,
        table_type: str | None = None,
        name_pattern: str | None = None,
    ) -> list[dict]:
        """List tables/views."""

    @abstractmethod
    def get_columns(
        self,
        cursor: pyodbc.Cursor,
        table: str,
        schema: str | None = None,
    ) -> list[dict]:
        """List columns for a table."""

    def get_primary_keys(
        self,
        cursor: pyodbc.Cursor,
        table: str,
        schema: str | None = None,
    ) -> list[dict]:
        """Default: use ODBC catalog function."""
        cursor.primaryKeys(table=table, schema=schema)
        desc = cursor.description
        if not desc:
            return []
        return [_row_to_dict(r, desc) for r in cursor.fetchall()]

    def get_foreign_keys(
        self,
        cursor: pyodbc.Cursor,
        table: str,
        schema: str | None = None,
    ) -> list[dict]:
        """Default: use ODBC catalog function."""
        cursor.foreignKeys(foreignTable=table, foreignSchema=schema)
        desc = cursor.description
        if not desc:
            return []
        return [_row_to_dict(r, desc) for r in cursor.fetchall()]

    def apply_connection_settings(self, connection: pyodbc.Connection) -> None:
        """Apply system-specific settings after connect (encoding, etc.)."""

    def get_sql_capabilities(self) -> dict:
        """Return SQL dialect info."""
        return {
            "supports_cte": True,
            "supports_limit": True,
            "read_only": False,
            "max_concurrent": None,
        }
