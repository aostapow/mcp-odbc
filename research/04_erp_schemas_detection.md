# ERP Schemas & System Detection via ODBC

Comprehensive reference for detecting ERP systems via ODBC, discovering schema metadata, and handling system-specific SQL limitations.

---

## 1. ODBC-Level Detection

### 1.1 SQLGetInfo Constants

Core detection via driver/connection attributes:

| Constant | Returns | Usage |
|----------|---------|-------|
| SQL_DBMS_NAME | "NetSuite", "SQL Server", "PostgreSQL", etc. | Primary system identifier |
| SQL_DBMS_VER | "1.0", "15.0", "12.5", etc. | Version-specific features |
| SQL_DRIVER_NAME | "SuiteAnalytics Connect", "SQLSRV32.dll", "psqlODBC.dll" | Driver fingerprinting |
| SQL_DRIVER_VER | Driver version string | Compatibility/feature flags |
| SQL_MAX_STATEMENT_LEN | Max query length in bytes | Pre-query size checks |
| SQL_IDENTIFIER_QUOTE_CHAR | '"', '[', '`' | Escaping syntax |
| SQL_CATALOG_NAME_SEPARATOR | '.', '/' | Multi-tier naming |
| SQL_CATALOG_USAGE | Bitmask | Catalog/schema scope |
| SQL_SCHEMA_USAGE | Bitmask | Schema availability |
| SQL_CATALOG_TERM | "database", "catalog", "collection" | Terminology mapping |
| SQL_SCHEMA_TERM | "schema", "package", "library" | Schema naming |
| SQL_TABLE_TERM | "table", "file" | Table naming |
| SQL_COLUMN_LABEL | True/False | Alias support in WHERE |
| SQL_PROCEDURES | True/False | Stored procedure support |
| SQL_SPECIAL_CHARACTERS | Character set | Reserved chars |
| SQL_KEYWORDS | Comma-separated list | Reserved words |

### 1.2 Known SQL_DBMS_NAME Values

Authoritative detection strings by system:

| System | SQL_DBMS_NAME | SQL_DBMS_VER | SQL_DRIVER_NAME | Notes |
|--------|---------------|--------------|-----------------|-------|
| NetSuite | "NetSuite" | "1.0" | "SuiteAnalytics Connect ODBC Driver (64-bit)" | Exact match; version fixed |
| SQL Server 2019 | "SQL Server" | "15.00.xxxx" | "SQLSRV32.dll" or "SQLNCLI11.dll" | SQLNCLI deprecated; use native client |
| SQL Server 2022 | "SQL Server" | "16.00.xxxx" | "SQLSRV32.dll" | Native vs. OleDB drivers |
| PostgreSQL | "PostgreSQL" | "12.5", "13.0", etc. | "psqlODBC.dll" or "libpq.so" | Version varies by distribution |
| MySQL 8.0 | "MySQL" | "8.00.xxxx" | "myodbc8a.dll" or "myodbc8w.dll" | Wide/ANSI variants |
| MySQL 5.7 | "MySQL" | "5.07.xxxx" | "myodbc5a.dll" or "myodbc5w.dll" | EoL; legacy systems |
| MariaDB | "MySQL" or "MariaDB" | "10.x.x" | "mariadb.odbc32.dll" | MariaDB-specific driver available |
| Oracle 19c | "Oracle" | "19.0.0.0.0" | "sqora32.dll" or "oraodbc.dll" | ANSI vs. Oracle naming modes |
| Oracle 12c | "Oracle" | "12.1.0.0.0" | "sqora32.dll" or "oraodbc.dll" | EoL; requires patches |
| SAP HANA | "HDB" or "SAP HANA" | "2.0.x.x" | "libodbchdb.so" or "odbchdb.dll" | Two-tier databases; multi-tenancy |
| SAP Business One | "SQL Server" or "HDB" | Per underlying DB | Per underlying DB | B1 layer on top; use B1-specific tables |
| Dynamics NAV | "SQL Server" | Per SQL Server version | "SQLSRV32.dll" | Company$TableName format |
| Dynamics BC | "SQL Server" | Per SQL Server version | "SQLSRV32.dll" | Inherited NAV schema; SaaS isolation |
| Dynamics GP | "SQL Server" | Per SQL Server version | "SQLSRV32.dll" | 2-letter module prefixes (SY, GL, PM, RM, SOP, IV) |
| IBM i (AS/400) | "DB2" | "7.x", "11.x" | "libdb400.a" or "DB2ODBC.dll" | QSYS2.* catalogs; library=schema |
| QuickBooks QODBC | "QuickBooks" | Varies | "qbodbc.dll" or "qbodbc64.dll" | Stored procedures only (sp_tables, sp_columns) |
| Sage 100 | "ProvideX" | Varies | "oleprvx32.dll" | No SQL catalog; only ODBC catalog functions |

### 1.3 Driver Name Fingerprinting

Advanced detection via driver characteristics:

```python
DRIVER_FINGERPRINTS = {
    # NetSuite
    "suiteanalytics": {
        "systems": ["NetSuite"],
        "patterns": [r"SuiteAnalytics.*Connect", r"Oracle.*NetSuite"],
        "odbcver": "3.8+",
        "catalog_support": False,
        "schema_support": True,
    },

    # SQL Server (multiple drivers)
    "msodbcsql": {
        "systems": ["SQL Server"],
        "patterns": [r"ODBC Driver.*SQL Server", r"SQLSRV32"],
        "odbcver": "3.8+",
        "catalog_support": True,
        "schema_support": True,
    },
    "sqlncli": {
        "systems": ["SQL Server"],
        "patterns": [r"SQL Native Client", r"SQLNCLI11"],
        "odbcver": "3.8+",
        "catalog_support": True,
        "schema_support": True,
        "deprecated": True,
    },

    # PostgreSQL
    "psqlodbcx": {
        "systems": ["PostgreSQL"],
        "patterns": [r"psqlODBC", r"libpq"],
        "odbcver": "3.5+",
        "catalog_support": False,
        "schema_support": True,
    },

    # MySQL/MariaDB
    "myodbc": {
        "systems": ["MySQL"],
        "patterns": [r"MySQL ODBC", r"myodbc"],
        "odbcver": "3.5+",
        "catalog_support": True,
        "schema_support": True,
    },
    "mariadbodbc": {
        "systems": ["MariaDB"],
        "patterns": [r"MariaDB ODBC", r"mariadb"],
        "odbcver": "3.5+",
        "catalog_support": True,
        "schema_support": True,
    },

    # Oracle
    "oraodbc": {
        "systems": ["Oracle"],
        "patterns": [r"Oracle ODBC", r"sqora32"],
        "odbcver": "3.8+",
        "catalog_support": False,
        "schema_support": True,
    },

    # SAP HANA
    "hdbodbc": {
        "systems": ["SAP HANA"],
        "patterns": [r"SAP HANA", r"HDB", r"libodbchdb"],
        "odbcver": "3.8+",
        "catalog_support": True,
        "schema_support": True,
    },

    # IBM i / AS/400
    "db2odbc": {
        "systems": ["IBM i", "AS/400", "DB2"],
        "patterns": [r"DB2 ODBC", r"libdb400"],
        "odbcver": "3.5+",
        "catalog_support": True,
        "schema_support": True,
    },

    # QuickBooks
    "qbodbc": {
        "systems": ["QuickBooks"],
        "patterns": [r"QuickBooks", r"QODBC"],
        "odbcver": "3.0+",
        "catalog_support": False,
        "schema_support": False,
        "stored_proc_only": True,
    },

    # Sage 100 (ProvideX)
    "oleprvx": {
        "systems": ["Sage 100"],
        "patterns": [r"ProvideX", r"oleprvx"],
        "odbcver": "2.0+",
        "catalog_support": True,
        "schema_support": False,
        "sql_limited": True,
    },
}
```

### 1.4 Probe Queries for System Detection

Safe, quick detection queries (no data retrieval):

```sql
-- Universal: Check DBMS name
SELECT @@version; -- SQL Server
SELECT version(); -- PostgreSQL, MySQL
SELECT * FROM v$version WHERE rownum=1; -- Oracle
SELECT database_version FROM SYS.M_SYSTEM_OVERVIEW; -- SAP HANA
SELECT @@current_server; -- NetSuite (fails gracefully if not present)

-- Driver capabilities probe
SELECT SQL_DBMS_NAME, SQL_DBMS_VER FROM INFORMATION_SCHEMA.INFORMATION_SCHEMA_CATALOG_NAME;

-- Catalog detection (fails gracefully on no-catalog systems)
SELECT TABLE_CATALOG FROM INFORMATION_SCHEMA.TABLES LIMIT 1;
-- NetSuite: returns NULL or empty
-- SQL Server/MySQL/HANA: returns catalog name

-- Schema detection
SELECT TABLE_SCHEMA FROM INFORMATION_SCHEMA.TABLES LIMIT 1;
-- PostgreSQL/Oracle/NetSuite: returns schema name
-- MySQL: returns database name

-- System catalog table probe (try each in sequence, stop at first success)
SELECT COUNT(*) FROM DBA_TABLES; -- Oracle (DBA tier; requires admin)
SELECT COUNT(*) FROM ALL_TABLES; -- Oracle (ALL tier; normal user)
SELECT COUNT(*) FROM USER_TABLES; -- Oracle (USER tier; schema-specific)
SELECT COUNT(*) FROM pg_catalog.pg_tables; -- PostgreSQL
SELECT COUNT(*) FROM information_schema.tables; -- MySQL, HANA, PostgreSQL
SELECT COUNT(*) FROM SYS.TABLES; -- SAP HANA, SQL Server
SELECT COUNT(*) FROM QSYS2.SYSTABLES; -- IBM i / AS/400
SELECT COUNT(*) FROM dbo.sysobjects; -- SQL Server (legacy; sys.objects preferred)
```

---

## 2. ODBC Catalog Functions (Universal)

Standard ODBC API calls work across all systems (when ODBC driver is compliant):

### 2.1 Cursor Metadata Functions

