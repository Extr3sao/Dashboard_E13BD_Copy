"""Deterministic, explainable Oracle-first DBA investigation intelligence."""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
from typing import Any

from src.api.security import redact_secrets

DEFAULT_WINDOW_SECONDS = 1800
MAX_CORRELATION_CANDIDATES = 100
MAX_EVIDENCE_ROWS = 500
MAX_TEXT = 500

_CATEGORY_RULES = (
    ("EXECUTION_PLAN", ("plan_hash", "execution_plan", "plan change", "plan_change")),
    ("STATISTICS", ("statistics", "last_analyzed", "stale stats", "num_rows", "stale_statistics")),
    ("LOCKING", ("blocking", "blocked session", "lock wait", "lock_chain", "blocking_session")),
    ("CAPACITY", ("tablespace", "segment growth", "space pressure", "capacity", "free_space")),
    ("CONNECTIVITY", ("connection", "unreachable", "oracle timeout", "ora-12170", "ora-12541")),
    ("AUDIT_COVERAGE", ("coverage", "skipped check", "audit incomplete")),
    ("OBJECT_HEALTH", ("invalid object", "object status", "compilation")),
    ("WORKLOAD", ("workload", "execution count", "buffer gets", "disk reads", "rows processed")),
    ("PERFORMANCE", ("slow", "elapsed", "duration", "performance", "latency", "execution time")),
    ("CONFIGURATION", ("configuration", "parameter", "setting changed")),
    ("AVAILABILITY", ("availability", "database down", "instance unavailable")),
)

_SAFE_META_KEYS = {
    "sql_id", "plan_hash", "previous_plan_hash", "tablespace", "segment_name", "owner",
    "object_name", "object_type", "blocking_session", "blocked_session", "session_id",
    "last_analyzed", "stale", "threshold", "threshold_value", "unit", "metric_name",
    "wait_class", "event", "sample_count", "source_view", "capability",
}
_METRIC_KEYS = {
    "elapsed_seconds", "duration_seconds", "execution_seconds", "execution_count", "buffer_gets",
    "disk_reads", "rows_processed", "used_bytes", "free_bytes", "used_percent", "growth_bytes",
    "wait_seconds", "statistics_age_days",
}

RULE_RELATIONSHIPS = {
    "LOCKING": ("PERFORMANCE", "LONG_RUNNING_SQL"),
    "STATISTICS": ("EXECUTION_PLAN", "PERFORMANCE"),
    "EXECUTION_PLAN": ("PERFORMANCE",),
    "CAPACITY": ("SEGMENT_GROWTH", "PERFORMANCE"),
    "OBJECT_HEALTH": ("DEPLOYMENT_CHANGE", "SCHEMA_CHANGE"),
}

RECOMMENDED_CHECKS = {
    "LOCKING": ["Review current blocking sessions and the blocking chain."],
    "PERFORMANCE": ["Compare execution duration and workload before and after first observation."],
    "EXECUTION_PLAN": ["Compare current and previous execution plans for the same SQL identifier."],
    "STATISTICS": ["Review statistics age/state for affected objects against the normal maintenance policy."],
    "CAPACITY": ["Review free space, segment growth and configured capacity thresholds."],
    "OBJECT_HEALTH": ["Review affected object validity and recent schema/deployment changes."],
    "CONNECTIVITY": ["Verify listener, network path and target credential references."],
    "AUDIT_COVERAGE": ["Restore full rule coverage before treating absent Findings as resolved."],
    "WORKLOAD": ["Compare execution count, reads and workload around the observation window."],
    "AVAILABILITY": ["Verify database and instance availability from the target operations team."],
    "CONFIGURATION": ["Compare effective configuration with the approved baseline."],
}


