"""Error handling, SQLSTATE mapping, and credential sanitization."""

import re

from fastmcp.exceptions import ToolError

SQLSTATE_MAP = {
    "08001": "Cannot connect to server. Check host/port and network.",
    "08S01": "Connection lost during operation. Try again.",
    "28000": "Authentication failed. Check credentials.",
    "42000": "SQL syntax error or access denied.",
    "42S02": "Table not found.",
    "HY000": "Driver error: {message}",
    "HYT00": "Query timed out.",
    "HYT01": "Connection timed out.",
    "HYC00": "Feature not supported by this driver.",
    "IM002": "Data source not found. Check DSN configuration.",
}

_CREDENTIAL_RE = re.compile(
    r"(PWD|PASSWORD|pwd|password)\s*=\s*[^;]*",
    re.IGNORECASE,
)


def sanitize_error_message(msg: str) -> str:
    """Strip PWD/PASSWORD values from error strings."""
    return _CREDENTIAL_RE.sub(r"\1=***", msg)


def handle_odbc_error(error: Exception) -> ToolError:
    """Extract SQLSTATE + message from pyodbc.Error, sanitize, return ToolError."""
    sqlstate = error.args[0] if error.args else "unknown"
    message = error.args[1] if len(error.args) > 1 else str(error)

    message = sanitize_error_message(message)

    template = SQLSTATE_MAP.get(sqlstate, "ODBC error ({sqlstate}): {message}")
    user_msg = template.format(sqlstate=sqlstate, message=message)
    return ToolError(user_msg)