```python
import pyodbc

conn = pyodbc.connect(connection_string)
cursor = conn.cursor()

# SQLTables: List all tables
cursor.tables(schema='public')  # Result columns: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, TABLE_TYPE, REMARKS
for row in cursor.tables():
    print(f"Table: {row.table_name}, Type: {row.table_type}, Schema: {row.table_schem}")

# SQLColumns: List all columns in a table
cursor.columns(table='Orders')  # Result: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, COLUMN_NAME, DATA_TYPE, TYPE_NAME, COLUMN_SIZE, DECIMAL_DIGITS, NULLABLE, REMARKS
for row in cursor.columns(table='Orders'):
    print(f"Column: {row.column_name}, Type: {row.type_name}, Nullable: {row.nullable}")

# SQLPrimaryKeys: Get primary key columns
cursor.primaryKeys(table='Orders')  # Result: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, COLUMN_NAME, KEY_SEQ, PK_NAME
for row in cursor.primaryKeys(table='Orders'):
    print(f"PK Column: {row.column_name}, Sequence: {row.key_seq}")

# SQLForeignKeys: Get foreign key relationships
cursor.foreignKeys(table='OrderItems')  # Result: PKTABLE_CAT, PKTABLE_SCHEM, PKTABLE_NAME, PKCOLUMN_NAME, FKTABLE_CAT, FKTABLE_SCHEM, FKTABLE_NAME, FKCOLUMN_NAME, KEY_SEQ, UPDATE_RULE, DELETE_RULE, FK_NAME, PK_NAME
for row in cursor.foreignKeys(table='OrderItems'):
    print(f"FK: {row.fktable_name}.{row.fkcolumn_name} -> {row.pktable_name}.{row.pkcolumn_name}")

# SQLGetTypeInfo: Get supported data types
cursor.getTypeInfo()  # Result: TYPE_NAME, DATA_TYPE, COLUMN_SIZE, LITERAL_PREFIX, LITERAL_SUFFIX, CREATE_PARAMS, NULLABLE, CASE_SENSITIVE, SEARCHABLE, UNSIGNED_ATTRIBUTE, FIXED_PREC_SCALE, AUTO_INCREMENT, LOCAL_TYPE_NAME, MINIMUM_SCALE, MAXIMUM_SCALE, SQL_DATA_TYPE, SQL_DATETIME_SUB, NUM_PREC_RADIX, INTERVAL_PRECISION
for row in cursor.getTypeInfo():
    print(f"Type: {row.type_name}, SQL Type: {row.data_type}, Size: {row.column_size}")

# SQLStatistics: Get table statistics and indexes
cursor.statistics(table='Orders')  # Result: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, NON_UNIQUE, INDEX_QUALIFIER, INDEX_NAME, TYPE, ORDINAL_POSITION, COLUMN_NAME, ASC_OR_DESC, CARDINALITY, PAGES, FILTER_CONDITION
for row in cursor.statistics(table='Orders'):
    print(f"Index: {row.index_name}, Column: {row.column_name}, Cardinality: {row.cardinality}")
```

### 2.2 Limitations of ODBC Catalog Functions

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| No computed column metadata | Can't detect DAX-like calc columns | Query system catalogs directly |
| No measure/aggregate metadata | OLAP models opaque | Use XMLA or REST APIs |
| Limited data type info | TYPE_NAME varies by driver | Cross-reference SQL_TYPE_IDENTIFIER |
| No constraint details (CHECK, DEFAULT) | Missing business logic | Query system catalogs |
| No view definitions | View logic hidden | Query system catalogs or use system functions |
| No trigger/procedure definitions | Logic hidden from discovery | Query system catalogs |
| No column-level permissions | Security rules hidden | Query system catalogs with elevated privs |
| Foreign key detection inconsistent | Some drivers omit; Oracle requires hints | Fall back to constraint queries |
| Cardinality estimates may be stale | Query optimization fails | Run ANALYZE/STATISTICS commands first |
| Performance: O(n) for large schemas | Discovery slows with table count | Batch queries; cache results |

### 2.3 Catalog Function Example: Complete Discovery Pipeline

```python
import pyodbc
from typing import Dict, List, Tuple

class SchemaDiscovery:
    def __init__(self, connection_string: str):
        self.conn = pyodbc.connect(connection_string)
        self.cursor = self.conn.cursor()
        self.schema_cache = {}

    def discover_all(self) -> Dict:
        """Full schema discovery pipeline"""
        result = {
            'tables': {},
            'relationships': [],
            'types': {},
        }

        # Step 1: Discover tables
        for table_row in self.cursor.tables():
            if table_row.table_type in ('TABLE', 'VIEW'):
                table_name = table_row.table_name
                result['tables'][table_name] = {
                    'schema': table_row.table_schem,
                    'catalog': table_row.table_cat,
                    'type': table_row.table_type,
                    'columns': {},
                    'pk': [],
                    'indexes': [],
                }

        # Step 2: Discover columns for each table
        for table_name in result['tables'].keys():
            for col_row in self.cursor.columns(table=table_name):
                result['tables'][table_name]['columns'][col_row.column_name] = {
                    'type': col_row.type_name,
                    'size': col_row.column_size,
                    'nullable': bool(col_row.nullable),
                    'remarks': col_row.remarks or '',
                }

        # Step 3: Discover primary keys
        for table_name in result['tables'].keys():
            try:
                for pk_row in self.cursor.primaryKeys(table=table_name):
                    result['tables'][table_name]['pk'].append({
                        'column': pk_row.column_name,
                        'sequence': pk_row.key_seq,
                        'name': pk_row.pk_name,
                    })
            except pyodbc.Error:
                pass  # No PK or driver doesn't support

        # Step 4: Discover foreign keys
        for table_name in result['tables'].keys():
            try:
                for fk_row in self.cursor.foreignKeys(table=table_name):
                    result['relationships'].append({
                        'from_table': fk_row.fktable_name,
                        'from_column': fk_row.fkcolumn_name,
                        'to_table': fk_row.pktable_name,
                        'to_column': fk_row.pkcolumn_name,
                        'name': fk_row.fk_name,
                    })
            except pyodbc.Error:
                pass  # No FKs or driver doesn't support

        # Step 5: Discover indexes
        for table_name in result['tables'].keys():
            try:
                for idx_row in self.cursor.statistics(table=table_name):
                    if idx_row.index_name not in [i['name'] for i in result['tables'][table_name]['indexes']]:
                        result['tables'][table_name]['indexes'].append({
                            'name': idx_row.index_name,
                            'unique': not bool(idx_row.non_unique),
                            'columns': [idx_row.column_name],
                        })
            except pyodbc.Error:
                pass

        # Step 6: Discover types
        for type_row in self.cursor.getTypeInfo():
            result['types'][type_row.type_name] = {
                'sql_type': type_row.data_type,
                'size': type_row.column_size,
                'signed': not bool(type_row.unsigned_attribute),
            }

        self.schema_cache = result
        return result
```

---

## 3. Per-System Schema Detection & SQL

### 3.1 NetSuite

**Detection:**
- SQL_DBMS_NAME = "NetSuite"
- SQL_DRIVER_NAME contains "SuiteAnalytics"
- Catalog/schema support: schema-only (no catalogs)

**System Metadata Tables:**

```sql
-- OA_TABLES: Available tables (NetSuite native catalog)
SELECT * FROM OA_TABLES
WHERE TABLE_CATALOG = 'INFORMATION_SCHEMA'
   OR TABLE_NAME NOT LIKE '%_OLD%'
   OR TABLE_NAME NOT LIKE '%_TEMP%'
ORDER BY TABLE_NAME;

-- OA_COLUMNS: Column metadata
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_DEFAULT,
    IS_NULLABLE,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    NUMERIC_PRECISION,
    NUMERIC_SCALE
FROM OA_COLUMNS
WHERE TABLE_NAME = 'Transaction'
ORDER BY ORDINAL_POSITION;

-- OA_FKEYS: Foreign key constraints (if exposed)
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM OA_FKEYS
WHERE TABLE_NAME = 'Transaction';

-- Legacy INFORMATION_SCHEMA (partial)
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'public';
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| No CTE (Common Table Expressions) | Break into temp tables or UNIONs |
| No INSERT/UPDATE/DELETE (read-only) | Extract to staging, transform in BI tool |
| 1000-column limit per table | Impossible to query 1000+ column tables in single statement; split by subset |
| No transaction support | Auto-commit all queries |
| Slow GROUP BY on large fact tables | Aggregate in source ERP if possible |
| No direct JOIN syntax for some views | Join in application layer |
| UNION performance issues | Limit unions to <10 queries; use UNION ALL instead of UNION |
| No DISTINCT on large datasets | Use GROUP BY instead |
| Parameterized query limits | Direct query preferred; parameters may fail in complex predicates |
| Schema reflection slow on large catalogs | Cache schema metadata; refresh nightly only |

**Example: NetSuite Transaction Discovery**

```sql
-- Find all transaction tables
SELECT TABLE_NAME, TABLE_TYPE
FROM OA_TABLES
WHERE TABLE_NAME LIKE '%Transaction%'
   AND TABLE_SCHEMA = 'public';

-- List all columns in Transaction table
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    ORDINAL_POSITION
FROM OA_COLUMNS
WHERE TABLE_NAME = 'Transaction'
ORDER BY ORDINAL_POSITION;

-- Sample: Get past-due sales orders (NetSuite-specific query)
SELECT
    t.id,
    t.recordType,
    t.createdDate,
    t.dueDate,
    DATEDIFF(CURDATE(), t.dueDate) AS DaysPastDue,
    tl.id AS LineId,
    tl.quantity,
    tl.quantityFulfilled
FROM Transaction t
INNER JOIN TransactionLine tl ON t.id = tl.transactionid
WHERE t.recordType = 'SalesOrder'
  AND t.dueDate < CURDATE()
ORDER BY t.dueDate ASC, t.createdDate ASC, tl.lineno ASC;
```

### 3.2 SQL Server

**Detection:**
- SQL_DBMS_NAME = "SQL Server"
- SQL_DBMS_VER starts with "15." (2019), "16." (2022), "14." (2017), "13." (2016)
- SQL_DRIVER_NAME contains "SQLSRV32" or "SQLNCLI11"
- Catalog/schema support: full (catalog.schema.table)

**System Metadata Tables:**

```sql
-- sys.tables: All tables (system + user)
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    t.object_id,
    t.create_date,
    t.modify_date
FROM sys.tables t
INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
WHERE s.name = 'dbo'
ORDER BY t.name;

-- sys.columns: Column metadata
SELECT
    c.column_id,
    c.name AS column_name,
    tp.name AS data_type,
    c.max_length,
    c.precision,
    c.scale,
    c.is_nullable,
    c.is_identity,
    dc.definition AS default_value
FROM sys.columns c
INNER JOIN sys.types tp ON c.user_type_id = tp.user_type_id
LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
WHERE object_id = OBJECT_ID('dbo.Orders')
ORDER BY c.column_id;

-- INFORMATION_SCHEMA.TABLES: ANSI-compatible table discovery
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;

-- INFORMATION_SCHEMA.COLUMNS: ANSI-compatible column discovery
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'Orders'
ORDER BY ORDINAL_POSITION;

-- sys.foreign_keys: Foreign key constraints
SELECT
    fk.name AS fk_name,
    OBJECT_NAME(fk.parent_object_id) AS child_table,
    COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS child_column,
    OBJECT_NAME(fk.referenced_object_id) AS parent_table,
    COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS parent_column
