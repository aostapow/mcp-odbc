"""Shared fixtures — mock pyodbc objects and test configs."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from mcp_odbc.config import ConnectionConfig, ServerConfig


# ---------------------------------------------------------------------------
# Test ServerConfig
# ---------------------------------------------------------------------------


@pytest.fixture
def test_config():
    """Minimal ServerConfig for unit tests."""
    return ServerConfig(
        default_connection="test",
        connections={
            "test": ConnectionConfig(
                connection_string="DSN=TestDSN",
                readonly=True,
                query_timeout=30,
                connect_timeout=10,
                max_rows=1000,
            ),
            "writable": ConnectionConfig(
                connection_string="DSN=WritableDSN",
                readonly=False,
                query_timeout=60,
                connect_timeout=5,
                max_rows=5000,
            ),
        },
    )


# ---------------------------------------------------------------------------
# Mock pyodbc objects
# ---------------------------------------------------------------------------


class MockRow:
    """Simulates a pyodbc Row with attribute access."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def mock_cursor():
    """A mock cursor with common catalog methods."""
    cursor = MagicMock()
    cursor.description = [
        ("col1", None, None, None, None, None, None),
        ("col2", None, None, None, None, None, None),
    ]
    cursor.fetchall.return_value = [("val1", "val2"), ("val3", "val4")]
    cursor.fetchmany.return_value = [("val1", "val2"), ("val3", "val4")]
    cursor.close.return_value = None
    return cursor


@pytest.fixture
def mock_connection(mock_cursor):
    """A mock pyodbc.Connection."""
    conn = MagicMock()
    conn.cursor.return_value = mock_cursor
    conn.execute.return_value = mock_cursor
    conn.getinfo.side_effect = lambda attr: {
        17: "TestDBMS",  # SQL_DBMS_NAME
        18: "1.0.0",  # SQL_DBMS_VER
        6: "testdriver.dll",  # SQL_DRIVER_NAME
    }.get(attr, "unknown")
    conn.timeout = 30
    return conn
