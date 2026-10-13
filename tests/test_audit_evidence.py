import json
from contextlib import contextmanager
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from src.api.alerting_engine import AlertingService
from src.api.audit_evidence import AuditEvidenceError, AuditEvidenceService, discover_oracle_capabilities, rule_capability_skip_reason
from src.api.automation_service import AutomationService
from src.api.check_engine import RuleDefinition, RuleResult, RuleStatus
from src.api.finding_engine import FindingStore
from src.api.post_crq_rule_adapter import definition_from_post_crq, result_from_post_crq
from src.core.automation_store import AutomationStore
from src.core.internal_db import InternalDBManager


@pytest.fixture
def stores(tmp_path):
    internal=InternalDBManager(str(tmp_path/"internal.db"))
    automation=AutomationStore(str(tmp_path/"automation.db"))
    findings=FindingStore(internal)
    alerts=AlertingService(findings)
    clock=[1_800_000_000.0]
    evidence=AuditEvidenceService(internal,findings,alerts,runtime={"application":"E13DB","application_version":"test","git_sha":"abc123","schema_version":"schema-test"},clock=lambda:clock[0])
    return internal,automation,findings,alerts,evidence,clock


def rule_result(database="DWH-TEST", *, value=11.4, status="FAIL", rule_id="SQL_ELAPSED"):
    return {"rule_id":rule_id,"database_id":database,"rule_version":"sha256:def-v1","definition_hash":"def-v1","status":status,"severity":"CRITICAL","started_at":10.0,"finished_at":12.0,"duration":2.0,"summary":"SQL execution duration increased","metrics":{"value":value,"duration_ms":2000,"comparison_direction":"higher_is_worse"},"evidence":{"elapsed_seconds":value,"sql_id":"SQL-TEST","sql_text":"select private_data","bind_values":{"token":"do-not-persist"}},"error":None,"object_type":"TABLE","owner":"APP","object_name":"ORDERS","recommendation":"Compare execution duration."}


def capability_snapshot(database="DWH-TEST", *, plan="AVAILABLE", engine_version="19.22"):
    return {"schema":"ORACLE_CAPABILITY_SNAPSHOT_V1","database_id":database,"engine":"oracle","engine_version":engine_version,"connection_status":"AVAILABLE","capabilities":{"BASE_DICTIONARY":"AVAILABLE","SQL_PLAN_VISIBILITY":plan,"AWR_ALLOWED":"NOT_LICENSED","ASH_ALLOWED":"NOT_LICENSED"},"reasons":{"SQL_PLAN_VISIBILITY":"test observation","AWR_ALLOWED":"license disabled"},"required_privileges":[],"available_privileges":[],"license_gates":{"awr_allowed":False,"ash_allowed":False},"probe_policy":"fixed read-only probes"}


def report(audit_id, database="DWH-TEST", *, value=11.4, status="FAIL", plan="AVAILABLE", trigger="MANUAL"):
    return {"audit_run_id":audit_id,"trigger_type":trigger,"trigger_reference":"unit-test","runtime_identity":{"git_sha":"abc123"},"rule_pack_identity":"pack-v1","capability_snapshot":capability_snapshot(database,plan=plan),"context":{"profile":database},"rule_results":[rule_result(database,value=value,status=status)],"finding_envelopes":[{"finding_id":"SQL_ELAPSED:0","check_id":"SQL_ELAPSED","title":"SQL elapsed","schema":"APP","object_name":"ORDERS","object_type":"TABLE","sql_severity":"CRITIC","runtime_status":"ok","evidence":{"elapsed_seconds":value,"sql_id":"SQL-TEST","source_row":{"private":"do-not-persist"}},"final_criticality":"CRITIC","row_index":0}]}


def test_authoritative_manual_and_scheduled_audit_runs_share_reconciliation(stores):
    _,_,findings,alerts,service,clock=stores
    context={"environment":"production","criticality":"critical"}
    ids=[]
    for index,(audit_id,trigger) in enumerate((("manual:1","MANUAL"),("schedule:job-4:tick-1","SCHEDULED"))):
        service.begin(audit_id,"DWH-TEST",trigger_type=trigger,trigger_reference=trigger.lower(),target_context=context)
        result=service.complete_and_reconcile(audit_id,1,report(audit_id,trigger=trigger,value=11.4 + index),target_context=context)
        ids.append(result["audit_run_id"])
        assert result["reconciliation_state"]=="RECONCILED"
    audits=findings._rows("SELECT audit_run_id,trigger_type,state,coverage_state,rule_pack_identity,capability_snapshot_id,reconciliation_state FROM audit_runs ORDER BY audit_run_id")
    assert {(row["audit_run_id"],row["trigger_type"],row["state"],row["reconciliation_state"]) for row in audits}=={("manual:1","MANUAL","SUCCESS","RECONCILED"),("schedule:job-4:tick-1","SCHEDULED","SUCCESS","RECONCILED")}
    assert len(findings.list_findings(database="DWH-TEST"))==1
    assert findings.list_findings(database="DWH-TEST")[0]["occurrences"]==2
    assert findings.list_red_flags(database_id="DWH-TEST")
    assert service.audit_detail("schedule:job-4:tick-1")["runtime_identity"]["git_sha"]=="abc123"
    assert service.audit_detail("schedule:job-4:tick-1")["capability_snapshot"]["snapshot"]["engine_version"]=="19.22"


