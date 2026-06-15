import datetime
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from src.core.check_explanation_catalog import load_check_explanation_catalog
from src.core.ownership_resolver import resolve_ownership


logger = logging.getLogger(__name__)


CRITICALITY_ORDER = ("CRITIC", "MITJA", "BAIX")
MALFORMED_TEXT_MARKERS = ("Ã", "Â", "incidÃ", "traÃ", "modificaciÃ")
CRITICALITY_LABELS = {
    "CRITIC": "Crític",
    "MITJA": "Mitjà",
    "BAIX": "Baix",
}
CRITICALITY_ACTIONS = {
    "CRITIC": "Aquestes incidències s'han de solucionar de manera urgent.",
    "MITJA": "Aquestes incidències s'han de solucionar en un termini màxim de 15 dies.",
    "BAIX": "Aquestes incidències s'han de solucionar en un termini màxim d'1 mes.",
}


class ExecutionContext(TypedDict):
    profile: str
    schemas: List[str]
    selected_checks: List[str]
    time_filter: Dict[str, Any]
    source_file: str
    source_path: str
    generated_at: str


class ExecutionPlan(TypedDict):
    lead_agent: str
    structural_copilot: str
    phases: List[Dict[str, Any]]
    selected_checks: List[str]
    criticality_overrides: Dict[str, Any]
    quality_gates: List[str]


