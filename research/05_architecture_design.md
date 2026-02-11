# ODBC MCP Server — Architecture Design

Synthesized from research on MCP SDK patterns, existing implementations, pyodbc/driver landscape, and ERP schema detection.

---

## 1. Project Identity

**Name**: `mcp-odbc`
**Tagline**: Universal ODBC MCP server — connect any database, detect any schema, just works.
**License**: MIT
**Language**: Python 3.10+

---

## 2. Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| MCP Framework | `fastmcp` v2.x (pin `>=2.0,<3.0`) | Best DX, decorator-based, auto JSON Schema, auto-threads sync functions |
| ODBC Driver | `pyodbc` >=5.0 | Standard Python ODBC binding, 4k+ stars, C extension |
| Config Validation | `pydantic` >=2.0 | Typed config, env var support, validation |
| Transport | STDIO (primary) | Local process, no network exposure, Claude Code native |
| Packaging | `pyproject.toml` + `hatchling` | Modern Python packaging, `pip install` + `uvx` support |
| Testing | `pytest` + `pytest-asyncio` + FastMCP `Client` | In-process testing, no subprocess needed |

---

## 3. Tool Design

### Core Tools (Phase 1 — MVP)

| Tool | Parameters | Returns | Description |
|------|-----------|---------|-------------|
| `list_connections` | — | Markdown table | Show configured connections + active status |
| `list_dsns` | — | Markdown table | Enumerate system ODBC data sources |
| `test_connection` | `connection?` | Status + driver info | Validate connection, report DBMS type/version |
| `list_tables` | `connection?`, `schema?`, `table_type?` | Markdown table | List tables/views with optional filtering |
| `describe_table` | `table`, `connection?`, `schema?` | Markdown (columns, types, PKs, FKs) | Full column metadata for a table |
| `execute_query` | `query`, `connection?`, `max_rows?`, `format?` | Markdown table or JSON | Execute read-only SQL, return results |
| `get_primary_keys` | `table`, `connection?`, `schema?` | Markdown table | PK columns for a table |
| `get_foreign_keys` | `table`, `connection?`, `schema?` | Markdown table | FK relationships for a table |

### Extended Tools (Phase 2)

| Tool | Parameters | Returns | Description |
|------|-----------|---------|-------------|
| `get_indexes` | `table`, `connection?` | Markdown table | Index info for a table |
| `search_tables` | `pattern`, `connection?` | Markdown table | Substring/wildcard table search |
| `search_columns` | `pattern`, `connection?`, `table?` | Markdown table | Find columns by name across tables |
| `get_schema_snapshot` | `connection?`, `tables?` | JSON | Full schema export for drift detection |
| `check_schema_drift` | `connection?` | Drift report | Compare current schema against cached baseline |
| `diagnose` | — | Diagnostic report | Python bitness, drivers, DSNs, platform info |
| `get_sample_data` | `table`, `connection?`, `rows?` | Markdown table | Quick `SELECT TOP N *` for data preview |
| `get_system_info` | `connection?` | JSON | Detected DBMS, version, adapter, capabilities |

### Tool Design Principles

1. **snake_case, verb-noun**: `list_tables`, `execute_query`, `describe_table`
2. **Optional `connection` param**: defaults to configured default connection; enables multi-DB
3. **Docstrings = LLM instructions**: describe when to use, what params mean, what to expect
4. **Markdown by default**: tables formatted for LLM consumption; JSON option for programmatic use
5. **`format` param on execute_query**: `"markdown"` (default) or `"json"`
6. **`max_rows` with sane defaults**: 100 default, 10000 max, configurable per-connection

---

## 4. Architecture

### Module Structure