def _json(value: Any, default):
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _safe_scalar(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return str(redact_secrets(value))[:MAX_TEXT]
    return None


def _walk(value, depth=0):
    if depth > 5 or not isinstance(value, dict):
        return
    for key, item in value.items():
        name = str(key).strip().lower().replace(" ", "_")
        if isinstance(item, dict):
            yield from _walk(item, depth + 1)
        elif isinstance(item, list):
            for child in item[:20]:
                if isinstance(child, dict):
                    yield from _walk(child, depth + 1)
        else:
            yield name, item


def classify_evidence(rule_id: str, summary: str, evidence: Any) -> str:
    text = " ".join([str(rule_id or ""), str(summary or "")] + [f"{key} {value}" for key, value in _walk(_json(evidence, {}))]).lower()
    for category, markers in _CATEGORY_RULES:
        if any(marker in text for marker in markers):
            return category
    return "OBJECT_HEALTH" if rule_id else "CONFIGURATION"


class InvestigationStore:
    """Persists cases but derives correlations from a bounded temporal window."""

    def __init__(self, finding_store, *, auto_open=None, window_seconds=DEFAULT_WINDOW_SECONDS, capabilities=None, clock=time.time):
        self.findings = finding_store
        self.clock = clock
        self.auto_open = os.getenv("E13DB_INVESTIGATIONS_AUTO_OPEN", "true").lower() == "true" if auto_open is None else bool(auto_open)
        self.window_seconds = max(60, min(int(window_seconds), 86400))
        self.capabilities = capabilities or {
            "oracle": True,
            "awr_license": os.getenv("E13DB_ORACLE_AWR_LICENSED", "false").lower() == "true",
            "awr_privilege": os.getenv("E13DB_ORACLE_AWR_PRIVILEGE", "false").lower() == "true",
            "ash_license": os.getenv("E13DB_ORACLE_ASH_LICENSED", "false").lower() == "true",
            "ash_privilege": os.getenv("E13DB_ORACLE_ASH_PRIVILEGE", "false").lower() == "true",
        }
        self._migrate()

    def _connect(self):
        return self.findings._connect()

    def _migrate(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS investigations(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, database_id TEXT NOT NULL,
                  primary_finding_id INTEGER REFERENCES findings(id), status TEXT NOT NULL DEFAULT 'OPEN',
                  opened_at REAL NOT NULL, updated_at REAL NOT NULL, closed_at REAL,
                  summary TEXT NOT NULL, source TEXT NOT NULL, actor TEXT NOT NULL,
                  time_window_start REAL NOT NULL, time_window_end REAL NOT NULL,
                  fingerprint TEXT NOT NULL, confirmed_cause TEXT, cause_actor TEXT, cause_at REAL,
                  cause_evidence TEXT NOT NULL DEFAULT '[]', resolution TEXT, actions_taken TEXT,
                  resolved_at REAL, resolved_by TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_investigation_db_status ON investigations(database_id,status,updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_investigation_fingerprint ON investigations(fingerprint,status,opened_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_investigation_one_open_primary
                  ON investigations(primary_finding_id) WHERE primary_finding_id IS NOT NULL AND status IN ('OPEN','MONITORING');
                CREATE TABLE IF NOT EXISTS investigation_events(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                  event_type TEXT NOT NULL, observed_at REAL NOT NULL, actor TEXT NOT NULL DEFAULT 'E13DB',
                  summary TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_investigation_events ON investigation_events(investigation_id,observed_at);
                CREATE TABLE IF NOT EXISTS investigation_evidence(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                  database_id TEXT NOT NULL, finding_id INTEGER, occurrence_id INTEGER, audit_run_id TEXT,
                  rule_id TEXT NOT NULL, category TEXT NOT NULL, observed_at REAL NOT NULL,
                  metric_name TEXT, value_json TEXT, unit TEXT, object_type TEXT, owner TEXT, object_name TEXT,
                  summary TEXT NOT NULL, source TEXT NOT NULL, sensitivity TEXT NOT NULL DEFAULT 'REDACTED', metadata_json TEXT NOT NULL DEFAULT '{}',
                  UNIQUE(investigation_id,occurrence_id,category,metric_name)
                );
                CREATE INDEX IF NOT EXISTS idx_inv_evidence_window ON investigation_evidence(investigation_id,observed_at,category);
                CREATE INDEX IF NOT EXISTS idx_inv_evidence_object ON investigation_evidence(database_id,owner,object_name,observed_at);
                CREATE TABLE IF NOT EXISTS investigation_correlations(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                  related_finding_id INTEGER NOT NULL, category TEXT NOT NULL, strength TEXT NOT NULL,
                  occurred_at REAL NOT NULL, reasons_json TEXT NOT NULL, UNIQUE(investigation_id,related_finding_id,category)
                );
                CREATE TABLE IF NOT EXISTS investigation_hypotheses(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                  hypothesis_type TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
                  supporting_evidence_json TEXT NOT NULL DEFAULT '[]', contradicting_evidence_json TEXT NOT NULL DEFAULT '[]',
                  status TEXT NOT NULL DEFAULT 'POSSIBLE', recommended_checks_json TEXT NOT NULL DEFAULT '[]',
                  updated_at REAL NOT NULL, updated_by TEXT NOT NULL DEFAULT 'E13DB',
                  UNIQUE(investigation_id,hypothesis_type)
                );
                CREATE TABLE IF NOT EXISTS investigation_checks(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, investigation_id INTEGER NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
                  check_key TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
                  result_summary TEXT, actor TEXT, updated_at REAL NOT NULL, UNIQUE(investigation_id,check_key)
                );
                CREATE TABLE IF NOT EXISTS investigation_plan_observations(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, database_id TEXT NOT NULL, sql_id TEXT NOT NULL,
                  plan_hash TEXT NOT NULL, first_seen REAL NOT NULL, last_seen REAL NOT NULL,
                  metrics_json TEXT NOT NULL DEFAULT '{}', UNIQUE(database_id,sql_id,plan_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_inv_plan_history ON investigation_plan_observations(database_id,sql_id,first_seen);
                CREATE TABLE IF NOT EXISTS investigation_rule_relationships(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, source_category TEXT NOT NULL, target_category TEXT NOT NULL,
                  reason TEXT NOT NULL, source_rule TEXT NOT NULL DEFAULT '', target_rule TEXT NOT NULL DEFAULT '',
                  UNIQUE(source_category,target_category,source_rule,target_rule)
                );
            """)
            for source,targets in RULE_RELATIONSHIPS.items():
                for target in targets:
                    conn.execute("INSERT OR IGNORE INTO investigation_rule_relationships(source_category,target_category,reason) VALUES(?,?,?)",(source,target,f"Documented rule relationship: {source} may relate to {target}; this is not causal evidence."))

    @staticmethod
    def _rows(conn, sql, args=()):
        cursor = conn.execute(sql, args)
        names = [col[0] for col in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def _fingerprint(self, finding):
        raw = "\x1f".join(str(finding.get(key) or "").strip().upper() for key in ("database_id", "rule_id", "owner", "object_name", "object_type"))
        return hashlib.sha256(raw.encode()).hexdigest()

    def open(self, finding_id, *, actor="operator", source="manual", at=None):
        finding = self.findings.get_finding(int(finding_id))
        now = self.clock() if at is None else float(at)
        fingerprint = self._fingerprint(finding)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id FROM investigations WHERE primary_finding_id=? AND status IN ('OPEN','MONITORING')", (finding_id,)).fetchone()
            if row:
                investigation_id = row[0]
                created = False
            else:
                cursor = conn.execute("INSERT INTO investigations(database_id,primary_finding_id,status,opened_at,updated_at,summary,source,actor,time_window_start,time_window_end,fingerprint) VALUES(?,?,'OPEN',?,?,?,?,?,?,?,?)",
                    (finding["database_id"], finding_id, now, now, str(redact_secrets(str(finding.get("summary") or finding["rule_id"])))[:MAX_TEXT], source, actor, float(finding["first_seen"])-self.window_seconds, float(finding["last_seen"])+self.window_seconds, fingerprint))
                investigation_id = cursor.lastrowid
                conn.execute("INSERT INTO investigation_events(investigation_id,event_type,observed_at,actor,summary,payload_json) VALUES(?,?,?,?,?,?)", (investigation_id,"INVESTIGATION_OPENED",now,actor,"Investigation opened from a Finding.",json.dumps({"source": source})))
                created = True
        self.refresh(int(investigation_id))
        detail = self.get(int(investigation_id))
        detail["created"] = created
        return detail

    def open_manual(self, database_id, finding_id, actor):
        finding = self.findings.get_finding(int(finding_id))
        if finding["database_id"] != database_id:
            raise ValueError("finding_database_mismatch")
        return self.open(finding_id, actor=actor, source="manual")

    def on_reconcile(self, database_id, at=None):
        """Hook called only after a durable Finding reconciliation."""
        now = self.clock() if at is None else float(at)
        recently_changed=self.findings._rows("SELECT id FROM findings WHERE database_id=? AND last_seen>=? ORDER BY last_seen DESC LIMIT ?",(database_id,now-2,MAX_CORRELATION_CANDIDATES))
        changed_ids=[row["id"] for row in recently_changed]
        if changed_ids:
            placeholders=','.join('?' for _ in changed_ids)
            refresh_ids=self._rows_for(f"SELECT id FROM investigations WHERE database_id=? AND status IN ('OPEN','MONITORING') AND primary_finding_id IN ({placeholders}) LIMIT ?",(database_id,*changed_ids,MAX_CORRELATION_CANDIDATES))
        else:
            refresh_ids=[]
        for case in refresh_ids:
            self.refresh(case["id"])
        if not self.auto_open:
            return []
        candidates = self.findings._rows("SELECT * FROM findings WHERE database_id=? AND status!='RESOLVED' AND last_seen>=? AND (severity='CRITICAL' AND delta IN ('WORSENING','REOPENED') OR id IN (SELECT finding_id FROM red_flags WHERE priority='P1' AND status='OPEN')) ORDER BY last_seen DESC LIMIT 50", (database_id, now-2))
        opened = []
        for finding in candidates:
            opened.append(self.open(finding["id"], actor="E13DB", source="automatic", at=now))
        unstable=self.findings._rows("SELECT * FROM red_flags WHERE database_id=? AND finding_id IS NULL AND status='OPEN' AND occurrences>=2 AND flag_type IN ('AUDIT_EXECUTION_FAILURE','DATABASE_UNREACHABLE') ORDER BY updated_at DESC LIMIT 5",(database_id,))
        for flag in unstable:
            opened.append(self.open_database_issue(database_id, flag, at=now))
        return opened

    def open_database_issue(self, database_id, flag, *, at=None):
        now=self.clock() if at is None else float(at)
        identity=hashlib.sha256(f"{database_id}\x1f{flag['flag_type']}".encode()).hexdigest()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing=conn.execute("SELECT id FROM investigations WHERE database_id=? AND fingerprint=? AND status IN ('OPEN','MONITORING')",(database_id,identity)).fetchone()
            if existing:
                return self.get(existing[0])
            summary="Repeated audit execution failure" if flag["flag_type"]=="AUDIT_EXECUTION_FAILURE" else "Repeated database connectivity failure"
            cursor=conn.execute("INSERT INTO investigations(database_id,primary_finding_id,status,opened_at,updated_at,summary,source,actor,time_window_start,time_window_end,fingerprint) VALUES(?,NULL,'OPEN',?,?,?,?,?,?,?,?)",(database_id,now,now,summary,"automatic","E13DB",now-self.window_seconds,now+self.window_seconds,identity))
            investigation_id=cursor.lastrowid
            conn.execute("INSERT INTO investigation_events(investigation_id,event_type,observed_at,actor,summary,payload_json) VALUES(?,?,?,?,?,?)",(investigation_id,"INVESTIGATION_OPENED",now,"E13DB",summary,json.dumps({"red_flag_type":flag["flag_type"],"occurrences":flag["occurrences"]})))
        self.refresh(investigation_id)
        return self.get(investigation_id)

    def list(self, *, database_id=None, status=None, rule=None, category=None, object_name=None, cause=None, opened_from=None, opened_to=None, limit=100, offset=0):
        limit = max(1,min(int(limit),200)); offset=max(0,int(offset))
        filters=[]; args=[]
        if database_id: filters.append("database_id=?"); args.append(database_id)
        if status:
            state = status.upper()
            if state not in {"OPEN","MONITORING","RESOLVED","CLOSED"}: raise ValueError("invalid_investigation_status")
            filters.append("status=?"); args.append(state)
        if rule: filters.append("primary_finding_id IN (SELECT id FROM findings WHERE rule_id=?)"); args.append(str(rule)[:128])
        if category: filters.append("id IN (SELECT investigation_id FROM investigation_evidence WHERE category=?)"); args.append(str(category).upper())
        if object_name: filters.append("primary_finding_id IN (SELECT id FROM findings WHERE object_name LIKE ?)"); args.append("%"+str(object_name)[:100]+"%")
        if cause: filters.append("confirmed_cause LIKE ?"); args.append("%"+str(cause)[:100]+"%")
        if opened_from is not None: filters.append("opened_at>=?"); args.append(float(opened_from))
        if opened_to is not None: filters.append("opened_at<=?"); args.append(float(opened_to))
        where=" WHERE "+" AND ".join(filters) if filters else ""
        with self._connect() as conn:
            rows=self._rows(conn,"SELECT * FROM investigations"+where+" ORDER BY CASE status WHEN 'OPEN' THEN 0 WHEN 'MONITORING' THEN 1 WHEN 'RESOLVED' THEN 2 ELSE 3 END,updated_at DESC LIMIT ? OFFSET ?",(*args,limit,offset))
            total=conn.execute("SELECT COUNT(*) FROM investigations"+where,args).fetchone()[0]
        items=[]
        for row in rows:
            finding = self.findings.get_finding(row["primary_finding_id"]) if row["primary_finding_id"] else None
            hypotheses=self._rows_for("SELECT * FROM investigation_hypotheses WHERE investigation_id=? ORDER BY id",(row["id"],))
            relation=self._rows_for("SELECT category,strength,reasons_json,occurred_at FROM investigation_correlations WHERE investigation_id=? ORDER BY occurred_at DESC LIMIT 1",(row["id"],))
            items.append({**row,"primary_finding":self._finding_summary(finding),"top_hypothesis":hypotheses[0]["title"] if hypotheses else None,"next_recommended_check":self._next_check(row["id"]),"related_findings_count":len(self._rows_for("SELECT id FROM investigation_correlations WHERE investigation_id=?",(row["id"],))),"recent_correlation":({**relation[0],"reasons":_json(relation[0]["reasons_json"],[])} if relation else None)})
        return {"items":items,"total":total,"limit":limit,"offset":offset}

    def _rows_for(self, sql, args=()):
        with self._connect() as conn: return self._rows(conn,sql,args)

    @staticmethod
    def _finding_summary(finding):
        if not finding: return None
        result={key:finding.get(key) for key in ("id","database_id","rule_id","summary","severity","status","delta","first_seen","last_seen","owner","object_name","object_type")}
        result["summary"]=str(redact_secrets(str(result.get("summary") or "")))[:MAX_TEXT]
        return result

    def get(self, investigation_id):
        rows=self._rows_for("SELECT * FROM investigations WHERE id=?",(int(investigation_id),))
        if not rows: raise KeyError(investigation_id)
        row=rows[0]
        primary=self.findings.get_finding(row["primary_finding_id"]) if row["primary_finding_id"] else None
        return {**row,"primary_finding":self._finding_summary(primary),"facts":self.evidence(investigation_id),"timeline":self.timeline(investigation_id),"correlations":self.correlations(investigation_id),"hypotheses":self.hypotheses(investigation_id),"recommended_checks":self.checks(investigation_id),"lock_chain":self.lock_chain(investigation_id),"recurrence":self.recurrence(investigation_id)}

    def evidence(self, investigation_id):
        return self._rows_for("SELECT * FROM investigation_evidence WHERE investigation_id=? ORDER BY observed_at,id LIMIT ?",(int(investigation_id),MAX_EVIDENCE_ROWS))

    def _safe_evidence(self, raw):
        data=_json(raw,{})
        metadata={}
        metrics=[]
        for key,value in list(_walk(data))[:100]:
            clean=_safe_scalar(value)
            if clean is None: continue
            if key in _SAFE_META_KEYS: metadata[key]=clean
            if key in _METRIC_KEYS and isinstance(clean,(int,float)):
                metrics.append((key,clean,metadata.get("unit")))
        return metadata,metrics

    def refresh(self, investigation_id):
        row=self._rows_for("SELECT * FROM investigations WHERE id=?",(int(investigation_id),))
        if not row: raise KeyError(investigation_id)
        case=row[0]; now=self.clock()
        primary=self.findings.get_finding(case["primary_finding_id"]) if case["primary_finding_id"] else None
        if primary:
            case["time_window_start"]=min(float(case["time_window_start"]),float(primary["first_seen"])-self.window_seconds)
            case["time_window_end"]=max(float(case["time_window_end"]),float(primary["last_seen"])+self.window_seconds)
            with self._connect() as conn:
                conn.execute("UPDATE investigations SET time_window_start=?,time_window_end=? WHERE id=?",(case["time_window_start"],case["time_window_end"],int(investigation_id)))
        if primary and case["status"] not in {"CLOSED","RESOLVED"}:
            if primary["status"]=="RESOLVED":
                self.set_status(investigation_id,"RESOLVED",actor="E13DB",at=primary["last_seen"],summary="Primary Finding resolved by a successful audit.")
            elif primary["delta"]=="IMPROVING" and case["status"]=="OPEN":
                self.set_status(investigation_id,"MONITORING",actor="E13DB",at=now,summary="Primary Finding improved; monitor for a sustained recovery.")
        self._sync_evidence(investigation_id,case)
        self._correlate(investigation_id,case)
        self._generate_hypotheses(investigation_id,case)
        self._generate_checks(investigation_id)
        return self.get(investigation_id)

    def _sync_evidence(self, investigation_id, case):
        start=float(case["time_window_start"]); end=float(case["time_window_end"])
        occurrence_rows=self.findings._rows("SELECT o.*,f.database_id,f.rule_id,f.object_type,f.owner,f.object_name FROM finding_occurrences o JOIN findings f ON f.id=o.finding_id WHERE f.database_id=? AND o.observed_at BETWEEN ? AND ? ORDER BY o.observed_at ASC LIMIT ?",(case["database_id"],start,end,MAX_CORRELATION_CANDIDATES*10))
        primary=self.findings.get_finding(case["primary_finding_id"]) if case["primary_finding_id"] else None
        if primary and not any(int(item["finding_id"])==int(primary["id"]) for item in occurrence_rows):
            occurrence_rows.extend(self.findings._rows("SELECT o.*,f.database_id,f.rule_id,f.object_type,f.owner,f.object_name FROM finding_occurrences o JOIN findings f ON f.id=o.finding_id WHERE f.id=? ORDER BY o.observed_at DESC LIMIT 50",(primary["id"],)))
        with self._connect() as conn:
            for occ in occurrence_rows:
                category=classify_evidence(occ["rule_id"],occ.get("summary") or "",occ.get("evidence"))
                metadata,metrics=self._safe_evidence(occ.get("evidence"))
                if not metrics and occ.get("value") is not None:
                    val=_json(occ["value"],occ["value"])
                    if isinstance(val,(int,float)):
                        metrics.append(("finding_value",val,metadata.get("unit")))
                # Facts are safe operator summaries: raw SQL and bind payloads are
                # never copied into this investigation projection.
                summary=str(redact_secrets(str(occ.get("summary") or occ["rule_id"])))[:MAX_TEXT]
                for metric,value,unit in (metrics or [(None,None,None)]):
                    value_json=json.dumps(value) if value is not None else None
                    conn.execute("INSERT OR IGNORE INTO investigation_evidence(investigation_id,database_id,finding_id,occurrence_id,audit_run_id,rule_id,category,observed_at,metric_name,value_json,unit,object_type,owner,object_name,summary,source,sensitivity,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (investigation_id,occ["database_id"],occ["finding_id"],occ["id"],occ["audit_run_id"],occ["rule_id"],category,occ["observed_at"],metric,value_json,unit,occ.get("object_type"),occ.get("owner"),occ.get("object_name"),summary,"finding_occurrence","REDACTED",json.dumps(metadata)))
                self._record_plan_change(conn,investigation_id,occ,metadata,metrics)
            audit_rows=self._rows(conn,"SELECT * FROM audit_runs WHERE database_id=? AND completed_at BETWEEN ? AND ? AND state!='SUCCESS' ORDER BY completed_at LIMIT 100",(case["database_id"],start,end))
            for audit in audit_rows:
                reason="Oracle target audit did not complete successfully; connectivity or execution failure is observed." if audit["state"] != "SUCCESS" else "Audit coverage is incomplete."
                category="CONNECTIVITY" if audit["state"]!="SUCCESS" else "AUDIT_COVERAGE"
                conn.execute("INSERT OR IGNORE INTO investigation_evidence(investigation_id,database_id,audit_run_id,rule_id,category,observed_at,summary,source,sensitivity,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?)",(investigation_id,case["database_id"],audit["audit_run_id"],"AUDIT_RUNTIME",category,audit["completed_at"],reason,"audit_run","REDACTED",json.dumps({"state":audit["state"],"coverage_state":audit["coverage_state"],"checks_error":audit["checks_error"],"checks_skipped":audit["checks_skipped"]})))

    def _record_plan_change(self, conn, investigation_id, occurrence, metadata, metrics):
        sql_id=str(metadata.get("sql_id") or "")[:64]; plan_hash=str(metadata.get("plan_hash") or "")[:64]
        if not sql_id or not plan_hash: return
        database=occurrence["database_id"]; at=float(occurrence["observed_at"])
        prior=conn.execute("SELECT plan_hash FROM investigation_plan_observations WHERE database_id=? AND sql_id=? ORDER BY first_seen DESC,id DESC LIMIT 1",(database,sql_id)).fetchone()
        metric_map={name:value for name,value,_ in metrics}
        conn.execute("INSERT INTO investigation_plan_observations(database_id,sql_id,plan_hash,first_seen,last_seen,metrics_json) VALUES(?,?,?,?,?,?) ON CONFLICT(database_id,sql_id,plan_hash) DO UPDATE SET last_seen=excluded.last_seen,metrics_json=excluded.metrics_json",(database,sql_id,plan_hash,at,at,json.dumps(metric_map)))
        if prior and str(prior[0])!=plan_hash:
            payload={"sql_id":sql_id,"previous_plan_hash":str(prior[0]),"plan_hash":plan_hash}
            conn.execute("INSERT OR IGNORE INTO investigation_evidence(investigation_id,database_id,finding_id,occurrence_id,audit_run_id,rule_id,category,observed_at,metric_name,value_json,summary,source,sensitivity,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(investigation_id,database,"finding_id" in occurrence and occurrence["finding_id"] or None,occurrence["id"],occurrence["audit_run_id"],occurrence["rule_id"],"EXECUTION_PLAN",at,"plan_hash",json.dumps(plan_hash),"Execution plan hash changed for this SQL identifier; this is a plan-change observation only.","plan_hash_observation","REDACTED",json.dumps(payload)))

    def _correlate(self, investigation_id, case):
        primary=self.findings.get_finding(case["primary_finding_id"]) if case["primary_finding_id"] else None
        if not primary: return
        rows=self.findings._rows(f"SELECT f.*,MIN(o.observed_at) AS related_at,MAX(o.observed_at) AS last_related_at FROM findings f JOIN finding_occurrences o ON o.finding_id=f.id WHERE f.database_id=? AND o.observed_at BETWEEN ? AND ? AND f.id!=? GROUP BY f.id ORDER BY ABS(MIN(o.observed_at)-?) LIMIT {MAX_CORRELATION_CANDIDATES}",(case["database_id"],case["time_window_start"],case["time_window_end"],primary["id"],primary["last_seen"]))
        with self._connect() as conn:
            conn.execute("DELETE FROM investigation_correlations WHERE investigation_id=?",(investigation_id,))
            for item in rows:
                reasons=["same database",f"occurred within {int(abs(item['related_at']-primary['last_seen'])/60)} minutes"]
                direct=bool(primary.get("object_name") and item.get("object_name") and primary["object_name"].casefold()==item["object_name"].casefold() and (primary.get("owner") or "").casefold()==(item.get("owner") or "").casefold())
                same_schema=bool(primary.get("owner") and item.get("owner") and primary["owner"].casefold()==item["owner"].casefold())
                primary_meta,related_meta=_json(primary.get("evidence"),{}),_json(item.get("evidence"),{})
                primary_fields={key:value for key,value in _walk(primary_meta)}
                related_fields={key:value for key,value in _walk(related_meta)}
                same_sql=bool(primary_fields.get("sql_id") and related_fields.get("sql_id") and str(primary_fields["sql_id"]).casefold()==str(related_fields["sql_id"]).casefold())
                same_tablespace=bool(primary_fields.get("tablespace") and related_fields.get("tablespace") and str(primary_fields["tablespace"]).casefold()==str(related_fields["tablespace"]).casefold())
                related=self.findings._rows("SELECT category FROM investigation_evidence WHERE investigation_id=? AND finding_id IN (?,?)",(investigation_id,primary["id"],item["id"]))
                cats={entry["category"] for entry in related}
                category=classify_evidence(item["rule_id"],item.get("summary") or "",item.get("evidence"))
                primary_category=classify_evidence(primary["rule_id"],primary.get("summary") or "",primary.get("evidence"))
                relationship,relationship_reason=self._relationship(primary_category,category,primary["rule_id"],item["rule_id"])
                if direct: reasons.append("same schema and object"); strength="DIRECT"
                elif same_sql: reasons.append("same SQL identifier"); strength="STRONG"
                elif same_tablespace: reasons.append("same tablespace"); strength="RELATED"
                elif same_schema: reasons.append("same schema"); strength="STRONG"
                elif relationship: reasons.append(relationship_reason); strength="RELATED"
                else: reasons.append("temporal proximity only; no shared object or rule relationship established"); strength="WEAK"
                conn.execute("INSERT OR REPLACE INTO investigation_correlations(investigation_id,related_finding_id,category,strength,occurred_at,reasons_json) VALUES(?,?,?,?,?,?)",(investigation_id,item["id"],category,strength,item["related_at"],json.dumps(reasons)))

    def declare_rule_relationship(self, source_category, target_category, reason, *, source_rule="", target_rule=""):
        source_category=str(source_category).upper(); target_category=str(target_category).upper()
        known={category for category,_ in _CATEGORY_RULES}
        if source_category not in known or target_category not in known or not str(reason or "").strip():
            raise ValueError("invalid_rule_relationship")
        with self._connect() as conn:
            conn.execute("INSERT INTO investigation_rule_relationships(source_category,target_category,reason,source_rule,target_rule) VALUES(?,?,?,?,?) ON CONFLICT(source_category,target_category,source_rule,target_rule) DO UPDATE SET reason=excluded.reason",(source_category,target_category,str(redact_secrets(str(reason)))[:MAX_TEXT],str(source_rule)[:128],str(target_rule)[:128]))

    def rule_relationships(self):
        return self._rows_for("SELECT source_category,target_category,reason,source_rule,target_rule FROM investigation_rule_relationships ORDER BY source_category,target_category,source_rule,target_rule")

    def _relationship(self, source_category, target_category, source_rule, target_rule):
        with self._connect() as conn:
            row=conn.execute("SELECT reason FROM investigation_rule_relationships WHERE source_category=? AND target_category=? AND (source_rule='' OR source_rule=?) AND (target_rule='' OR target_rule=?) ORDER BY CASE WHEN source_rule!='' THEN 0 ELSE 1 END,CASE WHEN target_rule!='' THEN 0 ELSE 1 END LIMIT 1",(source_category,target_category,source_rule,target_rule)).fetchone()
            if row: return True,str(row[0])
            row=conn.execute("SELECT reason FROM investigation_rule_relationships WHERE source_category=? AND target_category=? AND (source_rule='' OR source_rule=?) AND (target_rule='' OR target_rule=?) LIMIT 1",(target_category,source_category,target_rule,source_rule)).fetchone()
            return (True,str(row[0])) if row else (False,"")

    def _generate_hypotheses(self, investigation_id, case):
        facts=self.evidence(investigation_id)
        categories={item["category"] for item in facts}
        primary=self.findings.get_finding(case["primary_finding_id"]) if case["primary_finding_id"] else None
        hypotheses=[]
        if "PERFORMANCE" in categories and "EXECUTION_PLAN" in categories:
            plan=[x for x in facts if x["category"]=="EXECUTION_PLAN" and ("changed" in x["summary"].lower() or _json(x["metadata_json"],{}).get("previous_plan_hash"))]
            perf=[x for x in facts if x["category"]=="PERFORMANCE"]
            if plan and perf:
                p_at=min(float(x["observed_at"]) for x in plan); f_at=min(float(x["observed_at"]) for x in perf)
                support=[x["id"] for x in plan+perf if x["id"]]
                contradiction=[x["id"] for x in (plan+perf) if (f_at < p_at and x["category"]=="EXECUTION_PLAN")]
                hypotheses.append(("PLAN_CHANGE_MAY_CONTRIBUTE","Execution plan change may be contributing","A plan hash change and a performance-degradation observation overlap this investigation window. Their temporal relationship does not establish causation.",support,contradiction,["Compare current and previous plans for the same SQL identifier.","Compare duration and workload on both plans."]))
        if "PERFORMANCE" in categories and "STATISTICS" in categories:
            stats=[x for x in facts if x["category"]=="STATISTICS" and (_json(x["metadata_json"],{}).get("stale") is True or (_json(x["metadata_json"],{}).get("statistics_age_days") or 0)>=7)]; perf=[x for x in facts if x["category"]=="PERFORMANCE"]
            if stats and perf:
                s_at=min(float(x["observed_at"]) for x in stats); p_at=min(float(x["observed_at"]) for x in perf)
                all_stats=[x for x in facts if x["category"]=="STATISTICS"]
                hypotheses.append(("STATISTICS_MAY_CONTRIBUTE","Statistics state may be contributing","Statistics-state evidence and performance degradation concern this database/time window. Review object overlap and event order; this is not causal proof.",[x["id"] for x in stats+perf if x["id"]],[x["id"] for x in all_stats if p_at<s_at],["Review statistics age/state for affected objects against the normal maintenance policy.","Check whether degradation preceded the observed statistics condition."]))
        if "PERFORMANCE" in categories and "LOCKING" in categories:
            locks=[x for x in facts if x["category"]=="LOCKING"]; perf=[x for x in facts if x["category"]=="PERFORMANCE"]
            l_at=min(float(x["observed_at"]) for x in locks); p_at=min(float(x["observed_at"]) for x in perf)
            hypotheses.append(("BLOCKING_MAY_CONTRIBUTE","Blocking may be contributing to observed performance degradation","Locking and performance evidence overlap in time. Session/object identity and event order should be checked before drawing conclusions.",[x["id"] for x in locks+perf if x["id"]],[x["id"] for x in locks if p_at<l_at],["Review the blocking chain and affected SQL around the slow execution.","Check whether performance degradation predates the blocking observation."]))
        if "CAPACITY" in categories:
            capacity=[x for x in facts if x["category"]=="CAPACITY"]
            hypotheses.append(("CAPACITY_PRESSURE","Capacity pressure may be relevant","Capacity/space observations exist in the investigation window. Compare the affected resource and growth with the primary Finding.",[x["id"] for x in capacity if x["id"]],[],RECOMMENDED_CHECKS["CAPACITY"]))
        now=self.clock()
        with self._connect() as conn:
            for key,title,description,support,contradict,checks in hypotheses:
                existing=conn.execute("SELECT status,updated_by FROM investigation_hypotheses WHERE investigation_id=? AND hypothesis_type=?",(investigation_id,key)).fetchone()
                # Never overwrite an operator disposition with an automated refresh.
                if existing and existing[1]!="E13DB": continue
                status="WEAKENED" if contradict else "SUPPORTED" if support else "POSSIBLE"
                conn.execute("INSERT INTO investigation_hypotheses(investigation_id,hypothesis_type,title,description,supporting_evidence_json,contradicting_evidence_json,status,recommended_checks_json,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?,?,'E13DB') ON CONFLICT(investigation_id,hypothesis_type) DO UPDATE SET title=excluded.title,description=excluded.description,supporting_evidence_json=excluded.supporting_evidence_json,contradicting_evidence_json=excluded.contradicting_evidence_json,status=excluded.status,recommended_checks_json=excluded.recommended_checks_json,updated_at=excluded.updated_at WHERE investigation_hypotheses.updated_by='E13DB'",(investigation_id,key,title,description,json.dumps(support),json.dumps(contradict),status,json.dumps(checks),now))

    def _generate_checks(self, investigation_id):
        categories={row["category"] for row in self.evidence(investigation_id)}
        with self._connect() as conn:
            for category in categories:
                for index,description in enumerate(RECOMMENDED_CHECKS.get(category,()),1):
                    key=f"{category}:{index}"
                    conn.execute("INSERT OR IGNORE INTO investigation_checks(investigation_id,check_key,description,status,updated_at) VALUES(?,?,?,'PENDING',?)",(investigation_id,key,description,self.clock()))

    def _next_check(self, investigation_id):
        rows=self._rows_for("SELECT description FROM investigation_checks WHERE investigation_id=? AND status='PENDING' ORDER BY id LIMIT 1",(investigation_id,))
        return rows[0]["description"] if rows else None

    def checks(self, investigation_id): return self._rows_for("SELECT * FROM investigation_checks WHERE investigation_id=? ORDER BY id",(int(investigation_id),))
    def hypotheses(self, investigation_id):
        rows=self._rows_for("SELECT * FROM investigation_hypotheses WHERE investigation_id=? ORDER BY id",(int(investigation_id),))
        return [{**row,"supporting_evidence":_json(row["supporting_evidence_json"],[]),"contradicting_evidence":_json(row["contradicting_evidence_json"],[]),"recommended_checks":_json(row["recommended_checks_json"],[])} for row in rows]
    def correlations(self, investigation_id):
        rows=self._rows_for("SELECT * FROM investigation_correlations WHERE investigation_id=? ORDER BY CASE strength WHEN 'DIRECT' THEN 0 WHEN 'STRONG' THEN 1 WHEN 'RELATED' THEN 2 ELSE 3 END,occurred_at DESC",(int(investigation_id),))
        result=[]
        for row in rows:
            try: finding=self._finding_summary(self.findings.get_finding(row["related_finding_id"]))
            except KeyError: finding=None
            result.append({**row,"reasons":_json(row["reasons_json"],[]),"finding":finding})
        return result

    def timeline(self, investigation_id):
        cases=self._rows_for("SELECT * FROM investigations WHERE id=?",(int(investigation_id),))
        if not cases: raise KeyError(investigation_id)
        case=cases[0]
        items=[]
        for row in self._rows_for("SELECT e.id,e.observed_at,e.category,e.summary,e.finding_id,e.audit_run_id,e.rule_id FROM investigation_evidence e WHERE e.investigation_id=? ORDER BY e.observed_at LIMIT ?",(int(investigation_id),MAX_EVIDENCE_ROWS)):
            items.append({"type":"FACT","at":row["observed_at"],"summary":row["summary"],"finding_id":row["finding_id"],"audit_run_id":row["audit_run_id"],"rule_id":row["rule_id"],"category":row["category"],"evidence_id":row["id"]})
        for row in self._rows_for("SELECT * FROM investigation_events WHERE investigation_id=? ORDER BY observed_at",(int(investigation_id),)):
            items.append({"type":"EVENT","at":row["observed_at"],"summary":row["summary"],"event_type":row["event_type"],"actor":row["actor"]})
        items.sort(key=lambda x:(x["at"],x["type"]))
        return items

    def set_status(self, investigation_id, status, *, actor, at=None, summary=None):
        status=status.upper()
        if status not in {"OPEN","MONITORING","RESOLVED","CLOSED"}: raise ValueError("invalid_investigation_status")
        now=self.clock() if at is None else float(at)
        with self._connect() as conn:
            row=conn.execute("SELECT status FROM investigations WHERE id=?",(int(investigation_id),)).fetchone()
            if not row: raise KeyError(investigation_id)
            closed=now if status in {"RESOLVED","CLOSED"} else None
            conn.execute("UPDATE investigations SET status=?,updated_at=?,closed_at=? WHERE id=?",(status,now,closed,int(investigation_id)))
            conn.execute("INSERT INTO investigation_events(investigation_id,event_type,observed_at,actor,summary,payload_json) VALUES(?,?,?,?,?,?)",(int(investigation_id),f"STATUS_{status}",now,actor,summary or f"Investigation status changed to {status}.",json.dumps({"previous_status":row[0],"status":status})))
        return self.get(int(investigation_id))

    def confirm_cause(self, investigation_id, *, actor, description, evidence=None):
        if not description or not description.strip(): raise ValueError("cause_description_required")
        now=self.clock(); safe=str(redact_secrets(description.strip()))[:MAX_TEXT]
        safe_evidence=[]
        for item in (evidence or [])[:50]:
            if isinstance(item,dict): safe_evidence.append({str(k):_safe_scalar(v) for k,v in item.items() if str(k).lower() in {"evidence_id","finding_id","audit_run_id","summary","source"}})
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM investigations WHERE id=?",(int(investigation_id),)).fetchone(): raise KeyError(investigation_id)
            for item in safe_evidence:
                if item.get("evidence_id") is not None and not conn.execute("SELECT 1 FROM investigation_evidence WHERE id=? AND investigation_id=?",(int(item["evidence_id"]),int(investigation_id))).fetchone():
                    raise ValueError("cause_evidence_not_in_investigation")
            conn.execute("UPDATE investigations SET confirmed_cause=?,cause_actor=?,cause_at=?,cause_evidence=?,updated_at=? WHERE id=?",(safe,actor,now,json.dumps(safe_evidence),now,int(investigation_id)))
            conn.execute("INSERT INTO investigation_events(investigation_id,event_type,observed_at,actor,summary,payload_json) VALUES(?,?,?,?,?,?)",(int(investigation_id),"CAUSE_CONFIRMED_BY_OPERATOR",now,actor,"Operator recorded a confirmed cause.",json.dumps({"cause":safe})))
        return self.get(int(investigation_id))

    def record_resolution(self, investigation_id, *, actor, resolution, actions_taken=""):
        if not resolution or not resolution.strip(): raise ValueError("resolution_required")
        now=self.clock()
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM investigations WHERE id=?",(int(investigation_id),)).fetchone(): raise KeyError(investigation_id)
            conn.execute("UPDATE investigations SET resolution=?,actions_taken=?,resolved_at=?,resolved_by=?,status='RESOLVED',closed_at=?,updated_at=? WHERE id=?",(str(redact_secrets(resolution.strip()))[:MAX_TEXT],str(redact_secrets(actions_taken))[:MAX_TEXT],now,actor,now,now,int(investigation_id)))
            conn.execute("INSERT INTO investigation_events(investigation_id,event_type,observed_at,actor,summary,payload_json) VALUES(?,?,?,?,?,?)",(int(investigation_id),"RESOLUTION_RECORDED",now,actor,"Operator recorded an investigation resolution.","{}"))
        return self.get(int(investigation_id))

    def update_hypothesis(self, investigation_id, hypothesis_id, *, actor, status):
        status=status.upper()
        if status not in {"POSSIBLE","SUPPORTED","WEAKENED","REJECTED","CONFIRMED_BY_OPERATOR"}: raise ValueError("invalid_hypothesis_status")
        with self._connect() as conn:
            cur=conn.execute("UPDATE investigation_hypotheses SET status=?,updated_at=?,updated_by=? WHERE id=? AND investigation_id=?",(status,self.clock(),actor,int(hypothesis_id),int(investigation_id)))
            if cur.rowcount!=1: raise KeyError(hypothesis_id)
            conn.execute("INSERT INTO investigation_events(investigation_id,event_type,observed_at,actor,summary,payload_json) VALUES(?,?,?,?,?,?)",(int(investigation_id),"HYPOTHESIS_STATUS_UPDATED",self.clock(),actor,"Operator updated a hypothesis status.",json.dumps({"hypothesis_id":int(hypothesis_id),"status":status})))
        return self.get(int(investigation_id))

    def update_check(self, investigation_id, check_id, *, actor, status, result_summary=""):
        status=status.upper()
        if status not in {"PENDING","RUNNING","COMPLETED","NOT_APPLICABLE"}: raise ValueError("invalid_check_status")
        safe=str(redact_secrets(result_summary))[:MAX_TEXT]
        with self._connect() as conn:
            cur=conn.execute("UPDATE investigation_checks SET status=?,result_summary=?,actor=?,updated_at=? WHERE id=? AND investigation_id=?",(status,safe,actor,self.clock(),int(check_id),int(investigation_id)))
            if cur.rowcount!=1: raise KeyError(check_id)
            conn.execute("INSERT INTO investigation_events(investigation_id,event_type,observed_at,actor,summary,payload_json) VALUES(?,?,?,?,?,?)",(int(investigation_id),"RECOMMENDED_CHECK_UPDATED",self.clock(),actor,"Operator updated a recommended check.",json.dumps({"check_id":int(check_id),"status":status})))
        return self.get(int(investigation_id))

    def recurrence(self, investigation_id):
        case_rows=self._rows_for("SELECT * FROM investigations WHERE id=?",(int(investigation_id),))
        if not case_rows: raise KeyError(investigation_id)
        case=case_rows[0]
        rows=self._rows_for("SELECT id,opened_at,closed_at,status,summary,confirmed_cause,cause_actor,resolution,actions_taken FROM investigations WHERE fingerprint=? AND id!=? AND status IN ('RESOLVED','CLOSED') ORDER BY opened_at DESC LIMIT 5",(case["fingerprint"],int(investigation_id)))
        return rows

    def capabilities_status(self):
        return {"engine":"Oracle-first; normalized Finding evidence only","awr":{"available":bool(self.capabilities.get("awr_license") and self.capabilities.get("awr_privilege")),"status":"AVAILABLE" if self.capabilities.get("awr_license") and self.capabilities.get("awr_privilege") else "SKIPPED","reason":"AWR requires explicit license and privilege gates; no AWR queries are run by this investigation engine."},"ash":{"available":bool(self.capabilities.get("ash_license") and self.capabilities.get("ash_privilege")),"status":"AVAILABLE" if self.capabilities.get("ash_license") and self.capabilities.get("ash_privilege") else "SKIPPED","reason":"ASH requires explicit license and privilege gates; no ASH queries are run by this investigation engine."},"sql_execution":"No arbitrary SQL execution is exposed. Recommended checks are operator guidance."}

    def capacity_projection(self, investigation_id, evidence_id):
        valid=self._rows_for("SELECT 1 FROM investigation_evidence WHERE id=? AND investigation_id=? AND category='CAPACITY'",(int(evidence_id),int(investigation_id)))
        if not valid: raise KeyError(evidence_id)
        rows=self._rows_for("SELECT observed_at,value_json,metadata_json FROM investigation_evidence WHERE investigation_id=? AND category='CAPACITY' AND metric_name=? ORDER BY observed_at LIMIT 500",(int(investigation_id),"growth_bytes"))
        samples=[(float(row["observed_at"]),float(_json(row["value_json"],0)),_json(row["metadata_json"],{})) for row in rows if _json(row["value_json"],None) is not None]
        if len(samples)<3: return {"available":False,"reason":"At least three dated growth observations are required."}
        slopes=[(samples[i][1]-samples[i-1][1])/(samples[i][0]-samples[i-1][0]) for i in range(1,len(samples)) if samples[i][0]>samples[i-1][0]]
        if len(slopes)<2 or statistics.mean(slopes)<=0: return {"available":False,"reason":"Recent growth is not consistently positive."}
        mean=statistics.mean(slopes); variation=max(abs(value-mean) for value in slopes)/abs(mean)
        if variation>0.25: return {"available":False,"reason":"Growth observations are unstable; no linear projection is shown."}
        threshold=next((float(item[2]["threshold_value"]) for item in samples if item[2].get("threshold_value") is not None),None)
        latest=samples[-1]
        if threshold is None or threshold<=latest[1]: return {"available":False,"reason":"No future threshold is present in evidence; no time-to-threshold estimate is shown."}
        seconds=(threshold-latest[1])/mean
        return {"available":True,"type":"LINEAR_PROJECTION_BASED_ON_RECENT_OBSERVATIONS","window_start":samples[0][0],"window_end":latest[0],"sample_count":len(samples),"assumption":"Recent positive growth remains approximately linear; this is an extrapolation, not a forecast.","mean_growth_per_second":mean,"threshold":threshold,"projected_threshold_at":latest[0]+seconds}

    def lock_chain(self, investigation_id):
        rows=[row for row in self.evidence(investigation_id) if row["category"]=="LOCKING"]
        edges=[]
        for row in rows:
            metadata=_json(row["metadata_json"],{})
            blocking=metadata.get("blocking_session"); blocked=metadata.get("blocked_session")
            if blocking is not None and blocked is not None: edges.append({"blocking_session":blocking,"blocked_session":blocked,"observed_at":row["observed_at"],"evidence_id":row["id"]})
        return edges[:50]
