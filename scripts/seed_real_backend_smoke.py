from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.automation_store import AutomationStore
from src.core.internal_db import InternalDBManager
from src.core.time_utils import utc_now_iso
from src.api.alerting_engine import AlertingService
from src.api.audit_evidence import AuditEvidenceService
from src.api.finding_engine import FindingStore
from src.api.investigation_engine import InvestigationStore


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

    # Seed a durable diagnostic AuditRun so the browser smoke exercises the
    # real API, SQLite projections, Findings and operator UI without claiming
    # that this fixture came from an Oracle server.
    findings=FindingStore(internal_db)
    alerts=AlertingService(findings)
    audit_evidence=AuditEvidenceService(internal_db,findings,alerts,runtime={"application":"E13DB","application_version":"playwright-fixture","git_sha":"fixture-only","schema_version":"1"})
    investigations=InvestigationStore(findings)
    findings.investigation_service=investigations
    audit_id="AUD-SCH-PLAYWRIGHT-DIAGNOSTICS"
    observed=time.time()
    audit_evidence.begin(audit_id,"E13DB",trigger_type="SCHEDULED",trigger_reference="playwright-fixture:scheduled-job",target_context={"environment":"production","criticality":"critical"})
    capability_status={
        "BASE_DICTIONARY":"AVAILABLE","SESSION_VISIBILITY":"AVAILABLE","GV_SESSION_VISIBILITY":"AVAILABLE",
        "LOCK_VISIBILITY":"AVAILABLE","GV_LOCK_VISIBILITY":"AVAILABLE","SQL_VISIBILITY":"AVAILABLE",
        "SQL_STATS_VISIBILITY":"AVAILABLE","GV_SQL_STATS_VISIBILITY":"AVAILABLE","SQL_PLAN_VISIBILITY":"AVAILABLE",
        "GV_SQL_PLAN_VISIBILITY":"AVAILABLE","STATISTICS_VISIBILITY":"AVAILABLE","SEGMENT_VISIBILITY":"AVAILABLE",
        "STORAGE_VISIBILITY":"AVAILABLE","TEMP_STORAGE_VISIBILITY":"AVAILABLE","TEMPFILE_VISIBILITY":"AVAILABLE",
        "CDB_VISIBILITY":"AVAILABLE","INSTANCE_VISIBILITY":"AVAILABLE","RAC_VISIBILITY":"AVAILABLE",
        "AWR_ALLOWED":"NOT_LICENSED","ASH_ALLOWED":"NOT_LICENSED",
    }
    diagnostic_report={
        "audit_type":"oracle_diagnostics","audit_run_id":audit_id,"trigger_type":"SCHEDULED",
        "trigger_reference":"playwright-fixture:scheduled-job","runtime_identity":{"application":"E13DB","application_version":"playwright-fixture","git_sha":"fixture-only","schema_version":"1"},
        "rule_pack_identity":"playwright-diagnostic-fixture-v1",
        "capability_snapshot":{"schema":"ORACLE_CAPABILITY_SNAPSHOT_V1","database_id":"E13DB","engine":"oracle","engine_version":"19.22-fixture","connection_status":"AVAILABLE","connection_class":"AVAILABLE","capabilities":capability_status,"reasons":{"LOCK_VISIBILITY":"Read-only fixture metadata probe succeeded.","RAC_VISIBILITY":"Two fixture instances represented."},"required_privileges":[],"available_privileges":[],"privilege_discovery_status":"NOT_REQUIRED","rac_instance_count":2,"cdb_mode":"CDB","current_container_id":5,"cdb_scope":"PDB","license_gates":{"awr_license_acknowledged":False,"awr_privilege_attested":False,"ash_license_acknowledged":False,"ash_privilege_attested":False,"disclosure":"Fixture; no AWR/ASH reads."}},
        "context":{"profile":"E13DB","generated_at":observed,"diagnostic_options":{"blocking_warning_seconds":30,"blocking_critical_seconds":300,"tablespace_warning_percent":80,"tablespace_critical_percent":95}},
        "summary":{"checks_total":2,"checks_pass":0,"checks_warn":1,"checks_fail":1,"checks_error":0,"checks_skipped":0,"diagnostic_observations":6,"finding_envelopes":1,"query_count":8,"queries_executed":8,"queries_succeeded":8,"queries_failed":0,"queries_skipped":0,"query_budget":8,"query_metrics":[{"rule_id":rule,"duration_seconds":0.02,"row_count":1,"status":"AVAILABLE"} for rule in ("ORACLE_SESSIONS","ORACLE_BLOCKING","ORACLE_SQL_PERFORMANCE","ORACLE_PLAN_CHANGES","ORACLE_OBJECT_STATISTICS","ORACLE_SEGMENT_GROWTH","ORACLE_CAPACITY","ORACLE_TEMP_CAPACITY")],"capability_probe_count":24,"capability_discovery_seconds":0.18},
        "rule_results":[
            {"rule_id":"ORACLE_BLOCKING","database_id":"E13DB","rule_version":"oracle-diagnostics-v1","definition_hash":"fixture-blocking-v1","status":"FAIL","severity":"CRITICAL","started_at":observed-2,"finished_at":observed,"duration":2,"summary":"Observed root blocker SID 128 affecting three sessions in the fixture.","metrics":{"value":3,"affected_sessions":3,"chain_depth":2,"comparison_direction":"higher_is_worse"},"evidence":{"row_count":3},"error":None,"recommendation":"Inspect the transaction owner and application workload.","coverage_meaning":"evaluated"},
            {"rule_id":"ORACLE_PLAN_CHANGES","database_id":"E13DB","rule_version":"oracle-diagnostics-v1","definition_hash":"fixture-plan-v1","status":"WARN","severity":"MEDIUM","started_at":observed-1,"finished_at":observed,"duration":1,"summary":"Plan hash change observed for SQL_ID SQLA; causality is not established.","metrics":{"value":1,"comparison_direction":"higher_is_worse"},"evidence":{"row_count":1},"error":None,"recommendation":"Compare both plan shapes and comparable workload metrics.","coverage_meaning":"evaluated"},
        ],
        "finding_envelopes":[{"check_id":"ORACLE_BLOCKING","title":"Root blocker INST 1 / CON 5 / SID 128 / SERIAL 900 affects three sessions","schema":"ORACLE_SESSION","object_name":"inst=1:con=5:sid=128:serial=900","object_type":"SESSION_CHAIN","sql_severity":"CRITIC","runtime_status":"ok","evidence":{"root_blocker":"inst=1:con=5:sid=128:serial=900","sql_id":"SQLA","value":3,"affected_sessions":3,"chain_depth":2,"first_observed_epoch":observed-60,"chain":[{"blocking_instance":1,"blocking_session":128,"blocking_serial":900,"blocked_instance":1,"blocked_session":205,"blocked_serial":901,"con_id":5,"sql_id":"SQLA","wait_class":"Application","event":"enq: TX - row lock contention","wait_seconds":60,"depth":1},{"blocking_instance":1,"blocking_session":128,"blocking_serial":900,"blocked_instance":2,"blocked_session":244,"blocked_serial":902,"con_id":5,"sql_id":"SQLA","wait_class":"Application","event":"enq: TX - row lock contention","wait_seconds":45,"depth":1},{"blocking_instance":2,"blocking_session":244,"blocking_serial":902,"blocked_instance":2,"blocked_session":301,"blocked_serial":903,"con_id":5,"sql_id":"SQLA","wait_class":"Application","event":"enq: TX - row lock contention","wait_seconds":30,"depth":2}]},"row_index":0}],
        "diagnostic_observations":[
            {"category":"BLOCKING","identity_key":"inst=1:con=5:sid=128:serial=900","observed_at":observed,"inst_id":1,"con_id":5,"sql_id":"SQLA","metrics":{"affected_sessions":3,"chain_depth":2,"seconds_in_wait":60,"sample_count":2},"evidence":{"root_blocker":"inst=1:con=5:sid=128:serial=900","root_blocker_name":"APP","chain_integrity":"OBSERVED_LOCK_AND_SESSION_EDGES","first_observed_epoch":observed-60,"chain":[{"blocking_instance":1,"blocking_session":128,"blocking_serial":900,"blocked_instance":2,"blocked_session":244,"blocked_serial":902,"con_id":5,"sql_id":"SQLA","wait_class":"Application","event":"enq: TX - row lock contention","wait_seconds":60,"depth":1}]}},
            {"category":"SQL_PERFORMANCE","identity_key":"sql:inst=1:con=5:sql_id=sqla","observed_at":observed,"inst_id":1,"con_id":5,"sql_id":"SQLA","plan_hash":"789012","metrics":{"executions":10,"elapsed_microseconds":150000000,"cpu_microseconds":60000000,"buffer_gets":100000,"disk_reads":100,"rows_processed":400,"elapsed_per_exec_seconds":15},"evidence":{"sql_id":"SQLA","plan_hash":"789012","comparison_status":"NO_PRIOR_SNAPSHOT","metric_basis":"fixture lifetime average"}},
            {"category":"PLAN","identity_key":"plan:inst=1:con=5:sql_id=sqla","observed_at":observed,"inst_id":1,"con_id":5,"sql_id":"SQLA","plan_hash":"789012","metrics":{"executions":10,"elapsed_microseconds":150000000},"evidence":{"sql_id":"SQLA","plan_hash":"789012","previous_plan_hash":"123456","plan_change_observed":True,"plan_steps_status":"AVAILABLE","plan_steps":[{"id":1,"parent_id":0,"operation":"TABLE ACCESS","options":"FULL","object_owner":"APP","object_name":"ORDERS","object_type":"TABLE","cardinality":1000,"cost":45,"plan_hash":789012}]}},
            {"category":"STATISTICS","identity_key":"stats:con=5:owner=app:object=orders:partition=","observed_at":observed,"inst_id":1,"con_id":5,"sql_id":"SQLA","owner":"APP","object_name":"ORDERS","metrics":{"statistics_age_days":12,"num_rows":10000,"blocks":500,"sample_size":1000},"evidence":{"object_owner":"APP","object_name":"ORDERS","last_analyzed":"2026-10-01T10:00:00","stale_stats":True,"sql_id":"SQLA"}},
            {"category":"SEGMENT_GROWTH","identity_key":"segment:con=5:owner=APP:name=ORDERS:partition=:type=TABLE","observed_at":observed,"con_id":5,"owner":"APP","object_name":"ORDERS","metrics":{"segment_bytes":2000000000,"segment_growth_bytes":400000000},"evidence":{"object_owner":"APP","object_name":"ORDERS","tablespace":"APP_DATA","segment_type":"TABLE","comparison_status":"COMPARABLE_SNAPSHOTS"}},
            {"category":"CAPACITY","identity_key":"capacity:con=5:tablespace=APP_DATA","observed_at":observed,"con_id":5,"owner":"TABLESPACE","object_name":"APP_DATA","metrics":{"capacity_known":True,"allocated_bytes":1000,"used_bytes":950,"free_bytes":50,"max_bytes":2000,"used_percent":95,"assigned_space_used_percent":95,"max_capacity_percent":47.5,"effective_capacity_used_percent":47.5,"autoextend_headroom_bytes":1000,"effective_free_capacity_bytes":1050,"quota_used_bytes":None,"quota_limit_bytes":None,"quota_used_percent":None,"quota_unlimited":None,"physical_capacity_limit_bytes":None,"growth_bytes":100},"evidence":{"tablespace":"APP_DATA","contents":"PERMANENT","warning_percent":80,"critical_percent":95,"quota_scope":"connected Oracle user only; other owners are not assessed","physical_capacity_status":"UNKNOWN_NOT_EXPOSED_BY_CURRENT_ORACLE_DICTIONARY_PROBES","autoextensible":True}},
        ],
    }
    audit_evidence.persist_completed(audit_id,1,diagnostic_report,target_context={"environment":"production","criticality":"critical"})
    audit_evidence.reconcile(audit_id)
    diag_job=store.create_job({"name":"Oracle diagnostics scheduled fixture","enabled":False,"audit_type":"oracle_diagnostics","profile":"E13DB","schemas":[],"checks":[],"time_filter":{},"report_format":"markdown","schedule_type":"once","schedule_config":{"start_at":utc_now_iso(now+dt.timedelta(days=2))},"timeout_seconds":30,"next_run_at":None,"last_run_at":utc_now_iso(now),"delivery_targets":[],"severity_rules":[],"job_config":{"diagnostic_options":{"tablespace_warning_percent":80,"tablespace_critical_percent":95}}})
    diag_run=store.create_run(diag_job["id"],started_at=utc_now_iso(now),audit_run_id=audit_id)
    store.complete_run(diag_run,status="success",duration_ms=1000,summary={"audit_run_id":audit_id,"diagnostic_observations":6},report_path=None,deliveries=[],created_tasks=[])

    print(
        json.dumps(
            {
                "internal_db_path": internal_db_path,
                "automation_db_path": automation_db_path,
                "report_path": str(report_path),
                "job_id": job["id"],
                "run_id": run_id,
                "diagnostic_audit_run_id":audit_id,
            }
        )
    )


if __name__ == "__main__":
    main()