```
mcp-odbc/
+-- pyproject.toml              # Package config, dependencies, entry point
+-- README.md                   # Usage docs
+-- LICENSE                     # MIT
+-- src/
|   +-- mcp_odbc/
|       +-- __init__.py
|       +-- server.py           # FastMCP server, tool registration, entry point
|       +-- connection.py       # ConnectionManager: lifecycle, health checks, pooling
|       +-- config.py           # Pydantic models, config loading (env/INI/JSON)
|       +-- query.py            # Query execution, read-only enforcement, formatting
|       +-- metadata.py         # Schema discovery, caching, drift detection
|       +-- detection.py        # DBMS detection, adapter registry
|       +-- formatting.py       # Output formatting (markdown tables, JSON, truncation)
|       +-- adapters/
|       |   +-- __init__.py     # Adapter registry + get_adapter()
|       |   +-- base.py         # SystemAdapter ABC
|       |   +-- generic.py      # GenericODBCAdapter (ODBC catalog functions fallback)
|       |   +-- netsuite.py     # NetSuite (OA_TABLES, OA_COLUMNS, OA_FKEYS)
|       |   +-- mssql.py        # SQL Server (sys.* views)
|       |   +-- postgresql.py   # PostgreSQL (pg_catalog)
|       |   +-- mysql.py        # MySQL/MariaDB (INFORMATION_SCHEMA)
|       |   +-- oracle.py       # Oracle (ALL_* data dictionary)
|       |   +-- hana.py         # SAP HANA (SYS.* views)
|       |   +-- db2.py          # IBM i / DB2 (QSYS2.*)
|       |   +-- quickbooks.py   # QuickBooks QODBC (sp_tables/sp_columns)
|       |   +-- sage.py         # Sage/ProvideX (ODBC catalog only)
|       +-- errors.py           # Error handling, SQLSTATE mapping, sanitization
+-- tests/
|   +-- test_server.py          # Tool-level integration tests via FastMCP Client
|   +-- test_connection.py      # Connection manager unit tests
|   +-- test_config.py          # Config loading/validation tests
|   +-- test_detection.py       # DBMS detection tests
|   +-- test_formatting.py      # Output formatting tests
|   +-- test_adapters.py        # Adapter-specific tests (mocked)
+-- config/
|   +-- config.example.ini      # Example INI config
+-- research/                   # This research folder
```

### Dependency Graph

```
server.py (entry point, tool definitions)
  +-- config.py (loads settings)
  +-- connection.py (manages ODBC connections)
  |     +-- detection.py (identifies DBMS type)
  |     +-- errors.py (connection error handling)
  +-- metadata.py (schema discovery + caching)
  |     +-- adapters/ (system-specific metadata queries)
  |     |     +-- base.py (ABC)
  |     |     +-- generic.py (ODBC fallback)
  |     |     +-- netsuite.py, mssql.py, ... (specific)
  |     +-- detection.py (selects correct adapter)
  +-- query.py (SQL execution)
  |     +-- formatting.py (result formatting)
  |     +-- errors.py (query error handling)
  +-- formatting.py (markdown/JSON output)
```

---

## 5. Connection Management

### Design: Named Multi-Connection with Lazy Loading

Borrowed from tylerstoltz/mcp-odbc (best pattern found), enhanced with explicit lifecycle and no ODBC pooling.

```python
# Conceptual design — not final implementation

pyodbc.pooling = False  # Disable ODBC-level pooling, manage explicitly

class ConnectionManager:
    """Manages named ODBC connections with lazy loading and health checks."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self._connections: dict[str, pyodbc.Connection] = {}

    def get(self, name: str | None = None) -> pyodbc.Connection:
        """Get connection by name (or default). Lazy-creates on first use."""
        name = name or self.config.default_connection
        conn_config = self.config.connections[name]

        if name in self._connections:
            if self._health_check(self._connections[name]):
                return self._connections[name]
            # Stale — close and recreate
            self._close(name)

        cnxn = pyodbc.connect(
            conn_config.connection_string,
            autocommit=True,
            timeout=conn_config.connect_timeout,
            readonly=conn_config.readonly,
        )
        cnxn.timeout = conn_config.query_timeout
        self._apply_encoding(cnxn, conn_config)
        self._connections[name] = cnxn
        return cnxn

    def _health_check(self, cnxn: pyodbc.Connection) -> bool:
        try:
            cnxn.execute("SELECT 1")
            return True
        except (pyodbc.Error, AttributeError):
            return False

    def _apply_encoding(self, cnxn, config):
        """Apply driver-specific encoding settings."""
        dbms = cnxn.getinfo(pyodbc.SQL_DBMS_NAME).lower()
        if 'mysql' in dbms or 'postgresql' in dbms:
            cnxn.setencoding(encoding='utf-8')
            cnxn.setdecoding(pyodbc.SQL_WCHAR, encoding='utf-8')

    def close_all(self):
        for name in list(self._connections):
            self._close(name)
```

