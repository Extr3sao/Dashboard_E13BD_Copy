"""
sql_codex_transformer.py
────────────────────────
Transforma queries SQL d'Oracle SQL Developer al format
compatible amb el motor Codex (E13BD).

Regles aplicades (en ordre):
  1. Eliminar línies DEFINE / UNDEFINE
  2. Normalitzar variables &VAR (treure cometes en TO_DATE, etc.)
  3. Netejar comentaris de capçalera irrelevants (autor, data, versió)
  4. Eliminar punt i coma final
  5. Formatar keywords en MAJÚSCULES (preservant strings)

Ús directe:
    from core.sql_codex_transformer import transform_for_codex
    clean_sql = transform_for_codex(raw_sql)

Ús amb mode debug:
    result = transform_for_codex(raw_sql, debug=True)
    # result → {"original": ..., "changes": [...], "sql": ...}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ─── Regex compilats ──────────────────────────────────────────────────────────

# Línies DEFINE / UNDEFINE (qualsevol indentació, case-insensitive)
_DEFINE_LINE = re.compile(
    r"^\s*(?:DEFINE|UNDEFINE)\s+.+$",
    re.IGNORECASE | re.MULTILINE,
)

# Comentaris de capçalera (-- Autor:, -- Data:, -- Versió:, -- Fitxer:, -- Dir:)
_HEADER_COMMENT = re.compile(
    r"^\s*--\s*(?:autor|author|data|date|versió|version|fitxer|file|dir(?:ectori)?|"
    r"descripcio|description|propòsit|purpose|creat|created).*$",
    re.IGNORECASE | re.MULTILINE,
)

# Variable &VAR entre cometes dins TO_DATE / TO_TIMESTAMP / TO_NUMBER
# Ex: TO_DATE('&START_AT', 'YYYY-MM-DD') → TO_DATE(&START_AT, 'YYYY-MM-DD')
_QUOTED_VAR_IN_FUNCTION = re.compile(
    r"(TO_DATE|TO_TIMESTAMP|TO_NUMBER)\s*\(\s*'(&[A-Z_][A-Z0-9_]*)'\s*,",
    re.IGNORECASE,
)

# Variable &VAR entre cometes simples en context genèric
# Ex: = '&NOM' → = &NOM   (només si el valor sencer de la cadena és la variable)
_QUOTED_STANDALONE_VAR = re.compile(
    r"'(&[A-Z_][A-Z0-9_]*)'",
    re.IGNORECASE,
)

# Punt i coma final (potencialment precedit d'espais / salts)
_TRAILING_SEMICOLON = re.compile(r"\s*;\s*$")

# Línies buides múltiples → màxim una línia en blanc
_MULTI_BLANK = re.compile(r"\n{3,}")

# Detectar variables &VAR (per validació final)
_ANY_VAR = re.compile(r"&[A-Z_][A-Z0-9_]*", re.IGNORECASE)


# ─── Dataclass resultat debug ─────────────────────────────────────────────────

@dataclass
class TransformResult:
    """Resultat complet de la transformació en mode debug."""
    original: str
    changes: list[str] = field(default_factory=list)
    sql: str = ""
    has_define_remaining: bool = False
    variables_found: list[str] = field(default_factory=list)


# ─── Funció principal ─────────────────────────────────────────────────────────

def transform_for_codex(raw_sql: str, *, debug: bool = False) -> Any:
    """
    Transforma raw_sql al format compatible amb Codex.

    Args:
        raw_sql:  SQL d'Oracle SQL Developer (pot contenir DEFINE, etc.)
        debug:    Si True, retorna TransformResult amb detall de canvis.
                  Si False (defecte), retorna el string SQL net.

    Returns:
        str (debug=False) o TransformResult (debug=True)
    """
    result = TransformResult(original=raw_sql)
    sql = raw_sql or ""

    # ── 1. Eliminar DEFINE / UNDEFINE ─────────────────────────────────────────
    found_defines = _DEFINE_LINE.findall(sql)
    if found_defines:
        result.changes.append(
            f"Eliminats {len(found_defines)} blocs DEFINE/UNDEFINE: "
            + ", ".join(line.strip()[:60] for line in found_defines)
        )
        sql = _DEFINE_LINE.sub("", sql)

    # ── 2. Netejar comentaris de capçalera ────────────────────────────────────
    header_hits = _HEADER_COMMENT.findall(sql)
    if header_hits:
        result.changes.append(
            f"Eliminats {len(header_hits)} comentaris de capçalera (autor/data/versió)"
        )
        sql = _HEADER_COMMENT.sub("", sql)

    # ── 3. Normalitzar &VAR entre cometes dins funcions (TO_DATE, etc.) ───────
    def _unwrap_fn_var(m: re.Match) -> str:
        fn, var = m.group(1), m.group(2)
        return f"{fn}({var},"

    hits_fn = len(_QUOTED_VAR_IN_FUNCTION.findall(sql))
    if hits_fn:
        result.changes.append(
            f"Normalitzades {hits_fn} variables '&VAR' dins funcions de conversió "
            "(eliminades cometes externes)"
        )
        sql = _QUOTED_VAR_IN_FUNCTION.sub(_unwrap_fn_var, sql)

    # ── 4. Normalitzar &VAR entre cometes en context genèric ──────────────────
    # Nota: només variables isolades ('&VAR'), no literals mixtos ('prefix_&VAR')
    standalone_hits = len(_QUOTED_STANDALONE_VAR.findall(sql))
    if standalone_hits:
        result.changes.append(
            f"Normalitzades {standalone_hits} variables '&VAR' en context string "
            "(eliminades cometes externes)"
        )
        sql = _QUOTED_STANDALONE_VAR.sub(r"\1", sql)

    # ── 5. Eliminar punt i coma final ─────────────────────────────────────────
    if _TRAILING_SEMICOLON.search(sql):
        result.changes.append("Eliminat punt i coma final")
        sql = _TRAILING_SEMICOLON.sub("", sql)

    # ── 6. Netejar línies buides excessives ───────────────────────────────────
    sql = _MULTI_BLANK.sub("\n\n", sql).strip()

    # ── 7. Validació final ────────────────────────────────────────────────────
    result.has_define_remaining = bool(_DEFINE_LINE.search(sql))
    result.variables_found = sorted(
        {m.upper() for m in _ANY_VAR.findall(sql)}
    )

    if result.has_define_remaining:
        result.changes.append(
            "⚠️  AVÍS: Queden línies DEFINE que no han pogut ser eliminades"
        )

    result.sql = sql

    if debug:
        return result
    return sql


# ─── Utilitat: validar SQL net ────────────────────────────────────────────────

def validate_codex_sql(sql: str) -> dict[str, Any]:
    """
    Valida que el SQL resultat és compatible amb Codex.

    Retorna:
        {
            "valid": bool,
            "errors": list[str],
            "warnings": list[str],
            "variables": list[str],
        }
    """
    errors: list[str] = []
    warnings: list[str] = []

    if _DEFINE_LINE.search(sql):
        errors.append("SQL conté línies DEFINE/UNDEFINE (no suportades per Codex)")

    variables = sorted({m.upper() for m in _ANY_VAR.findall(sql or "")})
    if not variables:
        warnings.append("SQL sense variables dinàmiques → execució estàtica")

    if sql.strip().endswith(";"):
        warnings.append("SQL acabat amb ';' (Codex pot no requerir-lo)")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "variables": variables,
    }


# ─── CLI mínim per proves ─────────────────────────────────────────────────────

if __name__ == "__main__":
    _DEMO = """
