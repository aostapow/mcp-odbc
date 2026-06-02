"""Adapter registry and discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_odbc.adapters.generic import GenericODBCAdapter
from mcp_odbc.adapters.sybase import SybaseAdapter

if TYPE_CHECKING:
    import pyodbc

    from mcp_odbc.adapters.base import SystemAdapter

# Ordered list — most-specific adapters first, GenericODBCAdapter always last.
ADAPTER_REGISTRY: list[type[SystemAdapter]] = [
    SybaseAdapter,
    GenericODBCAdapter,
]


def get_adapter(connection: pyodbc.Connection) -> SystemAdapter:
    """Iterate the registry and return the first adapter that matches."""
    for adapter_cls in ADAPTER_REGISTRY:
        if adapter_cls.detect(connection):
            return adapter_cls()
    return GenericODBCAdapter()