### Read-Only Enforcement (3 layers)

1. **ODBC level**: `pyodbc.connect(..., readonly=True)` sets `SQL_ACCESS_MODE = SQL_MODE_READ_ONLY`
2. **SQL validation**: Reject non-SELECT statements (check after comment stripping)
3. **Per-connection config**: `readonly = true/false` in config file

Layer 1 is the strongest — it's enforced by the ODBC driver itself. Layer 2 catches edge cases where drivers don't fully honor the ODBC attribute. Layer 3 allows opt-out for specific connections (e.g., staging DBs where writes are acceptable).

### Connection Health Checks

- Test with `SELECT 1` before returning cached connection
- On failure: close stale connection, create fresh one
- Transparent to caller — health check is internal

---

## 6. Configuration

### Config Sources (precedence order)

1. Environment variables (highest priority — for Claude Code `.mcp.json`)
2. Config file path from `ODBC_MCP_CONFIG` env var
3. INI file at `./config/config.ini` (default)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ODBC_DSN` | — | Default DSN (shortcut for single-connection setup) |
| `ODBC_CONNECTION_STRING` | — | Full connection string (overrides DSN) |
| `ODBC_READ_ONLY` | `true` | Read-only mode |
| `ODBC_MAX_ROWS` | `10000` | Global max rows |
| `ODBC_QUERY_TIMEOUT` | `30` | Query timeout (seconds) |
| `ODBC_CONNECT_TIMEOUT` | `10` | Connection timeout (seconds) |
| `ODBC_MCP_CONFIG` | — | Path to config file |
| `ODBC_CACHE_TTL` | `300` | Schema cache TTL (seconds) |

### INI Config (multi-connection)

```ini
[server]
default_connection = netsuite
max_rows = 10000
cache_ttl = 300

[netsuite]
connection_string = DSN=NetSuite;UID=user@co.com;PWD=secret
readonly = true
query_timeout = 60
connect_timeout = 15

[staging_sql]
connection_string = DRIVER={ODBC Driver 18 for SQL Server};SERVER=staging;DATABASE=erp;UID=sa;PWD=secret
readonly = false
query_timeout = 30
connect_timeout = 5
```

### Pydantic Config Models

```python
class ConnectionConfig(BaseModel):
    connection_string: str
    readonly: bool = True
    query_timeout: int = 30
    connect_timeout: int = 10
    max_rows: int = 10000

class ServerConfig(BaseModel):
    default_connection: str
    connections: dict[str, ConnectionConfig]
    cache_ttl: int = 300
    max_rows: int = 10000
```

### Claude Code Integration

```json
// .mcp.json (project-scoped)
{
  "mcpServers": {
    "odbc": {
      "command": "python",
      "args": ["-m", "mcp_odbc"],
      "env": {
        "ODBC_DSN": "${ODBC_DSN}",
        "ODBC_READ_ONLY": "true"
      }
    }
  }
}
```

Or with config file:
```json
{
  "mcpServers": {
    "odbc": {
      "command": "python",
      "args": ["-m", "mcp_odbc"],
      "env": {
        "ODBC_MCP_CONFIG": "${HOME}/odbc-mcp-config.ini"
      }
    }
  }
}
```

---

## 7. DBMS Detection & Adapter System

### Detection Strategy (3-tier)

```
Tier 1: ODBC SQLGetInfo (instant, no queries)
  connection.getinfo(SQL_DBMS_NAME)  -> "Microsoft SQL Server", "NetSuite", etc.
  connection.getinfo(SQL_DRIVER_NAME) -> driver DLL/SO filename

Tier 2: Probe Queries (when Tier 1 is ambiguous)
  SQL Server: SELECT @@VERSION
  NetSuite:   SELECT COUNT(*) FROM OA_TABLES
  Oracle:     SELECT * FROM V$VERSION WHERE ROWNUM = 1
  HANA:       SELECT VERSION FROM SYS.M_DATABASE

