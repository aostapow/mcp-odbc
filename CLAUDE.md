# CLAUDE.md — mcp-odbc

Agent and contributor guide for the Universal ODBC MCP Server.

---

## What This Is

`mcp-odbc` — a Python MCP server that connects to any ODBC data source, auto-detects the DBMS, and exposes schema discovery + read-only query tools. Designed for Claude Code but works with any MCP client.

---

## Architecture (read before writing code)

**MANDATORY**: Read `research/05_architecture_design.md` before making any changes. It contains the full design spec including module structure, tool signatures, adapter pattern, config schema, and security model. All code should follow this design.

### Key Research Files

| File | What It Covers |
|------|---------------|
| `research/05_architecture_design.md` | **START HERE** — full architecture, module structure, phased roadmap |
| `research/01_mcp_sdk_patterns.md` | FastMCP v2 API, tool decorators, transport, error handling, testing |
| `research/02_existing_implementations.md` | 4 repos analyzed, anti-patterns to avoid, ideas to steal |
| `research/03_pyodbc_drivers.md` | pyodbc catalog API, driver quirks, encoding, platform differences |
| `research/04_erp_schemas_detection.md` | 12 ERP/DB systems, detection queries, SQL_DBMS_NAME values, drift |

---

## Tech Stack

- **FastMCP v2.x** (`fastmcp>=2.0,<3.0`) — MCP framework, decorator-based tools
- **pyodbc >=5.0** — ODBC driver binding
- **Pydantic >=2.0** — config validation
- **Transport**: STDIO (Claude Code native)
- **Packaging**: `pyproject.toml` + `hatchling`
- **Testing**: `pytest` + `pytest-asyncio` + FastMCP `Client`

---

## Module Structure

```
mcp-odbc/
+-- pyproject.toml
+-- src/mcp_odbc/
|   +-- __init__.py
|   +-- server.py           # FastMCP server + tool registration + entry point
|   +-- connection.py       # ConnectionManager (lazy connect, health check, close)
|   +-- config.py           # Pydantic models, env var / INI loading
|   +-- query.py            # Query execution, read-only enforcement
|   +-- metadata.py         # Schema discovery, caching
|   +-- detection.py        # DBMS detection via SQL_DBMS_NAME
|   +-- formatting.py       # Markdown tables, JSON, value truncation
|   +-- errors.py           # SQLSTATE mapping, credential sanitization
|   +-- adapters/
|       +-- __init__.py     # Adapter registry + get_adapter()
|       +-- base.py         # SystemAdapter ABC
|       +-- generic.py      # GenericODBCAdapter (ODBC catalog fallback)
|       +-- netsuite.py     # OA_TABLES, OA_COLUMNS, OA_FKEYS
|       +-- mssql.py        # sys.* catalog views
|       +-- postgresql.py   # pg_catalog
|       +-- mysql.py        # INFORMATION_SCHEMA
|       +-- oracle.py       # ALL_* data dictionary
|       +-- (others)        # hana, db2, sage, quickbooks
+-- tests/
+-- config/config.example.ini
+-- research/               # Research docs (read-only reference)
```

---

## Core Patterns

### Tools

- snake_case, verb-noun: `list_tables`, `execute_query`, `describe_table`
- Optional `connection` param on every tool (defaults to configured default)
- Docstrings are LLM instructions — describe when/how to use
- Return markdown by default; JSON option on `execute_query`
- Use `ToolError` from `fastmcp.exceptions` for all application errors

### Connections

- `pyodbc.pooling = False` — manage lifecycle explicitly
- Lazy connect on first use, cache in dict, health-check with `SELECT 1`
- `autocommit=True`, `readonly=True` by default
- Apply encoding per detected DBMS (MySQL/PostgreSQL need UTF-8 config)

### Read-Only Enforcement (3 layers)

1. ODBC: `pyodbc.connect(readonly=True)` — driver-enforced
2. SQL: strip comments, reject non-SELECT (allow WITH where CTE supported)
3. Config: per-connection `readonly` flag

### DBMS Detection

- Primary: `connection.getinfo(pyodbc.SQL_DBMS_NAME)` — instant, no queries
- Fallback: probe queries when ambiguous
- Maps to adapter via registry; GenericODBCAdapter always last

### Adapter Pattern

Each DBMS gets an adapter in `adapters/`. Must implement:
- `detect(connection) -> bool` — static, checks SQL_DBMS_NAME/driver
- `get_tables(cursor, schema?, table_type?) -> list[dict]`
- `get_columns(cursor, table, schema?) -> list[dict]`

Optional overrides (default uses ODBC catalog functions):
- `get_primary_keys`, `get_foreign_keys`, `apply_connection_settings`, `get_sql_capabilities`

### Error Handling

- Catch `pyodbc.Error`, extract SQLSTATE, map to user-friendly message
- Always sanitize: strip PWD/PASSWORD from error messages and logs
- Raise `ToolError` so LLM sees the error and can react

### Output Formatting

- Markdown tables for LLM consumption (default)
- Truncate values >500 chars (configurable)
- Always use `fetchmany(max_rows)`, never `fetchall()`
- Report `has_more` flag when results truncated

---

## Config

### Simple (env vars for Claude Code)

```
ODBC_DSN=MyDataSource
ODBC_READ_ONLY=true
ODBC_MAX_ROWS=10000
ODBC_QUERY_TIMEOUT=30
```

### Advanced (INI for multi-connection)

```ini
[server]
default_connection = netsuite

[netsuite]
connection_string = DSN=NetSuite;UID=user;PWD=secret
readonly = true
query_timeout = 60

[staging]
connection_string = DRIVER={ODBC Driver 18 for SQL Server};SERVER=staging;DATABASE=erp;UID=sa;PWD=secret
readonly = false
```

---

## Anti-Patterns to Avoid

These were found in existing implementations — don't repeat them:

- **Per-request connections** — ODBC connect is expensive; cache and reuse
- **Regex-only SQL blocking** — use ODBC readonly attribute as primary defense
- **Single-file monolith** — separate server/connection/config/adapters
- **No row limits** — always `fetchmany()`, never `fetchall()` for user queries
- **Exposing credentials** — sanitize all output including error messages
- **Virtuoso-specific tools** — keep tools generic; system-specific logic goes in adapters
- **Blocking event loop** — FastMCP auto-threads sync functions; don't worry about async pyodbc

---

## Testing

```bash
# Run tests
pytest tests/

# Interactive debugging with MCP Inspector
fastmcp dev src/mcp_odbc/server.py

# Test against real DSN
ODBC_DSN=NetSuite python -m mcp_odbc
```

In-process testing via FastMCP Client:
```python
from fastmcp import Client
client = Client(transport=mcp)  # mcp = your FastMCP server instance
async with client:
    result = await client.call_tool("list_tables", {})
```

---

## Platform Notes

- Windows: built-in odbc32.dll, registry-based DSN config
- Linux: needs unixODBC (`apt install unixodbc-dev`)
- macOS: use unixODBC via brew (NOT iODBC)
- 64-bit Python = 64-bit drivers only; `pyodbc.drivers()` filters by bitness
- Disable ODBC pooling: `pyodbc.pooling = False` (cross-platform bugs)

---

## Commits

No co-author trailer on commits. Keep messages concise, imperative.
