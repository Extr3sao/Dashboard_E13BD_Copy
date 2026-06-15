import unittest
import zipfile
import io
import os
import sys
from typing import Any, Dict

# Afegim el directori arrel al path
sys.path.append(os.getcwd())

from src.api.post_crq_audit import generate_post_crq_zip_by_lots

class TestReproZipFail(unittest.TestCase):
    def setUp(self):
        self.profile = "TEST_DB"

    def test_zip_fail_when_lots_in_rows_but_not_in_summary(self):
        """
        Reprodueix la falla quan hi ha lots a les files detallades però NO al resum de lots.
        Això pot passar si la lògica de consolidació no ha inclòs el lot per algun motiu (p. ex. filtre).
        """
        mock_report = {
            "report_model": {
                "execution_parameters": {
                    "profile": "TEST_DB",
                    "generated_at": "2026-03-16 12:00:00"
                },
                "lot_summary": [], # Buit!
                "detail_sections": []
            },
            "results_by_check": [
                {
                    "check_id": "CHECK_1",
                    "rows": [
                        {"Lot": "LOT_X", "Altres": "Dades"}
                    ]
                }
            ]
        }
        
        # Això hauria de fallar si filter_report_model_for_lot llença ValueError
        try:
            zip_bytes = generate_post_crq_zip_by_lots(self.profile, mock_report)
            self.assertIsInstance(zip_bytes, bytes)
            
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                file_names = zf.namelist()
                print(f"File names in ZIP: {file_names}")
                self.assertIn("01_lot_LOT_X.pdf", file_names)
        except ValueError as e:
            print(f"CAUGHT EXPECTED ERROR: {e}")
            raise e

if __name__ == "__main__":
    unittest.main()
