from __future__ import annotations

import argparse
import difflib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from src.api.post_crq_audit import parse_post_crq_checks, resolve_post_crq_markdown_path
from src.core.check_explanation_catalog import (
    load_check_explanation_catalog_from_path,
    render_check_explanation_catalog_entry,
)
from src.core.dba_query_explainer import DBAExplainRequest, DBAQueryExplainer
from src.core.sqlite_paths import resolve_sqlite_path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _txt_path() -> Path:
    return _project_root() / "consultes_post_crq.txt"


def _explanation_path() -> Path:
    return _project_root() / "EXPLICACION_CHECKS_CONTROL_QUALITAT_CRQ.md"


def _load_txt_lines(path: Path) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        check_id = line.split("|", 1)[0].strip().upper()
        if check_id.startswith("CHECK_"):
            result[check_id] = line.strip()
    return result


def _unified_diff(current: str, proposed: str, fromfile: str, tofile: str) -> str:
    current_lines = current.strip().splitlines()
    proposed_lines = proposed.strip().splitlines()
    diff = list(
        difflib.unified_diff(
            current_lines,
            proposed_lines,
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        )
    )
    return "\n".join(diff) if diff else "(sense diferències)"


def _load_db_context(db_path: str, check_id: str) -> Optional[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        check = conn.execute(
            "SELECT * FROM audit_checks WHERE check_id = ? AND actiu = 1",
            (check_id,),
        ).fetchone()
        if not check:
            return None
        current = conn.execute(
            "SELECT * FROM consulta_versions WHERE check_id = ? AND es_vigent = 1 ORDER BY versio DESC LIMIT 1",
            (check_id,),
        ).fetchone()
        previous = conn.execute(
            "SELECT * FROM consulta_versions WHERE check_id = ? AND es_vigent = 0 ORDER BY versio DESC LIMIT 1",
            (check_id,),
        ).fetchone()
    if not current:
        return None
    return {
        "check": dict(check),
        "current": dict(current),
        "previous": dict(previous) if previous else None,
    }


def build_preview_report(check_ids: Optional[Iterable[str]] = None) -> Path:
    db_path = resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db")
    markdown_checks = {item["check_id"]: item for item in parse_post_crq_checks(resolve_post_crq_markdown_path())}
    explanation_catalog = load_check_explanation_catalog_from_path(_explanation_path())
    txt_lines = _load_txt_lines(_txt_path())
    explainer = DBAQueryExplainer(db_path=db_path)

    selected_ids = [check_id.upper() for check_id in (check_ids or markdown_checks.keys()) if check_id.upper() in markdown_checks]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = _project_root() / "output" / "ai-check-preview"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"ai_check_preview_{timestamp}.md"

    lines: List[str] = [
        "# Preview IA no destructiva de checks",
        "",
        f"- Generat: {datetime.now().isoformat(timespec='seconds')}",
        f"- Checks analitzats: {len(selected_ids)}",
        "- Mode: comparació sense escriure cap canvi a la BBDD ni als fitxers operatius.",
        "",
    ]

    summary_rows: List[str] = []
    detail_sections: List[str] = []

    for check_id in selected_ids:
        context = _load_db_context(db_path, check_id)
        if not context:
            summary_rows.append(f"| {check_id} | ERROR | No trobat a SQLite | - | - |")
            continue

        check = context["check"]
        current_version = context["current"]
        previous_version = context["previous"]

        params = [part.strip() for part in (check.get("parametres") or "").split(",") if part.strip()]
        request = DBAExplainRequest(
            check_id=check_id,
            titol=check.get("titol") or markdown_checks[check_id]["title"],
            severitat=check.get("severitat_base") or markdown_checks[check_id].get("severitat_base") or "Mitjà",
            sql_nou=current_version["sql_text"],
            versio_nova=current_version["versio"],
            parametres=params,
            sql_anterior=previous_version["sql_text"] if previous_version else None,
            context_check=check.get("context_check") or markdown_checks[check_id].get("criteri") or "",
            tipus=check.get("tipus") or "SQL",
        )

        try:
            response = explainer.explain(request)
        except Exception as exc:
            summary_rows.append(f"| {check_id} | ERROR | {str(exc).replace('|', '/')} | - | - |")
            continue

        current_expl = (
            render_check_explanation_catalog_entry(explanation_catalog[check_id])
            if check_id in explanation_catalog
            else "(sense secció actual)"
        )
        current_md_block = f"```sql\n{current_version['sql_text'].strip()}\n```"
        current_txt_line = txt_lines.get(check_id, "(sense línia actual)")

        expl_changed = "Sí" if current_expl.strip() != response.explicacio_check_text.strip() else "No"
        md_changed = "Sí" if current_md_block.strip() != response.bloc_auditoria_md.strip() else "No"
        txt_changed = "Sí" if current_txt_line.strip() != response.linia_consultes_txt.strip() else "No"

        summary_rows.append(
            f"| {check_id} | OK | {expl_changed} | {md_changed} | {txt_changed} |"
        )

        detail_sections.extend(
            [
                f"## {check_id}",
                "",
                f"- Explicació funcional diferent: **{expl_changed}**",
                f"- Bloc `auditoria_post_crq.md` diferent: **{md_changed}**",
                f"- Línia `consultes_post_crq.txt` diferent: **{txt_changed}**",
                "",
                "### Diff explicació funcional",
                "```diff",
                _unified_diff(current_expl, response.explicacio_check_text, "actual", "ia"),
                "```",
                "",
                "### Diff bloc auditoria_post_crq.md",
                "```diff",
                _unified_diff(current_md_block, response.bloc_auditoria_md, "actual", "ia"),
                "```",
                "",
                "### Diff línia consultes_post_crq.txt",
                "```diff",
                _unified_diff(current_txt_line, response.linia_consultes_txt, "actual", "ia"),
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## Resum",
            "",
            "| Check | Estat | Explicació diferent | MD diferent | TXT diferent |",
            "| --- | --- | --- | --- | --- |",
            *summary_rows,
            "",
            *detail_sections,
        ]
    )
    report_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview no destructiva de regeneració IA per checks.")
    parser.add_argument("--check-id", action="append", dest="check_ids", help="CHECK_xx concret a analitzar. Es pot repetir.")
    args = parser.parse_args()

    report_path = build_preview_report(args.check_ids)
    print(report_path)


if __name__ == "__main__":
    main()
