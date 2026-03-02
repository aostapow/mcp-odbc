# mcp-odbc

A Python MCP server that connects to **any ODBC data source** and exposes schema discovery + query tools. Read-only by default, write access available per-connection. Built on FastMCP v2, designed for Claude Code but works with any MCP client.

```
Claude Code  -->  mcp-odbc  -->  ODBC Driver  -->  Your Database
                  (this)         (any driver)       SQL Server, PostgreSQL,
                                                    MySQL, Oracle, NetSuite,
                                                    SAP, QuickBooks, ...
```

If your database has an ODBC driver, this server can talk to it.

## Why This Exists

We studied [four existing ODBC MCP implementations](research/02_existing_implementations.md) and found they all shared the same gaps: no access control, no credential sanitization in error output, monolithic architecture, and no test coverage. This project addresses all of them.

| Gap in existing implementations | How mcp-odbc solves it |
|---|---|
| No access control | 3-layer access control: ODBC driver flag + SQL validation + per-connection config |
| Credentials leak in error messages | Regex sanitization strips `PWD=` values before they reach the LLM |
| Single connection only | Named multi-connection config with per-connection settings |
| Monolithic single-file design | 9 modules + adapter pattern for DBMS-specific extensions |
| No tests | 69 tests, fully mocked (no real database needed to run) |

## Features

