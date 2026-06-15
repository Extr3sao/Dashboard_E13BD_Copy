import copy
import io
import html
import datetime as dt
import logging
import os
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.core.check_explanation_catalog import load_check_explanation_catalog


CARD_BORDER = colors.HexColor("#d7e2f3")
CARD_FILL = colors.HexColor("#f7faff")
PRIMARY = colors.HexColor("#1f4aa7")
PRIMARY_SOFT = colors.HexColor("#edf3ff")
TEXT = colors.HexColor("#223047")
MUTED = colors.HexColor("#5a6880")
CRITICAL = colors.HexColor("#d63031")
CRITICAL_SOFT = colors.HexColor("#fff1f1")
MEDIUM = colors.HexColor("#e67e22")
MEDIUM_SOFT = colors.HexColor("#fff5eb")
LOW = colors.HexColor("#3b82f6")
LOW_SOFT = colors.HexColor("#eef5ff")
SUCCESS = colors.HexColor("#16a34a")
SUCCESS_SOFT = colors.HexColor("#effaf2")
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
logger = logging.getLogger(__name__)


def _normalize_lot_code(value: Any) -> str:
    text = _normalize_text(value).strip()
    return text.upper()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_pdf_fonts() -> None:
    global FONT_REGULAR, FONT_BOLD
    if FONT_REGULAR != "Helvetica":
        return

    local_fonts = _project_root() / "resources" / "fonts"
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    font_candidates = [
        (windir / "Fonts" / "segoeui.ttf", windir / "Fonts" / "segoeuib.ttf"),
        (windir / "Fonts" / "arial.ttf", windir / "Fonts" / "arialbd.ttf"),
        (local_fonts / "arial.ttf", local_fonts / "arialbd.ttf"),
        (windir / "Fonts" / "calibri.ttf", windir / "Fonts" / "calibrib.ttf"),
        (local_fonts / "NotoSans-Regular.ttf", local_fonts / "NotoSans-Bold.ttf"),
    ]

    for regular_path, bold_path in font_candidates:
        if regular_path.exists() and bold_path.exists():
            pdfmetrics.registerFont(TTFont("OracleAuditExp-Regular", str(regular_path)))
            pdfmetrics.registerFont(TTFont("OracleAuditExp-Bold", str(bold_path)))
            pdfmetrics.registerFontFamily(
                "OracleAuditExp",
                normal="OracleAuditExp-Regular",
                bold="OracleAuditExp-Bold",
                italic="OracleAuditExp-Regular",
                boldItalic="OracleAuditExp-Bold",
            )
            addMapping("OracleAuditExp", 0, 0, "OracleAuditExp-Regular")
            addMapping("OracleAuditExp", 1, 0, "OracleAuditExp-Bold")
            addMapping("OracleAuditExp", 0, 1, "OracleAuditExp-Regular")
            addMapping("OracleAuditExp", 1, 1, "OracleAuditExp-Bold")
            FONT_REGULAR = "OracleAuditExp-Regular"
            FONT_BOLD = "OracleAuditExp-Bold"
            return


def _cover_path() -> Path | None:
    candidate = _project_root() / "logo" / "portada.png"
    return candidate if candidate.exists() else None


def _normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    text = html.unescape(text)
    replacements = {
        "Ã€": "À",
        "Ã‰": "É",
        "Ãˆ": "È",
        "Ã": "Í",
        "Ã’": "Ò",
        "Ã“": "Ó",
        "Ãš": "Ú",
        "Ãœ": "Ü",
        "Ã ": "à",
        "Ã¡": "á",
        "Ã¨": "è",
        "Ã©": "é",
        "Ã­": "í",
        "Ã²": "ò",
        "Ã³": "ó",
        "Ãº": "ú",
        "Ã¼": "ü",
        "Ã§": "ç",
        "Ã±": "ñ",
        "Â·": "·",
        "â€“": "-",
        "â€”": "-",
        "â€˜": "'",
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
    }
    for _ in range(2):
        try:
            if any(marker in text for marker in ("Ã", "Â", "â€", "â†")):
                candidate = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
                if candidate:
                    text = candidate
                    continue
        except (UnicodeEncodeError, UnicodeDecodeError) as exc:
            logger.debug("Experimental PDF text normalization fallback failed", exc_info=exc)
        break
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = (
        text
        .replace("SEQ??NCIES", "SEQÜÈNCIES")
        .replace("seq??ncies", "seqüències")
        .replace("Seq??ncies", "Seqüències")
        .replace("seq?ncies", "seqüències")
        .replace("Seq?ncies", "Seqüències")
        .replace("?NDEX", "ÍNDEX")
        .replace("?ndex", "índex")
        .replace("l'?s", "l'ús")
        .replace("?s real", "ús real")
        .replace("inserci?", "inserció")
        .replace("execuci?", "execució")
        .replace("validaci?", "validació")
        .replace("resoluci?", "resolució")
        .replace("correcci?", "correcció")
        .replace("distribuci?", "distribució")
        .replace("degradaci?", "degradació")
    )
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split())


def _safe(value: Any, fallback: str = "-") -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return fallback
    normalized = (
        normalized
        .replace("Cr?tic", "Crític")
        .replace("Mitj?", "Mitjà")
        .replace("Catal?", "Català")
        .replace("Per?ode", "Període")
        .replace("An?lisi", "Anàlisi")
        .replace("Validaci?", "Validació")
        .replace("Acci?", "Acció")
        .replace("Incid?ncies", "Incidències")
        .replace("incid?ncies", "incidències")
        .replace("P?gina", "Pàgina")
        .replace("?NDEX", "ÍNDEX")
        .replace("?ndex", "índex")
        .replace("Â·", "·")
        .replace("â€¦", "…")
        .replace("SEQ?NCIES", "SEQÜÈNCIES")
        .replace("SEQ??NCIES", "SEQÜÈNCIES")
        .replace("Seq?ncies", "Seqüències")
        .replace("seq?ncies", "seqüències")
    )
    escaped = html.escape(normalized, quote=False)
    return "".join(character if ord(character) < 128 else f"&#{ord(character)};" for character in escaped)


def _compact_text(value: Any, *, max_length: int = 220) -> str:
    text = _normalize_text(value)
    if not text:
        return "-"
    sentences = [sentence.strip() for sentence in text.split(".") if sentence.strip()]
    compact = f"{sentences[0]}." if sentences else text
    if len(compact) <= max_length:
        return _safe(compact)
    return _safe(f"{compact[: max_length - 1].rstrip(' ,;:-')}…")

