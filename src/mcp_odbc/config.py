"""Pydantic config models, env var / INI loading."""

from __future__ import annotations

import configparser
import os
from pathlib import Path

from pydantic import BaseModel

from mcp_odbc.vault import decrypt_connection_string


class ConnectionConfig(BaseModel):
    """Configuration for a single ODBC connection."""

    connection_string: str
    readonly: bool = True
    query_timeout: int = 30
    connect_timeout: int = 10
    max_rows: int = 10000
    # Stored-procedure execution
    allow_sp: bool = False
    sp_whitelist: list[str] = []   # if non-empty, only these SP names are allowed


class ServerConfig(BaseModel):
    """Top-level server configuration."""

    default_connection: str = "default"
    connections: dict[str, ConnectionConfig] = {}
    cache_ttl: int = 300
    max_rows: int = 10000


def _parse_ini_file(path: str | Path) -> ServerConfig:
    """Parse INI config file into ServerConfig.

    [server] section holds server-level settings.
    All other sections are connection definitions.

    Connection strings may contain ``dpapi:<base64>`` tokens in place of
    plain-text passwords.  These are transparently decrypted via
    :func:`mcp_odbc.vault.decrypt_connection_string` using Windows DPAPI.

    Stored-procedure options per connection::

        allow_sp   = true
        sp_whitelist = sp_cobis_saldos, sp_cobis_movimientos
    """
    config = configparser.ConfigParser()
    config.optionxform = str  # preserve key casing
    config.read(str(path))

    server_kwargs: dict = {}
    connections: dict[str, ConnectionConfig] = {}

    if config.has_section("server"):
        server_section = dict(config["server"])
        if "default_connection" in server_section:
            server_kwargs["default_connection"] = server_section["default_connection"]
        if "max_rows" in server_section:
            server_kwargs["max_rows"] = int(server_section["max_rows"])
        if "cache_ttl" in server_section:
            server_kwargs["cache_ttl"] = int(server_section["cache_ttl"])

    for section in config.sections():
        if section == "server":
            continue
        items = dict(config[section])
        raw_conn_str = items.get("connection_string", "")
        conn_str = decrypt_connection_string(raw_conn_str)

        conn_kwargs: dict = {"connection_string": conn_str}
        if "readonly" in items:
            conn_kwargs["readonly"] = items["readonly"].lower() in ("true", "1", "yes")
        if "query_timeout" in items:
            conn_kwargs["query_timeout"] = int(items["query_timeout"])
        if "connect_timeout" in items:
            conn_kwargs["connect_timeout"] = int(items["connect_timeout"])
        if "max_rows" in items:
            conn_kwargs["max_rows"] = int(items["max_rows"])
        if "allow_sp" in items:
            conn_kwargs["allow_sp"] = items["allow_sp"].lower() in ("true", "1", "yes")
        if "sp_whitelist" in items:
            # Comma-separated list of SP names
            conn_kwargs["sp_whitelist"] = [
                s.strip() for s in items["sp_whitelist"].split(",") if s.strip()
            ]
        connections[section] = ConnectionConfig(**conn_kwargs)

    server_kwargs["connections"] = connections
    return ServerConfig(**server_kwargs)


def load_config() -> ServerConfig:
    """Load configuration from INI file and/or environment variables.

    Precedence (highest first):
    1. Environment variables (create/override a "default" connection)
    2. Config file path from ODBC_MCP_CONFIG env var
    3. INI file at ./config/config.ini
    """
    config_path = os.environ.get("ODBC_MCP_CONFIG")
    if config_path and Path(config_path).exists():
        server_config = _parse_ini_file(config_path)
    elif Path("config/config.ini").exists():
        server_config = _parse_ini_file("config/config.ini")
    else:
        server_config = ServerConfig()

    dsn = os.environ.get("ODBC_DSN")
    conn_string = os.environ.get("ODBC_CONNECTION_STRING")

    if dsn or conn_string:
        env_conn_string = conn_string if conn_string else f"DSN={dsn}"

        uid = os.environ.get("ODBC_UID")
        pwd = os.environ.get("ODBC_PWD")
        if uid and "UID=" not in env_conn_string.upper():
            env_conn_string += f";UID={uid}"
        if pwd and "PWD=" not in env_conn_string.upper():
            plain_pwd = decrypt_connection_string(f"PWD={pwd}")[4:]
            env_conn_string += f";PWD={plain_pwd}"

        readonly_str = os.environ.get("ODBC_READ_ONLY", "true")
        readonly = readonly_str.lower() in ("true", "1", "yes")

        env_conn = ConnectionConfig(
            connection_string=env_conn_string,
            readonly=readonly,
            query_timeout=int(os.environ.get("ODBC_QUERY_TIMEOUT", "30")),
            connect_timeout=int(os.environ.get("ODBC_CONNECT_TIMEOUT", "10")),
            max_rows=int(os.environ.get("ODBC_MAX_ROWS", "10000")),
            allow_sp=os.environ.get("ODBC_ALLOW_SP", "").lower() in ("true", "1", "yes"),
        )
        server_config.connections["default"] = env_conn
        server_config.default_connection = "default"

    global_max_rows = os.environ.get("ODBC_MAX_ROWS")
    if global_max_rows:
        server_config.max_rows = int(global_max_rows)

    return server_config
