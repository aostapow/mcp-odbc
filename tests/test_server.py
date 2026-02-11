"""Integration tests via FastMCP Client with monkeypatched pyodbc."""

from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client

import mcp_odbc.server as server_module
from mcp_odbc.config import ConnectionConfig, ServerConfig
from mcp_odbc.connection import ConnectionManager
from mcp_odbc.server import mcp


@pytest.fixture
def mock_pyodbc_module():
    """Patch pyodbc at all relevant import sites."""
    with patch("mcp_odbc.connection.pyodbc") as mock_conn_pyodbc, \
         patch("mcp_odbc.server.pyodbc") as mock_srv_pyodbc, \
         patch("mcp_odbc.detection.detect_dbms") as mock_detect:

        mock_conn_pyodbc.pooling = False
        mock_conn_pyodbc.Error = Exception

        # Mock connection
        mock_conn = MagicMock()
        mock_conn.execute.return_value = None
        mock_conn.timeout = 30

        # Mock cursor
        mock_cursor = MagicMock()
        mock_cursor.description = [
            ("id", None, None, None, None, None, None),
            ("name", None, None, None, None, None, None),
        ]
        mock_cursor.fetchall.return_value = [
            MagicMock(
                table_cat="cat",
                table_schem="dbo",
                table_name="users",
                table_type="TABLE",
                remarks="",
            ),
        ]
        mock_cursor.fetchmany.return_value = [(1, "Alice"), (2, "Bob")]
        mock_cursor.close.return_value = None
        mock_conn.cursor.return_value = mock_cursor

        mock_conn_pyodbc.connect.return_value = mock_conn
        mock_conn.getinfo.return_value = "TestDBMS"

        # dataSources on the server-level pyodbc mock
        mock_srv_pyodbc.dataSources.return_value = {"TestDSN": "Test Driver"}

        # detect_dbms returns info + generic adapter
        from mcp_odbc.adapters.generic import GenericODBCAdapter
        mock_detect.return_value = (
            {"dbms_name": "TestDBMS", "dbms_version": "1.0", "driver_name": "test",
             "adapter": "generic", "adapter_display": "Generic ODBC"},
            GenericODBCAdapter(),
        )

        yield {
            "conn_pyodbc": mock_conn_pyodbc,
            "srv_pyodbc": mock_srv_pyodbc,
            "detect": mock_detect,
            "connection": mock_conn,
            "cursor": mock_cursor,
        }


@pytest.fixture
def setup_manager(mock_pyodbc_module):
    """Set up a ConnectionManager on the server module before tests."""
    config = ServerConfig(
        default_connection="default",
        connections={
            "default": ConnectionConfig(
                connection_string="DSN=TestDSN",
                readonly=True,
                query_timeout=30,
                connect_timeout=10,
                max_rows=1000,
            ),
        },
    )
    manager = ConnectionManager(config)
    server_module._conn_manager = manager
    yield mock_pyodbc_module
    server_module._conn_manager = None


@pytest.fixture
def client(setup_manager):
    """FastMCP test client with manager pre-initialized."""
    return Client(mcp)


@pytest.mark.asyncio
async def test_list_dsns(client, setup_manager):
    async with client:
        result = await client.call_tool("list_dsns", {})
        text = result.content[0].text
        assert "TestDSN" in text
        assert "Test Driver" in text


@pytest.mark.asyncio
async def test_list_connections(client):
    async with client:
        result = await client.call_tool("list_connections", {})
        text = result.content[0].text
        assert "default" in text


@pytest.mark.asyncio
async def test_test_connection(client):
    async with client:
        result = await client.call_tool("test_connection", {})
        text = result.content[0].text
        assert "successful" in text.lower() or "Connection" in text


@pytest.mark.asyncio
async def test_list_tables(client):
    async with client:
        result = await client.call_tool("list_tables", {})
        text = result.content[0].text
        assert "users" in text


@pytest.mark.asyncio
async def test_execute_query(client):
    async with client:
        result = await client.call_tool(
            "execute_query", {"query": "SELECT id, name FROM users"}
        )
        text = result.content[0].text
        assert "Alice" in text or "id" in text


@pytest.mark.asyncio
async def test_execute_query_json(client):
    async with client:
        result = await client.call_tool(
            "execute_query",
            {"query": "SELECT id, name FROM users", "format": "json"},
        )
        text = result.content[0].text
        assert '"rows"' in text


@pytest.mark.asyncio
async def test_execute_query_write_blocked(client):
    from fastmcp.exceptions import ToolError

    async with client:
        with pytest.raises(ToolError, match="read-only"):
            await client.call_tool(
                "execute_query", {"query": "DELETE FROM users"}
            )
