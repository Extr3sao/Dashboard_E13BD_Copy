import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.finding_engine import FindingStore
from src.api.investigation_engine import InvestigationStore, MAX_CORRELATION_CANDIDATES, classify_evidence
from src.api.investigations_router import create_investigations_router
from src.api.security import SessionStore
from src.core.internal_db import InternalDBManager


@pytest.fixture
def stores(tmp_path):
    findings = FindingStore(InternalDBManager(str(tmp_path / "internal.db")))
    clock = [100000.0]
    investigations = InvestigationStore(findings, clock=lambda: clock[0], capabilities={"oracle": True, "awr_license": False, "awr_privilege": False, "ash_license": False, "ash_privilege": False})
    findings.investigation_service = investigations
    return findings, investigations, clock


def result(rule, *, value=1, summary=None, evidence=None, severity="CRITICAL", owner="APP", object_name="ORDERS", status="FAIL"):
    return {"rule_id": rule, "status": status, "severity": severity, "summary": summary or rule.replace("_", " "), "owner": owner, "object_name": object_name, "object_type": "TABLE", "metrics": {"value": value, "comparison_direction": "higher_is_worse"}, "evidence": evidence or {}}


def seed_incident(findings, *, start=100000, second=100600):
    findings.set_target_context("DWH-TEST", environment="production", criticality="critical")
    baseline = [
        result("SQL_ELAPSED", value=2.1, summary="SQL execution duration baseline", evidence={"elapsed_seconds": 2.1, "unit": "s", "sql_id": "SQL-A"}),
        result("SQL_PLAN", severity="MEDIUM", value=1, summary="Execution plan observation", evidence={"plan_hash": "111", "sql_id": "SQL-A"}),
        result("TABLE_STATS", severity="MEDIUM", value=1, summary="Object statistics last_analyzed age observed", evidence={"statistics_age_days": 2, "last_analyzed": "2026-01-01", "stale": False}),
        result("BLOCKING_CHAIN", severity="MEDIUM", value=1, summary="Blocking session observed", evidence={"blocking_session": "42", "blocked_session": "77", "wait_seconds": 14}),
    ]
    findings.reconcile("DWH-TEST", baseline, audit_run_id="incident-1", target_context={"environment": "production", "criticality": "critical"}, observed_at=start)
    changed = [
        result("SQL_ELAPSED", value=11.4, summary="SQL execution duration increased", evidence={"elapsed_seconds": 11.4, "unit": "s", "sql_id": "SQL-A"}),
        result("SQL_PLAN", severity="MEDIUM", value=2, summary="Execution plan changed", evidence={"plan_hash": "222", "sql_id": "SQL-A"}),
        result("TABLE_STATS", severity="MEDIUM", value=2, summary="Statistics stale for affected table", evidence={"statistics_age_days": 20, "last_analyzed": "2025-12-01", "stale": True}),
        result("BLOCKING_CHAIN", severity="MEDIUM", value=2, summary="Blocking session blocks query", evidence={"blocking_session": "42", "blocked_session": "77", "wait_seconds": 90}),
    ]
    findings.reconcile("DWH-TEST", changed, audit_run_id="incident-2", observed_at=second)
    finding = next(item for item in findings.list_findings(database="DWH-TEST") if item["rule_id"] == "SQL_ELAPSED")
    return finding


def test_automatic_investigation_correlates_incident_with_explanations_and_contradictions(stores):
    findings, cases, _ = stores
    primary = seed_incident(findings)
    listed = cases.list(database_id="DWH-TEST")
    case = next(item for item in listed["items"] if item["primary_finding_id"] == primary["id"])
    detail = cases.get(case["id"])
    assert case["source"] == "automatic"
    assert primary["delta"] == "WORSENING"
    categories = {fact["category"] for fact in detail["facts"]}
    assert {"PERFORMANCE", "EXECUTION_PLAN", "STATISTICS", "LOCKING"} <= categories
    hypothesis_types = {item["hypothesis_type"] for item in detail["hypotheses"]}
    assert {"PLAN_CHANGE_MAY_CONTRIBUTE", "STATISTICS_MAY_CONTRIBUTE", "BLOCKING_MAY_CONTRIBUTE"} <= hypothesis_types
    stats = next(item for item in detail["hypotheses"] if item["hypothesis_type"] == "STATISTICS_MAY_CONTRIBUTE")
    assert stats["status"] == "WEAKENED"
    assert stats["contradicting_evidence"]
    assert "does not establish causation" in next(item for item in detail["hypotheses"] if item["hypothesis_type"] == "PLAN_CHANGE_MAY_CONTRIBUTE")["description"]
    assert any(item["strength"] == "DIRECT" and "same schema and object" in item["reasons"] for item in detail["correlations"])
    assert detail["recommended_checks"]
    assert any("blocking_session" in item for item in cases.lock_chain(case["id"]))
    assert [item["type"] for item in detail["timeline"]].count("FACT") >= 8


