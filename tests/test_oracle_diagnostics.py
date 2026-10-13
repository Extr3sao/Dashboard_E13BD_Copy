from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from src.api.alerting_engine import AlertingService
from src.api.audit_evidence import AuditEvidenceService
from src.api.audit_evidence import discover_oracle_capabilities
from src.api.automation_service import AutomationService
from src.api.check_engine import RuleDefinition
from src.api.finding_engine import FindingStore
from src.api.investigation_engine import InvestigationStore
from src.api.oracle_diagnostics import rule_capability_skip_reason,run_oracle_diagnostics
from src.api.cpd_operations import OperationsConfig,OperationsRuntime
from src.core.automation_store import AutomationStore
from src.core.internal_db import InternalDBManager


class ProbeCursor:
    def __init__(self, connection):
        self.connection=connection; self.rows=[]
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,params=None):
        query=" ".join(str(sql).lower().split()); self.connection.probes.append(query)
        if self.connection.deny_lock and ("from v$lock where 1=0" in query or "from gv$lock where 1=0" in query):
            raise RuntimeError("ORA-01031: insufficient privileges")
        if "session_privs" in query: self.rows=[("SELECT ANY DICTIONARY",)]
        elif "select cdb from v$database" in query: self.rows=[("YES",)]
        elif "sys_context('userenv','con_id')" in query: self.rows=[(5,)]
        elif "count(distinct inst_id)" in query: self.rows=[(2,)]
        else: self.rows=[]
    def fetchall(self): return self.rows


class ProbeConnection:
    version="19.22"
    def __init__(self,deny_lock=False):
        self.call_timeout=300_000; self.probes=[]; self.deny_lock=deny_lock
    def cursor(self): return ProbeCursor(self)


