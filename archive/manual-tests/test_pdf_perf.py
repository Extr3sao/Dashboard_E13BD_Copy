
import sys
import os
import io
import datetime
import json

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.api.report_builder import build_post_crq_pdf

# Mock data
report = {
    "context": {
        "source_file": "audit_post_crq.sql",
        "schemas": ["PRO", "E13BD"],
        "time_filter": {}
    },
    "summary": {
        "executed_checks": 10,
        "checks_with_findings": 3,
        "total_findings": 50
    },
    "results_by_check": [
        {
            "check_id": "C01",
            "title": "Taules sense index",
            "severitat": "ALTA",
            "status": "warning",
            "row_count": 5,
            "rows": [{"OWNER": "PRO", "TABLE_NAME": "T1"}]
        },
        {
            "check_id": "C02",
            "title": "Permisos excessius",
            "severitat": "CRÍTICA",
            "status": "warning",
            "row_count": 1,
            "rows": [{"GRANTEE": "PUBLIC", "PRIVILEGE": "DBA"}]
        }
    ]
}

print("Iniciant prova de generació PDF...")
start_time = datetime.datetime.now()

# Desactivem IA per la prova inicial per veure si és el motor de PDF
try:
    pdf_bytes = build_post_crq_pdf("PRO_TEST", report, ai_active=False)
    end_time = datetime.datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"PDF generat sense IA en {duration:.2f} segons.")
    
    with open("test_post_crq.pdf", "wb") as f:
        f.write(pdf_bytes)
    print("Fitxer 'test_post_crq.pdf' creat.")
except Exception as e:
    print(f"Error en la generació: {e}")

# Prova amb IA (si les claus estan configurades)
print("\nIniciant prova amb IA...")
start_time = datetime.datetime.now()
try:
    pdf_bytes = build_post_crq_pdf("PRO_TEST", report, ai_active=True)
    end_time = datetime.datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"PDF generat amb IA en {duration:.2f} segons.")
except Exception as e:
    print(f"Error en la generació amb IA: {e}")
