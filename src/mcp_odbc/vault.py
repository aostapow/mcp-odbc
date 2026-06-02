"""DPAPI credential vault for mcp-odbc.

Passwords in config.ini are stored as ``dpapi:<base64>`` tokens and decrypted
at startup using the Windows Data Protection API (DPAPI).  The encrypted blob
is tied to the current Windows user account, so it can only be decrypted on
the same machine by the same user that ran ``setup_vault.py``.

Non-Windows platforms are supported in *passthrough* mode: tokens that do NOT
start with ``dpapi:`` are returned as-is, so the server runs normally on Linux
/ macOS with plain-text passwords (useful for dev/CI).  If a ``dpapi:`` token
is encountered on a non-Windows platform an explicit error is raised.

Public API
----------
encrypt_password(plaintext: str) -> str
    Encrypt a plain-text password and return a ``dpapi:<base64>`` token.

decrypt_password(token: str) -> str
    Decrypt a ``dpapi:<base64>`` token and return the plain-text password.
    If *token* does not start with ``dpapi:``, it is returned unchanged
    (backwards-compatible with plain-text passwords).

decrypt_connection_string(conn_str: str) -> str
    Walk every ``KEY=VALUE`` segment of an ODBC connection string and decrypt
    any ``dpapi:`` tokens found in the values.
"""

from __future__ import annotations

import base64
import re
import sys

_DPAPI_PREFIX = "dpapi:"
_TOKEN_RE = re.compile(r"([^;=]+)=([^;]*)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return sys.platform == "win32"


def _win32crypt():
    """Lazy import of win32crypt — only available on Windows with pywin32."""
    try:
        import win32crypt  # type: ignore[import]
        return win32crypt
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "pywin32 is required for DPAPI vault support on Windows. "
            "Install it with: pip install pywin32"
        ) from exc


# ---------------------------------------------------------------------------
# Core encrypt / decrypt
# ---------------------------------------------------------------------------

def encrypt_password(plaintext: str) -> str:
    """Encrypt *plaintext* with DPAPI and return a ``dpapi:<base64>`` token.

    Raises
    ------
    RuntimeError
        On non-Windows platforms.
    ImportError
        If pywin32 is not installed.
    """
    if not _is_windows():
        raise RuntimeError(
            "DPAPI encryption is only available on Windows. "
            "Use plain-text passwords on non-Windows platforms."
        )
    w32 = _win32crypt()
    encrypted: bytes = w32.CryptProtectData(
        plaintext.encode("utf-8"),
        "mcp-odbc credential",   # optional description
        None,                    # optional entropy
        None,                    # reserved
        None,                    # no prompt
        0,                       # flags
    )
    return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")


def decrypt_password(token: str) -> str:
    """Decrypt a ``dpapi:<base64>`` token, or return *token* unchanged if it
    is not a vault token (plain-text passthrough).

    Raises
    ------
    RuntimeError
        If a ``dpapi:`` token is encountered on a non-Windows platform.
    ImportError
        If pywin32 is not installed.
    ValueError
        If the base64 payload is malformed or DPAPI decryption fails.
    """
    if not token.startswith(_DPAPI_PREFIX):
        return token  # plain-text passthrough

    if not _is_windows():
        raise RuntimeError(
            "A dpapi: credential token was found in the config but DPAPI "
            "decryption is only available on Windows. "
            "Re-run setup_vault.py on the target Windows machine."
        )

    w32 = _win32crypt()
    b64_payload = token[len(_DPAPI_PREFIX):]
    try:
        encrypted = base64.b64decode(b64_payload)
    except Exception as exc:
        raise ValueError(f"Malformed dpapi: token — invalid base64: {exc}") from exc

    try:
        _desc, plaintext_bytes = w32.CryptUnprotectData(
            encrypted,
            None,   # no entropy
            None,   # reserved
            None,   # no prompt
            0,      # flags
        )
    except Exception as exc:
        raise ValueError(
            "DPAPI decryption failed. The credential may have been encrypted "
            f"by a different Windows user or machine: {exc}"
        ) from exc

    return plaintext_bytes.decode("utf-8")


# ---------------------------------------------------------------------------
# Connection-string helper
# ---------------------------------------------------------------------------

def decrypt_connection_string(conn_str: str) -> str:
    """Replace any ``dpapi:`` tokens in an ODBC connection string with their
    decrypted plain-text values.

    The connection string format is ``KEY1=VALUE1;KEY2=VALUE2;...``.
    Only VALUES are inspected; KEYS are never modified.

    Examples
    --------
    >>> cs = "DRIVER={Sybase};SERVER=prod;UID=sa;PWD=dpapi:AAAA..."
    >>> decrypt_connection_string(cs)
    'DRIVER={Sybase};SERVER=prod;UID=sa;PWD=supersecret'
    """
    if _DPAPI_PREFIX not in conn_str:
        return conn_str  # fast path — nothing to decrypt

    parts: list[str] = []
    # Split on ";" but keep the delimiters so we can reconstruct faithfully.
    for segment in conn_str.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        if "=" in segment:
            key, _, value = segment.partition("=")
            decrypted_value = decrypt_password(value)
            parts.append(f"{key}={decrypted_value}")
        else:
            parts.append(segment)

    return ";".join(parts)
