import unittest
import zipfile
import io
from typing import Any, Dict
from pypdf import PdfReader
from src.api.post_crq_audit import generate_post_crq_zip_by_lots

class TestProva2Zip(unittest.TestCase):
    def setUp(self):
        # Simulem un report_model amb dos lots
        self.mock_report = {
            "context": {
                "profile": "TEST_DB",
                "schemas": ["APP_USER", "APP_AUX"],
                "time_filter": {"mode": "preset", "preset": "weekly", "days_back": 7},
            },
            "report_model": {
                "execution_parameters": {
                    "profile": "TEST_DB",
                    "generated_at": "2026-03-16 12:00:00",
                    "time_window": {"start_at": "2026-03-09T00:00", "end_at": "2026-03-16T12:00"},
                },
                "enabled_checks": [
                    {"check_id": "CHECK_03", "title": "SEQÜÈNCIES SENSE CACHE", "criticality": "Crític"},
                    {"check_id": "CHECK_01", "title": "TAULES SENSE PRIMARY KEY", "criticality": "Mitjà"},
                ],
                "lot_summary": [
                    {"lot": "LOT_A", "critical": 1, "medium": 0, "low": 0, "checks": ["CHECK_03"]},
                    {"lot": "LOT_B", "critical": 0, "medium": 2, "low": 1, "checks": ["CHECK_01"]},
                ],
                "lot_incident_groups": [
                    {
                        "lot": "LOT_A",
                        "check": "CHECK_03",
                        "title": "SEQÜÈNCIES SENSE CACHE",
                        "description": "S'ha detectat una seqüència sense cache.",
                        "severity": "Crític",
                        "termini_dies": 0,
                        "impacte": "Pot degradar insercions concurrents.",
                        "accio_recomanada": "Definir CACHE adequat.",
                        "validacio_posterior": "Reexecutar el check.",
                        "schemas": [{"nom": "APP_USER", "object_count": 1, "objectes": [{"OBJECTE": "SEQ_ALPHA", "TIPUS": "SEQUENCE", "DADA TÈCNICA": "CACHE=0"}]}],
                    },
                    {
                        "lot": "LOT_B",
                        "check": "CHECK_01",
                        "title": "TAULES SENSE PRIMARY KEY",
                        "description": "S'ha detectat una taula sense PK.",
                        "severity": "Mitjà",
                        "termini_dies": 15,
                        "impacte": "Pot afectar la integritat.",
                        "accio_recomanada": "Definir PRIMARY KEY.",
                        "validacio_posterior": "Reexecutar el check.",
                        "schemas": [{"nom": "APP_AUX", "object_count": 1, "objectes": [{"OBJECTE": "TMP_BETA", "TIPUS": "TABLE", "DADA TÈCNICA": "Sense PK"}]}],
                    },
                ],
                "detail_sections": [
                    {
                        "check_id": "CHECK_03",
                        "title": "SEQÜÈNCIES SENSE CACHE",
                        "criticality": "Crític",
                        "duration_ms": 1000,
                        "finding_count": 1,
                        "columns": ["Lot", "OBJECTE", "TIPUS", "DADA TÈCNICA"],
                        "rows": [{"Lot": "LOT_A", "OBJECTE": "SEQ_ALPHA", "TIPUS": "SEQUENCE", "DADA TÈCNICA": "CACHE=0"}],
                    },
                    {
                        "check_id": "CHECK_01",
                        "title": "TAULES SENSE PRIMARY KEY",
                        "criticality": "Mitjà",
                        "duration_ms": 900,
                        "finding_count": 1,
                        "columns": ["Lot", "OBJECTE", "TIPUS", "DADA TÈCNICA"],
                        "rows": [{"Lot": "LOT_B", "OBJECTE": "TMP_BETA", "TIPUS": "TABLE", "DADA TÈCNICA": "Sense PK"}],
                    },
                ],
                "final_observations": {"blocking_errors": [], "warnings": [], "next_steps": ["Aplicar correccions."]},
            },
            "results_by_check": []
        }
        self.profile = "TEST_DB"

    def test_generate_zip_structure(self):
        """Valida que es genera un ZIP amb el resum i els PDFs de cada lot."""
        # Nota: Necessitem mockejar build_post_crq_pdf_report si no volem que reportlab intenti generar PDFs reals
        # Però per aquest test d'integració, veurem si la estructura del ZIP és correcta.
        
        zip_bytes = generate_post_crq_zip_by_lots(self.profile, self.mock_report)
        
        self.assertIsInstance(zip_bytes, bytes)
        self.assertTrue(len(zip_bytes) > 0)
        
        # Obrir el ZIP i verificar contingut
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            file_names = zf.namelist()
            
            # Verificació de noms de fitxer
            self.assertIn("00_resum_general.pdf", file_names)
            self.assertIn("01_lot_LOT_A.pdf", file_names)
            self.assertIn("02_lot_LOT_B.pdf", file_names)
            self.assertEqual(len(file_names), 3)

    def test_empty_lots(self):
        """Valida el comportament quan no hi ha lots (només resum general)."""
        mock_report_no_lots = {
            "report_model": {
                "lot_summary": []
            }
        }
        zip_bytes = generate_post_crq_zip_by_lots(self.profile, mock_report_no_lots)
        
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            file_names = zf.namelist()
            self.assertIn("00_resum_general.pdf", file_names)
            self.assertEqual(len(file_names), 1)

    def test_zip_reports_use_same_visual_renderer(self):
        zip_bytes = generate_post_crq_zip_by_lots(self.profile, self.mock_report)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            general_reader = PdfReader(io.BytesIO(zf.read("00_resum_general.pdf")))
            lot_reader = PdfReader(io.BytesIO(zf.read("01_lot_LOT_A.pdf")))

        general_cover = general_reader.pages[0].extract_text() or ""
        general_index = general_reader.pages[1].extract_text() or ""
        lot_cover = lot_reader.pages[0].extract_text() or ""
        lot_index = lot_reader.pages[1].extract_text() or ""

        self.assertIn("Informe d'auditoria post-CRQ", general_cover)
        self.assertIn("Resum global", general_cover)
        self.assertIn("Índex", general_index)
        self.assertIn("Context de l'auditoria", general_index)
        self.assertIn("Objectes afectats", "\n".join(page.extract_text() or "" for page in general_reader.pages[:8]))

        self.assertIn("Informe d'auditoria post-CRQ", lot_cover)
        self.assertIn("Índex", lot_index)
        self.assertIn("LOT_A", "\n".join(page.extract_text() or "" for page in lot_reader.pages[:8]))

if __name__ == "__main__":
    unittest.main()
