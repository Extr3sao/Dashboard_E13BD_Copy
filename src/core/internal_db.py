import sqlite3
import os
import re
from pathlib import Path
from typing import Iterable, Optional, List, Dict, Any, Tuple

from src.core.sqlite_paths import resolve_sqlite_path
from src.core.ownership_resolver import detect_ownership_table

class InternalDBManager:
    def __init__(self, db_path=None):
        self.db_path = db_path or resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
        self._memory_fallback_conn = None
        self._ensure_dir()
        try:
            self._init_db()
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "disk i/o error" not in message:
                raise
            fallback_filename = Path(str(self.db_path)).name or "internal.db"
            fallback_disk_path = resolve_sqlite_path("INTERNAL_DB_PATH", fallback_filename)
            if fallback_disk_path != self.db_path:
                self.db_path = fallback_disk_path
                self._ensure_dir()
                self._init_db()
                return
            memory_name = re.sub(r"[^a-zA-Z0-9_]+", "_", Path(str(self.db_path)).stem or "internal")
            self.db_path = f"file:oracle_audit_{memory_name}?mode=memory&cache=shared"
            self._memory_fallback_conn = sqlite3.connect(self.db_path, uri=True, check_same_thread=False)
            self._init_db()

    def _ensure_dir(self):
        # If db_path is just a filename, dirname can be empty.
        d = os.path.dirname(self.db_path)
        if d:
            Path(d).mkdir(parents=True, exist_ok=True)

    def _build_fallback_path(self):
        path = Path(self.db_path)
        if path.suffix:
            return str(path.with_name(f"{path.stem}_fallback{path.suffix}"))
        return str(path.with_name(f"{path.name}_fallback.db"))

    def _get_connection(self):
        if str(self.db_path).startswith("file:"):
            conn = sqlite3.connect(self.db_path, uri=True, check_same_thread=False)
        else:
            conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # ── Taules existents ───────────────────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sql_text TEXT NOT NULL,
                    explanation TEXT,
                    source TEXT DEFAULT 'MANUAL',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id INTEGER,
                    name TEXT NOT NULL,
                    FOREIGN KEY (query_id) REFERENCES queries (id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meta_objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schema_name TEXT,
                    object_name TEXT,
                    object_type TEXT,
                    description TEXT,
                    is_obsolete INTEGER DEFAULT 0,
                    reason TEXT,
                    risk_level TEXT,
                    recommendation TEXT,
                    source TEXT DEFAULT 'DETECTED'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id INTEGER,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    result_summary TEXT,
                    FOREIGN KEY (query_id) REFERENCES queries (id)
                )
            """)

            # ── Mòdul de Gestió de Consultes (NOU) ────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_checks (
                    check_id         TEXT PRIMARY KEY,
                    titol            TEXT NOT NULL,
                    severitat_base   TEXT NOT NULL,
                    parametres       TEXT,
                    tipus            TEXT NOT NULL DEFAULT 'SQL',
                    ordre            INTEGER NOT NULL DEFAULT 0,
                    actiu            INTEGER NOT NULL DEFAULT 1,
                    context_check    TEXT,
                    creat_en         TEXT NOT NULL DEFAULT (datetime('now')),
                    actualitzat_en   TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS consulta_versions (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id         TEXT NOT NULL REFERENCES audit_checks(check_id),
                    versio           INTEGER NOT NULL,
                    sql_text         TEXT NOT NULL,
                    checksum         TEXT NOT NULL,
                    creat_per        TEXT NOT NULL DEFAULT 'sistema',
                    creat_en         TEXT NOT NULL DEFAULT (datetime('now')),
                    es_vigent        INTEGER NOT NULL DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS explicacions (
                    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id                  TEXT NOT NULL REFERENCES audit_checks(check_id),
                    consulta_version_id       INTEGER REFERENCES consulta_versions(id),
                    resum_executiu            TEXT,
                    explicacio_funcional      TEXT,
                    explicacio_tecnica        TEXT,
                    impacte                   TEXT,
                    riscos                    TEXT,
                    canvis_respecte_anterior  TEXT,
                    recomanacio_revisio       TEXT,
                    nivell_confianca          REAL,
                    advertiments              TEXT,
                    model_utilitzat           TEXT,
                    estat                     TEXT NOT NULL DEFAULT 'PENDENT',
                    error_missatge            TEXT,
                    creat_en                  TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS regeneracio_log (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id            TEXT NOT NULL,
                    consulta_version_id INTEGER,
                    model_intentat      TEXT NOT NULL,
                    model_ordre         INTEGER NOT NULL DEFAULT 0,
                    resultat            TEXT NOT NULL,
                    tokens_entrada      INTEGER,
                    tokens_sortida      INTEGER,
                    latencia_ms         INTEGER,
                    error_codi          TEXT,
                    intentat_en         TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sincronitzacio_fitxers (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id        TEXT NOT NULL,
                    fitxer          TEXT NOT NULL,
                    estat           TEXT NOT NULL DEFAULT 'PENDENT',
                    darrera_sync    TEXT,
                    error_missatge  TEXT,
                    UNIQUE(check_id, fitxer)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_lots (
                    schema_name TEXT PRIMARY KEY,
                    lot_name    TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS model_config (
                    ordre                   INTEGER PRIMARY KEY,
                    model_id                TEXT NOT NULL UNIQUE,
                    nom_display             TEXT NOT NULL,
                    proveidor               TEXT NOT NULL,
                    actiu                   INTEGER NOT NULL DEFAULT 1,
                    fallbacks_consecutius   INTEGER NOT NULL DEFAULT 0,
                    excloses_fins           TEXT
                )
            """)

            # Poblar model_config amb la llista prioritzada si és buida
            cursor.execute("SELECT COUNT(*) FROM model_config")
            if cursor.fetchone()[0] == 0:
                models_prioritzats = [
                    (1,  "openai/gpt-oss-120b:free",                         "gpt-oss-120b",                 "OpenAI"),
                    (2,  "google/gemma-4-31b-it:free",                       "Gemma 4 31B",                  "Google"),
                    (3,  "google/gemma-4-26b-a4b-it:free",                   "Gemma 4 26B A4B",              "Google"),
                    (4,  "nvidia/nemotron-3-super-120b-a12b:free",           "Nemotron 3 Super 120B",        "NVIDIA"),
                    (5,  "nvidia/nemotron-3-nano-30b-a3b:free",              "Nemotron 3 Nano 30B A3B",      "NVIDIA"),
                    (6,  "nvidia/nemotron-nano-9b-v2:free",                  "Nemotron Nano 9B V2",          "NVIDIA"),
                    (7,  "google/gemma-3-27b-it:free",                       "Gemma 3 27B",                  "Google"),
                    (8,  "google/gemma-3-12b-it:free",                       "Gemma 3 12B",                  "Google"),
                    (9,  "google/gemma-3-4b-it:free",                        "Gemma 3 4B",                   "Google"),
                    (10, "minimax/minimax-m2.5:free",                        "MiniMax M2.5",                 "MiniMax"),
                    (11, "arcee-ai/trinity-large-preview:free",              "Trinity Large Preview",        "Arcee AI"),
                    (12, "arcee-ai/trinity-mini:free",                       "Trinity Mini",                 "Arcee AI"),
                    (13, "liquid/lfm-2.5-1.2b-thinking:free",                "LFM 2.5 1.2B Thinking",        "LiquidAI"),
                    (14, "liquid/lfm-2.5-1.2b-instruct:free",                "LFM 2.5 1.2B Instruct",        "LiquidAI"),
                    (15, "openrouter/free",                                  "Free Models Router",           "OpenRouter"),
                ]
                cursor.executemany(
                    "INSERT OR IGNORE INTO model_config (ordre, model_id, nom_display, proveidor) VALUES (?,?,?,?)",
                    models_prioritzats,
                )

            conn.commit()

    @staticmethod
    def _normalize_meta_object_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(fields)
        for key in ("schema_name", "object_type", "risk_level", "source"):
            if key in normalized and normalized[key] is not None:
                normalized[key] = str(normalized[key]).strip().upper()
        if "object_name" in normalized and normalized["object_name"] is not None:
            normalized["object_name"] = str(normalized["object_name"]).strip()
        if "reason" in normalized and normalized["reason"] is not None:
            normalized["reason"] = str(normalized["reason"]).strip()
        if "recommendation" in normalized and normalized["recommendation"] is not None:
            normalized["recommendation"] = str(normalized["recommendation"]).strip()
        if "description" in normalized and normalized["description"] is not None:
            normalized["description"] = str(normalized["description"]).strip()
        if "is_obsolete" in normalized and normalized["is_obsolete"] is not None:
            normalized["is_obsolete"] = int(1 if normalized["is_obsolete"] else 0)
        return normalized

    def add_query(self, sql_text, explanation=None, source="MANUAL", tags: Optional[Iterable[str]] = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO queries (sql_text, explanation, source) VALUES (?, ?, ?)",
                (sql_text, explanation, source)
            )
            query_id = cursor.lastrowid
            for tag in (tags or []):
                cursor.execute("INSERT INTO tags (query_id, name) VALUES (?, ?)", (query_id, str(tag)))
            conn.commit()
            return query_id

    def get_queries(self, tag=None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if tag:
                cursor.execute("""
                    SELECT q.* FROM queries q
                    JOIN tags t ON q.id = t.query_id
                    WHERE t.name = ?
                """, (tag,))
            else:
                cursor.execute("SELECT * FROM queries ORDER BY created_at DESC")
            return cursor.fetchall()

    def register_obsolete(self, schema, name, obj_type, reason, risk, rec="", source="DETECTED"):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO meta_objects 
                (schema_name, object_name, object_type, reason, risk_level, recommendation, is_obsolete, source)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """, (schema, name, obj_type, reason, risk, rec, source))
            conn.commit()

    def get_obsolet_registry(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM meta_objects WHERE is_obsolete = 1")
            return cursor.fetchall()

    # --- Meta Objects (Obsolets) API helpers ---
    def list_meta_objects(
        self,
        only_obsolete: Optional[bool] = True,
        schema_name: Optional[str] = None,
        risk_level: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Tuple[List[Tuple[Any, ...]], List[str]]:
        """
        Returns (rows, columns) from meta_objects with optional filters.
        """
        limit = max(1, min(int(limit or 200), 1000))
        offset = max(0, int(offset or 0))

        where = []
        params: List[Any] = []

        if only_obsolete is True:
            where.append("is_obsolete = 1")
        elif only_obsolete is False:
            where.append("is_obsolete = 0")

        if schema_name:
            where.append("schema_name = ?")
            params.append(str(schema_name).strip().upper())
        if risk_level:
            where.append("risk_level = ?")
            params.append(str(risk_level).strip().upper())
        if source:
            where.append("source = ?")
            params.append(str(source).strip().upper())

        sql = "SELECT id, schema_name, object_name, object_type, description, is_obsolete, reason, risk_level, recommendation, source FROM meta_objects"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

        cols = [
            "id",
            "schema_name",
            "object_name",
            "object_type",
            "description",
            "is_obsolete",
            "reason",
            "risk_level",
            "recommendation",
            "source",
        ]
        return rows, cols

    def add_meta_object(
        self,
        schema_name: str,
        object_name: str,
        object_type: str,
        reason: str,
        risk_level: str,
        recommendation: str = "",
        description: str = "",
        is_obsolete: int = 1,
        source: str = "USER",
    ) -> int:
        normalized = self._normalize_meta_object_fields(
            {
                "schema_name": schema_name,
                "object_name": object_name,
                "object_type": object_type,
                "description": description,
                "reason": reason,
                "risk_level": risk_level,
                "recommendation": recommendation,
                "source": source,
            }
        )
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO meta_objects
                (schema_name, object_name, object_type, description, is_obsolete, reason, risk_level, recommendation, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["schema_name"],
                    normalized["object_name"],
                    normalized["object_type"],
                    normalized["description"],
                    int(1 if is_obsolete else 0),
                    normalized["reason"],
                    normalized["risk_level"],
                    normalized["recommendation"],
                    normalized["source"],
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def update_meta_object(self, obj_id: int, **fields: Any) -> bool:
        allowed = {
            "schema_name",
            "object_name",
            "object_type",
            "description",
            "is_obsolete",
            "reason",
            "risk_level",
            "recommendation",
            "source",
        }
        updates = []
        params: List[Any] = []
        normalized_fields = self._normalize_meta_object_fields(fields)
        for k, v in normalized_fields.items():
            if k not in allowed:
                continue
            updates.append(f"{k} = ?")
            params.append(v)

        if not updates:
            return False

        params.append(int(obj_id))
        sql = "UPDATE meta_objects SET " + ", ".join(updates) + " WHERE id = ?"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0

    def list_schema_lots(self) -> List[Dict[str, str]]:
        table_info = detect_ownership_table(self.db_path)
        if not table_info:
            return []

        query = f"""
            SELECT {table_info['schema_column']} AS schema_name, {table_info['lot_column']} AS lot_name
            FROM {table_info['table']}
            ORDER BY UPPER({table_info['schema_column']}) ASC
        """
        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            items = []
            for row in rows:
                schema_name = str(row[0] or "").strip().upper()
                lot_name = str(row[1] or "").strip().upper()
                if not schema_name:
                    continue
                items.append({"schema_name": schema_name, "lot_name": lot_name})
            return items

    def upsert_schema_lots(self, items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        normalized: List[Tuple[str, str]] = []
        seen: set[str] = set()
        for item in items or []:
            schema_name = str(item.get("schema_name") or "").strip().upper()
            lot_name = str(item.get("lot_name") or "").strip().upper()
            if not schema_name:
                continue
            if schema_name in seen:
                continue
            normalized.append((schema_name, lot_name or "SENSE LOT"))
            seen.add(schema_name)

        table_info = detect_ownership_table(self.db_path)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if not table_info:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_lots (
                        schema_name TEXT PRIMARY KEY,
                        lot_name TEXT NOT NULL
                    )
                    """
                )
                table_info = {
                    "table": "schema_lots",
                    "schema_column": "schema_name",
                    "lot_column": "lot_name",
                }

            table_name = table_info["table"]
            schema_column = table_info["schema_column"]
            lot_column = table_info["lot_column"]

            if table_name.lower() == "schema_lots" and schema_column == "schema_name" and lot_column == "lot_name":
                cursor.execute("DELETE FROM schema_lots")
                if normalized:
                    cursor.executemany(
                        "INSERT INTO schema_lots (schema_name, lot_name) VALUES (?, ?)",
                        normalized,
                    )
            else:
                cursor.execute(f"DELETE FROM {table_name}")
                if normalized:
                    cursor.executemany(
                        f"INSERT INTO {table_name} ({schema_column}, {lot_column}) VALUES (?, ?)",
                        normalized,
                    )
            conn.commit()
        return self.list_schema_lots()