Tier 3: ODBC Catalog Fallback (always works)
  cursor.tables(), cursor.columns(), etc.
```

### Known SQL_DBMS_NAME Values

| DBMS | SQL_DBMS_NAME |
|------|---------------|
| SQL Server | `"Microsoft SQL Server"` |
| PostgreSQL | `"PostgreSQL"` |
| MySQL | `"MySQL"` |
| MariaDB | `"MySQL"` (version reveals MariaDB) |
| Oracle | `"Oracle"` |
| SAP HANA | `"HDB"` |
| NetSuite | `"NetSuite"` |
| DB2 (LUW) | `"DB2/LINUX"`, `"DB2/NT"` |
| DB2 for i | `"DB2"`, `"AS"` |
| Snowflake | `"Snowflake"` |
| Access | `"ACCESS"` |

### Adapter Pattern

```python
class SystemAdapter(ABC):
    """Base for system-specific metadata operations."""

    name: str  # e.g., "netsuite", "mssql"
    display_name: str  # e.g., "NetSuite SuiteAnalytics", "Microsoft SQL Server"

    @staticmethod
    @abstractmethod
    def detect(connection: pyodbc.Connection) -> bool:
        """Return True if this adapter matches the connection."""

    @abstractmethod
    def get_tables(self, cursor, schema=None, table_type=None) -> list[dict]: ...

    @abstractmethod
    def get_columns(self, cursor, table, schema=None) -> list[dict]: ...

    def get_primary_keys(self, cursor, table, schema=None) -> list[dict]:
        """Default: use ODBC catalog function."""
        cursor.primaryKeys(table=table, schema=schema)
        return [_row_to_dict(r) for r in cursor.fetchall()]

    def get_foreign_keys(self, cursor, table, schema=None) -> list[dict]:
        """Default: use ODBC catalog function."""
        cursor.foreignKeys(table=table, schema=schema)
        return [_row_to_dict(r) for r in cursor.fetchall()]

    def apply_connection_settings(self, connection):
        """Apply system-specific settings after connect (encoding, etc.)."""
        pass

    def get_sql_capabilities(self) -> dict:
        """Return SQL dialect info (supports_cte, supports_limit, etc.)."""
        return {'supports_cte': True, 'supports_limit': True,
                'read_only': False, 'max_concurrent': None}
```

### Adapter Registry

```python
ADAPTER_REGISTRY: list[type[SystemAdapter]] = [
    NetSuiteAdapter,      # "NetSuite" in SQL_DBMS_NAME or "nlodbcns" in driver
    SqlServerAdapter,     # "Microsoft SQL Server" in SQL_DBMS_NAME
    PostgreSQLAdapter,    # "PostgreSQL" in SQL_DBMS_NAME
    MySQLAdapter,         # "MySQL" in SQL_DBMS_NAME
    OracleAdapter,        # "Oracle" in SQL_DBMS_NAME
    HANAAdapter,          # "HDB" in SQL_DBMS_NAME
    DB2Adapter,           # "DB2" in SQL_DBMS_NAME
    QuickBooksAdapter,    # QODBC driver detection
    SageAdapter,          # ProvideX driver detection
    GenericODBCAdapter,   # ALWAYS LAST — universal fallback
]

def get_adapter(connection: pyodbc.Connection) -> SystemAdapter:
    for adapter_cls in ADAPTER_REGISTRY:
        if adapter_cls.detect(connection):
            return adapter_cls()
    return GenericODBCAdapter()