def test_real_automation_execute_path_persists_and_deduplicates_scheduled_audit(stores,tmp_path):
    _,automation,findings,alerts,evidence,clock=stores
    job=automation.create_job({"name":"scheduled Post-CRQ","enabled":True,"audit_type":"post_crq","profile":"DWH-TEST","checks":["SQL_ELAPSED"],"schemas":["APP"],"schedule_type":"weekly","schedule_config":{"start_at":"2026-10-01T09:00"},"next_run_at":"2026-10-01T09:00:00Z","job_config":{"target_context":{"environment":"production","criticality":"critical"}},"report_format":"markdown","delivery_targets":[],"severity_rules":[]})
    service=AutomationService(automation,Mock(),reports_dir=str(tmp_path/"reports"))
    service.audit_evidence_service=evidence
    def run_post_crq(**kwargs):
        context=kwargs["audit_context"]
        return report(context["audit_run_id"],trigger="SCHEDULED")
    with patch.object(service,"_resolve_profile_config",return_value={"PROFILE_NAME":"DWH-TEST"}), \
         patch("src.api.automation_service.OracleDBManager",return_value=Mock()), \
         patch("src.api.automation_service.run_post_crq_audit",side_effect=run_post_crq) as execute, \
         patch.object(service,"_detect_report_generation_failure",return_value=None), \
         patch.object(service,"_write_report",return_value={"path":"test-report"}), \
         patch.object(service,"_deliver_targets",return_value=[]), \
         patch.object(service,"_finalize_report_output",return_value="test-report"), \
         patch.object(service,"_apply_rules",return_value=[]), \
         patch.object(service,"_persist_post_crq_analytics"):
        first=service.execute_job(job["id"],scheduled_reference="2026-10-01T09:00:00Z")
        second=service.execute_job(job["id"],scheduled_reference="2026-10-01T09:00:00Z")
    assert execute.call_count==1
    assert first["audit_run_id"]==second["audit_run_id"]
    assert second["summary"]["replayed"] is True
    assert findings.list_findings(database="DWH-TEST")[0]["occurrences"]==1
    runs=automation.list_runs(job["id"])
    assert all(item["audit_run_id"]==first["audit_run_id"] for item in runs)


def test_manual_api_uses_same_persisted_pipeline_and_replays_stably(stores,monkeypatch):
    import asyncio
    from src.api import main
    _,_,findings,alerts,service,_=stores
    monkeypatch.setattr(main,"audit_evidence_service",service)
    async def with_profile(_stage,profile,operation): return await operation(profile,Mock())
    monkeypatch.setattr(main,"_run_with_oracle_profile",with_profile)
    def run(**kwargs): return report(kwargs["audit_context"]["audit_run_id"],trigger="MANUAL")
    with patch.object(main,"run_post_crq_audit",side_effect=run) as execute:
        first=asyncio.run(main.run_post_crq({"profile":"DWH-TEST","audit_run_id":"manual-request-1","target_context":{"environment":"production","criticality":"critical"}}))
        replay=asyncio.run(main.run_post_crq({"profile":"DWH-TEST","audit_run_id":"manual-request-1","target_context":{"environment":"production","criticality":"critical"}}))
    assert execute.call_count==1
    assert first["audit_run_id"]==replay["audit_run_id"]=="manual-request-1"
    assert replay["status"]=="REPLAYED"
    assert replay["reconciliation_state"]=="RECONCILED"
    assert len(findings.list_findings(database="DWH-TEST"))==1
    assert service.audit_detail("manual-request-1")["trigger_type"]=="MANUAL"


def test_stable_run_id_duplicate_returns_receipt_without_reexecution(stores):
    _,_,findings,alerts,service,clock=stores
    service.begin("same-run","DWH-TEST",trigger_type="MANUAL")
    service.complete_and_reconcile("same-run",1,report("same-run"))
    duplicate=service.begin("same-run","DWH-TEST",trigger_type="MANUAL")
    assert duplicate["already_reconciled"]
    replay=service.replay_result("same-run")
    assert replay["status"]=="REPLAYED"
    assert findings.list_findings(database="DWH-TEST")[0]["occurrences"]==1
    assert findings._rows("SELECT COUNT(*) AS n FROM audit_reconciliation_receipts WHERE audit_run_id='same-run'")[0]["n"]==1


