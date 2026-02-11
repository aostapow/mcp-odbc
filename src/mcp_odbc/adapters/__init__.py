"""Adapter registry and discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_odbc.adapters.generic import GenericODBCAdapter

if TYPE_CHECKING:
    import pyodbc

    from mcp_odbc.adapters.base import SystemAdapter

# Ordered list — GenericODBCAdapter must always be last (universal fallback).
# Phase 2 adds system-specific adapters before it.
ADAPTER_REGISTRY: list[type[SystemAdapter]] = [
    GenericODBCAdapter,
]


def get_adapter(connection: pyodbc.Connection) -> SystemAdapter:
    """Iterate the registry and return the first adapter that matches."""
    for adapter_cls in ADAPTER_REGISTRY:
        if adapter_cls.detect(connection):
            return adapter_cls()
    # Should never reach here since GenericODBCAdapter.detect() returns True
    return GenericODBCAdapter()