class FixtureOracle:
    """Deterministic fixture for the SQL shapes; it never opens an Oracle socket."""
    def __init__(self,config=None,*,deny_lock=False,fail_sql_stats=None,sql_plan=123,sql_elapsed=150_000_000,free_bytes=50,segment_bytes=2_000_000_000):
        self.config=config or {"USER":"FIXTURE","PASSWORD":"secret","DSN":"fixture"}
        self.connection=ProbeConnection(deny_lock=deny_lock); self.last_error=None
        self.sql_plan=sql_plan; self.sql_elapsed=sql_elapsed; self.free_bytes=free_bytes; self.segment_bytes=segment_bytes; self.fail_sql_stats=fail_sql_stats
        self.queries=[]; self.closed=False
        self.now=datetime.now()
        self.sessions=[
            (1,5,128,900,"APP","INACTIVE",700,None,"SQLROOT","Application","TX open",0,None,None,"NO","fixture.module","2026-04-01 10:00:00",900,4),
            (1,5,205,901,"APP","ACTIVE",400,"SQLA","SQLA","Application","enq: TX - row lock contention",60,1,128,"VALID","fixture.module",None,None,None),
            (2,5,244,902,"APP","ACTIVE",350,"SQLA","SQLA","Application","enq: TX - row lock contention",50,1,128,"VALID","fixture.module",None,None,None),
            (2,5,301,903,"APP","ACTIVE",300,"SQLA","SQLA","Application","enq: TX - row lock contention",40,2,244,"VALID","fixture.module",None,None,None),
        ]
        self.session_columns=["inst_id","con_id","sid","serial_num","username","status","last_call_et","sql_id","prev_sql_id","wait_class","event","seconds_in_wait","blocking_instance","blocking_session","blocking_session_status","module","transaction_start","undo_blocks","undo_records"]
        self.lock_rows=[(1,128,5,1,205,5,"TX",60),(1,128,5,2,244,5,"TX",50),(2,244,5,2,301,5,"TX",40)]
        self.sql_rows=[(1,5,"SQLA",sql_plan,1,10,sql_elapsed,60_000_000,100_000,100,400,20,self.now)]
        self.sql_columns=["inst_id","con_id","sql_id","plan_hash_value","plan_variant_count","executions","elapsed_microseconds","cpu_microseconds","buffer_gets","disk_reads","rows_processed","parse_calls","last_active_time"]
        self.plan_rows=[(1,5,"SQLA",sql_plan,0,None,"SELECT STATEMENT","",None,None,"",1,10),(1,5,"SQLA",sql_plan,1,0,"TABLE ACCESS","FULL","APP","ORDERS","TABLE",1000,10)]
        self.plan_columns=["inst_id","con_id","sql_id","plan_hash_value","id","parent_id","operation","options","object_owner","object_name","object_type","cardinality","cost"]
        self.stats_rows=[(1,5,"SQLA","APP","ORDERS","TABLE",None,self.now-timedelta(days=12),"YES",10000,500,1000)]
        self.stats_columns=["inst_id","con_id","sql_id","object_owner","object_name","object_type","partition_name","last_analyzed","stale_stats","num_rows","blocks","sample_size"]
        self.segment_rows=[("APP","ORDERS",None,"TABLE","APP_DATA",segment_bytes)]
        self.segment_columns=["owner","segment_name","partition_name","segment_type","tablespace_name","segment_bytes"]
        self.space_rows=[(5,"APP_DATA","PERMANENT",1000,2000,free_bytes,1,1)]
        self.space_columns=["con_id","tablespace_name","contents","allocated_bytes","max_bytes","free_bytes","file_count","autoextend_files"]
        self.temp_rows=[(5,"TEMP",1000,1500,100,900,90,60,900,1,1)]
        self.temp_columns=["con_id","tablespace_name","allocated_bytes","max_bytes","free_bytes","used_bytes","used_percent","max_capacity_percent","allocated_space","file_count","autoextend_files"]

    def connect(self): return True
    def close(self): self.closed=True
    def execute_query(self,sql,params=None):
        query=" ".join(str(sql).lower().split()); self.queries.append((query,dict(params or {})))
        assert query.startswith("select"), f"diagnostic attempted non-SELECT statement: {query[:80]}"
        assert not any(token in query for token in ("dba_hist", "wrh$", "v$active_session_history", "dbms_workload_repository")), query
        if self.connection.deny_lock and "join gv$lock l" in query: self.last_error="ORA-01031: insufficient privileges"; return None,None
        if self.fail_sql_stats and any(view in query for view in ("from gv$sqlstats","from v$sqlstats","from gv$sql ","from v$sql ")):
            self.last_error=self.fail_sql_stats; return None,None
        if "join gv$lock l" in query: return self.lock_rows,["blocking_instance","blocking_session","blocking_con_id","blocked_instance","blocked_session","blocked_con_id","lock_type","lock_wait_seconds"]
        if "join v$lock l" in query: return [(1,128,None,1,205,None,"TX",60)],["blocking_instance","blocking_session","blocking_con_id","blocked_instance","blocked_session","blocked_con_id","lock_type","lock_wait_seconds"]
        if "from gv$session s" in query: return self.sessions,self.session_columns
        if "from v$session s" in query: return [row[1:] for row in self.sessions],["con_id",*self.session_columns[2:]]
        if "dba_tab_statistics" in query: return self.stats_rows,self.stats_columns
        if "dba_temp_free_space" in query: return self.temp_rows,self.temp_columns
        if "dba_tablespaces" in query: return self.space_rows,self.space_columns
        if "dba_segments" in query: return self.segment_rows,self.segment_columns
        if "gv$sql_plan" in query: return self.plan_rows,self.plan_columns
        if "gv$sqlstats" in query: return self.sql_rows,self.sql_columns
        if "v$sqlstats" in query: return [(row[1],*row[2:]) for row in self.sql_rows],["con_id",*self.sql_columns[2:]]
        raise AssertionError(f"unexpected diagnostic query shape: {query}")


class UnreachableOracle(FixtureOracle):
    def __init__(self):
        super().__init__(); self.connection=None; self.last_error="ORA-12541: TNS no listener"
    def connect(self): return False


@pytest.fixture
def stores(tmp_path):
    internal=InternalDBManager(str(tmp_path/"internal.db")); automation=AutomationStore(str(tmp_path/"automation.db"))
    findings=FindingStore(internal); alerts=AlertingService(findings); investigations=InvestigationStore(findings,auto_open=True)
    findings.investigation_service=investigations
    evidence=AuditEvidenceService(internal,findings,alerts,runtime={"application":"E13DB","application_version":"fixture","git_sha":"fixture-sha","schema_version":"test"})
    return internal,automation,findings,alerts,investigations,evidence


def run(db,profile="DWH-TEST",*,audit_id="diag-manual",service=None,trigger="MANUAL",options=None):
    context={"audit_run_id":audit_id,"trigger_type":trigger,"trigger_reference":"fixture"}
    return run_oracle_diagnostics(db,profile,audit_context=context,options=options,evidence_service=service)