def test_completed_unreconciled_run_recovers_after_new_service_instance(stores):
    internal,automation,findings,alerts,service,clock=stores
    service.begin("crash-before-reconcile","DB",trigger_type="MANUAL")
    service.persist_completed("crash-before-reconcile",1,report("crash-before-reconcile","DB"))
    assert findings.list_findings(database="DB")==[]
    restarted=AuditEvidenceService(internal,findings,alerts,runtime=service.runtime,clock=lambda:clock[0]+1)
    recovered=restarted.recover_pending_reconciliations()
    assert recovered[0]["audit_run_id"]=="crash-before-reconcile"
    assert restarted.audit_detail("crash-before-reconcile")["reconciliation_state"]=="RECONCILED"
    assert len(findings.list_findings(database="DB"))==1
    assert restarted.recover_pending_reconciliations()==[]


def test_retry_after_commit_before_receipt_is_idempotent(stores,monkeypatch):
    _,_,findings,alerts,service,clock=stores
    service.begin("crash-during-reconcile","DB",trigger_type="SCHEDULED")
    service.persist_completed("crash-during-reconcile",1,report("crash-during-reconcile","DB",trigger="SCHEDULED"))
    original=findings.reconcile_post_crq
    calls=[0]
    def crash_after_projection(*args,**kwargs):
        result=original(*args,**kwargs); calls[0]+=1
        if calls[0]==1: raise RuntimeError("simulated process loss after committed projection")
        return result
    monkeypatch.setattr(findings,"reconcile_post_crq",crash_after_projection)
    with pytest.raises(AuditEvidenceError,match="audit_reconciliation_failed"):
        service.reconcile("crash-during-reconcile")
    monkeypatch.setattr(findings,"reconcile_post_crq",original)
    service.reconcile("crash-during-reconcile")
    finding=findings.list_findings(database="DB")[0]
    assert finding["occurrences"]==1
    assert findings._rows("SELECT status FROM audit_reconciliation_receipts WHERE audit_run_id='crash-during-reconcile'")[0]["status"]=="RECONCILED"


def test_capability_loss_skips_rule_and_does_not_resolve_finding(stores):
    _,_,findings,alerts,service,clock=stores
    service.begin("capable","DWH-TEST",trigger_type="MANUAL")
    service.complete_and_reconcile("capable",1,report("capable"))
    first=findings.list_findings(database="DWH-TEST")[0]
    skipped=report("privilege-lost",status="SKIPPED",plan="INSUFFICIENT_PRIVILEGES")
    skipped["rule_results"][0]["coverage_meaning"]="not_evaluated"
    service.begin("privilege-lost","DWH-TEST",trigger_type="SCHEDULED")
    service.complete_and_reconcile("privilege-lost",1,skipped)
    after=findings.get_finding(first["id"])
    assert after["status"]!="RESOLVED"
    audit=service.audit_detail("privilege-lost")
    assert audit["coverage_state"] in {"DEGRADED","UNKNOWN"}
    snapshot=audit["capability_snapshot"]["snapshot"]
    assert snapshot["capabilities"]["SQL_PLAN_VISIBILITY"]=="INSUFFICIENT_PRIVILEGES"


def test_failed_audit_records_health_without_resolving_existing_findings(stores):
    _,_,findings,alerts,service,_=stores
    service.begin("known-good","DWH-TEST",trigger_type="MANUAL")
    service.complete_and_reconcile("known-good",1,report("known-good"))
    finding=findings.list_findings(database="DWH-TEST")[0]
    attempt=service.begin("failed-run","DWH-TEST",trigger_type="SCHEDULED")
    result=service.fail("failed-run",attempt["attempt_no"],"UNREACHABLE","Oracle connection unavailable")
    assert result["state"]=="FAILED"
    assert findings.get_finding(finding["id"])["status"]!="RESOLVED"
    assert service.audit_detail("failed-run")["state"]=="FAILED"
    assert service.audit_detail("failed-run")["attempts"][0]["failure_class"]=="UNREACHABLE"


def test_capability_snapshot_is_immutable_and_deterministically_identified(stores):
    _,_,_,_,service,clock=stores
    service.begin("snap-1","DB",trigger_type="MANUAL")
    service.persist_completed("snap-1",1,report("snap-1","DB",plan="AVAILABLE"))
    first=service.audit_detail("snap-1")["capability_snapshot"]
    service.begin("snap-2","DB",trigger_type="MANUAL")
    service.persist_completed("snap-2",1,report("snap-2","DB",plan="INSUFFICIENT_PRIVILEGES"))
    second=service.audit_detail("snap-2")["capability_snapshot"]
    assert first["snapshot_id"]!=second["snapshot_id"]
    assert first["snapshot"]["capabilities"]["SQL_PLAN_VISIBILITY"]=="AVAILABLE"
    assert second["snapshot"]["capabilities"]["SQL_PLAN_VISIBILITY"]=="INSUFFICIENT_PRIVILEGES"
    assert service.findings._rows("SELECT COUNT(*) AS n FROM capability_snapshots")[0]["n"]==2