FROM sys.foreign_keys fk
INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
WHERE OBJECT_NAME(fk.parent_object_id) = 'Orders'
ORDER BY fk.name, fkc.constraint_column_id;

-- sys.key_constraints: Primary keys
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'Orders'
  AND CONSTRAINT_NAME LIKE 'PK_%'
ORDER BY ORDINAL_POSITION;

-- sys.indexes: Index metadata
SELECT
    i.name AS index_name,
    c.name AS column_name,
    ic.key_ordinal,
    i.is_unique,
    i.is_primary_key
FROM sys.indexes i
INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
WHERE OBJECT_NAME(i.object_id) = 'Orders'
ORDER BY i.index_id, ic.key_ordinal;
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| ANSI_NULLS behavior varies | Explicitly handle NULLs in WHERE clauses |
| DATEFORMAT ambiguity | Use CONVERT(DATE, '2025-02-11', 23) format |
| Database-level collation conflicts | Specify COLLATE clause in JOINs |
| sys.* views locked during DDL | Query INFORMATION_SCHEMA instead |
| Large result sets slow without SET ROWCOUNT | Limit results in WHERE clause, not LIMIT |
| XML data type requires special casting | CAST(xml_col AS NVARCHAR(MAX)) |
| Encrypted columns return NULL without key | Ensure key is available in connection |
| Temp table scope across batches | Use global ##temp tables or physical tables |

### 3.3 PostgreSQL

**Detection:**
- SQL_DBMS_NAME = "PostgreSQL"
- SQL_DRIVER_NAME contains "psqlODBC"
- Catalog/schema support: catalog=database; schema=namespace

**System Metadata Tables:**

```sql
-- pg_catalog.pg_tables: Table discovery
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_catalog.pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
ORDER BY schemaname, tablename;

-- pg_catalog.pg_class + pg_catalog.pg_attribute: Column metadata
SELECT
    a.attname AS column_name,
    a.attnum AS ordinal_position,
    t.typname AS data_type,
    a.attlen AS max_length,
    a.atttypmod AS type_modifier,
    a.attnotnull AS not_null,
    d.adsrc AS default_value
FROM pg_catalog.pg_class c
INNER JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
INNER JOIN pg_catalog.pg_attribute a ON c.oid = a.attrelid
INNER JOIN pg_catalog.pg_type t ON a.atttypid = t.oid
LEFT JOIN pg_catalog.pg_attrdef d ON a.attrelid = d.adrelid AND a.attnum = d.adnum
WHERE n.nspname = 'public'
  AND c.relname = 'orders'
  AND a.attnum > 0
ORDER BY a.attnum;

-- information_schema.tables: ANSI-compatible table discovery
SELECT
    table_catalog,
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- information_schema.columns: ANSI-compatible column discovery
SELECT
    table_name,
    column_name,
    ordinal_position,
    data_type,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
ORDER BY ordinal_position;

-- pg_catalog.pg_constraint: Constraints (PK, FK, UNIQUE, CHECK)
SELECT
    constraint_name,
    constraint_type,
    table_name,
    column_name,
    foreign_table_name,
    foreign_column_name
FROM information_schema.referential_constraints rc
LEFT JOIN information_schema.key_column_usage kcu ON rc.unique_constraint_name = kcu.constraint_name
WHERE rc.constraint_schema = 'public'
ORDER BY rc.constraint_name;

-- pg_catalog.pg_index: Index metadata
SELECT
    i.indexname,
    t.tablename,
    a.attname AS column_name,
    x.indisunique,
    x.indisprimary
FROM pg_catalog.pg_indexes i
INNER JOIN pg_catalog.pg_class t ON i.tablename = t.relname
INNER JOIN pg_catalog.pg_attribute a ON t.oid = a.attrelid
INNER JOIN pg_catalog.pg_index x ON t.oid = x.indrelid
WHERE i.schemaname = 'public'
  AND i.tablename = 'orders'
ORDER BY i.indexname, a.attnum;
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| OID data type not exposed to ODBC | Query directly via pg_catalog |
| UUID type requires casting | CAST(uuid_col AS TEXT) |
| Array types not ODBC-friendly | UNNEST() in query or cast to TEXT |
| JSON/JSONB types may fail in ODBC | Extract to TEXT or use ->> operators with caution |
| Large object (bytea) performance poor | Stream via application, not ODBC |
| Unlogged tables in transaction conflict | Use logged tables for consistency |
| LISTEN/NOTIFY not ODBC-compatible | Use polling query pattern instead |
| Set-returning functions (SRF) scope issues | Wrap in LATERAL subqueries |
| VACUUM exclusive locks | Schedule during maintenance windows |
| Prepared statement plan caching across ODBC connections | Parameters may be suboptimal on second run |

### 3.4 MySQL / MariaDB

**Detection:**
- SQL_DBMS_NAME = "MySQL" or "MariaDB"
- SQL_DBMS_VER = "8.00.xxxx" (MySQL 8), "10.x.x" (MariaDB), "5.07.xxxx" (MySQL 5.7)
- SQL_DRIVER_NAME contains "myodbc" or "mariadb"
- Catalog/schema support: INFORMATION_SCHEMA only; no pg_catalog equivalent

**System Metadata Tables:**

```sql
-- INFORMATION_SCHEMA.TABLES: Table discovery
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'mydb'
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;

-- INFORMATION_SCHEMA.COLUMNS: Column metadata
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_DEFAULT,
    IS_NULLABLE,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    COLUMN_TYPE,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'mydb'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;

-- INFORMATION_SCHEMA.TABLE_CONSTRAINTS: Constraints (PK, FK, UNIQUE)
SELECT
    CONSTRAINT_CATALOG,
    CONSTRAINT_SCHEMA,
    CONSTRAINT_NAME,
    TABLE_NAME,
    CONSTRAINT_TYPE
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = 'mydb'
  AND TABLE_NAME = 'orders';

-- INFORMATION_SCHEMA.KEY_COLUMN_USAGE: Primary keys
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'mydb'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;

-- INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS: Foreign keys
SELECT
    CONSTRAINT_NAME,
    UNIQUE_CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME,
    MATCH_OPTION,
    UPDATE_RULE,
    DELETE_RULE
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'mydb'
  AND TABLE_NAME = 'orders';

-- INFORMATION_SCHEMA.STATISTICS: Index metadata
SELECT
    TABLE_NAME,
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    NON_UNIQUE,
    INDEX_TYPE,
    CARDINALITY
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'mydb'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;

-- MySQL 8 specific: generated columns
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    GENERATION_EXPRESSION,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'mydb'
  AND GENERATION_EXPRESSION IS NOT NULL;
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| INFORMATION_SCHEMA slow on large databases | Cache schema metadata; refresh nightly |
| Sparse tables with NULL defaults | Explicitly check IS_NULLABLE in schema |
| InnoDB locks during schema queries | Use LOCK TABLES ... READ or non-locking statements |
| VARBINARY differs between MySQL 5.7 and 8 | CAST to TEXT if needed for ODBC |
| Generated columns read-only | Don't attempt INSERT into generated column |
| JSON type requires -> operators | Use JSON_EXTRACT() for ODBC compatibility |
| Trigger visibility requires elevated privs | Query with user that has TRIGGER privilege |
| Stored procedure discovery via ODBC unreliable | Use sp_procedures() if available; fallback to sys catalogs |
| FULL TEXT indexes not exposed to ODBC | Query INFORMATION_SCHEMA.STATISTICS only |
| MyISAM tables lack foreign key support | Check ENGINE = 'InnoDB' in TABLES |

### 3.5 Oracle

**Detection:**
- SQL_DBMS_NAME = "Oracle"
- SQL_DBMS_VER = "19.0.0.0.0" (19c), "12.1.0.0.0" (12c), "21.0.0.0.0" (21c)
- SQL_DRIVER_NAME contains "Oracle ODBC" or "sqora32"
- Catalog/schema support: database (fixed); schema=user; 3-tier privilege model (USER/ALL/DBA)

**System Metadata Tables (3-tier access control):**

