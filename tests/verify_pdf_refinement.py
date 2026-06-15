import io
import sys
from pathlib import Path
from pypdf import PdfReader

# Add project root to sys.path
project_root = r"c:\Users\45485456N\OneDrive - Generalitat de Catalunya\.....Antigravity\Dashboard E13BD"
sys.path.insert(0, project_root)

from src.api.post_crq_audit import _build_post_crq_pdf_from_report_model_final_v7

# Mock data reflecting the new requirements
mock_report = {
    "context": {
        "time_filter": {"days_back": 1, "mode": "range"},
        "schemas": ["SCOTT", "HR"],
        "generated_at": "2026-03-16 17:00:00"
    },
    "report_model": {
        "execution_parameters": {"generated_at": "2026-03-16 17:00:00"},
        "enabled_checks": [
            {
                "check_id": "CHECK_01",
                "title": "Taules sense índex i accents (índex)",
                "criticality": "CRITIC"
            },
            {
                "check_id": "CHECK_11",
                "title": "Operacions N+1 (ï, À, é)",
                "criticality": "MITJA"
            }
        ],
        "detail_sections": [
            {
                "check_id": "CHECK_01",
                "title": "Taules sense índex i accents (índex)",
                "criticality": "CRITIC",
                "columns": ["Owner", "Table"],
                "rows": [{"Owner": "SCOTT", "Table": "EMP"}, {"Owner": "HR", "Table": "DEPT"}]
            }
        ],
        "summary": {
            "lot_counts": [
                {"lot": "LOT_TEST", "CRITIC": 1, "MITJA": 1, "BAIX": 0}
            ]
        }
    }
}

try:
    print("Generating PDF...")
    pdf_bytes = _build_post_crq_pdf_from_report_model_final_v7("TEST_PROFILE", mock_report)

    output_dir = Path(project_root) / "tmp" / "pdfs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "verify_refinement.pdf"
    with output_path.open("wb") as f:
        f.write(pdf_bytes)

    reader = PdfReader(io.BytesIO(pdf_bytes))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages[:6])

    assert "Informe d'auditoria post-CRQ" in extracted
    assert "Índex" in extracted
    assert "Context de l'auditoria" in extracted

    print(f"PDF generated successfully at: {output_path}")
    print(f"Pages: {len(reader.pages)}")
    print(f"PDF size: {len(pdf_bytes)} bytes")

except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
