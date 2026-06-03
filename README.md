# mcp-odbc

Servidor MCP en Python que conecta a **cualquier base de datos con driver ODBC** y expone herramientas de descubrimiento de esquema, consultas SQL y ejecucion de stored procedures. Construido sobre FastMCP v2, disenado para Claude Code y Claude Desktop.

```
Claude  -->  mcp-odbc  -->  Driver ODBC  -->  Tu base de datos
             (este)         (cualquiera)       Sybase ASE, SQL Server,
                                               PostgreSQL, MySQL, Oracle,
                                               NetSuite, SAP, ...
```

Si tu base de datos tiene un driver ODBC, este servidor puede hablarle.

---

## Que es y para que sirve

`mcp-odbc` actua como puente entre Claude y cualquier base de datos relacional. Una vez configurado, Claude puede:

- **Explorar el esquema** sin que vos le expliques nada: listar tablas, describir columnas, ver claves primarias y foraneas.
- **Ejecutar consultas SQL** de solo lectura y recibir los resultados formateados como tabla Markdown o JSON.
- **Ejecutar stored procedures** habilitados por configuracion (con whitelist de nombres).
- **Trabajar con multiples bases** simultaneamente: produccion, QA, staging, cada una con sus propios permisos.

El servidor corre localmente en tu maquina. Claude nunca accede directamente a la base de datos — todo pasa por este servidor que aplica las reglas de seguridad.

---

## Mejoras de seguridad implementadas

Este fork agrega cinco capas de seguridad sobre la version original:

### 1. Vault de credenciales con Windows DPAPI
Las contrasenas en `config.ini` se almacenan cifradas con la API de proteccion de datos de Windows (DPAPI). El cifrado esta atado al usuario de Windows que lo configuro — nadie mas puede descifrar el blob aunque tenga el archivo.

```ini
# Antes (texto plano — no recomendado)
connection_string = DSN=MiBaseDeDatos;UID=lector;PWD=mi_password

# Despues (cifrado con DPAPI)
connection_string = DSN=MiBaseDeDatos;UID=lector;PWD=dpapi:AQAAANCMnd8BFdERjH...
```

Para cifrar las contrasenas existentes:
```bash
python scripts/setup_vault.py --config config/config.ini
```

### 2. Sanitizacion extendida de errores
Antes de que cualquier mensaje de error llegue al LLM, se eliminan automaticamente:
- Valores de `PWD`, `PASSWORD`, `UID`, `USER`
- Nombres de servidor (`SERVER`, `SERVERNAME`)
- Nombres de base de datos (`DATABASE`, `DB`)
- Stack traces completos de Python
- Rutas internas del driver manager de ODBC

El LLM nunca ve informacion sensible de infraestructura.

### 3. Audit log rotativo
Cada consulta ejecutada queda registrada en `logs/mcp_odbc_audit.log` en formato JSON:

```json
{"ts": "2026-06-02T14:30:00Z", "connection": "soc1", "query_hash": "a3f1b2c4d5e6f7a8", "rows": 42, "duration_ms": 187.3, "truncated": false, "error": null}
```

El log rota automaticamente (10 MB por archivo, 5 backups). Solo se guarda el hash SHA-256 de la query, nunca el SQL en texto plano. Configurable con variables de entorno:

| Variable | Default | Descripcion |
|---|---|---|
| `ODBC_AUDIT_LOG` | `logs/mcp_odbc_audit.log` | Ruta del archivo de log |
| `ODBC_AUDIT_MAX_MB` | `10` | Tamano maximo por archivo |
| `ODBC_AUDIT_BACKUPS` | `5` | Cantidad de backups a conservar |
| `ODBC_AUDIT_DISABLE` | | Poner `1` para desactivar |

### 4. Adaptador nativo para Sybase ASE 16
El driver ODBC de Adaptive Server no implementa correctamente las funciones de catalogo estandar. El `SybaseAdapter` consulta directamente las tablas del sistema:

