"""Bloqueo por intentos fallidos de autenticacion (SQLSTATE 28000).

Cada vez que una conexion falla con error de autenticacion, se incrementa
un contador persistente en un archivo JSON.  Si el contador alcanza el
maximo configurado, la conexion queda bloqueada y se lanza un ToolError
con un mensaje claro -- sin volver a intentar el logon.

El archivo persiste entre reinicios del servidor, de modo que los intentos
no se pierden aunque el proceso se cierre y vuelva a abrir.

Estructura del archivo JSON
---------------------------
{
    "soc1": {
        "attempts": 2,
        "locked": true,
        "last_failure": "2026-06-02T14:30:00+00:00",
        "last_reset": null
    },
    "soc2": {
        "attempts": 0,
        "locked": false,
        "last_failure": null,
        "last_reset": "2026-06-02T10:00:00+00:00"
    }
}

Configuracion
-------------
ODBC_LOCKOUT_FILE   Ruta al archivo JSON (default: config/auth_lockout.json)
ODBC_MAX_AUTH_FAILURES  Maximo de intentos fallidos global (default: 2)
                    Puede sobreescribirse por conexion con max_auth_failures
                    en el INI.

API publica
-----------
check(connection_name, max_failures)
    Llama antes de intentar conectar.  Lanza ToolError si la conexion esta
    bloqueada.

record_failure(connection_name, max_failures)
    Llama cuando pyodbc lanza SQLSTATE 28000.  Incrementa el contador y
    bloquea si se alcanzo el maximo.

reset(connection_name)
    Llama despues de una conexion exitosa.  Resetea el contador a 0.

reset_manual(connection_name)
    Llama desde el tool reset_lockout del servidor para desbloquear
    manualmente sin necesidad de reiniciar.

status(connection_name)
    Devuelve el estado actual (attempts, locked, last_failure).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastmcp.exceptions import ToolError

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

_DEFAULT_FILE = "config/auth_lockout.json"
_DEFAULT_MAX  = 2

_LOCKOUT_FILE = Path(os.environ.get("ODBC_LOCKOUT_FILE", _DEFAULT_FILE))
_GLOBAL_MAX   = int(os.environ.get("ODBC_MAX_AUTH_FAILURES", str(_DEFAULT_MAX)))

# Lock para acceso thread-safe al archivo
_file_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers de I/O
# ---------------------------------------------------------------------------

def _load() -> dict:
    """Leer el archivo JSON; devuelve dict vacio si no existe o esta danado."""
    if not _LOCKOUT_FILE.exists():
        return {}
    try:
        with _LOCKOUT_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save(data: dict) -> None:
    """Escribir el archivo JSON de forma atomica."""
    _LOCKOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _LOCKOUT_FILE.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        tmp.replace(_LOCKOUT_FILE)
    except Exception:
        tmp.unlink(missing_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entry(data: dict, conn: str) -> dict:
    """Devuelve (y crea si no existe) la entrada para una conexion."""
    if conn not in data:
        data[conn] = {
            "attempts": 0,
            "locked": False,
            "last_failure": None,
            "last_reset": None,
        }
    return data[conn]


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def check(connection_name: str, max_failures: int = _GLOBAL_MAX) -> None:
    """Verificar si la conexion esta bloqueada.

    Debe llamarse ANTES de intentar abrir la conexion.

    Raises
    ------
    ToolError
        Si la conexion esta bloqueada por demasiados intentos fallidos.
    """
    with _file_lock:
        data = _load()
        entry = data.get(connection_name, {})

    if entry.get("locked", False):
        last = entry.get("last_failure", "desconocido")
        raise ToolError(
            f"La conexion '{connection_name}' esta BLOQUEADA por "
            f"{entry.get('attempts', max_failures)} intentos fallidos de "
            f"autenticacion consecutivos (ultimo: {last}). "
            "Verificar las credenciales y usar reset_lockout para desbloquear."
        )


def record_failure(connection_name: str, max_failures: int = _GLOBAL_MAX) -> None:
    """Registrar un intento fallido de autenticacion (SQLSTATE 28000).

    Si se alcanza el maximo, bloquea la conexion y lanza ToolError.

    Raises
    ------
    ToolError
        Si este intento es el que alcanza el limite.
    """
    with _file_lock:
        data = _load()
        entry = _entry(data, connection_name)
        entry["attempts"] += 1
        entry["last_failure"] = _now_iso()

        if entry["attempts"] >= max_failures:
            entry["locked"] = True
            _save(data)
            raise ToolError(
                f"AUTENTICACION BLOQUEADA para '{connection_name}': "
                f"{entry['attempts']} intentos fallidos consecutivos. "
                "La conexion no se volvera a intentar hasta que se "
                "corrijan las credenciales y se ejecute reset_lockout."
            )

        _save(data)


def reset(connection_name: str) -> None:
    """Resetear el contador tras una conexion exitosa."""
    with _file_lock:
        data = _load()
        if connection_name in data:
            data[connection_name]["attempts"] = 0
            data[connection_name]["locked"] = False
            data[connection_name]["last_reset"] = _now_iso()
            _save(data)


def reset_manual(connection_name: str) -> dict:
    """Desbloquear manualmente una conexion (llamado desde reset_lockout tool).

    Returns
    -------
    dict
        Estado previo antes del reset.
    """
    with _file_lock:
        data = _load()
        prev = dict(data.get(connection_name, {}))
        entry = _entry(data, connection_name)
        entry["attempts"] = 0
        entry["locked"] = False
        entry["last_reset"] = _now_iso()
        _save(data)
    return prev


def status(connection_name: str) -> dict:
    """Devolver el estado actual de bloqueo de una conexion."""
    with _file_lock:
        data = _load()
    return data.get(connection_name, {
        "attempts": 0,
        "locked": False,
        "last_failure": None,
        "last_reset": None,
    })


def status_all() -> dict:
    """Devolver el estado de todas las conexiones registradas."""
    with _file_lock:
        return _load()