def _humanize_duration_ms(value: Any) -> str:
    try:
        ms = int(float(value or 0))
    except (TypeError, ValueError):
        return "-"
    if ms < 1000:
        return f"{ms} ms"
    seconds = ms / 1000.0
    if seconds < 60:
        return f"{seconds:.2f} s".replace(".", ",")
    minutes = int(seconds // 60)
    remaining = int(round(seconds % 60))
    return f"{minutes} min {remaining} s"

def _time_window_label(report: Dict[str, Any]) -> str:
    execution_parameters = (report.get("report_model") or {}).get("execution_parameters") or {}
    time_window = execution_parameters.get("time_window") or {}
    start_at = _format_display_datetime(time_window.get("start_at") or time_window.get("range_start_at") or time_window.get("start_date"))
    end_at = _format_display_datetime(time_window.get("end_at") or time_window.get("range_end_at") or time_window.get("end_date"))
    if start_at and end_at:
        return f"{start_at} - {end_at}"
    return "-"


def _format_display_datetime(value: Any) -> str:
    text = _safe(value, "")
    if not text:
        return "-"
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                parsed = dt.datetime.strptime(text, pattern)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return text
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%d/%m/%Y %H:%M")


def _time_filter_label(report: Dict[str, Any]) -> str:
    context_filter = (report.get("context") or {}).get("time_filter") or {}
    start_raw = context_filter.get("range_start_at") or context_filter.get("start_at") or context_filter.get("start_date")
    end_raw = context_filter.get("range_end_at") or context_filter.get("end_at") or context_filter.get("end_date")
    start_label = _format_display_datetime(start_raw)
    end_label = _format_display_datetime(end_raw)
    if start_label != "-" and end_label != "-":
        return f"{start_label} - {end_label}"
    return "-"


def _validation_issue(code: str, title: str, message: str, *, severity: str = "warning") -> Dict[str, str]:
    return {"code": code, "title": title, "message": message, "severity": severity}


def _collect_report_strings(value: Any) -> List[str]:
    items: List[str] = []
    if isinstance(value, dict):
        for current_value in value.values():
            items.extend(_collect_report_strings(current_value))
    elif isinstance(value, list):
        for current_value in value:
            items.extend(_collect_report_strings(current_value))
    elif value is not None:
        text = _normalize_text(value)
        if text:
            items.append(text)
    return items


def _validate_post_crq_experimental_report(profile: str, report: Dict[str, Any]) -> List[Dict[str, str]]:
    report_model = report.get("report_model") or {}
    execution_parameters = report_model.get("execution_parameters") or {}
    context = report.get("context") or {}
    issues: List[Dict[str, str]] = []

    requested_profile = _normalize_text(profile).strip().upper()
    report_profile = _normalize_text(execution_parameters.get("profile") or context.get("profile")).strip().upper()
    if requested_profile and report_profile and requested_profile != report_profile:
        issues.append(
            _validation_issue(
                "PROFILE_MISMATCH",
                "Perfil inconsistent",
                f"El perfil sol·licitat és {requested_profile}, però el report_model declara {report_profile}.",
                severity="error",
            )
        )

    requested_window = _time_filter_label(report)
    report_window = _time_window_label(report)
    if requested_window != "-" and report_window != "-" and requested_window != report_window:
        issues.append(
            _validation_issue(
                "TIME_WINDOW_MISMATCH",
                "Finestra temporal inconsistent",
                f"La finestra consultada del context ({requested_window}) no coincideix amb la del report_model ({report_window}).",
                severity="error",
            )
        )

    report_strings = _collect_report_strings(report_model)
    if any("Objecte Oracle" in item or "OBJECTE ORACLE" in item for item in report_strings):
        issues.append(
            _validation_issue(
                "PLACEHOLDER_OBJECT",
                "Placeholder detectat",
                "Encara hi ha textos de reserva com 'Objecte Oracle'. Cal substituir-los per noms reals o per '-' si no hi ha objecte identificable.",
            )
        )

    detail_sections = report_model.get("detail_sections") or []
    summary_lots = report_model.get("lot_summary") or []
    total_findings_detail = sum(int(section.get("finding_count") or 0) for section in detail_sections)
    total_findings_lots = sum(int(item.get("critical") or 0) + int(item.get("medium") or 0) + int(item.get("low") or 0) for item in summary_lots)
    summary_findings = int((report.get("summary") or {}).get("total_findings") or 0)
    if summary_findings and (summary_findings != total_findings_detail or summary_findings != total_findings_lots):
        issues.append(
            _validation_issue(
                "TOTALS_MISMATCH",
                "Totals incoherents",
                f"El total declarat ({summary_findings}) no quadra amb el detall ({total_findings_detail}) ni amb el resum per lots ({total_findings_lots}).",
                severity="error",
            )
        )

    annexe_expected = len(_build_enabled_checks(report_model))
    annexe_actual = len(_build_annex_entries(report_model)) if annexe_expected else 0
    if annexe_expected and annexe_actual < annexe_expected:
        issues.append(
            _validation_issue(
                "ANNEX_GAP",
                "Annex incomplet",
                f"L'annex funcional només cobreix {annexe_actual} dels {annexe_expected} checks habilitats.",
            )
        )

    critical_detail = [section for section in detail_sections if _severity_key(section.get("criticality")) == "critical"]
    critical_with_findings = [section for section in critical_detail if int(section.get("finding_count") or 0) > 0]
    critical_without_findings = [section for section in critical_detail if int(section.get("finding_count") or 0) <= 0]
    if critical_without_findings and not critical_with_findings:
        issues.append(
            _validation_issue(
                "CRITICAL_WITHOUT_FINDINGS",
                "Checks crítics sense troballes",
                "Hi ha checks crítics sense troballes en aquesta execució. Revisa que la finestra i els filtres siguin correctes.",
            )
        )

    return issues


def _build_executive_summary_v2(report: Dict[str, Any], profile: str) -> Dict[str, Any]:
    report_model = report.get("report_model") or {}
    lot_summary = _sort_lot_summary(report_model.get("lot_summary") or [])
    detail_sections = report_model.get("detail_sections") or []
    summary = report.get("summary") or {}
    validation_issues = _validate_post_crq_experimental_report(profile, report)

    total_findings = int(summary.get("total_findings") or sum(int(section.get("finding_count") or 0) for section in detail_sections))
    lots_affected = len(lot_summary)
    critical_lots = sum(1 for item in lot_summary if int(item.get("critical") or 0) > 0)
    total_checks = len(detail_sections)
    checks_with_findings = sum(1 for section in detail_sections if int(section.get("finding_count") or 0) > 0)
    critical_checks = [section for section in detail_sections if _severity_key(section.get("criticality")) == "critical"]
    critical_checks_with_findings = [section for section in critical_checks if int(section.get("finding_count") or 0) > 0]
    critical_checks_without_findings = [section for section in critical_checks if int(section.get("finding_count") or 0) <= 0]
    checks_with_errors = int(summary.get("checks_with_errors") or 0)

    if critical_lots or checks_with_errors or any(issue.get("severity") == "error" for issue in validation_issues):
        traffic_light = "vermell"
        recommendation = "NO PAS"
    elif total_findings or critical_checks_with_findings:
        traffic_light = "ambre"
        recommendation = "PAS AMB CONDICIONS"
    else:
        traffic_light = "verd"
        recommendation = "PAS"

    top_lots = lot_summary[:3]
    top_risks: List[str] = []
    if top_lots:
        for item in top_lots:
            top_risks.append(
                f"LOT {item.get('lot') or 'SENSE LOT'}: {int(item.get('critical') or 0)} crítiques, {int(item.get('affected_objects') or 0)} objectes afectats i prioritat {item.get('priority') or 'Baix'}."
            )
    if critical_checks_with_findings:
        top_risks.append(
            "Checks crítics amb troballes: "
            + ", ".join(_normalize_text(section.get("check_id")) for section in critical_checks_with_findings[:4])
            + "."
        )
    if checks_with_errors:
        top_risks.append(f"{checks_with_errors} checks han retornat error i requereixen revisió abans del pas d'entorn.")
    if validation_issues:
        top_risks.append("Hi ha advertiments de coherència documental que s'han de revisar abans de signar l'informe.")

    remediation_plan = [
        "Corregir primer els lots crítics i reexecutar només els checks afectats.",
        "Revalidar CHECK_02, CHECK_05 i CHECK_12 sobre els objectes reals afectats abans del pas.",
        "Acceptar el canvi només si la finestra temporal i el perfil queden consistents en tot el document.",
    ]

    return {
        "total_findings": total_findings,
        "lots_affected": lots_affected,
        "critical_lots": critical_lots,
        "total_checks": total_checks,
        "checks_with_findings": checks_with_findings,
        "critical_checks_with_findings": len(critical_checks_with_findings),
        "critical_checks_without_findings": len(critical_checks_without_findings),
        "traffic_light": traffic_light,
        "recommendation": recommendation,
        "top_risks": top_risks[:4],
        "top_lots": top_lots,
        "remediation_plan": remediation_plan,
        "validation_issues": validation_issues,
    }


def _severity_meta(label: str) -> Tuple[colors.Color, colors.Color, str]:
    normalized = _normalize_text(label).casefold()
    if "cr" in normalized:
        return CRITICAL, CRITICAL_SOFT, "Aquestes incidències s'han de solucionar de manera urgent."
    if "mitj" in normalized:
        return MEDIUM, MEDIUM_SOFT, "Aquestes incidències s'han de revisar i resoldre en el termini establert per l'equip responsable."
    return LOW, LOW_SOFT, "Aquestes incidències s'han de planificar i corregir quan sigui operativament viable."


def _severity_key(label: str) -> str:
    normalized = _normalize_text(label).casefold()
    if "cr" in normalized:
        return "critical"
    if "mitj" in normalized:
        return "medium"
    return "low"


def _deadline_text(days: Any, severity: str) -> str:
    try:
        numeric_days = int(days)
    except (TypeError, ValueError):
        numeric_days = None
    if numeric_days is not None:
        if numeric_days <= 0:
            return "Termini de resolució orientatiu: urgent"
        return f"Termini de resolució orientatiu: {numeric_days} dies"
    return _severity_meta(severity)[2]


def _build_styles() -> Dict[str, ParagraphStyle]:
    _ensure_pdf_fonts()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "exp-title",
            parent=base["Title"],
            fontName=FONT_BOLD,
            fontSize=27,
            leading=31,
            textColor=PRIMARY,
            spaceAfter=10,
        ),
        "section": ParagraphStyle(
            "exp-section",
            parent=base["Heading1"],
            fontName=FONT_BOLD,
            fontSize=18,
            leading=22,
            textColor=PRIMARY,
            spaceAfter=8,
        ),
        "subsection": ParagraphStyle(
            "exp-subsection",
            parent=base["Heading2"],
            fontName=FONT_BOLD,
            fontSize=13,
            leading=16,
            textColor=TEXT,
            spaceAfter=6,
        ),
        "cardTitle": ParagraphStyle(
            "exp-card-title",
            parent=base["Heading2"],
            fontName=FONT_BOLD,
            fontSize=16,
            leading=19,
            textColor=TEXT,
            spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "exp-label",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=9,
            leading=11,
            textColor=MUTED,
            uppercase=True,
        ),
        "body": ParagraphStyle(
            "exp-body",
            parent=base["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=10,
            leading=14,
            textColor=TEXT,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "exp-small",
            parent=base["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
        ),
        "toc": ParagraphStyle(
            "exp-toc",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=12.5,
            leading=16,
            textColor=PRIMARY,
            spaceAfter=8,
        ),
        "tocLot": ParagraphStyle(
            "exp-toc-lot",
            parent=base["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=10,
            leading=13,
            textColor=TEXT,
            leftIndent=14,
            spaceAfter=4,
        ),
        "metricValue": ParagraphStyle(
            "exp-metric-value",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=20,
            leading=22,
            textColor=TEXT,
            alignment=TA_LEFT,
        ),
        "metricLabel": ParagraphStyle(
            "exp-metric-label",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=8.5,
            leading=10,
            textColor=MUTED,
            uppercase=True,
        ),
        "overline": ParagraphStyle(
            "exp-overline",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=8.5,
            leading=10,
            textColor=MUTED,
            uppercase=True,
            spaceAfter=3,
        ),
        "heroLot": ParagraphStyle(
            "exp-hero-lot",
            parent=base["Heading1"],
            fontName=FONT_BOLD,
            fontSize=22,
            leading=26,
            textColor=TEXT,
            spaceAfter=2,
        ),
        "heroCheck": ParagraphStyle(
            "exp-hero-check",
            parent=base["Heading2"],
            fontName=FONT_BOLD,
            fontSize=14,
            leading=18,
            textColor=TEXT,
            spaceAfter=4,
        ),
        "chip": ParagraphStyle(
            "exp-chip",
            parent=base["BodyText"],
            fontName=FONT_BOLD,
            fontSize=8.5,
            leading=10,
            textColor=PRIMARY,
            alignment=TA_CENTER,
        ),
    }


def _cover_summary(report_model: Dict[str, Any]) -> str:
    lot_summary = report_model.get("lot_summary") or []
    lots_with_findings = len(lot_summary)
    critical_lots = sum(1 for item in lot_summary if int(item.get("critical") or 0) > 0)
    return f"{lots_with_findings} lots amb incidències · {critical_lots} lots amb incidències crítiques"


def _build_index_entries(include_annex: bool, include_lot_map: bool) -> List[Tuple[str, str]]:
    entries = [
        ("cover", "Portada"),
        ("index", "Índex"),
        ("global-summary", "Resum executiu global"),
        ("lot-detail", "Detall per lot"),
        ("annex-check", "Annex A - Vista transversal per check"),
        ("final", "Observacions finals i properes passes"),
    ]
    if include_lot_map:
        entries.insert(3, ("lot-map", "Mapa de lots detectats"))
    if include_annex:
        entries.append(("annex-functional", "Annex B - Anàlisi funcional dels checks"))
    return entries


def _build_enabled_checks(report_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    enabled_checks = report_model.get("enabled_checks") or []
    return [
        {
            "check_id": _normalize_text(item.get("check_id")) or "-",
            "title": _normalize_text(item.get("title") or item.get("check_id") or "-"),
            "criticality": _normalize_text(item.get("criticality") or "Baix"),
        }
        for item in enabled_checks
    ]


def _anchor_paragraph(anchor: str, title: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(f'<a name="{anchor}"/>{_safe(title)}', style)


def _internal_link(label: str, anchor: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(f'<a href="#{anchor}">{_safe(label)}</a>', style)


def _return_to_index(styles: Dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(
        '<a href="#index">Tornar a l\'índex</a>',
        ParagraphStyle(
            "exp-back-link",
            parent=styles["small"],
            textColor=PRIMARY,
            fontName=FONT_BOLD,
            spaceAfter=8,
        ),
    )


def _format_check_with_description(check_id: str, title: str) -> str:
    return f"{_normalize_text(check_id) or '-'} - {_normalize_text(title) or _normalize_text(check_id) or '-'}"


def _render_enabled_checks_box(enabled_checks: Sequence[Dict[str, Any]], styles: Dict[str, ParagraphStyle], width: float) -> Table:
    rows: List[List[Any]] = [[Paragraph("Checks habilitats en el report", styles["subsection"])]]
    if not enabled_checks:
        rows.append([Paragraph("No hi ha checks habilitats per mostrar en aquesta execució.", styles["body"])])
    else:
        for item in enabled_checks:
            rows.append([Paragraph(_format_check_with_description(item.get("check_id"), item.get("title")), styles["body"])])
    table = Table(rows, colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CARD_FILL),
                ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_SOFT),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, CARD_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _summary_check_rows(summary_item: Dict[str, Any] | None) -> List[str]:
    summary_item = summary_item or {}
    described: List[str] = []
    for entry in summary_item.get("check_descriptions") or []:
        check_id = entry.get("check_id")
        title = entry.get("title")
        if check_id:
            described.append(_format_check_with_description(check_id, title or check_id))
    if described:
        return list(dict.fromkeys(described))
    fallback = [_normalize_text(check_id) for check_id in (summary_item.get("checks") or []) if check_id]
    return list(dict.fromkeys(fallback))


def _render_checks_box(
    title: str,
    checks: Sequence[str],
    styles: Dict[str, ParagraphStyle],
    width: float,
    *,
    fill: colors.Color = colors.white,
    max_items: int = 4,
) -> Table:
    rows: List[List[Any]] = [[Paragraph(_safe(title), styles["overline"])]]
    if not checks:
        rows.append([Paragraph("-", styles["body"])])
    else:
        for check in list(checks)[:max_items]:
            rows.append([Paragraph(_safe(check), styles["small"])])
        if len(checks) > max_items:
            rows.append([Paragraph("…", styles["small"])])
    table = Table(rows, colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.7, CARD_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _render_detected_lots_box(lot_summary: Sequence[Dict[str, Any]], styles: Dict[str, ParagraphStyle], width: float) -> Table:
    rows: List[List[Any]] = [[Paragraph("Lots detectats", styles["subsection"])]]
    if not lot_summary:
        rows.append([Paragraph("No s'han detectat lots amb incidències en aquesta execució.", styles["body"])])
    else:
        header = Table(
            [[
                Paragraph("<b>Lot</b>", styles["small"]),
                Paragraph("<b>Prioritat</b>", styles["small"]),
                Paragraph("<b>Objectes</b>", styles["small"]),
                Paragraph("<b>Checks</b>", styles["small"]),
            ]],
            colWidths=[width * 0.18, width * 0.16, width * 0.12, width * 0.54],
        )
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        rows.append([header])
        for item in lot_summary:
            lot = _safe(item.get("lot"), "SENSE LOT")
            checks_text = "<br/>".join(_safe(check) for check in _summary_check_rows(item)[:3]) or "-"
            entry = Table(
                [[
                    _internal_link(f"LOT {lot}", _lot_anchor(lot), styles["body"]),
                    Paragraph(_lot_priority_label(item), styles["small"]),
                    Paragraph(str(int(item.get("affected_objects") or 0)), styles["small"]),
                    Paragraph(checks_text, styles["small"]),
                ]],
                colWidths=[width * 0.18, width * 0.16, width * 0.12, width * 0.54],
            )
            entry.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.4, CARD_BORDER),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            rows.append([entry])
    table = Table(rows, colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_SOFT),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, CARD_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _build_annex_entries(report_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    catalog = load_check_explanation_catalog()
    entries = []
    for item in _build_enabled_checks(report_model):
        current = catalog.get(item["check_id"]) or {}
        if not current:
            continue
        entries.append(current)
    return entries


def _build_detectat_summary(summary_item: Dict[str, Any] | None, lot_groups: Sequence[Dict[str, Any]]) -> str:
    summary_item = summary_item or {}
    checks = [_format_check_with_description(group.get("check"), group.get("title")) for group in lot_groups if group.get("check")]
    checks = list(dict.fromkeys(checks)) or _summary_check_rows(summary_item)
    pattern_bits = []
    for group in lot_groups:
        description = _normalize_text(group.get("description"))
        if description:
            pattern_bits.append(_compact_text(description, max_length=110))
    pattern_bits = list(dict.fromkeys(pattern_bits))[:3]
    affected_objects = int(summary_item.get("affected_objects") or 0)
    schema_count = len(summary_item.get("schemas") or [])
    checks_text = "; ".join(checks[:3]) or "sense checks detallats"
    pattern_text = " ".join(pattern_bits) if pattern_bits else "Sense patró detallat addicional informat."
    return (
        f"S'han detectat {affected_objects} objectes afectats en {schema_count} esquemes. "
        f"Han saltat els controls {checks_text}. {pattern_text}"
    )


def _build_impacte_summary(summary_item: Dict[str, Any] | None, lot_groups: Sequence[Dict[str, Any]]) -> str:
    summary_item = summary_item or {}
    impacts = []
    for group in lot_groups:
        impact = _normalize_text(group.get("impacte"))
        if impact:
            impacts.append(_compact_text(impact, max_length=120))
    impacts = list(dict.fromkeys(impacts))[:3]
    dominant_impact = _compact_text(summary_item.get("dominant_impact"), max_length=120)
    checks = {_safe(group.get("check"), "") for group in lot_groups if group.get("check")}
    technical = "Pot afectar rendiment, estabilitat, mantenibilitat i integritat del desplegament." if checks else "Pot afectar la qualitat tècnica del lot."
    detail = " ".join(impacts) if impacts else dominant_impact or "Cal revisar l'impacte real segons el volum i l'ús dels objectes afectats."
    return f"{technical} {detail}".strip()


def _build_lot_action_summary(summary_item: Dict[str, Any] | None, lot_groups: Sequence[Dict[str, Any]]) -> str:
    summary_item = summary_item or {}
    actions: List[str] = []
    first_action = _normalize_text(summary_item.get("first_action"))
    if first_action:
        actions.append(_compact_text(first_action, max_length=130))
    for group in lot_groups:
        action = _normalize_text(group.get("accio_recomanada"))
        if action:
            actions.append(_compact_text(action, max_length=130))
    unique_actions = list(dict.fromkeys(actions))
    if unique_actions:
        return " ".join(unique_actions[:2])
    checks = "; ".join(_summary_check_rows(summary_item)[:3]) or "els checks detectats"
    return f"Cal prioritzar la correcció dels objectes afectats i reexecutar {checks} després de cada canvi rellevant."


def _build_lot_validation_summary(summary_item: Dict[str, Any] | None, lot_groups: Sequence[Dict[str, Any]]) -> str:
    summary_item = summary_item or {}
    validations: List[str] = []
    for group in lot_groups:
        validation = _normalize_text(group.get("validacio_posterior"))
        if validation:
            validations.append(_compact_text(validation, max_length=130))
    unique_validations = list(dict.fromkeys(validations))
    if unique_validations:
        return " ".join(unique_validations[:2])
    lot_name = _safe(summary_item.get("lot"), "SENSE LOT")
    schemas = ", ".join(_safe(schema) for schema in (summary_item.get("schemas") or [])[:3])
    if schemas:
        return f"Reexecutar els checks del lot {lot_name} i validar els objectes dels esquemes {schemas} després de la correcció."
    return f"Reexecutar els checks del lot {lot_name} i comprovar que no hi ha regressions ni troballes obertes."


def _lot_anchor(lot: str) -> str:
    base = _normalize_text(lot or "SENSE LOT").upper()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in base).strip("-")
    return f"lot-{cleaned or 'SENSE-LOT'}"


def _lot_subanchor(lot: str, suffix: str) -> str:
    return f"{_lot_anchor(lot)}-{suffix}"


def _lot_check_anchor(lot: str, check: str) -> str:
    return f"{_lot_anchor(lot)}-check-{_normalize_text(check or 'check').upper().replace('_', '-')}"


def _group_incidents_by_severity_and_lot(lot_incident_groups: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {"critical": {}, "medium": {}, "low": {}}
    for group in lot_incident_groups:
        severity = _severity_key(_safe(group.get("severity"), "Baixa"))
        lot = _safe(group.get("lot"), "SENSE LOT")
        grouped.setdefault(severity, {}).setdefault(lot, []).append(group)
    return grouped


def _row_lot_matches(row: Dict[str, Any], lot_code: str) -> bool:
    normalized_target = _normalize_lot_code(lot_code)
    if not normalized_target:
        return False
    for key in ("lot", "Lot", "LOT", "lot_code", "LOT_CODE"):
        if _normalize_lot_code(row.get(key)) == normalized_target:
            return True
    return False


def _filter_detail_sections_for_lot(detail_sections: Sequence[Dict[str, Any]], lot_code: str) -> List[Dict[str, Any]]:
    normalized_target = _normalize_lot_code(lot_code)
    filtered_sections: List[Dict[str, Any]] = []
    for section in detail_sections or []:
        section_copy = copy.deepcopy(section)
        rows = section_copy.get("rows") or []
        if not rows:
            filtered_sections.append(section_copy)
            continue
        matching_rows = [row for row in rows if _row_lot_matches(row, normalized_target)]
        has_lot_dimension = any(
            any(key in row for key in ("lot", "Lot", "LOT", "lot_code", "LOT_CODE"))
            for row in rows
        )
        if has_lot_dimension:
            if not matching_rows:
                continue
            section_copy["rows"] = matching_rows
            section_copy["finding_count"] = len(matching_rows)
            section_copy["row_count"] = len(matching_rows)
        filtered_sections.append(section_copy)
    return filtered_sections


def _report_contains_lot(report: Dict[str, Any], lot_code: str) -> bool:
    normalized_target = _normalize_lot_code(lot_code)
    if not normalized_target:
        return False

    report_model = report.get("report_model") or {}
    if any(_normalize_lot_code(item.get("lot")) == normalized_target for item in (report_model.get("lot_summary") or [])):
        return True

    if any(_normalize_lot_code(group.get("lot")) == normalized_target for group in (report_model.get("lot_incident_groups") or [])):
        return True

    for collection in (report_model.get("detail_sections") or [], report.get("results_by_check") or []):
        for section in collection:
            rows = section.get("rows") or []
            if any(_row_lot_matches(row, normalized_target) for row in rows):
                return True

    return False


def _collect_report_schemas(report: Dict[str, Any]) -> List[str]:
    schemas: set[str] = set()
    report_model = report.get("report_model") or {}

    for item in report_model.get("lot_summary") or []:
        for schema_name in item.get("schemas") or []:
            normalized = _normalize_text(schema_name).strip().upper()
            if normalized:
                schemas.add(normalized)

    for group in report_model.get("lot_incident_groups") or []:
        for schema_group in group.get("schemas") or []:
            normalized = _normalize_text(schema_group.get("nom")).strip().upper()
            if normalized:
                schemas.add(normalized)

    for collection_name in ("detail_sections",):
        for section in report_model.get(collection_name) or []:
            for row in section.get("rows") or []:
                for key in ("ESQUEMA", "esquema", "schema", "Schema"):
                    normalized = _normalize_text((row or {}).get(key)).strip().upper()
                    if normalized:
                        schemas.add(normalized)

    for section in report.get("results_by_check") or []:
        for row in section.get("rows") or []:
            for key in ("ESQUEMA", "esquema", "schema", "Schema"):
                normalized = _normalize_text((row or {}).get(key)).strip().upper()
                if normalized:
                    schemas.add(normalized)

    return sorted(schemas)


def filter_report_model_for_lot(report_model: Dict[str, Any], lot_code: str) -> Dict[str, Any]:
    normalized_target = _normalize_lot_code(lot_code)
    if not normalized_target:
        raise ValueError("Cal informar un lot vàlid per generar el PDF per lot.")

    report_model_copy = copy.deepcopy(report_model or {})
    lot_summary = report_model_copy.get("lot_summary") or []
    matching_lots = [
        item for item in lot_summary
        if _normalize_lot_code(item.get("lot")) == normalized_target
    ]
    if not matching_lots:
        # Si el lot no està al resum, creem un entrada minimal per permetre la generació del PDF individual
        matching_lots = [{
            "lot": lot_code,
            "critical": 0,
            "medium": 0,
            "low": 0,
            "affected_objects": 0,
            "checks": [],
            "schemas": []
        }]

    report_model_copy["lot_summary"] = matching_lots
    report_model_copy["lot_incident_groups"] = [
        group for group in (report_model_copy.get("lot_incident_groups") or [])
        if _normalize_lot_code(group.get("lot")) == normalized_target
    ]
    report_model_copy["detail_sections"] = _filter_detail_sections_for_lot(
        report_model_copy.get("detail_sections") or [],
        normalized_target,
    )
    return report_model_copy


def filter_post_crq_report_for_lot(report: Dict[str, Any], lot_code: str) -> Dict[str, Any]:
    report_copy = copy.deepcopy(report or {})
    normalized_target = _normalize_lot_code(lot_code)
    if not normalized_target:
        raise ValueError("Cal informar un lot vÃ lid per generar el PDF per lot.")
    if not _report_contains_lot(report_copy, normalized_target):
        raise ValueError(f"No s'ha trobat cap informaciÃ³ per al lot {lot_code}.")

    report_model = report_copy.get("report_model") or {}
    report_copy["report_model"] = filter_report_model_for_lot(report_model, normalized_target)

    filtered_results_by_check = _filter_detail_sections_for_lot(report_copy.get("results_by_check") or [], normalized_target)
    if filtered_results_by_check:
        report_copy["results_by_check"] = filtered_results_by_check
        valid_check_ids = {item.get("check_id") for item in filtered_results_by_check}
        report_copy["executed_checks"] = [
            item for item in (report_copy.get("executed_checks") or [])
            if item.get("check_id") in valid_check_ids
        ]

    affected_schemas = _collect_report_schemas(report_copy)
    context = report_copy.get("context") or {}
    report_copy["context"] = {**context, "schemas": affected_schemas}

    summary = report_copy.get("summary") or {}
    report_copy["summary"] = {
        **summary,
        "schemas_with_detected_changes": len(affected_schemas),
    }

    report_model = report_copy.get("report_model") or {}
    execution_parameters = report_model.get("execution_parameters") or {}
    report_model["execution_parameters"] = {**execution_parameters, "schemas": affected_schemas}
    report_copy["report_model"] = report_model
    return report_copy


def _lot_priority_rank(item: Dict[str, Any]) -> int:
    if int(item.get("critical") or 0) > 0:
        return 3
    if int(item.get("medium") or 0) > 0:
        return 2
    return 1


def _lot_priority_label(item: Dict[str, Any]) -> str:
    if int(item.get("critical") or 0) > 0:
        return "Crític"
    if int(item.get("medium") or 0) > 0:
        return "Mitjà"
    return "Baix"


def _sort_lot_summary(lot_summary: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        lot_summary,
        key=lambda item: (
            -_lot_priority_rank(item),
            -int(item.get("affected_objects") or 0),
            _safe(item.get("lot"), "SENSE LOT"),
        ),
    )


def _simple_table(
    data: Sequence[Sequence[Any]],
    col_widths: Sequence[float],
    table_style: List[Tuple],
    *,
    row_heights: Sequence[float] | None = None,
) -> Table:
    table = Table(
        data,
        colWidths=col_widths,
        rowHeights=row_heights,
        repeatRows=1 if len(data) > 1 else 0,
        splitByRow=1,
        splitInRow=1,
        longTableOptimize=1,
        hAlign="LEFT",
    )
    table.setStyle(TableStyle(table_style))
    return table


def _metric_card(title: str, value: Any, color: colors.Color, fill: colors.Color, styles: Dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [Paragraph(_safe(title).upper(), styles["metricLabel"])],
            [Paragraph(_safe(value), ParagraphStyle("metric-value-dynamic", parent=styles["metricValue"], textColor=color))],
        ],
        colWidths=[4.1 * cm],
        rowHeights=[0.9 * cm, 1.2 * cm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.9, color),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _pill(text: str, styles: Dict[str, ParagraphStyle], fill: colors.Color = PRIMARY_SOFT, border: colors.Color = CARD_BORDER, text_color: colors.Color = PRIMARY) -> Table:
    style = ParagraphStyle(
        f"pill-{text_color.hexval()}",
        parent=styles["chip"],
        textColor=text_color,
    )
    pill = Table([[Paragraph(_safe(text), style)]])
    pill.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return pill


def _cta_pill(label: str, href: str, styles: Dict[str, ParagraphStyle], border: colors.Color) -> Table:
    style = ParagraphStyle(
        f"cta-{border.hexval()}",
        parent=styles["chip"],
        textColor=colors.white,
        fontName=FONT_BOLD,
    )
    pill = Table([[Paragraph(f'<a href="#{href}" color="white">{_safe(label)}</a>', style)]])
    pill.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), border),
                ("BOX", (0, 0), (-1, -1), 0.8, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return pill


def _info_box(title: str, body: str, styles: Dict[str, ParagraphStyle], width: float, fill: colors.Color = colors.white) -> Table:
    table = Table(
        [
            [Paragraph(_safe(title), styles["overline"])],
            [Paragraph(_safe(body), styles["body"])],
        ],
        colWidths=[width],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.7, CARD_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _section_banner(title: str, subtitle: str, color: colors.Color, fill: colors.Color, width: float, styles: Dict[str, ParagraphStyle]) -> Table:
    badge = _pill(
        f"Bloc {title}",
        styles,
        fill=colors.white,
        border=color,
        text_color=color,
    )
    table = Table(
        [
            [
                Paragraph(_safe(title), ParagraphStyle("banner-title", parent=styles["cardTitle"], textColor=color, fontSize=17, leading=20)),
                badge,
            ],
            [Paragraph(_safe(subtitle), styles["body"]), ""],
        ],
        colWidths=[width * 0.72, width * 0.28],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.8, color),
                ("LINEBEFORE", (0, 0), (0, 1), 4, color),
                ("SPAN", (0, 1), (1, 1)),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _lot_stage_banner(title: str, subtitle: str, color: colors.Color, fill: colors.Color, width: float, styles: Dict[str, ParagraphStyle], *, anchor: str | None = None) -> Table:
    heading = _safe(title)
    if anchor:
        heading = f'<a name="{anchor}"/>{heading}'
    badge = _pill(title, styles, fill=colors.white, border=color, text_color=color)
    table = Table(
        [
            [
                Paragraph(heading, ParagraphStyle("lot-stage-title", parent=styles["cardTitle"], textColor=color, fontSize=15, leading=18)),
                badge,
            ],
            [Paragraph(_safe(subtitle), styles["small"]), ""],
        ],
        colWidths=[width * 0.72, width * 0.28],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.8, color),
                ("LINEBEFORE", (0, 0), (0, 1), 4, color),
                ("SPAN", (0, 1), (1, 1)),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _incident_object_count(group: Dict[str, Any]) -> int:
    total = 0
    for schema_group in group.get("schemas") or []:
        objectes = schema_group.get("objectes") or []
        total += int(schema_group.get("object_count") or len(objectes))
    return total


def _paired_info_boxes(
    left_title: str,
    left_body: str,
    right_title: str,
    right_body: str,
    styles: Dict[str, ParagraphStyle],
    total_width: float,
    *,
    left_fill: colors.Color = colors.white,
    right_fill: colors.Color = colors.white,
) -> Table:
    col_width = (total_width - 12) / 2
    content_width = col_width - 20
    left_title_paragraph = Paragraph(_safe(left_title), styles["overline"])
    right_title_paragraph = Paragraph(_safe(right_title), styles["overline"])
    left_body_paragraph = Paragraph(_safe(left_body), styles["body"])
    right_body_paragraph = Paragraph(_safe(right_body), styles["body"])
    _, left_title_height = left_title_paragraph.wrap(content_width, 1000)
    _, right_title_height = right_title_paragraph.wrap(content_width, 1000)
    _, left_body_height = left_body_paragraph.wrap(content_width, 10000)
    _, right_body_height = right_body_paragraph.wrap(content_width, 10000)
    title_height = max(left_title_height, right_title_height) + 8
    body_height = max(left_body_height, right_body_height) + 16
    table = Table(
        [
            [left_title_paragraph, right_title_paragraph],
            [left_body_paragraph, right_body_paragraph],
        ],
        colWidths=[col_width, col_width],
        rowHeights=[title_height, body_height],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 1), left_fill),
                ("BACKGROUND", (1, 0), (1, 1), right_fill),
                ("BOX", (0, 0), (0, 1), 0.7, CARD_BORDER),
                ("BOX", (1, 0), (1, 1), 0.7, CARD_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _lot_operational_summary_card(
    lot: str,
    summary_item: Dict[str, Any] | None,
    lot_groups: Sequence[Dict[str, Any]],
    severity_color: colors.Color,
    severity_fill: colors.Color,
    total_width: float,
    styles: Dict[str, ParagraphStyle],
) -> Table:
    summary_item = summary_item or {}
    priority_label = _lot_priority_label(summary_item)
    schemas = ", ".join(_safe(item) for item in (summary_item.get("schemas") or [])) or "Sense esquema detallat"
    metrics = Table(
        [[
            _metric_card("Crítiques", summary_item.get("critical") or 0, CRITICAL, CRITICAL_SOFT, styles),
            _metric_card("Mitjanes", summary_item.get("medium") or 0, MEDIUM, MEDIUM_SOFT, styles),
            _metric_card("Baixes", summary_item.get("low") or 0, LOW, LOW_SOFT, styles),
        ]],
        colWidths=[(total_width - 24) / 3] * 3,
    )
    metrics.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    executive_text = (
        f"El lot {_safe(lot, 'SENSE LOT')} concentra {int(summary_item.get('affected_objects') or 0)} objectes afectats, "
        f"repartits en {len(summary_item.get('schemas') or [])} esquemes i {len(summary_item.get('checks') or [])} checks detectats."
    )
    card = Table(
        [
            [
                [
                    Paragraph("Resum operatiu del lot", styles["overline"]),
                    Paragraph(executive_text, styles["body"]),
                    Paragraph(f"<b>Esquemes afectats:</b> {schemas}", styles["body"]),
                ],
                _pill(f"Prioritat {priority_label}", styles, fill=severity_fill, border=severity_color, text_color=severity_color),
            ],
            [metrics, ""],
        ],
        colWidths=[total_width * 0.74, total_width * 0.26],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CARD_FILL),
                ("BACKGROUND", (0, 0), (-1, 0), severity_fill),
                ("BOX", (0, 0), (-1, -1), 0.9, CARD_BORDER),
                ("LINEBEFORE", (0, 0), (0, 1), 4, severity_color),
                ("SPAN", (0, 1), (1, 1)),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return card


def _lot_analysis_flowables(
    lot: str,
    summary_item: Dict[str, Any] | None,
    lot_groups: Sequence[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    summary_item = summary_item or {}
    schemas = ", ".join(_safe(schema) for schema in (summary_item.get("schemas") or [])) or "Sense esquema detallat"
    checks = _summary_check_rows(summary_item)
    flowables: List[Any] = [
        Paragraph("Detectat", styles["subsection"]),
        Paragraph(_build_detectat_summary(summary_item, lot_groups), styles["body"]),
        Spacer(1, 0.08 * cm),
        Paragraph("Impacte", styles["subsection"]),
        Paragraph(_build_impacte_summary(summary_item, lot_groups), styles["body"]),
        Spacer(1, 0.08 * cm),
        Paragraph("Esquemes afectats", styles["subsection"]),
        Paragraph(f"Els objectes afectats del lot {_safe(lot)} es concentren principalment en: {schemas}.", styles["body"]),
        Spacer(1, 0.08 * cm),
        Paragraph("Checks presents al lot", styles["subsection"]),
    ]
    for check in checks:
        flowables.append(Paragraph(f"• {_safe(check)}", styles["body"]))
    flowables.extend(
        [
            Spacer(1, 0.08 * cm),
            Paragraph("Acció requerida", styles["subsection"]),
            Paragraph(_build_lot_action_summary(summary_item, lot_groups), styles["body"]),
            Spacer(1, 0.08 * cm),
            Paragraph("Validació posterior", styles["subsection"]),
            Paragraph(_build_lot_validation_summary(summary_item, lot_groups), styles["body"]),
        ]
    )
    return flowables


def _lot_final_observations(lot: str, summary_item: Dict[str, Any] | None, styles: Dict[str, ParagraphStyle]) -> List[Any]:
    summary_item = summary_item or {}
    checks = len(summary_item.get("checks") or [])
    objects = int(summary_item.get("affected_objects") or 0)
    return [
        Paragraph("Observacions finals del lot", styles["subsection"]),
        Paragraph(
            f"El lot {_safe(lot)} es pot considerar revalidat quan els {checks} checks detectats quedin sense troballes obertes o justificades, i els {objects} objectes afectats hagin estat revisats sense regressions.",
            styles["body"],
        ),
    ]


def _lot_detail_header_card(lot: str, summary_item: Dict[str, Any] | None, styles: Dict[str, ParagraphStyle], total_width: float) -> Table:
    summary_item = summary_item or {}
    priority_label = _lot_priority_label(summary_item)
    priority_color, priority_fill, _ = _severity_meta(priority_label)
    schemas = ", ".join(_safe(schema) for schema in (summary_item.get("schemas") or [])[:4]) or "Sense esquema detallat"
    checks_box = _render_checks_box(
        "Checks del lot",
        _summary_check_rows(summary_item),
        styles,
        total_width * 0.44,
        fill=colors.white,
        max_items=3,
    )
    nav_box = Table(
        [[
            Paragraph("Navegació interna", styles["overline"]),
            "",
        ], [
            _internal_link("Veure capçalera", _lot_anchor(lot), styles["small"]),
            _internal_link("Veure resum", _lot_subanchor(lot, "summary"), styles["small"]),
        ], [
            _internal_link("Veure mini índex", _lot_subanchor(lot, "mini-index"), styles["small"]),
            _internal_link("Veure detall", _lot_subanchor(lot, "findings"), styles["small"]),
        ], [
            Paragraph(f"{int(summary_item.get('affected_objects') or 0)} objectes afectats", styles["small"]),
            _internal_link("Tornar a l'índex", "index", styles["small"]),
        ]],
        colWidths=[(total_width * 0.48 - 12) / 2, (total_width * 0.48 - 12) / 2],
    )
    nav_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.7, CARD_BORDER),
                ("SPAN", (0, 0), (1, 0)),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    meta_row = Table(
        [[
            _pill(f"Prioritat {priority_label}", styles, fill=priority_fill, border=priority_color, text_color=priority_color),
            _pill(f"{len(summary_item.get('schemas') or [])} esquemes", styles, fill=PRIMARY_SOFT, border=CARD_BORDER, text_color=TEXT),
            _pill(f"{len(summary_item.get('checks') or [])} checks", styles, fill=PRIMARY_SOFT, border=CARD_BORDER, text_color=TEXT),
        ]],
        colWidths=[(total_width - 24) / 3] * 3,
    )
    meta_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    card = Table(
        [
            [
                [
                    Paragraph("Capítol de lot", styles["overline"]),
                    Paragraph(f'<a name="{_lot_anchor(lot)}"/>LOT {_safe(lot)}', styles["heroLot"]),
                    Paragraph(f"Esquemes en focus: {schemas}", styles["small"]),
                ],
                _pill(priority_label, styles, fill=priority_fill, border=priority_color, text_color=priority_color),
            ],
            [meta_row, ""],
            [checks_box, nav_box],
        ],
        colWidths=[total_width * 0.52, total_width * 0.48],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CARD_FILL),
                ("BACKGROUND", (0, 0), (-1, 0), priority_fill),
                ("BOX", (0, 0), (-1, -1), 0.9, CARD_BORDER),
                ("LINEBEFORE", (0, 0), (0, 2), 4, priority_color),
                ("SPAN", (0, 1), (1, 1)),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return card


def _lot_mini_index_box(lot: str, lot_groups: Sequence[Dict[str, Any]], styles: Dict[str, ParagraphStyle], total_width: float) -> Table:
    rows: List[List[Any]] = [[Paragraph(f'<a name="{_lot_subanchor(lot, "mini-index")}"/>Mini índex del lot', styles["subsection"])]]
    seen: set[str] = set()
    for group in lot_groups:
        check_id = _normalize_text(group.get("check"))
        title = _normalize_text(group.get("title"))
        if not check_id or check_id in seen:
            continue
        seen.add(check_id)
        rows.append([_internal_link(_format_check_with_description(check_id, title), _lot_check_anchor(lot, check_id), styles["body"])])
    if len(rows) == 1:
        rows.append([Paragraph("No hi ha checks detallats per a aquest lot.", styles["body"])])
    table = Table(rows, colWidths=[total_width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_SOFT),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, CARD_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _lots_overview_cards(lot_summary: Sequence[Dict[str, Any]], styles: Dict[str, ParagraphStyle], total_width: float) -> Table:
    total_lots = len(lot_summary)
    critical_lots = sum(1 for item in lot_summary if int(item.get("critical") or 0) > 0)
    affected_objects = sum(int(item.get("affected_objects") or 0) for item in lot_summary)
    distinct_checks = len({check for item in lot_summary for check in (item.get("checks") or [])})
    table = Table(
        [[
            _metric_card("Lots amb incidències", total_lots, PRIMARY, PRIMARY_SOFT, styles),
            _metric_card("Lots crítics", critical_lots, CRITICAL, CRITICAL_SOFT, styles),
            _metric_card("Objectes afectats", affected_objects, MEDIUM, MEDIUM_SOFT, styles),
            _metric_card("Checks diferents", distinct_checks, LOW, LOW_SOFT, styles),
        ]],
        colWidths=[(total_width - 18) / 4] * 4,
    )
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def _build_global_summary_blurbs(lot_summary: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    total_lots = len(lot_summary)
    critical_lots = sum(1 for item in lot_summary if int(item.get("critical") or 0) > 0)
    total_objects = sum(int(item.get("affected_objects") or 0) for item in lot_summary)
    different_checks = len({check for item in lot_summary for check in (item.get("checks") or [])})
    if not lot_summary:
        return {
            "executive": "No s'han detectat lots amb incidències en aquesta execució.",
            "impact": "No s'observa impacte global rellevant sobre la BBDD a partir dels checks executats.",
            "priority": "No cal priorització de lots; només convé conservar la traçabilitat de l'execució.",
            "totals": f"0 lots · 0 lots crítics · 0 objectes afectats · 0 checks diferents",
        }
    return {
        "executive": f"S'han detectat {total_lots} lots amb incidències, dels quals {critical_lots} presenten criticitat alta i requereixen una revisió preferent abans de validar el canvi.",
        "impact": f"El patró global apunta a {total_objects} objectes afectats repartits en {different_checks} checks diferents, amb risc combinat sobre integritat, compilació, rendiment i estabilitat post-desplegament.",
        "priority": "Es recomana començar pels lots amb incidències crítiques i més volum d'objectes afectats, i després continuar pels lots mitjans amb més dependències funcionals.",
        "totals": f"{total_lots} lots · {critical_lots} lots crítics · {total_objects} objectes afectats · {different_checks} checks diferents",
    }


def _prioritized_lots_table(lot_summary: Sequence[Dict[str, Any]], styles: Dict[str, ParagraphStyle], total_width: float) -> Table:
    rows: List[List[Any]] = [[
        Paragraph("<b>Lot</b>", styles["small"]),
        Paragraph("<b>Prioritat</b>", styles["small"]),
        Paragraph("<b>Objectes</b>", styles["small"]),
        Paragraph("<b>Checks</b>", styles["small"]),
    ]]
    for item in lot_summary[:6]:
        checks_text = "<br/>".join(_safe(check) for check in _summary_check_rows(item)[:4]) or "-"
        rows.append([
            Paragraph(_safe(item.get("lot"), "SENSE LOT"), styles["small"]),
            Paragraph(_lot_priority_label(item), styles["small"]),
            Paragraph(str(int(item.get("affected_objects") or 0)), styles["small"]),
            Paragraph(checks_text, styles["small"]),
        ])
    return _simple_table(
        rows,
        [total_width * 0.18, total_width * 0.18, total_width * 0.14, total_width * 0.50],
        [
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbff")]),
            ("GRID", (0, 0), (-1, -1), 0.5, CARD_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ],
    )


def _lot_severity_strip(item: Dict[str, Any], styles: Dict[str, ParagraphStyle], total_width: float) -> Table:
    table = Table(
        [[
            _pill(f"{int(item.get('critical') or 0)} crítiques", styles, fill=CRITICAL_SOFT, border=CRITICAL, text_color=CRITICAL),
            _pill(f"{int(item.get('medium') or 0)} mitjanes", styles, fill=MEDIUM_SOFT, border=MEDIUM, text_color=MEDIUM),
            _pill(f"{int(item.get('low') or 0)} baixes", styles, fill=LOW_SOFT, border=LOW, text_color=LOW),
        ]],
        colWidths=[(total_width - 24) / 3] * 3,
    )
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def _lots_navigation_cards(
    lot_summary: Sequence[Dict[str, Any]],
    incidents_by_lot: Dict[str, List[Dict[str, Any]]],
    styles: Dict[str, ParagraphStyle],
    total_width: float,
) -> List[Any]:
    if not lot_summary:
        return [Paragraph("No hi ha lots amb incidències en aquesta execució.", styles["body"])]

    cards: List[Any] = []
    for item in lot_summary:
        lot = _safe(item.get("lot"), "SENSE LOT")
        priority_label = _lot_priority_label(item)
        priority_color, priority_fill, _ = _severity_meta(priority_label)
        checks = _summary_check_rows(item)
        schemas = item.get("schemas") or []
        subtitle = " · ".join(
            part
            for part in [
                f"{int(item.get('affected_objects') or 0)} objectes",
                f"{len(schemas)} esquemes",
                f"{len(checks)} checks",
            ]
            if part
        )
        metrics = Table(
            [[
                _pill(f"{int(item.get('affected_objects') or 0)} objectes", styles, fill=priority_fill, border=priority_color, text_color=TEXT),
                _pill(f"{len(schemas)} esquemes", styles, fill=priority_fill, border=priority_color, text_color=TEXT),
                _pill(f"{len(checks)} checks", styles, fill=priority_fill, border=priority_color, text_color=TEXT),
            ]],
            colWidths=[(total_width - 36) / 3] * 3,
        )
        metrics.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        schemas_line = ", ".join(_safe(schema) for schema in schemas[:5])
        if len(schemas) > 5:
            schemas_line = f"{schemas_line}…"
        checks_box = _render_checks_box(
            "Checks afectats",
            checks,
            styles,
            total_width * 0.72 - 20,
            fill=colors.white,
        )
        link_button = _cta_pill("Obrir incidències del lot", _lot_anchor(lot), styles, priority_color)
        card = Table(
            [
                [
                    Paragraph(
                        f'<a href="#{_lot_anchor(lot)}">LOT {lot}</a>',
                        ParagraphStyle("lot-nav-title", parent=styles["heroLot"], textColor=TEXT, fontSize=18, leading=21),
                    ),
                    _pill(priority_label, styles, fill=priority_fill, border=priority_color, text_color=priority_color),
                ],
                [Paragraph(subtitle or "Sense detall disponible", styles["small"]), ""],
                [metrics, ""],
                [Paragraph(f"<b>Esquemes en focus:</b> {schemas_line or '-'}", styles["body"]), ""],
                [checks_box, link_button],
            ],
            colWidths=[total_width * 0.72, total_width * 0.28],
        )
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), CARD_FILL),
                    ("BACKGROUND", (0, 0), (-1, 0), priority_fill),
                    ("BOX", (0, 0), (-1, -1), 0.9, CARD_BORDER),
                    ("LINEBEFORE", (0, 0), (0, 4), 4, priority_color),
                    ("SPAN", (0, 1), (1, 1)),
                    ("SPAN", (0, 2), (1, 2)),
                    ("SPAN", (0, 3), (1, 3)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        cards.extend([card, Spacer(1, 0.18 * cm)])

    return cards[:-1] if cards else cards


def _severity_overview_cards(
    severity_key: str,
    lots_for_section: Dict[str, List[Dict[str, Any]]],
    lot_summary_by_name: Dict[str, Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
    total_width: float,
    accent_color: colors.Color,
    accent_fill: colors.Color,
) -> Table:
    lots_count = len(lots_for_section)
    incidents_count = sum(len(groups) for groups in lots_for_section.values())
    checks_count = len({group.get("check") for groups in lots_for_section.values() for group in groups if group.get("check")})
    if severity_key == "critical":
        affected_objects = sum(int((lot_summary_by_name.get(lot) or {}).get("critical") or 0) for lot in lots_for_section)
    elif severity_key == "medium":
        affected_objects = sum(int((lot_summary_by_name.get(lot) or {}).get("medium") or 0) for lot in lots_for_section)
    else:
        affected_objects = sum(int((lot_summary_by_name.get(lot) or {}).get("low") or 0) for lot in lots_for_section)

    table = Table(
        [[
            _metric_card("Lots afectats", lots_count, accent_color, accent_fill, styles),
            _metric_card("Incidències del bloc", incidents_count, accent_color, accent_fill, styles),
            _metric_card("Checks diferents", checks_count, accent_color, accent_fill, styles),
            _metric_card("Troballes d'aquesta criticitat", affected_objects, accent_color, accent_fill, styles),
        ]],
        colWidths=[(total_width - 18) / 4] * 4,
    )
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def _header_footer(canvas, doc, profile: str, generated_at: str) -> None:
    _ensure_pdf_fonts()
    canvas.saveState()
    width, height = doc.pagesize
    canvas.setStrokeColor(CARD_BORDER)
    canvas.line(doc.leftMargin, height - 1.15 * cm, width - doc.rightMargin, height - 1.15 * cm)
    canvas.setFillColor(PRIMARY)
    canvas.setFont(FONT_BOLD, 10)
    canvas.drawString(doc.leftMargin, height - 0.85 * cm, "Informe post-CRQ experimental V2")
    canvas.setFillColor(MUTED)
    canvas.setFont(FONT_REGULAR, 8.5)
    canvas.drawRightString(width - doc.rightMargin, height - 0.85 * cm, f"Perfil {profile} · {_safe(generated_at)}")
    canvas.setStrokeColor(CARD_BORDER)
    canvas.line(doc.leftMargin, 1.05 * cm, width - doc.rightMargin, 1.05 * cm)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 0.65 * cm, "Departament d'Educació i Formació Professional")
    canvas.drawRightString(width - doc.rightMargin, 0.65 * cm, f"Pàgina {doc.page}")
    canvas.restoreState()


def _cover(canvas, doc, profile: str, report_model: Dict[str, Any], report: Dict[str, Any]) -> None:
    _ensure_pdf_fonts()
    canvas.saveState()
    width, height = A4
    cover_path = _cover_path()
    if cover_path:
        img_height = 14.2 * cm
        canvas.drawImage(str(cover_path), 1.4 * cm, height - img_height - 1.4 * cm, width=width - 2.8 * cm, height=img_height, preserveAspectRatio=True, mask="auto")

    card_x = 1.8 * cm
    card_y = 2.2 * cm
    card_w = width - 3.6 * cm
    card_h = 8.0 * cm
    canvas.setFillColor(colors.white)
    canvas.roundRect(card_x, card_y, card_w, card_h, 14, stroke=0, fill=1)
    canvas.setStrokeColor(CARD_BORDER)
    canvas.roundRect(card_x, card_y, card_w, card_h, 14, stroke=1, fill=0)

    execution_parameters = report_model.get("execution_parameters") or {}
    lines = [
        ("Informe d'auditoria post-CRQ", PRIMARY, 24, FONT_BOLD),
        (_safe(profile), TEXT, 16, FONT_BOLD),
        (f"Data de generació: {_safe(execution_parameters.get('generated_at'))}", TEXT, 10, FONT_REGULAR),
        (f"Finestra auditada: {_time_window_label(report)}", TEXT, 10, FONT_REGULAR),
        (f"Resum global: {_cover_summary(report_model)}", MUTED, 10.5, FONT_REGULAR),
    ]

    current_y = card_y + card_h - 1.3 * cm
    for text, color, size, font in lines:
        canvas.setFillColor(color)
        canvas.setFont(font, size)
        canvas.drawString(card_x + 0.9 * cm, current_y, text)
        current_y -= 0.8 * cm if size >= 16 else 0.62 * cm

    canvas.setFillColor(PRIMARY_SOFT)
    canvas.roundRect(card_x + 0.9 * cm, card_y + 0.8 * cm, card_w - 1.8 * cm, 1.2 * cm, 8, stroke=0, fill=1)
    canvas.setFillColor(PRIMARY)
    canvas.setFont(FONT_BOLD, 10)
    canvas.drawString(card_x + 1.2 * cm, card_y + 1.2 * cm, "Versió experimental V2 per comparar resum, validacions i text documental sense afectar el flux oficial.")
    canvas.restoreState()


def _lot_summary_card(item: Dict[str, Any], styles: Dict[str, ParagraphStyle], total_width: float) -> Table:
    severity_cards = Table(
        [[
            _metric_card("Crítiques", item.get("critical") or 0, CRITICAL, CRITICAL_SOFT, styles),
            _metric_card("Mitjanes", item.get("medium") or 0, MEDIUM, MEDIUM_SOFT, styles),
            _metric_card("Baixes", item.get("low") or 0, LOW, LOW_SOFT, styles),
        ]],
        colWidths=[(total_width - 30) / 3] * 3,
    )
    severity_cards.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    schemas = item.get("schemas") or []
    schema_text = ", ".join(_safe(schema) for schema in schemas) if schemas else "Sense esquema detallat"
    checks = ", ".join(_safe(check) for check in item.get("checks") or []) or "-"
    priority_color, priority_fill, _ = _severity_meta(_safe(item.get("priority"), "Baix"))
    priority_badge = _pill(
        f"Prioritat {_safe(item.get('priority'), 'Baix')}",
        styles,
        fill=priority_fill,
        border=priority_color,
        text_color=priority_color,
    )

    schema_chips = [Paragraph(f"<b>Esquemes afectats:</b> {schema_text}", styles["body"])]
    action_impact = Table(
        [[
            _info_box("Acció inicial", _safe(item.get("first_action")), styles, (total_width - 12) / 2, fill=PRIMARY_SOFT),
            _info_box("Impacte principal", _safe(item.get("dominant_impact")), styles, (total_width - 12) / 2, fill=colors.white),
        ]],
        colWidths=[(total_width - 12) / 2, (total_width - 12) / 2],
    )
    action_impact.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    body = [
        [
            [
                Paragraph("Lot prioritzat", styles["overline"]),
                Paragraph(f"LOT {_safe(item.get('lot'), 'SENSE LOT')}", styles["heroLot"]),
                Paragraph(f"{int(item.get('affected_objects') or 0)} objectes afectats", styles["small"]),
            ],
            priority_badge,
        ],
        [severity_cards, ""],
        [schema_chips, ""],
        [Paragraph(f"<b>Checks afectats:</b> {checks}", styles["body"]), ""],
        [action_impact, ""],
    ]
    table = Table(body, colWidths=[total_width * 0.74, total_width * 0.26])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CARD_FILL),
                ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
                ("BACKGROUND", (0, 0), (-1, 0), colors.white),
                ("SPAN", (0, 1), (1, 1)),
                ("SPAN", (0, 2), (1, 2)),
                ("SPAN", (0, 3), (1, 3)),
                ("SPAN", (0, 4), (1, 4)),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, CARD_BORDER),
            ]
        )
    )
    return table


def _incident_object_table(schema_group: Dict[str, Any], total_width: float, styles: Dict[str, ParagraphStyle]) -> Table:
    object_rows = schema_group.get("objectes") or []
    preferred = ["OBJECTE", "TIPUS", "DADA TÈCNICA", "ESQUEMA", "OBSERVACIÓ", "SUBTIPUS"]
    present = []
    for key in preferred:
        if any(key in row and _safe(row.get(key), "") for row in object_rows):
            present.append(key)
    if not present:
        present = ["OBJECTE", "TIPUS", "DADA TÈCNICA"]
    deduped_rows: List[Dict[str, Any]] = []
    seen = set()
    for row in object_rows:
        signature = tuple(_safe(row.get(column), "") for column in present)
        if signature in seen:
            continue
        seen.add(signature)
        deduped_rows.append(row)
    object_rows = deduped_rows
    widths_map = {
        "OBJECTE": total_width * 0.27,
        "TIPUS": total_width * 0.14,
        "DADA TÈCNICA": total_width * 0.39,
        "ESQUEMA": total_width * 0.16,
        "OBSERVACIÓ": total_width * 0.22,
        "SUBTIPUS": total_width * 0.18,
    }
    total = sum(widths_map.get(key, total_width / max(len(present), 1)) for key in present)
    scale = total_width / total if total else 1
    col_widths = [widths_map.get(key, total_width / max(len(present), 1)) * scale for key in present]
    header_style = ParagraphStyle("incident-table-header", parent=styles["small"], fontName=FONT_BOLD, textColor=colors.white)
    body_style = ParagraphStyle("incident-table-body", parent=styles["small"], fontSize=8.7, leading=11.2, textColor=TEXT)
    data: List[List[Any]] = [
        [Paragraph(f"<b>{_safe(column)}</b>", header_style) for column in present]
    ]
    for row in object_rows:
        data.append([Paragraph(_safe(row.get(column)), body_style) for column in present])
    return _simple_table(
        data,
        col_widths,
        [
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbff")]),
            ("GRID", (0, 1), (-1, -1), 0.35, CARD_BORDER),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, PRIMARY),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ],
    )


def _schema_table_card(schema_group: Dict[str, Any], total_width: float, styles: Dict[str, ParagraphStyle]) -> List[Any]:
    schema_name = _safe(schema_group.get("nom"))
    object_count = int(schema_group.get("object_count") or len(schema_group.get("objectes") or []))
    chip = Table(
        [[Paragraph(f"{schema_name} ({object_count})", ParagraphStyle("schema-chip", parent=styles["small"], textColor=PRIMARY, alignment=TA_CENTER))]],
        colWidths=[min(total_width * 0.34, max(4.2 * cm, len(schema_name) * 0.23 * cm + 1.8 * cm))],
    )
    chip.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PRIMARY_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, CARD_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    summary_row = Table(
        [[
            chip,
            _pill(
                f"{object_count} objectes",
                styles,
                fill=colors.white,
                border=CARD_BORDER,
                text_color=TEXT,
            ),
        ]],
        colWidths=[total_width * 0.42, total_width * 0.22],
    )
    summary_row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    header_card = Table(
        [
            [summary_row],
            [Paragraph("Detall tècnic dels objectes afectats dins d'aquest esquema.", styles["small"])],
        ],
        colWidths=[total_width],
    )
    header_card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BACKGROUND", (0, 0), (-1, 1), PRIMARY_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.7, CARD_BORDER),
                ("LINEBELOW", (0, 1), (-1, 1), 0.6, CARD_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return [
        header_card,
        Spacer(1, 0.10 * cm),
        _incident_object_table(schema_group, total_width - 20, styles),
    ]


def _incident_card(group: Dict[str, Any], styles: Dict[str, ParagraphStyle], total_width: float) -> List[Any]:
    severity_color, severity_fill, _ = _severity_meta(_safe(group.get("severity"), "Baixa"))
    lot = _safe(group.get("lot"), "SENSE LOT")
    check_code = _safe(group.get("check"))
    schema_count = len(group.get("schemas") or [])
    object_count = _incident_object_count(group)
    badge = Table([[Paragraph(f"<b>{_safe(group.get('severity'), 'Baixa')}</b>", ParagraphStyle("sev-badge", parent=styles["small"], textColor=severity_color, alignment=TA_CENTER))]], colWidths=[3.3 * cm])
    badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), severity_fill), ("BOX", (0, 0), (-1, -1), 0.7, severity_color), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

    metrics = Table(
        [[
            _pill(f"{schema_count} esquemes", styles, fill=severity_fill, border=severity_color, text_color=severity_color),
            _pill(f"{object_count} objectes", styles, fill=severity_fill, border=severity_color, text_color=severity_color),
            _pill(_deadline_text(group.get("termini_dies"), _safe(group.get("severity"))), styles, fill=colors.white, border=CARD_BORDER, text_color=TEXT),
        ]],
        colWidths=[(total_width - 24) / 3] * 3,
    )
    metrics.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    header = Table(
        [
            [
                Paragraph(f'<a name="{_lot_check_anchor(lot, check_code)}"/>{check_code} — {_safe(group.get("title"))}', ParagraphStyle("incident-check-title", parent=styles["heroCheck"], fontSize=15, leading=19)),
                badge,
            ],
            [
                Table(
                    [[
                        _pill(f"LOT {lot}", styles, fill=colors.white, border=CARD_BORDER, text_color=TEXT),
                        _pill("Context del lot", styles, fill=colors.white, border=CARD_BORDER, text_color=MUTED),
                    ]],
                    colWidths=[3.6 * cm, 3.0 * cm],
                ),
                "",
            ],
            [
                Table(
                    [[
                        _internal_link("Tornar al mini índex del lot", _lot_subanchor(lot, "mini-index"), styles["small"]),
                        _internal_link("Tornar al capçal del lot", _lot_anchor(lot), styles["small"]),
                    ]],
                    colWidths=[4.8 * cm, 4.4 * cm],
                ),
                "",
            ],
            [metrics, ""],
        ],
        colWidths=[total_width * 0.72, total_width * 0.28],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CARD_FILL),
                ("BACKGROUND", (0, 0), (0, 3), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
                ("LINEBEFORE", (0, 0), (0, 3), 4, severity_color),
                ("SPAN", (0, 1), (1, 1)),
                ("SPAN", (0, 2), (1, 2)),
                ("SPAN", (0, 3), (1, 3)),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    content: List[Any] = [
        KeepTogether([header]),
        Spacer(1, 0.12 * cm),
        _paired_info_boxes(
            "Què s'ha detectat",
            _safe(group.get("description")),
            "Impacte",
            _safe(group.get("impacte")),
            styles,
            total_width,
            left_fill=colors.white,
            right_fill=severity_fill,
        ),
        Spacer(1, 0.14 * cm),
        _section_banner(
            "Esquemes afectats",
            "Objectes afectats agrupats per esquema per facilitar la revisió del lot.",
            PRIMARY,
            PRIMARY_SOFT,
            total_width,
            styles,
        ),
    ]

    schemas = group.get("schemas") or []
    if schemas:
        for schema_group in schemas:
            content.append(Spacer(1, 0.08 * cm))
            content.extend(_schema_table_card(schema_group, total_width, styles))
            content.append(Spacer(1, 0.12 * cm))
    else:
        content.append(Paragraph("No hi ha esquemes detallats per a aquesta incidència.", styles["body"]))

    content.extend(
        [
            Paragraph("Acció requerida", styles["subsection"]),
            Paragraph(_safe(group.get("accio_recomanada")), styles["body"]),
            Spacer(1, 0.05 * cm),
            Paragraph("Validació posterior", styles["subsection"]),
            Paragraph(_safe(group.get("validacio_posterior")), styles["body"]),
        ]
    )
    content.append(Spacer(1, 0.30 * cm))
    return content


def _detail_table(columns: List[str], rows: List[Dict[str, Any]], width: float, styles: Dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(f"<b>{_safe(column)}</b>", styles["small"]) for column in columns]]
    for row in rows:
        data.append([Paragraph(_safe(row.get(column)), styles["small"]) for column in columns])
    if not columns:
        columns = ["Resultat"]
    col_width = width / max(len(columns), 1)
    return _simple_table(
        data,
        [col_width] * max(len(columns), 1),
        [
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbff")]),
            ("GRID", (0, 0), (-1, -1), 0.4, CARD_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ],
    )


def _detail_requires_landscape(columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> bool:
    if len(columns) >= 6:
        return True
    avg_header = sum(len(_safe(column)) for column in columns) / max(len(columns), 1)
    if avg_header > 18:
        return True
    if not rows:
        return False
    sample = next(iter(rows), {})
    return any(len(_safe(sample.get(column))) > 40 for column in columns)


def build_post_crq_experimental_pdf(profile: str, report: Dict[str, Any]) -> bytes:
    report_model = report.get("report_model") or {}
    if not report_model:
        raise ValueError("El PDF experimental requereix report_model al payload post-CRQ.")

    include_annex = bool(((report.get("report_options") or {}).get("include_annex")))
    annex_entries = _build_annex_entries(report_model) if include_annex else []
    execution_parameters = report_model.get("execution_parameters") or {}
    generated_at = _safe(execution_parameters.get("generated_at"))
    styles = _build_styles()

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.35 * cm,
        rightMargin=1.35 * cm,
        topMargin=1.7 * cm,
        bottomMargin=1.4 * cm,
    )
    portrait_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="portrait-frame")
    landscape_size = landscape(A4)
    landscape_frame = Frame(1.0 * cm, 1.2 * cm, landscape_size[0] - 2.0 * cm, landscape_size[1] - 2.2 * cm, id="landscape-frame")
    cover_frame = Frame(0, 0, A4[0], A4[1], id="cover-frame")
    doc.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[cover_frame], pagesize=A4, onPage=lambda c, d: _cover(c, d, profile, report_model, report)),
            PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4, onPage=lambda c, d: _header_footer(c, d, profile, generated_at)),
            PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_size, onPage=lambda c, d: _header_footer(c, d, profile, generated_at)),
        ]
    )

    story: List[Any] = [Spacer(1, 26 * cm), NextPageTemplate("portrait"), PageBreak()]

    lot_summary = _sort_lot_summary(report_model.get("lot_summary") or [])
    lot_summary_by_name = {_safe(item.get("lot"), "SENSE LOT"): item for item in lot_summary}
    lot_incident_groups = report_model.get("lot_incident_groups") or []
    incidents_by_lot: Dict[str, List[Dict[str, Any]]] = {}
    for group in lot_incident_groups:
        incidents_by_lot.setdefault(_safe(group.get("lot"), "SENSE LOT"), []).append(group)
    incidents_by_severity_and_lot = _group_incidents_by_severity_and_lot(lot_incident_groups)
    enabled_checks = _build_enabled_checks(report_model)
    summary_blurbs = _build_global_summary_blurbs(lot_summary)
    real_lot_names = {
        _safe(item.get("lot"), "SENSE LOT")
        for item in lot_summary
        if _safe(item.get("lot"), "SENSE LOT") not in {"", "-", "SENSE LOT"}
    }
    include_lot_map = len(real_lot_names) > 1
    grouped_sections = [
        ("critical", "Crítiques", "Incidències que requereixen una actuació immediata del lot.", CRITICAL, CRITICAL_SOFT),
        ("medium", "Mitjanes", "Incidències que s'han de planificar i corregir dins del termini de l'equip responsable.", MEDIUM, MEDIUM_SOFT),
        ("low", "Baixes", "Incidències que convé calendaritzar i tancar sense perdre traçabilitat.", LOW, LOW_SOFT),
    ]

    story.append(_anchor_paragraph("index", "Índex", styles["title"]))
    for anchor, title in _build_index_entries(bool(annex_entries), include_lot_map):
        if anchor == "cover":
            story.append(Paragraph(_safe(title), styles["toc"]))
        else:
            story.append(_internal_link(title, anchor, styles["toc"]))
    story.append(Spacer(1, 0.12 * cm))
    story.append(_render_enabled_checks_box(enabled_checks, styles, doc.width))
    if include_lot_map:
        story.append(Spacer(1, 0.12 * cm))
        story.append(_render_detected_lots_box(lot_summary, styles, doc.width))

    story.append(PageBreak())
    story.append(_anchor_paragraph("global-summary", "Resum executiu global", styles["section"]))
    story.append(_return_to_index(styles))
    story.append(Paragraph(summary_blurbs["executive"], styles["body"]))
    story.append(Paragraph(summary_blurbs["impact"], styles["body"]))
    story.append(Paragraph(summary_blurbs["priority"], styles["body"]))
    executive_pack = _build_executive_summary_v2(report, profile)
    story.append(Spacer(1, 0.08 * cm))
    story.append(Paragraph(f"Semàfor executiu: <b>{_safe(executive_pack['traffic_light']).upper()}</b> · Recomanació: <b>{_safe(executive_pack['recommendation'])}</b>", styles["subsection"]))
    story.append(Paragraph(f"Troballes totals: {_safe(executive_pack['total_findings'])} · Lots afectats: {_safe(executive_pack['lots_affected'])} · Lots crítics: {_safe(executive_pack['critical_lots'])} · Checks crítics amb troballes: {_safe(executive_pack['critical_checks_with_findings'])} · Checks crítics sense troballes: {_safe(executive_pack['critical_checks_without_findings'])}", styles["body"]))
    if executive_pack["top_risks"]:
        story.append(Paragraph("Top riscos", styles["subsection"]))
        for risk in executive_pack["top_risks"]:
            story.append(Paragraph(f"• {_safe(risk)}", styles["body"]))
    if executive_pack["remediation_plan"]:
        story.append(Paragraph("Pla de remediació curt", styles["subsection"]))
        for step in executive_pack["remediation_plan"]:
            story.append(Paragraph(f"• {_safe(step)}", styles["body"]))
    story.append(Spacer(1, 0.08 * cm))
    story.append(Paragraph("Validacions de coherència", styles["subsection"]))
    if executive_pack["validation_issues"]:
        warning_rows = [[Paragraph("<b>Codi</b>", styles["small"]), Paragraph("<b>Missatge</b>", styles["small"])]]
        for issue in executive_pack["validation_issues"]:
            warning_rows.append([
                Paragraph(_safe(issue.get("code")), styles["small"]),
                Paragraph(_safe(issue.get("message")), styles["small"]),
            ])
        warning_table = _simple_table(
            warning_rows,
            [doc.width * 0.22, doc.width * 0.78],
            [
                ("BACKGROUND", (0, 0), (-1, 0), CRITICAL_SOFT),
                ("TEXTCOLOR", (0, 0), (-1, 0), CRITICAL),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fff9f9")]),
                ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ],
        )
        story.append(warning_table)
    else:
        story.append(Paragraph("Sense incidències de coherència detectades en aquesta execució experimental.", styles["body"]))
    story.append(_lots_overview_cards(lot_summary, styles, doc.width))
    story.append(Spacer(1, 0.18 * cm))
    story.append(_prioritized_lots_table(lot_summary, styles, doc.width))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Context de l'auditoria", styles["subsection"]))
    parameter_rows = [
        ("Perfil", _safe(execution_parameters.get("profile") or profile)),
        ("Data i hora", generated_at),
        ("Finestra consultada", _time_window_label(report)),
        ("Període aplicat", _safe(execution_parameters.get("time_filter_label"))),
        ("Idioma", _safe(execution_parameters.get("language"), "Català")),
        ("Codificació", _safe(execution_parameters.get("encoding"), "UTF-8")),
        ("Fitxer de checks", _safe(execution_parameters.get("source_file"))),
        ("Esquemes o lots filtrats", ", ".join(_safe(item) for item in (execution_parameters.get("schemas") or [])) or "Tots"),
    ]
    parameter_data = [[Paragraph(f"<b>{label}</b>", styles["body"]), Paragraph(value, styles["body"])] for label, value in parameter_rows]
    parameter_table = _simple_table(
        parameter_data,
        [doc.width * 0.28, doc.width * 0.72],
        [
            ("BACKGROUND", (0, 0), (-1, -1), CARD_FILL),
            ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [CARD_FILL, colors.white]),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ],
    )
    story.append(parameter_table)

    if include_lot_map:
        story.append(PageBreak())
        story.append(_anchor_paragraph("lot-map", "Mapa de lots detectats", styles["section"]))
        story.append(_return_to_index(styles))
        story.append(Paragraph("Aquesta pàgina actua com a mapa de navegació: resumeix cada lot detectat i enllaça directament amb el seu detall dins del document.", styles["body"]))
        for flowable in _lots_navigation_cards(lot_summary, incidents_by_lot, styles, doc.width):
            story.append(flowable)

    story.append(PageBreak())
    story.append(_anchor_paragraph("lot-detail", "Detall per lot", styles["section"]))
    story.append(_return_to_index(styles))
    if not lot_summary:
        story.append(Paragraph("No hi ha lots amb incidències per desenvolupar en el cos principal del document.", styles["body"]))
    else:
        anchored_lots: set[str] = set()
        for lot_index, summary_item in enumerate(lot_summary):
            lot = _safe(summary_item.get("lot"), "SENSE LOT")
            lot_groups = []
            for severity_key, _, _, _, _ in grouped_sections:
                lot_groups.extend((incidents_by_severity_and_lot.get(severity_key) or {}).get(lot) or [])
            if lot_index > 0:
                story.append(PageBreak())
            story.append(
                KeepTogether(
                    [
                        _lot_detail_header_card(lot, summary_item, styles, doc.width),
                        Spacer(1, 0.10 * cm),
                        _lot_mini_index_box(lot, lot_groups, styles, doc.width),
                    ]
                )
            )
            story.append(Spacer(1, 0.14 * cm))
            summary_banner = _lot_stage_banner(
                f"LOT {lot} — Resum executiu del lot",
                "Fotografia executiva del lot amb KPIs, volum i abast del canvi abans d'entrar en l'anàlisi.",
                PRIMARY,
                PRIMARY_SOFT,
                doc.width,
                styles,
                anchor=_lot_subanchor(lot, "summary"),
            )
            priority_color, priority_fill, _ = _severity_meta(_lot_priority_label(summary_item))
            summary_card = _lot_operational_summary_card(
                lot,
                summary_item,
                lot_groups,
                priority_color,
                priority_fill,
                doc.width,
                styles,
            )
            story.append(
                KeepTogether(
                    [
                        summary_banner,
                        _return_to_index(styles),
                        summary_card,
                    ]
                )
            )
            anchored_lots.add(lot)
            story.append(Spacer(1, 0.14 * cm))
            story.append(
                _lot_stage_banner(
                    f"LOT {lot} — Anàlisi del lot",
                    "Lectura executiva del que s'ha detectat, l'impacte probable i el criteri d'actuació del lot.",
                    MEDIUM,
                    MEDIUM_SOFT,
                    doc.width,
                    styles,
                )
            )
            story.extend(_lot_analysis_flowables(lot, summary_item, lot_groups, styles))
            story.append(Spacer(1, 0.16 * cm))
            story.append(
                _lot_stage_banner(
                    f"LOT {lot} — Detall per check",
                    "Evidència agrupada per criticitat i per check, amb objectes afectats i traçabilitat tècnica.",
                    SUCCESS,
                    SUCCESS_SOFT,
                    doc.width,
                    styles,
                    anchor=_lot_subanchor(lot, "findings"),
                )
            )

            has_findings_for_lot = False
            for severity_key, section_title, section_subtitle, section_color, section_fill in grouped_sections:
                groups = (incidents_by_severity_and_lot.get(severity_key) or {}).get(lot) or []
                if not groups:
                    continue
                has_findings_for_lot = True
                story.append(Spacer(1, 0.08 * cm))
                story.append(_section_banner(section_title, section_subtitle, section_color, section_fill, doc.width, styles))
                for group in groups:
                    story.extend(_incident_card(group, styles, doc.width))
            if not has_findings_for_lot:
                story.append(Paragraph("No hi ha incidències detallades associades a aquest lot en aquesta execució.", styles["body"]))
            story.append(Spacer(1, 0.12 * cm))
            story.extend(_lot_final_observations(lot, summary_item, styles))

    story.append(PageBreak())
    story.append(_anchor_paragraph("annex-check", "Annex A - Vista transversal per check", styles["section"]))
    story.append(_return_to_index(styles))
    if not enabled_checks:
        story.append(Paragraph("No hi ha checks executats amb detall disponible per construir la vista transversal.", styles["body"]))
    for section in report_model.get("detail_sections") or []:
        use_landscape = _detail_requires_landscape(section.get("columns") or [], section.get("rows") or [])
        story.append(NextPageTemplate("landscape" if use_landscape else "portrait"))
        story.append(PageBreak())
        current_width = landscape_frame.width if use_landscape else portrait_frame.width
        story.append(Paragraph(f"{_safe(section.get('check_id'))} - {_safe(section.get('title'))}", styles["cardTitle"]))
        story.append(Paragraph(f"<b>Criticitat:</b> {_safe(section.get('criticality'))} · <b>Temps:</b> {_humanize_duration_ms(section.get('duration_ms'))} · <b>Troballes:</b> {_safe(section.get('finding_count'))}", styles["body"]))
        if section.get("overview"):
            story.append(Paragraph(_safe(section.get("overview")), styles["body"]))
        story.append(_detail_table(section.get("columns") or [], section.get("rows") or [], current_width, styles))
        story.append(NextPageTemplate("portrait"))

    if annex_entries:
        story.append(PageBreak())
        story.append(_anchor_paragraph("annex-functional", "Annex B - Anàlisi funcional dels checks", styles["section"]))
        story.append(_return_to_index(styles))
        for entry in annex_entries:
            annex_card = Table(
                [[
                    [
                        Paragraph(f"{_safe(entry.get('check_id'))} - {_safe(entry.get('title'))}", styles["cardTitle"]),
                        Paragraph(f"<b>Què detecta:</b> {_safe(entry.get('que_detecta'))}", styles["body"]),
                        Paragraph(f"<b>Per què és important:</b> {_safe(entry.get('per_que_es_important'))}", styles["body"]),
                        Paragraph(f"<b>Impacte sobre el lot:</b> {_safe(entry.get('impacte_sobre_lot'))}", styles["body"]),
                        Paragraph(f"<b>Com s'ha de revisar:</b> {_safe(entry.get('com_revisar'))}", styles["body"]),
                        Paragraph(f"<b>Com es pot corregir:</b> {_safe(entry.get('com_corregir'))}", styles["body"]),
                        Paragraph(f"<b>Validació posterior:</b> {_safe(entry.get('validacio_posterior'))}", styles["body"]),
                    ]
                ]],
                colWidths=[doc.width],
            )
            annex_card.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CARD_FILL), ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER), ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 12)]))
            story.append(annex_card)
            story.append(Spacer(1, 0.18 * cm))

    story.append(PageBreak())
    story.append(_anchor_paragraph("final", "Observacions finals i properes passes", styles["section"]))
    story.append(_return_to_index(styles))
    final_observations = report_model.get("final_observations") or {}
    if final_observations.get("blocking_errors"):
        story.append(Paragraph("Bloquejos", styles["cardTitle"]))
        for item in final_observations.get("blocking_errors") or []:
            story.append(Paragraph(f"{_safe(item.get('check_id'))}: {_safe(item.get('error'))}", styles["body"]))
    if final_observations.get("warnings"):
        story.append(Paragraph("Advertiments", styles["cardTitle"]))
        for item in final_observations.get("warnings") or []:
            story.append(Paragraph(_safe(item), styles["body"]))
    if final_observations.get("next_steps"):
        story.append(Paragraph("Següents passos", styles["cardTitle"]))
        for item in final_observations.get("next_steps") or []:
            story.append(Paragraph(_safe(item), styles["body"]))

    doc.build(story)
    return buffer.getvalue()