| Tabla del sistema | Para que se usa |
|---|---|
| `sysobjects` | Listar tablas, vistas y procedimientos |
| `syscolumns` + `systypes` | Tipos y definiciones de columnas |
| `sysindexes` | Inferir claves primarias |
| `sysreferences` | Relaciones de claves foraneas |

Se activa automaticamente cuando el servidor detecta `"Adaptive Server"` en `SQL_DBMS_NAME`.

### 5. Ejecucion de stored procedures con whitelist
Por defecto los SPs estan deshabilitados. Se habilitan por conexion con dos controles:

```ini
[produccion]
connection_string = ...
allow_sp = true
sp_whitelist = sp_get_balance, sp_get_movements, sp_get_statement
```

- Si `sp_whitelist` esta vacio: cualquier SP del sistema es ejecutable.
- Si `sp_whitelist` tiene valores: solo esos SPs son aceptados.
- El nombre del SP se valida con regex estricto (`[\w@#]+`) para prevenir inyeccion.

---

## Instalacion

### Requisitos
- Python **32-bit** si tu driver ODBC es de 32 bits (verificar con `pyodbc.drivers()`)
- Driver ODBC instalado para tu base de datos

```bash
# Verificar bitness del Python que vas a usar
python -c "import struct; print(struct.calcsize('P')*8, 'bits')"

# Instalar
pip install -e .

# Con soporte para cifrado de credenciales (Windows)
pip install -e ".[vault]"
```

### Configuracion en Claude Desktop

Editar `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-odbc": {
      "command": "C:\\ruta\\al\\venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_odbc"],
      "env": {
        "ODBC_MCP_CONFIG": "C:\\ruta\\config\\config.ini"
      }
    }
  }
}
```

---

## Configuracion

### Opcion A: Variables de entorno (conexion unica)

```bash
ODBC_DSN=MiBaseDeDatos
ODBC_UID=usuario_lectura
ODBC_PWD=contrasena
ODBC_READ_ONLY=true
ODBC_MAX_ROWS=5000
```

`ODBC_PWD` acepta tanto texto plano como tokens `dpapi:...`.

### Opcion B: Archivo INI (multiples conexiones)

```ini
[server]
default_connection = produccion
max_rows = 5000
cache_ttl = 300

[produccion]
connection_string = DRIVER={Mi Driver ODBC};SERVER=prod-host;PORT=5000;DATABASE=mi_bd;UID=lector;PWD=dpapi:AQAAANCMnd8...
readonly         = true
query_timeout    = 60
connect_timeout  = 15
allow_sp         = true
sp_whitelist     = sp_get_balance, sp_get_movements

[qa]
connection_string = DRIVER={Mi Driver ODBC};SERVER=qa-host;PORT=5000;DATABASE=mi_bd;UID=qa_user;PWD=dpapi:AQAAANCMnd8...
readonly         = false
query_timeout    = 30
allow_sp         = true
```

Apuntar el servidor al archivo:
```json
"env": { "ODBC_MCP_CONFIG": "C:\\ruta\\config\\config.ini" }
```

### Cifrar las contrasenas existentes

Una vez que tenes el archivo INI con contrasenas en texto plano:

```bash
# Ver que cambiaria sin modificar nada
python scripts/setup_vault.py --dry-run

# Cifrar
python scripts/setup_vault.py

# Solo una conexion especifica
python scripts/setup_vault.py --section produccion
```

El script es idempotente: las contrasenas ya cifradas (`dpapi:...`) se saltean.

---

## Herramientas disponibles

Todas aceptan el parametro opcional `connection` para elegir la conexion.