def test_manual_open_status_check_cause_resolution_and_recurrence(stores):
    findings, cases, clock = stores
    findings.reconcile("DEV", [result("LOW_RULE", severity="MEDIUM", summary="Manual investigation target")], audit_run_id="manual-1", observed_at=clock[0])
    finding = findings.list_findings(database="DEV")[0]
    assert cases.list(database_id="DEV")["total"] == 0
    first = cases.open_manual("DEV", finding["id"], "dba.one")
    assert first["source"] == "manual" and first["actor"] == "dba.one"
    hypothesis = cases._rows_for("SELECT id FROM investigation_hypotheses WHERE investigation_id=?", (first["id"],))
    check = cases._rows_for("SELECT id FROM investigation_checks WHERE investigation_id=?", (first["id"],))[0]
    cases.update_check(first["id"], check["id"], actor="dba.one", status="COMPLETED", result_summary="Reviewed; no issue observed")
    cases.set_status(first["id"], "MONITORING", actor="dba.one")
    cases.confirm_cause(first["id"], actor="dba.one", description="Operator verified a blocking transaction", evidence=[{"summary":"blocking confirmed","evidence_id":1}])
    resolved = cases.record_resolution(first["id"], actor="dba.one", resolution="Blocking transaction ended", actions_taken="Application owner corrected transaction handling")
    assert resolved["status"] == "RESOLVED"
    assert resolved["confirmed_cause"] == "Operator verified a blocking transaction"
    findings.reconcile("DEV", [{**result("LOW_RULE", severity="MEDIUM"), "status":"PASS"}], audit_run_id="manual-2", observed_at=clock[0]+300)
    clock[0] += 7 * 86400
    findings.reconcile("DEV", [result("LOW_RULE", severity="MEDIUM", summary="Manual incident recurred")], audit_run_id="manual-3", observed_at=clock[0])
    recurrent = cases.open(finding["id"], actor="dba.one", source="manual", at=clock[0])
    history = cases.get(recurrent["id"])["recurrence"]
    assert history and history[0]["confirmed_cause"] == "Operator verified a blocking transaction"
    assert recurrent["id"] != first["id"]


def test_manual_database_mismatch_and_invalid_status_are_rejected(stores):
    findings, cases, clock = stores
    findings.reconcile("A", [result("RULE", severity="MEDIUM")], audit_run_id="a", observed_at=clock[0])
    finding = findings.list_findings(database="A")[0]
    with pytest.raises(ValueError, match="finding_database_mismatch"):
        cases.open_manual("B", finding["id"], "operator")
    case = cases.open_manual("A", finding["id"], "operator")
    with pytest.raises(ValueError, match="invalid_investigation_status"):
        cases.set_status(case["id"], "ROOT_CAUSE", actor="operator")


def test_rule_categories_explanations_and_weak_temporal_correlation(stores):
    findings, cases, clock = stores
    assert classify_evidence("TABLESPACE_FULL", "space pressure", {}) == "CAPACITY"
    findings.reconcile("A", [result("ALPHA", severity="MEDIUM", summary="first", owner="", object_name="")], audit_run_id="alpha", observed_at=clock[0])
    alpha = findings.list_findings(database="A")[0]
    case = cases.open(alpha["id"], actor="operator")
    findings.reconcile("A", [result("BETA", severity="MEDIUM", summary="second", owner="", object_name="")], audit_run_id="beta", observed_at=clock[0]+60)
    cases.refresh(case["id"])
    related = cases.correlations(case["id"])
    assert related[0]["strength"] == "WEAK"
    assert "temporal proximity only" in related[0]["reasons"][-1]