def persist(service,report,*,attempt=1,target_context=None):
    service.begin(report["audit_run_id"],report["context"]["profile"],trigger_type=report["trigger_type"],trigger_reference=report["trigger_reference"],target_context=target_context)
    service.persist_completed(report["audit_run_id"],attempt,report,target_context=target_context)
    return service.reconcile(report["audit_run_id"])


def test_diagnostic_queries_are_bounded_read_only_and_cover_oracle_domains():
    db=FixtureOracle()
    report=run(db)
    results={item["rule_id"]:item for item in report["rule_results"]}
    assert {"ORACLE_SESSIONS","ORACLE_BLOCKING","ORACLE_SQL_PERFORMANCE","ORACLE_PLAN_CHANGES","ORACLE_PLAN_DETAILS","ORACLE_OBJECT_STATISTICS","ORACLE_SEGMENT_GROWTH","ORACLE_CAPACITY","ORACLE_TEMP_CAPACITY"}.issubset(results)
    assert results["ORACLE_BLOCKING"]["status"]=="FAIL"
    assert results["ORACLE_SQL_PERFORMANCE"]["status"]=="WARN"
    assert results["ORACLE_OBJECT_STATISTICS"]["status"]=="WARN"
    assert results["ORACLE_CAPACITY"]["status"]=="FAIL"
    assert results["ORACLE_TEMP_CAPACITY"]["status"]=="WARN"
    blocker=next(item for item in report["finding_envelopes"] if item["check_id"]=="ORACLE_BLOCKING")
    assert "inst=1:con=5:sid=128:serial=900"==blocker["object_name"]
    assert len(blocker["evidence"]["chain"])==3
    assert report["capability_snapshot"]["rac_instance_count"]==2
    assert report["capability_snapshot"]["cdb_mode"]=="CDB"
    assert report["summary"]["query_count"]<=report["summary"]["query_budget"]
    assert len(report["diagnostic_observations"])<=500
    assert report["summary"]["capability_probe_count"]>report["summary"]["query_count"]
    assert all(query.startswith("select") for query,_ in db.queries)
    assert db.connection.call_timeout==300_000
    all_serialized=json.dumps(report,default=str).lower()
    assert "select * from app" not in all_serialized
    assert "literal_value" not in all_serialized
    assert not any(any(marker in query for marker in ("dba_hist","wrh$","v$active_session_history")) for query in db.connection.probes)
    changed=run(FixtureOracle(),audit_id="different-thresholds",options={"tablespace_warning_percent":85})
    assert changed["rule_pack_identity"]!=report["rule_pack_identity"]


def test_authoritative_diagnostics_persist_findings_investigations_and_plan_history(stores):
    _,_,findings,alerts,investigations,evidence=stores
    db=FixtureOracle()
    context={"environment":"production","criticality":"critical"}
    first=run(db,audit_id="diag-1",service=evidence)
    persist(evidence,first,target_context=context)
    first_plan=next(item for item in first["diagnostic_observations"] if item["category"]=="PLAN")
    second_db=FixtureOracle(sql_plan=789,sql_elapsed=300_000_000,free_bytes=30,segment_bytes=2_400_000_000)
    second=run(second_db,audit_id="diag-2",service=evidence)
    changed=next(item for item in second["finding_envelopes"] if item["check_id"]=="ORACLE_PLAN_CHANGES")
    assert changed["evidence"]["previous_plan_hash"]==123
    assert changed["evidence"]["plan_hash"]==789
    assert changed["evidence"]["plan_steps"]
    assert any(item["check_id"]=="ORACLE_SEGMENT_GROWTH" for item in second["finding_envelopes"])
    sql_finding=next(item for item in findings.list_findings(database="DWH-TEST") if item["rule_id"]=="ORACLE_SQL_PERFORMANCE")
    assert sql_finding["delta"]!="WORSENING"  # no new executions: cumulative change is not a comparable regression
    sql_observation=next(item for item in second["diagnostic_observations"] if item["category"]=="SQL_PERFORMANCE")
    assert sql_observation["evidence"]["comparison_status"]=="NOT_COMPARABLE_COUNTER_RESET_OR_NO_NEW_EXECUTIONS"
    persist(evidence,second,target_context=context)
    assert findings.list_findings(database="DWH-TEST")
    assert findings.list_red_flags(database_id="DWH-TEST")
    assert alerts.list_alerts(database="DWH-TEST")
    fleet=findings.fleet()
    assert any(item["database_id"]=="DWH-TEST" and item["health_status"]=="CRITICAL" for item in fleet["targets"])
    assert any(item["database_id"]=="DWH-TEST" and item["priority"]=="P1" for item in fleet["needs_attention"])
    cases=investigations.list(database_id="DWH-TEST",limit=100)["items"]
    assert cases
    all_facts=[fact for case in cases for fact in investigations.evidence(case["id"])]
    assert any(item["category"]=="LOCKING" for item in all_facts)
    assert any(item["category"]=="PERFORMANCE" for item in all_facts)
    all_hypotheses=[hypothesis for case in cases for hypothesis in investigations.hypotheses(case["id"])]
    assert any(item["hypothesis_type"]=="PLAN_CHANGE_MAY_CONTRIBUTE" for item in all_hypotheses)
    assert any("does not establish causation" in item["description"] for item in all_hypotheses)
    assert evidence.audit_detail("diag-2")["diagnostic_observations"]
    assert evidence.diagnostic_history("DWH-TEST",category="PLAN")["items"][0]["sql_id"]=="sqla"
    assert first_plan["plan_hash"]=="123"
    plan_findings=[item for item in findings.list_findings(database="DWH-TEST") if item["rule_id"]=="ORACLE_PLAN_CHANGES"]
    assert plan_findings
    assert "select *" not in json.dumps([item["evidence"] for item in findings.list_findings(database="DWH-TEST")]).lower()


