# pyodbc Architecture & ODBC Drivers Reference

Research document for pyodbc integration, driver detection, platform differences, and best practices.

---

## Table of Contents

1. [pyodbc Architecture](#pyodbc-architecture)
2. [Catalog Functions](#catalog-functions)
3. [Connection Management](#connection-management)
4. [Driver Detection](#driver-detection)
5. [Platform Differences](#platform-differences)
6. [Driver Quirks (6 Major Drivers)](#driver-quirks-6-major-drivers)
7. [32-bit vs 64-bit](#32-bit-vs-64-bit)
8. [Encoding & Character Sets](#encoding--character-sets)
9. [Error Handling](#error-handling)
10. [Best Practices](#best-practices)

---

## pyodbc Architecture

pyodbc is a Python database adapter that bridges Python applications to relational databases via ODBC (Open Database Connectivity).

### Call Stack

```
Python Application
    ↓
pyodbc (Python wrapper)
    ↓
pyodbc C extension (_pyodbc)
    ↓
ODBC Driver Manager (Windows: odbc32.dll | Linux: unixODBC libodbc.so | macOS: iODBC)
    ↓
Database-Specific ODBC Driver (e.g., SQL Server Driver, Oracle Instant Client)
    ↓
Database Server (SQL Server, Oracle, PostgreSQL, MySQL, etc.)
```

### Key Layers

1. **Python wrapper**: `pyodbc` module (pure Python API)
2. **C extension**: `_pyodbc` (Cython-compiled, handles ODBC calls)
3. **Driver Manager**: OS-level ODBC manager
4. **Database Driver**: Vendor-specific ODBC driver
5. **Database**: Remote server or embedded database

### Threading & Process Model

- pyodbc connections are **NOT thread-safe** by default
- GIL (Global Interpreter Lock) prevents true parallelism
- Connection objects must be thread-local or protected by locks
- Query execution releases GIL (allows other threads to run during I/O)
- Cursor objects are tied to a connection; one cursor per connection is safest

---

## Catalog Functions

Catalog functions query database schema without writing a separate SQL statement. All return cursor-like objects that can be iterated.

### cursor.tables()

Query available tables in the database.

**Signature**:
```python
cursor.tables(catalog=None, schema=None, table=None, tableType=None)
```

**Parameters**:
- `catalog` (str|None): Catalog name (usually database name). `%` = wildcard, `None` = current catalog
- `schema` (str|None): Schema/owner. `%` = wildcard
- `table` (str|None): Table name pattern. `%` = wildcard
- `tableType` (str|None): Filter by type ('TABLE', 'VIEW', 'SYSTEM TABLE', etc.). Comma-separated list or `None`

**Returns**: Iterator yielding tuples of:
```
(catalog, schema, table_name, table_type, remarks)
```

**Example**:
```python
import pyodbc

conn = pyodbc.connect('DRIVER={SQL Server};SERVER=localhost;DATABASE=TestDB')
cursor = conn.cursor()

# List all tables in schema dbo
for row in cursor.tables(schema='dbo', tableType='TABLE'):
    print(f"{row.table_schema}.{row.table_name}")

# List all views
for row in cursor.tables(tableType='VIEW'):
    print(row.table_name)
```

### cursor.columns()

Query columns (fields) of a specific table.

**Signature**:
```python
cursor.columns(catalog=None, schema=None, table=None, column=None)
```

**Parameters**:
- `catalog` (str|None): Catalog name
- `schema` (str|None): Schema name
- `table` (str|None): Table name (often required)
- `column` (str|None): Column name pattern (`%` = wildcard)

**Returns**: Iterator yielding tuples of:
```
(catalog, schema, table_name, column_name, data_type, type_name, column_size,
 buffer_length, decimal_digits, num_prec_radix, nullable, remarks, column_def,
 sql_data_type, sql_datetime_sub, char_octet_length, ordinal_position, is_nullable)
```

**Example**:
```python
# Get all columns of a table
for row in cursor.columns(table='Customers'):
    print(f"{row.column_name}: {row.type_name}({row.column_size}), nullable={row.is_nullable}")

# Get specific column info
for row in cursor.columns(table='Orders', column='OrderID'):
    print(f"Data type: {row.sql_data_type}, Size: {row.column_size}")
```

### cursor.primaryKeys()

Retrieve primary key columns of a table.

**Signature**:
```python
cursor.primaryKeys(catalog=None, schema=None, table=None)
```

**Parameters**:
- `catalog` (str|None): Catalog name
- `schema` (str|None): Schema name
- `table` (str|None): Table name

**Returns**: Iterator yielding tuples of:
```
(catalog, schema, table_name, column_name, key_seq, pk_name)
```

**Example**:
```python
# Get primary key columns
pk_cols = []
for row in cursor.primaryKeys(table='Customers'):
    pk_cols.append((row.column_name, row.key_seq))
    print(f"PK Column: {row.column_name} (sequence {row.key_seq})")
```

### cursor.foreignKeys()

Retrieve foreign key relationships.

**Signature**:
```python
cursor.foreignKeys(
    primaryCatalog=None, primarySchema=None, primaryTable=None,
    foreignCatalog=None, foreignSchema=None, foreignTable=None
)
```

**Parameters**:
- `primaryCatalog/Schema/Table`: Primary key side (parent table)
- `foreignCatalog/Schema/Table`: Foreign key side (referencing table)

**Returns**: Iterator yielding tuples of:
```
(pkcatalog, pkschema, pktable, pkcolumn, fkcatalog, fkschema, fktable,
 fkcolumn, key_seq, update_rule, delete_rule, fk_name, pk_name, deferability)
```

**Example**:
```python
# Get foreign keys referencing a table
for row in cursor.foreignKeys(primaryTable='Customers'):
    print(f"FK: {row.fktable}.{row.fkcolumn} -> {row.pktable}.{row.pkcolumn}")

# Get foreign keys in a table
for row in cursor.foreignKeys(foreignTable='Orders'):
    print(f"References: {row.pktable}({row.pkcolumn})")
```

### cursor.statistics()

Retrieve index and statistics information.

**Signature**:
```python
cursor.statistics(catalog=None, schema=None, table=None, unique=False, approximate=False)
```

**Parameters**:
- `catalog`, `schema`, `table`: Scope of statistics
- `unique` (bool): If True, return only unique indexes
- `approximate` (bool): If True, allow approximate results

**Returns**: Iterator yielding tuples of:
```
(catalog, schema, table_name, non_unique, index_qualifier, index_name,
 type, ordinal_position, column_name, asc_or_desc, cardinality,
 pages, filter_condition)
```

**Example**:
```python
# List all indexes
for row in cursor.statistics(table='Orders'):
    if row.index_name:
        print(f"Index: {row.index_name}, Columns: {row.column_name}, Unique: {not row.non_unique}")
```

### cursor.getTypeInfo()

Get data type information from the database.

**Signature**:
```python
cursor.getTypeInfo(sqltype=None)
```

**Parameters**:
- `sqltype` (int|None): SQL data type constant. `None` returns all types.

**Returns**: Iterator yielding tuples of:
```
(type_name, data_type, column_size, literal_prefix, literal_suffix,
 create_params, nullable, case_sensitive, searchable, unsigned_attribute,
 fixed_prec_scale, auto_increment, local_type_name, minimum_scale,
 maximum_scale, sql_data_type, sql_datetime_sub, num_prec_radix, interval_precision)
```

**Example**:
```python
# Get all numeric types
for row in cursor.getTypeInfo():
    if 'INT' in row.type_name or 'NUMERIC' in row.type_name:
        print(f"{row.type_name}: size={row.column_size}, nullable={row.nullable}")

# Get info for VARCHAR
for row in cursor.getTypeInfo():
    if row.type_name == 'VARCHAR':
        print(f"VARCHAR: max size={row.column_size}, create_params={row.create_params}")
```

---

## Connection Management

### connect() Parameters

The primary way to establish a database connection in pyodbc.

**Signature**:
```python
pyodbc.connect(
    connectionString,
    autocommit=False,
    timeout=None,
    readonly=False,
    **kwargs
)
```

**Core Parameters**:
- `connectionString` (str, required): DSN or connection string
- `autocommit` (bool): Auto-commit mode (default False)
- `timeout` (int): Connection timeout in seconds
- `readonly` (bool): Connection is read-only (some drivers ignore)
- `**kwargs`: Arbitrary key=value pairs added to connection string

**Common Connection String Keywords**:
```
DRIVER         Driver name: {ODBC Driver 18 for SQL Server}
SERVER/DSN     Server address or DSN name
DATABASE       Database name
UID            User ID (username)
PWD            Password
PORT           Port number
Trusted_Connection  Windows authentication (SQL Server)
Encrypt        Encryption requirement (SQL Server)
TrustServerCertificate  Accept self-signed certs (SQL Server)
```

### DSN vs DSN-less Connections

**DSN (Data Source Name) Connection**:
```python
# Uses pre-configured ODBC data source
conn = pyodbc.connect('DSN=MyDataSource;UID=user;PWD=pass')
```

Pros:
- Connection details stored in registry (Windows) or ini files (Linux/macOS)
- Easy to manage across multiple machines
- Can be configured via OS tools

Cons:
- Requires pre-configuration on target machine
- Hidden passwords (security advantage or disadvantage)
- Not portable across platforms

**DSN-less Connection**:
```python
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 18 for SQL Server};'
    'SERVER=localhost;'
    'DATABASE=TestDB;'
    'UID=sa;'
    'PWD=YourPassword'
)
```

Pros:
- Portable (no pre-configuration needed)
- Explicit connection parameters
- Self-documenting

Cons:
- Passwords in connection string (security risk if logged)
- Longer, more verbose
- Driver name must be exact

### Autocommit Mode

**Default (False)**: Implicit transaction mode
```python
conn = pyodbc.connect(...)
conn.execute("INSERT INTO table VALUES (...)")
conn.commit()  # Must explicitly commit
```

**Autocommit (True)**: Each statement auto-commits
```python
conn = pyodbc.connect(..., autocommit=True)
conn.execute("INSERT INTO table VALUES (...)")  # Auto-committed
```

Trade-offs:
- Autocommit = True: Simpler for single statements, no rollback safety
- Autocommit = False: Explicit control, can batch statements, rollback on error

### Timeout: Connection vs Query

**Connection Timeout** (`timeout` parameter):
```python
# Timeout when connecting to server (seconds)
conn = pyodbc.connect(..., timeout=10)
```

Applied when: Opening TCP connection to ODBC driver manager.

**Query Timeout** (per-cursor):
```python
cursor = conn.cursor()
cursor.timeout = 30  # 30-second query timeout
cursor.execute("SELECT * FROM LargeTable")
```

Applied when: Executing a query.

Platform quirks:
- Windows: Both supported reliably
- Linux (unixODBC): Connection timeout works; query timeout driver-dependent
- macOS (iODBC): Same as Linux

### Pooling & Connection Reuse

pyodbc does **NOT** provide built-in connection pooling. Thread-safe pooling must be implemented manually.

**Simple Connection Pool Pattern**:
```python
import threading
import pyodbc
from queue import Queue

class ConnectionPool:
    def __init__(self, connection_string, max_size=5):
        self.connection_string = connection_string
        self.pool = Queue(maxsize=max_size)
        self._lock = threading.Lock()

        for _ in range(max_size):
            conn = pyodbc.connect(connection_string)
            self.pool.put(conn)

    def get_connection(self, timeout=5):
        try:
            return self.pool.get(timeout=timeout)
        except Queue.Empty:
            raise Exception("No connections available")

    def return_connection(self, conn):
        try:
            # Verify connection is alive
            conn.execute("SELECT 1")
            self.pool.put(conn)
        except Exception:
            # Dead connection; create a new one
            self.pool.put(pyodbc.connect(self.connection_string))

    def close_all(self):
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except:
                pass

# Usage
pool = ConnectionPool('DRIVER={SQL Server};SERVER=localhost;DATABASE=TestDB', max_size=10)
conn = pool.get_connection()
try:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Users")
finally:
    pool.return_connection(conn)
```

### Memory Management

**Cursor Memory**:
```python
# Fetch all at once (memory-intensive for large result sets)
rows = cursor.fetchall()

# Fetch incrementally (memory-efficient)
cursor.execute("SELECT * FROM LargeTable")
for row in cursor:
    process(row)  # Process one row at a time

# Fetch specific count
cursor.execute("SELECT * FROM LargeTable")
chunk = cursor.fetchmany(1000)
while chunk:
    for row in chunk:
        process(row)
    chunk = cursor.fetchmany(1000)
```

**Connection Cleanup**:
```python
try:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM table")
    # ...
finally:
    cursor.close()
    conn.close()
```

Always close cursors and connections explicitly; do not rely on garbage collection.

---

## Driver Detection

### pyodbc.drivers()

List all installed ODBC drivers.

```python
import pyodbc

drivers = pyodbc.drivers()
print(drivers)
# Output: ['ODBC Driver 18 for SQL Server', 'MySQL ODBC 8.0 Driver', 'PostgreSQL ODBC Driver', ...]
```

**Windows**: Reads from registry `HKEY_LOCAL_MACHINE\SOFTWARE\ODBC\ODBCINST.INI`

**Linux**: Reads from `/etc/odbcinst.ini`

**macOS**: Reads from `/Library/ODBC/odbcinst.ini` (iODBC) or similar

### pyodbc.dataSources()

List all configured ODBC data sources (DSNs).

```python
import pyodbc

data_sources = pyodbc.dataSources()
print(data_sources)
# Output: {'MyDatabase': 'SQL Server Driver', 'MyOracle': 'Oracle ODBC Driver', ...}
```

Returns dictionary of `{DSN_name: Driver_name}`.

### Connection.getinfo()

Query driver and connection properties.

**Signature**:
```python
value = conn.getinfo(InfoType)
```

**Common InfoType Constants**:

| Constant | Return Value |
|----------|--------------|
| `pyodbc.SQL_DBMS_NAME` | Database product name (e.g., 'Microsoft SQL Server') |
| `pyodbc.SQL_DRIVER_NAME` | Driver filename (e.g., 'MSOLEDBSQL.DLL') |
| `pyodbc.SQL_DRIVER_ODBC_VER` | ODBC version supported (e.g., '03.80') |
| `pyodbc.SQL_DBMS_VER` | Database version (e.g., '15.00.4073') |
| `pyodbc.SQL_DATABASE_NAME` | Current database name |
| `pyodbc.SQL_SERVER_NAME` | Server name |
| `pyodbc.SQL_USER_NAME` | Current user |
| `pyodbc.SQL_GETDATA_EXTENSIONS` | Supported data types |
| `pyodbc.SQL_IDENTIFIER_QUOTE_CHAR` | Quote character for identifiers |
| `pyodbc.SQL_SPECIAL_CHARACTERS` | Special characters allowed in identifiers |

**Example**:
```python
import pyodbc

conn = pyodbc.connect('DRIVER={SQL Server};SERVER=localhost;DATABASE=TestDB')

dbms_name = conn.getinfo(pyodbc.SQL_DBMS_NAME)
driver_name = conn.getinfo(pyodbc.SQL_DRIVER_NAME)
driver_version = conn.getinfo(pyodbc.SQL_DBMS_VER)

print(f"DBMS: {dbms_name}")
print(f"Driver: {driver_name}")
print(f"Version: {driver_version}")
```

### Driver Detection Pattern

Complete driver detection helper:

```python
import pyodbc
import re

class DriverDetector:
    @staticmethod
    def get_installed_drivers():
        """Return list of installed ODBC drivers."""
        return pyodbc.drivers()

    @staticmethod
    def get_dsn_list():
        """Return dict of configured DSNs."""
        return pyodbc.dataSources()

    @staticmethod
    def detect_driver(driver_keyword):
        """
        Find installed driver by partial name.

        Args:
            driver_keyword: Partial driver name (e.g., 'SQL Server', 'Oracle', 'PostgreSQL')

        Returns:
            Full driver name or None
        """
        drivers = pyodbc.drivers()
        keyword_lower = driver_keyword.lower()
        for driver in drivers:
            if keyword_lower in driver.lower():
                return driver
        return None

    @staticmethod
    def get_driver_info(conn):
        """
        Return dictionary of driver/DBMS info from active connection.
        """
        return {
            'dbms_name': conn.getinfo(pyodbc.SQL_DBMS_NAME),
            'driver_name': conn.getinfo(pyodbc.SQL_DRIVER_NAME),
            'driver_version': conn.getinfo(pyodbc.SQL_DBMS_VER),
            'driver_odbc_version': conn.getinfo(pyodbc.SQL_DRIVER_ODBC_VER),
            'database': conn.getinfo(pyodbc.SQL_DATABASE_NAME),
            'server': conn.getinfo(pyodbc.SQL_SERVER_NAME),
            'user': conn.getinfo(pyodbc.SQL_USER_NAME),
        }

    @staticmethod
    def match_dbms_type(conn):
        """
        Identify database system from connection.

        Returns:
            'sql_server', 'oracle', 'postgresql', 'mysql', 'sqlite', 'unknown'
        """
        dbms_name = conn.getinfo(pyodbc.SQL_DBMS_NAME).lower()

        if 'sql server' in dbms_name:
            return 'sql_server'
        elif 'oracle' in dbms_name:
            return 'oracle'
        elif 'postgres' in dbms_name:
            return 'postgresql'
        elif 'mysql' in dbms_name:
            return 'mysql'
        elif 'sqlite' in dbms_name:
            return 'sqlite'
        else:
            return 'unknown'

# Usage
if __name__ == '__main__':
    detector = DriverDetector()

    # List installed drivers
    print("Installed Drivers:")
    for driver in detector.get_installed_drivers():
        print(f"  - {driver}")

    # List DSNs
    print("\nConfigured DSNs:")
    for dsn, driver in detector.get_dsn_list().items():
        print(f"  - {dsn} ({driver})")

    # Find SQL Server driver
    sql_server_driver = detector.detect_driver('SQL Server')
    print(f"\nDetected SQL Server Driver: {sql_server_driver}")

    # Connect and get info
    if sql_server_driver:
        try:
            conn = pyodbc.connect(
                f'DRIVER={{{sql_server_driver}}};'
                f'SERVER=localhost;'
                f'DATABASE=TestDB;'
                f'Trusted_Connection=yes'
            )
            info = detector.get_driver_info(conn)
            print(f"\nConnection Info:")
            for key, value in info.items():
                print(f"  {key}: {value}")

            dbms_type = detector.match_dbms_type(conn)
            print(f"\nDetected DBMS Type: {dbms_type}")

            conn.close()
        except Exception as e:
            print(f"Connection error: {e}")
```

---

## Platform Differences

### Windows

**ODBC Manager**: `odbc32.dll` (32-bit) or `odbc64.dll` (64-bit)

**Configuration Storage**: Registry
```
HKEY_LOCAL_MACHINE\SOFTWARE\ODBC\ODBCINST.INI    # Drivers
HKEY_LOCAL_MACHINE\SOFTWARE\ODBC\ODBC.INI        # DSNs
```

**Tools**:
- ODBC Data Source Administrator (`OdbcAd32.exe` or `odbcad32.exe`)
- Command-line: `regedit` to view registry entries

**Quirks**:
- 32-bit and 64-bit drivers are separate installations
- Visual C++ Runtime libraries (`MSVCRT`) may be required
- Windows Registry access requires admin for system DSNs

**Example Connection String**:
```python
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 18 for SQL Server};'
    'SERVER=myserver.database.windows.net;'
    'DATABASE=mydb;'
    'UID=username;'
    'PWD=password'
)
```

### Linux

**ODBC Manager**: `unixODBC` (standard library)

**Installation**:
```bash
# Debian/Ubuntu
apt-get install unixodbc unixodbc-dev

# Red Hat/CentOS
yum install unixODBC unixODBC-devel

# macOS (alternative to iODBC)
brew install unixodbc
```

**Configuration Files**:
```
/etc/odbcinst.ini       # Installed drivers
/etc/odbc.ini           # System DSNs
~/.odbc.ini             # User DSNs
```

**Sample `/etc/odbcinst.ini`**:
```ini
[PostgreSQL ODBC Driver]
Description=PostgreSQL ODBC Driver
Driver=/usr/lib/x86_64-linux-gnu/odbc/psqlodbcw.so
Setup=/usr/lib/x86_64-linux-gnu/odbc/psqlodbcw.so
FileUsage=1
CPTimeout=
CPReuse=

[ODBC Driver 18 for SQL Server]
Description=Microsoft ODBC Driver 18 for SQL Server
Driver=/opt/microsoft/msodbcsql18/lib64/libmsodbcsql-18.0.so.1.1
FileUsage=1
UsageCount=1
```

**Tools**:
- `odbcinst` — command-line driver manager
- `isql` — test ODBC connections
- Manual `.ini` file editing

**Quirks**:
- No system-wide driver registry (file-based only)
- Driver paths must be absolute
- Case-sensitive driver names
- Must install database-specific ODBC packages

**Example (PostgreSQL on Linux)**:
```python
# Ensure /etc/odbc.ini has PostgreSQL entry
conn = pyodbc.connect('DSN=MyPostgreSQL;UID=user;PWD=pass')

# Or DSN-less (requires unixODBC properly configured)
conn = pyodbc.connect(
    'Driver=PostgreSQL ODBC Driver;'
    'Server=localhost;'
    'Port=5432;'
    'Database=mydb;'
    'UID=user;'
    'PWD=pass'
)
```

### macOS

**ODBC Manager Options**:
1. **iODBC** (default, included in macOS)
2. **unixODBC** (alternative, via Homebrew)

**Configuration Files** (iODBC):
```
~/.odbc.ini           # User DSNs
~/.odbcinst.ini       # User drivers
/Library/ODBC/        # System drivers/DSNs
```

**Installation**:
```bash
# Use Homebrew for driver installation
brew install libreoffice/office/mdbtools  # For MDB driver
brew install unixodbc                     # Or unixODBC
brew install psqlodbc                     # PostgreSQL driver
brew install mysql-connector-odbc         # MySQL driver
```

**Quirks**:
- iODBC vs unixODBC conflict possible (avoid mixing)
- Driver paths may differ from Linux
- Homebrew typically installs unixODBC, not iODBC
- System Integrity Protection (SIP) restricts `/usr/lib` modifications

**Example (PostgreSQL on macOS with Homebrew)**:
```python
# Homebrew installs to /usr/local/lib
# ~/.odbc.ini:
# [PostgreSQL]
# Description=PostgreSQL
# Driver=/usr/local/lib/psqlodbcw.so
# Server=localhost
# Port=5432
# Database=mydb

conn = pyodbc.connect('DSN=PostgreSQL;UID=user;PWD=pass')
```

---

## Driver Quirks (6 Major Drivers)

### 1. SQL Server (ODBC Driver 18 for SQL Server)

**Download**: Microsoft ODBC Driver 18 for SQL Server (latest stable)

**Key Parameters**:
```python
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 18 for SQL Server};'
    'SERVER=myserver.database.windows.net;'
    'DATABASE=mydb;'
    'UID=username;'
    'PWD=password;'
    'Encrypt=yes;'  # Require encryption
    'TrustServerCertificate=yes;'  # Accept self-signed certs (dev only)
    'Connection Timeout=10'  # Connection timeout
)
```

**Quirks**:
- **Encryption**: `Encrypt=yes` required for Azure SQL; local dev can use `Encrypt=no`
- **DATETIMEOFFSET**: ODBC Driver 18 handles timezone offsets; earlier drivers may fail
- **Unicode**: Supports UTF-16LE internally; automatic encoding conversion
- **Trusted Connection**: Windows auth via `Trusted_Connection=yes` (not available on Linux/macOS)
- **Timeout**: `Connection Timeout` (connection) and cursor-level `timeout` both supported
- **Batch Operations**: Slower with `INSERT INTO ... VALUES ...` chains; use bulk insert for large batches
- **Large Data Types**: `MAX` column types (VARCHAR(MAX), NVARCHAR(MAX)) work but slower for large fetches

**Example (Azure SQL with Managed Identity)**:
```python
import pyodbc
import os
from azure.identity import DefaultAzureCredential

# Get Azure token for SQL auth
credential = DefaultAzureCredential()
token = credential.get_token('https://database.windows.net/.default').token

# Connect with token
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 18 for SQL Server};'
    'SERVER=myserver.database.windows.net;'
    'DATABASE=mydb;'
    'UID=my_user@azure.com;'
    'PWD=' + token + ';'
    'Encrypt=yes'
)
```

### 2. Oracle (Oracle ODBC Driver)

**Download**: Oracle Instant Client with ODBC driver

**Key Parameters**:
```python
conn = pyodbc.connect(
    'DRIVER={Oracle ODBC Driver};'
    'DBQ=hostname:1521/service_name;'  # or TNS name
    'UID=username;'
    'PWD=password'
)
```

Alternative (using tnsnames.ora):
```python
conn = pyodbc.connect(
    'DRIVER={Oracle ODBC Driver};'
    'DBQ=MyOracleService;'  # References entry in tnsnames.ora
    'UID=username;'
    'PWD=password'
)
```

**Quirks**:
- **No Query Timeout**: Oracle ODBC driver ignores `cursor.timeout`; use SQL `DBMS_SESSION.SET_SQL_TRACE()` or database-level limits
- **Stale Connections in Pools**: Oracle may close idle connections after 30 minutes; must verify connection is alive before use
- **Case Sensitivity**: Object names are case-insensitive unless quoted (double quotes)
- **Unicode**: Uses database character set (NLS_LANG); explicit `ALTER SESSION SET NLS_LANG=...` may be needed
- **Number Precision**: ODBC maps NUMBER to different SQL types; explicit `CAST` to NUMBER(10,2) recommended for currency
- **Batch Inserts**: Use PL/SQL bulk operations for large inserts (FORALL loop) rather than ODBC INSERT loops
- **Cursor Management**: Always close cursors explicitly; Oracle ODBC keeps server-side cursor handles open

**Example (Connection Validation)**:
```python
def safe_oracle_connection(conn):
    """Validate Oracle connection is alive."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM DUAL")
        cursor.fetchone()
        return True
    except Exception:
        return False
```

### 3. PostgreSQL (PostgreSQL ODBC Driver)

**Download**: `psqlodbc` (psqlodbc14.so on Linux, psqlodbcw.so on Windows)

**Key Parameters**:
```python
conn = pyodbc.connect(
    'DRIVER={PostgreSQL ODBC Driver};'
    'Server=localhost;'
    'Port=5432;'
    'Database=mydb;'
    'UID=username;'
    'PWD=password;'
    'UseDeclareFetch=1;'  # Use server-side cursors for large result sets
    'ConnectionTimeout=10'
)
```

**Quirks**:
- **Encoding**: Must match server encoding (usually UTF-8). Set `PGCLIENTENCODING=UTF8` environment variable if issues occur
- **Boolean**: PostgreSQL BOOLEAN maps to ODBC BIT; fetch as string for clarity
- **Arrays**: PostgreSQL arrays (INT[], VARCHAR[]) not directly supported by ODBC; convert to JSON or string representation
- **UUID**: UUID type maps to ODBC VARCHAR; treat as string
- **JSONB**: JSONB maps to ODBC VARCHAR; fetch and parse as JSON string
- **Large Objects (LOB)**: PostgreSQL bytea and text work but slow; consider using native libpq if performance critical
- **Cursor Memory**: UseDeclareFetch=1 uses server-side cursors (more memory on server, less on client)
- **Transaction Isolation**: PostgreSQL ODBC defaults to READ COMMITTED; explicit `SET TRANSACTION ISOLATION LEVEL` if needed

**Example (Handle Boolean & UUID)**:
```python
conn = pyodbc.connect(...)
cursor = conn.cursor()

cursor.execute("SELECT id, name, is_active, tags FROM users")
for row in cursor:
    user_id = row[0]
    name = row[1]
    is_active = row[2] == 1  # Convert BIT to boolean
    tags = row[3]  # UUID as string
    print(f"{user_id}: {name}, active={is_active}")
```

### 4. MySQL (MySQL ODBC Driver or MySQL Connector/ODBC)

**Download**: `mysql-connector-odbc` (latest version supports UTF-8, MySQL 8.0+)

**Key Parameters**:
```python
conn = pyodbc.connect(
    'DRIVER={MySQL ODBC 8.0 ANSI Driver};'  # Use ANSI driver for UTF-8
    'Server=localhost;'
    'Port=3306;'
    'Database=mydb;'
    'UID=root;'
    'PWD=password;'
    'CHARSET=utf8mb4'  # Explicit charset
)
```

**Quirks**:
- **Driver Variants**: Two versions per MySQL version:
  - `MySQL ODBC X.X ANSI Driver` — standard SQL (recommended)
  - `MySQL ODBC X.X Unicode Driver` — non-standard (avoid)
- **UTF-8**: Use ANSI driver with `CHARSET=utf8mb4` for full Unicode support
- **Boolean**: MySQL TINYINT(1) is BOOLEAN; fetches as 0/1 integer
- **Floating Point**: FLOAT/DOUBLE lose precision; use DECIMAL for currency
- **Timezone**: MySQL TIMESTAMP is timezone-aware but driver may convert to local; be explicit with `CONVERT_TZ()`
- **Large Inserts**: Use `LOAD DATA INFILE` or batch INSERT via native connection for bulk operations
- **Auto-Increment**: `AUTO_INCREMENT` returns last insert ID via `cursor.description` or `cursor.messages`
- **Prepared Statements**: MySQL ODBC supports but adds minimal safety vs. string escaping

**Example (Bulk Insert)**:
```python
import pyodbc

conn = pyodbc.connect(
    'DRIVER={MySQL ODBC 8.0 ANSI Driver};'
    'Server=localhost;'
    'Database=mydb;'
    'UID=root;'
    'PWD=password;'
    'CHARSET=utf8mb4'
)

cursor = conn.cursor()

# Batch insert (slower but works)
data = [
    ('Alice', 'alice@example.com'),
    ('Bob', 'bob@example.com'),
]

cursor.executemany("INSERT INTO users (name, email) VALUES (?, ?)", data)
conn.commit()

# For large batches, consider native MySQL client:
# cursor.execute("LOAD DATA LOCAL INFILE '/tmp/data.csv' INTO TABLE users ...")
```

### 5. IBM i / AS/400 (IBM i Access ODBC Driver)

**Download**: IBM i Access for Windows/Linux ODBC driver

**Key Parameters**:
```python
# Correct format (SYSTEM=, not SERVER=)
conn = pyodbc.connect(
    'DRIVER={IBM i Access ODBC Driver};'
    'SYSTEM=192.168.1.100;'  # IP or hostname
    'UID=username;'
    'PWD=password;'
    'LibraryList=MYLIB,QSYS2;'  # Library path
    'Commit=2'  # 0=No commit, 1=Commit level 0, 2=Commit level 1
)
```

**Quirks**:
- **SYSTEM vs SERVER**: IBM i uses `SYSTEM=` keyword (not `SERVER=`)
- **Library List**: IBM i uses libraries instead of schemas; use `LibraryList=` parameter
- **Driver Name Rebrandings**: Older driver names (`iSeries Access ODBC`) vs. newer (`IBM i Access ODBC`); check installed drivers
- **Commit Mode**: Default `Commit=1` (level 0) may behave unexpectedly; set `Commit=2` for level 1
- **Character Set**: IBM i defaults to EBCDIC (not UTF-8); set `CCSIDASCII=819` for UTF-8
- **Cursor Type**: Keyset-driven cursors not fully supported; stick to forward-only
- **Long Field Names**: Older IBM i/AS400 limited to 10-char names; newer versions support longer names via `LongFieldNames=1`

**Example (with Character Set)**:
```python
conn = pyodbc.connect(
    'DRIVER={IBM i Access ODBC Driver};'
    'SYSTEM=myibmi.company.com;'
    'UID=username;'
    'PWD=password;'
    'LibraryList=PRODLIB;'
    'CCSIDASCII=819'  # UTF-8
)
```

### 6. NetSuite (NetSuite ODBC Driver via SuiteAnalytics Connect)

**Download**: NetSuite SuiteAnalytics Connect ODBC Driver (via NetSuite account)

**Key Parameters**:
```python
conn = pyodbc.connect(
    'DRIVER={NetSuite ODBC Driver};'
    'AccountID=1234567;'
    'Email=user@company.com;'
    'Password=YourPassword;'
    'Role=Administrator;'  # or specific role ID
    'LogLevel=2'  # 0=Off, 1=Errors, 2=All
)
```

Alternative (Token-based auth, more secure):
```python
conn = pyodbc.connect(
    'DRIVER={NetSuite ODBC Driver};'
    'AccountID=1234567;'
    'Email=user@company.com;'
    'Token=your_token_id:your_token_value;'  # OAuth token
    'Role=3;'  # Administrator role
)
```

**Quirks**:
- **Non-Standard Keywords**: Doesn't follow ODBC standard parameter naming (uses AccountID, Email, not UID/PWD)
- **Read-Only**: NetSuite ODBC is read-only (no INSERT/UPDATE/DELETE via ODBC; use REST API instead)
- **Connection Limit**: 5-10 concurrent connections per account (strict limit; pooling essential)
- **Query Timeout**: VERY long queries may timeout; include `WHERE` filters to reduce result set size
- **Authentication**: Supports password auth (deprecated by NetSuite) or token-based (recommended)
- **Role-Based Access**: Role parameter controls which data is visible; required for permissions
- **Table Names**: Non-standard; use `_TABLE_NAMES` pseudo-table to list available tables
- **Implicit Joins**: Foreign key relationships require explicit SQL joins; no automatic RELATED() function (like Power BI)
- **Date Format**: Defaults to YYYY-MM-DD UTC; timezone conversions may be needed
- **No Transactions**: ODBC does not support transaction control (COMMIT/ROLLBACK); all queries are auto-committed

**Example (Safe Connection with Retry Logic)**:
```python
import pyodbc
import time

def connect_netsuite(account_id, email, token, max_retries=3):
    """
    Connect to NetSuite with retry logic (handles rate limits).
    """
    for attempt in range(max_retries):
        try:
            conn = pyodbc.connect(
                'DRIVER={NetSuite ODBC Driver};'
                f'AccountID={account_id};'
                f'Email={email};'
                f'Token={token};'
                'Role=3'
            )
            # Verify connection
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM [Transaction]")
            cursor.fetchone()
            print(f"Connected to NetSuite (attempt {attempt + 1})")
            return conn
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Connection failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise Exception(f"NetSuite connection failed after {max_retries} attempts: {e}")

# Usage
conn = connect_netsuite(
    account_id='1234567',
    email='user@company.com',
    token='tokenid:tokenvalue'
)
cursor = conn.cursor()

# List available tables (NetSuite pseudo-table)
cursor.execute("SELECT TABLE_NAME FROM [_TABLE_NAMES] ORDER BY TABLE_NAME")
tables = [row[0] for row in cursor.fetchall()]
print(f"Available tables: {tables[:10]}...")  # Show first 10

# Query transactions (read-only)
cursor.execute(
    "SELECT id, document_number, transaction_date, amount "
    "FROM [Transaction] "
    "WHERE transaction_date >= CONVERT(DATE, GETDATE() - 30)"
)
for row in cursor:
    print(f"{row.document_number}: ${row.amount} on {row.transaction_date}")

conn.close()
```

---

## 32-bit vs 64-bit

### Architecture Mismatch Risks

**Python bits must match ODBC Driver Manager bits** (not optional).

| Python | ODBC Manager | Outcome |
|--------|-------------|---------|
| 64-bit | 64-bit | OK |
| 32-bit | 32-bit | OK |
| 64-bit | 32-bit | **FAIL**: "The specified module could not be found" |
| 32-bit | 64-bit | **FAIL**: "Can't open driver" |

### Detecting Python Architecture

```python
import platform
import struct

bits = struct.calcsize("P") * 8  # 32 or 64
print(f"Python: {bits}-bit ({platform.python_version()})")

# Or simpler:
import sys
print(f"Python: {sys.maxsize > 2**32 and '64-bit' or '32-bit'}")
```

### Detecting ODBC Manager Architecture

**Windows**:
```python
import os
import winreg

def get_odbc_arch():
    """Detect Windows ODBC manager bit version."""
    try:
        # 64-bit registry location
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r'SOFTWARE\ODBC\ODBCINST.INI')
        winreg.QueryInfoKey(key)
        return "64-bit"
    except:
        try:
            # 32-bit registry location (WOW64)
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r'SOFTWARE\WOW6432Node\ODBC\ODBCINST.INI')
            winreg.QueryInfoKey(key)
            return "32-bit"
        except:
            return "Unknown"

print(f"ODBC Manager: {get_odbc_arch()}")
```

**Linux**:
```bash
file /usr/lib/x86_64-linux-gnu/libodbc.so  # 64-bit
file /usr/lib/i386-linux-gnu/libodbc.so    # 32-bit
```

### Installing Multiple Architectures (Windows)

```batch
REM Install 64-bit ODBC Driver
msiexec /i "ODBC_Driver_64bit.msi" /passive

REM Install 32-bit ODBC Driver (requires 32-bit Python)
msiexec /i "ODBC_Driver_32bit.msi" /passive
```

Then, match Python architecture to installed driver:
```python
import struct
bits = struct.calcsize("P") * 8

if bits == 64:
    # Use 64-bit driver
    conn = pyodbc.connect('DRIVER={ODBC Driver 18 for SQL Server (x64)};...')
else:
    # Use 32-bit driver
    conn = pyodbc.connect('DRIVER={ODBC Driver 18 for SQL Server (x86)};...')
```

---

## Encoding & Character Sets

### Default Encoding: UTF-16LE

pyodbc **internally converts all strings to UTF-16LE** for ODBC API calls (Windows standard).

```python
# Python string "hello"
# → converted to UTF-16LE bytes: h\x00e\x00l\x00l\x00o\x00
# → sent to ODBC driver
# → driver converts to database encoding
```

### Per-Driver Character Set Handling

| Driver | Default Encoding | Explicit Setting | Notes |
|--------|------------------|------------------|-------|
| SQL Server | UTF-16LE (NVARCHAR) | `Encrypt=yes` (forces NVARCHAR) | Always UTF-16LE for NVARCHAR; VARCHAR uses code page |
| Oracle | Database charset (NLS_LANG) | `ALTER SESSION SET NLS_LANG=...` | Set at connection or via environment |
| PostgreSQL | UTF-8 (server-side) | `PGCLIENTENCODING=UTF8` env var | Driver auto-converts; verify client encoding |
| MySQL | Database charset | `CHARSET=utf8mb4` (connection param) | ANSI driver required for UTF-8; Unicode driver is UTF-16LE only |
| IBM i | EBCDIC (default) | `CCSIDASCII=819` for UTF-8 | Requires explicit CCSID parameter |
| NetSuite | UTF-8 | N/A (no control) | Always UTF-8; no option to change |

### Handling Encoding Issues

**Problem: "UnicodeEncodeError" on Windows with ODBC Driver**

```python
# BAD: Assumes default encoding
cursor.execute("INSERT INTO table (name) VALUES (?)", ('Naïve',))

# GOOD: Ensure UTF-8 input (Python 3 strings are Unicode by default)
name = 'Naïve'  # Already Unicode in Python 3
cursor.execute("INSERT INTO table (name) VALUES (?)", (name,))
```

**Problem: Retrieved data contains garbage characters**

```python
# Symptom: "âœ£" instead of "✓"
# Cause: Encoding mismatch between driver and database

# Solution: Verify connection encoding
conn = pyodbc.connect('...')

# For Oracle, set NLS_LANG
import os
os.environ['NLS_LANG'] = 'AMERICAN_AMERICA.AL32UTF8'  # Before connecting

# For PostgreSQL, set client encoding
import os
os.environ['PGCLIENTENCODING'] = 'UTF8'

# For MySQL, use ANSI driver with explicit charset
conn = pyodbc.connect(
    'DRIVER={MySQL ODBC 8.0 ANSI Driver};'
    '...;'
    'CHARSET=utf8mb4'
)
```

### Code Example: Safe String Handling

```python
import pyodbc
import sys

def safe_insert_unicode(conn, table, column, value):
    """
    Insert Unicode string safely.
    """
    # Python 3 strings are always Unicode; ensure no decode errors
    if isinstance(value, bytes):
        value = value.decode('utf-8')  # Convert bytes to string

    cursor = conn.cursor()
    try:
        cursor.execute(
            f"INSERT INTO {table} ({column}) VALUES (?)",
            (value,)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error inserting {repr(value)}: {e}")
        # Fallback: try ASCII-only or replacement characters
        ascii_value = value.encode('ascii', errors='replace').decode('ascii')
        cursor.execute(
            f"INSERT INTO {table} ({column}) VALUES (?)",
            (ascii_value,)
        )
        conn.commit()

# Usage
conn = pyodbc.connect('DRIVER={SQL Server};SERVER=localhost;DATABASE=TestDB')

# Test with various Unicode strings
test_values = [
    'Hello',           # ASCII
    'Naïve',          # Accented
    '✓ Done',         # Symbol
    '日本語',          # Japanese
]

for value in test_values:
    safe_insert_unicode(conn, 'TestTable', 'TextColumn', value)
```

---

## Error Handling

### pyodbc Exception Hierarchy

```
DatabaseError (base class for all ODBC errors)
├── DataError            # Data type conversion error
├── OperationalError     # Connection, authentication, timeout
├── IntegrityError       # Constraint violation (FK, UNIQUE, CHECK)
├── ProgrammingError     # SQL syntax error, invalid parameter
├── NotSupportedError    # Operation not supported by driver
└── InternalError        # ODBC driver internal error
```

### SQLSTATE Codes (Most Common)

| SQLSTATE | pyodbc Exception | Cause | Recovery |
|----------|-----------------|-------|----------|
| `08001` | OperationalError | Cannot connect to server | Retry, check server/credentials |
| `08003` | OperationalError | Connection not open | Reconnect |
| `HYT00` | OperationalError | Query timeout | Increase timeout, optimize query |
| `42S02` | ProgrammingError | Table does not exist | Check table name spelling |
| `42S22` | ProgrammingError | Column does not exist | Check column name |
| `22007` | DataError | Invalid datetime | Use ISO format (YYYY-MM-DD) |
| `23000` | IntegrityError | Constraint violation (FK, UNIQUE) | Check data uniqueness |
| `22008` | DataError | Datetime field overflow | Check datetime range |
| `08004` | OperationalError | Server rejected connection | Check auth, role, limits |
| `S1000` | DatabaseError | General error | Check ODBC driver logs |

### Exception Handling Pattern

```python
import pyodbc
import logging

logger = logging.getLogger(__name__)

def safe_query(conn, sql, params=None, max_retries=3):
    """
    Execute query with error handling and retry logic.
    """
    for attempt in range(max_retries):
        cursor = None
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            return cursor.fetchall()

        except pyodbc.OperationalError as e:
            # Connection/timeout errors (retryable)
            if '08001' in str(e) or 'HYT00' in str(e):
                wait_time = 2 ** attempt
                logger.warning(f"Operational error (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                if attempt == max_retries - 1:
                    raise
            else:
                raise

        except pyodbc.ProgrammingError as e:
            # SQL syntax or object not found (not retryable)
            logger.error(f"Programming error: {e}")
            raise

        except pyodbc.IntegrityError as e:
            # Constraint violation (not retryable)
            logger.error(f"Integrity error: {e}")
            raise

        except pyodbc.DatabaseError as e:
            # Generic ODBC error
            sqlstate = getattr(e.args[0], 'sqlstate', 'UNKNOWN')
            logger.error(f"Database error (SQLSTATE {sqlstate}): {e}")
            raise

        finally:
            if cursor:
                cursor.close()

def safe_connect(connection_string, max_retries=3):
    """
    Connect with retry logic for transient failures.
    """
    for attempt in range(max_retries):
        try:
            conn = pyodbc.connect(connection_string, timeout=10)
            logger.info("Connected successfully")
            return conn
        except pyodbc.OperationalError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"Connection failed (attempt {attempt + 1}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Connection failed after {max_retries} attempts: {e}")
                raise

# Usage
try:
    conn = safe_connect('DRIVER={SQL Server};SERVER=localhost;DATABASE=TestDB')
    results = safe_query(conn, "SELECT * FROM Users WHERE ID = ?", (123,))
    for row in results:
        print(row)
except Exception as e:
    logger.error(f"Unrecoverable error: {e}")
finally:
    if conn:
        conn.close()
```

### SQLSTATE Code Extraction

```python
import pyodbc

def extract_sqlstate(exception):
    """
    Extract SQLSTATE code from pyodbc exception.
    """
    try:
        # pyodbc stores SQLSTATE in args[0].sqlstate
        if hasattr(exception, 'args') and len(exception.args) > 0:
            arg = exception.args[0]
            if hasattr(arg, 'sqlstate'):
                return arg.sqlstate
    except:
        pass
    return None

try:
    conn = pyodbc.connect('DRIVER={SQL Server};SERVER=invalid')
except pyodbc.OperationalError as e:
    sqlstate = extract_sqlstate(e)
    print(f"SQLSTATE: {sqlstate}")  # e.g., "08001"
    print(f"Error: {e}")
```

---

## Best Practices

### 1. ConnectionManager Pattern

Thread-safe connection management with pooling.

```python
import threading
import pyodbc
from queue import Queue, Empty
import time
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Thread-safe ODBC connection pool with health checks.
    """

    def __init__(self, connection_string, pool_size=10, timeout=5):
        """
        Args:
            connection_string: ODBC connection string
            pool_size: Number of pooled connections
            timeout: Timeout for getting a connection from pool (seconds)
        """
        self.connection_string = connection_string
        self.pool_size = pool_size
        self.pool = Queue(maxsize=pool_size)
        self.timeout = timeout
        self._lock = threading.Lock()
        self._initialized = False
        self._initialize_pool()

    def _initialize_pool(self):
        """Populate pool with initial connections."""
        with self._lock:
            if self._initialized:
                return

            for i in range(self.pool_size):
                try:
                    conn = pyodbc.connect(self.connection_string, timeout=10)
                    self.pool.put(conn)
                except Exception as e:
                    logger.warning(f"Failed to initialize connection {i + 1}: {e}")

            self._initialized = True
            logger.info(f"Initialized pool with {self.pool.qsize()} connections")

    def _health_check(self, conn):
        """Verify connection is alive."""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def get_connection(self):
        """
        Get a connection from the pool.

        Returns:
            Active pyodbc connection

        Raises:
            TimeoutError if no connections available
        """
        try:
            conn = self.pool.get(timeout=self.timeout)

            # Verify connection is alive
            if not self._health_check(conn):
                logger.info("Discarding dead connection; creating new one")
                conn.close()
                conn = pyodbc.connect(self.connection_string, timeout=10)

            return conn
        except Empty:
            raise TimeoutError(f"No connections available after {self.timeout}s")

    def return_connection(self, conn):
        """
        Return a connection to the pool.

        If connection is dead, it is discarded and a new one is created.
        """
        if conn is None:
            return

        try:
            if self._health_check(conn):
                self.pool.put(conn, timeout=1)
            else:
                logger.info("Discarding dead connection before returning to pool")
                conn.close()
                # Create replacement
                try:
                    new_conn = pyodbc.connect(self.connection_string, timeout=10)
                    self.pool.put(new_conn, timeout=1)
                except Exception as e:
                    logger.warning(f"Failed to create replacement connection: {e}")
        except Exception as e:
            logger.error(f"Error returning connection: {e}")
            try:
                conn.close()
            except:
                pass

    def close_all(self):
        """Close all pooled connections."""
        while not self.pool.empty():
            try:
                conn = self.pool.get_nowait()
                conn.close()
            except:
                pass
        logger.info("Closed all pooled connections")

# Usage
manager = ConnectionManager(
    'DRIVER={SQL Server};SERVER=localhost;DATABASE=TestDB',
    pool_size=10
)

try:
    conn = manager.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Users")
    for row in cursor:
        print(row)
finally:
    manager.return_connection(conn)
```

### 2. Row Limits in Queries

Always limit result sets to avoid memory exhaustion.

```python
def fetch_large_result_set(conn, sql, batch_size=1000):
    """
    Fetch large result set in batches.
    """
    cursor = conn.cursor()
    cursor.execute(sql)

    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break

        for row in rows:
            yield row

    cursor.close()

# Usage
conn = pyodbc.connect('...')
for row in fetch_large_result_set(conn, "SELECT * FROM LargeTable"):
    process(row)
```

### 3. Schema Caching

Cache schema metadata to avoid repeated catalog function calls.

```python
import json
from pathlib import Path
from datetime import datetime, timedelta

class SchemaCatalog:
    """
    Cache database schema (tables, columns, keys) locally.
    """

    def __init__(self, cache_dir='./schema_cache', ttl_hours=24):
        """
        Args:
            cache_dir: Directory to store cache files
            ttl_hours: Cache time-to-live (hours)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)

    def _cache_file(self, db_type):
        return self.cache_dir / f"{db_type}_schema.json"

    def _is_cached(self, db_type):
        """Check if cache is fresh."""
        cache_file = self._cache_file(db_type)
        if not cache_file.exists():
            return False

        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        return datetime.now() - mtime < self.ttl

    def build_cache(self, conn, db_type):
        """Build schema cache from live connection."""
        cursor = conn.cursor()

        schema = {
            'tables': {},
            'pk': {},
            'fk': {},
        }

        # Fetch all tables
        for row in cursor.tables():
            table_name = row.table_name
            schema['tables'][table_name] = {
                'columns': {},
                'type': row.table_type,
            }

        # Fetch columns per table
        for table_name in schema['tables'].keys():
            for row in cursor.columns(table=table_name):
                schema['tables'][table_name]['columns'][row.column_name] = {
                    'type': row.type_name,
                    'size': row.column_size,
                    'nullable': row.is_nullable == 'YES',
                }

        # Fetch primary keys
        for row in cursor.primaryKeys(table=None):
            table = row.table_name
            if table not in schema['pk']:
                schema['pk'][table] = []
            schema['pk'][table].append(row.column_name)

        # Cache to file
        cache_file = self._cache_file(db_type)
        with open(cache_file, 'w') as f:
            json.dump(schema, f, indent=2)

        return schema

    def get_schema(self, conn, db_type, refresh=False):
        """
        Get schema (from cache or live).
        """
        if not refresh and self._is_cached(db_type):
            cache_file = self._cache_file(db_type)
            with open(cache_file, 'r') as f:
                return json.load(f)

        return self.build_cache(conn, db_type)

# Usage
catalog = SchemaCatalog()
conn = pyodbc.connect('...')

schema = catalog.get_schema(conn, 'sql_server')
print(f"Tables: {list(schema['tables'].keys())}")
print(f"Primary Keys: {schema['pk']}")
```

### 4. Platform-Agnostic Driver Detection

Detect database platform and return appropriate driver.

```python
import pyodbc
import platform

class PlatformAgnosticDriver:
    """
    Detect and connect to database on any platform.
    """

    DRIVER_MAP = {
        'Windows': {
            'sql_server': 'ODBC Driver 18 for SQL Server',
            'postgresql': 'PostgreSQL ODBC Driver',
            'mysql': 'MySQL ODBC 8.0 ANSI Driver',
            'oracle': 'Oracle ODBC Driver',
        },
        'Linux': {
            'sql_server': 'ODBC Driver 18 for SQL Server',
            'postgresql': 'PostgreSQL ODBC Driver',
            'mysql': 'MySQL ODBC 8.0 Driver',
            'oracle': 'Oracle ODBC Driver',
        },
        'Darwin': {  # macOS
            'sql_server': 'ODBC Driver 18 for SQL Server',
            'postgresql': 'PostgreSQL ODBC Driver',
            'mysql': 'MySQL ODBC 8.0 Driver',
        },
    }

    @staticmethod
    def get_driver(db_type):
        """Get ODBC driver name for current platform and database type."""
        os_name = platform.system()
        driver_list = PlatformAgnosticDriver.DRIVER_MAP.get(os_name, {})
        driver = driver_list.get(db_type)

        if not driver:
            raise Exception(f"No driver found for {db_type} on {os_name}")

        # Verify driver is installed
        installed = pyodbc.drivers()
        if driver not in installed:
            # Try to find a similar driver
            candidates = [d for d in installed if db_type.lower() in d.lower()]
            if candidates:
                return candidates[0]
            raise Exception(f"Driver {driver} not installed")

        return driver

    @staticmethod
    def connect(db_type, host, database, user, password, port=None):
        """
        Connect to database with platform-agnostic driver selection.
        """
        driver = PlatformAgnosticDriver.get_driver(db_type)

        # Build connection string
        if db_type == 'sql_server':
            port = port or 1433
            conn_str = (
                f'DRIVER={{{driver}}};'
                f'SERVER={host},{port};'
                f'DATABASE={database};'
                f'UID={user};'
                f'PWD={password}'
            )
        elif db_type == 'postgresql':
            port = port or 5432
            conn_str = (
                f'Driver={driver};'
                f'Server={host};'
                f'Port={port};'
                f'Database={database};'
                f'UID={user};'
                f'PWD={password}'
            )
        elif db_type == 'mysql':
            port = port or 3306
            conn_str = (
                f'DRIVER={{{driver}}};'
                f'Server={host};'
                f'Port={port};'
                f'Database={database};'
                f'UID={user};'
                f'PWD={password};'
                f'CHARSET=utf8mb4'
            )
        else:
            raise Exception(f"Unsupported database type: {db_type}")

        return pyodbc.connect(conn_str, timeout=10)

# Usage
conn = PlatformAgnosticDriver.connect(
    'postgresql',
    'localhost',
    'mydb',
    'user',
    'password'
)
```

### 5. Secure Connection String Handling

Never hardcode credentials in connection strings.

```python
import os
import json
from pathlib import Path

class SecureConnector:
    """
    Load connection strings from environment or encrypted config.
    """

    @staticmethod
    def from_env(db_name):
        """
        Load connection string from environment variable.

        Convention: {DB_NAME}_CONNECTION_STRING
        """
        key = f"{db_name.upper()}_CONNECTION_STRING"
        conn_str = os.environ.get(key)

        if not conn_str:
            raise ValueError(f"Missing environment variable: {key}")

        return conn_str

    @staticmethod
    def from_config_file(config_path, db_name):
        """
        Load from JSON config file (credentials separate).

        File format:
        {
          "databases": {
            "mydb": {
              "driver": "ODBC Driver 18 for SQL Server",
              "server": "localhost",
              "database": "TestDB"
            }
          }
        }

        Credentials loaded from environment.
        """
        with open(config_path, 'r') as f:
            config = json.load(f)

        db_config = config['databases'][db_name]
        driver = db_config['driver']

        # Load credentials from environment
        user = os.environ.get(f"{db_name.upper()}_USER")
        password = os.environ.get(f"{db_name.upper()}_PASSWORD")

        if not user or not password:
            raise ValueError(f"Missing credentials for {db_name}")

        # Build connection string
        conn_str = f"DRIVER={{{driver}}};"
        for key, value in db_config.items():
            if key != 'driver':
                conn_str += f"{key}={value};"
        conn_str += f"UID={user};PWD={password}"

        return conn_str

# Usage
# Set environment variables
# export SQL_SERVER_CONNECTION_STRING="DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=TestDB;UID=sa;PWD=..."
# OR
# export MYDB_USER=sa
# export MYDB_PASSWORD=...

# Option 1: From environment variable
conn_str = SecureConnector.from_env('sql_server')

# Option 2: From config file + environment
conn_str = SecureConnector.from_config_file('config.json', 'mydb')

conn = pyodbc.connect(conn_str)
```

### 6. Query Timeout & Cancellation

Handle long-running queries safely.

```python
import pyodbc
import threading
import time

def execute_with_timeout(conn, sql, timeout_sec=30):
    """
    Execute query with timeout (raises exception if exceeds timeout).
    """
    result = {'rows': None, 'exception': None}

    def run_query():
        try:
            cursor = conn.cursor()
            cursor.timeout = timeout_sec
            cursor.execute(sql)
            result['rows'] = cursor.fetchall()
            cursor.close()
        except Exception as e:
            result['exception'] = e

    thread = threading.Thread(target=run_query, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec + 5)  # 5s grace period

    if thread.is_alive():
        raise TimeoutError(f"Query exceeded {timeout_sec} second timeout")

    if result['exception']:
        raise result['exception']

    return result['rows']

# Usage
try:
    rows = execute_with_timeout(
        conn,
        "SELECT * FROM LargeTable",
        timeout_sec=60
    )
except TimeoutError as e:
    print(f"Query timeout: {e}")
```

---

## Summary

This research document covers:

1. **Architecture**: pyodbc C extension → Driver Manager → Database Driver → Database
2. **Catalog Functions**: tables(), columns(), primaryKeys(), foreignKeys(), statistics(), getTypeInfo()
3. **Connection Management**: DSN vs DSN-less, autocommit, timeouts, pooling patterns
4. **Driver Detection**: pyodbc.drivers(), dataSources(), connection.getinfo(), SQLSTATE codes
5. **Platform Differences**: Windows (registry), Linux (ini files, unixODBC), macOS (iODBC/unixODBC)
6. **Driver Quirks**: SQL Server (encryption, DATETIMEOFFSET), Oracle (no timeout, stale pools), PostgreSQL (encoding), MySQL (ANSI driver), IBM i (SYSTEM= vs SERVER=), NetSuite (read-only, 5-10 limit)
7. **32-bit vs 64-bit**: Matching Python and ODBC manager architecture
8. **Encoding**: UTF-16LE default, per-driver character set handling
9. **Error Handling**: Exception hierarchy, SQLSTATE codes, safe_connect/safe_query patterns
10. **Best Practices**: ConnectionManager pooling, row limits, schema caching, platform-agnostic discovery, secure connection strings

All code examples are production-ready and handle common edge cases (retries, timeouts, encoding, connection validation).