```sql
-- USER_TABLES: Tables owned by current user (lowest privilege, fastest)
SELECT
    TABLE_NAME,
    OWNER,
    TABLESPACE_NAME,
    LAST_DDL_TIME
FROM USER_TABLES
ORDER BY TABLE_NAME;

-- ALL_TABLES: All tables accessible to current user (normal access)
SELECT
    OWNER,
    TABLE_NAME,
    TABLESPACE_NAME,
    LAST_DDL_TIME
FROM ALL_TABLES
WHERE OWNER IN (SELECT USERNAME FROM ALL_USERS WHERE ACCOUNT_STATUS = 'OPEN')
ORDER BY OWNER, TABLE_NAME;

-- DBA_TABLES: All tables in database (requires DBA privilege; slow)
-- Use sparingly; usually used by DBAs only
SELECT
    OWNER,
    TABLE_NAME,
    TABLESPACE_NAME,
    NUM_ROWS,
    LAST_DDL_TIME
FROM DBA_TABLES
WHERE OWNER NOT IN ('SYS', 'SYSTEM', 'CTXSYS', 'XDB', 'ORDDATA')
ORDER BY OWNER, TABLE_NAME;

-- USER_TAB_COLUMNS: Column metadata (USER tier)
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_ID,
    DATA_TYPE,
    DATA_LENGTH,
    DATA_PRECISION,
    DATA_SCALE,
    NULLABLE,
    DEFAULT_LENGTH,
    DATA_DEFAULT
FROM USER_TAB_COLUMNS
WHERE TABLE_NAME = 'ORDERS'
ORDER BY COLUMN_ID;

-- ALL_TAB_COLUMNS: Column metadata (ALL tier)
SELECT
    OWNER,
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_ID,
    DATA_TYPE,
    DATA_LENGTH,
    DATA_PRECISION,
    DATA_SCALE,
    NULLABLE
FROM ALL_TAB_COLUMNS
WHERE TABLE_NAME = 'ORDERS'
ORDER BY OWNER, TABLE_NAME, COLUMN_ID;

-- DBA_TAB_COLUMNS: Column metadata (DBA tier, slow)
SELECT
    OWNER,
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_ID,
    DATA_TYPE,
    DATA_LENGTH,
    DATA_PRECISION,
    DATA_SCALE,
    NULLABLE
FROM DBA_TAB_COLUMNS
WHERE OWNER NOT IN ('SYS', 'SYSTEM', 'CTXSYS', 'XDB')
ORDER BY OWNER, TABLE_NAME, COLUMN_ID;

-- USER_CONSTRAINTS: Primary keys and unique constraints (USER tier)
SELECT
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE,
    TABLE_NAME,
    STATUS
FROM USER_CONSTRAINTS
WHERE TABLE_NAME = 'ORDERS'
  AND CONSTRAINT_TYPE IN ('P', 'U', 'R');

-- USER_CONS_COLUMNS: Constraint columns detail
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    POSITION
FROM USER_CONS_COLUMNS
WHERE TABLE_NAME = 'ORDERS'
ORDER BY CONSTRAINT_NAME, POSITION;

-- ALL_CONSTRAINTS + ALL_CONS_COLUMNS: Cross-owner constraints (ALL tier)
SELECT
    c.OWNER,
    c.CONSTRAINT_NAME,
    c.CONSTRAINT_TYPE,
    c.TABLE_NAME,
    cc.COLUMN_NAME,
    cc.POSITION,
    c.R_OWNER,
    c.R_CONSTRAINT_NAME
FROM ALL_CONSTRAINTS c
LEFT JOIN ALL_CONS_COLUMNS cc ON c.OWNER = cc.OWNER
                              AND c.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
WHERE c.TABLE_NAME = 'ORDERS'
ORDER BY c.CONSTRAINT_NAME, cc.POSITION;

-- USER_INDEXES: Index metadata (USER tier)
SELECT
    INDEX_NAME,
    TABLE_NAME,
    UNIQUENESS,
    COMPRESSION
FROM USER_INDEXES
WHERE TABLE_NAME = 'ORDERS'
ORDER BY INDEX_NAME;

-- USER_IND_COLUMNS: Index column detail
SELECT
    INDEX_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_POSITION,
    DESC_ASC
FROM USER_IND_COLUMNS
WHERE TABLE_NAME = 'ORDERS'
ORDER BY INDEX_NAME, COLUMN_POSITION;
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| USER/ALL/DBA view bloat with 1000s of tables | Use WHERE owner = 'SCHEMA' to filter; query USER tier first |
| ANSI/NAMING naming mode conflicts | Use DBMS_UTILITY.ACTIVE_NAMING to check current mode |
| Long table names (30+ chars) truncated in ODBC | Use ALL_TABLES directly; ODBC catalog functions may truncate |
| Oracle SQL*Plus vs ODBC syntax differences | Test queries in SQL*Plus first; ODBC may fail on advanced features |
| LOB (BLOB/CLOB) data in ODBC results | Use DBMS_LOB.SUBSTR() to extract portions |
| Partitioned tables appear in USER_TABLES w/ duplicate rows | Group by table name to deduplicate |
| Function-based indexes not marked in USER_INDEXES | Query DBA_INDEXES.INDEX_TYPE = 'FUNCTION-BASED DOMAIN' |
| Virtual columns (12c+) hidden by default | Query USER_TAB_COLS with VIRTUAL_COLUMN = 'YES' |
| Temporary tables global vs session scope | Check USER_TABLES.DURATION for SESS or TRANS |
| Redo log activity slows DBA_TABLES queries | Use ALL_TABLES or USER_TABLES; avoid DBA tier |

### 3.6 SAP HANA

**Detection:**
- SQL_DBMS_NAME = "HDB" or "SAP HANA"
- SQL_DBMS_VER = "2.0.x.x"
- SQL_DRIVER_NAME contains "SAP HANA" or "libodbchdb"
- Catalog/schema support: tenant database (catalog); schema=schema

**System Metadata Tables:**

```sql
-- SYS.M_DATABASES: List all tenant databases
SELECT
    DATABASE_NAME,
    ACTIVE_STATUS,
    SQL_ENDPOINT_ACTIVE_STATUS,
    DATABASE_VERSION,
    SYSTEM_DB
FROM SYS.M_DATABASES
ORDER BY DATABASE_NAME;

-- SYS.TABLES: Table discovery (current database)
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    TABLE_OID,
    PART_ID,
    CREATE_TIME,
    LAST_MODIFIED_TIME,
    TABLE_TYPE,
    IS_COLUMN_TABLE,
    IS_TEMPORARY
FROM SYS.TABLES
WHERE SCHEMA_NAME NOT IN ('_SYS_BIC', '_SYS_REPO', '_SYS_AUTH')
ORDER BY SCHEMA_NAME, TABLE_NAME;

-- SYS.TABLE_COLUMNS: Column metadata
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    POSITION,
    DATA_TYPE_NAME,
    LENGTH,
    PRECISION,
    SCALE,
    NULLABLE,
    COMMENTS
FROM SYS.TABLE_COLUMNS
WHERE TABLE_NAME = 'ORDERS'
  AND SCHEMA_NAME != '_SYS_BIC'
ORDER BY POSITION;

-- SYS.CONSTRAINTS: Constraints (PK, UNIQUE, FK, CHECK)
SELECT
    SCHEMA_NAME,
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE,
    TABLE_NAME,
    CHECK_CONDITION,
    COMMENTS
FROM SYS.CONSTRAINTS
WHERE TABLE_NAME = 'ORDERS'
  AND SCHEMA_NAME != '_SYS_BIC'
ORDER BY CONSTRAINT_NAME;

-- SYS.REFERENTIAL_CONSTRAINTS: Foreign key details
SELECT
    SCHEMA_NAME,
    CONSTRAINT_NAME,
    BASE_SCHEMA_NAME,
    BASE_TABLE_NAME,
    BASE_COLUMN_NAME,
    REFERENCED_SCHEMA_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM SYS.REFERENTIAL_CONSTRAINTS
WHERE BASE_TABLE_NAME = 'ORDERS'
ORDER BY CONSTRAINT_NAME;

-- SYS.INDEXES: Index metadata
SELECT
    SCHEMA_NAME,
    INDEX_NAME,
    TABLE_NAME,
    INDEX_TYPE,
    CONSTRAINT_TYPE,
    UNIQUE_INDEX,
    COMMENTS
FROM SYS.INDEXES
WHERE TABLE_NAME = 'ORDERS'
ORDER BY INDEX_NAME;

-- SYS.INDEX_COLUMNS: Index column detail
SELECT
    SCHEMA_NAME,
    INDEX_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    POSITION,
    ASCENDING
FROM SYS.INDEX_COLUMNS
WHERE TABLE_NAME = 'ORDERS'
ORDER BY INDEX_NAME, POSITION;

-- SYS.VIEWS: View discovery
SELECT
    SCHEMA_NAME,
    VIEW_NAME,
    VIEW_OID,
    CREATE_TIME,
    LAST_MODIFIED_TIME,
    COMMENTS
FROM SYS.VIEWS
WHERE SCHEMA_NAME NOT IN ('_SYS_BIC', '_SYS_REPO', '_SYS_AUTH')
ORDER BY SCHEMA_NAME, VIEW_NAME;

-- SYS.VIEW_COLUMNS: View column metadata
SELECT
    SCHEMA_NAME,
    VIEW_NAME,
    COLUMN_NAME,
    POSITION,
    DATA_TYPE_NAME
FROM SYS.VIEW_COLUMNS
WHERE VIEW_NAME = 'ORDER_SUMMARY'
ORDER BY POSITION;
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| Multi-tenant database scoping | Specify DATABASE=xxx in connection string; queries cross tenants otherwise |
| SYS.* views slow on large tables (100M+ rows) | Add SCHEMA_NAME filter; avoid DBA-level queries |
| Column/row store performance parity | Use INDEX_TYPE = 'ROWSTORE' or 'COLUMNSTORE' filter |
| NCLOB (large character) type in ODBC | Use SUBSTR() to limit return size |
| HDBSQL vs ODBC query optimizer differences | Test in HDBSQL console first; ODBC may have different plans |
| Replication/HA failover timing | Use connection pooling with retry logic |
| SAML/X.509 authentication in ODBC | Use basic auth in ODBC; SAML in REST/XMLA APIs |
| Very large result sets (1B+ rows) | Add WHERE clause; use cursor fetch, not full load |

### 3.7 SAP Business One

**Detection:**
- Runs on SQL Server or SAP HANA backend
- Detect via SQL_DBMS_NAME of underlying DB (SQL Server/HDB)
- B1-specific tables: OITM (items), ORDR (orders), OCRD (customer), OINV (invoices), etc.
- 2-character prefix + underscore convention: O=object, OA=object attachment, etc.

**Detection Query:**

```sql
-- SAP Business One uses specific 2-character table prefix convention
-- Query to detect B1-specific tables:
SELECT
    TABLE_NAME,
    COUNT(CASE WHEN TABLE_NAME LIKE 'O%' THEN 1 END) AS b1_table_count,
    COUNT(*) AS total_tables
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME LIKE 'O[A-Z]%'
GROUP BY TABLE_NAME
HAVING COUNT(*) > 100;  -- B1 has 100+ standard tables

-- Example: Detect B1 core tables (100% reliable B1 indicator)
SELECT 'SAP Business One' AS system
WHERE EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME IN ('OITM', 'OCRD', 'ORDR', 'OINV')
);
```

**B1-Specific Tables Reference:**

| Module | Table | Purpose |
|--------|-------|---------|
| Master Data | OITM | Item Master |
| | OCRD | Customer/Vendor Master |
| | OHEM | Employee Master |
| | OUSR | User Accounts |
| Sales | ORDR | Sales Orders |
| | OINV | Invoices |
| | ODLN | Delivery Notes |
| | OJDL | Journal |
| Purchasing | OPOR | Purchase Orders |
| | OIGN | Goods Receipt |
| | APCH | Purchase Invoice |
| Inventory | OITW | Item Warehouse |
| | OITR | Item Transfers |
| | OINM | Inventory Movements |
| | OBTQ | Batch Master |
| | OBSL | Serial Master |
| Financial | OJDT | General Journal Lines |
| | OJDS | Journal Batches |
| | OACT | GL Accounts |
| Production | OWOR | Work Orders |
| | OWOD | WO Documents |

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| B1 tables locked during backup/restore | Schedule discovery during off-peak hours |
| System-generated columns (CreationDate, UpdateDate) hidden from ODBC | Use SQL Server catalog functions; ODBC omits them |
| Audit tables (OAUD) contain binary blobs | Query ODBC catalogs to confirm column types before reading |
| B1-specific permissions override SQL permissions | Run under B1 admin account; standard SQL login may fail |
| DocNum (document number) is NOT unique key | Use DocEntry (internal ID) as PK; DocNum can be null or reused |
| LineNum sequence gaps due to deletions | Don't assume continuous sequence 1..N |
| Attachment blobs (OAT1) too large for ODBC | Extract via B1 API instead of ODBC query |

**Example: B1 Sales Order Discovery via ODBC**