def _build_experimental_appendix_pdf(profile: str, report: Dict[str, Any]) -> bytes:
    report_model = report.get("report_model") or {}
    execution_parameters = report_model.get("execution_parameters") or {}
    styles = _build_styles()
    executive_pack = _build_executive_summary_v2(report, profile)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.55 * cm,
        rightMargin=1.55 * cm,
        topMargin=1.45 * cm,
        bottomMargin=1.35 * cm,
    )

    story: List[Any] = []
    story.append(Paragraph("Annex V2 - Resum executiu experimental", styles["section"]))
    story.append(
        Paragraph(
            "Aquesta pàgina conserva el format principal del PDF original i afegeix només la capa experimental de resum i validació.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 0.15 * cm))

    parameter_rows = [
        ("Perfil", _safe(execution_parameters.get("profile") or profile)),
        ("Finestra consultada", _time_window_label(report)),
        ("Període aplicat", _safe(execution_parameters.get("time_filter_label"))),
        ("Semàfor executiu", _safe(executive_pack["traffic_light"]).upper()),
        ("Recomanació", _safe(executive_pack["recommendation"])),
    ]
    parameter_table = _simple_table(
        [[Paragraph(f"<b>{label}</b>", styles["body"]), Paragraph(value, styles["body"])] for label, value in parameter_rows],
        [6.2 * cm, 10.4 * cm],
        [
            ("BACKGROUND", (0, 0), (-1, -1), CARD_FILL),
            ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [CARD_FILL, colors.white]),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ],
    )
    story.append(parameter_table)
    story.append(Spacer(1, 0.12 * cm))

    metric_rows = [
        [
            _metric_card("Troballes totals", executive_pack["total_findings"], CRITICAL, CRITICAL_SOFT, styles),
            _metric_card("Lots afectats", executive_pack["lots_affected"], PRIMARY, PRIMARY_SOFT, styles),
            _metric_card("Lots crítics", executive_pack["critical_lots"], MEDIUM, MEDIUM_SOFT, styles),
        ],
        [
            _metric_card("Checks crítics amb troballes", executive_pack["critical_checks_with_findings"], CRITICAL, CRITICAL_SOFT, styles),
            _metric_card("Checks crítics sense troballes", executive_pack["critical_checks_without_findings"], LOW, LOW_SOFT, styles),
            _metric_card("Checks totals", executive_pack["total_checks"], PRIMARY, PRIMARY_SOFT, styles),
        ],
    ]
    metrics_table = Table(metric_rows, colWidths=[5.3 * cm, 5.3 * cm, 5.3 * cm])
    metrics_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(metrics_table)
    story.append(Spacer(1, 0.12 * cm))

    if executive_pack["top_risks"]:
        story.append(Paragraph("Top riscos", styles["subsection"]))
        for risk in executive_pack["top_risks"][:3]:
            story.append(Paragraph(f"• {_safe(risk)}", styles["body"]))

    if executive_pack["remediation_plan"]:
        story.append(Spacer(1, 0.05 * cm))
        story.append(Paragraph("Pla de remediació curt", styles["subsection"]))
        for step in executive_pack["remediation_plan"][:3]:
            story.append(Paragraph(f"• {_safe(step)}", styles["body"]))

    story.append(Spacer(1, 0.08 * cm))
    story.append(Paragraph("Validacions de coherència", styles["subsection"]))
    if executive_pack["validation_issues"]:
        validation_rows = [[Paragraph("<b>Codi</b>", styles["small"]), Paragraph("<b>Missatge</b>", styles["small"])]]
        for issue in executive_pack["validation_issues"][:4]:
            validation_rows.append(
                [
                    Paragraph(_safe(issue.get("code")), styles["small"]),
                    Paragraph(_safe(issue.get("message")), styles["small"]),
                ]
            )
        validation_table = _simple_table(
            validation_rows,
            [4.0 * cm, 12.6 * cm],
            [
                ("BACKGROUND", (0, 0), (-1, 0), CRITICAL_SOFT),
                ("TEXTCOLOR", (0, 0), (-1, 0), CRITICAL),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fff9f9")]),
                ("BOX", (0, 0), (-1, -1), 0.8, CARD_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ],
        )
        story.append(validation_table)
    else:
        story.append(Paragraph("Sense incidències de coherència detectades en aquesta execució experimental.", styles["body"]))

    story.append(Spacer(1, 0.08 * cm))
    story.append(
        Paragraph(
            "Aquesta annexa no altera el cos principal del PDF original; només afegeix la lectura executiva V2 per comparació.",
            styles["small"],
        )
    )
    doc.build(story)
    return buffer.getvalue()


def build_post_crq_experimental_pdf(profile: str, report: Dict[str, Any]) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from src.api.post_crq_audit import build_post_crq_pdf_report

    base_pdf = build_post_crq_pdf_report(profile, report)
    appendix_pdf = _build_experimental_appendix_pdf(profile, report)

    writer = PdfWriter()
    for source in (base_pdf, appendix_pdf):
        reader = PdfReader(io.BytesIO(source))
        for page in reader.pages:
            writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
