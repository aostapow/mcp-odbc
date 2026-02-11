"""Tests for config loading — env vars, INI parsing, precedence."""

import os
import tempfile
from pathlib import Path

import pytest

from mcp_odbc.config import ConnectionConfig, ServerConfig, _parse_ini_file, load_config


class TestConnectionConfig:
    def test_defaults(self):
        c = ConnectionConfig(connection_string="DSN=Test")
        assert c.readonly is True
        assert c.query_timeout == 30
        assert c.connect_timeout == 10
        assert c.max_rows == 10000


class TestParseIniFile:
    def test_basic_ini(self, tmp_path):
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[server]\n"
            "default_connection = mydb\n"
            "max_rows = 5000\n"
            "\n"
            "[mydb]\n"
            "connection_string = DSN=MyDB;UID=user;PWD=pass\n"
            "readonly = true\n"
            "query_timeout = 45\n"
        )
        config = _parse_ini_file(ini)
        assert config.default_connection == "mydb"
        assert config.max_rows == 5000
        assert "mydb" in config.connections
        assert config.connections["mydb"].query_timeout == 45

    def test_multiple_connections(self, tmp_path):
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[server]\ndefault_connection = a\n\n"
            "[a]\nconnection_string = DSN=A\nreadonly = true\n\n"
            "[b]\nconnection_string = DSN=B\nreadonly = false\n"
        )
        config = _parse_ini_file(ini)
        assert len(config.connections) == 2
        assert config.connections["a"].readonly is True
        assert config.connections["b"].readonly is False

    def test_preserves_key_casing(self, tmp_path):
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[MyConnection]\n"
            "connection_string = DSN=Test\n"
        )
        config = _parse_ini_file(ini)
        assert "MyConnection" in config.connections


class TestLoadConfig:
    def test_env_var_dsn(self, monkeypatch):
        monkeypatch.setenv("ODBC_DSN", "TestDSN")
        monkeypatch.delenv("ODBC_CONNECTION_STRING", raising=False)
        monkeypatch.delenv("ODBC_MCP_CONFIG", raising=False)
        config = load_config()
        assert "default" in config.connections
        assert config.connections["default"].connection_string == "DSN=TestDSN"
        assert config.connections["default"].readonly is True

    def test_env_var_connection_string(self, monkeypatch):
        monkeypatch.setenv("ODBC_CONNECTION_STRING", "DRIVER={SQL};SERVER=x")
        monkeypatch.delenv("ODBC_DSN", raising=False)
        monkeypatch.delenv("ODBC_MCP_CONFIG", raising=False)
        config = load_config()
        assert config.connections["default"].connection_string == "DRIVER={SQL};SERVER=x"

    def test_env_var_readonly_false(self, monkeypatch):
        monkeypatch.setenv("ODBC_DSN", "Test")
        monkeypatch.setenv("ODBC_READ_ONLY", "false")
        monkeypatch.delenv("ODBC_MCP_CONFIG", raising=False)
        config = load_config()
        assert config.connections["default"].readonly is False

    def test_env_overrides_ini(self, monkeypatch, tmp_path):
        ini = tmp_path / "config.ini"
        ini.write_text(
            "[server]\ndefault_connection = fromini\n\n"
            "[fromini]\nconnection_string = DSN=FromINI\n"
        )
        monkeypatch.setenv("ODBC_MCP_CONFIG", str(ini))
        monkeypatch.setenv("ODBC_DSN", "FromEnv")
        config = load_config()
        # Env vars override default_connection to "default"
        assert config.default_connection == "default"
        assert "default" in config.connections
        # But INI connections are still present
        assert "fromini" in config.connections

    def test_missing_config_returns_empty(self, monkeypatch):
        monkeypatch.delenv("ODBC_DSN", raising=False)
        monkeypatch.delenv("ODBC_CONNECTION_STRING", raising=False)
        monkeypatch.delenv("ODBC_MCP_CONFIG", raising=False)
        # Ensure no config/config.ini exists in cwd
        config = load_config()
        assert isinstance(config, ServerConfig)
