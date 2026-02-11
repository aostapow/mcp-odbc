"""Output formatting — markdown tables, JSON, value truncation."""

import json

MAX_VALUE_LENGTH = 500


def truncate_value(val, max_len: int = MAX_VALUE_LENGTH):
    """Truncate long values, appending total char count."""
    if val is None:
        return ""
    s = str(val)
    if len(s) > max_len:
        return s[:max_len] + f"... ({len(s)} chars total)"
    return s


def _escape_pipe(val: str) -> str:
    """Escape pipe characters for markdown tables."""
    return val.replace("|", "\\|")


def format_as_markdown(
    columns: list[str],
    rows: list[tuple | list],
    has_more: bool = False,
) -> str:
    """Build a markdown table from columns and rows.

    Args:
        columns: Column header names.
        rows: List of row tuples/lists.
        has_more: Whether more rows exist beyond what was fetched.

    Returns:
        Markdown-formatted table string.
    """
    if not columns:
        return "*No results.*"

    header = "| " + " | ".join(_escape_pipe(str(c)) for c in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"

    lines = [header, separator]
    for row in rows:
        values = [_escape_pipe(truncate_value(v)) for v in row]
        lines.append("| " + " | ".join(values) + " |")

    if not rows:
        lines.append("\n*No rows returned.*")
    elif has_more:
        lines.append(f"\n*Results truncated. More rows available.*")

    return "\n".join(lines)


def format_as_json(
    columns: list[str],
    rows: list[tuple | list],
    has_more: bool = False,
) -> str:
    """Format query results as JSON.

    Args:
        columns: Column header names.
        rows: List of row tuples/lists.
        has_more: Whether more rows exist beyond what was fetched.

    Returns:
        JSON string with rows as list of dicts.
    """
    data = [dict(zip(columns, row)) for row in rows]
    result = {
        "columns": columns,
        "rows": data,
        "row_count": len(rows),
        "has_more": has_more,
    }
    return json.dumps(result, default=str, indent=2)