def test_privilege_loss_skips_blocking_and_never_resolves_existing_finding(stores):
    _,_,findings,_,_,evidence=stores
    first=run(FixtureOracle(),audit_id="lock-visible",service=evidence)
    persist(evidence,first)
    prior=next(item for item in findings.list_findings(database="DWH-TEST") if item["rule_id"]=="ORACLE_BLOCKING")
    limited=run(FixtureOracle(deny_lock=True),audit_id="lock-revoked",service=evidence,trigger="SCHEDULED")
    result=next(item for item in limited["rule_results"] if item["rule_id"]=="ORACLE_BLOCKING")
    assert result["status"]=="SKIPPED"
    assert limited["capability_snapshot"]["capabilities"]["LOCK_VISIBILITY"]=="INSUFFICIENT_PRIVILEGES"
    persist(evidence,limited)
    assert findings.get_finding(prior["id"])["status"]!="RESOLVED"
    assert evidence.audit_detail("lock-revoked")["coverage_state"] in {"DEGRADED","PARTIAL"}


def test_runtime_dictionary_error_is_typed_and_preserves_sql_findings(stores):
    _,_,findings,_,_,evidence=stores
    healthy=run(FixtureOracle(),audit_id="sql-visible",service=evidence)
    persist(evidence,healthy)
    prior=next(item for item in findings.list_findings(database="DWH-TEST") if item["rule_id"]=="ORACLE_SQL_PERFORMANCE")
    limited=run(FixtureOracle(fail_sql_stats="ORA-01031: insufficient privileges"),audit_id="sql-revoked",service=evidence,trigger="SCHEDULED")
    result=next(item for item in limited["rule_results"] if item["rule_id"]=="ORACLE_SQL_PERFORMANCE")
    assert result["status"]=="SKIPPED"
    assert limited["capability_snapshot"]["capabilities"]["GV_SQL_STATS_VISIBILITY"]=="INSUFFICIENT_PRIVILEGES"
    persist(evidence,limited)
    assert findings.get_finding(prior["id"])["status"]!="RESOLVED"


def test_query_timeout_is_isolated_and_does_not_hide_other_diagnostics():
    report=run(FixtureOracle(fail_sql_stats="ORA-01013: user requested cancel"),audit_id="diag-timeout")
    sql_result=next(item for item in report["rule_results"] if item["rule_id"]=="ORACLE_SQL_PERFORMANCE")
    assert sql_result["status"]=="ERROR"
    assert sql_result["error"]=="ORACLE_QUERY_TIMEOUT"
    assert any(item["rule_id"]=="ORACLE_CAPACITY" and item["status"]=="FAIL" for item in report["rule_results"])
    assert report["coverage_state"]=="DEGRADED"


