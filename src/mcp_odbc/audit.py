"""Query audit log — rotating file log for all SQL executions.

Each entry is a single JSON line containing:
    ts          ISO-8601 timestamp (UTC)
    connection  connection name
    query_hash  SHA-256 of the normalized SQL (first 16 hex chars)
    rows        number of rows returned (-1 if error / no result set)
    duration_ms wall-clock milliseconds for the query
    truncated   whether the result was capped at max_rows
    error       sanitized error message, or null on success

The log is managed by Python's RotatingFileHandler:
    default location : logs/mcp_odbc_audit.log
    max size         : 10 MB per file
    backups          : 5 rotated files kept

Override via environment variables:
    ODBC_AUDIT_LOG      absolute or relative path to the log file
    ODBC_AUDIT_MAX_MB   max MB per file (default 10)
    ODBC_AUDIT_BACKUPS  number of backup files to keep (default 5)
    ODBC_AUDIT_DISABLE  set to "1" / "true" to silence the audit log

Usage
-----
    from mcp_odbc.audit import audit_query, AuditContext

    with AuditContext(connection="soc1", sql=sql) as ctx:
        rows = cursor.fetchmany(max_rows + 1)
        ctx.record(rows=len(rows), truncated=has_more)
    # On exception the context records rows=-1 and the sanitized error.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Generator

# ---------------------------------------------------------------------------
# Configuration from env vars
# ---------------------------------------------------------------------------

_DISABLED = os.environ.get("ODBC_AUDIT_DISABLE", "").lower() in ("1", "true", "yes")
_LOG_PATH = os.environ.get("ODBC_AUDIT_LOG", "logs/mcp_odbc_audit.log")
_MAX_BYTES = int(os.environ.get("ODBC_AUDIT_MAX_MB", "10")) * 1024 * 1024
_BACKUP_COUNT = int(os.environ.get("ODBC_AUDIT_BACKUPS", "5"))

# ---------------------------------------------------------------------------
# Logger setup (lazy — only created on first use)
# ---------------------------------------------------------------------------

_audit_logger: logging.Logger | None = None


def _get_logger() -> logging.Logger | None:
    """Return (and lazily initialize) the audit logger. Returns None if disabled."""
    global _audit_logger
    if _DISABLED:
        return None
    if _audit_logger is not None:
        return _audit_logger

    log_path = Path(_LOG_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("mcp_odbc.audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # don't bubble up to root logger

    handler = RotatingFileHandler(
        str(log_path),
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    _audit_logger = logger
    return _audit_logger


# ---------------------------------------------------------------------------
# SQL normalization helpers
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_sql(sql: str) -> str:
    """Collapse whitespace for stable hashing."""
    return _WHITESPACE_RE.sub(" ", sql.strip()).upper()


def _query_hash(sql: str) -> str:
    """Return the first 16 hex chars of SHA-256 of the normalized SQL."""
    normalized = _normalize_sql(sql)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Low-level write
# ---------------------------------------------------------------------------

def _write_entry(entry: dict) -> None:
    logger = _get_logger()
    if logger is None:
        return
    try:
        logger.info(json.dumps(entry, ensure_ascii=False))
    except Exception:
        pass  # Audit failure must never crash the server


def audit_query(
    *,
    connection: str,
    sql: str,
    rows: int,
    duration_ms: float,
    truncated: bool = False,
    error: str | None = None,
) -> None:
    """Write a single audit entry.

    Parameters
    ----------
    connection:   logical connection name from config.ini
    sql:          the SQL that was executed (only its hash is stored)
    rows:         number of rows returned; -1 on error
    duration_ms:  wall-clock milliseconds
    truncated:    True when the result was capped at max_rows
    error:        sanitized error message or None on success
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "connection": connection,
        "query_hash": _query_hash(sql),
        "rows": rows,
        "duration_ms": round(duration_ms, 2),
        "truncated": truncated,
        "error": error,
    }
    _write_entry(entry)


# ---------------------------------------------------------------------------
# Context-manager helper
# ---------------------------------------------------------------------------

class AuditContext:
    """Context manager that records an audit entry on exit.

    Usage::

        with AuditContext(connection="soc1", sql=sql) as ctx:
            rows = cursor.fetchmany(max_rows + 1)
            ctx.record(rows=len(rows), truncated=len(rows) > max_rows)

    If the block raises, ``rows=-1`` and the sanitized exception message are
    logged automatically.
    """

    def __init__(self, connection: str, sql: str) -> None:
        self.connection = connection
        self.sql = sql
        self._start: float = 0.0
        self._rows: int = -1
        self._truncated: bool = False
        self._error: str | None = None
        self._recorded: bool = False

    def __enter__(self) -> "AuditContext":
        self._start = time.perf_counter()
        return self

    def record(self, *, rows: int, truncated: bool = False) -> None:
        """Call this inside the with-block once you have the result."""
        self._rows = rows
        self._truncated = truncated
        self._recorded = True

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        duration_ms = (time.perf_counter() - self._start) * 1000

        if exc_val is not None:
            # Import lazily to avoid circular deps
            from mcp_odbc.errors import sanitize_exception
            self._error = sanitize_exception(exc_val)
            self._rows = -1

        audit_query(
            connection=self.connection,
            sql=self.sql,
            rows=self._rows,
            duration_ms=duration_ms,
            truncated=self._truncated,
            error=self._error,
        )
        return False  # don't suppress exceptions
