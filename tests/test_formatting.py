"""Tests for output formatting — markdown tables, JSON, truncation."""

import json

from mcp_odbc.formatting import (
    MAX_VALUE_LENGTH,
    format_as_json,
    format_as_markdown,
    truncate_value,
)


class TestTruncateValue:
    def test_none_returns_empty(self):
        assert truncate_value(None) == ""

    def test_short_string_unchanged(self):
        assert truncate_value("hello") == "hello"

    def test_long_string_truncated(self):
        long_val = "x" * 600
        result = truncate_value(long_val)
        assert len(result) < 600
        assert "600 chars total" in result

    def test_custom_max_len(self):
        result = truncate_value("abcdefgh", max_len=5)
        assert result.startswith("abcde")
        assert "8 chars total" in result

    def test_non_string_converted(self):
        assert truncate_value(12345) == "12345"


class TestFormatAsMarkdown:
    def test_basic_table(self):
        result = format_as_markdown(["Name", "Age"], [("Alice", 30), ("Bob", 25)])
        assert "| Name | Age |" in result
        assert "| Alice | 30 |" in result
        assert "| Bob | 25 |" in result

    def test_empty_columns(self):
        assert "*No results.*" in format_as_markdown([], [])

    def test_no_rows(self):
        result = format_as_markdown(["A"], [])
        assert "*No rows returned.*" in result

    def test_has_more_flag(self):
        result = format_as_markdown(["A"], [("x",)], has_more=True)
        assert "truncated" in result.lower()

    def test_none_values(self):
        result = format_as_markdown(["A"], [(None,)])
        # None should render as empty string
        assert "| |" in result or "|  |" in result

    def test_pipe_escaped(self):
        result = format_as_markdown(["Col"], [("val|ue",)])
        assert "\\|" in result

    def test_truncation_in_table(self):
        long_val = "x" * 600
        result = format_as_markdown(["Col"], [(long_val,)])
        assert "chars total" in result


class TestFormatAsJson:
    def test_basic(self):
        result = format_as_json(["name", "age"], [("Alice", 30)])
        data = json.loads(result)
        assert data["row_count"] == 1
        assert data["rows"][0]["name"] == "Alice"
        assert data["has_more"] is False

    def test_has_more(self):
        result = format_as_json(["a"], [("x",)], has_more=True)
        data = json.loads(result)
        assert data["has_more"] is True

    def test_empty(self):
        result = format_as_json(["a"], [])
        data = json.loads(result)
        assert data["row_count"] == 0
        assert data["rows"] == []
