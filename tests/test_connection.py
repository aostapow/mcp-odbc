"""Tests for ConnectionManager — lazy connect, health check, close."""

from unittest.mock import MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from mcp_odbc.config import ConnectionConfig, ServerConfig
from mcp_odbc.connection import ConnectionManager


@pytest.fixture
def manager(test_config):
    """ConnectionManager with test config."""
    return ConnectionManager(test_config)


class TestConnectionManager:
    @patch("mcp_odbc.connection.pyodbc")
    @patch("mcp_odbc.connection.detect_dbms")
    def test_lazy_connect(self, mock_detect, mock_pyodbc, manager):
        mock_conn = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        mock_detect.return_value = ({"adapter": "generic"}, MagicMock())

        result = manager.get("test")
        assert result is mock_conn
        mock_pyodbc.connect.assert_called_once()

    @patch("mcp_odbc.connection.pyodbc")
    @patch("mcp_odbc.connection.detect_dbms")
    def test_cached_connection_reused(self, mock_detect, mock_pyodbc, manager):
        mock_conn = MagicMock()
        mock_conn.execute.return_value = None  # health check passes
        mock_pyodbc.connect.return_value = mock_conn
        mock_pyodbc.Error = Exception
        mock_detect.return_value = ({"adapter": "generic"}, MagicMock())

        manager.get("test")
        manager.get("test")
        # Should connect only once (cached)
        assert mock_pyodbc.connect.call_count == 1

    def test_unknown_connection_raises(self, manager):
        with pytest.raises(ToolError, match="Unknown connection"):
            manager.get("nonexistent")

    @patch("mcp_odbc.connection.pyodbc")
    @patch("mcp_odbc.connection.detect_dbms")
    def test_health_check_reconnects(self, mock_detect, mock_pyodbc, manager):
        mock_conn1 = MagicMock()
        mock_conn2 = MagicMock()
        mock_pyodbc.connect.side_effect = [mock_conn1, mock_conn2]
        mock_pyodbc.Error = Exception
        mock_detect.return_value = ({"adapter": "generic"}, MagicMock())

        # First connect
        manager.get("test")

        # Simulate stale connection (health check fails)
        mock_conn1.execute.side_effect = Exception("stale")

        result = manager.get("test")
        assert result is mock_conn2
        assert mock_pyodbc.connect.call_count == 2

    @patch("mcp_odbc.connection.pyodbc")
    @patch("mcp_odbc.connection.detect_dbms")
    def test_close_all(self, mock_detect, mock_pyodbc, manager):
        mock_conn = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        mock_pyodbc.Error = Exception
        mock_detect.return_value = ({"adapter": "generic"}, MagicMock())

        manager.get("test")
        manager.close_all()
        mock_conn.close.assert_called_once()
        assert len(manager._connections) == 0

    @patch("mcp_odbc.connection.pyodbc")
    @patch("mcp_odbc.connection.detect_dbms")
    def test_list_connections(self, mock_detect, mock_pyodbc, manager):
        mock_pyodbc.connect.return_value = MagicMock()
        mock_pyodbc.Error = Exception
        mock_detect.return_value = (
            {"adapter": "generic", "dbms_name": "TestDB"},
            MagicMock(),
        )

        conns = manager.list_connections()
        assert len(conns) == 2
        names = {c["name"] for c in conns}
        assert "test" in names
        assert "writable" in names

    @patch("mcp_odbc.connection.pyodbc")
    @patch("mcp_odbc.connection.detect_dbms")
    def test_default_connection(self, mock_detect, mock_pyodbc, manager):
        mock_pyodbc.connect.return_value = MagicMock()
        mock_pyodbc.Error = Exception
        mock_detect.return_value = ({"adapter": "generic"}, MagicMock())

        # None should resolve to "test" (the default)
        result = manager.get(None)
        assert result is not None
