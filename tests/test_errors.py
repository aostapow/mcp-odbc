"""Tests for error handling, sanitization, SQLSTATE mapping."""

from fastmcp.exceptions import ToolError

from mcp_odbc.errors import handle_odbc_error, sanitize_error_message


class TestSanitizeErrorMessage:
    def test_strips_pwd(self):
        msg = "Connection failed; PWD=supersecret; SERVER=host"
        result = sanitize_error_message(msg)
        assert "supersecret" not in result
        assert "PWD=***" in result
        assert "SERVER=host" in result

    def test_strips_password(self):
        msg = "Error password=mysecret123;UID=user"
        result = sanitize_error_message(msg)
        assert "mysecret123" not in result
        assert "password=***" in result
        assert "UID=user" in result

    def test_case_insensitive(self):
        msg = "Error Pwd=SECRET;server=x"
        result = sanitize_error_message(msg)
        assert "SECRET" not in result

    def test_no_credentials_unchanged(self):
        msg = "Table not found"
        assert sanitize_error_message(msg) == msg


class TestHandleOdbcError:
    def test_known_sqlstate(self):
        exc = Exception("42S02", "Table 'foo' not found")
        error = handle_odbc_error(exc)
        assert isinstance(error, ToolError)
        assert "Table not found" in str(error)

    def test_unknown_sqlstate(self):
        exc = Exception("ZZZZZ", "Something weird")
        error = handle_odbc_error(exc)
        assert isinstance(error, ToolError)
        assert "ODBC error" in str(error)

    def test_sanitizes_credentials_in_error(self):
        exc = Exception("08001", "Cannot connect; PWD=secret123")
        error = handle_odbc_error(exc)
        assert "secret123" not in str(error)

    def test_empty_args(self):
        exc = Exception()
        error = handle_odbc_error(exc)
        assert isinstance(error, ToolError)
