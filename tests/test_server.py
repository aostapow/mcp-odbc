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
async def test_list_tables_with_name_pattern(client, setup_manager):
    mock_cursor = setup_manager["cursor"]
    async with client:
        result = await client.call_tool(
            "list_tables", {"name_pattern": "%user%"}
        )
        text = result.content[0].text
        assert "users" in text
        # Verify the pattern was passed through to cursor.tables()
        mock_cursor.tables.assert_called()
        call_kwargs = mock_cursor.tables.call_args
        assert call_kwargs[1].get("table") == "%user%"


@pytest.mark.asyncio
async def test_describe_table_columns_only(client, setup_manager):
    """Default include='columns' should not call primaryKeys or foreignKeys."""
    mock_cursor = setup_manager["cursor"]
    # Set up column results
    mock_cursor.columns.return_value = None
    mock_cursor.description = [
        ("column_name",), ("type_name",), ("column_size",), ("nullable",), ("remarks",),
    ]
    mock_cursor.fetchall.return_value = [
        MagicMock(column_name="id", type_name="INTEGER", column_size=10, nullable=0, remarks=""),
    ]
    mock_cursor.primaryKeys.reset_mock()
    mock_cursor.foreignKeys.reset_mock()

    async with client:
        result = await client.call_tool("describe_table", {"table": "users"})
        text = result.content[0].text
        assert "Columns" in text
        assert "Primary Keys" not in text
        assert "Foreign Keys" not in text
        mock_cursor.primaryKeys.assert_not_called()
        mock_cursor.foreignKeys.assert_not_called()


@pytest.mark.asyncio
async def test_describe_table_all(client, setup_manager):
    """include='all' should return columns + PKs + FKs."""
    mock_cursor = setup_manager["cursor"]
    # Columns
    mock_cursor.columns.return_value = None
    mock_cursor.description = [
        ("column_name",), ("type_name",), ("column_size",), ("nullable",), ("remarks",),
    ]
    mock_cursor.fetchall.return_value = [
        MagicMock(column_name="id", type_name="INTEGER", column_size=10, nullable=0, remarks=""),
    ]
    # PKs — set up description and fetchall for primaryKeys call
    pk_desc = [("table_cat",), ("table_schem",), ("table_name",), ("column_name",), ("key_seq",), ("pk_name",)]
    pk_rows = [MagicMock(**{d[0]: f"pk_{d[0]}" for d in pk_desc})]
    # FKs
    fk_desc = [("pktable_name",), ("pkcolumn_name",), ("fktable_name",), ("fkcolumn_name",)]
    fk_rows = [MagicMock(**{d[0]: f"fk_{d[0]}" for d in fk_desc})]

    # We need description to alternate per cursor call. Use side_effect on the property.
    call_count = {"n": 0}
    descs = [
        # get_columns calls cursor.columns(), then cursor.description, then fetchall
        [("column_name",), ("type_name",), ("column_size",), ("nullable",), ("remarks",)],
        # get_primary_keys calls cursor.primaryKeys(), then cursor.description, then fetchall
        pk_desc,
        # get_foreign_keys calls cursor.foreignKeys(), then cursor.description, then fetchall
        fk_desc,
    ]
    fetchall_results = [
        [MagicMock(column_name="id", type_name="INTEGER", column_size=10, nullable=0, remarks="")],
        pk_rows,
        fk_rows,
    ]

    type(mock_cursor).description = property(
        lambda self: descs[call_count["n"]]
    )
    original_fetchall = mock_cursor.fetchall
    def rotating_fetchall():
        idx = call_count["n"]
        call_count["n"] += 1
        return fetchall_results[idx]
    mock_cursor.fetchall = rotating_fetchall

    async with client:
        result = await client.call_tool(
            "describe_table", {"table": "users", "include": "all"}
        )
        text = result.content[0].text
        assert "Columns" in text
        assert "Primary Keys" in text
        assert "Foreign Keys" in text

    # Restore mock
    mock_cursor.fetchall = original_fetchall
    type(mock_cursor).description = property(lambda self: [
        ("id", None, None, None, None, None, None),
        ("name", None, None, None, None, None, None),
    ])


@pytest.mark.asyncio
async def test_describe_table_selective_fks(client, setup_manager):
    """include='columns,fks' should fetch columns + FKs but not PKs."""
    mock_cursor = setup_manager["cursor"]
    # Columns
    col_desc = [("column_name",), ("type_name",), ("column_size",), ("nullable",), ("remarks",)]
    col_rows = [MagicMock(column_name="id", type_name="INTEGER", column_size=10, nullable=0, remarks="")]
    # FKs
    fk_desc = [("pktable_name",), ("pkcolumn_name",), ("fktable_name",), ("fkcolumn_name",)]
    fk_rows = [MagicMock(**{d[0]: f"fk_{d[0]}" for d in fk_desc})]

    call_count = {"n": 0}
    descs = [col_desc, fk_desc]
    fetchall_results = [col_rows, fk_rows]

    type(mock_cursor).description = property(
        lambda self: descs[call_count["n"]]
    )
    def rotating_fetchall():
        idx = call_count["n"]
        call_count["n"] += 1
        return fetchall_results[idx]
    mock_cursor.fetchall = rotating_fetchall
    mock_cursor.primaryKeys.reset_mock()

    async with client:
        result = await client.call_tool(
            "describe_table", {"table": "users", "include": "columns,fks"}
        )
        text = result.content[0].text
        assert "Columns" in text
        assert "Primary Keys" not in text
        assert "Foreign Keys" in text
        mock_cursor.primaryKeys.assert_not_called()

    # Restore mock
    type(mock_cursor).description = property(lambda self: [
        ("id", None, None, None, None, None, None),
        ("name", None, None, None, None, None, None),
    ])


@pytest.mark.asyncio
async def test_execute_query_write_blocked(client):
    from fastmcp.exceptions import ToolError

    async with client:
        with pytest.raises(ToolError, match="read-only"):
            await client.call_tool(
                "execute_query", {"query": "DELETE FROM users"}
            )
