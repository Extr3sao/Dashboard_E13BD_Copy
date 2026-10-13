"""Durable finding reconciliation and deterministic operational prioritisation."""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from typing import Any, Iterable

from src.api.check_engine import redact_evidence

OPEN_STATUSES = {"OPEN", "ACKNOWLEDGED", "ACCEPTED_RISK", "FALSE_POSITIVE"}
VALID_STATUSES = {"PASS", "WARN", "FAIL"}
MANUAL_STATUSES = {"ACKNOWLEDGED", "ACCEPTED_RISK", "FALSE_POSITIVE"}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalized(value: Any) -> str:
    return _text(value).upper()


def finding_fingerprint(database_id: Any, rule_id: Any, object_type: Any = None, owner: Any = None, object_name: Any = None) -> str:
    """Identity intentionally excludes volatile evidence, values, and run metadata."""
    identity = "\x1f".join((_normalized(database_id), _normalized(rule_id), _normalized(object_type), _normalized(owner), _normalized(object_name)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _severity(value: Any) -> str:
    text = _normalized(value)
    if any(token in text for token in ("CRIT", "CRITICAL", "ALT", "HIGH")):
        return "CRITICAL"
    if any(token in text for token in ("MED", "MITJ", "WARN")):
        return "MEDIUM"
    return "LOW"


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FindingStore:
    """SQLite-backed projection of stable findings plus append-only observations."""

    def __init__(self, db_manager: Any):
        self.db = db_manager
        self.investigation_service = None
        self._migrate()

    def _refresh_investigations(self, database_id: str, observed_at: float) -> None:
        if self.investigation_service:
            try:
                self.investigation_service.on_reconcile(database_id, at=observed_at)
            except Exception:
                # Finding/audit persistence must not be rolled back because an
                # optional derived investigation projection could not refresh.
                logging.getLogger(__name__).error("investigation_projection_refresh_failed", extra={"database_id": database_id, "reason": "projection_unavailable"})

    def _connect(self):
        return self.db._get_connection()

    def _migrate(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS findings (
              id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL UNIQUE,
              database_id TEXT NOT NULL, rule_id TEXT NOT NULL, object_type TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '', object_name TEXT NOT NULL DEFAULT '',
              severity TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN', delta TEXT NOT NULL,
              first_seen REAL NOT NULL, last_seen REAL NOT NULL, occurrences INTEGER NOT NULL DEFAULT 0,
              current_value TEXT, previous_value TEXT, summary TEXT, evidence TEXT, recommendation TEXT,
              status_actor TEXT, status_reason TEXT, status_at REAL, review_date TEXT,
              created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_findings_active ON findings(database_id, status, severity, delta);
            CREATE TABLE IF NOT EXISTS finding_occurrences (
              id INTEGER PRIMARY KEY AUTOINCREMENT, finding_id INTEGER NOT NULL REFERENCES findings(id), audit_run_id TEXT NOT NULL,
              observed_at REAL NOT NULL, severity TEXT NOT NULL, value TEXT, delta TEXT NOT NULL, summary TEXT, evidence TEXT,
              UNIQUE(finding_id, audit_run_id)
            );
            CREATE TABLE IF NOT EXISTS finding_actions (
              id INTEGER PRIMARY KEY AUTOINCREMENT, finding_id INTEGER NOT NULL REFERENCES findings(id), action TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
              review_date TEXT, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS target_contexts (
              database_id TEXT PRIMARY KEY, environment TEXT NOT NULL DEFAULT 'development', criticality TEXT NOT NULL DEFAULT 'medium', owner TEXT, tags TEXT NOT NULL DEFAULT '[]', updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS red_flags (
              id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe_key TEXT NOT NULL UNIQUE, finding_id INTEGER REFERENCES findings(id), database_id TEXT NOT NULL,
              flag_type TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN', explanation TEXT NOT NULL, recommendation TEXT,
              first_seen REAL NOT NULL, last_seen REAL NOT NULL, occurrences INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_red_flags_active ON red_flags(status, priority, database_id);
            CREATE TABLE IF NOT EXISTS audit_runs (
              audit_run_id TEXT PRIMARY KEY, database_id TEXT NOT NULL, state TEXT NOT NULL,
              started_at REAL NOT NULL, completed_at REAL NOT NULL, duration_seconds REAL NOT NULL DEFAULT 0,
              checks_total INTEGER NOT NULL DEFAULT 0, checks_pass INTEGER NOT NULL DEFAULT 0, checks_warn INTEGER NOT NULL DEFAULT 0,
              checks_fail INTEGER NOT NULL DEFAULT 0, checks_error INTEGER NOT NULL DEFAULT 0, checks_skipped INTEGER NOT NULL DEFAULT 0,
              coverage_state TEXT NOT NULL, coverage_ratio REAL, findings_created INTEGER NOT NULL DEFAULT 0,
              findings_resolved INTEGER NOT NULL DEFAULT 0, red_flags_generated INTEGER NOT NULL DEFAULT 0, error_summary TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_audit_runs_target_time ON audit_runs(database_id, completed_at DESC);
            CREATE TABLE IF NOT EXISTS finding_reconciliation_receipts (
              audit_run_id TEXT PRIMARY KEY, database_id TEXT NOT NULL, observed_at REAL NOT NULL,
              status TEXT NOT NULL DEFAULT 'PENDING'
            );
            CREATE TABLE IF NOT EXISTS red_flag_observations (
              dedupe_key TEXT NOT NULL, audit_run_id TEXT NOT NULL, observed_at REAL NOT NULL,
              PRIMARY KEY(dedupe_key,audit_run_id)
            );
            """)
            receipt_columns={row[1] for row in conn.execute("PRAGMA table_info(finding_reconciliation_receipts)")}
            if "status" not in receipt_columns:
                conn.execute("ALTER TABLE finding_reconciliation_receipts ADD COLUMN status TEXT NOT NULL DEFAULT 'COMPLETED'")

    def set_target_context(self, database_id: str, *, environment: str = "development", criticality: str = "medium", owner: str = "", tags: Iterable[str] = ()) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute("INSERT INTO target_contexts(database_id,environment,criticality,owner,tags,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(database_id) DO UPDATE SET environment=excluded.environment,criticality=excluded.criticality,owner=excluded.owner,tags=excluded.tags,updated_at=excluded.updated_at", (_text(database_id), _normalized(environment).lower(), _normalized(criticality).lower(), _text(owner), json.dumps(list(tags)), now))

    @staticmethod
    def _candidate(result: dict[str, Any]) -> dict[str, Any] | None:
        if _normalized(result.get("status")) not in {"WARN", "FAIL"}:
            return None
        metrics = result.get("metrics") or {}
        value = metrics.get("value", metrics.get("row_count", result.get("current_value")))
        return {
            "database_id": _text(result.get("database_id")), "rule_id": _text(result.get("rule_id")),
            "object_type": _text(result.get("object_type")), "owner": _text(result.get("owner")), "object_name": _text(result.get("object_name")),
            "severity": _severity(result.get("severity")), "value": value, "summary": _text(result.get("summary")),
            "evidence": redact_evidence(result.get("evidence") or {}), "recommendation": _text(result.get("recommendation")),
            "comparison_direction": _text(metrics.get("comparison_direction") or result.get("comparison_direction") or "higher_is_worse"),
        }

    def reconcile(self, database_id: str, rule_results: Iterable[dict[str, Any]], *, audit_run_id: str | None = None, audit_state: str = "SUCCESS", target_context: dict[str, Any] | None = None, observed_at: float | None = None) -> dict[str, Any]:
        """Reconcile one target only when the audit outcome proves coverage."""
        now = time.time() if observed_at is None else observed_at
        run_id = audit_run_id or str(uuid.uuid4())
        if target_context:
            self.set_target_context(database_id, **target_context)
        results = [dict(item) for item in rule_results]
        if _normalized(audit_state) != "SUCCESS":
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                receipt=conn.execute("SELECT database_id,status FROM finding_reconciliation_receipts WHERE audit_run_id=?",(run_id,)).fetchone()
                if receipt and receipt[0]!=database_id: raise ValueError("audit_run_target_mismatch")
                if receipt and receipt[1]=="COMPLETED":
                    conn.commit()
                    self._record_audit(run_id,database_id,results,audit_state,now,coverage_valid=False)
                    return {"audit_run_id":run_id,"findings":self.summary(database_id),"red_flags":self.list_red_flags(database_id=database_id),"coverage_valid":False}
                if receipt and receipt[1]=="FAILED":
                    conn.execute("UPDATE finding_reconciliation_receipts SET observed_at=?,status='PENDING' WHERE audit_run_id=?",(now,run_id))
                else:
                    conn.execute("INSERT OR IGNORE INTO finding_reconciliation_receipts(audit_run_id,database_id,observed_at,status) VALUES(?,?,?,'PENDING')",(run_id,database_id,now))
            self._upsert_run_health(database_id, "AUDIT_EXECUTION_FAILURE", now, "Audit execution did not complete; existing findings were not resolved.", audit_run_id=run_id)
            self._record_audit(run_id, database_id, results, audit_state, now, coverage_valid=False)
            with self._connect() as conn:
                conn.execute("UPDATE finding_reconciliation_receipts SET status='FAILED',observed_at=? WHERE audit_run_id=? AND status!='COMPLETED'",(now,run_id))
            self._refresh_investigations(database_id, now)
            return {"audit_run_id": run_id, "findings": self.summary(database_id), "red_flags": self.list_red_flags(database_id=database_id), "coverage_valid": False}
        evaluated = {_text(item.get("rule_id")) for item in results if _normalized(item.get("status")) in VALID_STATUSES}
        if any(_normalized(item.get("status")) in {"ERROR", "SKIPPED"} for item in results):
            self._upsert_run_health(database_id, "COVERAGE_DEGRADED", now, "One or more rules were not evaluated successfully; absent findings were retained.", audit_run_id=run_id)
        candidates = [item for item in (self._candidate(result) for result in results) if item]
        seen: set[str] = set()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            receipt = conn.execute("SELECT database_id,status FROM finding_reconciliation_receipts WHERE audit_run_id=?", (run_id,)).fetchone()
            if receipt and receipt[1]=="COMPLETED":
                if receipt[0] != database_id:
                    raise ValueError("audit_run_target_mismatch")
                # Repair projections after a crash between committed reconciliation
                # and projection publication without counting observations twice.
                conn.commit()
                self._refresh_red_flags(database_id, now, run_id)
                self._record_audit(run_id, database_id, results, audit_state, now, coverage_valid=bool(evaluated))
                self._refresh_investigations(database_id, now)
                return {"audit_run_id": run_id, "findings": self.summary(database_id), "red_flags": self.list_red_flags(database_id=database_id), "coverage_valid": bool(evaluated)}
            if receipt and receipt[0]!=database_id: raise ValueError("audit_run_target_mismatch")
            if receipt and receipt[1]=="FAILED":
                conn.execute("UPDATE finding_reconciliation_receipts SET observed_at=?,status='PENDING' WHERE audit_run_id=?",(now,run_id))
            else:
                conn.execute("INSERT OR IGNORE INTO finding_reconciliation_receipts(audit_run_id,database_id,observed_at,status) VALUES(?,?,?,'PENDING')",(run_id,database_id,now))
            for candidate in candidates:
                candidate["database_id"] = candidate["database_id"] or database_id
                fingerprint = finding_fingerprint(candidate["database_id"], candidate["rule_id"], candidate["object_type"], candidate["owner"], candidate["object_name"])
                seen.add(fingerprint)
                row = conn.execute("SELECT * FROM findings WHERE fingerprint=?", (fingerprint,)).fetchone()
                if row is None:
                    delta, status, previous, occurrences = "NEW", "OPEN", None, 1
                    conn.execute("INSERT INTO findings(fingerprint,database_id,rule_id,object_type,owner,object_name,severity,status,delta,first_seen,last_seen,occurrences,current_value,previous_value,summary,evidence,recommendation,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (fingerprint, candidate["database_id"], candidate["rule_id"], candidate["object_type"], candidate["owner"], candidate["object_name"], candidate["severity"], status, delta, now, now, occurrences, json.dumps(candidate["value"]), previous, candidate["summary"], json.dumps(candidate["evidence"]), candidate["recommendation"], now, now))
                    finding_id = conn.execute("SELECT id FROM findings WHERE fingerprint=?", (fingerprint,)).fetchone()[0]
                else:
                    record = dict(zip([x[0] for x in conn.execute("SELECT * FROM findings LIMIT 0").description], row))
                    previous = json.loads(record["current_value"]) if record["current_value"] else None
                    delta = self._evolution(previous, candidate["value"], candidate["comparison_direction"])
                    prior_status = record["status"]
                    status = prior_status if prior_status in MANUAL_STATUSES else "OPEN"
                    if prior_status == "RESOLVED": delta, status = "REOPENED", "OPEN"
                    finding_id, occurrences = record["id"], int(record["occurrences"]) + 1
                    conn.execute("UPDATE findings SET severity=?, status=?, delta=?, last_seen=?, occurrences=?, current_value=?, previous_value=?, summary=?, evidence=?, recommendation=?, updated_at=? WHERE id=?", (candidate["severity"], status, delta, now, occurrences, json.dumps(candidate["value"]), json.dumps(previous), candidate["summary"], json.dumps(candidate["evidence"]), candidate["recommendation"], now, finding_id))
                conn.execute("INSERT OR IGNORE INTO finding_occurrences(finding_id,audit_run_id,observed_at,severity,value,delta,summary,evidence) VALUES(?,?,?,?,?,?,?,?)", (finding_id, run_id, now, candidate["severity"], json.dumps(candidate["value"]), delta, candidate["summary"], json.dumps(candidate["evidence"])))
            # Only a successfully evaluated rule scope can resolve its absent open findings.
            if evaluated:
                placeholders = ",".join("?" for _ in evaluated)
                rows = conn.execute(f"SELECT id,fingerprint FROM findings WHERE database_id=? AND rule_id IN ({placeholders}) AND status IN ('OPEN','ACKNOWLEDGED','ACCEPTED_RISK','FALSE_POSITIVE')", (database_id, *evaluated)).fetchall()
                for finding_id, fingerprint in rows:
                    if fingerprint not in seen:
                        conn.execute("UPDATE findings SET status='RESOLVED',delta='RESOLVED',last_seen=?,updated_at=? WHERE id=?", (now, now, finding_id))
                        conn.execute("INSERT OR IGNORE INTO finding_occurrences(finding_id,audit_run_id,observed_at,severity,value,delta,summary,evidence) SELECT id,?,?,?,?,?,?,? FROM findings WHERE id=?", (run_id, now, "LOW", None, "RESOLVED", "Rule passed in a successfully evaluated scope.", "{}", finding_id))
            if evaluated and not any(_normalized(item.get("status")) in {"ERROR","SKIPPED"} for item in results):
                conn.execute("UPDATE red_flags SET status='RESOLVED',updated_at=? WHERE database_id=? AND finding_id IS NULL AND flag_type IN ('AUDIT_EXECUTION_FAILURE','DATABASE_UNREACHABLE','COVERAGE_DEGRADED') AND status='OPEN'",(now,database_id))
            conn.execute("UPDATE finding_reconciliation_receipts SET observed_at=?,status='COMPLETED' WHERE audit_run_id=?", (now,run_id))
        self._refresh_red_flags(database_id, now, run_id)
        self._record_audit(run_id, database_id, results, audit_state, now, coverage_valid=bool(evaluated))
        self._refresh_investigations(database_id, now)
        return {"audit_run_id": run_id, "findings": self.summary(database_id), "red_flags": self.list_red_flags(database_id=database_id), "coverage_valid": bool(evaluated)}

    def _record_audit(self, run_id: str, database_id: str, results: list[dict[str, Any]], state: str, now: float, *, coverage_valid: bool) -> None:
        counts = {_normalized(item.get("status")): 0 for item in results}
        for item in results: counts[_normalized(item.get("status"))] = counts.get(_normalized(item.get("status")), 0) + 1
        total = len(results); evaluated = sum(counts.get(key, 0) for key in VALID_STATUSES)
        coverage = "FULL" if total and evaluated == total else ("PARTIAL" if evaluated else "UNKNOWN")
        if counts.get("ERROR", 0) or counts.get("SKIPPED", 0): coverage = "DEGRADED" if evaluated == 0 else "PARTIAL"
        with self._connect() as conn:
            conn.execute("INSERT INTO audit_runs(audit_run_id,database_id,state,started_at,completed_at,checks_total,checks_pass,checks_warn,checks_fail,checks_error,checks_skipped,coverage_state,coverage_ratio,error_summary) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(audit_run_id) DO UPDATE SET database_id=excluded.database_id,state=excluded.state,completed_at=excluded.completed_at,checks_total=excluded.checks_total,checks_pass=excluded.checks_pass,checks_warn=excluded.checks_warn,checks_fail=excluded.checks_fail,checks_error=excluded.checks_error,checks_skipped=excluded.checks_skipped,coverage_state=excluded.coverage_state,coverage_ratio=excluded.coverage_ratio,error_summary=excluded.error_summary", (run_id, database_id, _normalized(state), now, now, total, counts.get("PASS", 0), counts.get("WARN", 0), counts.get("FAIL", 0), counts.get("ERROR", 0), counts.get("SKIPPED", 0), coverage, (evaluated / total) if total else None, None))

    def _latest_audit(self, database_id: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM audit_runs WHERE database_id=? ORDER BY completed_at DESC LIMIT 1", (database_id,))
        return rows[0] if rows else None

    def health(self, database_id: str, *, now: float | None = None, stale_after_seconds: float = 86400) -> dict[str, Any]:
        now = time.time() if now is None else now; audit = self._latest_audit(database_id)
        context_rows = self._rows("SELECT * FROM target_contexts WHERE database_id=?", (database_id,)); context = context_rows[0] if context_rows else {"environment": "development", "criticality": "medium", "owner": "", "tags": "[]"}
        active = self.list_findings(database=database_id); flags = self.list_red_flags(database_id=database_id)
        if not audit: status, reason = "NOT_AUDITED", "No completed audit is available."
        elif audit["state"] != "SUCCESS": status, reason = ("UNREACHABLE" if any(item["flag_type"] == "DATABASE_UNREACHABLE" for item in flags) else "AUDIT_FAILED"), "The latest audit did not complete successfully."
        elif now - audit["completed_at"] > stale_after_seconds: status, reason = "UNKNOWN", "The latest successful audit is stale."
        elif audit["coverage_state"] != "FULL": status, reason = "DEGRADED", f"Coverage is {audit['coverage_state'].lower()}: {audit['checks_error']} error, {audit['checks_skipped']} skipped."
        elif any(item["priority"] in {"P1", "P2"} for item in flags) or any(item["severity"] == "CRITICAL" for item in active): status, reason = "CRITICAL", "Critical findings or high-priority red flags require action."
        elif active or flags: status, reason = "ATTENTION", "Active findings require operator attention."
        else: status, reason = "HEALTHY", "Latest audit completed with full coverage and no active findings."
        return {"database_id": database_id, "name": database_id, "environment": context["environment"], "criticality": context["criticality"], "health_status": status, "health_reason": reason, "last_audit": audit, "reachable": status != "UNREACHABLE", "active_findings": len(active), "critical_findings": sum(item["severity"] == "CRITICAL" for item in active), "worsening_findings": sum(item["delta"] == "WORSENING" for item in active), "new_findings": sum(item["delta"] == "NEW" for item in active), "red_flags": len(flags), "highest_priority": flags[0]["priority"] if flags else None}

    def fleet(self, *, now: float | None = None) -> dict[str, Any]:
        now=time.time() if now is None else now
        ids={row["database_id"] for row in self._rows("SELECT database_id FROM target_contexts UNION SELECT database_id FROM audit_runs UNION SELECT database_id FROM findings")}
        contexts={row["database_id"]:row for row in self._rows("SELECT * FROM target_contexts")}
        audits={row["database_id"]:row for row in self._rows("SELECT * FROM (SELECT audit_runs.*,ROW_NUMBER() OVER (PARTITION BY database_id ORDER BY completed_at DESC,audit_run_id DESC) AS rn FROM audit_runs) WHERE rn=1")}
        activity={row["database_id"]:row for row in self._rows("SELECT database_id,COUNT(*) AS active_findings,SUM(CASE WHEN severity='CRITICAL' THEN 1 ELSE 0 END) AS critical_findings,SUM(CASE WHEN delta='WORSENING' THEN 1 ELSE 0 END) AS worsening_findings,SUM(CASE WHEN delta='NEW' THEN 1 ELSE 0 END) AS new_findings FROM findings WHERE status!='RESOLVED' GROUP BY database_id")}
        all_deltas=self._rows("SELECT delta,COUNT(*) AS count FROM findings GROUP BY delta")
        finding_counts={key:0 for key in ("NEW","WORSENING","PERSISTENT","IMPROVING","RESOLVED","REOPENED")}
        for row in all_deltas:
            if row["delta"] in finding_counts: finding_counts[row["delta"]]=row["count"]
        flags=self.list_red_flags()
        flags_by_database={}
        red_counts={key:0 for key in ("P1","P2","P3","P4")}
        for flag in flags:
            flags_by_database.setdefault(flag["database_id"],[]).append(flag)
            if flag["priority"] in red_counts: red_counts[flag["priority"]]+=1
        targets=[]
        for database_id in ids:
            audit=audits.get(database_id); context=contexts.get(database_id,{"environment":"development","criticality":"medium","owner":"","tags":"[]"})
            counts=activity.get(database_id,{"active_findings":0,"critical_findings":0,"worsening_findings":0,"new_findings":0})
            target_flags=flags_by_database.get(database_id,[])
            if not audit: status,reason="NOT_AUDITED","No completed audit is available."
            elif audit["state"]!="SUCCESS": status,reason=("UNREACHABLE" if any(flag["flag_type"]=="DATABASE_UNREACHABLE" for flag in target_flags) else "AUDIT_FAILED"),"The latest audit did not complete successfully."
            elif now-audit["completed_at"]>86400: status,reason="UNKNOWN","The latest successful audit is stale."
            elif audit["coverage_state"]!="FULL": status,reason="DEGRADED",f"Coverage is {audit['coverage_state'].lower()}: {audit['checks_error']} error, {audit['checks_skipped']} skipped."
            elif any(flag["priority"] in {"P1","P2"} for flag in target_flags) or counts["critical_findings"]: status,reason="CRITICAL","Critical findings or high-priority red flags require action."
            elif counts["active_findings"] or target_flags: status,reason="ATTENTION","Active findings require operator attention."
            else: status,reason="HEALTHY","Latest audit completed with full coverage and no active findings."
            targets.append({"database_id":database_id,"name":database_id,"environment":context["environment"],"criticality":context["criticality"],"health_status":status,"health_reason":reason,"last_audit":audit,"reachable":status!="UNREACHABLE","active_findings":counts["active_findings"],"critical_findings":counts["critical_findings"],"worsening_findings":counts["worsening_findings"],"new_findings":counts["new_findings"],"red_flags":len(target_flags),"highest_priority":target_flags[0]["priority"] if target_flags else None})
        priority={"CRITICAL":0,"UNREACHABLE":1,"AUDIT_FAILED":2,"DEGRADED":3,"ATTENTION":4,"UNKNOWN":5,"NOT_AUDITED":6,"HEALTHY":7}
        targets.sort(key=lambda item:(priority.get(item["health_status"],8),item["name"]))
        return {"targets":targets,"counts":{key:sum(item["health_status"]==key for item in targets) for key in ("HEALTHY","ATTENTION","CRITICAL","UNREACHABLE","DEGRADED","UNKNOWN","NOT_AUDITED")},"findings":finding_counts,"red_flags":red_counts,"needs_attention":flags}

    def audit_history(self, database_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM audit_runs" + (" WHERE database_id=?" if database_id else "") + " ORDER BY completed_at DESC LIMIT ?", ((database_id, max(1, min(limit, 200))) if database_id else (max(1, min(limit, 200)),)))

    def trends(self, database_id: str | None = None, window_hours: int = 168, *, now: float | None = None) -> list[dict[str, Any]]:
        now = time.time() if now is None else now; start = now - max(1, window_hours) * 3600; where = "completed_at>=?" + (" AND database_id=?" if database_id else ""); args = (start, database_id) if database_id else (start,)
        rows = self._rows("SELECT * FROM audit_runs WHERE " + where + " ORDER BY completed_at", args)
        return [{"at": row["completed_at"], "active_findings": len(self.list_findings(database=row["database_id"])), "critical_findings": sum(item["severity"] == "CRITICAL" for item in self.list_findings(database=row["database_id"])), "red_flags": len(self.list_red_flags(database_id=row["database_id"])), "unreachable": int(row["state"] != "SUCCESS"), "failed_audits": int(row["state"] != "SUCCESS"), "coverage": row["coverage_ratio"]} for row in rows]

    def reconcile_post_crq(self, report: dict[str, Any], *, target_context: dict[str, Any] | None = None, audit_run_id: str | None = None, audit_state: str = "SUCCESS") -> dict[str, Any]:
        """Use bounded row envelopes when Post-CRQ can identify the affected object."""
        database_id = _text((report.get("context") or {}).get("profile"))
        by_rule = {item.get("rule_id"): item for item in report.get("rule_results") or []}
        expanded: list[dict[str, Any]] = []
        for envelope in report.get("finding_envelopes") or []:
            if envelope.get("runtime_status") != "ok":
                continue
            base = by_rule.get(envelope.get("check_id"))
            if not base or _normalized(base.get("status")) not in {"WARN", "FAIL"}:
                continue
            item = dict(base)
            item.update({"owner": envelope.get("schema"), "object_name": envelope.get("object_name"), "object_type": envelope.get("object_type"), "severity": envelope.get("sql_severity") or base.get("severity"), "summary": envelope.get("title") or base.get("summary"), "evidence": redact_evidence(envelope.get("evidence") or {})})
            if str(report.get("audit_type") or "").lower()=="oracle_diagnostics":
                observed_value=(envelope.get("evidence") or {}).get("value")
                if isinstance(observed_value,(int,float)):
                    direction=(envelope.get("evidence") or {}).get("comparison_direction")
                    if direction not in {"higher_is_worse","lower_is_worse"}: direction="none"
                    item["metrics"]={**(item.get("metrics") or {}),"value":observed_value,"comparison_direction":direction}
            expanded.append(item)
        # Passes are kept so their successfully evaluated rule scope can resolve
        # prior object-level findings. A failed rule without a usable object stays rule-level.
        covered = {item.get("rule_id") for item in expanded}
        expanded.extend(item for item in by_rule.values() if _normalized(item.get("status")) == "PASS" or item.get("rule_id") not in covered)
        return self.reconcile(database_id, expanded, audit_run_id=audit_run_id or report.get("audit_run_id"), audit_state=audit_state, target_context=target_context)

    @staticmethod
    def _evolution(previous: Any, current: Any, direction: str) -> str:
        old, new = _number(previous), _number(current)
        if old is None or new is None or old == new or direction not in {"higher_is_worse", "lower_is_worse"}:
            return "PERSISTENT"
        worsening = new > old if direction == "higher_is_worse" else new < old
        return "WORSENING" if worsening else "IMPROVING"

    def _context(self, conn, database_id: str) -> dict[str, Any]:
        row = conn.execute("SELECT environment,criticality FROM target_contexts WHERE database_id=?", (database_id,)).fetchone()
        return {"environment": row[0], "criticality": row[1]} if row else {"environment": "development", "criticality": "medium"}

    def _priority(self, finding: dict[str, Any], context: dict[str, Any]) -> tuple[str, list[str]]:
        reasons = [f"finding severity {finding['severity'].lower()}", f"target {context['environment']}/{context['criticality']}"]
        if finding["delta"] in {"NEW", "WORSENING", "REOPENED"}: reasons.append(f"evolution {finding['delta'].lower()}")
        if finding["occurrences"] >= 3: reasons.append(f"present in {finding['occurrences']} audits")
        if context["environment"] == "production" and context["criticality"] == "critical" and finding["severity"] == "CRITICAL" and finding["delta"] in {"NEW", "WORSENING", "REOPENED"}: return "P1", reasons
        if finding["severity"] == "CRITICAL" or (finding["severity"] == "HIGH") or (finding["severity"] == "CRITICAL" and finding["occurrences"] >= 3): return "P2", reasons
        if finding["delta"] in {"NEW", "WORSENING", "REOPENED"} or finding["severity"] == "MEDIUM": return "P3", reasons
        return "P4", reasons

    def _refresh_red_flags(self, database_id: str, now: float, audit_run_id: str) -> None:
        with self._connect() as conn:
            context = self._context(conn, database_id)
            rows = conn.execute("SELECT * FROM findings WHERE database_id=? AND status IN ('OPEN','ACKNOWLEDGED','ACCEPTED_RISK','FALSE_POSITIVE')", (database_id,)).fetchall()
            columns = [item[0] for item in conn.execute("SELECT * FROM findings LIMIT 0").description]
            desired = set()
            for row in rows:
                finding = dict(zip(columns, row)); flag_type = None
                if finding["delta"] == "NEW" and finding["severity"] == "CRITICAL": flag_type = "NEW_CRITICAL_FINDING"
                elif finding["delta"] == "WORSENING": flag_type = "WORSENING_FINDING"
                elif finding["delta"] == "REOPENED": flag_type = "REOPENED_FINDING"
                elif finding["severity"] == "CRITICAL" and finding["occurrences"] >= 3: flag_type = "PERSISTENT_CRITICAL_FINDING"
                if not flag_type: continue
                priority, reasons = self._priority(finding, context); key = f"{flag_type}:{finding['id']}"; desired.add(key)
                explanation = "; ".join(reasons)
                existing = conn.execute("SELECT id,occurrences FROM red_flags WHERE dedupe_key=?", (key,)).fetchone()
                if existing:
                    observation=conn.execute("INSERT OR IGNORE INTO red_flag_observations(dedupe_key,audit_run_id,observed_at) VALUES(?,?,?)",(key,audit_run_id,now))
                    increments=1 if observation.rowcount else 0
                    conn.execute("UPDATE red_flags SET priority=?,status='OPEN',explanation=?,recommendation=?,last_seen=?,occurrences=?,updated_at=? WHERE id=?", (priority, explanation, finding["recommendation"], now, existing[1] + increments, now, existing[0]))
                else:
                    conn.execute("INSERT INTO red_flags(dedupe_key,finding_id,database_id,flag_type,priority,status,explanation,recommendation,first_seen,last_seen,occurrences,created_at,updated_at) VALUES(?,?,?,?,?,'OPEN',?,?,?,?,1,?,?)", (key, finding["id"], database_id, flag_type, priority, explanation, finding["recommendation"], now, now, now, now))
                    conn.execute("INSERT OR IGNORE INTO red_flag_observations(dedupe_key,audit_run_id,observed_at) VALUES(?,?,?)",(key,audit_run_id,now))
            if desired:
                placeholders = ",".join("?" for _ in desired)
                conn.execute(f"UPDATE red_flags SET status='RESOLVED',updated_at=? WHERE database_id=? AND finding_id IS NOT NULL AND dedupe_key NOT IN ({placeholders})", (now, database_id, *desired))
            else:
                conn.execute("UPDATE red_flags SET status='RESOLVED',updated_at=? WHERE database_id=? AND finding_id IS NOT NULL", (now, database_id))

    def _upsert_run_health(self, database_id: str, flag_type: str, now: float, explanation: str, *, audit_run_id: str) -> None:
        key = f"{flag_type}:{database_id}";
        with self._connect() as conn:
            old = conn.execute("SELECT id,occurrences FROM red_flags WHERE dedupe_key=?", (key,)).fetchone()
            observation=conn.execute("INSERT OR IGNORE INTO red_flag_observations(dedupe_key,audit_run_id,observed_at) VALUES(?,?,?)",(key,audit_run_id,now))
            if old:
                increments=1 if observation.rowcount else 0
                conn.execute("UPDATE red_flags SET last_seen=?,occurrences=?,status='OPEN',updated_at=? WHERE id=?", (now, old[1] + increments, now, old[0]))
            else:
                conn.execute("INSERT INTO red_flags(dedupe_key,database_id,flag_type,priority,status,explanation,first_seen,last_seen,occurrences,created_at,updated_at) VALUES(?,?,?,'P1','OPEN',?,?,?,1,?,?)", (key, database_id, flag_type, explanation, now, now, now, now))

    def action(self, finding_id: int, action: str, actor: str, reason: str, review_date: str | None = None) -> dict[str, Any]:
        status = _normalized(action)
        if status not in MANUAL_STATUSES or not _text(reason): raise ValueError("A reason is required for this lifecycle action.")
        now = time.time()
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM findings WHERE id=?", (finding_id,)).fetchone(): raise KeyError(finding_id)
            conn.execute("UPDATE findings SET status=?,status_actor=?,status_reason=?,status_at=?,review_date=?,updated_at=? WHERE id=?", (status, actor, reason.strip(), now, review_date, now, finding_id))
            conn.execute("INSERT INTO finding_actions(finding_id,action,actor,reason,review_date,created_at) VALUES(?,?,?,?,?,?)", (finding_id, status, actor, reason.strip(), review_date, now))
        return self.get_finding(finding_id)

    def _rows(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.execute(query, params); columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def list_findings(self, *, resolved: bool | None = False, database: str | None = None, severity: str | None = None, status: str | None = None, delta: str | None = None, rule: str | None = None) -> list[dict[str, Any]]:
        filters, args = [], []
        if resolved is True: filters.append("status='RESOLVED'")
        elif resolved is False: filters.append("status!='RESOLVED'")
        for field, value in (("database_id", database), ("severity", severity), ("status", status), ("delta", delta), ("rule_id", rule)):
            if value: filters.append(f"{field}=?"); args.append(_normalized(value) if field in {"severity", "status", "delta"} else value)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        return self._rows("SELECT * FROM findings" + where + " ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END, last_seen DESC", tuple(args))

    def get_finding(self, finding_id: int) -> dict[str, Any]:
        rows = self._rows("SELECT * FROM findings WHERE id=?", (finding_id,))
        if not rows: raise KeyError(finding_id)
        item = rows[0]; item["history"] = self._rows("SELECT * FROM finding_occurrences WHERE finding_id=? ORDER BY observed_at", (finding_id,)); item["actions"] = self._rows("SELECT * FROM finding_actions WHERE finding_id=? ORDER BY created_at DESC", (finding_id,)); return item

    def list_red_flags(self, *, database_id: str | None = None, priority: str | None = None, active_only: bool = True) -> list[dict[str, Any]]:
        filters, args = (["r.status='OPEN'"] if active_only else []), []
        if database_id: filters.append("r.database_id=?"); args.append(database_id)
        if priority: filters.append("r.priority=?"); args.append(_normalized(priority))
        where = " WHERE " + " AND ".join(filters) if filters else ""
        return self._rows("SELECT r.*,f.summary AS finding_summary,f.severity AS finding_severity,f.delta AS finding_delta,f.first_seen AS finding_first_seen,f.last_seen AS finding_last_seen,f.occurrences AS finding_occurrences FROM red_flags r LEFT JOIN findings f ON f.id=r.finding_id" + where + " ORDER BY r.priority, r.last_seen DESC", tuple(args))

    def summary(self, database_id: str | None = None) -> dict[str, Any]:
        rows = self.list_findings(resolved=None, database=database_id)
        flags = self.list_red_flags(database_id=database_id)
        return {"findings": {key: sum(1 for row in rows if row["delta"] == key) for key in ("NEW", "WORSENING", "PERSISTENT", "IMPROVING", "RESOLVED", "REOPENED")}, "red_flags": {key: sum(1 for row in flags if row["priority"] == key) for key in ("P1", "P2", "P3", "P4")}}
