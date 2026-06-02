"""ConnectionManager con soporte de bloqueo por autenticacion fallida."""

from __future__ import annotations

import pyodbc
from fastmcp.exceptions import ToolError

from mcp_odbc.adapters.base import SystemAdapter
from mcp_odbc.config import ServerConfig
from mcp_odbc.detection import detect_dbms
from mcp_odbc.errors import handle_odbc_error
from mcp_odbc import lockout

pyodbc.pooling = False

# SQLSTATE de autenticacion fallida
_AUTH_SQLSTATES = {"28000", "28001", "08004"}


class ConnectionManager:
    """Manages named ODBC connections with lazy loading, health checks,
    and authentication lockout protection."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._connections: dict[str, pyodbc.Connection] = {}
        self._adapters: dict[str, SystemAdapter] = {}
        self._dbms_info: dict[str, dict] = {}

    def _resolve_name(self, name: str | None) -> str:
        return name or self.config.default_connection

    def get(self, name: str | None = None) -> pyodbc.Connection:
        """Obtener conexion por nombre.  Verifica bloqueo antes de conectar."""
        name = self._resolve_name(name)

        if name not in self.config.connections:
            raise ToolError(
                f"Conexion desconocida '{name}'. "
                f"Disponibles: {', '.join(self.config.connections.keys()) or '(ninguna)'}"
            )

        conn_config = self.config.connections[name]
        max_failures = getattr(conn_config, "max_auth_failures", lockout._GLOBAL_MAX)

        # --- Verificar bloqueo ANTES de intentar conectar ---
        lockout.check(name, max_failures)

        # Reusar conexion cacheada si esta sana
        if name in self._connections:
            if self._health_check(self._connections[name]):
                return self._connections[name]
            self._close(name)

        # Intentar conexion
        try:
            cnxn = pyodbc.connect(
                conn_config.connection_string,
                autocommit=True,
                timeout=conn_config.connect_timeout,
                readonly=conn_config.readonly,
            )
        except pyodbc.Error as exc:
            sqlstate = exc.args[0] if exc.args else ""

            if sqlstate in _AUTH_SQLSTATES:
                # Registrar fallo de autenticacion (puede bloquear y lanzar ToolError)
                lockout.record_failure(name, max_failures)
                # Si record_failure no lanzo (aun no alcanzo el maximo), lanzar error normal
                raise handle_odbc_error(exc) from exc

            raise handle_odbc_error(exc) from exc

        # Conexion exitosa: resetear contador
        lockout.reset(name)

        try:
            cnxn.timeout = conn_config.query_timeout
        except pyodbc.Error:
            pass

        try:
            dbms_info, adapter = detect_dbms(cnxn)
            adapter.apply_connection_settings(cnxn)
            self._adapters[name] = adapter
            self._dbms_info[name] = dbms_info
        except Exception:
            from mcp_odbc.adapters.generic import GenericODBCAdapter
            self._adapters[name] = GenericODBCAdapter()
            self._dbms_info[name] = {"adapter": "generic"}

        self._connections[name] = cnxn
        return cnxn

    def get_adapter(self, name: str | None = None) -> SystemAdapter:
        name = self._resolve_name(name)
        if name not in self._adapters:
            self.get(name)
        return self._adapters[name]

    def get_dbms_info(self, name: str | None = None) -> dict:
        name = self._resolve_name(name)
        if name not in self._dbms_info:
            self.get(name)
        return self._dbms_info[name]

    def _health_check(self, cnxn: pyodbc.Connection) -> bool:
        try:
            cnxn.execute("SELECT 1")
            return True
        except (pyodbc.Error, AttributeError):
            return False

    def _close(self, name: str) -> None:
        cnxn = self._connections.pop(name, None)
        self._adapters.pop(name, None)
        self._dbms_info.pop(name, None)
        if cnxn:
            try:
                cnxn.close()
            except Exception:
                pass

    def close_all(self) -> None:
        for name in list(self._connections):
            self._close(name)

    def list_connections(self) -> list[dict]:
        result = []
        for name, conn_config in self.config.connections.items():
            connected = name in self._connections
            info = self._dbms_info.get(name, {})
            lk = lockout.status(name)
            result.append({
                "name": name,
                "connected": connected,
                "readonly": conn_config.readonly,
                "allow_sp": getattr(conn_config, "allow_sp", False),
                "dbms": info.get("dbms_name", ""),
                "adapter": info.get("adapter", ""),
                "auth_attempts": lk.get("attempts", 0),
                "locked": lk.get("locked", False),
            })
        return result