def test_plan_hash_change_generates_fact_not_plan_regression(stores):
    findings, cases, _ = stores
    seed_incident(findings)
    plan_facts = findings._rows("SELECT * FROM investigation_evidence WHERE category='EXECUTION_PLAN'")
    assert any(item["metric_name"] == "plan_hash" and "changed" in item["summary"].lower() for item in plan_facts)
    assert not any("regression" in item["summary"].lower() for item in plan_facts)
    plans = findings._rows("SELECT * FROM investigation_plan_observations WHERE database_id='DWH-TEST' AND sql_id='SQL-A'")
    assert {item["plan_hash"] for item in plans} == {"111", "222"}


def test_capacity_projection_requires_stable_positive_samples(stores):
    findings, cases, clock = stores
    findings.set_target_context("CAP", environment="production", criticality="critical")
    findings.reconcile("CAP", [result("CAPACITY", summary="Tablespace capacity", evidence={"used_percent":70,"growth_bytes":100,"threshold_value":1000,"unit":"bytes"})], audit_run_id="cap1", observed_at=clock[0])
    primary=findings.list_findings(database="CAP")[0]
    case=cases.open(primary["id"],actor="operator")
    for index,value in enumerate((200,300,400),1):
        # One Finding identity, repeated observations form a short, stable trend.
        findings.reconcile("CAP", [result("CAPACITY", value=value, summary="Tablespace capacity growth", evidence={"used_percent":70+index,"growth_bytes":value,"threshold_value":1000,"unit":"bytes"})], audit_run_id=f"cap{index+1}", observed_at=clock[0]+index*86400)
    refreshed=cases.refresh(case["id"])
    evidence=next(item for item in refreshed["facts"] if item["metric_name"]=="growth_bytes")
    projection=cases.capacity_projection(case["id"],evidence["id"])
    assert projection["available"] and projection["sample_count"] >= 3, projection
    assert projection["type"] == "LINEAR_PROJECTION_BASED_ON_RECENT_OBSERVATIONS"
    assert "not a forecast" in projection["assumption"]


def test_capacity_projection_rejected_for_unstable_or_insufficient_data(stores):
    findings,cases,clock=stores
    findings.set_target_context("CAP",environment="production",criticality="critical")
    findings.reconcile("CAP",[result("CAPACITY",evidence={"growth_bytes":10,"threshold_value":100})],audit_run_id="cap1",observed_at=clock[0])
    case=cases.open(findings.list_findings(database="CAP")[0]["id"],actor="operator")
    evidence=next(item for item in case["facts"] if item["metric_name"]=="growth_bytes")
    assert not cases.capacity_projection(case["id"],evidence["id"])["available"]


def test_sensitive_raw_sql_binds_and_passwords_not_persisted(stores):
    findings,cases,clock=stores
    finding=result("SQL_SLOW",summary="Slow SQL password=never-store",evidence={"elapsed_seconds":7,"sql_text":"select secret data","bind_values":{"token":"never-store"},"password":"never-store","sql_id":"safe-id"})
    findings.set_target_context("A",environment="production",criticality="critical")
    findings.reconcile("A",[finding],audit_run_id="secret",observed_at=clock[0])
    case=cases.open(findings.list_findings(database="A")[0]["id"],actor="operator")
    stored=json.dumps(cases.get(case["id"]))
    assert "never-store" not in stored
    assert "select secret data" not in stored
    assert "bind_values" not in stored
    assert "elapsed_seconds" in stored


def test_license_and_privilege_gates_skip_awr_ash(stores):
    _,cases,_=stores
    gated=cases.capabilities_status()
    assert gated["awr"]["status"]=="SKIPPED" and not gated["awr"]["available"]
    assert gated["ash"]["status"]=="SKIPPED" and not gated["ash"]["available"]
    allowed=InvestigationStore(cases.findings,capabilities={"oracle":True,"awr_license":True,"awr_privilege":True,"ash_license":True,"ash_privilege":False}).capabilities_status()
    assert allowed["awr"]["available"]
    assert not allowed["ash"]["available"]