```

### Adapter Examples

**NetSuite** — Uses OA_TABLES/OA_COLUMNS/OA_FKEYS:
```python
class NetSuiteAdapter(SystemAdapter):
    name = "netsuite"
    display_name = "NetSuite SuiteAnalytics Connect"

    @staticmethod
    def detect(cnxn):
        dbms = cnxn.getinfo(pyodbc.SQL_DBMS_NAME)
        return 'netsuite' in dbms.lower()

    def get_tables(self, cursor, schema=None, table_type=None):
        cursor.execute("SELECT TABLE_NAME, TABLE_TYPE, DESCRIPTION FROM OA_TABLES")
        return [{'table_name': r[0], 'table_type': r[1], 'remarks': r[2]}
                for r in cursor.fetchall()]

    def get_columns(self, cursor, table, schema=None):
        cursor.execute(
            "SELECT COLUMN_NAME, OA_TYPE, OA_LENGTH, OA_PRECISION, "
            "OA_NULLABLE, DESCRIPTION FROM OA_COLUMNS WHERE TABLE_NAME = ?",
            [table]
        )
        return [{'column_name': r[0], 'type_name': r[1], 'column_size': r[2],
                 'precision': r[3], 'nullable': r[4], 'remarks': r[5]}
                for r in cursor.fetchall()]

    def get_foreign_keys(self, cursor, table, schema=None):
        cursor.execute(
            "SELECT TABLE_NAME, COLUMN_NAME, FK_TABLE_NAME, FK_COLUMN_NAME "
            "FROM OA_FKEYS WHERE TABLE_NAME = ?",
            [table]
        )
        return [{'table_name': r[0], 'column_name': r[1],
                 'ref_table': r[2], 'ref_column': r[3]}
                for r in cursor.fetchall()]

    def get_sql_capabilities(self):
        return {'supports_cte': False, 'supports_limit': False,
                'read_only': True, 'max_concurrent': 10}
```

**Generic ODBC** — Universal fallback using catalog functions:
```python
class GenericODBCAdapter(SystemAdapter):
    name = "generic"
    display_name = "Generic ODBC"

    @staticmethod
    def detect(cnxn):
        return True  # Always matches as last resort

    def get_tables(self, cursor, schema=None, table_type=None):
        cursor.tables(schema=schema, tableType=table_type or 'TABLE')
        return [{'catalog': r.table_cat, 'schema': r.table_schem,
                 'table_name': r.table_name, 'table_type': r.table_type,
                 'remarks': r.remarks}
                for r in cursor.fetchall()]

    def get_columns(self, cursor, table, schema=None):
        cursor.columns(table=table, schema=schema)
        return [{'column_name': r.column_name, 'type_name': r.type_name,
                 'column_size': r.column_size, 'nullable': r.nullable,
                 'remarks': getattr(r, 'remarks', None)}
                for r in cursor.fetchall()]
```

---

## 8. Metadata Caching & Schema Drift

### Cache Design

```python
class SchemaCache:
    """TTL-based cache for metadata results."""

    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        if key in self._store:
            value, ts = self._store[key]
            if time.time() - ts < self.ttl:
                return value
            del self._store[key]
        return None

    def set(self, key: str, value: Any):
        self._store[key] = (value, time.time())

    def invalidate(self, pattern: str | None = None):
        if pattern is None:
            self._store.clear()
        else:
            self._store = {k: v for k, v in self._store.items()
                           if pattern not in k}
```

Cache keys: `"{connection}:tables"`, `"{connection}:columns:{table}"`, `"{connection}:pks:{table}"`, etc.

### Schema Drift Detection

```python
def schema_hash(columns: list[dict]) -> str:
    """Deterministic hash of column metadata."""
    normalized = sorted(
        [(c['column_name'], c['type_name'], c.get('column_size'))
         for c in columns]
    )
    return hashlib.sha256(json.dumps(normalized).encode()).hexdigest()
```

- Capture hash on first metadata fetch
- Compare on subsequent fetches
- Report drift as part of `check_schema_drift` tool
- Optional: store snapshots to local JSON file for cross-session comparison

---

## 9. Query Execution & Safety

### Read-Only Pipeline

```
User query
  |
  v
1. Strip SQL comments (-- and /* */)
  |
  v
2. Check ODBC readonly flag is set on connection
  |
  v
3. Validate: must start with SELECT (or WITH for CTEs where supported)
  |
  v
4. Reject known write keywords: INSERT, UPDATE, DELETE, DROP, CREATE,
   ALTER, TRUNCATE, GRANT, REVOKE, MERGE, EXEC, CALL
  |
  v
5. Execute with fetchmany(max_rows)
  |
  v
6. Check for more rows (has_more flag)
  |
  v
7. Format output (markdown/JSON) with value truncation
```

### Value Truncation

Long column values (e.g., CLOBs, large text) are truncated to prevent context window blowout:

```python
MAX_VALUE_LENGTH = 500  # configurable

