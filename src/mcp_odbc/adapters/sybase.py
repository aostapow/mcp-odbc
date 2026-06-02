"""SybaseAdapter — metadata adapter for Sybase ASE 16 (COBIS bancario).

Uses native system tables instead of ODBC catalog functions, which are
unreliable or unsupported on the Adaptive Server ODBC driver:

    sysobjects   — tables, views, stored procedures
    syscolumns   — column definitions + types
    systypes     — user and system type names
    sysindexes   — indexes (used to infer primary keys when no constraint exists)
    sysreferences — referential integrity / foreign keys

Detection
---------
SQL_DBMS_NAME returned by the Adaptive Server ODBC driver contains
"Adaptive Server" (ASE) or "Sybase" in older drivers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp_odbc.adapters.base import SystemAdapter

if TYPE_CHECKING:
    import pyodbc


# ---------------------------------------------------------------------------
# Sybase type-id → type-name lookup (abridged; covers all COBIS-relevant types)
# ---------------------------------------------------------------------------

_SYBASE_TYPES: dict[int, str] = {
    # Exact numeric
    48: "tinyint",
    52: "smallint",
    56: "int",
    63: "numeric",
    108: "numeric",  # decimal alias
    110: "money",
    122: "smallmoney",
    # Approximate numeric
    59: "real",
    62: "float",
    # Date / time
    58: "smalldatetime",
    61: "datetime",
    # Character
    39: "varchar",
    47: "char",
    35: "text",
    # Binary
    34: "image",
    45: "binary",
    37: "varbinary",
    # Other
    55: "bit",
    4: "int",       # int4
    6: "float",     # float8
    10: "varchar",  # nvarchar mapped
    11: "char",     # nchar mapped
}


def _type_name(type_id: int, user_type_name: str | None) -> str:
    """Return a human-readable type name."""
    if user_type_name:
        return user_type_name
    return _SYBASE_TYPES.get(type_id, f"type_{type_id}")


class SybaseAdapter(SystemAdapter):
    """Metadata adapter for Sybase ASE 16."""

    name = "sybase"
    display_name = "Sybase ASE 16"

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect(connection: pyodbc.Connection) -> bool:
        """Match Adaptive Server / Sybase SQL Anywhere ODBC drivers."""
        try:
            import pyodbc as _pyodbc
            dbms = connection.getinfo(_pyodbc.SQL_DBMS_NAME) or ""
            return "adaptive server" in dbms.lower() or "sybase" in dbms.lower()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Connection settings
    # ------------------------------------------------------------------

    def apply_connection_settings(self, connection: pyodbc.Connection) -> None:
        """Set character set to UTF-8 compatible; disable implicit transactions."""
        try:
            connection.execute("SET CHAR_CONVERT OFF")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Tables
    # ------------------------------------------------------------------

    def get_tables(
        self,
        cursor: pyodbc.Cursor,
        schema: str | None = None,
        table_type: str | None = None,
        name_pattern: str | None = None,
    ) -> list[dict]:
        """List tables and views from sysobjects.

        type codes:
            'U'  — user table
            'V'  — view
            'P'  — stored procedure (excluded unless type_filter includes 'PROCEDURE')
        """
        # Determine which sysobjects.type codes to include
        type_filter = _resolve_type_filter(table_type)

        params: list = list(type_filter)
        placeholders = ",".join("?" * len(type_filter))

        sql = f"""
            SELECT
                o.name          AS table_name,
                u.name          AS table_owner,
                CASE o.type
                    WHEN 'U' THEN 'TABLE'
                    WHEN 'V' THEN 'VIEW'
                    WHEN 'P' THEN 'PROCEDURE'
                    ELSE o.type
                END             AS table_type,
                o.crdate        AS create_date
            FROM sysobjects o
            JOIN sysusers   u ON u.uid = o.uid
            WHERE o.type IN ({placeholders})
        """

        if schema:
            sql += " AND u.name = ?"
            params.append(schema)

        if name_pattern:
            sql += " AND o.name LIKE ?"
            params.append(name_pattern)

        sql += " ORDER BY u.name, o.name"

        cursor.execute(sql, params)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    def get_columns(
        self,
        cursor: pyodbc.Cursor,
        table: str,
        schema: str | None = None,
    ) -> list[dict]:
        """Return column definitions from syscolumns + systypes."""
        params: list = [table]
        schema_clause = ""
        if schema:
            schema_clause = "AND u.name = ?"
            params.append(schema)

        sql = f"""
            SELECT
                c.name              AS column_name,
                c.colid             AS ordinal_position,
                t.name              AS type_name,
                c.length            AS max_length,
                c.prec              AS numeric_precision,
                c.scale             AS numeric_scale,
                CASE
                    WHEN (c.status & 8) = 8 THEN 'YES'
                    ELSE 'NO'
                END                 AS is_nullable,
                CASE
                    WHEN (c.status & 128) = 128 THEN 'YES'
                    ELSE 'NO'
                END                 AS has_default,
                c.usertype          AS user_type_id
            FROM syscolumns c
            JOIN sysobjects o ON o.id   = c.id
            JOIN systypes   t ON t.usertype = c.usertype
            JOIN sysusers   u ON u.uid  = o.uid
            WHERE o.name = ?
              {schema_clause}
            ORDER BY c.colid
        """

        cursor.execute(sql, params)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Primary keys
    # ------------------------------------------------------------------

    def get_primary_keys(
        self,
        cursor: pyodbc.Cursor,
        table: str,
        schema: str | None = None,
    ) -> list[dict]:
        """Derive primary keys from sysindexes (index with status 0x0800 = clustered PK).

        ASE stores PK info in sysindexes.keycnt / sysindexes.keys* columns.
        This query returns one row per key column.
        """
        params: list = [table]
        schema_clause = ""
        if schema:
            schema_clause = "AND u.name = ?"
            params.append(schema)

        # sysindexes.status bit 0x0800 = primary key index
        sql = f"""
            SELECT
                o.name          AS table_name,
                u.name          AS table_owner,
                c.name          AS column_name,
                i.name          AS pk_name,
                index_col(o.name, i.indid, colnum.n) AS key_col
            FROM sysobjects o
            JOIN sysusers   u ON u.uid  = o.uid
            JOIN sysindexes i ON i.id   = o.id
                              AND (i.status & 0x0800) = 0x0800
            JOIN syscolumns c ON c.id   = o.id
                              AND c.name = index_col(o.name, i.indid, 1)
            -- generate series 1..keycnt via a small cross join trick
            ,  (SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3
                UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6
                UNION ALL SELECT 7 UNION ALL SELECT 8) AS colnum
            WHERE o.name = ?
              {schema_clause}
              AND colnum.n <= i.keycnt
              AND index_col(o.name, i.indid, colnum.n) IS NOT NULL
            ORDER BY colnum.n
        """

        try:
            cursor.execute(sql, params)
            columns = [d[0] for d in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if rows:
                return rows
        except Exception:
            pass  # Fall through to ODBC catalog fallback

        # Fallback: ODBC catalog function
        try:
            cursor.primaryKeys(table=table, schema=schema)
            desc = cursor.description
            if desc:
                return [
                    {d[0]: getattr(r, d[0], None) for d in desc}
                    for r in cursor.fetchall()
                ]
        except Exception:
            pass

        return []

    # ------------------------------------------------------------------
    # Foreign keys
    # ------------------------------------------------------------------

    def get_foreign_keys(
        self,
        cursor: pyodbc.Cursor,
        table: str,
        schema: str | None = None,
    ) -> list[dict]:
        """Return foreign key relationships from sysreferences + sysobjects."""
        params: list = [table]
        schema_clause = ""
        if schema:
            schema_clause = "AND fu.name = ?"
            params.append(schema)

        sql = f"""
            SELECT
                fo.name     AS fk_table,
                fu.name     AS fk_schema,
                fc.name     AS fk_column,
                po.name     AS pk_table,
                pu.name     AS pk_schema,
                pc.name     AS pk_column,
                r.frgndbname AS fk_name
            FROM sysreferences r
            JOIN sysobjects fo  ON fo.id  = r.tableid
            JOIN sysusers   fu  ON fu.uid = fo.uid
            JOIN sysobjects po  ON po.id  = r.reftabid
            JOIN sysusers   pu  ON pu.uid = po.uid
            JOIN syscolumns fc  ON fc.id  = r.tableid
                                AND fc.colid = r.fokey1
            JOIN syscolumns pc  ON pc.id  = r.reftabid
                                AND pc.colid = r.refkey1
            WHERE fo.name = ?
              {schema_clause}
        """

        try:
            cursor.execute(sql, params)
            columns = [d[0] for d in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            if rows:
                return rows
        except Exception:
            pass

        # Fallback: ODBC catalog
        try:
            cursor.foreignKeys(foreignTable=table, foreignSchema=schema)
            desc = cursor.description
            if desc:
                return [
                    {d[0]: getattr(r, d[0], None) for d in desc}
                    for r in cursor.fetchall()
                ]
        except Exception:
            pass

        return []

    # ------------------------------------------------------------------
    # SQL capabilities
    # ------------------------------------------------------------------

    def get_sql_capabilities(self) -> dict:
        return {
            "supports_cte": True,   # ASE 15.7+ supports WITH
            "supports_limit": False,  # use SET ROWCOUNT / TOP instead
            "read_only": False,
            "max_concurrent": None,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    None: ("U", "V"),
    "TABLE": ("U",),
    "VIEW": ("V",),
    "PROCEDURE": ("P",),
    "SYSTEM TABLE": ("S",),
}


def _resolve_type_filter(table_type: str | None) -> tuple[str, ...]:
    """Map an MCP table_type string to sysobjects.type codes."""
    if table_type is None:
        return ("U", "V")
    return _TYPE_MAP.get(table_type.upper(), ("U", "V"))
