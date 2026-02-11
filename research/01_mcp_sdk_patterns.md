# MCP Python SDK Patterns & ODBC Integration Guide

Comprehensive reference for Model Context Protocol (MCP) implementation patterns, focusing on Python SDKs and ODBC transport for NetSuite.

---

## 1. MCP Python SDK Landscape

### 1.1 SDK Options

| SDK | Use Case | Stability | Recommendation |
|-----|----------|-----------|-----------------|
| **FastMCP v2** | Rapid prototyping, decorators | Stable (Aug 2024+) | First choice for local ODBC servers |
| **Official SDK** (mcp) | Full control, complex logic | Stable | Use when FastMCP insufficient |
| **Low-level Server** | Custom transports, edge cases | Advanced | Rare; use for non-STDIO needs |

### 1.2 FastMCP v2 Landscape

FastMCP (August 2024 release) modernized MCP server development:

- **Decorator-based** tool definition (eliminates boilerplate)
- **Pydantic v2** validation built-in
- **Async/await** native throughout
- **Context management** via lifespan handlers
- **Auto-schema generation** from type hints

```bash
pip install mcp>=1.0.0
pip install fastmcp>=0.2.0
```

### 1.3 Official SDK (mcp)

The foundational `mcp` package provides:

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.tools import Tool, ToolError
```

**When to use official SDK over FastMCP:**
- Custom transport protocols (WebSocket, HTTP, etc.)
- Fine-grained control over context lifecycle
- Existing codebase using pre-v2 patterns
- Advanced error handling beyond ToolError

### 1.4 Low-level Server

The raw `Server` class for complete control:

```python
from mcp.server import Server
from mcp.types import TextContent, Tool

server = Server("my-server")

@server.call_tool()
async def tool_handler(name: str, arguments: dict):
    # Manual validation, serialization, error handling
    pass
```

Use only if FastMCP & official SDK insufficient.

---

## 2. Tool Definition Patterns

### 2.1 FastMCP Decorators (Recommended)

Cleanest pattern for NetSuite ODBC server:

```python
from fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("netsuite-odbc")

# Simple tool with type hints
@mcp.tool()
async def query_transaction(so_number: str) -> str:
    """Fetch sales order details from NetSuite ODBC.

    Args:
        so_number: NetSuite transaction number (e.g., "SO-12345")

    Returns:
        JSON string with order details
    """
    # Implementation
    return result

# Tool with complex input model
class InventoryFilterInput(BaseModel):
    location_id: int = Field(..., description="NetSuite location internal ID")
    min_quantity: int = Field(default=0, description="Minimum on-hand qty")
    item_type: str = Field(default="Inventory Item", description="Item type")

@mcp.tool()
async def list_inventory(filters: InventoryFilterInput) -> str:
    """Query inventory balance by location and item type."""
    # Pydantic automatically validates input
    return query_netsuite_inventory(filters)
```

**Advantages:**
- Zero boilerplate schema definition
- Pydantic v2 validation automatic
- Type hints become docs + validation
- Async-first design

### 2.2 Pydantic Schema Models

Use Pydantic for complex tool inputs:

```python
from typing import Optional
from pydantic import BaseModel, Field, validator