def truncate_value(val, max_len=MAX_VALUE_LENGTH):
    if val is None:
        return None
    s = str(val)
    if len(s) > max_len:
        return s[:max_len] + f"... ({len(s)} chars total)"
    return s
```

### Result Formatting

```python
def format_as_markdown(columns: list[str], rows: list[tuple],
                       has_more: bool = False) -> str:
    """Format query results as markdown table."""
    # Header
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"

    # Rows
    lines = [header, separator]
    for row in rows:
        values = [truncate_value(v) for v in row]
        lines.append("| " + " | ".join(str(v) for v in values) + " |")

    if has_more:
        lines.append(f"\n*Results truncated. More rows available.*")

    return "\n".join(lines)
```

---

## 10. Error Handling

### Strategy: SQLSTATE-aware, user-friendly, LLM-visible

```python
from fastmcp.exceptions import ToolError

SQLSTATE_MAP = {
    '08001': "Cannot connect to server. Check host/port and network.",
    '08S01': "Connection lost during operation. Try again.",
    '28000': "Authentication failed. Check credentials.",
    '42000': "SQL syntax error or access denied.",
    '42S02': "Table not found.",
    'HY000': "Driver error: {message}",
    'HYT00': "Query timed out.",
    'HYT01': "Connection timed out.",
    'HYC00': "Feature not supported by this driver.",
    'IM002': "Data source not found. Check DSN configuration.",
}

def handle_odbc_error(error: pyodbc.Error) -> ToolError:
    sqlstate = error.args[0] if error.args else 'unknown'
    message = error.args[1] if len(error.args) > 1 else str(error)

    # Sanitize: remove connection string fragments from error messages
    message = sanitize_error_message(message)

    template = SQLSTATE_MAP.get(sqlstate, "ODBC error ({sqlstate}): {message}")
    user_msg = template.format(sqlstate=sqlstate, message=message)
    return ToolError(user_msg)

def sanitize_error_message(msg: str) -> str:
    """Strip credentials from error messages."""
    import re
    return re.sub(r'(PWD|PASSWORD|pwd|password)\s*=\s*[^;]*',
                  r'\1=***', msg, flags=re.IGNORECASE)
```

### Error Visibility

All errors raised as `ToolError` so the LLM sees them and can react (retry, adjust query, inform user). Never use protocol-level errors for application issues.

---

## 11. Security Model

| Layer | Mechanism | Notes |
|-------|-----------|-------|
| ODBC readonly | `pyodbc.connect(readonly=True)` | Driver-enforced; strongest |
| SQL validation | Reject non-SELECT after comment stripping | Catches drivers that don't honor readonly |
| Credential isolation | Env vars or INI file; never in responses | Sanitize connection strings before logging |
| Row limits | `fetchmany(max_rows)` | Prevent OOM from unbounded queries |
| Value truncation | Cap column value length | Prevent context window blowout |
| Query timeout | `connection.timeout = N` | Prevent runaway queries |
| No credential echo | Strip PWD/PASSWORD from all output | Including error messages |

---

## 12. Testing Strategy

### Unit Tests (mocked pyodbc)

- Config loading/validation
- SQL validation (read-only checks)
- Output formatting (markdown, JSON)
- DBMS detection logic
- Adapter selection
- Error handling/mapping
- Schema cache behavior
- Value truncation

### Integration Tests (FastMCP Client, real or mocked connections)

```python
@pytest.fixture
def server():
    from mcp_odbc.server import mcp
    return mcp

@pytest.fixture
def client(server):
    return Client(transport=server)

@pytest.mark.asyncio
async def test_list_tables(client):
    async with client:
        result = await client.call_tool("list_tables", {})
        assert "table_name" in result.text.lower()