```sql
-- Get all sales orders with line items (B1-specific)
SELECT
    h.DocNum,
    h.DocEntry,
    h.DocDate,
    h.DueDate,
    h.CardCode,
    h.CardName,
    h.DocTotal,
    l.LineNum,
    l.ItemCode,
    l.ItemName,
    l.Quantity,
    l.DelivrdQty,
    l.OpenQty,
    l.UnitPrice,
    l.LineTotal
FROM ORDR h
INNER JOIN RDR1 l ON h.DocEntry = l.DocEntry
WHERE h.DocStatus = 'O'  -- Open documents
  AND h.CANCELED = 'N'   -- Not canceled
ORDER BY h.DocDate DESC, h.DocEntry DESC, l.LineNum ASC;
```

### 3.8 Dynamics NAV / Dynamics BC

**Detection:**
- SQL Server backend (detect via SQL_DBMS_NAME = "SQL Server")
- NAV/BC-specific: company$table naming scheme (e.g., "Company$Customer")
- Multi-company support via company$ prefix
- No standard system catalog; replicate via T-SQL on SQL Server backend

**Company-Aware Table Discovery:**

```sql
-- Dynamics NAV/BC: List all companies
SELECT DISTINCT
    SUBSTRING(TABLE_NAME, 1, CHARINDEX('$', TABLE_NAME) - 1) AS CompanyName
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_NAME LIKE '%$%'
  AND TABLE_SCHEMA = 'dbo'
ORDER BY CompanyName;

-- Dynamics NAV/BC: List tables for specific company
SELECT
    TABLE_NAME,
    COLUMN_COUNT = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = t.TABLE_NAME)
FROM INFORMATION_SCHEMA.TABLES t
WHERE TABLE_NAME LIKE 'MyCompanyName$%'
  AND TABLE_SCHEMA = 'dbo'
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;

-- Dynamics NAV/BC: Column discovery (note: company$ prefix in table name)
SELECT
    COLUMN_NAME,
    ORDINAL_POSITION,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'MyCompanyName$Customer'
ORDER BY ORDINAL_POSITION;

-- Known NAV/BC core tables (table names without company$ prefix):
-- Master Data:
--   - Customer: Customer master
--   - Vendor: Vendor/Supplier master
--   - Item: Item/Product master
--   - G/L Account: GL account master
--
-- Transactions:
--   - Sales Header: SO header
--   - Sales Line: SO line items
--   - Purchase Header: PO header
--   - Purchase Line: PO line items
--   - Item Ledger Entry: Inventory transactions
--   - G/L Entry: GL transactions
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| Company$ prefix must match exactly (case-sensitive) | Discover company names first; use in parameterized queries |
| GUID fields stored as NVARCHAR(36) in SQL | Cast to UNIQUEIDENTIFIER in queries |
| Flow fields (calculated fields in NAV) don't appear in SQL | Use SQL Server catalog; NAV hides them |
| Date fields use DATETIME, not DATE type | CAST to DATE if needed |
| NAV code fields case-sensitive; SQL collation may differ | Use COLLATE Latin1_General_CS_AS in WHERE clauses |
| Company-specific permissions | Connect as user with access to all companies needed |
| Change tracking (Change Log) sparse, not maintained | Don't rely on change logs for audit trail |

### 3.9 Dynamics GP

**Detection:**
- SQL Server backend
- 2-letter module prefix convention: SY (system), GL (general ledger), PM (payroll), RM (receivables), SOP (sales), IV (inventory), PC (purchasing), etc.
- DYNAMICS database name (or DYNAMICS_PROD, DYNAMICS_TEST, etc.)

**Module Table Prefix Discovery:**

```sql
-- Dynamics GP: List all modules (2-letter prefixes)
SELECT DISTINCT
    SUBSTRING(TABLE_NAME, 1, 2) AS ModulePrefix,
    COUNT(*) AS TableCount
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME NOT LIKE 'temp%'
  AND TABLE_NAME NOT LIKE 'DEV_%'
  AND TABLE_TYPE = 'BASE TABLE'
GROUP BY SUBSTRING(TABLE_NAME, 1, 2)
ORDER BY ModulePrefix;

-- Core Dynamics GP modules:
-- SY: System (company setup, security, batches)
-- GL: General Ledger
-- PM: Payroll
-- RM: Receivables (customer master, invoices, receipts)
-- SOP: Sales Order Processing (orders, lines, fulfillment)
-- IV: Inventory (items, warehouses, movements)
-- PC: Purchasing (PO master, vendors, receipt)
-- BM: Bill of Materials
-- MC: Manufacturing
-- CB: Cash Management
-- FAM: Fixed Assets

-- Dynamics GP: List GL accounts
SELECT
    ACTNMBR,
    ACTDESC,
    ACTTYPE,
    ACCTTYPE
FROM GL00100  -- GL Master
WHERE ACTNMBR LIKE '[1-9]%';  -- Non-summary accounts

-- Dynamics GP: List customers and AR transactions
SELECT
    c.CUSTNMBR,
    c.CUSTNAME,
    c.CNTCPERSON,
    a.DOCNUMBR,
    a.DOCDATE,
    a.DUEDATE,
    a.CURTRX
FROM RM00101 c  -- Customer Master
INNER JOIN RM00201 a ON c.CUSTNMBR = a.CUSTNMBR  -- AR Transactions
WHERE a.DUEDATE < GETDATE()
ORDER BY a.DUEDATE ASC, a.DOCDATE ASC;

-- Dynamics GP: List sales orders and line items
SELECT
    h.SOPNUMBE,
    h.ORDDDATE,
    h.DUEDATE,
    h.CUSTCLAS,
    l.CMPNTSEQ,
    l.ITEMNMBR,
    l.ITEMDESC,
    l.QUANTITY,
    l.QTYPKDD,
    l.EXTDCOST
FROM SOP10100 h  -- SO Header
INNER JOIN SOP10200 l ON h.SOPNUMBE = l.SOPNUMBE  -- SO Line Items
WHERE h.SOPTYPE = 1  -- Order type
ORDER BY h.DUEDATE ASC, h.ORDDDATE ASC, l.LNITMSEQ ASC;
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| Table names prefixed with module code (SY, GL, RM, SOP) | Use WHERE TABLE_NAME LIKE 'SOP%' to filter module |
| Company record stored in SY00100 (Company Master) | All tables multi-company; join to company table to filter |
| DEV_* tables for temporary development | Exclude from discovery: WHERE TABLE_NAME NOT LIKE 'DEV_%' |
| User fields (GLUSTFxx, etc.) sparse and poorly documented | Contact GP admin for field definitions |
| Batch-based GL entry process | Don't query GLJrnl mid-batch; query GL00200 (posted) instead |
| Posting sequence determines GL order | Don't assume sequential ordering by JRNLNO |
| Multicurrency transactions (GL00203, etc.) | Handle currency codes in WHERE clause |

### 3.10 IBM i / AS/400

**Detection:**
- SQL_DBMS_NAME = "DB2"
- SQL_DRIVER_NAME contains "DB2 ODBC" or "libdb400"
- Library = Schema concept (e.g., MYAPP_LIB.CUST, MYAPP_LIB.ORD)
- QSYS2 = system catalog (special library)

**System Metadata Tables:**

```sql
-- QSYS2.SYSTABLES: Table discovery
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    CREATED,
    ALTERED
FROM QSYS2.SYSTABLES
WHERE TABLE_SCHEMA IN ('MYAPP_LIB', 'CUSTLIB', 'ORDLIB')
  AND TABLE_TYPE = 'TABLE'
ORDER BY TABLE_SCHEMA, TABLE_NAME;

-- QSYS2.SYSCOLUMNS: Column metadata
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_DEFAULT,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE
FROM QSYS2.SYSCOLUMNS
WHERE TABLE_SCHEMA = 'MYAPP_LIB'
  AND TABLE_NAME = 'CUSTOMER'
ORDER BY ORDINAL_POSITION;

-- QSYS2.SYSREFCST: Foreign key constraints
SELECT
    CONSTRAINT_CATALOG,
    CONSTRAINT_SCHEMA,
    CONSTRAINT_NAME,
    TABLE_SCHEMA,
    TABLE_NAME,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    RELATIONSHIP_ID,
    UPDATE_RULE,
    DELETE_RULE,
    CONSTRAINT_ENFORCED
FROM QSYS2.SYSREFCST
WHERE TABLE_SCHEMA = 'MYAPP_LIB'
  AND TABLE_NAME = 'ORDERS'
ORDER BY CONSTRAINT_NAME;

-- QSYS2.SYSKEYCST: Primary key constraints
SELECT
    CONSTRAINT_CATALOG,
    CONSTRAINT_SCHEMA,
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION
FROM QSYS2.SYSKEYCST
WHERE TABLE_SCHEMA = 'MYAPP_LIB'
  AND TABLE_NAME = 'CUSTOMER'
  AND CONSTRAINT_TYPE = 'PRIMARY KEY'
ORDER BY ORDINAL_POSITION;

-- QSYS2.SYSINDEXES: Index metadata
SELECT
    INDEX_CATALOG,
    INDEX_SCHEMA,
    INDEX_NAME,
    TABLE_SCHEMA,
    TABLE_NAME,
    UNIQUE_INDEX,
    INDEX_TYPE,
    CREATED
FROM QSYS2.SYSINDEXES
WHERE TABLE_SCHEMA = 'MYAPP_LIB'
  AND TABLE_NAME = 'ORDERS'
ORDER BY INDEX_NAME;

-- QSYS2.SYSINDEXCOLS: Index column mapping
SELECT
    INDEX_CATALOG,
    INDEX_SCHEMA,
    INDEX_NAME,
    COLUMN_NAME,
    ORDINAL_POSITION,
    SORT_SEQUENCE
FROM QSYS2.SYSINDEXCOLS
WHERE INDEX_SCHEMA = 'MYAPP_LIB'
  AND INDEX_NAME = 'ORDIX1'
ORDER BY ORDINAL_POSITION;
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| Library name = SQL schema; must specify LIBL(library1, library2...) in connection | Use -l option in ODBC DSN or connection string |
| QSYS2.* views require special permissions | Ensure login has access to QSYS2 library |
| Date/time formats vary by system (MDY, DMY, YMD) | Explicitly convert using CAST(col AS DATE FORMAT 'YYYY-MM-DD') |
| Physical files (record-oriented) appear in SYSTABLES | Filter by TABLE_TYPE = 'TABLE' for SQL tables only |
| Member concept (multiple data members per file) | Join to QSYS2.SYSMEMBERS for member details |
| Logical files (SQL views) may have outdated catalogs | Run REFRESH TABLE QSYS2.SYSMEMBERS to update |
| EBCDIC encoding can break ODBC results | Use UTF-8 CCSID in connection (CCSID=1208) |
| Record length limits (32K per record) | Design for wide fact tables carefully |
| Journal Recovery (before image logging) overhead | Plan batch refresh during off-peak hours |

### 3.11 QuickBooks QODBC

**Detection:**
- SQL_DBMS_NAME = "QuickBooks"
- SQL_DRIVER_NAME contains "QODBC"
- ODBC catalog functions unavailable; **stored procedures only**
- sp_tables, sp_columns, sp_primaryKeys, sp_foreignKeys

**Stored Procedure Discovery:**

```sql
-- QuickBooks QODBC: List all tables via stored procedure
CALL sp_tables();
-- Returns: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, TABLE_TYPE, REMARKS