def test_unreachable_target_is_failed_not_false_success_and_retains_findings(stores):
    _,_,findings,_,_,evidence=stores
    healthy=run(FixtureOracle(),audit_id="diag-before-disconnect",service=evidence)
    persist(evidence,healthy)
    prior=next(item for item in findings.list_findings(database="DWH-TEST") if item["rule_id"]=="ORACLE_BLOCKING")
    failed=run(UnreachableOracle(),audit_id="diag-unreachable",service=evidence,trigger="SCHEDULED")
    assert failed["audit_state"]=="FAILED"
    assert failed["capability_snapshot"]["connection_class"]=="UNREACHABLE"
    assert all(item["status"]=="SKIPPED" for item in failed["rule_results"])
    persist(evidence,failed)
    detail=evidence.audit_detail("diag-unreachable")
    assert detail["state"]=="FAILED"
    assert detail["failure_class"]=="UNREACHABLE"
    assert findings.get_finding(prior["id"])["status"]!="RESOLVED"
    assert findings.fleet()["targets"]
    history=evidence.diagnostic_history("DWH-TEST")
    assert history["items"] and all(item["audit_run_id"]=="diag-before-disconnect" for item in history["items"])
    assert history["latest_audit"]["audit_run_id"]=="diag-unreachable"
    assert history["latest_audit"]["state"]=="FAILED"
    assert history["latest_audit"]["capability_snapshot"]["snapshot"]["connection_class"]=="UNREACHABLE"


def test_tablespace_capacity_finding_lifecycle_tracks_warning_critical_and_recovery(stores):
    _,_,findings,_,_,evidence=stores
    for audit_id,free in (("cap-normal",300),("cap-warning",150),("cap-critical",50),("cap-recovered",300)):
        report=run(FixtureOracle(free_bytes=free),audit_id=audit_id,service=evidence)
        persist(evidence,report)
        rows=[item for item in findings.list_findings(database="DWH-TEST",resolved=None) if item["rule_id"]=="ORACLE_CAPACITY" and item["object_name"]=="APP_DATA@CON5"]
        if audit_id=="cap-normal": assert not rows
        elif audit_id=="cap-warning": assert rows and rows[0]["status"]!="RESOLVED" and rows[0]["severity"]=="MEDIUM"
        elif audit_id=="cap-critical": assert rows and rows[0]["severity"]=="CRITICAL"
        else: assert rows and rows[0]["status"]=="RESOLVED"


def test_retention_protects_diagnostic_evidence_referenced_by_active_investigation(stores,tmp_path):
    internal,automation,findings,alerts,investigations,evidence=stores
    report=run(FixtureOracle(),audit_id="retained-diagnostic",service=evidence)
    persist(evidence,report,target_context={"environment":"production","criticality":"critical"})
    critical=next(item for item in findings.list_findings(database="DWH-TEST") if item["rule_id"]=="ORACLE_BLOCKING")
    case=investigations.open(critical["id"],actor="test",source="acceptance")
    old=time.time()-800*86400
    with internal._get_connection() as conn:
        conn.execute("UPDATE audit_runs SET completed_at=?,started_at=? WHERE audit_run_id=?",(old,old,"retained-diagnostic"))
        conn.execute("UPDATE oracle_diagnostic_observations SET observed_at=? WHERE audit_run_id=?",(old,"retained-diagnostic"))
    config=OperationsConfig({"E13DB_BACKUP_PATH":str(tmp_path/"backups"),"E13DB_RETENTION_AUDIT_HISTORY_DAYS":"1"})
    scheduler=AutomationService(automation,Mock(),reports_dir=str(tmp_path/"reports"))
    operations=OperationsRuntime(internal,automation,scheduler,alerts,config)
    operations.migrate()
    preview=operations.retention()
    assert preview["eligible_records"]["audit_runs"]==0
    assert preview["eligible_records"]["oracle_diagnostic_observations"]==0
    assert evidence.audit_detail("retained-diagnostic")["diagnostic_observations"]
    assert investigations.get(case["id"])["facts"]


