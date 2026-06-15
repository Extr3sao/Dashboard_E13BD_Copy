import os
from pathlib import Path
import ctypes

import oracledb


DEFAULT_ORACLE_CLIENT_LIB_DIR = "./instantclient"


def _is_ascii_path(path):
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _windows_short_path(path):
    if os.name != "nt":
        return None

    buffer = ctypes.create_unicode_buffer(1024)
    result = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    if result == 0 or result >= len(buffer):
        return None

    short_path = buffer.value
    if not short_path or not _is_ascii_path(short_path):
        return None
    return short_path


def _oracle_client_init_path(client_path):
    resolved_path = client_path.resolve()
    if _is_ascii_path(resolved_path):
        return str(resolved_path)
    short_path = _windows_short_path(resolved_path)
    if short_path:
        return short_path
    return str(resolved_path)


def resolve_oracle_client_lib_dir(config=None):
    config = config or {}
    return (
        config.get("ORACLE_CLIENT_LIB_DIR")
        or os.getenv("ORACLE_CLIENT_LIB_DIR")
        or os.getenv("OCI_LIB_DIR")
        or DEFAULT_ORACLE_CLIENT_LIB_DIR
    )


def ensure_oracle_thick_mode(config=None):
    """Initialize python-oracledb Thick mode before any Oracle connection."""
    if not oracledb.is_thin_mode():
        return None

    lib_dir = resolve_oracle_client_lib_dir(config)
    if not lib_dir:
        raise RuntimeError(
            "Oracle Thick Mode es obligatori. Configura ORACLE_CLIENT_LIB_DIR amb la ruta de l'Oracle Instant Client."
        )

    client_path = Path(lib_dir).expanduser()
    if not client_path.exists():
        raise RuntimeError(
            "Oracle Thick Mode es obligatori, pero no s'ha trobat l'Oracle Instant Client a "
            f"'{client_path}'. Configura ORACLE_CLIENT_LIB_DIR correctament."
        )

    init_path = _oracle_client_init_path(client_path)

    try:
        oracledb.init_oracle_client(lib_dir=init_path)
    except Exception as exc:
        raise RuntimeError(
            "No s'ha pogut inicialitzar Oracle Thick Mode amb l'Oracle Instant Client a "
            f"'{client_path}'. Revisa que la ruta contingui les llibreries OCI correctes. Detall: {exc}"
        ) from exc

    if oracledb.is_thin_mode():
        raise RuntimeError(
            "Oracle Thick Mode es obligatori, pero python-oracledb continua en Thin mode despres d'inicialitzar "
            f"l'Instant Client a '{client_path}'."
        )

    return init_path