class FindingEnvelope(TypedDict, total=False):
    finding_id: str
    check_id: str
    title: str
    schema: Optional[str]
    object_name: Optional[str]
    object_type: Optional[str]
    sql_severity: str
    runtime_status: str
    evidence: Dict[str, Any]
    dba_enrichment: Dict[str, Any]
    lot_assignment: Dict[str, Any]
    final_criticality: str
    final_criticality_label: str
    row_index: int
    ai_analysis: Dict[str, Any]
    incident_table_entry: Dict[str, Any]
    source_row: Dict[str, Any]


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _normalize_text(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _normalize_institutional_text(value: Any) -> str:
    text = str(value or "")
    replacements = (
        (r"\bprimary key\b", "clau primària"),
        (r"\bforeign keys\b", "claus foranes"),
        (r"\bforeign key\b", "clau forana"),
        (r"\bnumber\b", "NUMBER"),
        (r"\bapex\b", "APEX"),
        (r"\blote\b", "lot"),
        (r"\bpostdeploy\b", "postdesplegament"),
        (r"\bgo-live\b", "entrada en producció"),
        (r"\btests\b", "proves"),
        (r"\btest\b", "prova"),
        (r"\bvolver\b", "tornar"),
        (r"\beliminarlo\b", "eliminar-lo"),
        (r"\binadecuat\b", "inadequat"),
        (r"\bcoluna\b", "columna"),
        (r"\bomettant\b", "ometent"),
        (r"\bdesenvolupaments\b", "desenvolupament"),
        (r"\bentrega\b", "lliurament"),
        (r"perqu\?", "perquè"),
        (r"freq\?ents", "freqüents"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _normalize_catalog_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(entry)
    for key in (
        "title",
        "que_detecta",
        "per_que_es_important",
        "impacte_sobre_lot",
        "com_revisar",
        "com_corregir",
        "validacio_posterior",
        "limitacions",
    ):
        normalized[key] = _normalize_institutional_text(normalized.get(key) or "")
    return normalized


def _normalize_guidance_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(entry)
    for key in (
        "technical_explanation",
        "functional_explanation",
        "recommended_fix",
        "review_steps",
        "limitations",
        "post_validation",
    ):
        normalized[key] = _normalize_institutional_text(normalized.get(key) or "")
    normalized["impact_categories"] = [
        _normalize_institutional_text(item)
        for item in (normalized.get("impact_categories") or [])
    ]
    normalized["recommended_table_columns"] = [
        _normalize_institutional_text(item)
        for item in (normalized.get("recommended_table_columns") or [])
    ]
    return normalized


def _criticality_key(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "CRITIC" in text: return "CRITIC"
    if "MITJ" in text or "MEDIUM" in text: return "MITJA"
    if "BAIX" in text or "LOW" in text: return "BAIX"
    return "BAIX"

def _criticality_rank(value: Any) -> int:
    key = _criticality_key(value)
    if key == "CRITIC": return 0
    if key == "MITJA":  return 1
    return 2

def _parse_iso_dt(val: str, end: bool = False) -> Optional[datetime.datetime]:
    if not val or not str(val).strip():
        return None
    val_orig = str(val)
    if not val:
        return None
    try:
        # Normalitzar: espai -> T per a intercanviabilitat ISO
        normalized = str(val).strip().split('.')[0].replace(" ", "T")
        
        if "T" in normalized:
            # Intents de parseig amb hores/minuts
            formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
            for fmt in formats:
                try:
                    return datetime.datetime.strptime(normalized[:len(fmt)-2], fmt) if len(normalized) >= len(fmt)-2 else None
                except ValueError:
                    continue
            try:
                return datetime.datetime.fromisoformat(normalized)
            except ValueError:
                pass

        # Fallback a data simple
        if len(normalized) >= 10:
            parsed_date = datetime.date.fromisoformat(normalized[:10])
            time_value = datetime.time.max.replace(second=59, microsecond=0) if end else datetime.time.min
            return datetime.datetime.combine(parsed_date, time_value)
        return None
    except Exception as exc:
        logger.debug("No s'ha pogut parsejar la data ISO %r: %s", val, exc)
        return None


def _criticality_label(value: Any) -> str:
    return CRITICALITY_LABELS.get(_criticality_key(value), "Baix")


def _resolve_time_window(time_filter: Dict[str, Any]) -> Dict[str, Optional[str]]:
    mode = str(time_filter.get("mode") or "preset").strip().lower()
    if mode == "range":
        start_raw = str(time_filter.get("range_start_at") or time_filter.get("start_date") or "").strip()
        end_raw = str(time_filter.get("range_end_at") or time_filter.get("end_date") or "").strip()
        if start_raw and end_raw:
            start_dt = _parse_iso_dt(start_raw)
            end_has_time = "T" in end_raw or bool(re.search(r"\d{2}:\d{2}", end_raw))
            end_dt = _parse_iso_dt(end_raw, end=not end_has_time)
            if start_dt and end_dt:
                return {
                    "start_at": start_dt.isoformat(timespec="minutes"),
                    "end_at": end_dt.isoformat(timespec="minutes"),
                }

    resolved_at = str(time_filter.get("resolved_at") or "").strip()
    if not resolved_at:
        return {"start_at": None, "end_at": None}
    end_dt = _parse_iso_dt(resolved_at, end=True)
    if not end_dt:
        return {"start_at": None, "end_at": None}
    days_back = max(1, int(time_filter.get("days_back") or 1))
    start_dt = end_dt - datetime.timedelta(days=days_back)
    return {
        "start_at": start_dt.isoformat(timespec="minutes"),
        "end_at": end_dt.isoformat(timespec="minutes"),
    }


def build_execution_context(
    *,
    profile: str,
    schemas: List[str],
    selected_checks: List[str],
    time_filter: Dict[str, Any],
    source_file: str,
    source_path: str,
    generated_at: str,
) -> ExecutionContext:
    return {
        "profile": profile,
        "schemas": list(schemas or []),
        "selected_checks": list(selected_checks or []),
        "time_filter": dict(time_filter or {}),
        "source_file": source_file,
        "source_path": source_path,
        "generated_at": generated_at,
    }


def build_execution_plan(
    context: ExecutionContext,
    *,
    selected_checks: List[str],
    criticality_overrides: Optional[Dict[str, Any]] = None,
) -> ExecutionPlan:
    return {
        "lead_agent": "orchestrator-e13bd",
        "structural_copilot": "architect-e13bd",
        "selected_checks": list(selected_checks or []),
        "criticality_overrides": dict(criticality_overrides or {}),
        "quality_gates": [
            "sql_execution_completed_or_controlled_error",
            "dba_diagnostic_present_for_failed_checks",
            "critical_findings_have_lot_assignment",
            "report_text_is_utf8_clean",
        ],
        "phases": [
            {"id": "context", "lead": "orchestrator-e13bd", "validators": ["architect-e13bd"]},
            {"id": "planning", "lead": "orchestrator-e13bd", "validators": ["architect-e13bd", "dba-e13bd"]},
            {"id": "execution", "lead": "orchestrator-e13bd", "validators": ["dba-e13bd"]},
            {"id": "enrichment", "lead": "dba-e13bd", "validators": ["architect-e13bd"]},
            {"id": "validation", "lead": "tester-e13bd", "validators": ["architect-e13bd", "dba-e13bd"]},
            {"id": "ownership", "lead": "orchestrator-e13bd", "validators": ["dba-e13bd"]},
            {"id": "reporting", "lead": "insights-reporting-e13bd", "validators": ["tester-e13bd"]},
        ],
    }


def _extract_oracle_error_code(error_text: str) -> Optional[str]:
    match = re.search(r"\b(ORA-\d{5})\b", error_text or "", flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def _oracle_error_diagnostic(error_text: str, executed_sql: str) -> Dict[str, Any]:
    code = _extract_oracle_error_code(error_text or "")
    if code == "ORA-00923":
        return {
            "status": "error",
            "oracle_error_code": code,
            "oracle_error_summary": "Falta o està mal ubicada la clàusula FROM en una SELECT.",
            "likely_causes": [
                "coma sobrant abans de FROM",
                "alias o expressió calculada mal tancada",
                "SELECT amb CASE o LISTAGG incomplet",
            ],
            "review_hint": "Revisar l'última columna del SELECT abans del FROM i validar una versió mínima executable.",
            "patch_proposal": {
                "allowed_in_development": True,
                "target_file": "auditoria_post_crq.md",
                "summary": "Ajustar la projecció del SELECT i validar la sintaxi Oracle abans de publicar el check.",
            },
        }
    return {
        "status": "error",
        "oracle_error_code": code,
        "oracle_error_summary": "La consulta no s'ha pogut executar correctament a Oracle.",
        "likely_causes": ["sintaxi no compatible", "objecte Oracle inexistent", "construcció SQL incompleta"],
        "review_hint": "Executar la consulta aïlladament amb els mateixos binds i revisar el punt exacte de fallada.",
        "patch_proposal": {
            "allowed_in_development": True,
            "target_file": "auditoria_post_crq.md",
            "summary": "Corregir el SQL font del check al markdown canònic en fase de desenvolupament.",
        },
    }


def _pick_value(row: Dict[str, Any], candidates: List[str]) -> Optional[str]:
    for candidate in candidates:
        for key, value in row.items():
            if _normalize_key(key) == candidate and _normalize_text(value):
                return _normalize_text(value)
    return None


SCHEMA_FIELD_CANDIDATES = [
    "esquema",
    "schema",
    "schema_name",
    "owner",
    "username",
    "propietari",
    "propietari_desti",
    "propietari_index",
    "grantor",
    "grantee",
    "dependent_owner",
]


def _resolve_schema_value(
    row: Optional[Dict[str, Any]],
    context: Optional[ExecutionContext] = None,
) -> Optional[str]:
    schema = _pick_value(row or {}, SCHEMA_FIELD_CANDIDATES)
    if schema:
        return schema

    context_schemas = list((context or {}).get("schemas") or [])
    if len(context_schemas) == 1:
        candidate = str(context_schemas[0] or "").strip().upper()
        if candidate:
            return candidate
    return None


def _has_assignable_schema(finding: FindingEnvelope) -> bool:
    return bool(str(finding.get("schema") or "").strip())


def _has_meaningful_value(value: Any) -> bool:
    text = _normalize_text(value)
    return text not in {"", "-", "N/D", "No disponible", "sense estadistiques", "sense estadístiques", "mai"}


def _read_row_value(row: Dict[str, Any], candidates: List[str]) -> Optional[str]:
    return _pick_value(row, candidates)


def _format_numeric_text(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    digits = re.sub(r"[^\d-]", "", text)
    if digits and re.fullmatch(r"-?\d+", digits):
        try:
            return f"{int(digits):,}".replace(",", ".")
        except ValueError:
            return text
    return text


def _compact_parts(parts: List[str]) -> str:
    return " · ".join(part for part in parts if _has_meaningful_value(part))


def _build_incident_table_entry(check_id: str, row: Dict[str, Any], schema: Optional[str], object_name: Optional[str], object_type: Optional[str]) -> Dict[str, Any]:
    normalized_check = str(check_id or "").strip().upper()
    current_object = object_name or _read_row_value(row, ["objecte", "object_name", "nom_objecte", "taula", "tabla", "nom_taula", "sequencia", "sinonim", "constraint_fk", "nom_constraint", "columna"]) or "-"
    current_type = object_type or _read_row_value(row, ["tipus_objecte", "tipus", "tipus_constraint"]) or "-"

    if normalized_check == "CHECK_01":
        num_rows = _format_numeric_text(_read_row_value(row, ["num_rows", "num_files", "num_filas"]) or "")
        stats = _read_row_value(row, ["darrera_estadistica", "last_analyzed", "ultima_estadistica"]) or ""
        ddl = _read_row_value(row, ["data_modificacio_objecte", "last_ddl_time", "fecha_modif", "data_modificacio_taula"]) or ""
        return {
            "OBJECTE": current_object,
            "TIPUS": "TABLE",
            "DADA TÈCNICA": _compact_parts([
                "Sense clau primària activa",
                f"Volum estimat: {num_rows} files" if _has_meaningful_value(num_rows) else "",
                f"Estadístiques: {stats}" if _has_meaningful_value(stats) else "",
                f"DDL: {ddl}" if _has_meaningful_value(ddl) else "",
            ]),
        }

    if normalized_check == "CHECK_02":
        num_rows = _format_numeric_text(_read_row_value(row, ["num_rows", "num_files"]) or "")
        stats = _read_row_value(row, ["darrera_estadistica", "last_analyzed"]) or ""
        ddl = _read_row_value(row, ["data_modificacio_objecte", "last_ddl_time"]) or ""
        return {
            "OBJECTE": current_object,
            "TIPUS": "TABLE",
            "DADA TÈCNICA": _compact_parts([
                "Sense índex actiu",
                f"Volum estimat: {num_rows} files" if _has_meaningful_value(num_rows) else "",
                f"Estadístiques: {stats}" if _has_meaningful_value(stats) else "",
                f"DDL: {ddl}" if _has_meaningful_value(ddl) else "",
            ]),
        }

    if normalized_check == "CHECK_03":
        cache_actual = _read_row_value(row, ["cache_actual"]) or ""
        increment = _read_row_value(row, ["increment_by_value", "increment_by"]) or ""
        problema = _read_row_value(row, ["problema"]) or ""
        cache_recomanada = _read_row_value(row, ["cache_recomanada"]) or ""
        justificacio = _read_row_value(row, ["justificacio"]) or ""
        entry = {
            "OBJECTE": current_object,
            "TIPUS": "SEQUENCE",
            "DADA TÈCNICA": _compact_parts([
                f"CACHE {cache_actual}" if _has_meaningful_value(cache_actual) else "",
                f"INCREMENT {increment}" if _has_meaningful_value(increment) else "",
                problema,
                f"Cache recomanada: {cache_recomanada}" if _has_meaningful_value(cache_recomanada) else "",
            ]),
        }
        if _has_meaningful_value(justificacio):
            entry["OBSERVACIÓ"] = justificacio
        return entry

    if normalized_check == "CHECK_04":
        table_name = _read_row_value(row, ["taula"]) or ""
        columns_fk = _read_row_value(row, ["columnes_fk"]) or ""
        parent_table = _read_row_value(row, ["taula_pare"]) or ""
        ddl = _read_row_value(row, ["data_modificacio_taula"]) or ""
        return {
            "OBJECTE": current_object,
            "TIPUS": "FOREIGN KEY",
            "DADA TÈCNICA": _compact_parts([
                "Clau forana sense índex de suport",
                f"Taula: {table_name}" if _has_meaningful_value(table_name) else "",
                f"Columnes: {columns_fk}" if _has_meaningful_value(columns_fk) else "",
                f"Taula pare: {parent_table}" if _has_meaningful_value(parent_table) else "",
                f"DDL: {ddl}" if _has_meaningful_value(ddl) else "",
            ]),
        }

    if normalized_check == "CHECK_05":
        table_name = _read_row_value(row, ["taula"]) or ""
        status = _read_row_value(row, ["estat"]) or ""
        validated = _read_row_value(row, ["validada"]) or ""
        validation_state = _read_row_value(row, ["validation_state", "estat_validacio"]) or ""
        ddl = _read_row_value(row, ["data_modificacio_taula"]) or ""
        return {
            "OBJECTE": current_object,
            "TIPUS": current_type or "CONSTRAINT",
            "DADA TÈCNICA": _compact_parts([
                f"Taula: {table_name}" if _has_meaningful_value(table_name) else "",
                f"Estat: {status}" if _has_meaningful_value(status) else "",
                f"Validada: {validated}" if _has_meaningful_value(validated) else "",
                f"Estat validació: {validation_state}" if _has_meaningful_value(validation_state) else "",
                f"DDL: {ddl}" if _has_meaningful_value(ddl) else "",
            ]),
        }

    if normalized_check == "CHECK_06":
        table_name = _read_row_value(row, ["taula"]) or ""
        other_index = _read_row_value(row, ["index_2"]) or ""
        leader = _read_row_value(row, ["columna_lider_comuna"]) or ""
        data_recent = _read_row_value(row, ["data_modificacio_mes_recent"]) or ""
        return {
            "OBJECTE": _compact_parts([current_object, f"duplicat amb {other_index}" if _has_meaningful_value(other_index) else ""]).replace(" · ", " "),
            "TIPUS": "INDEX",
            "DADA TÈCNICA": _compact_parts([
                f"Taula: {table_name}" if _has_meaningful_value(table_name) else "",
                f"Columna líder comuna: {leader}" if _has_meaningful_value(leader) else "",
                f"Darrera modificació: {data_recent}" if _has_meaningful_value(data_recent) else "",
            ]),
        }

    if normalized_check == "CHECK_07":
        invalidated_at = _read_row_value(row, ["data_invalidacio"]) or ""
        created_at = _read_row_value(row, ["data_creacio"]) or ""
        return {
            "OBJECTE": current_object,
            "TIPUS": current_type or "OBJECTE ORACLE",
            "DADA TÈCNICA": _compact_parts([
                "Objecte invàlid",
                f"Darrera modificació: {invalidated_at}" if _has_meaningful_value(invalidated_at) else "",
                f"Creació: {created_at}" if _has_meaningful_value(created_at) else "",
            ]),
        }

    if normalized_check == "CHECK_08":
        table_name = _read_row_value(row, ["taula"]) or ""
        nullable = _read_row_value(row, ["nullable"]) or ""
        position = _read_row_value(row, ["posicio"]) or ""
        ddl = _read_row_value(row, ["data_modificacio_taula"]) or ""
        return {
            "OBJECTE": f"{table_name}.{current_object}" if _has_meaningful_value(table_name) else current_object,
            "TIPUS": "COLUMN NUMBER",
            "DADA TÈCNICA": _compact_parts([
                "Sense precisió ni escala",
                f"Nullable: {nullable}" if _has_meaningful_value(nullable) else "",
                f"Posició: {position}" if _has_meaningful_value(position) else "",
                f"DDL: {ddl}" if _has_meaningful_value(ddl) else "",
            ]),
        }

    if normalized_check == "CHECK_09":
        owner_target = _read_row_value(row, ["propietari_desti"]) or ""
        target_object = _read_row_value(row, ["objecte_desti"]) or ""
        ddl = _read_row_value(row, ["data_modificacio_sinonim"]) or ""
        return {
            "OBJECTE": current_object,
            "TIPUS": "SYNONYM",
            "DADA TÈCNICA": _compact_parts([
                "Destí inexistent",
                f"Objecte destí: {owner_target}.{target_object}" if _has_meaningful_value(owner_target) and _has_meaningful_value(target_object) else "",
                f"DDL: {ddl}" if _has_meaningful_value(ddl) else "",
            ]),
        }

    if normalized_check == "CHECK_10":
        line = _read_row_value(row, ["linia"]) or ""
        code = _read_row_value(row, ["codi"]) or ""
        modified = _read_row_value(row, ["data_modificacio_objecte"]) or ""
        return {
            "OBJECTE": current_object,
            "TIPUS": current_type or "PL/SQL",
            "DADA TÈCNICA": _compact_parts([
                "WHEN OTHERS THEN NULL",
                f"Línia {line}" if _has_meaningful_value(line) else "",
                f"Darrera modificació: {modified}" if _has_meaningful_value(modified) else "",
            ]),
            "OBSERVACIÓ": code if _has_meaningful_value(code) else None,
        }

    if normalized_check == "CHECK_11":
        problem_type = _read_row_value(row, ["tipus_problema"]) or ""
        line = _read_row_value(row, ["linia"]) or ""
        code = _read_row_value(row, ["codi"]) or ""
        modified = _read_row_value(row, ["data_modificacio_objecte"]) or ""
        return {
            "OBJECTE": current_object,
            "TIPUS": current_type or "PL/SQL",
            "DADA TÈCNICA": _compact_parts([
                problem_type,
                f"Línia {line}" if _has_meaningful_value(line) else "",
                f"Darrera modificació: {modified}" if _has_meaningful_value(modified) else "",
            ]),
            "OBSERVACIÓ": code if _has_meaningful_value(code) else None,
        }

    if normalized_check in {"CHECK_12", "CHECK_13"}:
        recommendation = _read_row_value(row, ["recomanacio", "recomendacion"]) or ""
        te_bulk = _read_row_value(row, ["te_bulk"]) or ""
        modified = _read_row_value(row, ["data_modificacio", "data_modificacio_objecte"]) or ""
        return {
            "OBJECTE": current_object,
            "TIPUS": current_type or "PL/SQL",
            "DADA TÈCNICA": _compact_parts([
                recommendation,
                f"TE_BULK: {te_bulk}" if _has_meaningful_value(te_bulk) else "",
                f"Darrera modificació: {modified}" if _has_meaningful_value(modified) else "",
            ]),
        }

    generic_parts = []
    for candidate in ["observacio", "descripcio", "problema", "data_modificacio_objecte", "data_modificacio_taula"]:
        value = _read_row_value(row, [candidate]) or ""
        if _has_meaningful_value(value):
            generic_parts.append(value)
    return {
        "OBJECTE": current_object,
        "TIPUS": current_type or "-",
        "DADA TÈCNICA": _compact_parts(generic_parts) or "Sense detall tècnic resumit.",
    }


def _row_evidence(row: Dict[str, Any]) -> Dict[str, Any]:
    evidence: Dict[str, Any] = {}
    for key in row:
        normalized = _normalize_key(key)
        if normalized in {
            "linia",
            "linies_sospitoses_en_loop",
            "linies_detall",
            "observacio",
            "codi",
            "data_modificacio_objecte",
            "data_modificacio_taula",
            "data_invalidacio",
            "classificacio_ia",
            "confianca_ia",
            "explicacio_ia",
            "recomanacio_ia",
            "estat_analisi_ia",
        }:
            evidence[key] = row.get(key)
    return evidence


def _dba_guidance_for_check(check_id: str) -> Dict[str, Any]:
    guidance = {
        "CHECK_03": {
            "technical_explanation": "La seqüència té cache inexistent o insuficient, cosa que incrementa el cost de generar nous valors en escenaris concurrents.",
            "functional_explanation": "L'objecte pot alentir insercions massives o processos batch que consumeixen identificadors de forma intensiva.",
            "impact_categories": ["rendiment", "risc de desplegament"],
            "recommended_fix": "Ajustar el valor de CACHE segons el volum real d'ús i validar si existeix justificació per mantenir un cache baix.",
            "post_validation": "Executar prova concurrent i revisar esperes o temps d'inserció després del canvi.",
        },
        "CHECK_04": {
            "technical_explanation": "S'ha detectat una foreign key sense índex de suport complet a la taula filla, fet que pot provocar bloquejos i scans innecessaris.",
            "functional_explanation": "El canvi pot degradar operacions de manteniment sobre la taula pare i bloquejar processos concurrents.",
            "impact_categories": ["rendiment", "robustesa operativa", "risc de desplegament"],
            "recommended_fix": "Crear o completar l'índex de suport considerant tota la definició de la foreign key.",
            "post_validation": "Validar esborrats o actualitzacions sobre la taula pare i confirmar que no apareixen locks amplis.",
        },
        "CHECK_11": {
            "technical_explanation": "S'han localitzat patrons PL/SQL amb COMMIT en LOOP, EXECUTE IMMEDIATE concatenat o DBMS_OUTPUT residual en codi recient.",
            "functional_explanation": "Aquests patrons barregen control transaccional, debug i construcció dinàmica de SQL, incrementant el risc operatiu i la dificultat de manteniment.",
            "impact_categories": ["mantenibilitat", "robustesa operativa", "risc de desplegament"],
            "recommended_fix": "Eliminar debug residual, evitar COMMIT dins de loops i substituir SQL dinàmic concatenat per SQL parametritzat o justificat.",
            "post_validation": "Executar prova funcional del paquet/procediment i revisar que el comportament transaccional no canvia.",
        },
        "CHECK_12": {
            "technical_explanation": "El codi conté operacions SQL dins de bucles PL/SQL sense evidència clara de BULK COLLECT o FORALL, indicant possible processament fila a fila.",
            "functional_explanation": "Aquesta implementació pot ser acceptable amb poca cardinalitat, però es converteix en un coll d'ampolla quan augmenta el volum de registres.",
            "impact_categories": ["rendiment", "mantenibilitat", "risc de desplegament"],
            "recommended_fix": "Analitzar cardinalitat real i substituir el patró per tractament bulk quan el flux sigui massiu.",
            "post_validation": "Comparar temps, lectures lògiques i CPU abans i després del refactor bulk.",
        },
    }
    return guidance.get(
        check_id,
        {
            "technical_explanation": "La troballa incompleix un patró de qualitat Oracle definit per l'auditoria post-CRQ.",
            "functional_explanation": "Cal revisar el canvi perquè la incidència pot afectar estabilitat, manteniment o rendiment segons el context.",
            "impact_categories": ["mantenibilitat"],
            "recommended_fix": "Revisar el check amb criteri tècnic DBA i aplicar la correcció estructural adequada.",
            "post_validation": "Reexecutar el check i validar que la troballa desapareix sense regressions funcionals.",
        },
    )


def _dba_guidance_for_check_v2(check_id: str, title: str) -> Dict[str, Any]:
    catalog = load_check_explanation_catalog()
    current = catalog.get(check_id)
    if current:
        return {
            "technical_explanation": current["per_que_es_important"],
            "functional_explanation": current["impacte_sobre_lot"],
            "impact_categories": [current["per_que_es_important"]],
            "recommended_fix": current["com_corregir"],
            "review_steps": current["com_revisar"],
            "limitations": current["limitacions"],
            "post_validation": current["validacio_posterior"],
            "recommended_table_columns": current["columnes_taula_recomanades"],
        }

    return {
        "technical_explanation": "La troballa incompleix un patró de qualitat Oracle definit per l'auditoria post-CRQ.",
        "functional_explanation": "Cal revisar el canvi perquè la incidència pot afectar estabilitat, manteniment o rendiment segons el context.",
        "impact_categories": ["mantenibilitat"],
        "recommended_fix": "Revisar el check amb criteri tècnic DBA i aplicar la correcció estructural adequada.",
        "review_steps": "Validar el resultat del check i contrastar-lo amb el context funcional del desplegament.",
        "limitations": "La incidència s'ha d'interpretar conjuntament amb el context del lot i la naturalesa de l'objecte.",
        "post_validation": "Reexecutar el check i validar que la troballa desapareix sense regressions funcionals.",
        "recommended_table_columns": ["Lot", "Esquema", "Objecte", "Severitat", "Acció recomanada"],
    }


def _dba_guidance_for_check_v3(check_id: str, title: str) -> Dict[str, Any]:
    current = _catalog_entry_v2_normalized(check_id, title)
    return _normalize_guidance_entry(
        {
            "technical_explanation": current["per_que_es_important"],
            "functional_explanation": current["impacte_sobre_lot"],
            "impact_categories": [current["per_que_es_important"]],
            "recommended_fix": current["com_corregir"],
            "review_steps": current["com_revisar"],
            "limitations": current["limitacions"],
            "post_validation": current["validacio_posterior"],
            "recommended_table_columns": current.get("columnes_taula_recomanades") or ["Lot", "Esquema", "Objecte", "Severitat", "Acció recomanada"],
        }
    )


def _build_dba_enrichment(check_result: Dict[str, Any], row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    check_id = str(check_result.get("check_id") or "").strip().upper()
    guidance = _dba_guidance_for_check_v3(check_id, str(check_result.get("title") or check_id))
    sql_diagnostic: Dict[str, Any] = {"status": "finding"}
    if check_result.get("status") != "ok":
        sql_diagnostic = _oracle_error_diagnostic(
            str(check_result.get("error") or ""),
            str(check_result.get("executed_sql") or ""),
        )

    schema = _resolve_schema_value(row, None)
    object_name = _pick_value(
        row or {},
        ["objecte_plsql", "objecte", "taula", "sequencia", "sinonim", "constraint_fk", "constraint_name"],
    )
    object_type = _pick_value(row or {}, ["tipus_objecte", "tipus"])
    priority = _criticality_key(check_result.get("criticitat_key") or check_result.get("criticitat") or check_result.get("severitat"))

    enrichment = {
        "check_id": check_id,
        "object_key": {
            "schema": schema,
            "object_name": object_name,
            "object_type": object_type,
        },
        "sql_diagnostic": sql_diagnostic,
        "resum_operatiu": guidance["technical_explanation"],
        "technical_explanation": guidance["technical_explanation"],
        "functional_explanation": guidance["functional_explanation"],
        "impact": {
            "priority": priority,
            "categories": guidance["impact_categories"],
        },
        "recommended_fix": guidance["recommended_fix"],
        "review_steps": guidance["review_steps"],
        "limitations": guidance["limitations"],
        "post_validation": guidance["post_validation"],
        "recommended_table_columns": guidance["recommended_table_columns"],
    }
    if row:
        ai_summary = {
            "classificacio_ia": row.get("CLASSIFICACIO_IA") or row.get("classificacio_ia"),
            "confianca_ia": row.get("CONFIANCA_IA") or row.get("confianca_ia"),
            "explicacio_ia": row.get("EXPLICACIO_IA") or row.get("explicacio_ia"),
            "recomanacio_ia": row.get("RECOMANACIO_IA") or row.get("recomanacio_ia"),
            "estat_analisi_ia": row.get("ESTAT_ANALISI_IA") or row.get("estat_analisi_ia"),
        }
        if any(value not in (None, "") for value in ai_summary.values()):
            enrichment["ai_analysis"] = ai_summary
    return enrichment


def build_finding_envelopes(
    executed_checks: List[Dict[str, Any]],
    *,
    context: ExecutionContext,
    ownership_db_path: Optional[str],
) -> List[FindingEnvelope]:
    findings: List[FindingEnvelope] = []
    for check_result in executed_checks:
        rows = check_result.get("rows") or []
        if check_result.get("status") != "ok":
            dba_enrichment = _build_dba_enrichment(check_result)
            findings.append(
                {
                    "finding_id": f"{check_result['check_id']}:ERROR",
                    "check_id": check_result["check_id"],
                    "title": str(check_result.get("title") or ""),
                    "schema": None,
                    "object_name": None,
                    "object_type": None,
                    "sql_severity": str(check_result.get("severitat_original") or check_result.get("severitat") or ""),
                    "runtime_status": "error",
                    "evidence": {
                        "error": check_result.get("error"),
                        "executed_sql": check_result.get("executed_sql"),
                    },
                    "dba_enrichment": dba_enrichment,
                    "lot_assignment": resolve_ownership("", mapping={}, db_path=ownership_db_path),
                    "final_criticality": _criticality_key(check_result.get("criticitat_key")),
                    "final_criticality_label": _criticality_label(check_result.get("criticitat_key")),
                    "row_index": -1,
                }
            )
            continue

        for index, row in enumerate(rows):
            schema = _resolve_schema_value(row, context)
            object_name = _pick_value(
                row,
                ["objecte_plsql", "objecte", "taula", "tabla", "nom_taula", "sequencia", "sinonim", "constraint_fk", "constraint_name"],
            )
            object_type = _pick_value(row, ["tipus_objecte", "tipus"])
            dba_enrichment = _build_dba_enrichment(check_result, row)
            lot_assignment = resolve_ownership(schema or "", object_name, db_path=ownership_db_path)
            incident_table_entry = _build_incident_table_entry(check_result["check_id"], row, schema, object_name, object_type)
            findings.append(
                {
                    "finding_id": f"{check_result['check_id']}:{index}",
                    "check_id": check_result["check_id"],
                    "title": str(check_result.get("title") or ""),
                    "schema": schema,
                    "object_name": object_name,
                    "object_type": object_type,
                    "sql_severity": str(
                        row.get("SEVERITAT_SQL")
                        or row.get("SEVERITAT")
                        or check_result.get("severitat_original")
                        or check_result.get("severitat")
                        or ""
                    ),
                    "runtime_status": "ok",
                    "evidence": _row_evidence(row),
                    "dba_enrichment": dba_enrichment,
                    "lot_assignment": lot_assignment,
                    "final_criticality": _criticality_key(check_result.get("criticitat_key")),
                    "final_criticality_label": _criticality_label(check_result.get("criticitat_key")),
                    "row_index": index,
                    "source_row": dict(row),
                    "incident_table_entry": incident_table_entry,
                }
            )
    return findings


def _summarize_group(findings: List[FindingEnvelope], criticality_key: str) -> str:
    if not findings:
        return ""
    check_id = findings[0]["check_id"]
    title = findings[0]["title"]
    schemas = sorted({finding.get("schema") for finding in findings if finding.get("schema")})
    objects = [finding.get("object_name") for finding in findings if finding.get("object_name")][:3]
    schema_text = ", ".join(schemas) if schemas else "diversos esquemes"
    count = len(findings)

    templates = {
        "CHECK_11": (
            f"S'han detectat {count} incidències de codi PL/SQL als esquemes {schema_text}, incloent control transaccional insegur (COMMIT en loop) o debug residual (DBMS_OUTPUT). "
            f"Cal prioritzar la revisió de {', '.join(objects) if objects else 'els objectes afectats'}."
        ),
        "CHECK_12": (
            f"S'han detectat {count} objectes PL/SQL dels esquemes {schema_text} amb patrons de processament fila a fila o N+1. "
            f"Cal revisar {', '.join(objects) if objects else 'els objectes afectats'} per implementar BULK COLLECT o FORALL i millorar el rendiment."
        ),
        "CHECK_04": (
            f"S'han detectat {count} foreign keys recents sense índex de suport als esquemes {schema_text}. "
            f"Això pot provocar bloquejos i degradació DML si el canvi passa a entorns superiors."
        ),
        "CHECK_03": (
            f"S'han detectat {count} seqüències amb cache inexistent o insuficient als esquemes {schema_text}. "
            f"Això penalitza processos d'inserció concurrents i s'ha de revisar amb urgència."
        ),
    }
    base = templates.get(
        check_id,
        f"S'han detectat {count} incidències del {check_id} als esquemes {schema_text}. Cal revisar {title.lower()} i aplicar la correcció estructural recomanada.",
    )
    action = CRITICALITY_ACTIONS.get(criticality_key, CRITICALITY_ACTIONS["BAIX"])
    return f"{base}\n\n{action}"


def _summarize_group_institutional(findings: List[FindingEnvelope], criticality_key: str) -> str:
    if not findings:
        return ""
    check_id = findings[0]["check_id"]
    title = findings[0]["title"]
    schemas = sorted({finding.get("schema") for finding in findings if finding.get("schema")})
    objects = [finding.get("object_name") for finding in findings if finding.get("object_name")][:3]
    schema_text = ", ".join(schemas) if schemas else "diversos esquemes"
    count = len(findings)

    templates = {
        "CHECK_11": (
            f"S'han detectat {count} incidències de codi PL/SQL als esquemes {schema_text}, incloent control transaccional insegur (COMMIT dins d'un bucle) o codi de depuració residual (DBMS_OUTPUT). "
            f"Cal prioritzar la revisió de {', '.join(objects) if objects else 'els objectes afectats'}."
        ),
        "CHECK_12": (
            f"S'han detectat {count} objectes PL/SQL dels esquemes {schema_text} amb patrons de processament fila a fila o N+1. "
            f"Cal revisar {', '.join(objects) if objects else 'els objectes afectats'} per implementar BULK COLLECT o FORALL i millorar el rendiment."
        ),
        "CHECK_04": (
            f"S'han detectat {count} claus foranes recents sense índex de suport als esquemes {schema_text}. "
            f"Això pot provocar bloquejos i degradació DML si el canvi passa a entorns superiors."
        ),
        "CHECK_03": (
            f"S'han detectat {count} seqüències amb cache inexistent o insuficient als esquemes {schema_text}. "
            f"Això penalitza processos d'inserció concurrents i s'ha de revisar amb urgència."
        ),
    }
    base = templates.get(
        check_id,
        f"S'han detectat {count} incidències del {check_id} als esquemes {schema_text}. Cal revisar {_normalize_institutional_text(title).lower()} i aplicar la correcció recomanada.",
    )
    action = CRITICALITY_ACTIONS.get(criticality_key, CRITICALITY_ACTIONS["BAIX"])
    return _normalize_institutional_text(f"{base}\n\n{action}")


def _build_block_items(findings: List[FindingEnvelope], criticality_key: str) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[FindingEnvelope]] = {}
    for finding in findings:
        grouped.setdefault(finding["check_id"], []).append(finding)

    items: List[Dict[str, Any]] = []
    for check_id, current_findings in sorted(grouped.items(), key=lambda item: item[0]):
        first = current_findings[0]
        items.append(
            {
                "check_id": check_id,
                "title": first["title"],
                "criticality_key": criticality_key,
                "criticality_label": _criticality_label(criticality_key),
                "summary_text": _summarize_group_institutional(current_findings, criticality_key),
                "finding_count": len(current_findings),
                "schemas": sorted({finding.get("schema") for finding in current_findings if finding.get("schema")}),
                "top_examples": [
                    {
                        "schema": finding.get("schema"),
                        "object_name": finding.get("object_name"),
                        "lot": (finding.get("lot_assignment") or {}).get("lot"),
                        "responsable": (finding.get("lot_assignment") or {}).get("responsable"),
                    }
                    for finding in current_findings[:3]
                ],
                "status": "error" if any(f.get("runtime_status") != "ok" for f in current_findings) else "ok",
            }
        )
    return items


def build_report_model(
    context: ExecutionContext,
    plan: ExecutionPlan,
    executed_checks: List[Dict[str, Any]],
    finding_envelopes: List[FindingEnvelope],
) -> Dict[str, Any]:
    findings_by_criticality: Dict[str, List[FindingEnvelope]] = {key: [] for key in CRITICALITY_ORDER}
    for finding in finding_envelopes:
        findings_by_criticality[_criticality_key(finding.get("final_criticality"))].append(finding)

    criticality_blocks = []
    for criticality_key in CRITICALITY_ORDER:
        current_findings = findings_by_criticality[criticality_key]
        criticality_blocks.append(
            {
                "criticality_key": criticality_key,
                "criticality_label": _criticality_label(criticality_key),
                "action_text": CRITICALITY_ACTIONS[criticality_key],
                "total_findings": len(current_findings),
                "items": _build_block_items(current_findings, criticality_key),
            }
        )

    critical_incident_cards = []
    for finding in findings_by_criticality["CRITIC"]:
        lot_assignment = finding.get("lot_assignment") or {}
        dba_enrichment = finding.get("dba_enrichment") or {}
        sql_diagnostic = dba_enrichment.get("sql_diagnostic") or {}
        evidence = finding.get("evidence") or {}
        critical_incident_cards.append(
            {
                "check_id": finding["check_id"],
                "title": finding["title"],
                "severity": finding["sql_severity"],
                "schema": finding.get("schema") or "No disponible",
                "object_name": finding.get("object_name") or "No disponible",
                "object_type": finding.get("object_type") or "No disponible",
                "lot": lot_assignment.get("lot") or "SENSE LOT",
                "responsable": lot_assignment.get("responsable") or "No assignat",
                "summary_text": dba_enrichment.get("functional_explanation") or "Incidència crítica que requereix revisió immediata.",
                "technical_explanation": dba_enrichment.get("technical_explanation") or "Diagnòstic tècnic no disponible.",
                "evidence_text": evidence.get("observacio") or evidence.get("codi") or evidence.get("linies_detall") or sql_diagnostic.get("oracle_error_summary") or "Sense evidència textual resumida.",
                "impact_text": ", ".join((dba_enrichment.get("impact") or {}).get("categories") or []),
                "recommended_action": dba_enrichment.get("recommended_fix") or "Revisar i corregir la incidència abans del següent pas d'entorn.",
                "post_validation": dba_enrichment.get("post_validation") or "Reexecutar el check després de la correcció.",
                "priority": _criticality_label(finding.get("final_criticality")),
                "oracle_error_code": sql_diagnostic.get("oracle_error_code"),
                "oracle_error_summary": sql_diagnostic.get("oracle_error_summary"),
            }
        )

    detail_sections = []
    by_check: Dict[str, List[FindingEnvelope]] = {}
    for finding in finding_envelopes:
        by_check.setdefault(finding["check_id"], []).append(finding)

    for check_result in executed_checks:
        current_findings = by_check.get(check_result["check_id"], [])
        detail_sections.append(
            {
                "check_id": check_result["check_id"],
                "title": check_result["title"],
                "status": check_result.get("status"),
                "criticality": _criticality_label(check_result.get("criticitat_key")),
                "overview": _summarize_group_institutional(current_findings, _criticality_key(check_result.get("criticitat_key"))) if current_findings else "",
                "finding_count": len(current_findings),
                "rows": check_result.get("rows") or [],
                "columns": check_result.get("columns") or [],
            }
        )

    encoding_issues = []
    for marker in MALFORMED_TEXT_MARKERS:
        if marker in str(criticality_blocks) or marker in str(critical_incident_cards):
            encoding_issues.append(marker)

    quality_gate = {
        "status": "ok" if not encoding_issues else "warning",
        "issues": [f"mojibake_detectat:{marker}" for marker in encoding_issues],
        "critical_without_lot": sum(1 for card in critical_incident_cards if card.get("lot") == "SENSE LOT"),
    }

    return {
        "agent_runtime": {
            "orchestrator": "orchestrator-e13bd",
            "architect": "architect-e13bd",
            "developer": "developer-e13bd",
            "tester": "tester-e13bd",
            "dba": "dba-e13bd",
            "reporting": "insights-reporting-e13bd",
            "phases": plan["phases"],
        },
        "criticality_blocks": criticality_blocks,
        "critical_incident_cards": critical_incident_cards,
        "detail_sections": detail_sections,
        "quality_gate": quality_gate,
        "time_window": _resolve_time_window(context["time_filter"]),
    }


def apply_ownership_to_check_rows(
    executed_checks: List[Dict[str, Any]],
    finding_envelopes: List[FindingEnvelope],
) -> List[Dict[str, Any]]:
    finding_lookup = {
        (finding["check_id"], finding["row_index"]): finding
        for finding in finding_envelopes
        if finding.get("row_index", -1) >= 0
    }
    for check in executed_checks:
        if check.get("status") != "ok":
            continue
        columns = list(check.get("columns") or [])
        if "Lot" not in columns:
            columns.append("Lot")
        if "Responsable" not in columns:
            columns.append("Responsable")
        check["columns"] = columns
        new_rows = []
        for index, row in enumerate(check.get("rows") or []):
            current = dict(row)
            finding = finding_lookup.get((check["check_id"], index))
            lot_assignment = (finding or {}).get("lot_assignment") or {}
            current["Lot"] = lot_assignment.get("lot") or "SENSE LOT"
            current["Responsable"] = lot_assignment.get("responsable") or "No assignat"
            new_rows.append(current)
        check["rows"] = new_rows
    return executed_checks


def _catalog_entry_v2(check_id: str, title: str) -> Dict[str, Any]:
    catalog = load_check_explanation_catalog()
    return catalog.get(check_id) or {
        "check_id": check_id,
        "title": title,
        "que_detecta": (
            "Aquest control detecta una anomalia tècnica estructural en el model de dades o el codi PL/SQL "
            "que s'ha introduït recentment.\nL'eina analitza el diccionari Oracle per identificar patrons "
            "que no compleixen els estàndards de qualitat establerts per l'ATIC."
        ),
        "per_que_es_important": (
            "Mantenir el compliment dels estàndards és vital per garantir l'escalabilitat del sistema.\n"
            "Una desviació en aquest punt pot provocar un degradament progressiu del rendiment global,\n"
            "augmentant els temps de resposta i dificultant el manteniment futur del producte."
        ),
        "impacte_sobre_lot": (
            "El lot afectat ha de detenir la promoció d'aquest canvi fins que es revisi detingudament.\n"
            "L'impacte directe es tradueix en un risc d'inestabilitat en l'entorn de producció i possibles\n"
            "bloquejos transaccionals si la incidència no es corregeix abans del tancament del CRQ."
        ),
        "com_revisar": (
            "Cal extreure el detall tècnic de la troballa mitjançant el SQL Explorer de l'aplicació.\n"
            "Es recomana contrastar l'objecte afectat amb la versió anterior del codi per aïllar el canvi\n"
            "i validar si la troballa és un deute tècnic justificat o una mala praxis accidental."
        ),
        "com_corregir": (
            "S'ha d'aplicar la correcció estructural seguint les recomanacions de l'arquitectura Oracle.\n"
            "Això sol implicar un refactor del codi, la creació d'índexs de suport o el canvi de tipus de dades,\n"
            "assegurant sempre que la nova versió compleixi el check de control de qualitat al 100%."
        ),
        "validacio_posterior": (
            "Un cop aplicada la correcció, s'ha de tornar a executar aquesta auditoria post-CRQ.\n"
            "S'ha de verificar que el recompte de files per a aquest check sigui zero (0) i que\n"
            "no s'hagin introduït regressions en altres objectes vinculats durant el procés de fix."
        ),
        "limitacions": "Sense limitacions documentades per a aquest check genèric.",
    }


def _catalog_entry_v2_normalized(check_id: str, title: str) -> Dict[str, Any]:
    catalog = load_check_explanation_catalog()
    if check_id in catalog:
        return _normalize_catalog_entry(catalog[check_id])
    return _normalize_catalog_entry(
        {
            "check_id": check_id,
            "title": _normalize_institutional_text(title),
            "que_detecta": (
                "Aquest control detecta una desviació tècnica introduïda recentment en objectes Oracle o en codi PL/SQL.\n"
                "L'auditoria analitza el diccionari Oracle i els objectes modificats per identificar patrons que no compleixen els criteris de qualitat establerts."
            ),
            "per_que_es_important": (
                "Mantenir aquests criteris és essencial per preservar la integritat, el rendiment i la mantenibilitat del sistema.\n"
                "Si no es corregeix, la incidència pot arribar a entorns superiors i generar regressions o costos addicionals de suport."
            ),
            "impacte_sobre_lot": (
                "El lot afectat ha de revisar la incidència abans de promoure el canvi.\n"
                "L'impacte pot traduir-se en risc operatiu, degradació del rendiment o inestabilitat si no es corregeix abans del tancament del CRQ."
            ),
            "com_revisar": (
                "Cal extreure el detall tècnic de la troballa i contrastar-lo amb la versió anterior de l'objecte afectat.\n"
                "També s'ha de verificar si el patró detectat respon a un canvi justificat o a una desviació que s'ha de corregir."
            ),
            "com_corregir": (
                "S'ha d'aplicar la correcció estructural d'acord amb les recomanacions d'arquitectura Oracle.\n"
                "Segons el cas, això pot implicar refactorar el codi, crear índexs de suport, revalidar constraints o ajustar la definició de dades."
            ),
            "validacio_posterior": (
                "Un cop aplicada la correcció, cal tornar a executar el check o l'auditoria post-CRQ corresponent.\n"
                "S'ha de verificar que la incidència deixa d'aparèixer i que no s'han introduït regressions en objectes relacionats."
            ),
            "limitacions": "Sense limitacions documentades per a aquest check genèric.",
        }
    )


def _sql_severity_key_v2(value: Any) -> str:
    normalized = _normalize_key(value)
    if normalized in {"critic", "critical", "stopper"}:
        return "CRITIC"
    if normalized == "alt":
        return "ALT"
    if normalized in {"mitja", "medium"}:
        return "MITJA"
    if normalized in {"baix", "low"}:
        return "BAIX"
    return "INFO"


def _should_expose_responsable_v2(value: Any) -> bool:
    return _normalize_key(value) not in {"", "no_informat", "no_assignat"}


def _build_lot_summary_v2(findings: List[FindingEnvelope]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for finding in findings:
        if not _has_assignable_schema(finding):
            continue
        lot_assignment = finding.get("lot_assignment") or {}
        lot = str(lot_assignment.get("lot") or "SENSE LOT").strip() or "SENSE LOT"
        current = grouped.setdefault(
            lot,
            {
                "lot": lot,
                "responsable": lot_assignment.get("responsable") if _should_expose_responsable_v2(lot_assignment.get("responsable")) else None,
                "critical": 0,
                "medium": 0,
                "low": 0,
                "checks": set(),
                "check_titles": {},
                "schemas": set(),
                "affected_objects": set(),
                "first_action": "",
                "dominant_impact": "",
                "priority": "Baix",
                "risk_index": 0,
            },
        )
        current["checks"].add(finding["check_id"])
        current["check_titles"][finding["check_id"]] = finding.get("title") or finding["check_id"]
        if finding.get("schema"):
            current["schemas"].add(finding["schema"])
        if finding.get("object_name"):
            current["affected_objects"].add(finding["object_name"])

        criticality_key = _criticality_key(finding.get("final_criticality"))
        if criticality_key == "CRITIC":
            current["critical"] += 1
            current["priority"] = "Crític"
            current["risk_index"] += 10
        elif criticality_key == "MITJA":
            current["medium"] += 1
            current["risk_index"] += 4
            if current["priority"] != "Crític":
                current["priority"] = "Mitjà"
        else:
            current["low"] += 1
            current["risk_index"] += 1

        enrichment = finding.get("dba_enrichment") or {}
        if not current["first_action"]:
            current["first_action"] = enrichment.get("recommended_fix") or "Revisar la incidència i aplicar la correcció estructural recomanada."
        if not current["dominant_impact"]:
            current["dominant_impact"] = enrichment.get("functional_explanation") or "Impacte pendent de concretar amb el detall tècnic."

    return [
        {
            **value,
            "checks": sorted(value["checks"]),
            "check_descriptions": [
                {"check_id": check_id, "title": value["check_titles"].get(check_id) or check_id}
                for check_id in sorted(value["checks"])
            ],
            "schemas": sorted(value["schemas"]),
            "affected_objects": len(value["affected_objects"]),
            "risk_label": "EXTREM" if value["risk_index"] >= 50 else "ALT" if value["risk_index"] >= 20 else "MITJÀ" if value["risk_index"] >= 10 else "BAIX",
        }
        for _, value in sorted(
            grouped.items(), 
            key=lambda item: (
                -item[1]["risk_index"],
                item[0]
            )
        )
    ]


def _build_lot_incident_groups_v2(findings: List[FindingEnvelope]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[str, str], Dict[str, Any]] = {}
    for finding in findings:
        if not _has_assignable_schema(finding):
            continue
        lot_assignment = finding.get("lot_assignment") or {}
        lot = str(lot_assignment.get("lot") or "SENSE LOT").strip() or "SENSE LOT"
        check_id = finding["check_id"]
        key = (lot, check_id)
        catalog_entry = _catalog_entry_v2_normalized(check_id, finding.get("title") or check_id)
        current = grouped.setdefault(
            key,
            {
                "lot": lot,
                "check": check_id,
                "title": finding.get("title") or check_id,
                "description": catalog_entry["que_detecta"],
                "severity": finding.get("final_criticality_label") or _criticality_label(finding.get("final_criticality")),
                "termini_dies": 0 if _criticality_key(finding.get("final_criticality")) == "CRITIC" else 15 if _criticality_key(finding.get("final_criticality")) == "MITJA" else 30,
                "impacte": catalog_entry["impacte_sobre_lot"],
                "accio_recomanada": (finding.get("dba_enrichment") or {}).get("recommended_fix") or catalog_entry["com_corregir"],
                "validacio_posterior": (finding.get("dba_enrichment") or {}).get("post_validation") or catalog_entry["validacio_posterior"],
                "limitacions": catalog_entry["limitacions"],
                "schemas": {},
            },
        )
        schema = finding.get("schema")
        table_entry = dict(finding.get("incident_table_entry") or {})
        schema_group = current["schemas"].setdefault(
            schema,
            {
                "nom": schema,
                "objectes": [],
            },
        )
        if not table_entry:
            table_entry = {
                "OBJECTE": finding.get("object_name") or finding.get("object_type") or finding.get("table_name") or "-",
                "TIPUS": finding.get("object_type") or "-",
                "DADA TÈCNICA": "Sense detall tècnic resumit.",
            }
        schema_group["objectes"].append(table_entry)

    rows: List[Dict[str, Any]] = []
    for _, current in sorted(
        grouped.items(), 
        key=lambda item: (
            item[0][0], # Lot
            _criticality_rank(item[1].get("severity")), # Severity rank
            item[0][1]  # Check ID
        )
    ):
        rows.append(
            {
                **current,
                "schemas": [
                    {
                        "nom": schema_name,
                        "object_count": len(schema_group["objectes"]),
                        "objectes": schema_group["objectes"],
                    }
                    for schema_name, schema_group in sorted(current["schemas"].items(), key=lambda item: item[0])
                ],
            }
        )
    return rows


def _build_critical_grouped_v2(findings: List[FindingEnvelope]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[FindingEnvelope]] = {}
    for finding in findings:
        grouped.setdefault(finding["check_id"], []).append(finding)

    cards: List[Dict[str, Any]] = []
    for check_id, current_findings in sorted(grouped.items(), key=lambda item: item[0]):
        first = current_findings[0]
        catalog_entry = _catalog_entry_v2_normalized(check_id, first["title"])
        lot_rows = []
        lot_groups: Dict[str, Dict[str, Any]] = {}
        for finding in current_findings:
            if not _has_assignable_schema(finding):
                continue
            lot_assignment = finding.get("lot_assignment") or {}
            dba = finding.get("dba_enrichment") or {}
            lot = str(lot_assignment.get("lot") or "SENSE LOT").strip() or "SENSE LOT"
            schema = finding.get("schema")
            object_name = finding.get("object_name") or finding.get("object_type") or finding.get("table_name") or "-"
            severity = finding.get("sql_severity") or "N/A"
            incident_entry = dict(finding.get("incident_table_entry") or {})
            object_label = incident_entry.get("OBJECTE") or object_name
            object_type = incident_entry.get("TIPUS") or finding.get("object_type") or "-"
            technical_value = (
                incident_entry.get("DADA TÈCNICA")
                or incident_entry.get("DADA TECNICA")
                or "-"
            )
            observation = incident_entry.get("OBSERVACIÓ") or incident_entry.get("OBSERVACIO") or ""
            lot_rows.append(
                {
                    "lot": lot,
                    "esquema": schema,
                    "objecte": object_label,
                    "tipus": object_type,
                    "dada_tecnica": technical_value,
                    "observacio": observation,
                    "accio_recomanada": dba.get("recommended_fix") or catalog_entry.get("com_corregir") or "Aplicar la correcció estructural recomanada.",
                }
            )
            current_lot = lot_groups.setdefault(
                lot,
                {
                    "lot": lot,
                    "check": check_id,
                    "severitat": severity,
                    "termini_dies": 0 if _sql_severity_key_v2(severity) == "CRITIC" else 15 if _sql_severity_key_v2(severity) in {"ALT", "MITJA"} else 30,
                    "esquemes": {},
                },
            )
            schema_group = current_lot["esquemes"].setdefault(schema, [])
            if object_label not in schema_group:
                schema_group.append(object_label)

        if not lot_rows:
            continue

        cards.append(
            {
                "check_id": check_id,
                "title": first["title"],
                "summary_text": catalog_entry["que_detecta"],
                "impact_text": catalog_entry["impacte_sobre_lot"],
                "urgency_label": "URGENT",
                "recommended_action": catalog_entry["com_corregir"],
                "review_steps": catalog_entry["com_revisar"],
                "post_validation": catalog_entry["validacio_posterior"],
                "limitations": catalog_entry["limitacions"],
                "finding_count": len(current_findings),
                "schemas": sorted({finding.get("schema") for finding in current_findings if finding.get("schema")}),
                "sql_severity": first.get("sql_severity") or "N/A",
                "lot_rows": lot_rows,
                "lot_groups": [
                    {
                        "lot": lot_value["lot"],
                        "check": lot_value["check"],
                        "severitat": lot_value["severitat"],
                        "termini_dies": lot_value["termini_dies"],
                        "esquemes": [
                            {"nom": schema_name, "objectes": sorted(objectes)}
                            for schema_name, objectes in sorted(lot_value["esquemes"].items(), key=lambda item: item[0])
                        ],
                    }
                    for _, lot_value in sorted(lot_groups.items(), key=lambda item: item[0])
                ],
                "top_examples": lot_rows[:3],
            }
        )
    return cards


def _build_execution_parameters_v2(context: ExecutionContext, executed_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "profile": context["profile"],
        "generated_at": context["generated_at"],
        "time_window": _resolve_time_window(context["time_filter"]),
        "time_filter_label": context["time_filter"].get("preset") or f"{context['time_filter'].get('start_date') or ''} -> {context['time_filter'].get('end_date') or ''}",
        "language": "Català",
        "encoding": "UTF-8",
        "source_file": context["source_file"],
        "source_path": context["source_path"],
        "enabled_checks": [
            {
                "check_id": item["check_id"],
                "title": item.get("title"),
                "criticality": _criticality_label(item.get("criticitat_key")),
                "description": _catalog_entry_v2_normalized(item["check_id"], item.get("title") or "")["que_detecta"]
            }
            for item in executed_checks
        ],
        "schemas": list(context["schemas"] or []),
    }


def build_report_model_v2(
    context: ExecutionContext,
    plan: ExecutionPlan,
    executed_checks: List[Dict[str, Any]],
    finding_envelopes: List[FindingEnvelope],
) -> Dict[str, Any]:
    findings_by_criticality: Dict[str, List[FindingEnvelope]] = {key: [] for key in CRITICALITY_ORDER}
    for finding in finding_envelopes:
        findings_by_criticality[_criticality_key(finding.get("final_criticality"))].append(finding)

    criticality_blocks = []
    for criticality_key in CRITICALITY_ORDER:
        current_findings = findings_by_criticality[criticality_key]
        grouped: Dict[str, List[FindingEnvelope]] = {}
        for finding in current_findings:
            grouped.setdefault(finding["check_id"], []).append(finding)

        items = []
        for check_id, grouped_findings in sorted(grouped.items(), key=lambda item: item[0]):
            catalog_entry = _catalog_entry_v2_normalized(check_id, grouped_findings[0]["title"])
            items.append(
                {
                    "check_id": check_id,
                    "title": grouped_findings[0]["title"],
                    "criticality_key": criticality_key,
                    "criticality_label": _criticality_label(criticality_key),
                    "summary_text": catalog_entry["que_detecta"],
                    "finding_count": len(grouped_findings),
                    "schemas": sorted({finding.get("schema") for finding in grouped_findings if finding.get("schema")}),
                    "top_examples": [
                        {
                            "lot": (finding.get("lot_assignment") or {}).get("lot") or "SENSE LOT",
                            "schema": finding.get("schema") or "No disponible",
                            "object_name": finding.get("object_name") or "No disponible",
                        }
                        for finding in grouped_findings[:3]
                    ],
                    "status": "error" if any(f.get("runtime_status") != "ok" for f in grouped_findings) else "ok",
                }
            )

        criticality_blocks.append(
            {
                "criticality_key": criticality_key,
                "criticality_label": _criticality_label(criticality_key),
                "action_text": CRITICALITY_ACTIONS[criticality_key],
                "total_findings": len(current_findings),
                "items": items,
            }
        )

    detail_sections = []
    by_check: Dict[str, List[FindingEnvelope]] = {}
    for finding in finding_envelopes:
        by_check.setdefault(finding["check_id"], []).append(finding)

    for check_result in executed_checks:
        current_findings = by_check.get(check_result["check_id"], [])
        catalog_entry = _catalog_entry_v2_normalized(check_result["check_id"], str(check_result.get("title") or ""))
        detail_sections.append(
            {
                "check_id": check_result["check_id"],
                "title": check_result["title"],
                "status": check_result.get("status"),
                "criticality": _criticality_label(check_result.get("criticitat_key")),
                "overview": catalog_entry["que_detecta"],
                "why_it_matters": catalog_entry["per_que_es_important"],
                "finding_count": len(current_findings),
                "duration_ms": check_result.get("duration_ms") or 0,
                "rows": check_result.get("rows") or [],
                "columns": check_result.get("columns") or [],
            }
        )

    critical_checks_grouped = _build_critical_grouped_v2(findings_by_criticality["CRITIC"])
    lot_incident_groups = _build_lot_incident_groups_v2(finding_envelopes)
    execution_parameters = _build_execution_parameters_v2(context, executed_checks)
    lot_summary = _build_lot_summary_v2(finding_envelopes)
    findings_without_schema = sum(1 for finding in finding_envelopes if not _has_assignable_schema(finding))

    rendered_probe = str(execution_parameters) + str(lot_summary) + str(critical_checks_grouped)
    quality_gate = {
        "status": "ok" if not any(marker in rendered_probe for marker in MALFORMED_TEXT_MARKERS) else "warning",
        "issues": [f"mojibake_detectat:{marker}" for marker in MALFORMED_TEXT_MARKERS if marker in rendered_probe],
        "critical_without_lot": sum(1 for card in critical_checks_grouped for row in card.get("lot_rows") or [] if row.get("lot") == "SENSE LOT"),
        "findings_without_schema": findings_without_schema,
    }

    final_observations = {
        "blocking_errors": [
            {
                "check_id": item["check_id"],
                "error": item.get("error") or "Error Oracle no detallat.",
            }
            for item in executed_checks
            if item.get("status") == "error"
        ],
        "warnings": quality_gate["issues"] + (
            ["Existeixen incidències crítiques sense lot assignat."]
            if quality_gate["critical_without_lot"]
            else []
        ) + (
            [f"Hi ha {findings_without_schema} troballes sense esquema identificable. No s'inclouen al resum per lots fins que el check retorni l'esquema."]
            if findings_without_schema
            else []
        ),
        "next_steps": [
            "Prioritzar primer les incidències d'integritat i referencialitat que puguin admetre dades inconsistents, duplicades o òrfenes abans del següent pas d'entorn.",
            "Regularitzar després els objectes invàlids i confirmar-ne la compilació, execució o refresh segons el tipus d'objecte afectat.",
            "Planificar tot seguit la correcció dels riscos de rendiment, traçabilitat i mantenibilitat, i reexecutar només els checks afectats amb validació funcional o tècnica proporcional al risc.",
        ],
    }

    return {
        "agent_runtime": {
            "orchestrator": "orchestrator-e13bd",
            "architect": "architect-e13bd",
            "developer": "developer-e13bd",
            "tester": "tester-e13bd",
            "dba": "dba-e13bd",
            "reporting": "insights-reporting-e13bd",
            "phases": plan["phases"],
        },
        "execution_parameters": execution_parameters,
        "enabled_checks": execution_parameters["enabled_checks"],
        "lot_summary": lot_summary,
        "lot_incident_groups": lot_incident_groups,
        "criticality_blocks": criticality_blocks,
        "critical_checks_grouped": critical_checks_grouped,
        "critical_incident_cards": critical_checks_grouped,
        "detail_sections": detail_sections,
        "final_observations": final_observations,
        "quality_gate": quality_gate,
        "time_window": _resolve_time_window(context["time_filter"]),
    }


def apply_ownership_to_check_rows_v2(
    executed_checks: List[Dict[str, Any]],
    finding_envelopes: List[FindingEnvelope],
) -> List[Dict[str, Any]]:
    finding_lookup = {
        (finding["check_id"], finding["row_index"]): finding
        for finding in finding_envelopes
        if finding.get("row_index", -1) >= 0
    }
    include_responsable = any(
        _should_expose_responsable_v2((finding.get("lot_assignment") or {}).get("responsable"))
        for finding in finding_envelopes
    )
    for check in executed_checks:
        if check.get("status") != "ok":
            continue
        columns = [column for column in list(check.get("columns") or []) if column != "Responsable"]
        if "Lot" not in columns:
            columns.append("Lot")
        if include_responsable:
            columns.append("Responsable")
        check["columns"] = columns
        updated_rows = []
        for index, row in enumerate(check.get("rows") or []):
            current = dict(row)
            current.pop("Responsable", None)
            finding = finding_lookup.get((check["check_id"], index))
            lot_assignment = (finding or {}).get("lot_assignment") or {}
            current["Lot"] = (lot_assignment.get("lot") or "SENSE LOT").strip() or "SENSE LOT"
            if include_responsable and _should_expose_responsable_v2(lot_assignment.get("responsable")):
                current["Responsable"] = lot_assignment.get("responsable")
            updated_rows.append(current)
        check["rows"] = updated_rows
    return executed_checks

