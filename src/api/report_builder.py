"""
report_builder.py — Mòdul estàndard de generació d'informes d'auditoria Oracle E13BD.

Implementa el patró de 8 seccions obligatòries:
  0. Portada / Capçalera
  1. Índex navegable (TOC)
  2. Context i metadades
  3. Resum Executiu
  4. [Condicional] Diagnòstic IA (AI_IMPROVEMENT_PLAN=true)
  5. Detall analític per esquema
  6. Matriu de Risc Global
  7. Properes Accions

Formats suportats:
  - Markdown (pur, amb blocs Mermaid per dependències)
  - PDF (via xhtml2pdf, amb capçalera/peu per pàgina, SVG progress bars, fallback tabular per Mermaid)
"""

import logging
import datetime
import html as _html_module
import io
import os
import re as _re
from pathlib import Path
from typing import Any, Dict, List, Optional

from xhtml2pdf import pisa
from src.core.report_design_agent import ReportDesignAgent
from src.core.time_utils import utc_now

# Instància global de l'agent de disseny per a coherència visual
_DESIGN_AGENT = ReportDesignAgent()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def _report_now_text() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M:%S")


def _generate_ai_text(prompt: str, *, timeout: int = 15) -> Optional[str]:
    try:
        from src.core.ai_assistant import AIAssistant

        return AIAssistant().generate_response(prompt, timeout=timeout)
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        logger.warning("No s'ha pogut generar el bloc IA del report", exc_info=exc)
        return None



def _build_deep_ai_prompt(profile: str, data: List[Dict[str, Any]]) -> str:
    schema_lines = []
    for item in data[:20]:
        summary = item.get("summary") or {}
        schema_lines.append(
            f"- {item.get('username') or 'N/A'}: "
            f"Score={int(_to_float(item.get('obsolescence_score')))}%, "
            f"Decisio={item.get('audit_result', 'PRECAUCIO')}, "
            f"Mida={_to_float(summary.get('SIZE_GB')):.2f}GB, "
            f"Jobs={int(_to_float(summary.get('ACTIVE_JOBS')))}, "
            f"Deps.in={int(_to_float(summary.get('INBOUND_REFERENCES')))}"
        )
    return (
        f"Ets un DBA Oracle Senior. Analitza breument en catala l'estat d'obsolescencia del perfil '{profile}' amb les seguents dades:\n"
        + "\n".join(schema_lines)
        + "\nEmet recomanacions estrategiques per a gestors."
    )


def _build_post_crq_ai_prompt(profile: str, results: List[Dict[str, Any]], *, intro: str) -> str:
    check_lines = [
        f"- {item.get('title')}: {item.get('row_count')} troballes ({item.get('severitat')})"
        for item in results[:15]
    ]
    return (
        f"{intro} per al perfil '{profile}':\n"
        + "\n".join(check_lines)
        + "\nProporciona un resum curt en catala normatiu, ben escrit i revisat."
    )

QUERY_EXPLANATIONS: Dict[str, str] = {
    "Q01_SUMMARY_360": "Consolida activitat, mida, dependències i alarmes globals de risc.",
    "Q02_SIZE": "Calcula volum real ocupat per segments de l'esquema.",
    "Q03_USER_ACCOUNT": "Mostra estat de compte, perfil i dates de seguretat/login.",
    "Q04_ACTIVITY_CLASS": "Classifica activitat recent (DDL, stats i modificacions DML).",
    "Q05_OBJECTS_BY_TYPE": "Inventari d'objectes per tipus i extrem de dates DDL/creació.",
    "Q06_RECENT_DDL": "Detall d'objectes amb canvis estructurals recents.",
    "Q07_TABLE_STATS": "Vigència d'estadístiques i volum de taules.",
    "Q08_DEPS_INCOMING": "Dependències entrants (bloquejador principal de baixa).",
    "Q09_DEPS_OUTGOING": "Dependències sortints cap a altres esquemes.",
    "Q10_SYNONYMS": "Sinònims relacionats amb l'esquema (propis i externs).",
    "Q11_GRANTS_GIVEN": "Permisos atorgats per l'esquema a tercers.",
    "Q12_GRANTS_RECEIVED": "Permisos rebuts sobre objectes externs.",
    "Q13_SYS_PRIVS": "Privilegis de sistema de l'esquema.",
    "Q14_CODE_REFS_SOURCE": "Referències literals en codi PL/SQL (DBA_SOURCE).",
    "Q14_CODE_REFS_VIEWS": "Referències literals en definicions de vistes.",
    "Q14_CODE_REFS_TRIGGERS": "Referències literals en clàusules WHEN de triggers.",
    "Q15_JOBS": "Inventari de jobs scheduler i estat d'execució.",
    "Q16_TRIGGERS_ENABLED": "Triggers habilitats i events associats.",
    "Q17_APEX_APPS": "Aplicacions APEX associades a l'esquema.",
    "Q18_DB_LINKS": "DB links que poden afectar dependències remotes.",
    "Q19_INVALID_OBJECTS": "Objectes invàlids amb risc funcional.",
}

RISK_MATRIX_DIMENSIONS = [
    "Operatiu",
    "Seguretat",
    "Arquitectura",
    "Continuïtat",
    "Obsolescència",
]


# ---------------------------------------------------------------------------
# Helpers compartits
# ---------------------------------------------------------------------------

def _ai_improvement_active() -> bool:
    """Retorna True si AI_IMPROVEMENT_PLAN=true al .env / entorn."""
    # Per defecte ho posem a false per petició de l'usuari
    return os.getenv("AI_IMPROVEMENT_PLAN", "false").strip().lower() == "true"


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(str(value).replace("%", "").strip())
    except (ValueError, TypeError):
        return default


def _safe_text(value: Any, max_len: Optional[int] = 120) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if max_len is None or max_len <= 0:
        return text
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _safe_html(value: Any, max_len: Optional[int] = 160) -> str:
    return _html_module.escape(_safe_text(value, max_len))


def _recommendation(decision: str) -> str:
    d = str(decision).upper()
    if "ELIMINAR" in d and "NO" not in d:
        return "Candidat de baixa. Preparar checklist pre-drop i backup."
    if "PRECAUCIO" in d:
        return "Validar amb equip funcional i planificar finestra tècnica."
    return "Mantenir en servei. Revisar impacte transversal i canvis controlats."


def _slug(text: str) -> str:
    """Genera un àncora CSS segura a partir d'un títol."""
    t = str(text).lower().strip()
    t = _re.sub(r"[àáâãä]", "a", t)
    t = _re.sub(r"[èéêë]", "e", t)
    t = _re.sub(r"[ìíîï]", "i", t)
    t = _re.sub(r"[òóôõö]", "o", t)
    t = _re.sub(r"[ùúûü]", "u", t)
    t = _re.sub(r"[ç]", "c", t)
    t = _re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")


def _score_color(score: int) -> str:
    if score >= 70:
        return "#ef4444"  # vermell
    if score >= 40:
        return "#f97316"  # taronja
    return "#22c55e"  # verd


def _decision_color(decision: str) -> str:
    d = str(decision).upper()
    if "ELIMINAR" in d and "NO" not in d:
        return "#ef4444"
    if "NO ELIMINAR" in d:
        return "#22c55e"
    return "#f97316"


def _ascii_bar(score: int, width: int = 20) -> str:
    filled = round(score * width / 100)
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
# Funcions de payload de consultes (mapping qid → dades)
# ---------------------------------------------------------------------------

def _deep_query_payload(schema_item: Dict, query_id: str) -> List[Dict]:
    mapping = {
        "Q01_SUMMARY_360": lambda d: [d.get("summary")] if d.get("summary") else [],
        "Q02_SIZE": lambda d: d.get("size_segments") or [],
        "Q03_USER_ACCOUNT": lambda d: [d.get("account")] if d.get("account") else [],
        "Q04_ACTIVITY_CLASS": lambda d: [d.get("activity_classification")] if d.get("activity_classification") else [],
        "Q05_OBJECTS_BY_TYPE": lambda d: d.get("object_types") or [],
        "Q06_RECENT_DDL": lambda d: (d.get("activity") or {}).get("ddl") or [],
        "Q07_TABLE_STATS": lambda d: d.get("table_stats") or [],
        "Q08_DEPS_INCOMING": lambda d: (d.get("dependencies") or {}).get("incoming") or [],
        "Q09_DEPS_OUTGOING": lambda d: (d.get("dependencies") or {}).get("outgoing") or [],
        "Q10_SYNONYMS": lambda d: d.get("synonyms") or [],
        "Q11_GRANTS_GIVEN": lambda d: d.get("grants_given") or [],
        "Q12_GRANTS_RECEIVED": lambda d: d.get("grants_received") or [],
        "Q13_SYS_PRIVS": lambda d: d.get("sys_privs") or [],
        "Q14_CODE_REFS_SOURCE": lambda d: d.get("code_refs") or [],
        "Q14_CODE_REFS_VIEWS": lambda d: d.get("code_refs") or [],
        "Q14_CODE_REFS_TRIGGERS": lambda d: d.get("code_refs") or [],
        "Q15_JOBS": lambda d: d.get("active_jobs") or [],
        "Q16_TRIGGERS_ENABLED": lambda d: d.get("enabled_triggers") or [],
        "Q17_APEX_APPS": lambda d: d.get("apex_apps") or [],
        "Q18_DB_LINKS": lambda d: d.get("db_links") or [],
        "Q19_INVALID_OBJECTS": lambda d: d.get("invalid_objects") or [],
    }
    fn = mapping.get(query_id)
    return fn(schema_item) if fn else []


# ---------------------------------------------------------------------------
# Blocs Markdown
# ---------------------------------------------------------------------------

def _md_rows_table(rows: List[Dict], max_rows: Optional[int] = None) -> str:
    if not rows:
        return "_Sense files retornades._"
    sample = rows if max_rows in (None, 0) else rows[:max_rows]
    cols = list(sample[0].keys())
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for row in sample:
        vals = [_safe_text(row.get(c, ""), None) for c in cols]
        lines.append("| " + " | ".join(vals) + " |")
    if max_rows not in (None, 0) and len(rows) > max_rows:
        lines.append(f"_… {len(rows) - max_rows} files addicionals no mostrades._")
    return "\n".join(lines)


