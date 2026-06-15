from __future__ import annotations

import html
import io
from typing import Any, Dict, List

from xhtml2pdf import pisa

from src.core.time_utils import utc_now


def _safe(value: Any) -> str:
    return html.escape(str(value if value is not None else "-"))


def _generated_at_text() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M")


def _render_table(title: str, columns: List[str], rows: List[Dict[str, Any]], keys: List[str]) -> str:
    header_html = "".join(f"<th>{_safe(column)}</th>" for column in columns)
    body_rows = []
    for row in rows or []:
        cells = "".join(f"<td>{_safe(row.get(key))}</td>" for key in keys)
        body_rows.append(f"<tr>{cells}</tr>")
    if not body_rows:
        body_rows.append(f"<tr><td colspan=\"{len(columns)}\">Sense dades per al període seleccionat.</td></tr>")
    return f"""
    <div class="section">
      <h2>{_safe(title)}</h2>
      <table>
        <thead><tr>{header_html}</tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </div>
    """


def build_automation_analytics_monthly_pdf(
    *,
    month: str,
    overview: Dict[str, Any],
    lots: List[Dict[str, Any]],
    schemas: List[Dict[str, Any]],
    checks: List[Dict[str, Any]],
) -> bytes:
    generated_at = _generated_at_text()
    summary_cards = [
        ("Execucions", overview.get("runs", 0)),
        ("Troballes totals", overview.get("total_findings", 0)),
        ("Lots amb troballes", overview.get("lots_with_findings", 0)),
        ("Checks amb errors", overview.get("checks_with_errors", 0)),
    ]
    cards_html = "".join(
        f"""
        <div class="card">
          <div class="card-label">{_safe(label)}</div>
          <div class="card-value">{_safe(value)}</div>
        </div>
        """
        for label, value in summary_cards
    )

    html_content = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          @page {{
            size: A4;
            margin: 1.5cm;
          }}
          body {{
            font-family: Helvetica;
            color: #1e293b;
            font-size: 10pt;
          }}
          h1 {{
            color: #b91c1c;
            font-size: 22pt;
            margin-bottom: 6px;
            border-bottom: 2px solid #fecaca;
            padding-bottom: 8px;
          }}
          h2 {{
            color: #0f172a;
            font-size: 13pt;
            margin: 20px 0 8px 0;
          }}
          p {{
            line-height: 1.45;
          }}
          .muted {{
            color: #64748b;
            font-size: 9pt;
          }}
          .cards {{
            margin-top: 16px;
            margin-bottom: 18px;
          }}
          .card {{
            display: inline-block;
            width: 23%;
            min-height: 54px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 10px 12px;
            margin-right: 1%;
          }}
          .card-label {{
            font-size: 8pt;
            text-transform: uppercase;
            color: #64748b;
            margin-bottom: 6px;
          }}
          .card-value {{
            font-size: 18pt;
            font-weight: bold;
            color: #0f172a;
          }}
          .section {{
            margin-top: 12px;
          }}
          table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
          }}
          th {{
            background: #fee2e2;
            color: #7f1d1d;
            text-align: left;
            font-size: 8pt;
            text-transform: uppercase;
            padding: 8px 6px;
            border: 1px solid #fecaca;
          }}
          td {{
            padding: 7px 6px;
            border: 1px solid #e2e8f0;
            vertical-align: top;
          }}
        </style>
      </head>
      <body>
        <h1>Dashboard mensual d'automatitzacions</h1>
        <p class="muted">Mes analitzat: {_safe(month)} | Generat: {_safe(generated_at)}</p>
        <p>
          Resum analític agregat de les execucions Post-CRQ desades a la base de dades,
          agrupat per lot, esquema i tipus de check.
        </p>
        <div class="cards">{cards_html}</div>
        {_render_table("Lots", ["Lot", "Execucions", "Troballes totals", "Runs amb troballes"], lots, ["lot", "runs", "total_findings", "runs_with_findings"])}
        {_render_table("Esquemes", ["Esquema", "Lot", "Execucions", "Troballes totals", "Checks totals"], schemas, ["schema_name", "lot", "runs", "total_findings", "total_checks"])}
        {_render_table("Checks", ["Check", "Títol", "Severitat", "Execucions", "Troballes totals", "Lots afectats", "Esquemes afectats"], checks, ["check_id", "title", "severity", "runs", "total_findings", "affected_lots", "affected_schemas"])}
      </body>
    </html>
    """

    buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.BytesIO(html_content.encode("utf-8")), dest=buffer, encoding="utf-8")
    if pisa_status.err:
        raise RuntimeError(f"Error generant PDF analític: {pisa_status.err}")
    return buffer.getvalue()