- **8 tools** for schema discovery and querying (see [Tools](#tools) below)
- **Multi-connection** support with named connections and per-connection config
- **Read-only by default**, write access opt-in per-connection — 3 independent enforcement layers
- **Credential sanitization** in all error output
- **DBMS auto-detection** via `SQL_DBMS_NAME` (zero probe queries)
- **Adapter pattern** for DBMS-specific metadata (extensible to any system)
- **Markdown output** optimized for LLM consumption with value truncation and `has_more` pagination
- **JSON output** option on `execute_query`
- Works with **Claude Code**, **Claude Desktop**, **MCP Inspector**, or any MCP client

## Quick Start

### Install

```bash
pip install mcp-odbc
```

Or from source:

```bash
git clone https://github.com/phil-cheesman/mcp-odbc.git
cd mcp-odbc
pip install -e .
```

### Prerequisites

- Python 3.10+
- An ODBC driver for your database (most databases ship one)
- A configured DSN or connection string

### Wire into Claude Code

Add to your Claude Code MCP config (`~/.claude.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "odbc": {
      "type": "stdio",
      "command": "mcp-odbc",
      "env": {
        "ODBC_DSN": "MyDatabase",
        "ODBC_UID": "readonly_user",
        "ODBC_PWD": "password",
        "ODBC_READ_ONLY": "true"
      }
    }
  }
}
```

That's it. Claude Code can now discover your schema and run queries.

### Wire into Claude Desktop

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "odbc": {
      "command": "mcp-odbc",
      "env": {
        "ODBC_DSN": "MyDatabase",
        "ODBC_UID": "readonly_user",
        "ODBC_PWD": "password"
      }
    }
  }
}
```

## Configuration

### Simple: Environment Variables

For a single connection, set environment variables:

| Variable | Default | Description |
|---|---|---|
| `ODBC_DSN` | | DSN name |
| `ODBC_CONNECTION_STRING` | | Full connection string (alternative to DSN) |
| `ODBC_UID` | | Username (appended to connection string if not already present) |
| `ODBC_PWD` | | Password (appended to connection string if not already present) |
| `ODBC_READ_ONLY` | `true` | Read-only enforcement (`false` to allow writes) |
| `ODBC_QUERY_TIMEOUT` | `30` | Query timeout in seconds |
| `ODBC_CONNECT_TIMEOUT` | `10` | Connection timeout in seconds |
| `ODBC_MAX_ROWS` | `10000` | Maximum rows returned per query |

### Advanced: INI Config File

For multiple connections, create a config file:

```ini
[server]
default_connection = production
max_rows = 10000

[production]
connection_string = DSN=ProdDB;UID=reader;PWD=secret
readonly = true
query_timeout = 60

[staging]
connection_string = DRIVER={ODBC Driver 18 for SQL Server};SERVER=staging;DATABASE=erp;UID=sa;PWD=secret
readonly = false
query_timeout = 30
```

Point the server at it:

```json
{
  "mcpServers": {
    "odbc": {
      "type": "stdio",
      "command": "mcp-odbc",
      "env": {
        "ODBC_MCP_CONFIG": "/path/to/config.ini"
      }
    }
  }
}
```

The agent selects a connection per-call: `execute_query("SELECT ...", connection="staging")`. If `connection` is omitted, the `default_connection` is used.

**Config precedence** (highest first):
1. Environment variables (create/override a `default` connection)
2. INI file path from `ODBC_MCP_CONFIG`
3. `./config/config.ini` if present

## Tools

All tools accept an optional `connection` parameter for multi-connection setups.

| Tool | Description |
|---|---|
| `list_dsns` | List ODBC data sources configured on the system |
| `list_connections` | Show configured connections and their status |
| `test_connection` | Verify connectivity, report DBMS type and version |
| `list_tables` | Discover tables/views with optional schema, type, and name pattern filters |
| `describe_table` | Get columns, types, PKs, and FKs for a table |
| `execute_query` | Run a SQL query with row limits and markdown/JSON output |
| `get_primary_keys` | Get primary key columns for a table |
| `get_foreign_keys` | Get foreign key relationships for a table |

### Example Interaction

```
User: What tables have "invoice" in the name?

Claude: [calls list_tables with name_pattern="%invoice%"]

| table_name       | table_type |
| ---              | ---        |
| AR_Invoices      | TABLE      |
| InvoiceLines     | TABLE      |
| InvoiceHistory   | TABLE      |

User: Describe InvoiceLines

Claude: [calls describe_table with table="InvoiceLines", include="all"]

### Columns — InvoiceLines
| column_name | type_name | column_size | nullable |
| ---         | ---       | ---         | ---      |
| LineID      | INTEGER   | 10          | NO       |
| InvoiceID   | INTEGER   | 10          | NO       |
| ItemCode    | VARCHAR   | 50          | YES      |
| Quantity    | DECIMAL   | 18          | YES      |
| UnitPrice   | DECIMAL   | 18          | YES      |

### Primary Keys
| column_name | key_seq |
| ---         | ---     |
| LineID      | 1       |

### Foreign Keys
| fk_column_name | pk_table_name | pk_column_name |
| ---            | ---           | ---            |
| InvoiceID      | AR_Invoices   | InvoiceID      |
```

## Using with Claude Code Agents

The MCP tools work fine when called directly, but on real projects the schema dumps and query results eat up your main context window fast. The better pattern is to **dispatch a sub-agent** that handles all database work in an isolated context and returns just the results you need.

The [`examples/`](examples/) directory includes everything you need:

| File | What it does |
|------|-------------|
| [`examples/agents/odbc-crawler.md`](examples/agents/odbc-crawler.md) | Agent prompt — copy to `.claude/agents/` |
| [`examples/CLAUDE.md.example`](examples/CLAUDE.md.example) | CLAUDE.md snippet — tells Claude to auto-dispatch the agent |

### Setup

**Step 1:** Copy the agent into your project:

```bash
mkdir -p .claude/agents
cp examples/agents/odbc-crawler.md .claude/agents/
```

**Step 2:** Add the CLAUDE.md snippet to your project's `CLAUDE.md` (see [`examples/CLAUDE.md.example`](examples/CLAUDE.md.example) for the full block):

```markdown
## ODBC Data Source

When you need to query, explore schema, or retrieve data from the database,
**always dispatch the `odbc-crawler` agent** rather than calling MCP tools
directly. This isolates database interactions in a separate context window
so query results, schema dumps, and error diagnostics don't consume the
main conversation context.
```

With both pieces in place, Claude Code will automatically dispatch the crawler agent whenever database work comes up — no special prompting needed.

### Example Prompts

**Simple lookups** — the agent handles one focused task and returns:

> "Use the ODBC crawler to find all tables related to inventory and describe the top 3."

> "Dispatch the crawler to check the distinct values in the status column of the orders table."

**Bulk orchestration** — this is where the agent pattern really shines. Because each dispatch is an isolated context, you can fan out dozens of parallel agents across a large schema without any of them competing for context space:

> "I have these 50 source columns that need to be mapped to the new schema. For each one, dispatch a crawler to search for matching columns by name and data type, then compile the results into a mapping table."

> "For each table in this list — orders, customers, products, inventory, shipments, returns — dispatch parallel crawlers to get the full schema with PKs and FKs, then generate a migration plan with the combined results."

> "Search the entire database for every table that contains a `customer_id` column. Fan out crawlers in batches, compile the results, and build me a dependency graph."

> "I'm building column mappings between the source ERP and our target warehouse. Here's the target schema with 200 columns. Dispatch crawlers in parallel to find the most likely source column for each one based on name, type, and sample values."

The single-query examples are useful, but the real power is using the agent as a **parallelizable worker**. A task that would blow out a single context window — like mapping 200 columns across a schema with thousands of tables — becomes manageable when you can dispatch 20 crawlers simultaneously, each searching for a handful of columns and returning just the matches.

## Security

### Access Control (3 Layers)

When `readonly = true` (the default), write operations are blocked at three independent levels:

1. **ODBC driver** — Connections open with `readonly=True`, which tells the driver to reject writes at the protocol level.
2. **SQL validation** — Before execution, queries are parsed: comments are stripped, and the statement is rejected if it starts with anything other than `SELECT` or `WITH`, or contains write keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `GRANT`, `EXEC`, etc.).
3. **Config flag** — Per-connection `readonly` setting (defaults to `true`). Set `readonly = false` on any connection to allow write operations — all three layers step aside for that connection.

This is configured per-connection, so you can have a locked-down production connection alongside a write-enabled staging connection in the same config file.

### Credential Sanitization

All error messages are scrubbed before reaching the LLM. Any `PWD=value` or `PASSWORD=value` patterns are replaced with `PWD=***` so credentials never appear in tool output.

### Recommendations

- Create a **read-only database user** for connections that don't need write access. Database-level permissions are the strongest protection.
- Keep credentials in environment variables or a gitignored INI file, not in source control.
- Use `readonly = true` for production connections. Use `readonly = false` where writes are intentional (staging, testing, ETL workflows).

## Architecture

```
src/mcp_odbc/
  server.py         # FastMCP server, 8 tool registrations, entry point
  config.py         # Pydantic models, env var + INI loading
  connection.py     # ConnectionManager (lazy connect, health check, cache)
  query.py          # SQL execution, read-only validation
  metadata.py       # Schema discovery (delegates to adapter)
  detection.py      # DBMS detection via SQL_DBMS_NAME
  formatting.py     # Markdown tables, JSON, value truncation
  errors.py         # SQLSTATE mapping, credential sanitization
  adapters/
    base.py         # SystemAdapter ABC
    generic.py      # GenericODBCAdapter (works with any ODBC driver)
```

### Key Design Decisions

- **No ODBC pooling.** `pyodbc.pooling` is disabled because it has [cross-platform bugs](https://github.com/mkleehammer/pyodbc/wiki/Connection-Pooling). Connections are cached in a dict with health checks and auto-reconnect.
- **Sync tools, auto-threaded.** pyodbc is synchronous. FastMCP automatically runs sync tool functions in a thread pool, so there's no async boilerplate.
- **Adapter pattern.** Each DBMS can have a dedicated adapter that overrides metadata queries. The `GenericODBCAdapter` uses standard ODBC catalog functions and works with any driver. DBMS-specific adapters (SQL Server, PostgreSQL, etc.) can provide richer metadata without changing any tool code.
- **LLM-first output.** Markdown tables are the default because LLMs parse them natively. Values longer than 500 characters are truncated to avoid token waste. A `has_more` flag signals when results are paginated.

### Extending with Adapters

To add support for a specific DBMS, create an adapter in `src/mcp_odbc/adapters/`:

```python
from mcp_odbc.adapters.base import SystemAdapter

class MySQLAdapter(SystemAdapter):
    name = "mysql"
    display_name = "MySQL"

    @staticmethod
    def detect(connection) -> bool:
        return "mysql" in connection.getinfo(pyodbc.SQL_DBMS_NAME).lower()

    def get_tables(self, cursor, schema=None, table_type=None, name_pattern=None):
        # Use INFORMATION_SCHEMA for richer metadata
        ...

    def get_columns(self, cursor, table, schema=None):
        ...

    def apply_connection_settings(self, connection):
        # Set UTF-8 encoding for MySQL connections
        ...
```

Register it in `adapters/__init__.py` and it will be auto-selected when a MySQL connection is detected.

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run the test suite (no real database needed — everything is mocked)
pytest tests/

# 69 tests covering config, connections, query validation,
# error handling, formatting, and end-to-end tool integration
```

### Interactive Debugging

```bash
# MCP Inspector (browser-based tool testing)
fastmcp dev src/mcp_odbc/server.py

# Run against a real DSN
ODBC_DSN=MyDatabase python -m mcp_odbc
```

## Platform Notes

| Platform | ODBC Driver Manager | Notes |
|---|---|---|
| Windows | Built-in (odbc32.dll) | DSNs configured in ODBC Data Source Administrator |
| Linux | unixODBC | `apt install unixodbc-dev` or `yum install unixODBC-devel` |
| macOS | unixODBC via Homebrew | `brew install unixodbc` (do NOT use iODBC) |

64-bit Python requires 64-bit ODBC drivers. `pyodbc.drivers()` only lists drivers matching your Python bitness.

## Contributing

Contributions welcome, especially DBMS-specific adapters. The adapter pattern makes it straightforward to add support for new databases without modifying core code.

1. Fork the repo
2. Create a feature branch
3. Add tests (all tests must pass with mocked ODBC — no real driver dependencies)
4. Submit a PR

## License

MIT
