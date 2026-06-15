"""
query_sync_service.py
=====================
Servei de sincronitzacio segura entre la BBDD SQLite (font de veritat)
i els fitxers derivats:
  - auditoria_post_crq.md   -> blocs SQL amb capcalera de comentari
  - consultes_post_crq.txt  -> index de checks, un per linia

Estrategia:
  1. Llegir fitxer original a memoria
  2. Localitzar el bloc del check per regex (marcador identificador)
  3. Substituir el bloc mantenint el format original
  4. Validar before/after (nombre de blocs, integritat)
  5. Backup .bak previ
  6. Escriure fitxer
  7. Marcar estat a sincronitzacio_fitxers

Codificacio: UTF-8
"""
from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Optional, Tuple

from src.core.check_explanation_catalog import load_check_explanation_catalog
from src.core.time_utils import utc_now_iso

logger = logging.getLogger(__name__)

FITXER_MD = "auditoria_post_crq.md"
FITXER_TXT = "consultes_post_crq.txt"
FITXER_EXPL = "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md"

_BLOCK_RE = re.compile(
    r"```sql\s*\n"
    r"(-- =+\s*\n"
    r"-- CHECK[ _](\d+):.*?"
    r"-- =+\s*\n"
    r".*?)"
    r"```",
    re.DOTALL | re.IGNORECASE,
)