def test_aw_policy_requires_both_explicit_acknowledgements_and_never_queries_views(monkeypatch):
    monkeypatch.setenv("E13DB_ORACLE_AWR_LICENSED","true"); monkeypatch.setenv("E13DB_ORACLE_AWR_PRIVILEGE","true")
    monkeypatch.setenv("E13DB_ORACLE_ASH_LICENSED","true"); monkeypatch.setenv("E13DB_ORACLE_ASH_PRIVILEGE","true")
    db=FixtureOracle(); result=run(db)
    query_text="\n".join(query for query,_ in db.queries)
    probe_text="\n".join(db.connection.probes)
    assert "dba_hist" not in query_text.lower()+probe_text.lower()
    assert "wrh$" not in query_text.lower()+probe_text.lower()
    assert "v$active_session_history" not in query_text.lower()+probe_text.lower()
    assert result["capability_snapshot"]["capabilities"]["AWR_ALLOWED"]=="AVAILABLE"
    assert "not probed or queried" in result["capability_snapshot"]["license_gates"]["disclosure"].lower()


def test_capability_discovery_distinguishes_configuration_and_unsupported_multitenant():
    no_config=Mock(); no_config.config={}; no_config.connection=None; no_config.connect.return_value=False
    unavailable=discover_oracle_capabilities(no_config,"DB")
    assert unavailable["connection_class"]=="CONFIGURATION_ERROR"
    assert unavailable["capabilities"]["SESSION_VISIBILITY"]=="UNAVAILABLE"
    old=FixtureOracle(); old.connection.version="11.2.0.4"
    unsupported=discover_oracle_capabilities(old,"DB")
    assert unsupported["capabilities"]["CDB_VISIBILITY"]=="UNSUPPORTED_VERSION"
    assert unsupported["cdb_mode"]=="PRE_12C_NON_CDB"


def test_awr_rule_requires_both_license_and_privilege_attestations():
    rule=RuleDefinition(rule_id="AWRAWARE",name="AWR aware",license_requirements=("awr",))
    snapshot={"capabilities":{"AWR_ALLOWED":"INSUFFICIENT_PRIVILEGES"}}
    assert rule_capability_skip_reason(rule,snapshot,{"awr_license":True,"awr_privilege":False})=="INSUFFICIENT_PRIVILEGES:AWR"
    snapshot["capabilities"]["AWR_ALLOWED"]="AVAILABLE"
    assert not rule_capability_skip_reason(rule,snapshot,{"awr_license":True,"awr_privilege":True})


def test_real_scheduler_tick_reconciles_and_replays_diagnostic_run(stores,tmp_path):
    _,automation,findings,alerts,_,evidence=stores
    job=automation.create_job({"name":"oracle diagnostic soak","enabled":True,"audit_type":"oracle_diagnostics","profile":"DWH-TEST","schedule_type":"daily","schedule_config":{"start_at":"2020-01-01T09:00"},"next_run_at":"2020-01-01T09:00:00Z","job_config":{"diagnostic_options":{"tablespace_warning_percent":80,"tablespace_critical_percent":95},"target_context":{"environment":"production","criticality":"critical"}},"report_format":"markdown","delivery_targets":[],"severity_rules":[]})
    scheduled_reference=job["next_run_at"]
    loader=Mock(); loader.get_env_var.return_value=""
    service=AutomationService(automation,loader,reports_dir=str(tmp_path/"reports")); service.audit_evidence_service=evidence
    with patch.object(service,"_resolve_profile_config",return_value={"PROFILE_NAME":"DWH-TEST","CALL_TIMEOUT_MS":300000}),patch("src.api.automation_service.OracleDBManager",FixtureOracle),patch.object(service,"_deliver_targets",return_value=[]),patch.object(service,"_apply_rules",return_value=[]):
        service.tick()
        deadline=time.monotonic()+10
        runs=[]
        while time.monotonic()<deadline:
            runs=automation.list_runs(job["id"])
            if runs and runs[0]["status"]!="running": break
            time.sleep(0.02)
        assert len(runs)==1 and runs[0]["status"]=="success"
        first=runs[0]
        second=service.execute_job(job["id"],manual=False,scheduled_reference=scheduled_reference)
        service.stop(grace_seconds=1)
        runs=automation.list_runs(job["id"])
        assert len(runs)>=2 and second["status"]=="success"
    assert first["audit_run_id"]==second["audit_run_id"]
    assert second["summary"]["replayed"] is True
    assert first["status"]=="success"
    persisted=evidence.audit_detail(first["audit_run_id"])
    assert persisted["execution_options"]["tablespace_warning_percent"]==80
    assert persisted["target_context"]["environment"]=="production"
    assert persisted["diagnostic_summary"]["query_count"]<=persisted["diagnostic_summary"]["query_budget"]
    assert findings.list_findings(database="DWH-TEST")
    assert all(item["audit_run_id"]==first["audit_run_id"] for item in automation.list_runs(job["id"]))
    assert len(findings.list_findings(database="DWH-TEST"))==len({item["fingerprint"] for item in findings.list_findings(database="DWH-TEST")})


