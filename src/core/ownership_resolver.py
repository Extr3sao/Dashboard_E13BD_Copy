import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


TABLE_CANDIDATES = ("esquema_lot", "schema_lots")
SCHEMA_COLUMN_CANDIDATES = ("schema_name", "esquema", "schema", "owner")
LOT_COLUMN_CANDIDATES = ("lot_name", "lot", "lote")
RESPONSABLE_COLUMN_CANDIDATES = ("responsable", "owner_name", "team_name", "equip", "team")


def default_ownership_assignment(schema: str, object_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema": str(schema or "").strip().upper() or None,
        "object_name": str(object_name or "").strip() or None,
        "lot": "SENSE LOT",
        "responsable": "No assignat",
        "source": "fallback",
        "confidence": "default",
    }


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    row = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND lower(name) = lower(?)",
        (table_name,),
    ).fetchone()
    return bool(row)


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> List[str]:
    rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in rows]


def _pick_column(columns: List[str], candidates: tuple[str, ...]) -> Optional[str]:
    lowered = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def detect_ownership_table(db_path: str) -> Optional[Dict[str, Any]]:
    path = Path(db_path)
    if not path.exists():
        return None

    with sqlite3.connect(str(path)) as connection:
        cursor = connection.cursor()
        for table_name in TABLE_CANDIDATES:
            if not _table_exists(cursor, table_name):
                continue
            columns = _table_columns(cursor, table_name)
            schema_column = _pick_column(columns, SCHEMA_COLUMN_CANDIDATES)
            lot_column = _pick_column(columns, LOT_COLUMN_CANDIDATES)
            responsable_column = _pick_column(columns, RESPONSABLE_COLUMN_CANDIDATES)
            if schema_column and lot_column:
                return {
                    "table": table_name,
                    "schema_column": schema_column,
                    "lot_column": lot_column,
                    "responsable_column": responsable_column,
                }
    return None


def load_ownership_mapping(db_path: str) -> Dict[str, Dict[str, Any]]:
    table_info = detect_ownership_table(db_path)
    if not table_info:
        return {}

    query = (
        f"SELECT {table_info['schema_column']}, {table_info['lot_column']}"
        + (
            f", {table_info['responsable_column']}"
            if table_info.get("responsable_column")
            else ", NULL"
        )
        + f" FROM {table_info['table']}"
    )

    mapping: Dict[str, Dict[str, Any]] = {}
    with sqlite3.connect(db_path) as connection:
        for schema_name, lot_name, responsable in connection.execute(query).fetchall():
            normalized_schema = str(schema_name or "").strip().upper()
            if not normalized_schema:
                continue
            mapping[normalized_schema] = {
                "schema": normalized_schema,
                "lot": str(lot_name or "").strip() or "SENSE LOT",
                "responsable": str(responsable or "").strip() or "No informat",
                "source": table_info["table"],
                "confidence": "exact",
            }
    return mapping


def resolve_ownership(
    schema: str,
    object_name: Optional[str] = None,
    *,
    mapping: Optional[Dict[str, Dict[str, Any]]] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_schema = str(schema or "").strip().upper()
    if not normalized_schema:
        return default_ownership_assignment(schema, object_name)

    current_mapping = mapping if mapping is not None else (load_ownership_mapping(db_path) if db_path else {})
    current = current_mapping.get(normalized_schema)
    if not current:
        return default_ownership_assignment(normalized_schema, object_name)

    return {
        **current,
        "schema": normalized_schema,
        "object_name": str(object_name or "").strip() or None,
    }