def _md_mermaid_deps(incoming: List[Dict], outgoing: List[Dict], schema: str) -> str:
    """Genera un bloc Mermaid flowchart de dependències."""
    if not incoming and not outgoing:
        return "_Sense dependències detectades._"

    lines = ["```mermaid", "flowchart TD"]
    seen: set = set()

    for dep in incoming[:10]:
        owner = _safe_text(dep.get("REFERENCED_OWNER") or dep.get("OWNER") or "?", 30)
        name = _safe_text(dep.get("NAME") or dep.get("OBJECT_NAME") or "?", 30)
        node = f"{owner}.{name}".replace(" ", "_").replace(".", "_")
        if node not in seen:
            lines.append(f'    {node}["{owner}.{name}"] -->|usa| {schema}["{schema}"]')
            seen.add(node)

    for dep in outgoing[:10]:
        ref = _safe_text(dep.get("REFERENCED_OWNER") or dep.get("OWNER") or "?", 30)
        refname = _safe_text(dep.get("REFERENCED_NAME") or dep.get("OBJECT_NAME") or "?", 30)
        node = f"{ref}.{refname}".replace(" ", "_").replace(".", "_")
        if node not in seen:
            lines.append(f'    {schema}["{schema}"] -->|depèn de| {node}["{ref}.{refname}"]')
            seen.add(node)

    lines.append("```")
    return "\n".join(lines)


def _md_toc(sections: List[Dict[str, str]]) -> str:
    """Genera la taula de continguts Markdown amb links."""
    lines = ["## Índex", ""]
    for i, section in enumerate(sections, 1):
        depth = section.get("depth", 0)
        indent = "    " * depth
        title = section["title"]
        anchor = section.get("anchor") or _slug(title)
        lines.append(f"{indent}{i}. [{title}](#{anchor})")
    lines.append("")
    return "\n".join(lines)


