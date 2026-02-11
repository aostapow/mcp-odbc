"""ConnectionManager — lazy connect, health check, lifecycle management."""

from __future__ import annotations

import pyodbc
from fastmcp.exceptions import ToolError

from mcp_odbc.adapters.base import SystemAdapter
from mcp_odbc.config import ServerConfig
from mcp_odbc.detection import detect_dbms
from mcp_odbc.errors import handle_odbc_error

# Disable ODBC-level pooling — we manage lifecycle explicitly.
pyodbc.pooling = False


class ConnectionManager:
    """Manages named ODBC connections with lazy loading and health checks."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._connections: dict[str, pyodbc.Connection] = {}
        self._adapters: dict[str, SystemAdapter] = {}
        self._dbms_info: dict[str, dict] = {}

    def _resolve_name(self, name: str | None) -> str:
        """Resolve None to the default connection name."""
        return name or self.config.default_connection

    def get(self, name: str | None = None) -> pyodbc.Connection:
        """Get connection by name (or default). Lazy-creates on first use."""
        name = self._resolve_name(name)

        if name not in self.config.connections:
            raise ToolError(
                f"Unknown connection '{name}'. "
                f"Available: {', '.join(self.config.connections.keys()) or '(none configured)'}"
            )

        # Return cached connection if healthy
        if name in self._connections:
            if self._health_check(self._connections[name]):
                return self._connections[name]
            self._close(name)

        conn_config = self.config.connections[name]

        try:
            cnxn = pyodbc.connect(
                conn_config.connection_string,
                autocommit=True,
                timeout=conn_config.connect_timeout,
                readonly=conn_config.readonly,
            )
        except pyodbc.Error as exc:
            raise handle_odbc_error(exc) from exc

        cnxn.timeout = conn_config.query_timeout

        # Detect DBMS and cache adapter
        try:
            dbms_info, adapter = detect_dbms(cnxn)
            adapter.apply_connection_settings(cnxn)
            self._adapters[name] = adapter
            self._dbms_info[name] = dbms_info
        except Exception:
            # Detection failure is non-fatal — use generic adapter
            from mcp_odbc.adapters.generic import GenericODBCAdapter

            self._adapters[name] = GenericODBCAdapter()
            self._dbms_info[name] = {"adapter": "generic"}

        self._connections[name] = cnxn
        return cnxn

    def get_adapter(self, name: str | None = None) -> SystemAdapter:
        """Return the cached adapter for a connection (connects if needed)."""
        name = self._resolve_name(name)
        if name not in self._adapters:
            self.get(name)  # triggers detection
        return self._adapters[name]

    def get_dbms_info(self, name: str | None = None) -> dict:
        """Return cached DBMS detection info (connects if needed)."""
        name = self._resolve_name(name)
        if name not in self._dbms_info:
            self.get(name)
        return self._dbms_info[name]

    def _health_check(self, cnxn: pyodbc.Connection) -> bool:
        """Quick health check with SELECT 1."""
        try:
            cnxn.execute("SELECT 1")
            return True
        except (pyodbc.Error, AttributeError):
            return False

    def _close(self, name: str) -> None:
        """Close a single connection and remove from caches."""
        cnxn = self._connections.pop(name, None)
        self._adapters.pop(name, None)
        self._dbms_info.pop(name, None)
        if cnxn:
            try:
                cnxn.close()
            except Exception:
                pass

    def close_all(self) -> None:
        """Close all connections."""
        for name in list(self._connections):
            self._close(name)

    def list_connections(self) -> list[dict]:
        """Return status of all configured connections."""
        result = []
        for name, conn_config in self.config.connections.items():
            connected = name in self._connections
            info = self._dbms_info.get(name, {})
            result.append(
                {
                    "name": name,
                    "connected": connected,
                    "readonly": conn_config.readonly,
                    "dbms": info.get("dbms_name", ""),
                    "adapter": info.get("adapter", ""),
                }
            )
        return result
