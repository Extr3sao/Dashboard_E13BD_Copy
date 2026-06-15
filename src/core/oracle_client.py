import os
from pathlib import Path

import oracledb


DEFAULT_ORACLE_CLIENT_LIB_DIR = "./instantclient"


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

    try:
        oracledb.init_oracle_client(lib_dir=str(client_path.resolve()))
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

    return str(client_path.resolve())
