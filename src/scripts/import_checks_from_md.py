"""
import_checks_from_md.py
========================
Script de migració inicial: parseja `auditoria_post_crq.md` i
pobla les taules `audit_checks` + `consulta_versions` a SQLite.

Execució:
    python src/scripts/import_checks_from_md.py

Idempotent: si un check_id ja existeix, s'actualitza la seva versió
sense duplicar dades.

Codificació: UTF-8  (garantia lingüística català)
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ─── Configuració de rutes ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/scripts → projecte arrel
MD_FILE = PROJECT_ROOT / "auditoria_post_crq.md"
TXT_FILE = PROJECT_ROOT / "consultes_post_crq.txt"

# Afegim el projecte al path per poder importar
sys.path.insert(0, str(PROJECT_ROOT))
from src.core.sqlite_paths import resolve_sqlite_path
from src.core.time_utils import utc_now_iso

DB_PATH = resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")

# ─── Inicialització de la BBDD ────────────────────────────────────────────────
def inicialitzar_db():
    try:
        from src.core.internal_db import InternalDBManager
        # Al crear l'objecte, ja s'executa _init_db()
        InternalDBManager(db_path=DB_PATH)
        print(f"  [OK] Base de dades inicialitzada a {DB_PATH}")
    except Exception as e:
        print(f"  [AVIS] Avis al inicialitzar DB: {e}")


# ─── Patrons de parsing del .md ───────────────────────────────────────────────
# Captura el bloc complet SQL d'un check:
# -- CHECK NN: TÍTOL
# -- Severitat: X
# -- Criteri: ...
# ============
_BLOCK_RE = re.compile(
    r"```sql\s*\n"
    r"-- =+\s*\n"
    r"-- CHECK[ _](\d+):\s*(.+?)\s*\n"       # grup 1=nn, grup 2=títol
    r"-- Severitat:\s*(.+?)\s*\n"             # grup 3=severitat
    r"(?:-- Criteri:\s*\n)?"
    r"((?:--.*?\n)*?)"                        # grup 4=criteri (comentaris)
    r"-- =+\s*\n"
    r"(.*?)"                                  # grup 5=SQL
    r"```",
    re.DOTALL | re.IGNORECASE,
)

# Parsing del catàleg .txt per obtenir els paràmetres
# CHECK_NN | TITOL | severitat base: X | paràmetres: Y
_TXT_RE = re.compile(
    r"CHECK_(\d+)\s*\|[^|]+\|[^|]+\|\s*paràmetres:\s*(.+)",
    re.IGNORECASE,
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_md(md_path: Path) -> list[dict]:
    """Parseja el fitxer .md i retorna una llista de dicts per cada check."""
    contingut = md_path.read_text(encoding="utf-8")
    checks = []
    for m in _BLOCK_RE.finditer(contingut):
        nn      = m.group(1).zfill(2)
        titol   = m.group(2).strip().upper()
        sev     = m.group(3).strip().upper()
        # Netejar el criteri de comentaris SQL
        criteri_raw = m.group(4) or ""
        criteri = " ".join(
            line.lstrip("-").strip()
            for line in criteri_raw.splitlines()
            if line.strip().startswith("--")
        ).strip()
        sql_text = m.group(5).strip()
        checks.append({
            "check_id":      f"CHECK_{nn}",
            "titol":         titol,
            "severitat_base": _normalitza_severitat(sev),
            "context_check": criteri,
            "sql_text":      sql_text,
            "ordre":         int(nn),
            "tipus":         _detecta_tipus(sql_text),
        })
    return checks


def parse_txt(txt_path: Path) -> dict[str, str]:
    """Retorna un dict {CHECK_NN: paràmetres_str} del catàleg .txt."""
    params_map: dict[str, str] = {}
    if not txt_path.exists():
        return params_map
    for line in txt_path.read_text(encoding="utf-8").splitlines():
        m = _TXT_RE.search(line)
        if m:
            nn = m.group(1).zfill(2)
            params_map[f"CHECK_{nn}"] = m.group(2).strip()
    return params_map


def _normalitza_severitat(sev: str) -> str:
    mapping = {
        "CRÍTIC": "CRÍTIC",
        "CRITIC": "CRÍTIC",
        "STOPPER": "STOPPER",
        "ALT": "ALT",
        "MITTÀ": "MITJÀ",
        "MITJA": "MITJÀ",
        "MITJÀ": "MITJÀ",
        "BAIX": "BAIX",
    }
    return mapping.get(sev.upper(), sev)


def _detecta_tipus(sql: str) -> str:
    indicadors_plsql = ("BEGIN", "DECLARE", "PROCEDURE", "FUNCTION", "PACKAGE",
                        "DBMS_", "EXECUTE", "LOOP", "CURSOR")
    sql_upper = sql.upper()
    return "PLSQL" if any(k in sql_upper for k in indicadors_plsql) else "SQL"


def importar(checks: list[dict], params_map: dict[str, str]) -> None:
    ara = utc_now_iso()
    amb_error = 0

    with sqlite3.connect(DB_PATH) as conn:
        for c in checks:
            check_id = c["check_id"]
            parametres = params_map.get(check_id, "days_back")
            try:
                # Upsert del check
                conn.execute(
                    """INSERT INTO audit_checks
                       (check_id, titol, severitat_base, parametres, tipus, ordre, actiu,
                        context_check, creat_en, actualitzat_en)
                       VALUES (?,?,?,?,?,?,1,?,?,?)
                       ON CONFLICT(check_id) DO UPDATE SET
                           titol = excluded.titol,
                           severitat_base = excluded.severitat_base,
                           parametres = excluded.parametres,
                           context_check = excluded.context_check,
                           actualitzat_en = excluded.actualitzat_en
                    """,
                    (check_id, c["titol"], c["severitat_base"], parametres,
                     c["tipus"], c["ordre"], c["context_check"], ara, ara),
                )

                # Comprovar si ja té una versió vigent amb el mateix SQL
                row = conn.execute(
                    "SELECT id, sql_text, versio FROM consulta_versions "
                    "WHERE check_id = ? AND es_vigent = 1",
                    (check_id,),
                ).fetchone()

                nou_checksum = sha256(c["sql_text"])
                if row:
                    actual_checksum = sha256(row[1])
                    if actual_checksum == nou_checksum:
                        print(f"  ✓ {check_id} — versió vigent sense canvis, omès.")
                        continue
                    # Desactivar la versió actual
                    conn.execute(
                        "UPDATE consulta_versions SET es_vigent = 0 WHERE id = ?",
                        (row[0],),
                    )
                    nova_versio = row[2] + 1
                else:
                    nova_versio = 1

                conn.execute(
                    """INSERT INTO consulta_versions
                       (check_id, versio, sql_text, checksum, creat_per, creat_en, es_vigent)
                       VALUES (?,?,?,?,'migracio',?,1)""",
                    (check_id, nova_versio, c["sql_text"], nou_checksum, ara),
                )
                print(f"  ✅ {check_id} — versió {nova_versio} importada.")

            except Exception as exc:
                print(f"  ❌ Error en {check_id}: {exc}")
                amb_error += 1

        conn.commit()

    print(f"\nMigració completada: {len(checks) - amb_error}/{len(checks)} checks importats.")
    if amb_error:
        print(f"⚠️  {amb_error} checks amb errors (revisa el log).")


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  Migració de checks: {MD_FILE.name}")
    print(f"  BBDD destí: {DB_PATH}")
    inicialitzar_db()

    print(f"{'='*60}\n")

    if not MD_FILE.exists():
        print(f"❌ No s'ha trobat el fitxer: {MD_FILE}")
        sys.exit(1)

    checks = parse_md(MD_FILE)
    params_map = parse_txt(TXT_FILE)
    print(f"  Checks detectats al .md: {len(checks)}")
    print()

    importar(checks, params_map)


if __name__ == "__main__":
    main()