class TransactionLineFilter(BaseModel):
    """Filter for transaction line queries."""

    transaction_id: int = Field(
        ...,
        description="NetSuite transaction internal ID (required)"
    )
    item_ids: Optional[list[int]] = Field(
        default=None,
        description="Filter by specific item IDs; if None, all items returned"
    )
    exclude_cancelled: bool = Field(
        default=True,
        description="Exclude cancelled lines"
    )
    quantity_threshold: Optional[float] = Field(
        default=None,
        description="Only return lines with quantity > threshold"
    )

    @validator('transaction_id')
    def validate_transaction_id(cls, v):
        if v < 0:
            raise ValueError("transaction_id must be non-negative")
        return v

    @validator('item_ids')
    def validate_item_ids(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError("item_ids must be non-empty if provided")
        return v

@mcp.tool()
async def get_transaction_lines(filter: TransactionLineFilter) -> str:
    """Get line items from a sales order."""
    # filter is validated Pydantic model
    return query_transaction_lines(
        transaction_id=filter.transaction_id,
        item_ids=filter.item_ids,
        exclude_cancelled=filter.exclude_cancelled,
        quantity_threshold=filter.quantity_threshold
    )
```

### 2.3 Typing with Annotated (Advanced)

For advanced schemas with additional metadata:

```python
from typing import Annotated
from pydantic import BaseModel, Field

class LocationContext(BaseModel):
    location_id: int = Field(
        ...,
        ge=1,  # Greater than or equal to 1
        description="NetSuite location ID"
    )
    include_empty: Annotated[bool, Field(
        default=False,
        description="Include locations with zero inventory"
    )]

@mcp.tool()
async def inventory_by_location(
    location: LocationContext,
    sort_by: Annotated[str, Field(
        default="item_number",
        regex="^(item_number|quantity|reorder_level)$",
        description="Sort result by field"
    )] = "item_number"
) -> str:
    """Query inventory filtered by location."""
    return query_and_sort(location, sort_by)
```

### 2.4 Official SDK Tool Definition

When using `mcp` directly (more verbose):

```python
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("netsuite-odbc")

# Define tool schema
QUERY_INVENTORY_TOOL = Tool(
    name="query_inventory",
    description="Search NetSuite inventory by location and item",
    inputSchema={
        "type": "object",
        "properties": {
            "location_id": {
                "type": "integer",
                "description": "NetSuite location internal ID"
            },
            "min_quantity": {
                "type": "integer",
                "default": 0,
                "description": "Minimum on-hand quantity"
            }
        },
        "required": ["location_id"]
    }
)

@server.call_tool()
async def handle_tool_call(name: str, arguments: dict):
    if name == "query_inventory":
        location_id = arguments.get("location_id")
        min_qty = arguments.get("min_quantity", 0)

        # Validate manually
        if not isinstance(location_id, int) or location_id < 0:
            raise ToolError("Invalid location_id")

        result = await query_netsuite(location_id, min_qty)
        return [TextContent(type="text", text=result)]
```

---

## 3. Transport Options

### 3.1 STDIO (Recommended for ODBC)

**Why STDIO for NetSuite ODBC server:**
- No network overhead (local ODBC connection)
- Simple debugging (stdin/stdout readable)
- Claude Code native support
- Perfect for single-user dev environments
- ODBC driver handles network to NetSuite

### 3.2 STDIO Implementation

#### FastMCP (Simplest)

```python
from fastmcp import FastMCP

mcp = FastMCP("netsuite-odbc")

@mcp.tool()
async def query_sales_order(so_id: str) -> str:
    """Fetch sales order from NetSuite via ODBC."""
    # Implementation
    return result

if __name__ == "__main__":
    mcp.run()  # Auto-runs STDIO transport
```

#### Official SDK

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("netsuite-odbc")

# Add tools via @server.call_tool() decorator

if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(server))
```

### 3.3 Transport Comparison

| Transport | Setup | Local ODBC | Debugging | Use Case |
|-----------|-------|-----------|-----------|----------|
| **STDIO** | 1 line | Excellent | Easy (logs to stderr) | Claude Code, local dev |
| **SSE** | Medium | Good | Moderate | Web apps, cloud |
| **WebSocket** | Complex | Good | Moderate | Bidirectional, real-time |
| **HTTP** | Complex | Good | Good | REST-first systems |

### 3.4 Production Transport Notes

**For NetSuite ODBC server (local Power BI machine):**

1. **STDIO is sufficient** - local ODBC driver handles NetSuite communication
2. **No need for network transports** - ODBC abstracts network layer
3. **Containerization** - if dockerizing, STDIO + volume mount for ODBC config
4. **Scaling** - if multi-user, use SSE behind reverse proxy (future)

---

## 4. Context Management & Lifespan

### 4.1 FastMCP Lifespan (Recommended)

```python
from fastmcp import FastMCP
import pyodbc

mcp = FastMCP("netsuite-odbc")

# Global connection pool (initialized at startup)
connection_pool = None

@mcp.lifecycle.on_startup()
async def startup():
    """Initialize ODBC connection pool on server start."""
    global connection_pool

    # Connection string from environment or config
    conn_str = "Driver={NetSuite ODBC Driver};Server=...;UID=...;PWD=..."

    # Create pool (or single connection if small)
    connection_pool = ConnectionPool(
        conn_str,
        pool_size=5,
        timeout=30
    )
    print("ODBC connection pool initialized", file=sys.stderr)

@mcp.lifecycle.on_shutdown()
async def shutdown():
    """Cleanup on server shutdown."""
    global connection_pool
    if connection_pool:
        await connection_pool.close()
        print("ODBC connection pool closed", file=sys.stderr)

@mcp.tool()
async def query_transaction(so_number: str) -> str:
    """Query uses global connection_pool."""
    async with connection_pool.acquire() as conn:
        result = await conn.execute("SELECT * FROM transaction WHERE ...")
        return json.dumps(result)
```

### 4.2 Official SDK Lifespan

```python
from mcp.server import Server
from contextlib import asynccontextmanager

server = Server("netsuite-odbc")
connection_pool = None

@asynccontextmanager
async def lifespan():
    """Context manager for server lifecycle."""
    global connection_pool

    # Startup
    connection_pool = ConnectionPool(
        os.getenv("NETSUITE_ODBC_STRING"),
        pool_size=5
    )
    try:
        yield
    finally:
        # Shutdown
        await connection_pool.close()

if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server

    async def main():
        async with lifespan():
            await stdio_server(server)

    asyncio.run(main())
```

### 4.3 Connection Pool Pattern (ODBC-Specific)

```python
import pyodbc
from asyncio import Semaphore
from typing import AsyncGenerator

class ODBCConnectionPool:
    """Async connection pool for NetSuite ODBC."""

    def __init__(self, conn_str: str, pool_size: int = 5):
        self.conn_str = conn_str
        self.pool_size = pool_size
        self.semaphore = Semaphore(pool_size)
        self.connections = []

    async def initialize(self):
        """Lazy-init connections (called on startup)."""
        for _ in range(self.pool_size):
            # pyodbc is sync, so use thread pool
            conn = await asyncio.to_thread(
                pyodbc.connect,
                self.conn_str
            )
            self.connections.append(conn)

    async def acquire(self) -> 'PooledConnection':
        """Acquire connection from pool."""
        await self.semaphore.acquire()
        return PooledConnection(self, self.connections[0])

    async def release(self, conn):
        """Release connection back to pool."""
        self.semaphore.release()

    async def close(self):
        """Close all connections."""
        for conn in self.connections:
            await asyncio.to_thread(conn.close)

class PooledConnection:
    """Context manager for pooled connection."""

    def __init__(self, pool: ODBCConnectionPool, conn):
        self.pool = pool
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        await self.pool.release(self.conn)
```

---

## 5. Error Handling

### 5.1 Three-Tier Error Model

MCP defines three error categories:

| Tier | Use Case | Example |
|------|----------|---------|
| **ToolError** | Tool logic failure (user's fault) | Invalid SO number, missing field |
| **InternalError** | Server issue (our fault) | ODBC connection lost, DB query timeout |
| **Other** | Unexpected (recovery unknown) | OOM, OS signal |

### 5.2 FastMCP Error Handling

```python
from mcp.tools import ToolError

@mcp.tool()
async def query_sales_order(so_number: str) -> str:
    """Fetch sales order from NetSuite ODBC."""

    # Validate input (user's responsibility)
    if not so_number or not so_number.startswith("SO-"):
        raise ToolError(f"Invalid SO number format: {so_number}")

    try:
        # Query ODBC
        async with connection_pool.acquire() as conn:
            result = await asyncio.to_thread(
                conn.execute,
                "SELECT * FROM transaction WHERE transactionNumber = ?",
                (so_number,)
            )
            rows = await asyncio.to_thread(result.fetchall)

            if not rows:
                raise ToolError(f"Sales order not found: {so_number}")

            return json.dumps([dict(row) for row in rows])

    except pyodbc.DatabaseError as e:
        # Server error (we should retry or alert)
        logger.error(f"ODBC database error querying {so_number}: {e}")
        raise ToolError(f"Database error (contact admin): {e}")

    except asyncio.TimeoutError:
        # Timeout = server issue
        logger.error(f"Query timeout for {so_number}")
        raise ToolError("Query timeout; NetSuite ODBC unresponsive")

    except Exception as e:
        # Unexpected error
        logger.exception(f"Unexpected error querying {so_number}")
        raise ToolError(f"Unexpected error: {type(e).__name__}")
```

### 5.3 Structured Error Responses

For complex tools, return structured error info:

```python
from pydantic import BaseModel
from typing import Optional

class QueryResult(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[dict] = None

@mcp.tool()
async def query_with_details(so_number: str) -> str:
    """Query with structured error response."""
    try:
        result = await fetch_sales_order(so_number)
        return json.dumps(QueryResult(
            success=True,
            data=result
        ).model_dump())

    except ValueError as e:
        return json.dumps(QueryResult(
            success=False,
            error={
                "code": "VALIDATION_ERROR",
                "message": str(e),
                "input": so_number
            }
        ).model_dump())

    except Exception as e:
        return json.dumps(QueryResult(
            success=False,
            error={
                "code": "INTERNAL_ERROR",
                "message": "Server error occurred",
                "detail": str(e) if not isinstance(e, pyodbc.DatabaseError) else None
            }
        ).model_dump())
```

### 5.4 Logging & Debugging

```python
import logging
import sys

# Configure logging to stderr (STDIO safe)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

logger = logging.getLogger("netsuite-odbc")

@mcp.tool()
async def query_sales_order(so_number: str) -> str:
    """Fetch sales order with detailed logging."""
    logger.info(f"Querying sales order: {so_number}")

    try:
        result = await fetch_so(so_number)
        logger.debug(f"Query successful, returned {len(result)} rows")
        return json.dumps(result)

    except Exception as e:
        logger.error(f"Query failed for {so_number}", exc_info=True)
        raise ToolError(f"Query failed: {e}")
```

---

## 6. Security & Input Validation

### 6.1 Input Validation (Pydantic)

```python
from pydantic import BaseModel, Field, validator

class SalesOrderQuery(BaseModel):
    """Safe SalesOrderQuery with validation."""

    so_number: str = Field(
        ...,
        min_length=1,
        max_length=50,
        regex="^[A-Z0-9-]+$",  # Alphanumeric + dash
        description="Sales order number"
    )

    include_details: bool = Field(
        default=True,
        description="Include line items"
    )

    @validator('so_number')
    def validate_so_number(cls, v):
        # Additional custom validation
        if v.upper() != v:
            raise ValueError("SO number must be uppercase")
        if v.count('-') > 2:
            raise ValueError("SO number has too many dashes")
        return v

@mcp.tool()
async def query_sales_order(query: SalesOrderQuery) -> str:
    """Query with validated input."""
    # query is guaranteed valid
    return await fetch_so(query.so_number)
```

### 6.2 SQL Injection Prevention

Always use parameterized queries:

```python
# UNSAFE - DON'T DO THIS
unsafe_query = f"SELECT * FROM transaction WHERE transactionNumber = '{so_number}'"
result = conn.execute(unsafe_query)

# SAFE - Use parameters
safe_query = "SELECT * FROM transaction WHERE transactionNumber = ?"
result = conn.execute(safe_query, (so_number,))
```

### 6.3 Environment Variable Security

```python
import os
from dotenv import load_dotenv

# Load from .env (dev only, never commit .env to git)
load_dotenv()

ODBC_CONNECTION_STRING = os.getenv(
    "NETSUITE_ODBC_STRING",
    default="Driver={NetSuite ODBC Driver};..."  # Fallback for CI/CD
)

# Validate required env vars
required_vars = ["NETSUITE_ODBC_STRING"]
for var in required_vars:
    if not os.getenv(var):
        raise RuntimeError(f"Missing required environment variable: {var}")
```

### 6.4 Rate Limiting (Optional)

```python
from asyncio import Semaphore
from datetime import datetime, timedelta

class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.semaphore = Semaphore(calls_per_minute)
        self.reset_time = datetime.now() + timedelta(minutes=1)

    async def acquire(self):
        """Acquire token (blocks if exhausted)."""
        now = datetime.now()
        if now > self.reset_time:
            # Reset tokens
            for _ in range(self.calls_per_minute):
                self.semaphore.release()
            self.reset_time = now + timedelta(minutes=1)

        await self.semaphore.acquire()

rate_limiter = RateLimiter(calls_per_minute=120)

@mcp.tool()
async def query_sales_order(so_number: str) -> str:
    """Rate-limited query."""
    await rate_limiter.acquire()
    return await fetch_so(so_number)
```

---

## 7. Configuration Patterns

### 7.1 Environment Variables

```python
import os
from dataclasses import dataclass

@dataclass
class ODBCConfig:
    """ODBC connection configuration."""

    driver: str = os.getenv("ODBC_DRIVER", "NetSuite ODBC Driver")
    server: str = os.getenv("ODBC_SERVER", "")
    uid: str = os.getenv("ODBC_UID", "")
    pwd: str = os.getenv("ODBC_PWD", "")
    pool_size: int = int(os.getenv("ODBC_POOL_SIZE", "5"))
    timeout: int = int(os.getenv("ODBC_TIMEOUT", "30"))

    @property
    def connection_string(self) -> str:
        return f"Driver={{{self.driver}}};Server={self.server};UID={self.uid};PWD={self.pwd};"

    def validate(self):
        """Validate required fields."""
        if not self.server:
            raise ValueError("ODBC_SERVER not configured")
        if not self.uid or not self.pwd:
            raise ValueError("ODBC_UID and ODBC_PWD required")

config = ODBCConfig()
config.validate()
```

### 7.2 .env File (Development)

```bash
# .env (never commit to git)
ODBC_DRIVER=NetSuite ODBC Driver
ODBC_SERVER=netsuite-odbc.example.com
ODBC_UID=your_username
ODBC_PWD=your_password
ODBC_POOL_SIZE=5
ODBC_TIMEOUT=30
LOG_LEVEL=INFO
```

### 7.3 FastMCP Settings

```python
from fastmcp import FastMCP

mcp = FastMCP(
    "netsuite-odbc",
    description="NetSuite ODBC bridge for Power BI",
    version="1.0.0"
)

# FastMCP respects environment:
# - MCP_DEBUG=1 for verbose logging
# - MCP_LOG_LEVEL=DEBUG for debug output
```

### 7.4 CLI Configuration

```python
import argparse
import sys

def parse_args():
    parser = argparse.ArgumentParser(
        description="NetSuite ODBC MCP server"
    )
    parser.add_argument(
        '--config',
        type=str,
        default=os.getenv("ODBC_CONFIG_PATH", ".odbc.ini"),
        help="Path to ODBC config file"
    )
    parser.add_argument(
        '--log-level',
        type=str,
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help="Logging level"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    # Configure logging
    logging.basicConfig(level=getattr(logging, args.log_level))

    # Load config
    config = load_odbc_config(args.config)

    # Run MCP server
    mcp.run()
```

---

## 8. Claude Code Integration

### 8.1 .mcp.json Configuration

```json
{
  "mcpServers": {
    "netsuite-odbc": {
      "command": "python",
      "args": [
        "C:\\path\\to\\mcp-odbc\\src\\server.py"
      ],
      "env": {
        "NETSUITE_ODBC_STRING": "Driver={NetSuite ODBC Driver};Server=...;UID=...;PWD=...;",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### 8.2 Tool Naming for LLM Optimization

MCP servers appear as tools in Claude Code. Use clear, verb-first names:

```python
# GOOD - clear action verbs
@mcp.tool()
async def query_sales_order(so_number: str) -> str:
    """Fetch sales order details."""

@mcp.tool()
async def list_inventory_by_location(location_id: int) -> str:
    """List all items in a warehouse location."""

@mcp.tool()
async def calculate_days_past_due(order_date: str) -> int:
    """Calculate number of days since order creation date."""

# POOR - vague names
@mcp.tool()
async def get_stuff(id: str) -> str:
    """Get data."""

@mcp.tool()
async def search_data(query: str) -> str:
    """Find things."""
```

**Naming conventions:**
- Use `query_`, `list_`, `get_`, `calculate_`, `update_`, `delete_` prefixes
- Include resource type (e.g., `query_sales_order` not `query_order`)
- Be specific (e.g., `list_inventory_by_location` not `search_inventory`)
- Keep under 50 chars for readability in Claude Code UI

### 8.3 Description & Documentation

```python
@mcp.tool()
async def query_sales_order(so_number: str) -> str:
    """Fetch sales order details from NetSuite ODBC.

    Queries the transaction table via ODBC driver. Returns complete order
    details including customer, items, quantities, and status.

    Args:
        so_number: NetSuite sales order number (e.g., "SO-12345"). Must
                   match exactly; search tools are not case-insensitive.

    Returns:
        JSON string containing order object with fields:
        - transactionNumber: Order number
        - createdDate: Order creation date
        - customerName: Customer name
        - items: Array of line items with quantity and pricing
        - status: Current order status

    Raises:
        ToolError: If order not found or ODBC connection fails.

    Example:
        >>> query_sales_order("SO-12345")
        '{"transactionNumber": "SO-12345", "customerName": "Acme Corp", ...}'
    """
    # Implementation
    pass
```

### 8.4 Windows Path Notes

On Windows, MCP server paths use backslashes in JSON:

```json
{
  "netsuite-odbc": {
    "command": "python",
    "args": [
      "C:\\mcp-odbc\\mcp-odbc\\src\\server.py"
    ]
  }
}
```

Or use forward slashes (also valid):

```json
{
  "netsuite-odbc": {
    "command": "python",
    "args": [
      "C:/dev/mcp-odbc/src/server.py"
    ]
  }
}
```

---

## 9. Packaging & Deployment

### 9.1 pyproject.toml Structure

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mcp-netsuite-odbc"
version = "1.0.0"
description = "MCP server for NetSuite ODBC bridge"
readme = "README.md"
license = {text = "MIT"}
authors = [{name = "Your Name", email = "email@example.com"}]

requires-python = ">=3.9"
dependencies = [
    "fastmcp>=0.2.0",
    "mcp>=1.0.0",
    "pydantic>=2.0",
    "pyodbc>=4.0",
    "python-dotenv>=1.0"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "black>=23.0",
    "ruff>=0.1.0",
    "mypy>=1.0"
]

[project.scripts]
mcp-netsuite-odbc = "mcp_odbc.server:main"

[tool.black]
line-length = 100
target-version = ["py39"]

[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "UP"]

[tool.mypy]
python_version = "3.9"
check_untyped_defs = true
```

### 9.2 uv (Fast Python Package Manager)

```bash
# Install uv
curl https://astral.sh/uv/install.sh | sh

# Create virtual environment and install
uv venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate.bat  # Windows

# Install dependencies
uv pip install -e ".[dev]"

# Run server
python src/server.py
```

### 9.3 Docker Setup

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml pyproject.toml
COPY src/ src/

# Install dependencies
RUN pip install --no-cache-dir -e .

# Expose for remote (if needed)
EXPOSE 8000

# Run MCP server
CMD ["python", "src/server.py"]
```

### 9.4 Docker Compose (with ODBC)

```yaml
version: '3.9'

services:
  netsuite-odbc:
    build: .
    container_name: mcp-netsuite-odbc
    environment:
      NETSUITE_ODBC_STRING: ${NETSUITE_ODBC_STRING}
      LOG_LEVEL: INFO
    volumes:
      # Mount ODBC config if needed
      - /etc/odbc.ini:/etc/odbc.ini:ro
    ports:
      - "8000:8000"  # For remote transport (if used)
    networks:
      - netsuite-network

networks:
  netsuite-network:
    driver: bridge
```

---

## 10. Architecture Patterns from Popular Servers

### 10.1 Layered Architecture (Recommended)

Organize code by concern:

```
mcp-odbc/
├── src/
│   ├── server.py              # FastMCP initialization + tool decorators
│   ├── config.py              # Configuration management
│   ├── odbc_pool.py           # ODBC connection pooling
│   ├── services/
│   │   ├── sales_order_service.py     # Sales order business logic
│   │   ├── inventory_service.py       # Inventory queries
│   │   └── customer_service.py        # Customer master queries
│   ├── models/
│   │   ├── sales_order.py     # Pydantic models for queries
│   │   ├── inventory.py
│   │   └── shared.py          # Common models
│   └── utils/
│       ├── error_handler.py   # Error handling utilities
│       ├── logger.py          # Logging setup
│       └── validators.py      # Input validation helpers
├── tests/
│   ├── test_sales_order_service.py
│   ├── test_inventory_service.py
│   └── fixtures.py
├── pyproject.toml
├── .env.example
└── README.md
```

### 10.2 Service Layer Pattern

```python
# services/sales_order_service.py
from typing import Optional, List
import pyodbc

class SalesOrderService:
    """Business logic for sales orders."""

    def __init__(self, connection_pool):
        self.pool = connection_pool

    async def get_sales_order(self, so_number: str) -> Optional[dict]:
        """Fetch single sales order by number."""
        async with self.pool.acquire() as conn:
            result = await asyncio.to_thread(
                conn.execute,
                "SELECT * FROM transaction WHERE transactionNumber = ? AND status = 'Open'",
                (so_number,)
            )
            row = await asyncio.to_thread(result.fetchone)
            return dict(row) if row else None

    async def list_overdue_orders(self, days_past_due: int) -> List[dict]:
        """List sales orders overdue by N days."""
        async with self.pool.acquire() as conn:
            result = await asyncio.to_thread(
                conn.execute,
                """
                SELECT transactionNumber, customerName, createdDate, DATEDIFF(day, createdDate, GETDATE()) as daysPastDue
                FROM transaction
                WHERE status = 'Open' AND DATEDIFF(day, createdDate, GETDATE()) >= ?
                ORDER BY createdDate ASC
                """,
                (days_past_due,)
            )
            rows = await asyncio.to_thread(result.fetchall)
            return [dict(row) for row in rows]

# server.py
service = None

@mcp.lifecycle.on_startup()
async def startup():
    global service
    pool = ODBCConnectionPool(config.connection_string)
    await pool.initialize()
    service = SalesOrderService(pool)

@mcp.tool()
async def query_sales_order(so_number: str) -> str:
    """Fetch sales order details."""
    order = await service.get_sales_order(so_number)
    if not order:
        raise ToolError(f"Order not found: {so_number}")
    return json.dumps(order)

@mcp.tool()
async def list_overdue_orders(days_past_due: int = 7) -> str:
    """List orders overdue by N days."""
    orders = await service.list_overdue_orders(days_past_due)
    return json.dumps({
        "count": len(orders),
        "orders": orders
    })
```

### 10.3 Model Layer Pattern

```python
# models/sales_order.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class SalesOrderQuery(BaseModel):
    """Input model for sales order queries."""

    so_number: str = Field(
        ...,
        regex="^SO-[0-9]+$",
        description="Sales order number"
    )
    include_items: bool = Field(
        default=True,
        description="Include line items"
    )

class SalesOrderResponse(BaseModel):
    """Output model for sales order response."""

    transaction_id: int
    transaction_number: str
    customer_name: str
    created_date: datetime
    status: str
    total_amount: float
    items: Optional[List[SalesOrderItem]] = None

class SalesOrderItem(BaseModel):
    """Line item in sales order."""

    line_number: int
    item_number: str
    item_name: str
    quantity: float
    price_per_unit: float
    total_price: float
```

### 10.4 Error Handler Pattern

```python
# utils/error_handler.py
import logging
from mcp.tools import ToolError
from typing import Callable, Any

logger = logging.getLogger(__name__)

def handle_tool_error(func: Callable) -> Callable:
    """Decorator for consistent error handling."""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)

        except ValueError as e:
            # User error (validation, bad input)
            logger.warning(f"Validation error in {func.__name__}: {e}")
            raise ToolError(f"Invalid input: {e}")

        except pyodbc.DatabaseError as e:
            # Database error (server issue)
            logger.error(f"Database error in {func.__name__}: {e}")
            raise ToolError("Database error; contact admin")

        except asyncio.TimeoutError:
            # Timeout (server issue)
            logger.error(f"Timeout in {func.__name__}")
            raise ToolError("Query timeout; server unresponsive")

        except Exception as e:
            # Unexpected error
            logger.exception(f"Unexpected error in {func.__name__}")
            raise ToolError(f"Server error: {type(e).__name__}")

    return wrapper

# Usage
@mcp.tool()
@handle_tool_error
async def query_sales_order(so_number: str) -> str:
    """Fetch sales order."""
    return await service.get_sales_order(so_number)
```

---

## 11. Testing

### 11.1 FastMCP Test Client

```python
# tests/test_server.py
import pytest
import json
from fastmcp import FastMCP

# Import server
from src.server import mcp

@pytest.mark.asyncio
async def test_query_sales_order():
    """Test query_sales_order tool."""

    # Call tool via FastMCP test client
    result = await mcp.call_tool(
        "query_sales_order",
        {"so_number": "SO-12345"}
    )

    # Verify response
    assert result is not None
    data = json.loads(result)
    assert data["transaction_number"] == "SO-12345"

@pytest.mark.asyncio
async def test_query_sales_order_not_found():
    """Test query with non-existent order."""

    with pytest.raises(Exception):  # ToolError
        await mcp.call_tool(
            "query_sales_order",
            {"so_number": "SO-99999"}
        )
```

### 11.2 MCP Inspector

MCP provides built-in inspector for debugging:

```bash
# Start inspector (shows incoming/outgoing messages)
mcp inspect src/server.py

# In another terminal, connect Claude Code to inspector URL
# See detailed STDIO messages in real-time
```

### 11.3 Unit Testing Services

```python
# tests/test_sales_order_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.sales_order_service import SalesOrderService

@pytest.fixture
def mock_pool():
    """Mock ODBC connection pool."""
    pool = AsyncMock()
    pool.acquire = AsyncMock()
    return pool

@pytest.mark.asyncio
async def test_get_sales_order(mock_pool):
    """Test fetching a sales order."""

    # Setup mock
    mock_conn = AsyncMock()
    mock_result = AsyncMock()
    mock_result.fetchone = AsyncMock(return_value=("SO-12345", "Acme", "2024-01-01"))
    mock_conn.execute = AsyncMock(return_value=mock_result)
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Test
    service = SalesOrderService(mock_pool)
    result = await service.get_sales_order("SO-12345")

    # Verify
    assert result is not None
```

### 11.4 Integration Testing

```python
# tests/test_integration.py
import pytest
import os
from src.config import ODBCConfig
from src.odbc_pool import ODBCConnectionPool
from src.services.sales_order_service import SalesOrderService

@pytest.fixture
async def real_pool():
    """Create real ODBC connection pool for integration testing."""
    config = ODBCConfig()
    pool = ODBCConnectionPool(config.connection_string)
    await pool.initialize()
    yield pool
    await pool.close()

@pytest.mark.asyncio
async def test_list_overdue_orders_integration(real_pool):
    """Integration test: fetch real overdue orders from NetSuite."""

    # Skip if ODBC not configured
    if not os.getenv("NETSUITE_ODBC_STRING"):
        pytest.skip("ODBC not configured")

    service = SalesOrderService(real_pool)
    orders = await service.list_overdue_orders(days_past_due=7)

    # Verify structure
    assert isinstance(orders, list)
    if orders:
        assert "transaction_number" in orders[0]
```

---

## 12. Connection Lifecycle (STDIO Servers)

### 12.1 STDIO Server Lifecycle

```
1. STARTUP PHASE
   ├─ Claude Code starts Python process with server.py
   ├─ Server initializes (imports modules)
   ├─ on_startup() hooks execute
   │  ├─ ODBC connection pool created
   │  ├─ Environment variables validated
   │  └─ Services initialized
   └─ Server enters STDIO loop (listening on stdin)

2. RUNNING PHASE
   ├─ Claude Code sends JSON-RPC request on stdin
   │  └─ {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {...}}
   ├─ Server deserializes request
   ├─ Tool handler executes (acquires ODBC connection)
   ├─ Server serializes response
   └─ Server writes JSON-RPC response on stdout
       └─ {"jsonrpc": "2.0", "id": 1, "result": {...}}

3. SHUTDOWN PHASE
   ├─ Claude Code sends EOF on stdin (closes pipe)
   ├─ Server detects EOF
   ├─ on_shutdown() hooks execute
   │  ├─ ODBC connection pool closed
   │  └─ Resources cleaned up
   └─ Python process exits (exit code 0)
```

### 12.2 Graceful Shutdown

```python
import signal
import sys

async def shutdown_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    logger.info(f"Received signal {sig}, shutting down...")
    # FastMCP handles cleanup via on_shutdown()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)
```

### 12.3 Connection Timeout Handling

```python
import asyncio

class ODBCConnectionPool:
    """Connection pool with timeout protection."""

    async def acquire(self, timeout_seconds: int = 30):
        """Acquire connection with timeout."""
        try:
            # Wait up to timeout_seconds for a connection
            conn = await asyncio.wait_for(
                self._get_connection(),
                timeout=timeout_seconds
            )
            return conn

        except asyncio.TimeoutError:
            logger.error(f"Connection acquisition timeout after {timeout_seconds}s")
            raise ToolError("ODBC connection timeout; server unresponsive")

    async def _get_connection(self):
        """Get connection from pool (may block if pool exhausted)."""
        await self.semaphore.acquire()
        return self.connections.pop()
```

---

## 13. Tool Naming Conventions

### 13.1 Verb-First Pattern

Use action verbs to indicate intent:

```python
# QUERY (retrieval, read-only)
@mcp.tool()
async def query_sales_order(so_number: str) -> str:
    """Fetch a single sales order."""

@mcp.tool()
async def query_transaction_line(transaction_id: int) -> str:
    """Get line items from a transaction."""

# LIST (bulk retrieval, read-only)
@mcp.tool()
async def list_overdue_orders(days_threshold: int = 7) -> str:
    """List all orders overdue by N days."""

@mcp.tool()
async def list_inventory_by_location(location_id: int) -> str:
    """List all items in a warehouse location."""

# SEARCH (fuzzy retrieval, read-only)
@mcp.tool()
async def search_customers_by_name(name_pattern: str) -> str:
    """Search for customers matching name pattern."""

@mcp.tool()
async def search_items_by_sku(sku_pattern: str) -> str:
    """Find items by SKU (supports wildcards)."""

# CALCULATE (derived value, read-only)
@mcp.tool()
async def calculate_days_past_due(order_date: str) -> str:
    """Calculate days since order creation date."""

@mcp.tool()
async def calculate_inventory_value(location_id: int) -> str:
    """Calculate total inventory value at location."""

# GET (single object, read-only) - use rarely, QUERY preferred
@mcp.tool()
async def get_customer(customer_id: int) -> str:
    """Fetch customer details by ID."""

# UPDATE (modification)
@mcp.tool()
async def update_order_status(so_number: str, new_status: str) -> str:
    """Update sales order status."""

# CREATE (new object)
@mcp.tool()
async def create_purchase_order(supplier_id: int, items: List[dict]) -> str:
    """Create new purchase order."""

# DELETE (removal)
@mcp.tool()
async def delete_draft_order(so_number: str) -> str:
    """Delete draft sales order."""
```

### 13.2 Naming Anti-Patterns

```python
# POOR - vague verbs
@mcp.tool()
async def process_data(input: str) -> str:
    """Process some data."""  # What data? What process?

# POOR - missing context
@mcp.tool()
async def get_info(id: str) -> str:
    """Get information."""  # What info? For what object?

# POOR - abbreviations
@mcp.tool()
async def qry_so(num: str) -> str:
    """Qry SO by num."""  # Unclear to LLM

# POOR - inconsistent naming
@mcp.tool()
async def fetch_orders() -> str:
    """Get orders."""  # fetch vs get?

@mcp.tool()
async def list_invoices() -> str:
    """Get invoices."""  # list vs get?

# GOOD - clear, consistent
@mcp.tool()
async def query_sales_orders_by_customer(customer_id: int) -> str:
    """Fetch all sales orders for a specific customer."""

@mcp.tool()
async def list_invoices_by_date_range(start_date: str, end_date: str) -> str:
    """List invoices within date range."""
```

### 13.3 LLM-Friendly Naming

Names should be unambiguous to Claude when used as function calls:

```python
# Good - Claude will understand exactly what this does
query_sales_order
list_overdue_orders
calculate_days_past_due
search_customers_by_name

# Less helpful - Claude might misinterpret
get_data  # Which data?
process  # Process what?
execute  # Execute what?
handle   # Handle what?
do_stuff # Meaningless
```

---

## Summary: Quick Reference

### FastMCP Server Template

```python
# src/server.py
import asyncio
import os
import json
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from src.config import ODBCConfig
from src.odbc_pool import ODBCConnectionPool
from src.services.sales_order_service import SalesOrderService

# Initialize MCP server
mcp = FastMCP("netsuite-odbc")

# Global state (initialized on startup)
config = None
connection_pool = None
sales_order_service = None

# Startup hook
@mcp.lifecycle.on_startup()
async def startup():
    global config, connection_pool, sales_order_service

    config = ODBCConfig()
    config.validate()

    connection_pool = ODBCConnectionPool(
        config.connection_string,
        pool_size=config.pool_size
    )
    await connection_pool.initialize()

    sales_order_service = SalesOrderService(connection_pool)

# Shutdown hook
@mcp.lifecycle.on_shutdown()
async def shutdown():
    global connection_pool
    if connection_pool:
        await connection_pool.close()

# Tool definitions
@mcp.tool()
async def query_sales_order(so_number: str) -> str:
    """Fetch sales order details from NetSuite ODBC.

    Args:
        so_number: Sales order number (e.g., "SO-12345")

    Returns:
        JSON string with order details
    """
    order = await sales_order_service.get_sales_order(so_number)
    if not order:
        from mcp.tools import ToolError
        raise ToolError(f"Order not found: {so_number}")
    return json.dumps(order)

@mcp.tool()
async def list_overdue_orders(days_past_due: int = 7) -> str:
    """List sales orders overdue by N days.

    Args:
        days_past_due: Threshold in days (default 7)

    Returns:
        JSON string with list of overdue orders
    """
    orders = await sales_order_service.list_overdue_orders(days_past_due)
    return json.dumps({
        "count": len(orders),
        "orders": orders
    })

# Entry point
if __name__ == "__main__":
    mcp.run()
```

---

## Appendix: Resources

- **MCP Spec**: https://modelcontextprotocol.io/
- **FastMCP GitHub**: https://github.com/jlowin/fastmcp
- **Official MCP SDK**: https://github.com/modelcontextprotocol/python-sdk
- **NetSuite ODBC Driver Docs**: NetSuite admin portal
- **Pydantic v2**: https://docs.pydantic.dev/latest/
- **pyodbc**: https://github.com/mkleehammer/pyodbc

---

**Document Version**: 1.0
**Last Updated**: 2026-02-11
**Status**: Complete reference for MCP Python SDK patterns and ODBC integration
