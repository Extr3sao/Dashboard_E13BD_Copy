"""One durable AuditRun/RuleResult authority for manual and scheduled runs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from typing import Any

from src.api.check_engine import RuleStatus, redact_evidence

CAPABILITY_SCHEMA = "ORACLE_CAPABILITY_SNAPSHOT_V1"
AUDIT_SCHEMA_VERSION = "1"
PROBE_VIEWS = {
    "BASE_DICTIONARY": "dual",
    "SESSION_VISIBILITY": "v$session",
    "LOCK_VISIBILITY": "v$lock",
    "SQL_VISIBILITY": "v$sql",
    "SQL_PLAN_VISIBILITY": "v$sql_plan",
    "STATISTICS_VISIBILITY": "dba_tab_statistics",
    "SEGMENT_VISIBILITY": "dba_segments",
    "STORAGE_VISIBILITY": "dba_tablespaces",
    "CDB_VISIBILITY": "v$containers",
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json(value,default):
    if value is None or value=="": return default
    try: return value if isinstance(value,(dict,list)) else json.loads(value)
    except (TypeError,json.JSONDecodeError): return default


def runtime_identity(environ=None):
    env=os.environ if environ is None else environ
    return {"application":"E13DB","application_version":str(env.get("E13DB_APP_VERSION") or "UNKNOWN"),"git_sha":str(env.get("E13DB_GIT_SHA") or "UNKNOWN"),"schema_version":AUDIT_SCHEMA_VERSION}


def classify_failure(error, *, stage="audit"):
    text=str(error or "").lower()
    if any(token in text for token in ("timeout","timed out","ora-12170")): return "TIMEOUT"
    if any(token in text for token in ("ora-01017","invalid username","authentication")): return "AUTHENTICATION_FAILED"
    if any(token in text for token in ("ora-01031","insufficient privilege","permission denied")): return "INSUFFICIENT_PRIVILEGES"
    if any(token in text for token in ("ora-12541","connection refused","unreachable","connection reset")): return "UNREACHABLE"
    if "ora-" in text or "query" in text: return "QUERY_ERROR"
    if stage in {"configuration","profile"}: return "CONFIGURATION_ERROR"
    if stage=="storage": return "STORAGE_ERROR"
    return "INTERNAL_ERROR"


def _sanitize_rule_result(item):
    status=str(item.get("status") or "ERROR").upper()
    if status not in {value.value for value in RuleStatus}:
        status="ERROR"
    metrics=item.get("metrics") or {}
    # Keep normalized numeric/text metrics and column names only; never persist
    # query text, bind values, or arbitrary fetched row payloads in RuleResults.
    safe_metrics={}
    for key,value in list(metrics.items())[:100]:
        if str(key).lower() in {"value","duration_ms","row_count","execution_count","elapsed_seconds","buffer_gets","disk_reads","rows_processed","used_percent","free_bytes","used_bytes","wait_seconds","statistics_age_days","comparison_direction"} and isinstance(value,(str,int,float,bool,type(None))):
            safe_metrics[str(key)[:80]]=redact_evidence(value)
    evidence=redact_evidence(item.get("evidence") or {})
    if isinstance(evidence,dict):
        evidence={str(key)[:80]:redact_evidence(value) for key,value in evidence.items() if str(key).lower() in {"row_count","columns","elapsed_seconds","duration_seconds","execution_count","buffer_gets","disk_reads","rows_processed","used_percent","free_bytes","used_bytes","wait_seconds","statistics_age_days","sql_id","plan_hash","previous_plan_hash","tablespace","segment_name","owner","object_name","object_type","blocking_session","blocked_session","session_id","last_analyzed","stale","threshold","threshold_value","unit","metric_name","source_view","capability"}}
    return {"rule_id":str(item.get("rule_id") or "UNKNOWN")[:128],"database_id":str(item.get("database_id") or "UNKNOWN")[:200],"rule_version":str(item.get("rule_version") or "UNKNOWN")[:128],"definition_hash":str(item.get("definition_hash") or "")[:128],"status":status,"severity":str(item.get("severity") or "LOW")[:32],"started_at":float(item.get("started_at") or 0),"finished_at":float(item.get("finished_at") or 0),"duration":max(0.0,float(item.get("duration") or 0)),"summary":str(redact_evidence(str(item.get("summary") or "")))[:500],"metrics":safe_metrics,"evidence":evidence,"error":redact_evidence(str(item.get("error") or ""))[:500] if item.get("error") else None,"object_type":str(item.get("object_type") or "")[:128],"owner":str(item.get("owner") or "")[:128],"object_name":str(item.get("object_name") or "")[:256],"recommendation":str(redact_evidence(str(item.get("recommendation") or "")))[:500],"coverage_meaning":str(item.get("coverage_meaning") or ("not_evaluated" if status=="SKIPPED" else "evaluation_error" if status=="ERROR" else "evaluated"))[:64]}


def _safe_envelope(item, result_index):
    allowed={"finding_id","check_id","title","schema","object_name","object_type","sql_severity","runtime_status","evidence","final_criticality","final_criticality_label","row_index","lot_assignment"}
    result={}
    for key in allowed:
        if key not in item: continue
        value=item[key]
        if key=="evidence":
            value=redact_evidence(value)
            if isinstance(value,dict):
                value={str(k)[:80]:v for k,v in value.items() if str(k).lower() not in {"rows","source_row","sql_text","executed_sql","sql_binds","bind_values","password","token","credential"}}
        elif isinstance(value,str): value=str(redact_evidence(value))[:500]
        elif key=="lot_assignment" and isinstance(value,dict): value={k:v for k,v in value.items() if k in {"lot","source","confidence"}}
        result[key]=value
    result["row_index"]=int(item.get("row_index",result_index))
    return result


def discover_oracle_capabilities(db_manager, database_id, *, license_flags=None, required_privileges=(), timeout_ms=2000):
    """Read-only allow-listed metadata probes; AWR/ASH are never queried here."""
    flags=license_flags or {}
    status={name:"UNKNOWN" for name in PROBE_VIEWS}
    reasons={name:"Discovery not completed." for name in PROBE_VIEWS}
    version="UNKNOWN"; connection_status="UNAVAILABLE"; available_privileges=[]; privilege_discovery_status="NOT_REQUIRED" if not required_privileges else "UNKNOWN"
    if db_manager is not None and hasattr(db_manager,"connect"):
        try:
            connected=bool(getattr(db_manager,"connection",None)) or bool(db_manager.connect())
            connection=getattr(db_manager,"connection",None)
            if connected and connection is not None:
                connection_status="AVAILABLE"
                version=str(getattr(connection,"version",None) or "UNKNOWN")[:128]
                previous_timeout=getattr(connection,"call_timeout",None)
                try:
                    if hasattr(connection,"call_timeout"): connection.call_timeout=min(int(previous_timeout or timeout_ms),int(timeout_ms))
                    for name,view in PROBE_VIEWS.items():
                        query="SELECT 1 FROM dual WHERE 1=0" if name=="BASE_DICTIONARY" else f"SELECT 1 FROM {view} WHERE 1=0"
                        try:
                            with connection.cursor() as cursor: cursor.execute(query)
                            status[name]="AVAILABLE"; reasons[name]="Read-only zero-row metadata probe succeeded."
                        except Exception as exc:
                            text=str(exc).upper()
                            status[name]="INSUFFICIENT_PRIVILEGES" if "ORA-01031" in text else "UNKNOWN"
                            reasons[name]="Required dictionary view is not accessible or its privilege is unknown."
                    required={str(value).upper() for value in required_privileges if value}
                    if required:
                        try:
                            binds={f"p{i}":value for i,value in enumerate(sorted(required))}
                            slots=",".join(f":p{i}" for i in range(len(binds)))
                            with connection.cursor() as cursor:
                                cursor.execute(f"SELECT PRIVILEGE FROM SESSION_PRIVS WHERE PRIVILEGE IN ({slots})",binds)
                                available_privileges=sorted(str(row[0]).upper() for row in cursor.fetchall())
                            privilege_discovery_status="AVAILABLE"
                        except Exception:
                            # Do not infer missing privileges from an unreadable
                            # catalog; preserve UNKNOWN rather than false denial.
                            available_privileges=[]
                finally:
                    if hasattr(connection,"call_timeout"):
                        try: connection.call_timeout=previous_timeout
                        except Exception: pass
        except Exception:
            connection_status="UNAVAILABLE"
    if connection_status!="AVAILABLE":
        for name in status:
            status[name]="UNAVAILABLE"
            reasons[name]="Oracle connection was unavailable during capability discovery."
    awr_license=bool(flags.get("awr_license")); awr_privilege=bool(flags.get("awr_privilege"))
    ash_license=bool(flags.get("ash_license")); ash_privilege=bool(flags.get("ash_privilege"))
    status["AWR_ALLOWED"]="NOT_LICENSED" if not awr_license else "INSUFFICIENT_PRIVILEGES" if not awr_privilege else "AVAILABLE"
    status["ASH_ALLOWED"]="NOT_LICENSED" if not ash_license else "INSUFFICIENT_PRIVILEGES" if not ash_privilege else "AVAILABLE"
    reasons["AWR_ALLOWED"]="AWR/ASH queries are not executed by this audit runner; license and privilege flags only describe the configured gate."
    reasons["ASH_ALLOWED"]=reasons["AWR_ALLOWED"]
    return {"schema":"ORACLE_CAPABILITY_SNAPSHOT_V1","database_id":str(database_id),"engine":"oracle","engine_version":version,"connection_status":connection_status,"capabilities":status,"reasons":reasons,"required_privileges":sorted(str(value).upper() for value in required_privileges if value),"available_privileges":available_privileges,"privilege_discovery_status":privilege_discovery_status,"license_gates":{"awr_allowed":awr_license,"awr_privilege_declared":awr_privilege,"ash_allowed":ash_license,"ash_privilege_declared":ash_license},"probe_policy":"allow-listed SELECT zero-row probes; AWR/ASH never queried"}


def rule_pack_identity(definitions):
    material=sorted(({"rule_id":rule.rule_id,"version":rule.version,"definition_hash":rule.definition_hash,"required_privileges":sorted(rule.required_privileges),"required_capabilities":sorted(rule.required_capabilities),"license_requirements":sorted(rule.license_requirements)} for rule in definitions),key=lambda item:item["rule_id"])
    return hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()


def rule_capability_skip_reason(definition, snapshot, license_flags=None):
    """Return an explicit reason when the stored run snapshot cannot satisfy a rule."""
    cap_status=snapshot.get("capabilities") or {}
    missing=[str(name) for name in definition.required_capabilities if cap_status.get(str(name),"UNKNOWN")!="AVAILABLE"]
    if missing:
        states=sorted({cap_status.get(name,"UNKNOWN") for name in missing})
        return f"CAPABILITY_{states[0]}:"+",".join(missing)
    available={str(value).upper() for value in snapshot.get("available_privileges",[])}
    privileges=[str(value).upper() for value in definition.required_privileges]
    denied=[value for value in privileges if value not in available]
    if denied and snapshot.get("privilege_discovery_status")!="AVAILABLE": return "CAPABILITY_UNKNOWN_PRIVILEGE_DISCOVERY"
    if denied: return "INSUFFICIENT_PRIVILEGES:"+",".join(denied)
    flags=license_flags or {}
    denied_license=[]
    for requirement in definition.license_requirements:
        name=str(requirement).strip().lower()
        env_key=name if name in flags else f"{name}_license"
        if not flags.get(env_key,False): denied_license.append(str(requirement))
    return "NOT_LICENSED:"+",".join(denied_license) if denied_license else ""


class AuditEvidenceError(RuntimeError): pass


class AuditEvidenceService:
    """Durable audit execution, results, capability snapshots and reconciliation."""
    def __init__(self, internal_db, finding_store, alerting_service, *, runtime=None, clock=time.time):
        self.db=internal_db; self.findings=finding_store; self.alerts=alerting_service
        self.runtime=runtime or runtime_identity(); self.clock=clock
        self._migrate()

    def _connect(self): return self.db._get_connection()

    @staticmethod
    def scheduled_identity(job_id, scheduled_reference):
        material=f"scheduled-post-crq\x1f{int(job_id)}\x1f{str(scheduled_reference)}"
        return "AUD-SCH-"+hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]

    @staticmethod
    def sanitize_target_context(value):
        if not isinstance(value,dict) or not value: return {}
        tags=value.get("tags",[])
        return redact_evidence({
            "environment":str(value.get("environment") or "development")[:80],
            "criticality":str(value.get("criticality") or "medium")[:40],
            "owner":str(value.get("owner") or "")[:160],
            "tags":[str(tag)[:80] for tag in tags[:32]] if isinstance(tags,list) else [],
        })

    def _migrate(self):
        with self._connect() as conn:
            columns={row[1] for row in conn.execute("PRAGMA table_info(audit_runs)")}
            for name,ddl in {
                "trigger_type":"trigger_type TEXT NOT NULL DEFAULT 'LEGACY'",
                "trigger_reference":"trigger_reference TEXT",
                "runtime_identity_json":"runtime_identity_json TEXT NOT NULL DEFAULT '{}'",
                "rule_pack_identity":"rule_pack_identity TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "capability_snapshot_id":"capability_snapshot_id TEXT",
                "reconciliation_state":"reconciliation_state TEXT NOT NULL DEFAULT 'LEGACY'",
                "reconciliation_started_at":"reconciliation_started_at REAL",
                "reconciled_at":"reconciled_at REAL",
                "attempt_count":"attempt_count INTEGER NOT NULL DEFAULT 0",
                "failure_class":"failure_class TEXT",
                "target_context_json":"target_context_json TEXT NOT NULL DEFAULT '{}'",
            }.items():
                if name not in columns: conn.execute(f"ALTER TABLE audit_runs ADD COLUMN {ddl}")
            conn.executescript("""
              CREATE TABLE IF NOT EXISTS capability_snapshots(
                snapshot_id TEXT PRIMARY KEY,database_id TEXT NOT NULL,engine TEXT NOT NULL,
                engine_version TEXT NOT NULL,status TEXT NOT NULL,snapshot_hash TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,created_at REAL NOT NULL);
              CREATE INDEX IF NOT EXISTS idx_capability_snapshot_target ON capability_snapshots(database_id,created_at DESC);
              CREATE TABLE IF NOT EXISTS audit_attempts(
                audit_run_id TEXT NOT NULL,attempt_no INTEGER NOT NULL,attempt_id TEXT NOT NULL UNIQUE,
                trigger_type TEXT NOT NULL,status TEXT NOT NULL,started_at REAL NOT NULL,finished_at REAL,
                failure_class TEXT,reason TEXT,PRIMARY KEY(audit_run_id,attempt_no));
              CREATE TABLE IF NOT EXISTS rule_results(
                audit_run_id TEXT NOT NULL,attempt_no INTEGER NOT NULL,rule_id TEXT NOT NULL,
                rule_version TEXT NOT NULL,definition_hash TEXT NOT NULL,status TEXT NOT NULL,severity TEXT NOT NULL,
                started_at REAL NOT NULL,finished_at REAL NOT NULL,duration REAL NOT NULL,summary TEXT NOT NULL,
                metrics_json TEXT NOT NULL,evidence_json TEXT NOT NULL,error_json TEXT,coverage_meaning TEXT NOT NULL,
                object_type TEXT,owner TEXT,object_name TEXT,recommendation TEXT NOT NULL,
                PRIMARY KEY(audit_run_id,attempt_no,rule_id));
              CREATE INDEX IF NOT EXISTS idx_rule_results_audit_status ON rule_results(audit_run_id,attempt_no,status);
              CREATE TABLE IF NOT EXISTS audit_rule_evidence(
                audit_run_id TEXT NOT NULL,attempt_no INTEGER NOT NULL,rule_id TEXT NOT NULL,evidence_index INTEGER NOT NULL,
                database_id TEXT NOT NULL,envelope_json TEXT NOT NULL,evidence_hash TEXT NOT NULL,
                PRIMARY KEY(audit_run_id,attempt_no,rule_id,evidence_index));
              CREATE INDEX IF NOT EXISTS idx_audit_evidence_run ON audit_rule_evidence(audit_run_id,attempt_no);
              CREATE TABLE IF NOT EXISTS audit_reconciliation_receipts(
                audit_run_id TEXT PRIMARY KEY,receipt_id TEXT NOT NULL UNIQUE,input_hash TEXT NOT NULL,
                status TEXT NOT NULL,attempt_count INTEGER NOT NULL DEFAULT 0,started_at REAL NOT NULL,
                completed_at REAL,result_json TEXT NOT NULL DEFAULT '{}',error_class TEXT);
              CREATE TABLE IF NOT EXISTS notification_outbox(
                id INTEGER PRIMARY KEY AUTOINCREMENT,delivery_key TEXT NOT NULL UNIQUE,target_type TEXT NOT NULL,
                target_id INTEGER NOT NULL,channel TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,updated_at REAL NOT NULL,attempt_started_at REAL,completed_at REAL,
                recipient_fingerprint TEXT NOT NULL DEFAULT '',error_class TEXT,reason TEXT);
              CREATE INDEX IF NOT EXISTS idx_notification_outbox_status ON notification_outbox(status,created_at);
            """)
            conn.execute("UPDATE audit_runs SET reconciliation_state='RECONCILED' WHERE reconciliation_state='LEGACY' AND audit_run_id IN (SELECT audit_run_id FROM finding_reconciliation_receipts)")

    @staticmethod
    def _rows(conn,sql,args=()):
        cursor=conn.execute(sql,args); names=[column[0] for column in cursor.description]
        return [dict(zip(names,row)) for row in cursor.fetchall()]

    def begin(self, audit_run_id, database_id, *, trigger_type, trigger_reference="", target_context=None):
        audit_run_id=str(audit_run_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}",audit_run_id): raise ValueError("invalid_audit_run_id")
        now=float(self.clock()); trigger_type=str(trigger_type).upper()
        if trigger_type not in {"MANUAL","SCHEDULED"}: raise ValueError("invalid_trigger_type")
        runtime=_canonical(self.runtime); context=self.sanitize_target_context(target_context)
        trigger_reference=str(redact_evidence(str(trigger_reference or "")))[:240]
        if not context:
            saved_context=self.findings._rows("SELECT environment,criticality,owner,tags FROM target_contexts WHERE database_id=?",(database_id,))
            if saved_context:
                context={"environment":saved_context[0]["environment"],"criticality":saved_context[0]["criticality"],"owner":saved_context[0]["owner"],"tags":_json(saved_context[0]["tags"],[])}
        existing=self.findings._rows("SELECT database_id FROM audit_runs WHERE audit_run_id=?",(audit_run_id,))
        if existing and existing[0]["database_id"]!=database_id: raise ValueError("audit_run_target_mismatch")
        if context: self.findings.set_target_context(database_id,environment=context.get("environment","development"),criticality=context.get("criticality","medium"),owner=context.get("owner", ""),tags=context.get("tags",[]) if isinstance(context.get("tags",[]),list) else [])
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row=conn.execute("SELECT database_id,state,reconciliation_state,attempt_count FROM audit_runs WHERE audit_run_id=?",(audit_run_id,)).fetchone()
            if row and row[0]!=database_id: raise ValueError("audit_run_target_mismatch")
            if row and row[1]=="SUCCESS" and row[2]=="RECONCILED":
                return {"audit_run_id":audit_run_id,"attempt_no":row[3],"already_reconciled":True,"needs_reconciliation":False,"started_at":now}
            if row and row[1]=="SUCCESS" and row[2] in {"PENDING","RECONCILING"}:
                return {"audit_run_id":audit_run_id,"attempt_no":row[3],"already_reconciled":False,"needs_reconciliation":True,"started_at":now}
            if row and row[1]=="RUNNING":
                raise AuditEvidenceError("audit_run_in_progress")
            attempt_no=(int(row[3])+1) if row else 1
            attempt_id=f"{audit_run_id}:attempt:{attempt_no}"
            if row:
                conn.execute("UPDATE audit_runs SET state='RUNNING',started_at=?,completed_at=?,duration_seconds=0,reconciliation_state='RUNNING',attempt_count=?,trigger_type=?,trigger_reference=?,runtime_identity_json=?,target_context_json=? WHERE audit_run_id=?",(now,now,attempt_no,trigger_type,trigger_reference,runtime,_canonical(context),audit_run_id))
            else:
                conn.execute("INSERT INTO audit_runs(audit_run_id,database_id,state,started_at,completed_at,duration_seconds,checks_total,checks_pass,checks_warn,checks_fail,checks_error,checks_skipped,coverage_state,trigger_type,trigger_reference,runtime_identity_json,reconciliation_state,attempt_count,target_context_json) VALUES(?,?,'RUNNING',?,?,0,0,0,0,0,0,0,'UNKNOWN',?,?,?,?,?,?)",(audit_run_id,database_id,now,now,trigger_type,trigger_reference,runtime,"RUNNING",attempt_no,_canonical(context)))
            conn.execute("INSERT INTO audit_attempts(audit_run_id,attempt_no,attempt_id,trigger_type,status,started_at) VALUES(?,?,?,?,'RUNNING',?)",(audit_run_id,attempt_no,attempt_id,trigger_type,now))
        return {"audit_run_id":audit_run_id,"attempt_no":attempt_no,"attempt_id":attempt_id,"already_reconciled":False,"needs_reconciliation":False,"started_at":now}

    def fail(self,audit_run_id,attempt_no,failure_class,reason=""):
        now=float(self.clock()); safe=str(redact_evidence(str(reason)))[:500]
        with self._connect() as conn:
            conn.execute("UPDATE audit_runs SET state='FAILED',completed_at=?,failure_class=?,reconciliation_state='FAILED' WHERE audit_run_id=?",(now,failure_class,audit_run_id))
            conn.execute("UPDATE audit_attempts SET status='FAILED',finished_at=?,failure_class=?,reason=? WHERE audit_run_id=? AND attempt_no=?",(now,failure_class,safe,audit_run_id,attempt_no))
        run=self.findings._rows("SELECT database_id FROM audit_runs WHERE audit_run_id=?",(audit_run_id,))
        if run:
            result=self.findings.reconcile(run[0]["database_id"],[],audit_run_id=audit_run_id,audit_state="FAILED",observed_at=now)
            self.alerts.evaluate(run[0]["database_id"],now=now)
        return {"audit_run_id":audit_run_id,"state":"FAILED","failure_class":failure_class,"reason":safe}

    def _store_capability_snapshot(self, conn, database_id, snapshot):
        snapshot=redact_evidence(snapshot); material={key:value for key,value in snapshot.items() if key not in {"observed_at","created_at"}}
        digest=_digest(material); snapshot_id=f"CAP-{digest[:24]}"
        conn.execute("INSERT OR IGNORE INTO capability_snapshots(snapshot_id,database_id,engine,engine_version,status,snapshot_hash,snapshot_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(snapshot_id,database_id,str(snapshot.get("engine") or "UNKNOWN"),str(snapshot.get("engine_version") or "UNKNOWN"),str(snapshot.get("connection_status") or "UNKNOWN"),digest,_canonical(snapshot),float(self.clock())))
        return snapshot_id,digest

    def persist_completed(self,audit_run_id,attempt_no,report,*,target_context=None):
        if target_context is None:
            saved=self.findings._rows("SELECT target_context_json FROM audit_runs WHERE audit_run_id=?",(audit_run_id,))
            target_context=_json(saved[0]["target_context_json"],{}) if saved else {}
        else: target_context=self.sanitize_target_context(target_context)
        results=[_sanitize_rule_result(item) for item in (report.get("rule_results") or [])]
        snapshot=report.get("capability_snapshot") or {"schema":CAPABILITY_SCHEMA,"database_id":report.get("context",{}).get("profile"),"engine":"oracle","engine_version":"UNKNOWN","connection_status":"UNKNOWN","capabilities":{},"reasons":{"snapshot":"not captured"}}
        database_id=str(report.get("context",{}).get("profile") or snapshot.get("database_id") or "UNKNOWN")
        report_trigger=str(report.get("trigger_type") or "MANUAL").upper()
        if report_trigger not in {"MANUAL","SCHEDULED"}: report_trigger="MANUAL"
        report_reference=str(redact_evidence(str(report.get("trigger_reference") or "")))[:240]
        existing=self.findings._rows("SELECT database_id FROM audit_runs WHERE audit_run_id=?",(audit_run_id,))
        if existing and existing[0]["database_id"]!=database_id: raise ValueError("audit_run_target_mismatch")
        evidence_by_rule={}
        for item in (report.get("finding_envelopes") or []):
            safe=_safe_finding_envelope(item)
            evidence_by_rule.setdefault(str(safe.get("check_id") or "UNKNOWN"),[]).append(safe)
        rule_pack=str(report.get("rule_pack_identity") or _digest(sorted((item["rule_id"],item["rule_version"],item["definition_hash"]) for item in results)))
        now=float(self.clock()); status_counts={status:sum(item["status"]==status for item in results) for status in ("PASS","WARN","FAIL","ERROR","SKIPPED")}
        total=len(results); evaluated=status_counts["PASS"]+status_counts["WARN"]+status_counts["FAIL"]
        coverage="FULL" if total and evaluated==total else "PARTIAL" if evaluated else "UNKNOWN"
        if status_counts["ERROR"] or status_counts["SKIPPED"]: coverage="DEGRADED" if evaluated==0 else "PARTIAL"
        snapshot_hash=None
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            snapshot_id,snapshot_hash=self._store_capability_snapshot(conn,database_id,snapshot)
            for result in results:
                conn.execute("INSERT OR REPLACE INTO rule_results(audit_run_id,attempt_no,rule_id,rule_version,definition_hash,status,severity,started_at,finished_at,duration,summary,metrics_json,evidence_json,error_json,coverage_meaning,object_type,owner,object_name,recommendation) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (audit_run_id,attempt_no,result["rule_id"],result["rule_version"],result["definition_hash"],result["status"],result["severity"],result["started_at"],result["finished_at"],result["duration"],result["summary"],_canonical(result["metrics"]),_canonical(result["evidence"]),_canonical(result["error"]) if result["error"] else None,result["coverage_meaning"],result["object_type"],result["owner"],result["object_name"],result["recommendation"]))
            for rule_id,envelopes in evidence_by_rule.items():
                for index,envelope in enumerate(envelopes):
                    raw=_canonical(envelope); conn.execute("INSERT OR REPLACE INTO audit_rule_evidence(audit_run_id,attempt_no,rule_id,evidence_index,database_id,envelope_json,evidence_hash) VALUES(?,?,?,?,?,?,?)",(audit_run_id,attempt_no,rule_id,index,database_id,raw,_digest(envelope)))
            existing=conn.execute("SELECT started_at FROM audit_runs WHERE audit_run_id=?",(audit_run_id,)).fetchone()
            started=float(existing[0]) if existing else now
            conn.execute("UPDATE audit_runs SET database_id=?,state='SUCCESS',started_at=?,completed_at=?,duration_seconds=?,checks_total=?,checks_pass=?,checks_warn=?,checks_fail=?,checks_error=?,checks_skipped=?,coverage_state=?,coverage_ratio=?,trigger_type=?,trigger_reference=?,runtime_identity_json=?,rule_pack_identity=?,capability_snapshot_id=?,reconciliation_state='PENDING',target_context_json=? WHERE audit_run_id=?",
                (database_id,started,now,max(0,now-started),total,status_counts["PASS"],status_counts["WARN"],status_counts["FAIL"],status_counts["ERROR"],status_counts["SKIPPED"],coverage,evaluated/total if total else None,report_trigger,report_reference,_canonical(report.get("runtime_identity") or self.runtime),rule_pack,snapshot_id,_canonical(redact_evidence(target_context or {})),audit_run_id))
            conn.execute("UPDATE audit_attempts SET status='COMPLETED',finished_at=? WHERE audit_run_id=? AND attempt_no=?",(now,audit_run_id,attempt_no))
        return {"audit_run_id":audit_run_id,"capability_snapshot_id":snapshot_id,"capability_snapshot_hash":snapshot_hash,"rule_pack_identity":rule_pack,"coverage_state":coverage,"reconciliation_state":"PENDING","rule_result_count":total,"rule_result_counts":status_counts,"input_hash":_digest({"audit_run_id":audit_run_id,"results":results,"envelopes":evidence_by_rule,"capability_snapshot_hash":snapshot_hash,"rule_pack_identity":rule_pack})}

    def complete_and_reconcile(self,audit_run_id,attempt_no,report,*,target_context=None):
        if target_context is not None: target_context=self.sanitize_target_context(target_context)
        persisted=self.persist_completed(audit_run_id,attempt_no,report,target_context=target_context)
        reconciled=self.reconcile(audit_run_id)
        return {**persisted,**reconciled}

    def reconcile(self,audit_run_id):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows=self._rows(conn,"SELECT * FROM audit_runs WHERE audit_run_id=?",(audit_run_id,))
            if not rows: raise KeyError(audit_run_id)
            row=rows[0]
            receipt=conn.execute("SELECT status,result_json FROM audit_reconciliation_receipts WHERE audit_run_id=?",(audit_run_id,)).fetchone()
            if receipt and receipt[0]=="RECONCILED": return {**_json(receipt[1],{}),"reconciliation_state":"RECONCILED"}
            attempt_no=int(row["attempt_count"] or 1)
            result_rows=self._rows(conn,"SELECT * FROM rule_results WHERE audit_run_id=? AND attempt_no=? ORDER BY rule_id",(audit_run_id,attempt_no))
            evidence_rows=self._rows(conn,"SELECT envelope_json FROM audit_rule_evidence WHERE audit_run_id=? AND attempt_no=? ORDER BY rule_id,evidence_index",(audit_run_id,attempt_no))
            started=float(self.clock())
            input_hash=_digest({"audit_run_id":audit_run_id,"rules":[{key:item[key] for key in ("rule_id","rule_version","definition_hash","status","severity","summary","metrics_json","evidence_json")} for item in result_rows],"evidence":[item["envelope_json"] for item in evidence_rows],"capability_snapshot_id":row["capability_snapshot_id"],"rule_pack_identity":row["rule_pack_identity"]})
            if receipt:
                conn.execute("UPDATE audit_reconciliation_receipts SET input_hash=?,status='RECONCILING',attempt_count=attempt_count+1,started_at=?,completed_at=NULL,error_class=NULL WHERE audit_run_id=?",(input_hash,started,audit_run_id))
            else:
                conn.execute("INSERT INTO audit_reconciliation_receipts(audit_run_id,receipt_id,input_hash,status,attempt_count,started_at) VALUES(?,?,?,'RECONCILING',1,?)",(audit_run_id,f"RECON-{uuid.uuid4().hex}",input_hash,started))
            conn.execute("UPDATE audit_runs SET reconciliation_state='RECONCILING',reconciliation_started_at=? WHERE audit_run_id=?",(started,audit_run_id))
            rules=[]
            for item in result_rows:
                rules.append({"rule_id":item["rule_id"],"database_id":row["database_id"],"status":item["status"],"severity":item["severity"],"summary":item["summary"],"recommendation":item["recommendation"],"metrics":json.loads(item["metrics_json"] or "{}"),"evidence":json.loads(item["evidence_json"] or "{}"),"definition_hash":item["definition_hash"],"rule_version":item["rule_version"],"duration":item["duration"],"started_at":item["started_at"],"finished_at":item["finished_at"]})
            envelopes=[json.loads(item["envelope_json"]) for item in evidence_rows]
            target_context=json.loads(row["target_context_json"] or "{}")
            report={"audit_type":"post_crq","audit_run_id":audit_run_id,"rule_results":rules,"finding_envelopes":envelopes,"context":{"profile":row["database_id"]}}
        try:
            operational=self.findings.reconcile_post_crq(report,target_context=target_context,audit_run_id=audit_run_id)
            new_alerts=self.alerts.evaluate(row["database_id"])
            summary={"audit_run_id":audit_run_id,"findings":operational.get("findings"),"red_flags":operational.get("red_flags"),"coverage_valid":operational.get("coverage_valid"),"alerts_created":len(new_alerts),"reconciliation_state":"RECONCILED"}
            completed=float(self.clock())
            with self._connect() as conn:
                conn.execute("UPDATE audit_reconciliation_receipts SET status='RECONCILED',completed_at=?,result_json=? WHERE audit_run_id=?",(completed,_canonical(summary),audit_run_id))
                conn.execute("UPDATE audit_runs SET reconciliation_state='RECONCILED',reconciled_at=? WHERE audit_run_id=?",(completed,audit_run_id))
            return summary
        except Exception as exc:
            with self._connect() as conn:
                conn.execute("UPDATE audit_reconciliation_receipts SET status='FAILED',completed_at=?,error_class='RECONCILIATION_ERROR' WHERE audit_run_id=?",(float(self.clock()),audit_run_id))
                conn.execute("UPDATE audit_runs SET reconciliation_state='PENDING',failure_class='RECONCILIATION_ERROR' WHERE audit_run_id=?",(audit_run_id,))
            raise AuditEvidenceError("audit_reconciliation_failed") from exc

    def recover_pending_reconciliations(self,limit=100):
        rows=self.findings._rows("SELECT audit_run_id FROM audit_runs WHERE state='SUCCESS' AND reconciliation_state IN ('PENDING','RECONCILING') ORDER BY completed_at LIMIT ?",(max(1,min(int(limit),500)),))
        recovered=[]
        for row in rows:
            recovered.append(self.reconcile(row["audit_run_id"]))
        return recovered

    def recover_interrupted_runs(self,*,now=None,stale_after_seconds=60):
        now=float(self.clock() if now is None else now); cutoff=now-max(0,float(stale_after_seconds))
        with self._connect() as conn:
            rows=self._rows(conn,"SELECT audit_run_id,attempt_count FROM audit_runs WHERE state='RUNNING' AND started_at<? ORDER BY started_at LIMIT 500",(cutoff,))
            for row in rows:
                conn.execute("UPDATE audit_runs SET state='INTERRUPTED',completed_at=?,failure_class='INTERRUPTED',reconciliation_state='INTERRUPTED' WHERE audit_run_id=? AND state='RUNNING'",(now,row["audit_run_id"]))
                conn.execute("UPDATE audit_attempts SET status='INTERRUPTED',finished_at=?,failure_class='INTERRUPTED',reason='process_recovery' WHERE audit_run_id=? AND attempt_no=? AND status='RUNNING'",(now,row["audit_run_id"],row["attempt_count"]))
        return [row["audit_run_id"] for row in rows]

    def replay_result(self,audit_run_id):
        rows=self.findings._rows("SELECT * FROM audit_runs WHERE audit_run_id=?",(audit_run_id,))
        if not rows: raise KeyError(audit_run_id)
        run=rows[0]
        if run["state"]=="SUCCESS" and run["reconciliation_state"]=="RECONCILED":
            detail=self.audit_detail(audit_run_id)
            receipt=detail.get("reconciliation_receipt") or {}
            projection=receipt.get("result") or {}
            results=detail.get("rule_results") or []
            checks=[{"check_id":item["rule_id"],"title":item["rule_id"],"status":"ok" if item["status"] in {"PASS","WARN","FAIL"} else "skipped" if item["status"]=="SKIPPED" else "error","row_count":item["metrics"].get("row_count",0),"duration_ms":round(item["duration"]*1000),"columns":item["evidence"].get("columns",[]),"rows":[],"error":item.get("error")} for item in results]
            return {"audit_run_id":audit_run_id,"audit_type":"post_crq","status":"REPLAYED","trigger_type":run["trigger_type"],"trigger_reference":run["trigger_reference"],"runtime_identity":detail["runtime_identity"],"rule_pack_identity":run["rule_pack_identity"],"capability_snapshot":detail.get("capability_snapshot"),"capability_snapshot_hash":(detail.get("capability_snapshot") or {}).get("snapshot_hash"),"reconciliation_state":"RECONCILED","coverage_state":run["coverage_state"],"summary":{"checks_total":run["checks_total"],"checks_pass":run["checks_pass"],"checks_warn":run["checks_warn"],"checks_fail":run["checks_fail"],"checks_error":run["checks_error"],"checks_skipped":run["checks_skipped"]},"rule_results":results,"executed_checks":checks,"results_by_check":checks,"operational_summary":projection.get("findings"),"red_flags":projection.get("red_flags"),"context":{"profile":run["database_id"],"generated_at":run["completed_at"]},"replayed":True}
        return self.reconcile(audit_run_id)

    def list_audits(self,*,database_id=None,status=None,trigger_type=None,limit=50,offset=0):
        limit=max(1,min(int(limit),200)); offset=max(0,int(offset)); filters=[]; args=[]
        if database_id: filters.append("database_id=?"); args.append(str(database_id))
        if status: filters.append("state=?"); args.append(str(status).upper())
        if trigger_type: filters.append("trigger_type=?"); args.append(str(trigger_type).upper())
        where=" WHERE "+" AND ".join(filters) if filters else ""
        rows=self.findings._rows("SELECT audit_run_id,database_id,state,started_at,completed_at,duration_seconds,checks_total,checks_pass,checks_warn,checks_fail,checks_error,checks_skipped,coverage_state,coverage_ratio,trigger_type,trigger_reference,runtime_identity_json,rule_pack_identity,capability_snapshot_id,reconciliation_state,attempt_count,failure_class FROM audit_runs"+where+" ORDER BY started_at DESC LIMIT ? OFFSET ?",(*args,limit,offset))
        total=self.findings._rows("SELECT COUNT(*) AS count FROM audit_runs"+where,tuple(args))[0]["count"]
        return {"items":rows,"total":total,"limit":limit,"offset":offset}

    def audit_detail(self,audit_run_id):
        rows=self.findings._rows("SELECT * FROM audit_runs WHERE audit_run_id=?",(audit_run_id,))
        if not rows: raise KeyError(audit_run_id)
        run=rows[0]
        run["runtime_identity"]=_json(run.pop("runtime_identity_json",None),{})
        run["target_context"]=_json(run.pop("target_context_json",None),{})
        rules=self.findings._rows("SELECT attempt_no,rule_id,rule_version,definition_hash,status,severity,started_at,finished_at,duration,summary,metrics_json,evidence_json,error_json,coverage_meaning,object_type,owner,object_name,recommendation FROM rule_results WHERE audit_run_id=? ORDER BY attempt_no,rule_id",(audit_run_id,))
        for item in rules:
            item["metrics"]=_json(item.pop("metrics_json"),{})
            item["evidence"]=_json(item.pop("evidence_json"),{})
            item["error"]=_json(item.pop("error_json"),None)
        run["rule_results"]=rules
        evidence_rows=self.findings._rows("SELECT attempt_no,rule_id,evidence_index,database_id,evidence_hash,envelope_json FROM audit_rule_evidence WHERE audit_run_id=? ORDER BY attempt_no,rule_id,evidence_index",(audit_run_id,))
        for item in evidence_rows: item["envelope"]=_json(item.pop("envelope_json"),{})
        run["finding_evidence"]=evidence_rows
        run["attempts"]=self.findings._rows("SELECT attempt_no,attempt_id,trigger_type,status,started_at,finished_at,failure_class,reason FROM audit_attempts WHERE audit_run_id=? ORDER BY attempt_no",(audit_run_id,))
        run["capability_snapshot"]=(self.findings._rows("SELECT snapshot_id,database_id,engine,engine_version,status,snapshot_hash,snapshot_json,created_at FROM capability_snapshots WHERE snapshot_id=?",(run.get("capability_snapshot_id"),)) or [None])[0]
        if run["capability_snapshot"]:
            run["capability_snapshot"]["snapshot"]=_json(run["capability_snapshot"].pop("snapshot_json"),{})
        run["reconciliation_receipt"]=(self.findings._rows("SELECT receipt_id,input_hash,status,attempt_count,started_at,completed_at,result_json,error_class FROM audit_reconciliation_receipts WHERE audit_run_id=?",(audit_run_id,)) or [None])[0]
        if run["reconciliation_receipt"]:
            run["reconciliation_receipt"]["result"]=_json(run["reconciliation_receipt"].pop("result_json"),{})
        return run


def _safe_finding_envelope(item):
    allowed={"finding_id","check_id","title","schema","object_name","object_type","sql_severity","runtime_status","final_criticality","final_criticality_label","row_index","evidence","lot_assignment"}
    out={key:item.get(key) for key in allowed if key in item}
    if isinstance(out.get("evidence"),dict):
        out["evidence"]={key:redact_evidence(value) for key,value in out["evidence"].items() if key.lower() not in {"source_row","rows","sql_text","executed_sql","sql_binds","bind_values"}}
    if isinstance(out.get("lot_assignment"),dict): out["lot_assignment"]={key:value for key,value in out["lot_assignment"].items() if key in {"lot","source","confidence"}}
    return redact_evidence(out)
