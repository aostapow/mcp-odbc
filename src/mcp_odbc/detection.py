"""DBMS detection via ODBC SQLGetInfo + adapter registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_odbc.adapters import get_adapter

if TYPE_CHECKING:
    import pyodbc

    from mcp_odbc.adapters.base import SystemAdapter


def detect_dbms(connection: pyodbc.Connection) -> tuple[dict, SystemAdapter]:
    """Detect the DBMS type and return info dict + matched adapter.

    Uses connection.getinfo() for SQL_DBMS_NAME, SQL_DBMS_VER, SQL_DRIVER_NAME.
    Each call is wrapped in try/except since not all drivers support all info types.

    Returns:
        Tuple of (info_dict, adapter_instance).
    """
    import pyodbc as _pyodbc

    info: dict = {}

    for key, attr in [
        ("dbms_name", _pyodbc.SQL_DBMS_NAME),
        ("dbms_version", _pyodbc.SQL_DBMS_VER),
        ("driver_name", _pyodbc.SQL_DRIVER_NAME),
    ]:
        try:
            info[key] = connection.getinfo(attr)
        except Exception:
            info[key] = "unknown"

    adapter = get_adapter(connection)
    info["adapter"] = adapter.name
    info["adapter_display"] = adapter.display_name

    return info, adapter