def test_unknown_privilege_discovery_is_not_reported_as_insufficient_privileges():
    rule=RuleDefinition(rule_id="priv",name="privilege gate",required_privileges=("SELECT_CATALOG_ROLE",))
    snapshot={"capabilities":{},"available_privileges":[],"privilege_discovery_status":"UNKNOWN"}
    assert rule_capability_skip_reason(rule,snapshot)=="CAPABILITY_UNKNOWN_PRIVILEGE_DISCOVERY"
    snapshot["privilege_discovery_status"]="AVAILABLE"
    assert rule_capability_skip_reason(rule,snapshot)=="INSUFFICIENT_PRIVILEGES:SELECT_CATALOG_ROLE"


def test_scheduled_identity_is_stable_for_the_same_reference():
    first=AuditEvidenceService.scheduled_identity(12,"2026-10-01T09:00:00Z")
    assert first==AuditEvidenceService.scheduled_identity(12,"2026-10-01T09:00:00Z")
    assert first!=AuditEvidenceService.scheduled_identity(12,"2026-10-08T09:00:00Z")


class _ProbeCursor:
    def __init__(self, connection): self.connection=connection
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,params=None):
        self.connection.queries.append(sql)
        if "v$lock" in sql.lower(): raise RuntimeError("ORA-01031: insufficient privileges")
        if "session_privs" in sql.lower(): self.rows=[("SELECT ANY DICTIONARY",)]
        else: self.rows=[]
    def fetchall(self): return self.rows


class _ProbeConnection:
    version="19.22"
    call_timeout=None
    def __init__(self): self.queries=[]
    def cursor(self): return _ProbeCursor(self)


def test_capability_discovery_is_read_only_bounded_and_license_gated():
    dbm=Mock(); dbm.connection=_ProbeConnection(); dbm.connect.return_value=True
    snapshot=discover_oracle_capabilities(dbm,"DWH",required_privileges=("SELECT ANY DICTIONARY",),license_flags={"awr_license":False,"ash_license":False})
    assert snapshot["engine_version"]=="19.22"
    assert snapshot["capabilities"]["BASE_DICTIONARY"]=="AVAILABLE"
    assert snapshot["capabilities"]["LOCK_VISIBILITY"]=="INSUFFICIENT_PRIVILEGES"
    assert snapshot["available_privileges"]==["SELECT ANY DICTIONARY"]
    assert snapshot["capabilities"]["AWR_ALLOWED"]=="NOT_LICENSED"
    assert not any("awr" in sql.lower() or "ash" in sql.lower() for sql in dbm.connection.queries)
    assert all(sql.lstrip().lower().startswith("select") for sql in dbm.connection.queries)
    assert any("session_privs" in sql.lower() for sql in dbm.connection.queries)
    assert any("sys_context('userenv','con_id')" in sql.lower() for sql in dbm.connection.queries)


def test_rulepack_identity_and_failure_classes_are_stable(stores):
    from src.api.audit_evidence import classify_failure, rule_pack_identity
    a=definition_from_post_crq({"check_id":"C1","title":"one","sql":"SELECT 1 FROM dual"})
    b=definition_from_post_crq({"check_id":"C1","title":"one","sql":"SELECT 1 FROM dual"})
    c=definition_from_post_crq({"check_id":"C1","title":"one","sql":"SELECT 2 FROM dual"})
    assert rule_pack_identity([a])==rule_pack_identity([b])
    assert rule_pack_identity([a])!=rule_pack_identity([c])
    assert classify_failure("ORA-12170 timeout") == "TIMEOUT"
    assert classify_failure("ORA-01031 insufficient privileges") == "INSUFFICIENT_PRIVILEGES"
    assert classify_failure("SMTP refused",stage="delivery")=="INTERNAL_ERROR"


def test_legacy_audit_rows_migrate_without_fabricating_provenance(stores):
    internal,_,findings,alerts,service,clock=stores
    findings.reconcile("LEGACY",[rule_result("LEGACY")],audit_run_id="legacy-run",observed_at=clock[0])
    AuditEvidenceService(internal,findings,alerts,runtime=service.runtime,clock=lambda:clock[0])
    row=findings._rows("SELECT trigger_type,rule_pack_identity,reconciliation_state FROM audit_runs WHERE audit_run_id='legacy-run'")[0]
    assert row["trigger_type"]=="LEGACY"
    assert row["rule_pack_identity"]=="UNKNOWN"
    assert row["reconciliation_state"]=="RECONCILED"
