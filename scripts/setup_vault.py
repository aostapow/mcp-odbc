#!/usr/bin/env python
"""setup_vault.py — Encrypt plain-text passwords in config/config.ini using Windows DPAPI.

Usage
-----
    python scripts/setup_vault.py [--config PATH] [--dry-run]

What it does
------------
1. Reads the INI file (default: config/config.ini).
2. Scans every connection section for a ``connection_string`` that contains a
   plain ``PWD=<value>`` segment (i.e., a value that does NOT already start
   with ``dpapi:``).
3. Encrypts each found password with Windows DPAPI via
   :func:`mcp_odbc.vault.encrypt_password`.
4. Rewrites the INI file with ``PWD=dpapi:<base64>`` tokens in place of the
   plain-text passwords.

The script is idempotent: already-encrypted tokens (``dpapi:...``) are left
unchanged.

Options
-------
--config PATH   Path to the INI file.  Defaults to ``config/config.ini``.
--dry-run       Show what would change without writing anything.
--section NAME  Process only the named section (can be repeated).
"""

from __future__ import annotations

import argparse
import configparser
import re
import sys
from pathlib import Path

# Make the script runnable both as ``python scripts/setup_vault.py`` from the
# repo root and as an installed entry-point.
try:
    from mcp_odbc.vault import encrypt_password
except ImportError:
    # Fallback: add src/ to sys.path when running from the repo root without
    # the package installed.
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from mcp_odbc.vault import encrypt_password  # type: ignore[no-redef]

_PWD_RE = re.compile(r"(PWD=)([^;]*)", re.IGNORECASE)
_DPAPI_PREFIX = "dpapi:"


def _encrypt_conn_str(conn_str: str) -> tuple[str, list[str]]:
    """Encrypt plain PWD values in *conn_str*.

    Returns the (possibly modified) connection string and a list of human-
    readable change descriptions.
    """
    changes: list[str] = []

    def replacer(m: re.Match) -> str:  # type: ignore[type-arg]
        key_eq = m.group(1)   # "PWD=" (original casing preserved)
        value = m.group(2)
        if value.startswith(_DPAPI_PREFIX):
            return m.group(0)  # already encrypted
        if not value:
            return m.group(0)  # empty password — skip
        encrypted = encrypt_password(value)
        changes.append(f"PWD=<plain> → PWD=dpapi:<encrypted>")
        return f"{key_eq}{encrypted}"

    new_conn_str = _PWD_RE.sub(replacer, conn_str)
    return new_conn_str, changes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Encrypt plain-text passwords in config.ini using Windows DPAPI."
    )
    parser.add_argument(
        "--config",
        default="config/config.ini",
        help="Path to the INI config file (default: config/config.ini)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing the file.",
    )
    parser.add_argument(
        "--section",
        action="append",
        dest="sections",
        metavar="NAME",
        help="Process only this section (can be repeated; default: all sections).",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = configparser.RawConfigParser()
    config.optionxform = str  # preserve key casing
    config.read(str(config_path))

    target_sections = set(args.sections) if args.sections else None
    total_changes = 0

    for section in config.sections():
        if section == "server":
            continue
        if target_sections and section not in target_sections:
            continue
        if not config.has_option(section, "connection_string"):
            continue

        raw = config.get(section, "connection_string")
        new_conn_str, changes = _encrypt_conn_str(raw)

        if changes:
            total_changes += len(changes)
            if args.dry_run:
                print(f"[DRY-RUN] [{section}] {'; '.join(changes)}")
            else:
                config.set(section, "connection_string", new_conn_str)
                print(f"[OK] [{section}] {'; '.join(changes)}")
        else:
            print(f"[SKIP] [{section}] No plain-text PWD found (already encrypted or absent).")

    if args.dry_run:
        print(f"\n{total_changes} change(s) would be made (dry-run — file not modified).")
        return

    if total_changes == 0:
        print("Nothing to do.")
        return

    # Write the modified INI back to disk, preserving comments as best we can.
    # configparser does not preserve comments, so we warn the user.
    print(
        "\n[WARNING] configparser does not preserve INI comments. "
        "Any comments in the file will be lost."
    )
    with config_path.open("w", encoding="utf-8") as fh:
        config.write(fh)
    print(f"[DONE] Wrote {total_changes} encrypted password(s) to {config_path}")


if __name__ == "__main__":
    main()