-- Autor: J. García
-- Data: 2026-04-09
-- Versió: 1.2
DEFINE START_AT = '2026-04-09 11:42:00'
DEFINE END_AT   = '2026-04-10 11:42:00'

SELECT t.owner        AS ESQUEMA,
       t.object_name  AS NOM_OBJECTE,
       t.last_ddl_time AS DATA_MODIFICACIO
FROM   dba_objects t
WHERE  t.last_ddl_time > TO_DATE('&START_AT', 'YYYY-MM-DD HH24:MI:SS')
  AND  t.last_ddl_time < TO_DATE('&END_AT',   'YYYY-MM-DD HH24:MI:SS')
  AND  t.owner = '&OWNER_NAME'
ORDER BY t.last_ddl_time DESC;
"""

    print("=== MODE NORMAL ===")
    print(transform_for_codex(_DEMO))

    print("\n=== MODE DEBUG ===")
    r = transform_for_codex(_DEMO, debug=True)
    print("Canvis aplicats:")
    for change in r.changes:
        print(f"  • {change}")
    print(f"\nVariables trobades: {r.variables_found}")
    print(f"DEFINE restants: {r.has_define_remaining}")
    print("\nSQL final:")
    print(r.sql)

    print("\n=== VALIDACIÓ ===")
    import json
    print(json.dumps(validate_codex_sql(r.sql), indent=2, ensure_ascii=False))