| Herramienta | Descripcion |
|---|---|
| `list_dsns` | Lista los DSN ODBC configurados en el sistema |
| `list_connections` | Muestra las conexiones configuradas y su estado |
| `test_connection` | Verifica la conectividad e informa el tipo de DBMS |
| `list_tables` | Descubre tablas y vistas con filtros por esquema, tipo y nombre |
| `describe_table` | Muestra columnas, tipos, PKs y FKs de una tabla |
| `execute_query` | Ejecuta una consulta SELECT con limite de filas y salida Markdown o JSON |
| `get_primary_keys` | Obtiene las columnas de clave primaria de una tabla |
| `get_foreign_keys` | Obtiene las relaciones de clave foranea de una tabla |
| `execute_sp` | Ejecuta un stored procedure habilitado en la whitelist |

### Ejemplo de uso

```
Usuario: Que tablas tienen informacion de clientes?

Claude: [llama list_tables con name_pattern="%client%"]

| table_name       | table_owner | table_type |
| clients          | dbo         | TABLE      |
| client_accounts  | dbo         | TABLE      |
| client_history   | dbo         | TABLE      |

Usuario: Describe client_accounts

Claude: [llama describe_table con table="client_accounts", include="all"]

### Columnas — client_accounts
| column_name     | type_name | max_length | is_nullable |
| account_id      | int       | 4          | NO          |
| client_id       | int       | 4          | NO          |
| balance         | money     | 8          | YES         |
| open_date       | datetime  | 8          | YES         |

### Claves primarias
| column_name | pk_name              |
| account_id  | pk_client_accounts   |

Usuario: Ejecuta el SP de saldos para la cuenta 10045

Claude: [llama execute_sp con sp_name="sp_get_balance", params=["10045"]]
```

---

## Seguridad — resumen de las 3 capas de solo lectura

Cuando `readonly = true` (por defecto), las escrituras se bloquean en tres niveles independientes:

1. **Driver ODBC** — La conexion se abre con `readonly=True`, el driver rechaza escrituras a nivel de protocolo.
2. **Validacion SQL** — Se eliminan comentarios del SQL y se rechaza cualquier sentencia que no comience con `SELECT` o `WITH`, o que contenga palabras clave de escritura (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `EXEC`, etc.).
3. **Flag de configuracion** — El campo `readonly` por conexion en el INI (por defecto `true`). Poner `readonly = false` para habilitar escrituras en esa conexion especifica.

---

## Arquitectura

```
src/mcp_odbc/
  server.py           # Servidor FastMCP, 9 herramientas, punto de entrada
  config.py           # Modelos Pydantic, carga de env vars e INI, allow_sp
  connection.py       # ConnectionManager (conexion lazy, health check, cache)
  query.py            # Ejecucion SQL, validacion readonly, audit log, run_sp
  metadata.py         # Descubrimiento de esquema (delega al adaptador)
  detection.py        # Deteccion de DBMS via SQL_DBMS_NAME
  formatting.py       # Tablas Markdown, JSON, truncado de valores
  errors.py           # Mapeo de SQLSTATE, sanitizacion extendida de errores
  audit.py            # Log rotativo JSON de todas las ejecuciones
  vault.py            # Cifrado/descifrado DPAPI de credenciales
  adapters/
    base.py           # ABC SystemAdapter
    generic.py        # GenericODBCAdapter (funciona con cualquier driver)
    sybase.py         # SybaseAdapter para Sybase ASE 16
scripts/
  setup_vault.py      # CLI para cifrar contrasenas en config.ini
```

---

## Tests

```bash
pip install -e ".[dev]"
pytest tests/

# Los tests del vault corren sin pywin32 real (mock de win32crypt)
# No se necesita base de datos para correr ninguno de los tests
```

---

## Notas de plataforma

| Plataforma | Driver Manager | Notas |
|---|---|---|
| Windows | odbc32.dll (incluido) | DSNs en el Administrador de origenes de datos ODBC |
| Linux | unixODBC | `apt install unixodbc-dev` |
| macOS | unixODBC via Homebrew | `brew install unixodbc` (NO usar iODBC) |

**Importante:** Python de 32 bits solo puede cargar drivers ODBC de 32 bits, y viceversa. Usar `pyodbc.drivers()` para verificar que el driver aparece en la lista.

---

## Licencia

MIT