def _md_risk_matrix(data: List[Dict]) -> str:
    """Genera la matriu de risc global en Markdown."""
    lines = [
        "## Matriu de Risc {#matriu-de-risc}",
        "",
        "| Dimensió | Nivell | Justificació |",
        "| --- | --- | --- |",
    ]

    # Calcular nivells globals
    scores = [int(_to_float(d.get("obsolescence_score"))) for d in data if d.get("obsolescence_score") is not None]
    avg_score = round(sum(scores) / len(scores), 0) if scores else 0
    decisions = [str(d.get("audit_result", "")) for d in data]
    has_blockers = any(
        _to_float((d.get("summary") or {}).get("INBOUND_REFERENCES")) > 0 or
        _to_float((d.get("summary") or {}).get("ACTIVE_JOBS")) > 0
        for d in data
    )

    operatiu = "ALT" if has_blockers else ("MITJÀ" if avg_score >= 40 else "BAIX")
    seguretat = "ALT" if any("NO ELIMINAR" in d for d in decisions) else "BAIX"
    arquitectura = "MITJÀ" if any("PRECAUCIO" in d for d in decisions) else "BAIX"
    continuitat = "ALT" if has_blockers else "BAIX"
    obsolescencia = "ALT" if avg_score >= 70 else ("MITJÀ" if avg_score >= 40 else "BAIX")

    matrix = [
        ("Operatiu", operatiu, "Presència de jobs, triggers o APEX actius" if has_blockers else "Sense automatismes crítics"),
        ("Seguretat", seguretat, "Esquemes amb dependències crítiques detectades" if seguretat == "ALT" else "Sense riscos de seguretat greus"),
        ("Arquitectura", arquitectura, "Esquemes en revisió que poden afectar fluxos" if arquitectura == "MITJÀ" else "Arquitectura estable"),
        ("Continuïtat", continuitat, "Bloquejadors operatius detectats" if continuitat == "ALT" else "Sense riscos operatius immediatament urgents"),
        ("Obsolescència", obsolescencia, f"Score mitjà: {int(avg_score)}%"),
    ]
    for dim, nivell, just in matrix:
        lines.append(f"| {dim} | **{nivell}** | {just} |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# BUILD MARKDOWN (deep audit)
# ---------------------------------------------------------------------------

def build_standard_markdown(profile: str, data: List[Dict], ai_active: Optional[bool] = None) -> str:
    """
    Construeix un informe Markdown estàndard E13BD.
    Itera dinàmicament sobre la configuració _DESIGN_AGENT.get_report_structure().
    """
    if ai_active is None:
        ai_active = _ai_improvement_active()

    now = _report_now_text()
    total_gb = sum(_to_float((d.get("summary") or {}).get("SIZE_GB")) for d in data)
    avg_score = round(sum(int(_to_float(d.get("obsolescence_score"))) for d in data) / len(data), 1) if data else 0
    decisions = [str(d.get("audit_result", "PRECAUCIO")) for d in data]
    no_eliminar = decisions.count("NO ELIMINAR")
    precaucio = decisions.count("PRECAUCIO")
    eliminar = decisions.count("ELIMINAR")

    md: List[str] = []
    structure = _DESIGN_AGENT.get_report_structure()

    for section in structure:
        if not section.get("enabled", True):
            continue
            
        sec_id = section.get("id")

        # ---- Portada ----
        if sec_id == "cover":
            md.append(f"# {_DESIGN_AGENT.title} — Perfil: {profile}")
            if _DESIGN_AGENT.subtitle:
                md.append("")
                md.append(f"**{_DESIGN_AGENT.subtitle}**")
            md.append("")
            md.append(f"_Generat: {now} | Tipus: Deep Scan Q01–Q19 | Esquemes: {len(data)}_")
            md.append("")
            md.append("---")
            md.append("")

        # ---- SECCIÓ 1: Índex ----
        elif sec_id == "toc":
            toc_sections = []
            for s in structure:
                if s.get("enabled", True) and s.get("id") not in ("cover", "toc"):
                    anchor = _slug(s["title"])
                    toc_sections.append({"title": s["title"], "anchor": anchor})
                    if s.get("id") == "schema_detail" and data:
                        for i, item in enumerate(data):
                            schema = item.get("username") or (item.get("summary") or {}).get("USERNAME") or "N/A"
                            toc_sections.append({"title": f"Detall: {schema}", "anchor": f"esquema-{_slug(schema)}", "depth": 1})
            md.append(_md_toc(toc_sections))
            md.append("---")
            md.append("")

        # ---- SECCIÓ 2: Context ----
        elif sec_id == "context":
            md.append(f"## {section['title']} {{#{_slug(section['title'])}}}")
            md.append("")
            md.append("| Paràmetre | Valor |")
            md.append("| --- | --- |")
            md.append(f"| Perfil actiu | **{profile}** |")
            md.append("| Pla executat | Q01..Q19 |")
            md.append(f"| Esquemes analitzats | **{len(data)}** |")
            md.append(f"| Data de generació | **{now}** |")
            md.append(f"| Mode IA actiu | **{'Sí' if ai_active else 'No'}** |")
            md.append("")

        # ---- SECCIÓ 3: Resum Executiu ----
        elif sec_id == "executive_summary":
            summary_narrative = _DESIGN_AGENT.get_summary_narrative_template()
            total = len(data) or 1
            html = f"""
    <h1 id="{_slug(section['title'])}">{_DESIGN_AGENT.title}</h1>
    <div class="summary-box">
        <h2 style="margin-top:0; border:none; page-break-before:avoid;">{section['title']}</h2>
        <p>{summary_narrative}</p>
        <table class="kpi-table">
            <thead>
                <tr>
                    <th>Esquemes</th>
                    <th>Volum Total</th>
                    <th>Score Mitjà</th>
                    <th>Candidats Baixa</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{total}</td>
                    <td>{total_gb:.2f} GB</td>
                    <td>{avg_score}%</td>
                    <td class="risk-high">{eliminar}</td>
                </tr>
            </tbody>
        </table>
    </div>
"""
            md.append(html)
            md.append("")
            md.append("### Indicadors Clau de l'Auditoria")
            md.append("")
            md.append(f"- **Abast de l'anàlisi**: S'han auditat un total de **{len(data)}** esquemes sota el perfil `{profile}`.")
            md.append(f"- **Ocupació de dades**: El volum total de dades analitzat ascendeix a **{total_gb:.2f} GB**.")
            md.append(f"- **Índex d'obsolescència mitjà**: Se situa en un **{avg_score}%**, reflectint l'estat global de vigència tecnològica.")
            md.append(f"- **Classificació de decisions**: El resultat de l'auditoria suggereix mantenir **{no_eliminar}** esquemes, revisar-ne **{precaucio}** per precaució i procedir a la baixa de **{eliminar}** candidats.")
            md.append("")
            md.append("### Distribució de decisions")
            md.append("")
            md.append("| Decisió | Comptador | % del total |")
            md.append("| --- | --- | --- |")
            md.append(f"| **NO ELIMINAR** | {no_eliminar} | {no_eliminar/total*100:.1f}% |")
            md.append(f"| **PRECAUCIO** | {precaucio} | {precaucio/total*100:.1f}% |")
            md.append(f"| **ELIMINAR** | {eliminar} | {eliminar/total*100:.1f}% |")
            md.append("")
            md.append("### Resum global per esquema")
            md.append("")
            md.append("| Esquema | Decisió | Score | Mida(GB) | Deps In | Jobs | APEX | Triggers | Invàlids |")
            md.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
            for d in sorted(data, key=lambda x: -int(_to_float(x.get("obsolescence_score")))):
                sch = d.get("username") or (d.get("summary") or {}).get("USERNAME") or "N/A"
                dec = d.get("audit_result", "PRECAUCIO")
                sc = int(_to_float(d.get("obsolescence_score")))
                sumry = d.get("summary") or {}
                gb = _to_float(sumry.get("SIZE_GB"))
                in_d = int(_to_float(sumry.get("INBOUND_REFERENCES")))
                jbs = int(_to_float(sumry.get("ACTIVE_JOBS")))
                apx = int(_to_float(sumry.get("APEX_APPLICATIONS")))
                trg = int(_to_float(sumry.get("ENABLED_TRIGGERS")))
                inv = len(d.get("invalid_objects") or [])
                md.append(f"| {sch} | **{dec}** | {sc}% | {gb:.2f} | {in_d} | {jbs} | {apx} | {trg} | {inv} |")
            md.append("")
            md.append("### Resum de consultes Q01..Q19")
            md.append("")
            md.append("Agregat de resultats de totes les consultes executades sobre tots els esquemes:")
            md.append("")
            md.append("| Consulta | Que valida | Esquemes amb dades | Total files |")
            md.append("| --- | --- | --- | --- |")
            q_agg: dict = {}
            for d in data:
                for q in (d.get("executed_queries") or []):
                    qid = q.get("query", "N/A")
                    rows_val = int(_to_float(q.get("rows", 0)))
                    if qid not in q_agg:
                        q_agg[qid] = {"schemas_amb_dades": 0, "total_files": 0}
                    if rows_val > 0:
                        q_agg[qid]["schemas_amb_dades"] += 1
                        q_agg[qid]["total_files"] += rows_val
            for qid in sorted(q_agg.keys()):
                expl = QUERY_EXPLANATIONS.get(qid, "—")
                amb_dades = q_agg[qid]["schemas_amb_dades"]
                total_files_q = q_agg[qid]["total_files"]
                md.append(f"| `{qid}` | {expl} | {amb_dades} | {total_files_q} |")
            md.append("")
            total_in_deps = sum(int(_to_float((d.get("summary") or {}).get("INBOUND_REFERENCES"))) for d in data)
            total_jobs = sum(int(_to_float((d.get("summary") or {}).get("ACTIVE_JOBS"))) for d in data)
            total_apex = sum(int(_to_float((d.get("summary") or {}).get("APEX_APPLICATIONS"))) for d in data)
            total_trigs = sum(int(_to_float((d.get("summary") or {}).get("ENABLED_TRIGGERS"))) for d in data)
            total_invalids = sum(len(d.get("invalid_objects") or []) for d in data)
            md.append("### KPIs globals agregats")
            md.append("")
            md.append("| KPI | Total |")
            md.append("| --- | --- |")
            md.append(f"| Mida total analitzada | **{total_gb:.2f} GB** |")
            md.append(f"| Dependències entrants totals | **{total_in_deps}** |")
            md.append(f"| Jobs actius totals | **{total_jobs}** |")
            md.append(f"| Aplicacions APEX totals | **{total_apex}** |")
            md.append(f"| Triggers habilitats totals | **{total_trigs}** |")
            md.append(f"| Objectes invàlids totals | **{total_invalids}** |")
            md.append("")

        # ---- SECCIÓ 4: Diagnòstic IA ----
        elif sec_id == "ai_diagnostic":
            if ai_active:
                md.append(f"## {section['title']} {{#{_slug(section['title'])}}}")
                md.append("")
                md.append("> _Bloc generat per Gemini_")
                md.append("")
                prompt = _build_deep_ai_prompt(profile, data)
                md.append(_generate_ai_text(prompt) or "_No s'ha pogut generar el diagnostic IA._")
                md.append("")

        # ---- SECCIÓ 5: Detall per esquema ----
        elif sec_id == "schema_detail":
            for schema_item in data:
                schema = schema_item.get("username") or (schema_item.get("summary") or {}).get("USERNAME") or "N/A"
                summary = schema_item.get("summary") or {}
                decision = schema_item.get("audit_result", "PRECAUCIO")
                score = int(_to_float(schema_item.get("obsolescence_score")))
                in_deps = int(_to_float(summary.get("INBOUND_REFERENCES")))
                jobs = int(_to_float(summary.get("ACTIVE_JOBS")))
                apex = int(_to_float(summary.get("APEX_APPLICATIONS")))
                trigs = int(_to_float(summary.get("ENABLED_TRIGGERS")))
                invalids = len(schema_item.get("invalid_objects") or [])
                gb = _to_float(summary.get("SIZE_GB"))

                if score >= 100 and (in_deps + jobs + apex + trigs) == 0 and decision == "PRECAUCIO":
                    decision = "ELIMINAR"

                anchor = f"esquema-{_slug(schema)}"
                md.append(f"## Esquema: `{schema}` {{#{anchor}}}")
                md.append("")
                md.append(f"**Decisió final: {decision}** | Score: {score}% | Mida: {gb:.2f} GB")
                md.append("")
                md.append("### KPIs")
                md.append("")
                md.append("| Mètrica | Valor |")
                md.append("| --- | --- |")
                md.append(f"| Dependències entrants | **{in_deps}** |")
                md.append(f"| Jobs actius | **{jobs}** |")
                md.append(f"| APEX apps | **{apex}** |")
                md.append(f"| Triggers habilitats | **{trigs}** |")
                md.append(f"| Objectes invàlids | **{invalids}** |")
                md.append("")
                md.append("### Score d'obsolescència")
                md.append("")
                md.append(f"`{score}%` {_ascii_bar(score)}")
                md.append("")
                md.append("### Diagrama de dependències")
                md.append("")
                incoming = (schema_item.get("dependencies") or {}).get("incoming") or []
                outgoing = (schema_item.get("dependencies") or {}).get("outgoing") or []
                md.append(_md_mermaid_deps(incoming, outgoing, schema))
                md.append("")

                breakdown = schema_item.get("score_breakdown") or []
                if breakdown:
                    md.append("### Scoring breakdown")
                    md.append("")
                    md.append("| Factor | Punts | Explicació |")
                    md.append("| --- | --- | --- |")
                    for b in breakdown:
                        md.append(f"| {_safe_text(b.get('factor'))} | {_safe_text(b.get('pts'))} | {_safe_text(b.get('desc'), 200)} |")
                    md.append("")

                md.append("### Traçabilitat Q01..Q19")
                md.append("")
                md.append("| Consulta | Estat | Files | Que valida |")
                md.append("| --- | --- | --- | --- |")
                for q in schema_item.get("executed_queries") or []:
                    qid = q.get("query", "N/A")
                    md.append(f"| {qid} | {q.get('status', 'N/A')} | {q.get('rows', 0)} | {QUERY_EXPLANATIONS.get(qid, '—')} |")
                md.append("")
                md.append("### Resultats per consulta")
                md.append("")
                for q in schema_item.get("executed_queries") or []:
                    qid = q.get("query", "N/A")
                    rows_data = _deep_query_payload(schema_item, qid)
                    if not rows_data:
                        continue
                    expl = QUERY_EXPLANATIONS.get(qid, "Consulta d'auditoria")
                    md.append(f"#### {qid} — {expl}")
                    md.append("")
                    md.append(f"- Files retornades: **{len(rows_data)}**")
                    md.append("")
                    md.append(_md_rows_table(rows_data))
                    md.append("")
                md.append("### Recomanació operativa")
                md.append("")
                md.append(f"- {_recommendation(decision)}")
                md.append("")
                md.append("---")
                md.append("")

        # ---- SECCIÓ 6: Matriu de Risc ----
        elif sec_id == "risk_matrix":
            md.append(f"## {section['title']} {{#{_slug(section['title'])}}}")
            md.append("")
            # Strip hardcoded title from helper output
            risk_html_lines = _md_risk_matrix(data).split("\n")[2:]
            md.extend(risk_html_lines)
            md.append("---")
            md.append("")

        # ---- SECCIÓ 7: Properes Accions ----
        elif sec_id == "next_actions":
            md.append(f"## {section['title']} {{#{_slug(section['title'])}}}")
            md.append("")
            default_actions = [
                "Validar manualment esquemes `NO ELIMINAR` amb dependències entrants.",
                "Preparar pla de remediació per `PRECAUCIO` (finestra, proves, rollback).",
                "Executar checklist pre-drop per candidats `ELIMINAR` (backup → aprovació → traçabilitat)."
            ]
            for i, step in enumerate(_DESIGN_AGENT.get_template_content("next_steps", default_actions), 1):
                md.append(f"{i}. {step}")
            md.append("")

    return "\n".join(md)


# ---------------------------------------------------------------------------
# Helpers HTML/PDF
# ---------------------------------------------------------------------------

def _md_to_html(text: str) -> str:
    """Converteix Markdown bàsic a HTML per a xhtml2pdf."""

    def _fmt(s: str) -> str:
        s = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = _re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
        return s

    lines = text.split("\n")
    result: List[str] = []
    in_ul = False
    in_table = False
    table_rows: List[str] = []

    def flush_table() -> None:
        if not table_rows:
            return
        out = ["<table>"]
        for i, row in enumerate(table_rows):
            cells = [c.strip() for c in row.strip("|").split("|")]
            if i == 0:
                out.append("<thead><tr>")
                for c in cells:
                    out.append(f"<th>{_fmt(c)}</th>")
                out.append("</tr></thead><tbody>")
            else:
                out.append("<tr>")
                for c in cells:
                    out.append(f"<td>{_fmt(c)}</td>")
                out.append("</tr>")
        out.append("</tbody></table>")
        result.extend(out)
        table_rows.clear()

    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")
        is_separator = _re.match(r"^\|[-| :]+\|$", stripped) is not None

        if is_table_line:
            in_table = True
            if in_ul:
                result.append("</ul>")
                in_ul = False
            if not is_separator:
                table_rows.append(stripped)
            continue
        else:
            if in_table:
                flush_table()
                in_table = False

        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_ul:
                result.append("<ul>")
                in_ul = True
            result.append(f"<li>{_fmt(stripped[2:])}</li>")
            continue
        else:
            if in_ul:
                result.append("</ul>")
                in_ul = False

        if not stripped:
            continue
        elif stripped.startswith("### "):
            result.append(f"<h3>{_fmt(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            result.append(f"<h3>{_fmt(stripped[3:])}</h3>")
        elif stripped.startswith("# "):
            result.append(f"<h3>{_fmt(stripped[2:])}</h3>")
        else:
            result.append(f"<p>{_fmt(stripped)}</p>")

    if in_ul:
        result.append("</ul>")
    if in_table:
        flush_table()

    return "\n".join(result)


def _build_score_bar_svg(score: int) -> str:
    """Genera una barra de progrés SVG inline per al score."""
    color = _score_color(score)
    fill_width = max(0, min(200, score * 2))
    return (
        f'<svg width="200" height="14" style="vertical-align:middle;margin-left:8px;">'
        f'<rect width="200" height="14" rx="4" fill="#e5e7eb"/>'
        f'<rect width="{fill_width}" height="14" rx="4" fill="{color}"/>'
        f"</svg>"
    )


def _build_deps_html_table(incoming: List[Dict], outgoing: List[Dict]) -> str:
    """Fallback tabular per dependències quan Mermaid no és disponible en PDF."""
    if not incoming and not outgoing:
        return "<p><em>Sense dependències detectades.</em></p>"

    parts: List[str] = []
    if incoming:
        rows_html = "".join(
            f"<tr>"
            f"<td>{_safe_html(d.get('REFERENCED_OWNER') or d.get('OWNER', '?'))}</td>"
            f"<td>{_safe_html(d.get('NAME') or d.get('OBJECT_NAME', '?'))}</td>"
            f"<td>{_safe_html(d.get('TYPE') or d.get('OBJECT_TYPE', '?'))}</td>"
            f"</tr>"
            for d in incoming[:15]
        )
        parts.append(
            f"<p><strong>Dependències entrants ({len(incoming)}):</strong></p>"
            f"<table><thead><tr><th>Propietari</th><th>Objecte</th><th>Tipus</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table>"
        )
    if outgoing:
        rows_html = "".join(
            f"<tr>"
            f"<td>{_safe_html(d.get('REFERENCED_OWNER') or d.get('OWNER', '?'))}</td>"
            f"<td>{_safe_html(d.get('REFERENCED_NAME') or d.get('OBJECT_NAME', '?'))}</td>"
            f"<td>{_safe_html(d.get('TYPE') or d.get('OBJECT_TYPE', '?'))}</td>"
            f"</tr>"
            for d in outgoing[:15]
        )
        parts.append(
            f"<p><strong>Dependències sortints ({len(outgoing)}):</strong></p>"
            f"<table><thead><tr><th>Propietari</th><th>Objecte</th><th>Tipus</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table>"
        )
    return "".join(parts)


def _build_html_rows_table(rows: List[Dict], max_rows: int = 5, max_cols: int = 6) -> str:
    if not rows:
        return "<p><em>Sense dades.</em></p>"
    sample = rows[:max_rows]
    cols = list(sample[0].keys())[:max_cols]
    header = "".join(f"<th>{_safe_html(c, 30)}</th>" for c in cols)
    body_rows = []
    for row in sample:
        cells = ""
        for c in cols:
            val = str(row.get(c, ""))
            if len(val) > 40 and " " not in val[:40]:
                val = " ".join(val[i:i+40] for i in range(0, len(val), 40))
            cells += f"<td>{_safe_html(val, 80)}</td>"
        body_rows.append(f"<tr>{cells}</tr>")
    extra = f"<p><em>… {len(rows) - max_rows} files addicionals.</em></p>" if len(rows) > max_rows else ""
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>{extra}"


def _build_pdf_header_footer(profile: str, generation_date: str, footer_text: Optional[str] = None) -> str:
    """Genera HTML especial per a capçaleres i peus delegant a l'Agent de Disseny."""
    header_html = _DESIGN_AGENT.get_header_html(profile, generation_date)
    
    # Text per defecte si no es proporciona un de personalitzat
    if not footer_text:
        footer_text = f"Confidencial - {_DESIGN_AGENT.institution_name}"
        
    return f"""
    <div id="header_content">
        {header_html}
    </div>
    <div id="footer_content">
        Pàgina <pdf:pagenumber> de <pdf:pagecount> | {footer_text}
    </div>
    """


def _build_risk_matrix_html(data: List[Dict]) -> str:
    scores = [int(_to_float(d.get("obsolescence_score"))) for d in data if d.get("obsolescence_score") is not None]
    avg_score = round(sum(scores) / len(scores), 0) if scores else 0
    decisions = [str(d.get("audit_result", "")) for d in data]
    has_blockers = any(
        _to_float((d.get("summary") or {}).get("INBOUND_REFERENCES")) > 0 or
        _to_float((d.get("summary") or {}).get("ACTIVE_JOBS")) > 0
        for d in data
    )

    operatiu = ("ALT", "#ef4444") if has_blockers else (("MITJÀ", "#f97316") if avg_score >= 40 else ("BAIX", "#22c55e"))
    seguretat = ("ALT", "#ef4444") if any("NO ELIMINAR" in d for d in decisions) else ("BAIX", "#22c55e")
    arquitectura = ("MITJÀ", "#f97316") if any("PRECAUCIO" in d for d in decisions) else ("BAIX", "#22c55e")
    continuitat = ("ALT", "#ef4444") if has_blockers else ("BAIX", "#22c55e")
    obsoles = ("ALT", "#ef4444") if avg_score >= 70 else (("MITJÀ", "#f97316") if avg_score >= 40 else ("BAIX", "#22c55e"))

    matrix = [
        ("Operatiu", *operatiu, "Presència d'automatismes crítics" if has_blockers else "Sense automatismes"),
        ("Seguretat", *seguretat, "Esquemes amb dependències crítiques" if seguretat[0] == "ALT" else "Sense riscos greus"),
        ("Arquitectura", *arquitectura, "Esquemes en revisió activa" if arquitectura[0] == "MITJÀ" else "Arquitectura estable"),
        ("Continuïtat", *continuitat, "Bloquejadors operatius detectats" if continuitat[0] == "ALT" else "Sense riscos urgents"),
        ("Obsolescència", *obsoles, f"Score mitjà: {int(avg_score)}%"),
    ]

    rows_html = "".join(
        f"<tr>"
        f"<td><strong>{_safe_html(dim)}</strong></td>"
        f'<td><span style="background:{color};color:white;padding:2px 6px;border-radius:3px;font-size:8pt;">{_safe_html(nivell)}</span></td>'
        f"<td>{_safe_html(text)}</td>"
        f"</tr>"
        for dim, nivell, color, text in matrix
    )
    return (
        "<h2>Matriu de Risc</h2>"
        "<table><thead><tr><th>Dimensió</th><th>Nivell</th><th>Justificació</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
    )


def _build_all_schemas_html_rows(data: List[Dict]) -> str:
    """Genera les files HTML de la taula global d'esquemes per al PDF."""
    rows = []
    for d in sorted(data, key=lambda x: -int(_to_float(x.get("obsolescence_score")))):
        sch = d.get("username") or (d.get("summary") or {}).get("USERNAME") or "N/A"
        dec = d.get("audit_result", "PRECAUCIO")
        dec_col = _decision_color(dec)
        sc = int(_to_float(d.get("obsolescence_score")))
        sc_col = _score_color(sc)
        sumry = d.get("summary") or {}
        gb = _to_float(sumry.get("SIZE_GB"))
        in_d = int(_to_float(sumry.get("INBOUND_REFERENCES")))
        jbs = int(_to_float(sumry.get("ACTIVE_JOBS")))
        apx = int(_to_float(sumry.get("APEX_APPLICATIONS")))
        trg = int(_to_float(sumry.get("ENABLED_TRIGGERS")))
        inv = len(d.get("invalid_objects") or [])
        rows.append(
            f"<tr>"
            f"<td><strong>{_safe_html(sch)}</strong></td>"
            f'<td><span class="badge" style="background:{dec_col}">{_safe_html(dec)}</span></td>'
            f'<td><span class="badge" style="background:{sc_col}">{sc}%</span></td>'
            f"<td>{gb:.2f}</td>"
            f"<td style='text-align:center;'>{in_d}</td>"
            f"<td style='text-align:center;'>{jbs}</td>"
            f"<td style='text-align:center;'>{apx}</td>"
            f"<td style='text-align:center;'>{trg}</td>"
            f"<td style='text-align:center;'>{inv}</td>"
            f"</tr>"
        )
    return "".join(rows)


def _build_queries_summary_html(data: List[Dict]) -> str:
    """Genera les files HTML del resum agregat de consultes Q01..Q19 per al PDF."""
    q_agg: dict = {}
    for d in data:
        for q in (d.get("executed_queries") or []):
            qid = q.get("query", "N/A")
            rows_val = int(_to_float(q.get("rows", 0)))
            if qid not in q_agg:
                q_agg[qid] = {"schemas_amb_dades": 0, "total_files": 0}
            if rows_val > 0:
                q_agg[qid]["schemas_amb_dades"] += 1
                q_agg[qid]["total_files"] += rows_val

    rows_html = []
    for qid in sorted(q_agg.keys()):
        expl = _safe_html(QUERY_EXPLANATIONS.get(qid, "—"))
        amb_dades = q_agg[qid]["schemas_amb_dades"]
        total_f = q_agg[qid]["total_files"]
        bg = "#f0fdf4" if amb_dades > 0 else "#fafafa"
        rows_html.append(
            f'<tr style="background:{bg};">'
            f"<td><strong>{_safe_html(qid)}</strong></td>"
            f"<td>{expl}</td>"
            f"<td style='text-align:center;'><strong>{amb_dades}</strong></td>"
            f"<td style='text-align:center;'>{total_f}</td>"
            f"</tr>"
        )
    return "".join(rows_html)


def _build_global_kpis_html(data: List[Dict], total_gb: float) -> str:
    """Genera una taula de KPIs globals en 2 columnes per al PDF."""
    total_in_deps = sum(int(_to_float((d.get("summary") or {}).get("INBOUND_REFERENCES"))) for d in data)
    total_jobs = sum(int(_to_float((d.get("summary") or {}).get("ACTIVE_JOBS"))) for d in data)
    total_apex = sum(int(_to_float((d.get("summary") or {}).get("APEX_APPLICATIONS"))) for d in data)
    total_trigs = sum(int(_to_float((d.get("summary") or {}).get("ENABLED_TRIGGERS"))) for d in data)
    total_invalids = sum(len(d.get("invalid_objects") or []) for d in data)
    kpis = [
        ("Mida total analitzada", f"{total_gb:.2f} GB"),
        ("Dependències entrants totals", str(total_in_deps)),
        ("Jobs actius totals", str(total_jobs)),
        ("Aplicacions APEX totals", str(total_apex)),
        ("Triggers habilitats totals", str(total_trigs)),
        ("Objectes invàlids totals", str(total_invalids)),
    ]
    rows_html = "".join(
        f"<tr><td>{_safe_html(k)}</td><td style='text-align:right;font-weight:bold;'>{_safe_html(v)}</td></tr>"
        for k, v in kpis
    )
    return (
        "<table style='width:50%;'>"
        "<thead><tr><th>KPI</th><th style='text-align:right;'>Valor</th></tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )


# ---------------------------------------------------------------------------
# BUILD PDF (deep audit)
# ---------------------------------------------------------------------------

def build_standard_pdf(profile: str, data: List[Dict], ai_active: Optional[bool] = None) -> bytes:
    """
    Construeix un PDF estàndard E13BD (8 seccions, capçalera/peu per pàgina, SVG progress bars).
    Si ai_active és None, llegeix la variable d'entorn AI_IMPROVEMENT_PLAN.
    """
    if ai_active is None:
        ai_active = _ai_improvement_active()

    now = _report_now_text()
    total_gb = sum(_to_float((d.get("summary") or {}).get("SIZE_GB")) for d in data)
    avg_score = round(sum(int(_to_float(d.get("obsolescence_score"))) for d in data) / len(data), 1) if data else 0
    decisions = [str(d.get("audit_result", "PRECAUCIO")) for d in data]
    no_eliminar = decisions.count("NO ELIMINAR")
    precaucio = decisions.count("PRECAUCIO")
    eliminar = decisions.count("ELIMINAR")
    total = len(data) or 1
    
    # Obtenir configuració d'estils i estructura de l'Agent de Disseny
    config = _DESIGN_AGENT.get_style_config()
    colors = _DESIGN_AGENT.colors
    structure = _DESIGN_AGENT.get_report_structure("standard")
    
    css = f"""
    @page {{
        size: A4 portrait;
        margin: 3.5cm 1.5cm 1.5cm 1.5cm;
        @frame header {{
            -pdf-frame-content: header_content;
            top: 0.8cm;
            margin-left: 1.5cm;
            margin-right: 1.5cm;
            height: 2.5cm;
        }}
        @frame footer {{
            -pdf-frame-content: footer_content;
            bottom: 0.5cm;
            margin-left: 1.5cm;
            margin-right: 1.5cm;
            height: 0.8cm;
        }}
    }}
    body {{ font-family: {config['font_family']}; color: {colors['text_main']}; font-size: {config['font_size_base']}; line-height: {config['line_height']}; }}
    h1 {{ color: {config['h1_color']}; font-size: 24pt; border-bottom: 4px solid {config['h1_color']}; padding-bottom: 10px; margin-bottom: 12px; font-weight: bold; -pdf-outline: true; -pdf-level: 0; }}
    h2 {{ color: {config['h2_color']}; font-size: 14pt; margin-top: 25px; border-bottom: 1px solid {colors['border']}; padding-bottom: 6px; page-break-before: always; font-weight: bold; -pdf-outline: true; -pdf-level: 1; }}
    h2:first-of-type {{ page-break-before: avoid; }}
    h3 {{ color: {config['h3_color']}; font-size: 11.5pt; margin-top: 18px; margin-bottom: 6px; font-weight: bold; -pdf-outline: true; -pdf-level: 2; }}
    
    .summary-box {{ 
        background: {config['summary_box_bg']}; 
        border-left: 5px solid {config['summary_box_border']}; 
        padding: 12px 16px; 
        margin: 15px 0; 
        border-radius: 6px; 
    }}
    .context-list {{ list-style-type: none; padding: 0; margin: 10px 0; border-top: 1px solid {colors['border']}; border-bottom: 2px solid {colors['primary']}; padding: 10px 0; }}
    .context-list li {{ margin-bottom: 4px; font-size: 9pt; }}
    
    #toc ul {{ list-style-type: none; padding-left: 0; }}
    #toc li {{ margin-bottom: 6px; border-bottom: 1px solid #f1f5f9; padding-bottom: 2px; }}
    #toc a {{ color: {colors['primary']}; text-decoration: none; }}
    #toc .toc-sub {{ padding-left: 15px; font-size: 8pt; color: #64748b; }}
    #toc .toc-query {{ padding-left: 30px; font-size: 7.5pt; color: #94a3b8; }}
    
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0 16px 0; font-size: 8.5pt; table-layout: fixed; border-radius: 4px; overflow: hidden; }}
    th {{ background: {config['table_header_bg']}; color: #ffffff; border: 1px solid #ffffff; padding: 7px 8px; text-align: left; font-weight: bold; }}
    td {{ border: 1px solid {colors['border']}; padding: 6px 8px; vertical-align: top; }}
    tr:nth-child(even) {{ background: #f8fafc; }}
    .risk-high {{ color: {colors['danger']}; font-weight: bold; }}
    .risk-medium {{ color: {colors['warning']}; font-weight: bold; }}
    """

    hf_html = _build_pdf_header_footer(profile, now)

    # TOC construction dynamically based on structure
    toc_html = ["<ul>"]
    section_counter = 1
    for section in structure:
        sec_id = section["id"]
        sec_title = section["title"]
        sec_type = section["type"]
        
        if section.get("condition") == "ai_active" and not ai_active:
            continue
            
        if sec_type == "schema_details":
            for idx, item in enumerate(data):
                schema = item.get("username") or (item.get("summary") or {}).get("USERNAME") or "N/A"
                schema_slug = f"schema_{idx}"
                toc_html.append(f'<li class="toc-sub"><a href="#{schema_slug}">› Detall: {_safe_html(schema, 40)}</a></li>')
                
                # Afegir enllaços a les consultes Q01..Q19 que tenen dades
                for q in (item.get("executed_queries") or []):
                    qid = q.get("query", "N/A")
                    rows_data = _deep_query_payload(item, qid)
                    if rows_data:
                        query_anchor = f"q_{idx}_{qid}"
                        toc_html.append(f'<li class="toc-query"><a href="#{query_anchor}">&nbsp;&nbsp;· {qid}</a></li>')
        else:
            prefix = ""
            if sec_type not in ["risk_matrix", "action_plan"]:
                prefix = f"{section_counter}. "
            toc_html.append(f'<li><a href="#{sec_id}">{prefix}{_safe_html(sec_title)}</a></li>')
            section_counter += 1
    toc_html.append("</ul>")
    toc_links = "".join(toc_html)

    # Cos del Document - Iteració Dinàmica
    body_parts = []
    
    # Capçalera inicial i Index
    body_parts.append(f"""
<h1>Informe d'Auditoria Oracle</h1>
<p style="color:#6b7280;margin-top:0;">Perfil: <strong>{_safe_html(profile)}</strong> | Generat: {_safe_html(now)}</p>

<h2 style="page-break-before:avoid;">Índex</h2>
<div id="toc" style="margin-left:10px;margin-top:12px;">
{toc_links}
</div>
""")

    for section in structure:
        sec_id = section["id"]
        sec_title = section["title"]
        sec_type = section["type"]

        if section.get("condition") == "ai_active" and not ai_active:
            continue

        if sec_type == "context":
            body_parts.append(f"""
<h2 id="{sec_id}">{_safe_html(sec_title)}</h2>
<ul class="context-list">
  <li><strong>Perfil actiu:</strong> {_safe_html(profile)}</li>
  <li><strong>Pla executat:</strong> Q01..Q19 | <strong>Esquemes analitzats:</strong> {len(data)}</li>
  <li><strong>Data de generació:</strong> {_safe_html(now)}</li>
  <li><strong>Mode IA actiu:</strong> {'Sí (AI_IMPROVEMENT_PLAN=true)' if ai_active else 'No'}</li>
</ul>
""")
        elif sec_type == "summary":
            # Resum executiu globals
            top = sorted(data, key=lambda x: (
                x.get("audit_result") != "NO ELIMINAR",
                -int(_to_float(x.get("obsolescence_score"))),
            ))[:5]
            
            body_parts.append(f"""
<h2 id="{sec_id}">{_safe_html(sec_title)}</h2>
<div class="summary-box">
  <p><strong>Esquemes:</strong> {len(data)} | <strong>Mida total:</strong> {total_gb:.2f} GB | <strong>Score mitjà:</strong> {avg_score}%</p>
  <p><strong>NO ELIMINAR:</strong> {no_eliminar} ({no_eliminar/total*100:.1f}%) &nbsp;|&nbsp;
     <strong>PRECAUCIO:</strong> {precaucio} ({precaucio/total*100:.1f}%) &nbsp;|&nbsp;
     <strong>ELIMINAR:</strong> {eliminar} ({eliminar/total*100:.1f}%)</p>
</div>

<h3>Resum global per esquema</h3>
<table class="kpi-table">
  <thead><tr><th>Esquema</th><th>Decisió</th><th>Score</th><th>Mida(GB)</th><th>Deps In</th><th>Jobs</th><th>APEX</th><th>Triggers</th><th>Invàlids</th></tr></thead>
  <tbody>{_build_all_schemas_html_rows(data)}</tbody>
</table>

<h3>Resum de consultes Q01..Q19</h3>
<p style="font-size:8pt;color:#555;">Agregat de totes les consultes sobre tots els esquemes analitzats.</p>
<table>
  <thead><tr><th width="22%">Consulta</th><th>Que valida</th><th width="15%">Esquemes amb dades</th><th width="10%">Total files</th></tr></thead>
  <tbody>{_build_queries_summary_html(data)}</tbody>
</table>

<h3>KPIs globals agregats</h3>
{_build_global_kpis_html(data, total_gb)}
""")
        elif sec_type == "ai_diagnostic":
            prompt = _build_deep_ai_prompt(profile, data)
            ai_text = _generate_ai_text(prompt, timeout=15)
            ai_html = _md_to_html(ai_text) if ai_text else "<p><em>Diagnostic no disponible.</em></p>"
            body_parts.append(f"""
<div class="insights-box">{ai_html}</div>
""")
        elif sec_type == "schema_details":
            schema_sections_html = ""
            for idx, schema_item in enumerate(data):
                schema = schema_item.get("username") or (schema_item.get("summary") or {}).get("USERNAME") or "N/A"
                summary = schema_item.get("summary") or {}
                decision = schema_item.get("audit_result", "PRECAUCIO")
                score = int(_to_float(schema_item.get("obsolescence_score")))
                in_deps = int(_to_float(summary.get("INBOUND_REFERENCES")))
                jobs = int(_to_float(summary.get("ACTIVE_JOBS")))
                apex_count = int(_to_float(summary.get("APEX_APPLICATIONS")))
                trigs = int(_to_float(summary.get("ENABLED_TRIGGERS")))
                invalids = len(schema_item.get("invalid_objects") or [])
                gb = _to_float(summary.get("SIZE_GB"))

                if score >= 100 and (in_deps + jobs + apex_count + trigs) == 0 and decision == "PRECAUCIO":
                    decision = "ELIMINAR"

                dec_color = _decision_color(decision)
                score_color = _score_color(score)
                score_bar = _build_score_bar_svg(score)

                # Scoring breakdown
                breakdown_rows = "".join(
                    f"<tr><td>{_safe_html(b.get('factor'))}</td>"
                    f"<td style='text-align:center;'><strong>{_safe_html(b.get('pts'))}</strong></td>"
                    f"<td>{_safe_html(b.get('desc'), 200)}</td></tr>"
                    for b in (schema_item.get("score_breakdown") or [])
                )
                breakdown_html = (
                    "<h4>Scoring breakdown</h4>"
                    "<table><thead><tr><th>Factor</th><th width='10%'>Punts</th><th>Explicació</th></tr></thead>"
                    f"<tbody>{breakdown_rows}</tbody></table>"
                ) if breakdown_rows else ""

                # Traçabilitat
                trace_rows = "".join(
                    f"<tr>"
                    f"<td>{_safe_html(q.get('query','N/A'))}</td>"
                    f"<td style='text-align:center;'>{_safe_html(q.get('status','N/A'))}</td>"
                    f"<td style='text-align:center;'>{q.get('rows',0)}</td>"
                    f"<td>{_safe_html(QUERY_EXPLANATIONS.get(q.get('query',''),'—'))}</td>"
                    f"</tr>"
                    for q in (schema_item.get("executed_queries") or [])
                )
                trace_html = (
                    "<h4>Traçabilitat Q01..Q19</h4>"
                    "<table><thead><tr><th width='22%'>Consulta</th><th width='12%'>Estat</th><th width='8%'>Files</th><th>Que valida</th></tr></thead>"
                    f"<tbody>{trace_rows}</tbody></table>"
                ) if trace_rows else ""

                # Resultats de consultes (amb files)
                query_results_html = "<h4>Resultats per consulta</h4>"
                has_results = False
                for q in (schema_item.get("executed_queries") or []):
                    qid = q.get("query", "N/A")
                    rows_data = _deep_query_payload(schema_item, qid)
                    if not rows_data:
                        continue
                    has_results = True
                    query_anchor = f"q_{idx}_{qid}"
                    query_results_html += (
                        f"<p id='{query_anchor}'><strong>{_safe_html(qid)}</strong> — {_safe_html(QUERY_EXPLANATIONS.get(qid, ''))}"
                        f" <em>({len(rows_data)} files)</em></p>"
                        + _build_html_rows_table(rows_data)
                        + "<br/>"
                    )
                if not has_results:
                    query_results_html += "<p><em>Sense resultats amb files per mostrar.</em></p>"

                # Dependències (fallback taula HTML)
                incoming = (schema_item.get("dependencies") or {}).get("incoming") or []
                outgoing_list = (schema_item.get("dependencies") or {}).get("outgoing") or []
                deps_html = _build_deps_html_table(incoming, outgoing_list)

                schema_sections_html += f"""
<h2 id="schema_{idx}" class="schema-section">Detall: Esquema {_safe_html(schema)}</h2>

<table class="kpi-table">
  <thead>
    <tr><th>Decisió</th><th>Score</th><th>Mida (GB)</th><th>Deps In</th><th>Jobs</th><th>APEX</th><th>Triggers</th><th>Invàlids</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><span class="badge" style="background:{dec_color}">{_safe_html(decision)}</span></td>
      <td><span class="badge" style="background:{score_color}">{score}%</span> {score_bar}</td>
      <td>{gb:.2f}</td><td>{in_deps}</td><td>{jobs}</td><td>{apex_count}</td><td>{trigs}</td><td>{invalids}</td>
    </tr>
  </tbody>
</table>

<h4>Dependències</h4>
{deps_html}

{breakdown_html}
{trace_html}
{query_results_html}

<p><strong>Recomanació operativa:</strong> {_safe_html(_recommendation(decision))}</p>
"""
            body_parts.append(schema_sections_html)
        elif sec_type == "risk_matrix":
            body_parts.append(f'<h2 id="{sec_id}">{_safe_html(sec_title)}</h2>')
            body_parts.append(_build_risk_matrix_html(data))
        elif sec_type == "action_plan":
            body_parts.append(f"""
<h2 id="{sec_id}">{_safe_html(sec_title)}</h2>
<ol>
  <li>Validar manualment esquemes <strong>NO ELIMINAR</strong> amb dependències entrants.</li>
  <li>Preparar pla de remediació per <strong>PRECAUCIO</strong> (finestra, proves, rollback).</li>
  <li>Executar checklist pre-drop per candidats <strong>ELIMINAR</strong> (backup → aprovació → traçabilitat).</li>
</ol>
""")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
</head>
<body>
{hf_html}

{"".join(body_parts)}

</body>
</html>"""

    buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.BytesIO(html_content.encode("utf-8")), dest=buffer, encoding="utf-8")
    if pisa_status.err:
        raise RuntimeError(f"Error generant PDF estàndard: {pisa_status.err}")
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# POST-CRQ REPORTS (Professional wrapping)
# ---------------------------------------------------------------------------

def _build_post_crq_checks_summary_html(summary_data: Dict) -> str:
    severity_counts = summary_data.get("findings_by_severity") or {}
    rows_html = "".join(
        f"<tr><td><strong>{_safe_html(sev)}</strong></td><td>{_safe_html(count)}</td></tr>"
        for sev, count in severity_counts.items()
    )
    return (
        "<h3>KPI per severitat</h3>"
        "<table><thead><tr><th>Severitat</th><th>Total troballes</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
    )


def _render_time_filter_label(time_filter: Dict[str, Any]) -> str:
    if not time_filter:
        return "Sense filtre temporal"
    start_date = time_filter.get("start_date") or "?"
    end_date = time_filter.get("end_date") or "?"
    if time_filter.get("preset"):
        return f"{time_filter.get('preset')} ({start_date} -> {end_date})"
    return f"{start_date} -> {end_date}"


def _build_post_crq_schema_changes_markdown(items: List[Dict[str, Any]]) -> List[str]:
    if not items:
        return []
    lines = [
        "## Darrera modificacio per esquema",
        "| Esquema | Darrera modificacio | Check origen |",
        "| --- | --- | --- |",
    ]
    for item in items:
        lines.append(
            f"| {item.get('schema')} | {item.get('last_modified_at') or 'No disponible'} | {item.get('source_check') or '-'} |"
        )
    lines.append("")
    return lines


def _post_crq_column_type(column_name: str) -> str:
    normalized = _slug(column_name).replace("-", "_")
    if "severitat" in normalized or "severity" in normalized:
        return "severity"
    if any(token in normalized for token in ("date", "data", "hora", "time", "timestamp")):
        return "datetime"
    if any(token in normalized for token in ("num", "count", "rows", "files", "size", "cache", "increment")):
        return "numeric"
    return "text"


def _post_crq_column_width_weight(column_name: str) -> float:
    normalized = _slug(column_name).replace("-", "_")
    if normalized in {"esquema", "schema"}:
        return 1.65
    if normalized in {"taula", "table", "taula_pare", "sequencia", "sequence", "objecte", "sinonim"}:
        return 2.2
    if normalized in {"index_1", "index_2", "constraint_fk", "nom_constraint", "objecte_desti", "propietari_desti"}:
        return 1.55
    if normalized in {"columnes_fk", "columna_lider_comuna", "descripcio", "codi"}:
        return 1.95
    if normalized in {"tipus_1", "tipus_2", "tipus", "tipus_constraint", "tipus_objecte"}:
        return 0.78
    if normalized in {"severitat", "severity", "num_files", "linia", "posicio", "nullable", "cache_actual", "increment_by_value", "cicle"}:
        return 0.48
    if any(token in normalized for token in ("darrera_estadistica", "data_modificacio", "data_invalidacio", "data_creacio", "last", "date", "data")):
        return 0.74
    if normalized in {"validada", "estat"}:
        return 0.58

    column_type = _post_crq_column_type(column_name)
    if column_type == "severity":
        return 0.68
    if column_type == "datetime":
        return 0.92
    if column_type == "numeric":
        return 0.78
    return 1.18


def _post_crq_column_min_width(column_name: str) -> float:
    normalized = _slug(column_name).replace("-", "_")
    if normalized in {"severitat", "severity", "num_files", "linia", "posicio", "nullable", "cache_actual", "increment_by_value", "cicle"}:
        return 4.4
    if normalized in {"tipus_1", "tipus_2", "tipus", "tipus_constraint", "tipus_objecte", "validada", "estat"}:
        return 5.0
    if any(token in normalized for token in ("data_modificacio", "darrera_estadistica", "data_invalidacio", "data_creacio", "date", "data")):
        return 6.4
    if normalized in {"esquema", "schema"}:
        return 8.4
    if normalized in {"taula", "table", "sequencia", "sequence", "objecte", "sinonim"}:
        return 12.2
    if normalized in {"columnes_fk", "columna_lider_comuna", "descripcio", "codi", "taula_pare"}:
        return 12.6
    return 6.0


def _post_crq_column_widths(columns: List[str]) -> List[str]:
    if not columns:
        return []
    weights = [_post_crq_column_width_weight(column) for column in columns]
    total_weight = sum(weights) or 1.0
    widths = [(weight / total_weight) * 100 for weight in weights]
    minimums = [_post_crq_column_min_width(column) for column in columns]
    widths = [max(width, minimums[index]) for index, width in enumerate(widths)]

    overflow = sum(widths) - 100.0
    while overflow > 0.01:
        adjustable = [index for index, width in enumerate(widths) if width - minimums[index] > 0.01]
        if not adjustable:
            break
        adjustable_total = sum(widths[index] - minimums[index] for index in adjustable) or 1.0
        for index in adjustable:
            reducible = widths[index] - minimums[index]
            reduction = min(reducible, overflow * (reducible / adjustable_total))
            widths[index] -= reduction
        overflow = sum(widths) - 100.0

    remaining = 100.0 - sum(widths)
    if remaining > 0.01:
        total_weights = sum(weights) or 1.0
        for index, weight in enumerate(weights):
            widths[index] += remaining * (weight / total_weights)

    return [f"{width:.2f}%" for width in widths]


def _build_post_crq_html_table(rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> str:
    if not rows:
        return "<p><em>Sense troballes per aquest check.</em></p>"

    ordered_columns = columns or list(rows[0].keys())
    column_widths = _post_crq_column_widths(ordered_columns)
    compact_class = " is-wide" if len(ordered_columns) >= 7 else ""
    colgroup = "".join(
        f"<col style='width:{column_widths[index]}'>"
        for index, column in enumerate(ordered_columns)
    )
    header = "".join(
        f"<th class='col-{_post_crq_column_type(column)}'>{_safe_html(column, None)}</th>"
        for column in ordered_columns
    )

    body_rows = []
    for row in rows:
        cells = []
        for column in ordered_columns:
            cell_type = _post_crq_column_type(column)
            value = row.get(column)
            rendered = _safe_html("-" if value in (None, "") else value, None)
            cells.append(f"<td class='col-{cell_type}'>{rendered}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    return (
        f"<table class='post-crq-detail-table{compact_class}'>"
        f"<colgroup>{colgroup}</colgroup>"
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        f"</table>"
    )


def build_post_crq_markdown(profile: str, report: Dict[str, Any], ai_active: Optional[bool] = None) -> str:
    if ai_active is None:
        ai_active = _ai_improvement_active()

    context = report.get("context") or {}
    summary = report.get("summary") or {}
    schema_last_modifications = report.get("schema_last_modifications") or summary.get("schema_last_modifications") or []
    results = report.get("results_by_check") or []
    time_filter = context.get("time_filter") or {}
    now = _report_now_text()

    md: List[str] = []
    md.append(f"# Informe Auditoria de Canvis Post-CRQ - Perfil: {profile}")
    md.append("")
    md.append(f"_Generat: {now} | Fitxer: {context.get('source_file')} | Checks: {summary.get('executed_checks')}_")
    md.append("")
    
    # Índex
    md.append("## Index")
    section_counter = 1
    structure = _DESIGN_AGENT.get_report_structure("post_crq")
    for section in structure:
        if section.get("condition") == "ai_active" and not ai_active:
            continue
        md.append(f"{section_counter}. [{section['title']}](#{section['id']})")
        section_counter += 1
    md.append("")

    for section in structure:
        sec_id = section["id"]
        sec_title = section["title"]
        sec_type = section["type"]
        
        if section.get("condition") == "ai_active" and not ai_active:
            continue
            
        if sec_type == "context":
            md.append(f"## {sec_title} {{#{sec_id}}}")
            md.append(f"- Perfil actiu: **{profile}**")
            md.append(f"- Fitxer origen: **{context.get('source_file')}**")
            md.append(f"- Mode temporal: **{time_filter.get('mode', 'preset')}**")
            if time_filter.get("preset"):
                md.append(f"- Període aplicat: **{_render_time_filter_label(time_filter)}**")
            if time_filter.get("start_date") and time_filter.get("end_date"):
                md.append(f"- Rang consultat: **{time_filter['start_date']} -> {time_filter['end_date']}**")
            md.append(f"- Dies enrere resolts: **{time_filter.get('days_back', 0)}**")
            if time_filter.get("resolved_on"):
                md.append(f"- Data de resolucio: **{time_filter.get('resolved_on')}**")
            md.append(f"- Esquemes: **{', '.join(context.get('schemas') or ['TOTS'])}**")
            md.append("")
            
        elif sec_type == "summary":
            md.append(f"## {sec_title} {{#{sec_id}}}")
            md.append(f"- **Checks executats**: {summary.get('executed_checks', 0)}")
            md.append(f"- **Checks amb troballes**: {summary.get('checks_with_findings', 0)}")
            md.append(f"- **Total de registres afectats**: {summary.get('total_findings', 0)}")
            md.append(f"- **Checks amb error**: {summary.get('checks_with_errors', 0)}")
            md.append(f"- **Esquemes amb canvis detectats**: {summary.get('schemas_with_detected_changes', 0)}")
            if summary.get("latest_change_at"):
                md.append(f"- **Ultima modificacio detectada**: {summary.get('latest_change_at')}")
            md.append("")
            md.append("Auditoria post-canvi amb KPIs clars i detall complet per check, sense truncament de files.")
            md.append("")
            md.append("### Troballes per severitat")
            for sev, count in (summary.get("findings_by_severity") or {}).items():
                md.append(f"- **{sev}**: {count}")
            md.append("")
            md.extend(_build_post_crq_schema_changes_markdown(schema_last_modifications))
            
        elif sec_type == "ai_diagnostic":
            md.append(f"## {sec_title} {{#{sec_id}}}")
            md.append("> _Analisi automatica de riscos post-canvi_")
            md.append("")
            prompt = _build_post_crq_ai_prompt(
                profile,
                results,
                intro="Ets un expert en QA i auditoria Oracle. Analitza aquests resultats",
            )
            md.append(_generate_ai_text(prompt) or "_IA no disponible._")
            md.append("")
            md.append("| Check | Titol | Severitat | Estat | Files |")
            md.append("| --- | --- | --- | --- | --- |")
            for item in results:
                md.append(
                    f"| {item.get('check_id')} | {item.get('title')} | {item.get('severitat')} | {item.get('status')} | {item.get('row_count')} |"
                )
            md.append("")
            
        elif sec_type == "findings_details":
            md.append(f"## {sec_title} {{#{sec_id}}}")
            for item in results:
                if int(item.get("row_count", 0)) > 0 or item.get("status") != "ok":
                    md.append(f"### {item.get('check_id')} - {item.get('title')}")
                    md.append(f"- Severitat: **{item.get('severitat')}** | Estat: **{item.get('status')}**")
                    if item.get("criteri"):
                        md.append(f"- Criteri: {item.get('criteri')}")
                    if item.get("temporal_column"):
                        md.append(f"- Columna temporal detectada: **{item.get('temporal_column')}**")
                    if item.get("error"):
                        md.append(f"- Error: `{item.get('error')}`")
                    md.append("")
                    md.append(_md_rows_table(item.get("rows") or [], max_rows=None))
                    md.append("")

    return "\n".join(md)


def build_post_crq_pdf(profile: str, report: Dict[str, Any], ai_active: Optional[bool] = None) -> bytes:
    if ai_active is None:
        ai_active = _ai_improvement_active()

    structure = _DESIGN_AGENT.get_report_structure("post_crq")

    context = report.get("context") or {}
    summary = report.get("summary") or {}
    schema_last_modifications = report.get("schema_last_modifications") or summary.get("schema_last_modifications") or []
    results = report.get("results_by_check") or []
    time_filter = context.get("time_filter") or {}
    now = _report_now_text()
    config = _DESIGN_AGENT.get_style_config()
    colors = _DESIGN_AGENT.colors
    footer_txt = "GESIN @ 2026"
    official_logo_path = Path(_DESIGN_AGENT.logo_path)
    official_logo_html = ""
    if official_logo_path.exists():
        official_logo_html = (
            f"<img src='{official_logo_path.resolve().as_posix()}' "
            "style='width:6.2cm;display:block;margin-bottom:12px;'/>"
        )
    cover_visual_path = Path(_DESIGN_AGENT.base_dir) / "resources" / "logo_oracle_audit.png"
    cover_visual_html = ""
    if cover_visual_path.exists():
        cover_visual_html = (
            f"<img src='{cover_visual_path.resolve().as_posix()}' "
            "style='width:4.4cm;height:4.4cm;display:block;margin-left:auto;margin-top:10px;'/>"
        )

    css = f"""
    @page portrait_template {{
        size: A4 portrait;
        margin: 3.2cm 1.2cm 1.7cm 1.2cm;
        @frame header {{
            -pdf-frame-content: header_content;
            top: 0.8cm;
            margin-left: 1.2cm;
            margin-right: 1.2cm;
            height: 2.2cm;
        }}
        @frame footer {{
            -pdf-frame-content: footer_content;
            bottom: 0.35cm;
            margin-left: 1.2cm;
            margin-right: 1.2cm;
            height: 0.95cm;
        }}
    }}
    @page landscape_template {{
        size: A4 landscape;
        margin: 2.8cm 1cm 1.55cm 1cm;
        @frame header {{
            -pdf-frame-content: header_content;
            top: 0.6cm;
            margin-left: 1cm;
            margin-right: 1cm;
            height: 2cm;
        }}
        @frame footer {{
            -pdf-frame-content: footer_content;
            bottom: 0.35cm;
            margin-left: 1cm;
            margin-right: 1cm;
            height: 0.95cm;
        }}
    }}
    body {{ font-family: {config['font_family']}; color: {colors['text_main']}; font-size: 8.8pt; line-height: 1.38; }}
    h1 {{ color: {colors['primary']}; font-size: 19pt; border-bottom: 2px solid {colors['primary']}; padding-bottom: 7px; margin: 6px 0 10px 0; -pdf-outline: true; -pdf-level: 0; }}
    h2 {{ color: {colors['text_main']}; font-size: 13.2pt; margin-top: 20px; border-bottom: 1px solid {colors['border']}; padding-bottom: 5px; -pdf-outline: true; -pdf-level: 1; }}
    h3 {{ color: {colors['secondary']}; font-size: 10.7pt; margin-top: 14px; margin-bottom: 5px; -pdf-outline: true; -pdf-level: 2; }}
    p, li {{ margin: 0 0 4px 0; }}

    #toc ul { list-style-type: none; padding-left: 0; }
    #toc li { margin-bottom: 12px; border-bottom: 1px solid #f1f5f9; padding-bottom: 4px; }
    #toc a { color: {colors['primary']}; text-decoration: none; }
    #toc .toc-sub { padding-left: 24px; font-size: 8.8pt; color: {colors['primary']}; margin-top: 4px; }

    table {{ width: 100%; border-collapse: collapse; margin: 10px 0 14px 0; table-layout: fixed; }}
    th {{ background: {config['table_header_bg']}; color: #ffffff; border: 1px solid #ffffff; padding: 7px 5px; font-size: 7.1pt; text-align: center; line-height: 1.08; overflow-wrap: anywhere; word-break: break-word; }}
    td {{ border: 1px solid {colors['border']}; padding: 6px 5px; font-size: 7.1pt; vertical-align: top; white-space: normal; word-wrap: break-word; overflow-wrap: break-word; line-height: 1.22; }}
    tr:nth-child(even) {{ background: #f8fafc; }}
    .cover-kicker {{ color: {colors['secondary']}; font-size: 8pt; text-transform: uppercase; letter-spacing: 0.9px; font-weight: bold; margin-top: 2px; }}
    .cover-subtitle {{ color: {colors['text_light']}; font-size: 8.2pt; margin-bottom: 8px; }}
    .lead-box {{ border-left: 4px solid {colors['primary']}; border-top: 1px solid {colors['border']}; border-right: 1px solid {colors['border']}; border-bottom: 1px solid {colors['border']}; background: #f6f9ff; padding: 12px 12px; margin: 12px 0 16px 0; }}
    .context-table td.label {{ width: 30%; font-weight: bold; color: {colors['secondary']}; background: #f8fafc; }}
    .context-table td.value {{ width: 70%; }}
    .summary-box {{ border: 1px solid {colors['border']}; background: #fbfcfe; padding: 10px; margin: 10px 0 14px 0; }}
    .compact-table th {{ font-size: 7.2pt; }}
    .compact-table td {{ font-size: 6.9pt; }}
    .kpi-table td.metric {{ font-weight: bold; color: {colors['secondary']}; background: #f8fafc; }}
    .kpi-table td.value {{ text-align: center; font-size: 8.2pt; font-weight: bold; }}
    .section-note {{ color: {colors['text_light']}; font-size: 7.9pt; margin-top: -3px; }}
    .detail-meta {{ color: {colors['text_main']}; font-size: 8pt; margin-bottom: 6px; }}
    .cover-page {{ padding-top: 0.25cm; }}
    .cover-title {{ font-size: 24pt; color: {colors['primary']}; margin: 8px 0 10px 0; }}
    .cover-panel {{ border: 1px solid {colors['border']}; background: #f8fbff; padding: 12px; margin: 14px 0; }}
    .cover-layout td {{ border: none; vertical-align: top; padding: 0; }}
    .cover-hero {{ border: 1px solid {colors['border']}; background: #f8fbff; padding: 12px 14px; }}
    .cover-badge {{ display: inline-block; background: #e8f0ff; color: {colors['secondary']}; font-weight: bold; padding: 4px 8px; border: 1px solid #cfe0ff; font-size: 7.8pt; margin-bottom: 8px; }}
    .cover-mini-grid td {{ border: 1px solid {colors['border']}; background: #ffffff; padding: 8px; }}
    .cover-mini-grid .label {{ color: {colors['text_light']}; font-size: 7.4pt; text-transform: uppercase; }}
    .cover-mini-grid .value {{ color: {colors['secondary']}; font-size: 10pt; font-weight: bold; }}
    .index-list {{ margin: 6px 0 0 18px; }}
    .index-list li {{ margin-bottom: 5px; }}
    .post-crq-detail-table th.col-severity, .post-crq-detail-table td.col-severity,
    .post-crq-detail-table th.col-numeric, .post-crq-detail-table td.col-numeric,
    .post-crq-detail-table th.col-datetime, .post-crq-detail-table td.col-datetime {{ text-align: center; }}
    .post-crq-detail-table th {{ overflow-wrap: anywhere; word-break: break-word; }}
    .post-crq-detail-table td {{ line-height: 1.18; }}
    .post-crq-detail-table.is-wide th {{ font-size: 5.7pt; padding: 4px 2px; }}
    .post-crq-detail-table.is-wide td {{ font-size: 5.95pt; padding: 4px 2px; }}
    .detail-section {{ margin-bottom: 12px; border-top: 2px solid {colors['border']}; padding-top: 8px; }}
    .detail-section h3 {{ margin-top: 0; }}
    #footer_content {{ font-size: 7.7pt; color: {colors['text_light']}; text-align: right; border-top: 1px solid {colors['border']}; padding-top: 4px; }}
    """

    # Construcció de l'índex (TOC) per al PDF
    toc_html = ["<ul>"]
    section_counter = 1
    for section in structure:
        if section.get("condition") == "ai_active" and not ai_active:
            continue
        
        # Excloure Portada i Index de l'índex real
        if section["id"] in ["portada", "index"] or section["title"].lower() in ["portada", "index", "índex"]:
            continue

        toc_html.append(f'<li><a href="#{section["id"]}">{section_counter}. {section["title"]}</a></li>')
        section_counter += 1
        
        if section["type"] == "findings_details":
            for item in results:
                if int(item.get("row_count", 0)) > 0 or item.get("status") != "ok":
                    cid = item.get("check_id", "N/A")
                    c_title = item.get("title") or ""
                    slug = f"check_{_slug(cid)}"
                    # Mateix tamany i color (via CSS toc-sub), incloent descripció
                    toc_html.append(f'<li class="toc-sub"><a href="#{slug}">- {cid}: {_safe_html(c_title, 60)}</a></li>')

    toc_html.append("</ul>")
    toc_links = "".join(toc_html)

    body_parts = []
    
    # Init HTML structure and cover page
    body_parts.append(f"""
<pdf:nexttemplate name="portrait_template" />
{_build_pdf_header_footer(profile, now, footer_txt)}

<div class="cover-page">
  {official_logo_html}
  <table class="cover-layout">
    <tr>
      <td width="68%">
        <div class="cover-kicker">Auditoria BBDD - Control post-CRQ</div>
        <div class="cover-title">Informe de Validacio de Canvis</div>
        <p class="cover-subtitle">Document executiu i tecnic per revisar troballes de qualitat en Oracle amb detall complet per check.</p>
        <div class="cover-hero">
          <span class="cover-badge">CONTROL DE QUALITAT POST-CRQ</span>
          <p><strong>Perfil:</strong> {_safe_html(profile)}<br/>
          <strong>Generat:</strong> {now}<br/>
          <strong>Font de consultes:</strong> {_safe_html(context.get('source_file') or '-')}<br/>
          <strong>Rang temporal:</strong> {_safe_html((time_filter.get('start_date') or '?') + ' -> ' + (time_filter.get('end_date') or '?'), None)}</p>
        </div>
      </td>
      <td width="32%" align="right">{cover_visual_html}</td>
    </tr>
  </table>
  <table class="cover-mini-grid">
    <tr>
      <td width="33%"><div class="label">Checks executats</div><div class="value">{summary.get('executed_checks', 0)}</div></td>
      <td width="33%"><div class="label">Troballes</div><div class="value">{summary.get('total_findings', 0)}</div></td>
      <td width="34%"><div class="label">Ultim canvi detectat</div><div class="value">{_safe_html(summary.get('latest_change_at') or 'N/D', None)}</div></td>
    </tr>
  </table>
  <div class="lead-box">
    <p><strong>Document de validacio post-canvi</strong></p>
    <p>Inclou context de l'auditoria, resum executiu, KPI per severitat, darrera modificacio per esquema i detall complet de troballes sense truncament.</p>
  </div>
</div>

<pdf:nextpage />

<h1>Index i Checks de l'Informe</h1>
<div class="summary-box">
  {toc_links}
</div>

<pdf:nextpage />
""")

    for section in structure:
        sec_id = section["id"]
        sec_title = section["title"]
        sec_type = section["type"]

        if section.get("condition") == "ai_active" and not ai_active:
            continue

        if sec_type == "context":
            context_rows = "".join([
                f"<tr><td class='label'>Fitxer origen</td><td class='value'>{_safe_html(context.get('source_file'))}</td></tr>",
                f"<tr><td class='label'>Mode temporal</td><td class='value'>{_safe_html(time_filter.get('mode', 'preset'))}</td></tr>",
                f"<tr><td class='label'>Període aplicat</td><td class='value'>{_safe_html(_render_time_filter_label(time_filter), None)}</td></tr>",
                f"<tr><td class='label'>Rang consultat</td><td class='value'>{_safe_html((time_filter.get('start_date') or '?') + ' -> ' + (time_filter.get('end_date') or '?'), None)}</td></tr>",
                f"<tr><td class='label'>Dies enrere</td><td class='value'>{_safe_html(time_filter.get('days_back', 0))}</td></tr>",
                f"<tr><td class='label'>Data de resolucio</td><td class='value'>{_safe_html(time_filter.get('resolved_on') or '-', None)}</td></tr>",
                f"<tr><td class='label'>Esquemes</td><td class='value'>{_safe_html(', '.join(context.get('schemas') or ['TOTS']), None)}</td></tr>",
            ])
            body_parts.append(f"""
<h2 id="{sec_id}">{_safe_html(sec_title)}</h2>
<table class="context-table compact-table">
  <tbody>{context_rows}</tbody>
</table>
""")
        elif sec_type == "summary":
            kpi_rows = "".join([
                f"<tr><td class='metric'>Checks executats</td><td class='value'>{summary.get('executed_checks', 0)}</td></tr>",
                f"<tr><td class='metric'>Checks amb troballes</td><td class='value'>{summary.get('checks_with_findings', 0)}</td></tr>",
                f"<tr><td class='metric'>Total registres afectats</td><td class='value'>{summary.get('total_findings', 0)}</td></tr>",
                f"<tr><td class='metric'>Checks amb error</td><td class='value'>{summary.get('checks_with_errors', 0)}</td></tr>",
                f"<tr><td class='metric'>Esquemes amb canvis detectats</td><td class='value'>{summary.get('schemas_with_detected_changes', 0)}</td></tr>",
                f"<tr><td class='metric'>Ultima modificacio detectada</td><td class='value'>{_safe_html(summary.get('latest_change_at') or 'No disponible', None)}</td></tr>",
            ])
            schema_changes_html = ""
            if schema_last_modifications:
                rows_html = "".join(
                    f"<tr><td>{_safe_html(item.get('schema'), None)}</td><td>{_safe_html(item.get('last_modified_at') or 'No disponible', None)}</td><td>{_safe_html(item.get('source_check') or '-', None)}</td></tr>"
                    for item in schema_last_modifications
                )
                schema_changes_html = (
                    "<h3>Darrera modificacio per esquema</h3>"
                    "<p class='section-note'>Data i hora mes recents detectades als resultats de la revisio.</p>"
                    "<table class='compact-table'><thead><tr><th>Esquema</th><th>Darrera modificacio</th><th>Check origen</th></tr></thead>"
                    f"<tbody>{rows_html}</tbody></table>"
                )
            body_parts.append(f"""
<h2 id="{sec_id}">{_safe_html(sec_title)}</h2>
<div class="lead-box">
  <p>Visio resumida de l'auditoria post-canvi amb KPIs clars, rang temporal explicit i detall complet per check.</p>
</div>
<table class="kpi-table compact-table"><tbody>{kpi_rows}</tbody></table>
{_build_post_crq_checks_summary_html(summary)}
{schema_changes_html}
""")
        elif sec_type == "ai_diagnostic":
            prompt = _build_post_crq_ai_prompt(
                profile,
                results,
                intro="Ets auditor Oracle. Analitza aquests canvis post-CRQ",
            )
            ai_text = _generate_ai_text(prompt, timeout=15)
            ai_content = f"<div class='summary-box'>{_md_to_html(ai_text)}</div>" if ai_text else "<p>IA no disponible.</p>"
            body_parts.append(f"""
<h2 id="{sec_id}">{_safe_html(sec_title)}</h2>
{ai_content}
<p class="section-note">Relacio de checks executats amb el seu estat i volum de troballes.</p>
<table class="compact-table">
  <thead><tr><th>Check</th><th>Titol</th><th>Severitat</th><th>Estat</th><th>Files</th></tr></thead>
  <tbody>{trace_rows}</tbody>
</table>
""")
        elif sec_type == "findings_details":
            detail_html = []
            for item in results:
                if int(item.get("row_count", 0)) > 0 or item.get("status") != "ok":
                    error_html = ""
                    if item.get("error"):
                        error_html = f"<p><strong>Error:</strong> {_safe_html(item.get('error'), None)}</p>"
                    cid = item.get('check_id', 'none')
                    page_break = "" if not detail_html else "<pdf:nextpage />"
                    detail_html.append(
                        f"{page_break}<div class='detail-section'>"
                        f"<h3 id='check_{_slug(cid)}'>{_safe_html(cid, None)} - {_safe_html(item.get('title'), None)}</h3>"
                        f"<p class='detail-meta'><strong>Severitat:</strong> {_safe_html(item.get('severitat'), None)} | "
                        f"<strong>Estat:</strong> {_safe_html(item.get('status'), None)} | "
                        f"<strong>Files:</strong> {item.get('row_count', 0)}</p>"
                        f"<p><strong>Criteri:</strong> {_safe_html(item.get('criteri') or '-', None)}</p>"
                        f"{error_html}"
                        f"{_build_post_crq_html_table(item.get('rows') or [], item.get('columns') or [])}"
                        f"</div>"
                    )
            body_parts.append(f"""
<pdf:nexttemplate name="landscape_template" />
<pdf:nextpage />
<h2 id="{sec_id}">{_safe_html(sec_title)}</h2>
<p class="section-note">Cada check arrenca en una pàgina neta i la taula reparteix l'espai segons el contingut real de les columnes.</p>
{''.join(detail_html)}
""")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>{css}</style>
</head>
<body>
{"".join(body_parts)}
</body>
</html>
"""

    buffer = io.BytesIO()
    pisa_tmp_dir = Path(_DESIGN_AGENT.base_dir) / "tmp" / "pisa-font-cache"
    pisa_tmp_dir.mkdir(parents=True, exist_ok=True)
    old_tmp = os.environ.get("TMP")
    old_temp = os.environ.get("TEMP")
    os.environ["TMP"] = str(pisa_tmp_dir)
    os.environ["TEMP"] = str(pisa_tmp_dir)
    try:
        pisa_status = pisa.CreatePDF(io.BytesIO(html_content.encode("utf-8")), dest=buffer, encoding="utf-8")
    finally:
        if old_tmp is None:
            os.environ.pop("TMP", None)
        else:
            os.environ["TMP"] = old_tmp
        if old_temp is None:
            os.environ.pop("TEMP", None)
        else:
            os.environ["TEMP"] = old_temp
    if pisa_status.err:
        raise RuntimeError(f"Error generant PDF Post-CRQ: {pisa_status.err}")
    buffer.seek(0)
    return buffer.getvalue()
