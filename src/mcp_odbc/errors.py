"""Error handling, SQLSTATE mapping, and credential/server sanitization.

Sanitization rules (applied before any message reaches the LLM):
- PWD / PASSWORD values → ***
- UID / USER values → ***
- SERVER / SERVERNAME values → ***
- DATABASE / DB values → ***
- Full stack traces (Traceback …) → single opaque line
- pyodbc native-error noise (driver manager paths, line numbers) → stripped
"""

from __future__ import annotations

import re
import traceback

from fastmcp.exceptions import ToolError

# ---------------------------------------------------------------------------
# SQLSTATE catalogue
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Sanitization patterns
# ---------------------------------------------------------------------------

# Credential and server tokens — KEY=VALUE form in ODBC connection strings
_SENSITIVE_KV_RE = re.compile(
    r"(?P<key>PWD|PASSWORD|UID|USER|SERVER|SERVERNAME|DATABASE|DB|ADDR|ADDRESS)"
    r"(?P<sep>\s*=\s*)"
    r"(?P<value>[^;{}\r\n]*)",
    re.IGNORECASE,
)

# Named-param form: PWD='value' or PWD="value"
_SENSITIVE_QUOTED_RE = re.compile(
    r"(?P<key>PWD|PASSWORD|UID|USER|SERVER|DATABASE|DB)"
    r"(?P<sep>\s*[=:]\s*)"
    r"(?P<q>['\"])(?P<value>.*?)(?P=q)",
    re.IGNORECASE,
)

# Stack trace header — anything from "Traceback (most recent call last):"
# through to the final "ExceptionType: message" line
_TRACEBACK_RE = re.compile(
    r"Traceback \(most recent call last\):.*",
    re.DOTALL,
)

# pyodbc adds "[Microsoft][ODBC Driver Manager] ... " prefixes
_DRIVER_MANAGER_RE = re.compile(
    r"\[[\w\s]+\]\s*\[[\w\s]+\]\s*",
)

# File/line noise like "(pyodbc.py, line 42)"
_FILE_LINE_RE = re.compile(
    r"\(\s*[\w/\\. ]+\.py\s*,\s*line\s*\d+\s*\)"
)


def sanitize_error_message(msg: str) -> str:
    """Strip sensitive connection details and noisy internals from *msg*.

    Applied in order:
    1. Remove full stack traces
    2. Mask sensitive KEY=VALUE pairs
    3. Strip driver-manager prefix noise
    4. Strip file/line references
    """
    # 1. Collapse stack traces
    msg = _TRACEBACK_RE.sub("[internal error — details hidden]", msg)

    # 2. Mask sensitive key=value (quoted form first, then plain)
    msg = _SENSITIVE_QUOTED_RE.sub(r"\g<key>\g<sep>\g<q>***\g<q>", msg)
    msg = _SENSITIVE_KV_RE.sub(r"\g<key>\g<sep>***", msg)

    # 3. Strip [Driver Manager] prefixes
    msg = _DRIVER_MANAGER_RE.sub("", msg)

    # 4. Strip file/line noise
    msg = _FILE_LINE_RE.sub("", msg)

    return msg.strip()


def sanitize_exception(exc: BaseException) -> str:
    """Return a sanitized one-line summary of an exception.

    Never includes a stack trace or raw connection parameters.
    """
    return sanitize_error_message(str(exc))


# ---------------------------------------------------------------------------
# ODBC error → ToolError
# ---------------------------------------------------------------------------

def handle_odbc_error(error: Exception) -> ToolError:
    """Extract SQLSTATE + message from a pyodbc.Error, sanitize, return ToolError."""
    sqlstate = error.args[0] if error.args else "unknown"
    raw_message = error.args[1] if len(error.args) > 1 else str(error)

    message = sanitize_error_message(raw_message)

    template = SQLSTATE_MAP.get(sqlstate, "ODBC error ({sqlstate}): {message}")
    user_msg = template.format(sqlstate=sqlstate, message=message)
    return ToolError(user_msg)


def handle_unexpected_error(error: Exception) -> ToolError:
    """Wrap a non-ODBC exception as a sanitized ToolError.

    Use for catching broad Exception blocks where you want to avoid leaking
    internals to the LLM.
    """
    sanitized = sanitize_exception(error)
    return ToolError(f"Unexpected error: {sanitized}")


def safe_traceback(error: Exception) -> str:
    """Return a sanitized traceback string suitable for *server-side* logging only.

    Do NOT send this to the LLM — use it only in log files.
    """
    raw = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    return sanitize_error_message(raw)