```

### MCP Inspector

```bash
fastmcp dev src/mcp_odbc/server.py
```

Interactive debugging — test tools manually during development.

---

## 13. Packaging & Distribution

### pyproject.toml

```toml
[project]
name = "mcp-odbc"
version = "0.1.0"
description = "Universal ODBC MCP server for Claude Code"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
dependencies = [
    "fastmcp>=2.0,<3.0",
    "pyodbc>=5.0",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff"]

[project.scripts]
mcp-odbc = "mcp_odbc.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Installation Methods

```bash
# From PyPI (once published)
pip install mcp-odbc
uvx mcp-odbc

# From source
git clone <repo>
cd mcp-odbc
pip install -e ".[dev]"

# Claude Code integration
claude mcp add --transport stdio odbc -- python -m mcp_odbc
```

---

## 14. Phased Roadmap

### Phase 1: MVP (target: 1-2 days) ✅ COMPLETE

- [x] Project scaffolding (pyproject.toml, module structure)
- [x] Config system (env vars + INI + Pydantic validation)
- [x] ConnectionManager (lazy connect, health check, close)
- [x] GenericODBCAdapter (cursor.tables, cursor.columns, cursor.primaryKeys, cursor.foreignKeys)
- [x] DBMS detection (SQL_DBMS_NAME + adapter registry)
- [x] Core tools: `list_dsns`, `list_connections`, `test_connection`, `list_tables`, `describe_table`, `execute_query`, `get_primary_keys`, `get_foreign_keys`
- [x] Read-only enforcement (3-layer)
- [x] Markdown output formatting + JSON option on execute_query
- [x] Basic error handling with SQLSTATE mapping + credential sanitization
- [x] Entry point + Claude Code integration
- [x] 65 unit + integration tests (all passing, mocked pyodbc)
- [ ] Test against local NetSuite ODBC DSN

### Phase 2: System Adapters (target: 1-2 days)

- [ ] NetSuiteAdapter (OA_TABLES, OA_COLUMNS, OA_FKEYS)
- [ ] SqlServerAdapter (sys.* views)
- [ ] PostgreSQLAdapter (pg_catalog)
- [ ] MySQLAdapter (INFORMATION_SCHEMA)
- [ ] OracleAdapter (ALL_* dictionary)
- [ ] Encoding auto-configuration per detected DBMS
- [ ] Additional tools: `search_tables` (get_primary_keys, get_foreign_keys done in Phase 1)

### Phase 3: Advanced Features (target: 1-2 days)

- [ ] Schema caching with TTL
- [ ] Schema drift detection
- [ ] `diagnose` tool (platform, bitness, drivers, DSNs)
- [ ] JSON output format option
- [ ] Value truncation configuration
- [ ] Multi-connection support (named connections, INI config)
- [ ] `get_sample_data`, `search_columns`, `get_system_info` tools

### Phase 4: Polish & Distribution (target: 1 day)

- [ ] Comprehensive test suite
- [ ] README with usage examples
- [ ] PyPI publishing
- [ ] Docker image (optional)
- [ ] HANAAdapter, DB2Adapter, SageAdapter, QuickBooksAdapter
- [ ] Streamable HTTP transport option

---

## 15. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | FastMCP v2 over raw MCP SDK | Better DX, auto-threading, auto-schema |
| Transport | STDIO over HTTP | ODBC is local; no network exposure needed |
| Pooling | Explicit management, disable ODBC pooling | Cross-platform pooling bugs; explicit is safer |
| Read-only | ODBC attribute + SQL validation | Belt and suspenders; ODBC attribute is strongest |
| Adapters | Plugin pattern, registry-based | Easy to add new systems; graceful fallback |
| Caching | In-memory TTL cache | Catalog functions are slow; schema rarely changes |
| Output | Markdown default, JSON option | LLMs consume markdown well; JSON for programmatic use |
| Config | Env vars (simple) + INI (multi-conn) | Claude Code uses env vars; INI for power users |
| Sync | Sync pyodbc, FastMCP auto-threads | pyodbc is C extension, can't be async; threading is correct |
| Naming | Tools-only, no resources/prompts | Maximum client compatibility |

---

## 16. Sources

Research documents synthesized:
- `01_mcp_sdk_patterns.md` — MCP Python SDK, FastMCP, transport, tool patterns
- `02_existing_implementations.md` — 4 existing ODBC MCP repos analyzed
- `03_pyodbc_drivers.md` — pyodbc API, driver quirks, platform differences
- `04_erp_schemas_detection.md` — 12 ERP/DB systems, detection strategies, drift