def test_realistic_dwh_incident_recovers_and_recurs_with_operator_memory(stores):
    findings,cases,clock=stores
    primary=seed_incident(findings)
    first=next(item for item in cases.list(database_id="DWH-TEST")["items"] if item["primary_finding_id"]==primary["id"])
    cases.confirm_cause(first["id"],actor="dba",description="Blocking transaction verified in the application workflow")
    recovered=[
        result("SQL_ELAPSED",value=2.0,summary="SQL returned to baseline",evidence={"elapsed_seconds":2.0,"sql_id":"SQL-A"},status="PASS"),
        result("SQL_PLAN",severity="MEDIUM",value=2,summary="Execution plan hash unchanged",evidence={"plan_hash":"222","sql_id":"SQL-A"},status="PASS"),
        result("TABLE_STATS",severity="MEDIUM",value=2,summary="Statistics reviewed",evidence={"statistics_age_days":20,"stale":False},status="PASS"),
        result("BLOCKING_CHAIN",severity="MEDIUM",value=2,summary="No blocking sessions",evidence={},status="PASS"),
    ]
    clock[0]+=900
    findings.reconcile("DWH-TEST",recovered,audit_run_id="incident-resolved",observed_at=clock[0])
    resolved=cases.get(first["id"])
    assert findings.get_finding(primary["id"])["status"]=="RESOLVED"
    assert resolved["status"]=="RESOLVED"
    cases.record_resolution(first["id"],actor="dba",resolution="Blocking transaction ended and performance returned to baseline",actions_taken="Application transaction handling corrected")
    clock[0]+=14*86400
    findings.reconcile("DWH-TEST",[result("SQL_ELAPSED",value=14,summary="SQL execution duration degraded again",evidence={"elapsed_seconds":14,"sql_id":"SQL-A"})],audit_run_id="incident-recurred",observed_at=clock[0])
    reopened=next(item for item in cases.list(database_id="DWH-TEST")["items"] if item["primary_finding_id"]==primary["id"] and item["status"]=="OPEN")
    history=cases.get(reopened["id"])["recurrence"]
    assert history and history[0]["confirmed_cause"]=="Blocking transaction verified in the application workflow"
    assert "Application transaction handling corrected" in history[0]["actions_taken"]


def test_repeated_audit_failures_open_database_instability_case(stores):
    findings,cases,clock=stores
    findings.set_target_context("ORACLE-DOWN",environment="production",criticality="high")
    findings.reconcile("ORACLE-DOWN",[],audit_run_id="failed-one",audit_state="FAILED",observed_at=clock[0])
    assert cases.list(database_id="ORACLE-DOWN")["total"]==0
    clock[0]+=60
    findings.reconcile("ORACLE-DOWN",[],audit_run_id="failed-two",audit_state="FAILED",observed_at=clock[0])
    result_set=cases.list(database_id="ORACLE-DOWN")
    assert result_set["total"]==1
    detail=cases.get(result_set["items"][0]["id"])
    assert detail["primary_finding"] is None
    assert any(fact["category"]=="CONNECTIVITY" for fact in detail["facts"])


def test_idempotent_auto_open_and_bounded_related_candidate_query(stores):
    findings,cases,clock=stores
    primary=seed_incident(findings)
    case=next(item for item in cases.list(database_id="DWH-TEST")["items"] if item["primary_finding_id"]==primary["id"])
    findings.investigation_service.on_reconcile("DWH-TEST",at=clock[0])
    assert cases.list(database_id="DWH-TEST")["total"] <= findings._rows("SELECT COUNT(*) n FROM findings")[0]["n"]
    statements=[]
    original_rows=findings._rows
    def capture_rows(sql,args=()):
        statements.append(sql)
        return original_rows(sql,args)
    findings._rows=capture_rows
    try:
        cases._correlate(case["id"],cases._rows_for("SELECT * FROM investigations WHERE id=?",(case["id"],))[0])
    finally:
        findings._rows=original_rows
    candidate_sql=[sql.lower() for sql in statements if "join finding_occurrences" in sql.lower() and "group by f.id" in sql.lower()]
    assert candidate_sql and f"limit {MAX_CORRELATION_CANDIDATES}" in candidate_sql[0]


def test_api_user_csrf_and_no_mutation_without_csrf(stores):
    findings,cases,clock=stores
    findings.reconcile("A",[result("RULE",severity="MEDIUM")],audit_run_id="api-1",observed_at=clock[0])
    finding=findings.list_findings(database="A")[0]
    app=FastAPI(); sessions=SessionStore(); app.include_router(create_investigations_router(cases,sessions,"session")); client=TestClient(app)
    assert client.get("/api/investigations").status_code==401
    token=sessions.create("operator"); client.cookies.set("session",token)
    response=client.post("/api/investigations",json={"database_id":"A","finding_id":finding["id"]})
    assert response.status_code==403
    created=client.post("/api/investigations",json={"database_id":"A","finding_id":finding["id"]},headers={"X-CSRF-Token":sessions.csrf_token(token)})
    assert created.status_code==201
    case_id=created.json()["id"]
    assert client.post(f"/api/investigations/{case_id}/cause",json={"description":"cause"}).status_code==403
    assert client.post(f"/api/investigations/{case_id}/cause",json={"description":"cause"},headers={"X-CSRF-Token":sessions.csrf_token(token)}).status_code==200
    service=sessions.create("service",role="SERVICE"); client.cookies.set("session",service)
    assert client.get("/api/investigations").status_code==401