class QuerySyncService:
    """Gestiona la sincronitzacio segura dels fitxers derivats d'un check."""

    def __init__(self, project_root: str | Path, db_path: str):
        self.root = Path(project_root)
        self.db_path = str(db_path)

    def sync_check(
        self,
        check_id: str,
        bloc_md: str,
        linia_txt: str,
        explicacio_check_text: Optional[str] = None,
    ) -> dict:
        resultats = {"md": "PENDENT", "txt": "PENDENT", "expl": "PENDENT", "errors": []}

        path_md = self.root / FITXER_MD
        ok_md, err_md = self._sync_md(check_id, bloc_md, path_md)
        resultats["md"] = "OK" if ok_md else "ERROR"
        if err_md:
            resultats["errors"].append(f"MD: {err_md}")

        path_txt = self.root / FITXER_TXT
        nn = check_id.replace("CHECK_", "").lstrip("0").zfill(2)
        ok_txt, err_txt = self._sync_txt(f"CHECK_{nn}", linia_txt, path_txt)
        resultats["txt"] = "OK" if ok_txt else "ERROR"
        if err_txt:
            resultats["errors"].append(f"TXT: {err_txt}")

        path_expl = self.root / FITXER_EXPL
        ok_expl, err_expl = self._sync_explanation_catalog(check_id, explicacio_check_text, path_expl)
        resultats["expl"] = "OK" if ok_expl else "ERROR"
        if err_expl:
            resultats["errors"].append(f"EXPL: {err_expl}")

        for fitxer_clau, estat, err in [
            (FITXER_MD, resultats["md"], err_md),
            (FITXER_TXT, resultats["txt"], err_txt),
            (FITXER_EXPL, resultats["expl"], err_expl),
        ]:
            self._update_sync_status(check_id, fitxer_clau, estat, err)
        return resultats

    def mark_pending(self, check_id: str) -> None:
        for fitxer in [FITXER_MD, FITXER_TXT, FITXER_EXPL]:
            self._update_sync_status(check_id, fitxer, "PENDENT", None)

    def mark_error(self, check_id: str, error_message: Optional[str]) -> None:
        for fitxer in [FITXER_MD, FITXER_TXT, FITXER_EXPL]:
            self._update_sync_status(check_id, fitxer, "ERROR", error_message)

    def get_sync_status(self, check_id: str) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                columns = self._get_sync_table_columns(conn)
                darrera_sync_expr = "darrera_sync" if "darrera_sync" in columns else "NULL AS darrera_sync"
                error_expr = "error_missatge" if "error_missatge" in columns else "NULL AS error_missatge"
                rows = conn.execute(
                    f"SELECT fitxer, estat, {darrera_sync_expr}, {error_expr} "
                    "FROM sincronitzacio_fitxers WHERE check_id = ?",
                    (check_id,),
                ).fetchall()
            return [
                {"fitxer": row[0], "estat": row[1], "darrera_sync": row[2], "error": row[3]}
                for row in rows
            ]
        except sqlite3.OperationalError:
            return []

    def _sync_md(self, check_id: str, nou_bloc: str, path_md: Path) -> Tuple[bool, Optional[str]]:
        if not path_md.exists():
            return False, f"Fitxer no trobat: {path_md}"

        contingut_original = path_md.read_text(encoding="utf-8")
        if not re.search(r"\d+", check_id):
            return False, f"No s'ha pogut extreure el numero de {check_id}"

        blocs_originals = list(_BLOCK_RE.finditer(contingut_original))
        if not blocs_originals:
            contingut_nou = contingut_original.rstrip() + "\n\n---\n\n" + nou_bloc + "\n"
            return self._write_safe(path_md, contingut_original, contingut_nou)

        target_num = (check_id.replace("CHECK_", "").lstrip("0") or "0").zfill(2)
        target_matches = [
            match
            for match in blocs_originals
            if match.group(2).zfill(2) == target_num
        ]

        if not target_matches:
            contingut_nou = contingut_original.rstrip() + "\n\n---\n\n" + nou_bloc + "\n"
        else:
            parts: list[str] = []
            cursor = 0
            for index, match in enumerate(target_matches):
                start, end = match.span()
                segment = contingut_original[cursor:start]
                if index == 0:
                    parts.append(segment)
                    parts.append(nou_bloc)
                else:
                    segment = re.sub(r"\n\s*---\s*\n\s*$", "\n", segment)
                    parts.append(segment)
                cursor = end
            parts.append(contingut_original[cursor:])
            contingut_nou = "".join(parts)
            contingut_nou = re.sub(r"\n{3,}", "\n\n", contingut_nou)

        return self._write_safe(path_md, contingut_original, contingut_nou)

    def _sync_txt(self, check_prefix: str, nova_linia: str, path_txt: Path) -> Tuple[bool, Optional[str]]:
        if not path_txt.exists():
            return False, f"Fitxer no trobat: {path_txt}"

        contingut_original = path_txt.read_text(encoding="utf-8")
        updated = []
        trobat = False
        for line in contingut_original.splitlines(keepends=True):
            if line.startswith(f"{check_prefix} |") or line.startswith(f"{check_prefix}|"):
                updated.append(nova_linia + "\n")
                trobat = True
            else:
                updated.append(line)

        if not trobat:
            updated.append(nova_linia + "\n")

        contingut_nou = "".join(updated)
        return self._write_safe(path_txt, contingut_original, contingut_nou)

    def _sync_explanation_catalog(
        self,
        check_id: str,
        explicacio_check_text: Optional[str],
        path_expl: Path,
    ) -> Tuple[bool, Optional[str]]:
        if not explicacio_check_text or not explicacio_check_text.strip():
            return False, "Contingut d'explicacio buit."
        if not path_expl.exists():
            return False, f"Fitxer no trobat: {path_expl}"

        contingut_original = path_expl.read_text(encoding="utf-8")
        escaped_check_id = re.escape(check_id)
        block_pattern = re.compile(
            rf"(?ms)^##\s+{escaped_check_id}\s+[-—].*?(?=^##\s+CHECK_\d+\s+[-—]|\Z)"
        )
        replacement = explicacio_check_text.strip() + "\n\n"

        if block_pattern.search(contingut_original):
            contingut_nou = block_pattern.sub(replacement, contingut_original, count=1)
        else:
            contingut_nou = contingut_original.rstrip() + "\n\n" + replacement

        ok, err = self._write_safe(path_expl, contingut_original, contingut_nou)
        if ok:
            load_check_explanation_catalog.cache_clear()
        return ok, err

    def _write_safe(self, path: Path, contingut_original: str, contingut_nou: str) -> Tuple[bool, Optional[str]]:
        ok, err = self._validate_change(path, contingut_original, contingut_nou)
        if not ok:
            return False, err

        bak = path.with_suffix(path.suffix + ".bak")
        try:
            shutil.copy2(path, bak)
        except OSError as exc:
            logger.warning("[SyncService] No s'ha pogut fer backup de %s: %s", path, exc)

        try:
            path.write_text(contingut_nou, encoding="utf-8")
            logger.info("[SyncService] Fitxer actualitzat: %s", path.name)
            return True, None
        except OSError as exc:
            if bak.exists():
                try:
                    shutil.copy2(bak, path)
                except OSError as restore_exc:
                    logger.error(
                        "[SyncService] Error restaurant backup de %s despres d'una fallada d'escriptura: %s",
                        path,
                        restore_exc,
                    )
                    return False, f"{exc} | restore_failed: {restore_exc}"
            return False, str(exc)

    def _validate_change(self, path: Path, original: str, nou: str) -> Tuple[bool, Optional[str]]:
        if not nou.strip():
            return False, "El contingut nou es buit."

        if len(nou) < len(original) * 0.6:
            return False, (
                f"El nou contingut ({len(nou)} bytes) es massa curt "
                f"respecte l'original ({len(original)} bytes). Operacio cancel.lada."
            )

        if path.suffix == ".md":
            n_blocs_orig = len(_BLOCK_RE.findall(original))
            n_blocs_nou = len(_BLOCK_RE.findall(nou))
            if n_blocs_orig > 0 and n_blocs_nou < n_blocs_orig - 1:
                return False, (
                    f"S'han perdut blocs SQL: original={n_blocs_orig}, nou={n_blocs_nou}."
                )

        return True, None

    def _update_sync_status(self, check_id: str, fitxer: str, estat: str, error: Optional[str]) -> None:
        ara = utc_now_iso()
        try:
            with sqlite3.connect(self.db_path) as conn:
                columns = self._get_sync_table_columns(conn)
                existing = conn.execute(
                    "SELECT id FROM sincronitzacio_fitxers WHERE check_id = ? AND fitxer = ? ORDER BY id DESC LIMIT 1",
                    (check_id, fitxer),
                ).fetchone()
                if {"darrera_sync", "error_missatge"}.issubset(columns):
                    values = (estat, ara if estat != "PENDENT" else None, error)
                    if existing:
                        conn.execute(
                            """
                            UPDATE sincronitzacio_fitxers
                            SET estat = ?, darrera_sync = ?, error_missatge = ?
                            WHERE id = ?
                            """,
                            (*values, existing[0]),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat, darrera_sync, error_missatge)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (check_id, fitxer, *values),
                        )
                else:
                    if existing:
                        conn.execute(
                            "UPDATE sincronitzacio_fitxers SET estat = ? WHERE id = ?",
                            (estat, existing[0]),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO sincronitzacio_fitxers (check_id, fitxer, estat)
                            VALUES (?, ?, ?)
                            """,
                            (check_id, fitxer, estat),
                        )
                conn.commit()
        except sqlite3.OperationalError as exc:
            logger.error("[SyncService] Error actualitzant estat sync: %s", exc)

    def _get_sync_table_columns(self, conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("PRAGMA table_info(sincronitzacio_fitxers)").fetchall()
        return {str(row[1]) for row in rows}
