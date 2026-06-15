from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.automation_store import AutomationStore
from src.core.internal_db import InternalDBManager
from src.core.time_utils import utc_now_iso


def write_dummy_pdf(path: Path) -> None:
    path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )


def main() -> None:
    internal_db_path = os.environ["INTERNAL_DB_PATH"]
    automation_db_path = os.environ["AUTOMATION_DB_PATH"]
    output_dir = Path(os.environ["REAL_SMOKE_OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)

    internal_db = InternalDBManager(internal_db_path)
    store = AutomationStore(automation_db_path)

    internal_db.register_obsolete(
        "APP_REAL",
        "TMP_REAL",
        "TABLE",
        "Taula temporal detectada al smoke real",
        "MITJA",
        "Revisar i eliminar si ja no s'utilitza",
        "SMOKE_REAL",
    )

    store.update_delivery_config(
        {
            "smtp_host": "smtp.real.local",
            "smtp_port": 587,
            "smtp_username": "qa",
            "smtp_password": "secret",
            "smtp_use_tls": True,
            "from_email": "oracle-audit@example.com",
            "default_recipients": ["ops@example.com"],
            "failure_notification_recipients": ["suport@example.com"],
        }
    )
    store.update_delivery_routes(
        {
            "tic_summary_recipients": ["tic@example.com"],
            "providers": [
                {
                    "provider_code": "LOT_APP",
                    "label": "Aplicacions",
                    "emails": ["app@example.com"],
                    "enabled": True,
                },
                {
                    "provider_code": "LOT_AUX",
                    "label": "Auxiliar",
                    "emails": ["aux@example.com"],
                    "enabled": True,
                },
            ],
        }
    )
    store.upsert_master_lots(
        [
            {
                "code": "LOT_APP",
                "label": "Aplicacions",
                "description": "Lot principal de smoke real",
                "enabled": True,
            },
            {
                "code": "LOT_AUX",
                "label": "Auxiliar",
                "description": "Lot auxiliar de smoke real",
                "enabled": True,
            },
        ],
        actor="smoke-real",
        reason="Seed backend real smoke",
    )
    store.upsert_delivery_templates(
        [
            {
                "template_key": "provider_with_findings",
                "audience": "provider",
                "subject_template": "Assumpte real smoke",
                "body_template": "Cos real smoke",
                "enabled": True,
            }
        ],
        actor="smoke-real",
        reason="Seed backend real smoke",
    )
    store.create_severity_rule(
        {
            "scope": "global",
            "severity": "ALT",
            "create_task": True,
            "task_priority": "high",
            "send_email": True,
            "attach_report": True,
            "recipients": ["ops@example.com"],
            "conditions": {"min_findings": 1},
            "enabled": True,
        }
    )

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    started_at = utc_now_iso(now - dt.timedelta(hours=1))
    finished_at = utc_now_iso(now - dt.timedelta(minutes=55))
    next_run_at = utc_now_iso(now + dt.timedelta(days=1))
    current_month = now.strftime("%Y-%m")
    execution_id = "real-smoke-run-1"

    report_path = output_dir / "real_backend_run_report.pdf"
    write_dummy_pdf(report_path)

    job = store.create_job(
        {
            "name": "Job real backend",
            "enabled": True,
            "audit_type": "post_crq_distribution",
            "profile": "E13DB",
            "schemas": ["APP_REAL", "APP_AUX"],
            "checks": ["CHECK_01", "CHECK_03"],
            "time_filter": {"mode": "preset", "preset": "weekly", "days_back": 7},
            "report_format": "pdf",
            "schedule_type": "weekly",
            "schedule_config": {"start_at": next_run_at},
            "timeout_seconds": 120,
            "next_run_at": next_run_at,
            "last_run_at": finished_at,
            "delivery_targets": [],
            "severity_rules": [],
            "job_config": {},
        }
    )
    run_id = store.create_run(job["id"], started_at=started_at)
    store.complete_run(
        run_id,
        status="success",
        finished_at=finished_at,
        duration_ms=4200,
        summary={"total_findings": 2, "checks_with_findings": 1},
        report_path=str(report_path),
        deliveries=[],
        created_tasks=[],
    )
    store.replace_run_lot_statuses(
        run_id,
        job["id"],
        [
            {
                "lot": "LOT_APP",
                "detection_status": "CON_HALLAZGOS",
                "num_findings": 2,
                "report_generated": True,
                "email_sent": True,
                "delivery_audience": "provider",
                "delivery_result": "sent",
                "observaciones": "Smoke real",
            },
            {
                "lot": "LOT_AUX",
                "detection_status": "SIN_HALLAZGOS",
                "num_findings": 0,
                "report_generated": False,
                "email_sent": False,
                "delivery_audience": "provider",
                "delivery_result": "skipped_no_findings",
                "observaciones": "Sense troballes",
            },
        ],
        execution_id=execution_id,
        executed_at=finished_at,
    )
    store.create_retry_queue_item(
        {
            "run_id": run_id,
            "job_id": job["id"],
            "lot": "LOT_APP",
            "audience": "provider",
            "status": "pending",
            "requested_by": "smoke-real",
            "retry_mode": "manual",
        }
    )
    store.create_task(
        source_run_id=run_id,
        source_job_id=job["id"],
        title="Revisar LOT_APP",
        severity="ALT",
        priority="high",
        description="Tasques de smoke real",
        metadata={"lot": "LOT_APP"},
    )
    store.replace_post_crq_analytics(
        run_id,
        job["id"],
        {
            "execution": {
                "execution_id": execution_id,
                "executed_at": finished_at,
                "audit_type": "post_crq_distribution",
                "profile": "E13DB",
                "total_findings": 2,
                "checks_with_findings": 1,
                "checks_with_errors": 0,
                "lots_with_findings": 1,
                "schemas_in_scope": 2,
                "payload": {"month": current_month},
            },
            "lots": [
                {
                    "execution_id": execution_id,
                    "executed_at": finished_at,
                    "lot": "LOT_APP",
                    "detection_status": "CON_HALLAZGOS",
                    "finding_count": 2,
                    "schema_count": 1,
                    "check_count": 1,
                    "payload": {},
                },
                {
                    "execution_id": execution_id,
                    "executed_at": finished_at,
                    "lot": "LOT_AUX",
                    "detection_status": "SIN_HALLAZGOS",
                    "finding_count": 0,
                    "schema_count": 1,
                    "check_count": 1,
                    "payload": {},
                },
            ],
            "schemas": [
                {
                    "execution_id": execution_id,
                    "executed_at": finished_at,
                    "schema_name": "APP_REAL",
                    "lot": "LOT_APP",
                    "finding_count": 2,
                    "check_count": 1,
                    "payload": {},
                },
                {
                    "execution_id": execution_id,
                    "executed_at": finished_at,
                    "schema_name": "APP_AUX",
                    "lot": "LOT_AUX",
                    "finding_count": 0,
                    "check_count": 1,
                    "payload": {},
                },
            ],
            "checks": [
                {
                    "execution_id": execution_id,
                    "executed_at": finished_at,
                    "check_id": "CHECK_01",
                    "title": "TAULES RECENTS SENSE PRIMARY KEY",
                    "severity": "ALT",
                    "status": "ok",
                    "row_count": 2,
                    "finding_count": 2,
                    "affected_lots": 1,
                    "affected_schemas": 1,
                    "payload": {},
                }
            ],
        },
    )

    print(
        json.dumps(
            {
                "internal_db_path": internal_db_path,
                "automation_db_path": automation_db_path,
                "report_path": str(report_path),
                "job_id": job["id"],
                "run_id": run_id,
            }
        )
    )


if __name__ == "__main__":
    main()