def test_manual_diagnostics_api_uses_durable_pipeline_and_replay(stores,monkeypatch):
    import asyncio
    from src.api import main
    _,_,findings,_,_,evidence=stores
    monkeypatch.setattr(main,"audit_evidence_service",evidence)
    async def with_profile(_stage,profile,operation): return await operation(profile,FixtureOracle())
    monkeypatch.setattr(main,"_run_with_oracle_profile",with_profile)
    payload={"profile":"DWH-TEST","audit_run_id":"manual-oracle-diag-1","diagnostic_options":{"tablespace_warning_percent":80}}
    first=asyncio.run(main.run_oracle_diagnostics_api(payload))
    replay=asyncio.run(main.run_oracle_diagnostics_api(payload))
    assert first["audit_run_id"]==replay["audit_run_id"]==payload["audit_run_id"]
    assert first["reconciliation_state"]=="RECONCILED"
    assert replay["audit_type"]=="oracle_diagnostics" and replay["replayed"] is True
    assert replay["diagnostic_observations"]
    assert len(findings.list_findings(database="DWH-TEST"))==len({item["fingerprint"] for item in findings.list_findings(database="DWH-TEST")})


def test_scheduler_payload_normalizes_diagnostic_thresholds(monkeypatch):
    from src.api import main
    monkeypatch.setattr(main.config_loader,"load_connections",lambda:{"DWH-TEST":{"USER":"u","PASSWORD":"p","DSN":"fixture"}})
    monkeypatch.setattr(main,"_resolve_profile_key",lambda profile,profiles:"DWH-TEST")
    normalized=main._normalize_automation_job_payload({"name":"oracle diag","audit_type":"oracle_diagnostics","profile":"DWH-TEST","schedule_type":"daily","schedule_config":{"start_at":"2026-10-13T09:00"},"report_format":"pdf","diagnostic_options":{"tablespace_warning_percent":84,"tablespace_critical_percent":80,"query_timeout_ms":1}})
    options=normalized["job_config"]["diagnostic_options"]
    assert normalized["audit_type"]=="oracle_diagnostics"
    assert normalized["report_format"]=="markdown"
    assert options["tablespace_warning_percent"]==80
    assert options["tablespace_critical_percent"]==95
    assert options["query_timeout_ms"]==250


def test_crash_after_diagnostic_projection_recovers_without_duplicate_facts(stores,monkeypatch):
    internal,_,findings,alerts,_,evidence=stores
    report=run(FixtureOracle(),audit_id="diag-crash-recovery",service=evidence,trigger="SCHEDULED")
    evidence.begin(report["audit_run_id"],"DWH-TEST",trigger_type="SCHEDULED",trigger_reference="scheduled:fixture")
    evidence.persist_completed(report["audit_run_id"],1,report)
    original=findings.reconcile_post_crq
    crashes=[True]
    def fail_after_projection(*args,**kwargs):
        result=original(*args,**kwargs)
        if crashes[0]: crashes[0]=False; raise RuntimeError("simulated process loss after projection commit")
        return result
    monkeypatch.setattr(findings,"reconcile_post_crq",fail_after_projection)
    with pytest.raises(Exception,match="audit_reconciliation_failed"):
        evidence.reconcile(report["audit_run_id"])
    before=findings._rows("SELECT COUNT(*) AS n FROM oracle_diagnostic_observations WHERE audit_run_id=?",(report["audit_run_id"],))[0]["n"]
    monkeypatch.setattr(findings,"reconcile_post_crq",original)
    restarted=AuditEvidenceService(internal,findings,alerts,runtime=evidence.runtime)
    recovered=restarted.recover_pending_reconciliations()
    after=findings._rows("SELECT COUNT(*) AS n FROM oracle_diagnostic_observations WHERE audit_run_id=?",(report["audit_run_id"],))[0]["n"]
    assert recovered[0]["reconciliation_state"]=="RECONCILED"
    assert before==after==len(report["diagnostic_observations"])
    assert all(item["occurrences"]==1 for item in findings.list_findings(database="DWH-TEST"))
