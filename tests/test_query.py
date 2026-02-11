"""Tests for query validation — comment stripping, readonly enforcement."""

import pytest
from fastmcp.exceptions import ToolError

from mcp_odbc.query import strip_sql_comments, validate_readonly


class TestStripSqlComments:
    def test_line_comment(self):
        sql = "SELECT 1 -- this is a comment"
        assert strip_sql_comments(sql) == "SELECT 1"

    def test_block_comment(self):
        sql = "SELECT /* inline */ 1"
        assert strip_sql_comments(sql) == "SELECT  1"

    def test_multiline_block_comment(self):
        sql = "SELECT\n/* line1\nline2 */\n1"
        result = strip_sql_comments(sql)
        assert "/*" not in result
        assert "*/" not in result

    def test_no_comments(self):
        sql = "SELECT col FROM table WHERE id = 1"
        assert strip_sql_comments(sql) == sql

    def test_empty_after_stripping(self):
        sql = "-- just a comment"
        assert strip_sql_comments(sql) == ""


class TestValidateReadonly:
    def test_select_allowed(self):
        validate_readonly("SELECT * FROM users")

    def test_with_cte_allowed(self):
        validate_readonly("WITH cte AS (SELECT 1) SELECT * FROM cte")

    def test_with_cte_disallowed_when_no_support(self):
        with pytest.raises(ToolError):
            validate_readonly("WITH cte AS (SELECT 1) SELECT * FROM cte", supports_cte=False)

    def test_insert_blocked(self):
        with pytest.raises(ToolError, match="INSERT"):
            validate_readonly("INSERT INTO users VALUES (1)")

    def test_update_blocked(self):
        with pytest.raises(ToolError, match="UPDATE"):
            validate_readonly("UPDATE users SET name = 'x'")

    def test_delete_blocked(self):
        with pytest.raises(ToolError, match="DELETE"):
            validate_readonly("DELETE FROM users")

    def test_drop_blocked(self):
        with pytest.raises(ToolError, match="DROP"):
            validate_readonly("DROP TABLE users")

    def test_create_blocked(self):
        with pytest.raises(ToolError, match="CREATE"):
            validate_readonly("CREATE TABLE foo (id INT)")

    def test_truncate_blocked(self):
        with pytest.raises(ToolError, match="TRUNCATE"):
            validate_readonly("TRUNCATE TABLE users")

    def test_exec_blocked(self):
        with pytest.raises(ToolError, match="EXEC"):
            validate_readonly("EXEC sp_help")

    def test_comment_hiding_blocked(self):
        """Write keyword hidden in comment is stripped first."""
        with pytest.raises(ToolError):
            validate_readonly("-- SELECT\nINSERT INTO t VALUES (1)")

    def test_empty_query(self):
        with pytest.raises(ToolError, match="Empty"):
            validate_readonly("")

    def test_case_insensitive(self):
        validate_readonly("select * from users")

    def test_select_with_subquery_containing_keyword(self):
        # SELECT that mentions DELETE in a string literal — we accept false
        # positives here for safety; the ODBC readonly flag is the real guard
        with pytest.raises(ToolError):
            validate_readonly("SELECT * FROM t WHERE status = DELETE")