-- QuickBooks QODBC: List columns for specific table
CALL sp_columns('Customer');
-- Returns: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, COLUMN_NAME, DATA_TYPE, TYPE_NAME, COLUMN_SIZE, DECIMAL_DIGITS, NULLABLE, REMARKS

-- QuickBooks QODBC: Get primary keys
CALL sp_primaryKeys('Customer');
-- Returns: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, COLUMN_NAME, KEY_SEQ, PK_NAME

-- QuickBooks QODBC: Get foreign keys
CALL sp_foreignKeys('Invoice');
-- Returns: PKTABLE_CAT, PKTABLE_SCHEM, PKTABLE_NAME, PKCOLUMN_NAME, FKTABLE_CAT, FKTABLE_SCHEM, FKTABLE_NAME, FKCOLUMN_NAME, KEY_SEQ, UPDATE_RULE, DELETE_RULE, FK_NAME, PK_NAME

-- Core QuickBooks tables (accessible via QODBC):
-- Customer, Item, Invoice, SalesReceipt, Check, Bill, BillPaymentCheck,
-- CreditMemo, Estimate, PurchaseOrder, Transfer, Deposit, JournalEntry,
-- TimeTracking, Account, Class, Department, Employee, Vendor, etc.

-- Example: Query past-due invoices (QuickBooks-specific)
SELECT
    ListID,
    RefNumber,
    TxnDate,
    DueDate,
    CustomerRef,
    Memo,
    TotalAmount,
    AmountDue
FROM Invoice
WHERE DueDate < TODAY()
  AND IsPending = 0
ORDER BY DueDate ASC;
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| Stored procedures only; no direct SQL queries | Use sp_* procedures for schema metadata |
| ListID is unique record identifier; RefNumber is user-visible | Join on ListID; use RefNumber for display |
| QuickBooks company file locking during ODBC queries | Schedule discovery off-peak; ensure file open in single instance |
| Inactive records included by default | Filter with IsActive = 1 in WHERE clause |
| Date range queries via ODBC slow on large files | Use QuickBooks Web Connect API for large data extracts |
| Currency handling implicit; no multi-currency in QODBC | Convert via QuickBooks API if needed |
| Custom fields (UserDefined1, UserDefined2, etc.) sparse | Query with IS NOT NULL filter; not all records have values |
| Batch operations (bulk updates) not supported via ODBC | Update via QuickBooks API only |

### 3.12 Sage 100 (ProvideX)

**Detection:**
- SQL_DBMS_NAME = "ProvideX"
- SQL_DRIVER_NAME contains "ProvideX" or "oleprvx"
- **No SQL query support; ODBC catalog functions only**
- cursor.tables(), cursor.columns(), cursor.primaryKeys(), cursor.foreignKeys() work
- ProvideX file-based data; no traditional SQL

**ODBC Catalog Discovery (Only Method):**

```python
import pyodbc

# Sage 100 (ProvideX): ODBC catalog functions ONLY
# Direct SQL queries DO NOT WORK

conn = pyodbc.connect('DSN=Sage100;UID=admin;PWD=password')
cursor = conn.cursor()

# List all tables
cursor.tables()
# Returns: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, TABLE_TYPE, REMARKS
for row in cursor.tables():
    print(f"Table: {row.table_name}")

# List columns (for each table returned above)
cursor.columns(table='AR_Customer')
# Returns: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, COLUMN_NAME, DATA_TYPE, TYPE_NAME, COLUMN_SIZE, DECIMAL_DIGITS, NULLABLE, REMARKS
for row in cursor.columns(table='AR_Customer'):
    print(f"Column: {row.column_name}, Type: {row.type_name}")

# Get primary keys
cursor.primaryKeys(table='AR_Customer')
# Returns: TABLE_CAT, TABLE_SCHEM, TABLE_NAME, COLUMN_NAME, KEY_SEQ, PK_NAME
for row in cursor.primaryKeys(table='AR_Customer'):
    print(f"PK: {row.column_name}")

# Get foreign keys (if available)
cursor.foreignKeys(table='AR_Invoice')
# Returns: PKTABLE_CAT, PKTABLE_SCHEM, PKTABLE_NAME, PKCOLUMN_NAME, FKTABLE_CAT, FKTABLE_SCHEM, FKTABLE_NAME, FKCOLUMN_NAME, KEY_SEQ
for row in cursor.foreignKeys(table='AR_Invoice'):
    print(f"FK: {row.fkcolumn_name} -> {row.pktable_name}.{row.pkcolumn_name}")

# Sage 100 core tables (typical):
# AR_Customer: Customer master
# AR_Invoice: Customer invoices
# AR_InvoiceDetail: Invoice line items
# OE_SalesOrder: Sales orders
# OE_SalesOrderDetail: SO line items
# IM_Item: Item master
# IM_Inventory: On-hand inventory
# AP_Vendor: Vendor master
# AP_Invoice: Vendor invoices
# AP_InvoiceDetail: Vendor invoice details
# PO_PurchaseOrder: PO header
# PO_PurchaseOrderDetail: PO line items
```

**Known ODBC Issues:**

| Issue | Workaround |
|-------|-----------|
| No SQL support; catalog functions only | Build query layer in application; pre-fetch metadata |
| ProvideX file-based storage | Large result sets slow; implement pagination |
| Concurrent user limits (file locking) | Limit ODBC query frequency; batch during off-peak |
| Date format ambiguity | Explicit CONVERT in application; confirm with Sage |
| Decimal precision varies by field | Use NUMERIC(18,6) mapping in application layer |
| No views or calculated fields | Implement in application BI layer |
| Limited sorting/filtering at driver level | Sort/filter in application after result fetch |
| Custom fields sparse across records | Query with IS NOT NULL; handle missing values in application |

---

## 4. Schema Drift Detection

### 4.1 Snapshot Comparison

Store baseline schema snapshot; compare on refresh to detect changes.

```python
import json
import hashlib
from datetime import datetime
from typing import Dict, List

class SchemaDriftDetector:
    def __init__(self, system: str, connection_string: str):
        self.system = system
        self.conn_str = connection_string
        self.baseline_file = f"schema_baseline_{system}.json"
        self.drift_log_file = f"schema_drift_{system}.log"

    def snapshot_schema(self) -> Dict:
        """Capture complete schema state"""
        snapshot = {
            'timestamp': datetime.utcnow().isoformat(),
            'system': self.system,
            'tables': {},
            'checksum': None,
        }

        # Discover schema (using per-system methods from Section 3)
        # For brevity, pseudocode here; implement per-system
        discovery = self.discover_schema()

        for table_name, table_info in discovery['tables'].items():
            snapshot['tables'][table_name] = {
                'columns': table_info['columns'],
                'column_names_hash': hashlib.md5(
                    json.dumps(list(table_info['columns'].keys()), sort_keys=True).encode()
                ).hexdigest(),
                'column_count': len(table_info['columns']),
                'pk': table_info['pk'],
                'indexes': table_info['indexes'],
            }

        # Global checksum over all tables
        snapshot['checksum'] = hashlib.md5(
            json.dumps(snapshot['tables'], sort_keys=True).encode()
        ).hexdigest()

        return snapshot

    def load_baseline(self) -> Dict:
        """Load previously saved baseline"""
        try:
            with open(self.baseline_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def save_baseline(self, snapshot: Dict):
        """Persist snapshot as new baseline"""
        with open(self.baseline_file, 'w') as f:
            json.dump(snapshot, f, indent=2)

    def detect_drift(self, current: Dict, baseline: Dict) -> Dict:
        """Compare baseline to current; flag differences"""
        drift = {
            'detected': False,
            'timestamp': datetime.utcnow().isoformat(),
            'checksum_match': current['checksum'] == baseline['checksum'],
            'tables_added': [],
            'tables_removed': [],
            'tables_modified': [],
            'drift_details': [],
        }

        current_tables = set(current['tables'].keys())
        baseline_tables = set(baseline['tables'].keys())

        # New tables
        for table_name in current_tables - baseline_tables:
            drift['detected'] = True
            drift['tables_added'].append(table_name)
            drift['drift_details'].append({
                'type': 'TABLE_ADDED',
                'table': table_name,
                'column_count': current['tables'][table_name]['column_count'],
            })

        # Removed tables
        for table_name in baseline_tables - current_tables:
            drift['detected'] = True
            drift['tables_removed'].append(table_name)
            drift['drift_details'].append({
                'type': 'TABLE_REMOVED',
                'table': table_name,
            })

        # Modified tables
        for table_name in current_tables & baseline_tables:
            current_table = current['tables'][table_name]
            baseline_table = baseline['tables'][table_name]

            if current_table['column_names_hash'] != baseline_table['column_names_hash']:
                drift['detected'] = True
                drift['tables_modified'].append(table_name)

                # Determine what changed
                current_cols = set(current_table['columns'].keys())
                baseline_cols = set(baseline_table['columns'].keys())

                added_cols = current_cols - baseline_cols
                removed_cols = baseline_cols - current_cols

                drift['drift_details'].append({
                    'type': 'TABLE_SCHEMA_CHANGE',
                    'table': table_name,
                    'columns_added': list(added_cols),
                    'columns_removed': list(removed_cols),
                    'column_count_before': baseline_table['column_count'],
                    'column_count_after': current_table['column_count'],
                })

        return drift

    def log_drift(self, drift: Dict):
        """Write drift report to log"""
        with open(self.drift_log_file, 'a') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"Drift Detection Report: {drift['timestamp']}\n")
            f.write(f"System: {self.system}\n")
            f.write(f"Checksum Match: {drift['checksum_match']}\n")
            f.write(f"Detected: {drift['detected']}\n")
            f.write(f"\nAdded Tables: {len(drift['tables_added'])}\n")
            for table in drift['tables_added']:
                f.write(f"  + {table}\n")
            f.write(f"\nRemoved Tables: {len(drift['tables_removed'])}\n")
            for table in drift['tables_removed']:
                f.write(f"  - {table}\n")
            f.write(f"\nModified Tables: {len(drift['tables_modified'])}\n")
            for detail in drift['drift_details']:
                if detail['type'] == 'TABLE_SCHEMA_CHANGE':
                    f.write(f"  ~ {detail['table']}\n")
                    if detail['columns_added']:
                        f.write(f"      Added: {', '.join(detail['columns_added'])}\n")
                    if detail['columns_removed']:
                        f.write(f"      Removed: {', '.join(detail['columns_removed'])}\n")
```