def test_api_rejects_arbitrary_cause_fields_and_requires_resolution_text(stores):
    findings,cases,clock=stores
    findings.reconcile("A",[result("RULE",severity="MEDIUM")],audit_run_id="api-2",observed_at=clock[0])
    finding=findings.list_findings(database="A")[0]
    case=cases.open(finding["id"],actor="operator")
    with pytest.raises(ValueError,match="resolution_required"):
        cases.record_resolution(case["id"],actor="operator",resolution="")
    with pytest.raises(ValueError,match="cause_description_required"):
        cases.confirm_cause(case["id"],actor="operator",description=" ")


def test_relationship_metadata_is_persisted_and_rule_scoped(stores):
    _,cases,_=stores
    cases.declare_rule_relationship("LOCKING","PERFORMANCE","Rule APP_LOCK_CHECK can overlap rule SQL_ELAPSED",source_rule="APP_LOCK_CHECK",target_rule="SQL_ELAPSED")
    declared=next(item for item in cases.rule_relationships() if item["source_rule"]=="APP_LOCK_CHECK")
    assert declared["reason"]=="Rule APP_LOCK_CHECK can overlap rule SQL_ELAPSED"
    matched,reason=cases._relationship("LOCKING","PERFORMANCE","APP_LOCK_CHECK","SQL_ELAPSED")
    assert matched and reason==declared["reason"]
    with pytest.raises(ValueError,match="invalid_rule_relationship"):
        cases.declare_rule_relationship("FAKE_CATEGORY","PERFORMANCE","no")


def test_auto_investigation_can_be_disabled(stores):
    findings,cases,clock=stores
    cases.auto_open=False
    seed_incident(findings)
    assert cases.list(database_id="DWH-TEST")["total"]==0


def test_capacity_projection_suppressed_for_unstable_growth(stores):
    findings,cases,clock=stores
    findings.set_target_context("CAP",environment="production",criticality="critical")
    for index,value in enumerate((100,110,1500,1600)):
        findings.reconcile("CAP",[result("CAPACITY",value=value,evidence={"growth_bytes":value,"threshold_value":10000,"unit":"bytes"})],audit_run_id=f"unstable-{index}",observed_at=clock[0]+index*86400)
    case=cases.list(database_id="CAP")["items"][0]
    evidence=next(item for item in cases.get(case["id"])["facts"] if item["metric_name"]=="growth_bytes")
    projection=cases.capacity_projection(case["id"],evidence["id"])
    assert not projection["available"]
    assert "unstable" in projection["reason"]


def test_user_pagination_and_filter_surface_is_bounded(stores):
    findings,cases,clock=stores
    for index in range(4):
        database=f"DB-{index}"
        findings.reconcile(database,[result(f"RULE-{index}",severity="MEDIUM",owner="APP",object_name=f"OBJ-{index}")],audit_run_id=f"filter-{index}",observed_at=clock[0]+index)
        cases.open_manual(database,findings.list_findings(database=database)[0]["id"],"operator")
    result_page=cases.list(status="OPEN",rule="RULE-2",object_name="OBJ-2",limit=1,offset=0)
    assert result_page["total"]==1 and len(result_page["items"])==1
    assert cases.list(limit=999)["limit"]==200


def test_findings_database_projection_never_calls_external_oracle(stores):
    findings,cases,clock=stores
    findings.set_target_context("ORACLE",environment="production",criticality="critical")
    findings.reconcile("ORACLE",[result("SQL_ELAPSED",evidence={"elapsed_seconds":4,"sql_id":"SQL-1"})],audit_run_id="only-stored-evidence",observed_at=clock[0])
    case=cases.list(database_id="ORACLE")["items"][0]
    detail=cases.get(case["id"])
    assert detail["facts"]
    assert all(item["source"] in {"finding_occurrence","audit_run"} for item in detail["facts"])
    assert cases.capabilities_status()["awr"]["status"]=="SKIPPED"
