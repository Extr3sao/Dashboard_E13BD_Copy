from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from src.api.post_crq_audit import parse_post_crq_checks, resolve_post_crq_markdown_path
from src.core.check_explanation_catalog import load_check_explanation_catalog_from_path
from src.core.sqlite_paths import resolve_sqlite_path
from src.core.time_utils import utc_now_iso


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_txt_path() -> Path:
    return _project_root() / "consultes_post_crq.txt"


def _default_explanation_path() -> Path:
    return _project_root() / "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md"


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _extract_txt_check_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    check_ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*(CHECK_\d+)\s*\|", line, flags=re.IGNORECASE)
        if match:
            check_ids.add(match.group(1).upper())
    return check_ids


def _build_txt_line(check_row: sqlite3.Row) -> str:
    params = str(check_row["parametres"] or "days_back").strip() or "days_back"
    return (
        f"{check_row['check_id']} | {check_row['titol']} | "
        f"severitat base: {check_row['severitat_base']} | paràmetres: {params}"
    )


def _build_explanation_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    review = str(entry.get("com_revisar") or "No informat.").strip()
    fix = str(entry.get("com_corregir") or "No informat.").strip()
    limits = str(entry.get("limitacions") or "No informat.").strip()
    impact = str(entry.get("impacte_sobre_lot") or "No informat.").strip()
    importance = str(entry.get("per_que_es_important") or "No informat.").strip()
    functional = str(entry.get("que_detecta") or "No informat.").strip()
    columns = entry.get("columnes_taula_recomanades") or []
    validation = str(entry.get("validacio_posterior") or "No informat.").strip()
    technical_parts = [
        f"Com revisar: {review}",
        f"Com corregir: {fix}",
        f"Limitacions: {limits}",
        f"Columnes recomanades: {', '.join(columns) if columns else '-'}",
        f"Validació posterior: {validation}",
    ]
    return {
        "resum_executiu": importance[:300] if importance else functional[:300],
        "explicacio_funcional": functional,
        "explicacio_tecnica": "\n\n".join(part for part in technical_parts if part.strip()),
        "impacte": impact,
        "riscos": importance,
        "canvis_respecte_anterior": "Backfill des de documentació existent.",
        "recomanacio_revisio": review,
        "nivell_confianca": 1.0,
        "advertiments": limits,
        "model_utilitzat": "backfill-existing-docs",
        "estat": "VIGENT",
    }


def _upsert_sync_status(conn: sqlite3.Connection, check_id: str, fitxer: str, estat: str, now: str) -> None:
    row = conn.execute(
        "SELECT id FROM sincronitzacio_fitxers WHERE check_id = ? AND fitxer = ? ORDER BY id DESC LIMIT 1",
        (check_id, fitxer),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE sincronitzacio_fitxers SET estat = ?, darrera_sync = ?, error_missatge = NULL WHERE id = ?",
            (estat, now, row[0]),
        )
        return
    conn.execute(
        "INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat, darrera_sync, error_missatge) VALUES (?, ?, ?, ?, NULL)",
        (check_id, fitxer, estat, now),
    )


def _upsert_explanation_row(
    conn: sqlite3.Connection,
    *,
    check_id: str,
    version_id: Optional[int],
    payload: Dict[str, Any],
    now: str,
) -> None:
    columns = _table_columns(conn, "explicacions")
    if "estat" in columns:
        conn.execute(
            "UPDATE explicacions SET estat = 'OBSOLETA' WHERE check_id = ? AND estat = 'VIGENT'",
            (check_id,),
        )

    lookup_sql = "SELECT id FROM explicacions WHERE check_id = ?"
    lookup_params: list[Any] = [check_id]
    if "consulta_version_id" in columns and version_id is not None:
        lookup_sql += " AND consulta_version_id = ?"
        lookup_params.append(version_id)
    lookup_sql += " ORDER BY id DESC LIMIT 1"
    existing = conn.execute(lookup_sql, tuple(lookup_params)).fetchone()

    values: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in columns:
            values[key] = value
    if "check_id" in columns:
        values["check_id"] = check_id
    if "consulta_version_id" in columns and version_id is not None:
        values["consulta_version_id"] = version_id
    if "creat_en" in columns:
        values["creat_en"] = now

    if existing:
        assignments = ", ".join(f"{column} = ?" for column in values)
        conn.execute(
            f"UPDATE explicacions SET {assignments} WHERE id = ?",
            (*values.values(), existing[0]),
        )
        return

    insert_columns = ", ".join(values.keys())
    placeholders = ", ".join("?" for _ in values)
    conn.execute(
        f"INSERT INTO explicacions ({insert_columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def backfill_check_states_from_documents(
    *,
    db_path: Optional[str] = None,
    markdown_path: Optional[str] = None,
    txt_path: Optional[str] = None,
    explanation_path: Optional[str] = None,
) -> Dict[str, int]:
    db = db_path or resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
    markdown = Path(markdown_path) if markdown_path else Path(resolve_post_crq_markdown_path())
    txt = Path(txt_path) if txt_path else _default_txt_path()
    explanation = Path(explanation_path) if explanation_path else _default_explanation_path()

    markdown_checks = {item["check_id"]: item for item in parse_post_crq_checks(str(markdown))}
    txt_check_ids = _extract_txt_check_ids(txt)
    explanation_catalog = load_check_explanation_catalog_from_path(explanation)
    now = utc_now_iso()

    stats = {"checks_seen": 0, "explanations_upserted": 0, "sync_rows_updated": 0, "txt_lines_repaired": 0}

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        for check_id in sorted(markdown_checks):
            stats["checks_seen"] += 1
            check_row = conn.execute(
                "SELECT * FROM audit_checks WHERE check_id = ? AND actiu = 1",
                (check_id,),
            ).fetchone()
            if not check_row:
                continue

            current_version = conn.execute(
                "SELECT id FROM consulta_versions WHERE check_id = ? AND es_vigent = 1 ORDER BY versio DESC LIMIT 1",
                (check_id,),
            ).fetchone()
            version_id = current_version["id"] if current_version else None

            if check_id in explanation_catalog and version_id is not None:
                payload = _build_explanation_payload(explanation_catalog[check_id])
                _upsert_explanation_row(
                    conn,
                    check_id=check_id,
                    version_id=version_id,
                    payload=payload,
                    now=now,
                )
                stats["explanations_upserted"] += 1

            _upsert_sync_status(conn, check_id, "auditoria_post_crq.md", "OK", now)
            stats["sync_rows_updated"] += 1

            if check_id not in txt_check_ids and txt.exists():
                with txt.open("a", encoding="utf-8") as handle:
                    if txt.stat().st_size > 0:
                        handle.write("\n")
                    handle.write(_build_txt_line(check_row))
                txt_check_ids.add(check_id)
                stats["txt_lines_repaired"] += 1

            if check_id in txt_check_ids:
                _upsert_sync_status(conn, check_id, "consultes_post_crq.txt", "OK", now)
                stats["sync_rows_updated"] += 1

            if check_id in explanation_catalog:
                _upsert_sync_status(conn, check_id, "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md", "OK", now)
                stats["sync_rows_updated"] += 1

        conn.commit()

    return stats