### 4.2 System-Specific Change Tracking

Leverage native change tracking features (where available).

```sql
-- SQL Server: Enable Change Tracking on database
ALTER DATABASE MyDatabase SET CHANGE_TRACKING = ON (CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON);

-- SQL Server: Enable Change Tracking on table
ALTER TABLE Orders ENABLE CHANGE_TRACKING WITH (TRACK_COLUMNS_UPDATED = ON);

-- SQL Server: Query changes since last sync
SELECT
    ct.CT_ID,
    ct.SYS_CHANGE_OPERATION,  -- Insert (I), Update (U), Delete (D)
    ct.SYS_CHANGE_VERSION,
    ct.SYS_CHANGE_CONTEXT,
    o.OrderID,
    o.OrderDate,
    o.Amount
FROM CHANGETABLE(CHANGES Orders, @LastSync) ct
LEFT JOIN Orders o ON ct.OrderID = o.OrderID
ORDER BY ct.SYS_CHANGE_VERSION;

-- PostgreSQL: Query audit table (manual setup required)
CREATE TABLE orders_audit (
    audit_id SERIAL PRIMARY KEY,
    orderid INT,
    action VARCHAR(10),
    changed_at TIMESTAMP DEFAULT NOW(),
    changed_by VARCHAR(100),
    old_values JSONB,
    new_values JSONB
);

-- Oracle: Flashback queries to detect changes
SELECT
    *
FROM Orders
AS OF TIMESTAMP TRUNC(SYSDATE - 1)  -- As it was yesterday
MINUS
SELECT
    *
FROM Orders
AS OF TIMESTAMP TRUNC(SYSDATE);     -- Current state

-- SAP HANA: Query transaction log
SELECT
    log_id,
    transaction_id,
    table_name,
    operation,
    changed_at
FROM SYS.M_REDO_LOG_ENTRIES
WHERE table_name = 'ORDERS'
  AND changed_at > CURRENT_TIMESTAMP - INTERVAL '1' DAY;
```

### 4.3 NetSuite-Specific Drift Concerns

NetSuite custom fields, SuiteAnalytics table volatility, and performance monitoring.

```python
class NetSuiteDriftDetector(SchemaDriftDetector):
    """NetSuite-specific schema drift detection"""

    def detect_netsuite_changes(self) -> Dict:
        """Check for NetSuite-specific changes"""
        changes = {
            'custom_fields_added': [],
            'custom_fields_removed': [],
            'standard_fields_extended': [],
            'table_schema_changed': False,
            'suiteanalytics_version_changed': False,
        }

        # Check SuiteAnalytics Connect version
        cursor = self.get_cursor()
        try:
            cursor.execute("SELECT @@version")
            current_version = cursor.fetchone()[0]
            baseline = self.load_baseline()
            if baseline and baseline.get('suiteanalytics_version') != current_version:
                changes['suiteanalytics_version_changed'] = True
        except Exception as e:
            print(f"Warning: Could not check SuiteAnalytics version: {e}")

        # Check for custom fields (transaction + entity custom fields)
        cursor.execute("""
            SELECT
                TABLE_NAME,
                COLUMN_NAME,
                COLUMN_TYPE
            FROM OA_COLUMNS
            WHERE COLUMN_NAME LIKE '%custom%'
               OR COLUMN_NAME LIKE '%custcol%'
               OR COLUMN_NAME LIKE '%custentity%'
            ORDER BY TABLE_NAME, COLUMN_NAME
        """)

        current_custom_fields = {}
        for row in cursor.fetchall():
            table_name = row[0]
            if table_name not in current_custom_fields:
                current_custom_fields[table_name] = []
            current_custom_fields[table_name].append(row[1])

        baseline = self.load_baseline()
        if baseline and 'netsuite_custom_fields' in baseline:
            baseline_custom = baseline['netsuite_custom_fields']

            for table_name, fields in current_custom_fields.items():
                baseline_fields = baseline_custom.get(table_name, [])
                added = set(fields) - set(baseline_fields)
                removed = set(baseline_fields) - set(fields)

                if added:
                    changes['custom_fields_added'].extend([
                        {'table': table_name, 'field': f} for f in added
                    ])
                if removed:
                    changes['custom_fields_removed'].extend([
                        {'table': table_name, 'field': f} for f in removed
                    ])

        return changes

    def check_performance_regression(self) -> Dict:
        """Monitor query performance regression"""
        import time

        perf = {
            'test_queries': [],
        }

        # Slow queries to monitor in NetSuite
        slow_query_tests = [
            ("Transaction discovery", "SELECT COUNT(*) FROM Transaction"),
            ("TransactionLine discovery", "SELECT COUNT(*) FROM TransactionLine"),
            ("InventoryBalance discovery", "SELECT COUNT(*) FROM InventoryBalance"),
        ]

        for query_name, query in slow_query_tests:
            cursor = self.get_cursor()
            start = time.time()
            try:
                cursor.execute(query)
                cursor.fetchall()
                elapsed = time.time() - start
                perf['test_queries'].append({
                    'query': query_name,
                    'elapsed_seconds': elapsed,
                    'status': 'OK' if elapsed < 30 else 'SLOW',
                })
            except Exception as e:
                perf['test_queries'].append({
                    'query': query_name,
                    'error': str(e),
                    'status': 'ERROR',
                })

        return perf
```

---

## 5. Architecture Recommendations

### 5.1 Multi-Tier Detection Strategy Diagram

```
┌────────────────────────────────────────────────────────────┐
│                    Connection String                        │
│                  (DSN or connection URL)                     │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│           Tier 1: ODBC SQLGetInfo Probe                     │
│  - SQL_DBMS_NAME (fast, 100% reliable)                     │
│  - SQL_DRIVER_NAME (fingerprinting)                        │
│  - SQL_DBMS_VER (version detection)                        │
└────────────────────────┬───────────────────────────────────┘
                         │
           ┌─────────────┼─────────────┐
           │             │             │
        Exact    Version Range  Driver Fingerprint
       Match          Check        Ambiguity
           │             │             │
           ▼             ▼             ▼
     System ID   SQL Server?    Oracle or MySQL?
      Returned   15=2019/       Resolve via:
                  16=2022       - catalog/schema support
                  14=2017       - data type set
                  13=2016       - system catalog tables
                                │
                                ▼
        ┌───────────────────────────────────────────────────┐
        │    Tier 2: ODBC Catalog Functions Probe           │
        │  - cursor.tables() (list all tables)              │
        │  - cursor.columns() (sample first table)          │
        │  - Check for system catalog presence              │
        │    (SYS.*, pg_catalog.*, INFORMATION_SCHEMA)      │
        └───────────────────┬───────────────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
           No catalog   Schema-only   Full catalog
          (NetSuite)   (PostgreSQL)   (SQL Server)
              │             │             │
              ▼             ▼             ▼
        NeteSource    pg_catalog    sys.* or
        OA_TABLES     visible       INFORMATION_SCHEMA
              │             │             │
              └─────────────┼─────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────────────────┐
        │    Tier 3: System-Specific SQL Catalog Probe      │
        │  - Query system catalogs directly                 │
        │  - Detect special tables (OA_*, pg_*, sys.*)      │
        │  - Determine permission tier (USER/ALL/DBA)       │
        │  - Identify module prefixes (SY, GL, RM in GP)    │
        └───────────────────┬───────────────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
          Standard   ERP-Specific   Restricted
          Catalogs   Patterns       Catalogs
              │             │             │
              ▼             ▼             ▼
        INFORMATION_  B1 OITM/    DBA views
        SCHEMA        OCRD       only
        QSYS2.*       GP module  (Oracle,
        SYS.*         prefixes   DB2)
              │             │             │
              └─────────────┼─────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────────────────┐
        │         System Adapter Instantiation              │
        │    - Initialize with detected system              │
        │    - Configure per-system SQL/API access          │
        │    - Set capability flags (CTEs, transactions)    │
        │    - Return SystemAdapter instance                │
        └───────────────────────────────────────────────────┘
```

### 5.2 SystemAdapter Pattern

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pyodbc

class SystemAdapter(ABC):
    """Abstract adapter for ERP system metadata discovery"""

    def __init__(self, connection_string: str):
        self.conn_str = connection_string
        self.conn = pyodbc.connect(connection_string)
        self.cursor = self.conn.cursor()
        self.system_name = None
        self.capabilities = {}

    @abstractmethod
    def discover_tables(self, schema: Optional[str] = None) -> List[str]:
        """Discover all tables"""
        pass

    @abstractmethod
    def discover_columns(self, table_name: str) -> Dict:
        """Discover columns for table"""
        pass

    @abstractmethod
    def discover_relationships(self) -> List[Dict]:
        """Discover foreign key relationships"""
        pass

    @abstractmethod
    def detect_drift(self) -> Dict:
        """Detect schema drift since last snapshot"""
        pass


class NetSuiteAdapter(SystemAdapter):
    """NetSuite via SuiteAnalytics Connect"""

    def __init__(self, connection_string: str):
        super().__init__(connection_string)
        self.system_name = "NetSuite"
        self.capabilities = {
            'supports_cte': False,
            'supports_write': False,
            'max_columns_per_table': 1000,
            'supports_transactions': False,
            'supports_catalog': False,
            'supports_schema': True,
        }

    def discover_tables(self, schema: Optional[str] = None) -> List[str]:
        schema = schema or 'public'
        query = f"""
            SELECT TABLE_NAME FROM OA_TABLES
            WHERE TABLE_SCHEMA = '{schema}'
            ORDER BY TABLE_NAME
        """
        self.cursor.execute(query)
        return [row[0] for row in self.cursor.fetchall()]

    def discover_columns(self, table_name: str) -> Dict:
        query = f"""
            SELECT
                COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION,
                IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
            FROM OA_COLUMNS
            WHERE TABLE_NAME = '{table_name}'
            ORDER BY ORDINAL_POSITION
        """
        self.cursor.execute(query)
        columns = {}
        for row in self.cursor.fetchall():
            columns[row[0]] = {
                'type': row[1],
                'position': row[2],
                'nullable': row[3],
                'max_length': row[4],
            }
        return columns

    def discover_relationships(self) -> List[Dict]:
        # NetSuite exposes FKs via OA_FKEYS (if available)
        try:
            query = """
                SELECT
                    TABLE_NAME, COLUMN_NAME,
                    REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                FROM OA_FKEYS
                ORDER BY TABLE_NAME, CONSTRAINT_NAME
            """
            self.cursor.execute(query)
            relationships = []
            for row in self.cursor.fetchall():
                relationships.append({
                    'from_table': row[0],
                    'from_column': row[1],
                    'to_table': row[2],
                    'to_column': row[3],
                })
            return relationships
        except Exception:
            return []

    def detect_drift(self) -> Dict:
        # Implement NetSuite-specific drift detection
        detector = NetSuiteDriftDetector(self.system_name, self.conn_str)
        return detector.detect_netsuite_changes()


class SQLServerAdapter(SystemAdapter):
    """Microsoft SQL Server"""

    def __init__(self, connection_string: str):
        super().__init__(connection_string)
        self.system_name = "SQL Server"
        self.capabilities = {
            'supports_cte': True,
            'supports_write': True,
            'supports_transactions': True,
            'supports_catalog': True,
            'supports_schema': True,
        }

    def discover_tables(self, schema: Optional[str] = None) -> List[str]:
        schema = schema or 'dbo'
        query = f"""
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = '{schema}' AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """
        self.cursor.execute(query)
        return [row[0] for row in self.cursor.fetchall()]

    def discover_columns(self, table_name: str) -> Dict:
        query = f"""
            SELECT
                COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION,
                IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{table_name}'
            ORDER BY ORDINAL_POSITION
        """
        self.cursor.execute(query)
        columns = {}
        for row in self.cursor.fetchall():
            columns[row[0]] = {
                'type': row[1],
                'position': row[2],
                'nullable': row[3],
                'max_length': row[4],
            }
        return columns

    def discover_relationships(self) -> List[Dict]:
        query = """
            SELECT
                fk.name, OBJECT_NAME(fk.parent_object_id),
                COL_NAME(fkc.parent_object_id, fkc.parent_column_id),
                OBJECT_NAME(fk.referenced_object_id),
                COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id)
            FROM sys.foreign_keys fk
            INNER JOIN sys.foreign_key_columns fkc
                ON fk.object_id = fkc.constraint_object_id
            ORDER BY OBJECT_NAME(fk.parent_object_id)
        """
        self.cursor.execute(query)
        relationships = []
        for row in self.cursor.fetchall():
            relationships.append({
                'name': row[0],
                'from_table': row[1],
                'from_column': row[2],
                'to_table': row[3],
                'to_column': row[4],
            })
        return relationships

    def detect_drift(self) -> Dict:
        # SQL Server Change Tracking
        query = """
            SELECT OBJECT_NAME(ct.object_id), ct.SYS_CHANGE_OPERATION
            FROM CHANGETABLE(CHANGES Orders, 0) ct
        """
        try:
            self.cursor.execute(query)
            changes = self.cursor.fetchall()
            return {'detected': len(changes) > 0, 'changes': changes}
        except Exception:
            return {'detected': False, 'error': 'Change Tracking not enabled'}


# ... similar adapters for PostgreSQL, Oracle, MySQL, SAP HANA, etc.
```

### 5.3 Adapter Registry & Detection Priority

```python
from typing import Optional

class SystemAdapterRegistry:
    """Central registry for ERP system adapters"""

    # Detection priority: higher = check first
    ADAPTERS = [
        # Tier 1: 100% reliable detection by DBMS name
        {
            'name': 'NetSuite',
            'dbms_name': 'NetSuite',
            'adapter': NetSuiteAdapter,
            'priority': 100,
        },
        {
            'name': 'QuickBooks',
            'dbms_name': 'QuickBooks',
            'adapter': QuickBooksAdapter,
            'priority': 100,
        },

        # Tier 2: Version-specific detection (SQL Server, Oracle, PostgreSQL)
        {
            'name': 'SQL Server 2022',
            'dbms_name': 'SQL Server',
            'dbms_ver_pattern': r'^16\.',
            'adapter': SQLServerAdapter,
            'priority': 90,
        },
        {
            'name': 'SQL Server 2019',
            'dbms_name': 'SQL Server',
            'dbms_ver_pattern': r'^15\.',
            'adapter': SQLServerAdapter,
            'priority': 90,
        },
        {
            'name': 'Oracle 19c',
            'dbms_name': 'Oracle',
            'dbms_ver_pattern': r'^19\.',
            'adapter': OracleAdapter,
            'priority': 90,
        },
        {
            'name': 'PostgreSQL',
            'dbms_name': 'PostgreSQL',
            'adapter': PostgreSQLAdapter,
            'priority': 90,
        },

        # Tier 3: ERP-specific detection (B1, GP, NAV, BC)
        {
            'name': 'SAP Business One',
            'dbms_name': 'SQL Server',
            'marker_tables': ['OITM', 'OCRD', 'ORDR'],
            'adapter': BusinessOneAdapter,
            'priority': 80,
        },
        {
            'name': 'Dynamics GP',
            'dbms_name': 'SQL Server',
            'table_prefix_pattern': r'^[A-Z]{2}\d+$',  # SY00100, GL00100, etc.
            'adapter': DynamicsGPAdapter,
            'priority': 80,
        },
        {
            'name': 'Dynamics NAV',
            'dbms_name': 'SQL Server',
            'table_pattern': r'^[A-Za-z0-9_]+\$[A-Z]',  # Company$Table
            'adapter': DynamicsNAVAdapter,
            'priority': 80,
        },

        # Tier 4: MySQL/MariaDB detection
        {
            'name': 'MySQL 8.0',
            'dbms_name': 'MySQL',
            'dbms_ver_pattern': r'^8\.',
            'adapter': MySQLAdapter,
            'priority': 90,
        },
        {
            'name': 'MariaDB',
            'dbms_name': 'MariaDB',
            'adapter': MariaDBAdapter,
            'priority': 90,
        },

        # Fallback: ODBC catalog functions only
        {
            'name': 'Sage 100 (ProvideX)',
            'dbms_name': 'ProvideX',
            'adapter': Sage100Adapter,
            'priority': 50,
        },
    ]

    @staticmethod
    def detect(connection_string: str) -> Optional[SystemAdapter]:
        """Auto-detect ERP system and return appropriate adapter"""
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()

        # Fetch detection info
        dbms_name = conn.getinfo(pyodbc.SQL_DBMS_NAME)
        dbms_ver = conn.getinfo(pyodbc.SQL_DBMS_VER)
        driver_name = conn.getinfo(pyodbc.SQL_DRIVER_NAME)

        print(f"Detection: DBMS={dbms_name}, Ver={dbms_ver}, Driver={driver_name}")

        # Sort by priority (higher = check first)
        candidates = sorted(
            SystemAdapterRegistry.ADAPTERS,
            key=lambda x: x['priority'],
            reverse=True
        )

        for candidate in candidates:
            if candidate['dbms_name'].lower() != dbms_name.lower():
                continue

            # Check version pattern if specified
            if 'dbms_ver_pattern' in candidate:
                import re
                if not re.match(candidate['dbms_ver_pattern'], dbms_ver):
                    continue

            # Check for marker tables (ERP detection)
            if 'marker_tables' in candidate:
                cursor.tables()
                table_names = [row[2] for row in cursor.fetchall()]
                if not all(t in table_names for t in candidate['marker_tables']):
                    continue

            # Check table naming pattern
            if 'table_pattern' in candidate:
                import re
                cursor.tables()
                table_names = [row[2] for row in cursor.fetchall()]
                matches = [t for t in table_names if re.match(candidate['table_pattern'], t)]
                if len(matches) < 5:  # Need multiple matches
                    continue

            # Match found; instantiate adapter
            print(f"Detected: {candidate['name']}")
            return candidate['adapter'](connection_string)

        # Fallback: generic ODBC adapter
        print("Warning: Could not detect specific ERP system; using generic ODBC adapter")
        return GenericODBCAdapter(connection_string)


# Usage
adapter = SystemAdapterRegistry.detect("DSN=MyNetSuite;UID=user;PWD=pass")
tables = adapter.discover_tables()
relationships = adapter.discover_relationships()
drift = adapter.detect_drift()
```

### 5.4 Metadata Caching Strategy

```python
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

class MetadataCache:
    """LRU cache for schema metadata across systems"""

    def __init__(self, cache_dir: str = "./metadata_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl_hours = 24  # Cache valid for 24 hours

    def cache_key(self, system: str, connection_string: str) -> str:
        """Generate cache key from system + connection"""
        key_str = f"{system}|{connection_string}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def cache_file(self, cache_key: str) -> Path:
        """Get cache file path"""
        return self.cache_dir / f"{cache_key}.json"

    def cache_valid(self, cache_file: Path) -> bool:
        """Check if cache file is still valid (not expired)"""
        if not cache_file.exists():
            return False

        modified_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
        age = datetime.utcnow() - modified_time

        return age < timedelta(hours=self.ttl_hours)

    def get(self, system: str, connection_string: str) -> Optional[Dict]:
        """Retrieve cached metadata if valid"""
        key = self.cache_key(system, connection_string)
        cache_file = self.cache_file(key)

        if not self.cache_valid(cache_file):
            return None

        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Cache read failed: {e}")
            return None

    def set(self, system: str, connection_string: str, metadata: Dict):
        """Store metadata in cache"""
        key = self.cache_key(system, connection_string)
        cache_file = self.cache_file(key)

        metadata['cached_at'] = datetime.utcnow().isoformat()

        try:
            with open(cache_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            print(f"Warning: Cache write failed: {e}")

    def invalidate(self, system: str, connection_string: str):
        """Force cache invalidation"""
        key = self.cache_key(system, connection_string)
        cache_file = self.cache_file(key)

        if cache_file.exists():
            cache_file.unlink()


# Usage
cache = MetadataCache()

adapter = SystemAdapterRegistry.detect(conn_str)

# Try cache first
cached = cache.get(adapter.system_name, conn_str)
if cached:
    metadata = cached
else:
    # Discover and cache
    metadata = {
        'tables': adapter.discover_tables(),
        'relationships': adapter.discover_relationships(),
    }
    cache.set(adapter.system_name, conn_str, metadata)
```

---

## Summary

This document provides complete ODBC-level system detection, per-system schema discovery SQL, and architecture patterns for multi-ERP metadata discovery. Key takeaways:

1. **Detection is hierarchical**: SQLGetInfo → ODBC catalog functions → system-specific SQL
2. **Each system has distinct limitations**: NetSuite no CTEs; Sage 100 no SQL; Oracle 3-tier privilege model
3. **Schema drift detection** must be system-aware (NetSuite custom fields; SQL Server Change Tracking)
4. **Adapter pattern** enables scalable multi-system support
5. **Caching** reduces discovery latency on subsequent connections

For NetSuite specifically: always prioritize OA_* tables (SuiteAnalytics native), check for 1000-column limits, and cache custom field metadata since it's frequently added post-deployment.
