"""Persistent, low-noise operational alerts and windowed reports."""
from __future__ import annotations

import hashlib
import json
import smtplib
import time
from email.message import EmailMessage
from typing import Any, Protocol

from src.api.security import redact_secrets

PRIORITY_ORDER = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
DEFAULT_POLICY = {"P1": {"mode": "immediate", "cooldown_seconds": 3600}, "P2": {"mode": "immediate", "cooldown_seconds": 14400}, "P3": {"mode": "digest", "cooldown_seconds": 86400}, "P4": {"mode": "dashboard", "cooldown_seconds": 86400}}


class NotificationChannel(Protocol):
    name: str
    def send(self, subject: str, body: str, recipients: list[str]) -> None: ...


class SmtpNotificationChannel:
    name = "email"
    def __init__(self, config: dict[str, Any]): self.config = config
    def send(self, subject: str, body: str, recipients: list[str]) -> None:
        if not recipients or not self.config.get("smtp_host") or not self.config.get("from_email"):
            raise ValueError("notification email is not configured")
        message = EmailMessage(); message["Subject"] = subject; message["From"] = self.config["from_email"]; message["To"] = ", ".join(recipients); message.set_content(body)
        with smtplib.SMTP(self.config["smtp_host"], int(self.config.get("smtp_port") or 587), timeout=30) as server:
            if self.config.get("smtp_use_tls", True): server.starttls()
            if self.config.get("smtp_username"): server.login(self.config["smtp_username"], self.config.get("smtp_password", ""))
            server.send_message(message)


class AlertingService:
    def __init__(self, findings: Any, automation_service: Any | None = None):
        self.findings, self.automation_service = findings, automation_service
        self._migrate()

    def _connect(self): return self.findings._connect()
    def _migrate(self):
        with self._connect() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS alert_events (id INTEGER PRIMARY KEY AUTOINCREMENT, alert_key TEXT UNIQUE NOT NULL, database_id TEXT NOT NULL, finding_id INTEGER, red_flag_id INTEGER, type TEXT NOT NULL, priority TEXT NOT NULL, severity TEXT, title TEXT NOT NULL, summary TEXT NOT NULL, reason TEXT NOT NULL, recommended_action TEXT, first_triggered_at REAL NOT NULL, last_triggered_at REAL NOT NULL, notification_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'OPEN', linked_alert_id INTEGER, actor TEXT, action_reason TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_alert_events_list ON alert_events(status, priority, last_triggered_at DESC);
            CREATE TABLE IF NOT EXISTS alert_deliveries (id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id INTEGER NOT NULL, channel TEXT NOT NULL, attempted_at REAL NOT NULL, status TEXT NOT NULL, error_reason TEXT, attempt INTEGER NOT NULL DEFAULT 1);
            CREATE INDEX IF NOT EXISTS idx_alert_deliveries_alert ON alert_deliveries(alert_id, attempted_at DESC);
            CREATE TABLE IF NOT EXISTS maintenance_windows (id INTEGER PRIMARY KEY AUTOINCREMENT, database_id TEXT NOT NULL, starts_at REAL NOT NULL, ends_at REAL NOT NULL, reason TEXT NOT NULL, created_by TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_maintenance_window ON maintenance_windows(database_id, starts_at, ends_at);
            CREATE TABLE IF NOT EXISTS operational_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, report_type TEXT NOT NULL, period_start REAL NOT NULL, period_end REAL NOT NULL, generated_at REAL NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, markdown TEXT NOT NULL, html TEXT NOT NULL, delivery_status TEXT, UNIQUE(report_type, period_start, period_end));
            CREATE INDEX IF NOT EXISTS idx_operational_reports_history ON operational_reports(report_type, generated_at DESC);
            """)
            if "delivered_at" not in {row[1] for row in conn.execute("PRAGMA table_info(operational_reports)")}:
                conn.execute("ALTER TABLE operational_reports ADD COLUMN delivered_at REAL")

    @staticmethod
    def _rows(conn, sql, args=()):
        cursor = conn.execute(sql, args); names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    @staticmethod
    def _record(cursor, row):
        return None if row is None else dict(zip([column[0] for column in cursor.description], row))
    @staticmethod
    def _key(database_id, event_type, identity): return hashlib.sha256(f"{database_id}|{event_type}|{identity}".encode()).hexdigest()
    def _context(self, database_id):
        rows = self.findings._rows("SELECT * FROM target_contexts WHERE database_id=?", (database_id,))
        return rows[0] if rows else {"environment": "development", "criticality": "medium", "tags": "[]"}
    def _priority(self, finding, context):
        if finding.get("severity") == "CRITICAL": return "P1" if context.get("criticality") in {"critical", "high"} or context.get("environment") == "production" else "P2"
        return "P3" if finding.get("severity") == "MEDIUM" else "P4"
    def _maintenance(self, database_id, now):
        with self._connect() as conn: return bool(conn.execute("SELECT 1 FROM maintenance_windows WHERE database_id=? AND starts_at<=? AND ends_at>=? LIMIT 1", (database_id, now, now)).fetchone())
    def evaluate(self, database_id: str, now: float | None = None) -> list[dict[str, Any]]:
        now = time.time() if now is None else now; context = self._context(database_id); candidates = []
        for f in self.findings.list_findings(database=database_id, resolved=None):
            if f["severity"] != "CRITICAL": continue
            mapping = {"NEW": "NEW_CRITICAL_FINDING", "WORSENING": "WORSENING_CRITICAL_FINDING", "REOPENED": "REOPENED_CRITICAL_FINDING", "RESOLVED": "RESOLVED_CRITICAL_FINDING"}
            typ = mapping.get(f["delta"])
            if typ: candidates.append((typ, self._priority(f, context), f, None))
        finding_ids = {item[2].get("id") for item in candidates if item[2].get("id")}
        for flag in self.findings.list_red_flags(database_id=database_id):
            # A P1 projection of the same critical finding is prioritisation evidence,
            # not a second operator situation.
            if flag["priority"] == "P1" and flag.get("finding_id") not in finding_ids:
                candidates.append(("NEW_P1_RED_FLAG", "P1", flag, flag))
        audit = self.findings._latest_audit(database_id)
        if audit and audit["state"] != "SUCCESS": candidates.append(("AUDIT_EXECUTION_FAILURE", "P1", {"id": None, "summary": "Audit execution failed", "recommendation": "Review audit connectivity and runtime logs.", "severity": "CRITICAL"}, None))
        elif audit and audit["coverage_state"] != "FULL": candidates.append(("COVERAGE_DEGRADED", "P2", {"id": None, "summary": "Audit coverage degraded", "recommendation": "Restore full check coverage before resolving findings.", "severity": "MEDIUM"}, None))
        results = [self._upsert_event(database_id, typ, priority, item, flag, context, now) for typ, priority, item, flag in candidates]
        return [item for item in results if item]
    def _upsert_event(self, database_id, typ, priority, item, flag, context, now):
        identity = item.get("id") or item.get("finding_id") or typ; key = self._key(database_id, typ, identity); suppressed = self._maintenance(database_id, now)
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM alert_events WHERE alert_key=?", (key,)); event = self._record(cursor, cursor.fetchone())
            title = f"[{priority}] {database_id} requires attention"; summary = str(redact_secrets(str(item.get("summary") or item.get("explanation") or typ))).strip(); reason = f"{typ.replace('_', ' ').title()} on {context.get('environment', 'development')} target"; rec = str(redact_secrets(str(item.get("recommendation") or "Review the operational evidence and take the recommended corrective action.")))
            linked_alert_id = None
            if typ == "RESOLVED_CRITICAL_FINDING" and item.get("id"):
                prior = conn.execute("SELECT id FROM alert_events WHERE database_id=? AND finding_id=? AND type != ? ORDER BY last_triggered_at DESC LIMIT 1", (database_id, item["id"], typ)).fetchone()
                if prior:
                    linked_alert_id = prior[0]
                    conn.execute("UPDATE alert_events SET status='RECOVERED',updated_at=? WHERE id=?", (now, linked_alert_id))
                    typ = "RECOVERY"
                    key = self._key(database_id, typ, identity)
                    reason = "Recovery detected after a previously alerted critical finding."
            if event is None:
                status = "SUPPRESSED" if suppressed else "OPEN"; conn.execute("INSERT INTO alert_events(alert_key,database_id,finding_id,red_flag_id,type,priority,severity,title,summary,reason,recommended_action,first_triggered_at,last_triggered_at,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (key,database_id,item.get("id"),flag.get("id") if flag else None,typ,priority,item.get("severity"),title,summary,reason,rec,now,now,status,now,now)); cursor=conn.execute("SELECT * FROM alert_events WHERE alert_key=?", (key,)); event=self._record(cursor,cursor.fetchone()); should = not suppressed
                if linked_alert_id:
                    conn.execute("UPDATE alert_events SET linked_alert_id=? WHERE id=?", (linked_alert_id, event["id"]))
            else:
                escalated = PRIORITY_ORDER.get(priority, 9) < PRIORITY_ORDER.get(event["priority"], 9); cooldown = DEFAULT_POLICY[priority]["cooldown_seconds"]; should = not suppressed and event["status"] not in {"SUPPRESSED", "CLOSED"} and (escalated or now - event["last_triggered_at"] >= cooldown)
                conn.execute("UPDATE alert_events SET priority=?,summary=?,reason=?,recommended_action=?,last_triggered_at=?,updated_at=? WHERE id=?", (priority,summary,reason,rec,now,now,event["id"])); cursor=conn.execute("SELECT * FROM alert_events WHERE id=?", (event["id"],)); event=self._record(cursor,cursor.fetchone())
            if should and DEFAULT_POLICY[priority]["mode"] == "immediate": self._deliver(conn, event, now)
            return event
    def _deliver(self, conn, event, now, channel: NotificationChannel | None = None):
        attempt = int(conn.execute("SELECT COUNT(*) FROM alert_deliveries WHERE alert_id=?", (event["id"],)).fetchone()[0]) + 1
        try:
            if channel is None:
                config = self.automation_service._delivery_config() if self.automation_service else {}; channel = SmtpNotificationChannel(config); recipients = config.get("default_recipients", [])
            else: recipients = []
            channel.send(event["title"], f"Database: {event['database_id']}\n\nProblem: {event['summary']}\n\nReason: {event['reason']}\n\nRecommended action: {event['recommended_action']}", recipients)
            conn.execute("INSERT INTO alert_deliveries(alert_id,channel,attempted_at,status,attempt) VALUES(?,?,?,?,?)", (event["id"],channel.name,now,"SENT",attempt)); conn.execute("UPDATE alert_events SET notification_count=notification_count+1 WHERE id=?", (event["id"],))
        except Exception as exc:
            safe = str(redact_secrets(str(exc)))[:240]; conn.execute("INSERT INTO alert_deliveries(alert_id,channel,attempted_at,status,error_reason,attempt) VALUES(?,?,?,?,?,?)", (event["id"],getattr(channel,"name","email"),now,"FAILED",safe,attempt))
    def list_alerts(self, *, status=None, priority=None, database=None, limit=100):
        where=[]; args=[]
        for field, value in (("status",status),("priority",priority),("database_id",database)):
            if value: where.append(f"{field}=?"); args.append(value)
        sql="SELECT * FROM alert_events" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY last_triggered_at DESC LIMIT ?"; args.append(max(1,min(int(limit),200)))
        with self._connect() as conn: return self._rows(conn,sql,args)
    def alert(self, alert_id):
        with self._connect() as conn:
            cursor=conn.execute("SELECT * FROM alert_events WHERE id=?",(alert_id,)); event=self._record(cursor,cursor.fetchone())
            if not event: raise KeyError(alert_id)
            event["deliveries"]=self._rows(conn,"SELECT channel,attempted_at,status,error_reason,attempt FROM alert_deliveries WHERE alert_id=? ORDER BY attempted_at DESC",(alert_id,)); return event
    def action(self, alert_id, status, actor, reason):
        if status not in {"ACKNOWLEDGED","SUPPRESSED","CLOSED"}: raise ValueError("Unsupported alert action")
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM alert_events WHERE id=?",(alert_id,)).fetchone(): raise KeyError(alert_id)
            conn.execute("UPDATE alert_events SET status=?,actor=?,action_reason=?,updated_at=? WHERE id=?",(status,actor,str(reason or ""),time.time(),alert_id))
        return self.alert(alert_id)
    def add_maintenance(self, database_id, starts_at, ends_at, reason, actor):
        if ends_at <= starts_at: raise ValueError("Maintenance end must be after start")
        with self._connect() as conn:
            cur=conn.execute("INSERT INTO maintenance_windows(database_id,starts_at,ends_at,reason,created_by,created_at) VALUES(?,?,?,?,?,?)",(database_id,starts_at,ends_at,reason,actor,time.time())); return {"id":cur.lastrowid,"database_id":database_id}
    def notification_health(self):
        with self._connect() as conn:
            rows=self._rows(conn,"SELECT status,attempted_at FROM alert_deliveries ORDER BY attempted_at DESC LIMIT 3")
        failures=sum(r["status"]=="FAILED" for r in rows); return {"status":"DEGRADED" if failures >= 3 else "HEALTHY", "consecutive_failures":failures, "last_delivery":rows[0] if rows else None}
    def generate_report(self, report_type="daily", now=None):
        if report_type not in {"daily", "weekly"}: raise ValueError("Unknown report type")
        now=time.time() if now is None else now; seconds=86400 if report_type=="daily" else 604800; end=(now // seconds) * seconds; start=end-seconds
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM operational_reports WHERE report_type=? AND period_start=? AND period_end=?", (report_type,start,end))
            existing = self._record(cursor, cursor.fetchone())
        if existing:
            existing["payload"] = json.loads(existing["payload"])
            return existing
        audits=self.findings._rows("SELECT * FROM audit_runs WHERE completed_at>=?",(start,)); findings=self.findings.list_findings(resolved=None); fleet=self.findings.fleet(now=now); aging=[f for f in findings if f["severity"]=="CRITICAL" and now-f["first_seen"] >= seconds]
        audits = [audit for audit in audits if audit["completed_at"] < end]
        payload={"type":report_type,"period_start":start,"period_end":end,"fleet":fleet["counts"],"new":sum(f["delta"]=="NEW" for f in findings),"worsening":sum(f["delta"]=="WORSENING" for f in findings),"resolved":sum(f["delta"]=="RESOLVED" for f in findings),"aging_findings":[{"id":f["id"],"database_id":f["database_id"],"summary":redact_secrets(f["summary"]),"days_open":round((now-f["first_seen"])/86400,1),"occurrences":f["occurrences"]} for f in aging],"audit_successful":sum(a["state"]=="SUCCESS" for a in audits),"audit_failed":sum(a["state"]!="SUCCESS" for a in audits),"needs_attention":[redact_secrets(item) for item in fleet["needs_attention"][:10]]}
        lines=[f"# E13DB {report_type.upper()} REPORT", "", "## Needs Attention"]+[f"- {x['priority']} {x['database_id']}: {x.get('explanation','') }" for x in payload['needs_attention']] + ["", "## Fleet", json.dumps(payload["fleet"]), "", f"New: {payload['new']} | Worsening: {payload['worsening']} | Resolved: {payload['resolved']}"]
        markdown="\n".join(lines); html="<h1>E13DB %s Report</h1><h2>Needs Attention</h2><ul>%s</ul><h2>Fleet</h2><pre>%s</pre>" % (report_type.title(), "".join(f"<li>{x['priority']} {x['database_id']}: {x.get('explanation','')}</li>" for x in payload['needs_attention']), json.dumps(payload['fleet']))
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO operational_reports(report_type,period_start,period_end,generated_at,status,payload,markdown,html) VALUES(?,?,?,?,?,?,?,?)",(report_type,start,end,now,"GENERATED",json.dumps(payload),markdown,html)); cursor=conn.execute("SELECT * FROM operational_reports WHERE report_type=? AND period_start=? AND period_end=?",(report_type,start,end)); row=self._record(cursor,cursor.fetchone())
        row["payload"] = json.loads(row["payload"])
        return row
    def list_reports(self, limit=50):
        with self._connect() as conn: return self._rows(conn,"SELECT id,report_type,period_start,period_end,generated_at,status,delivery_status FROM operational_reports ORDER BY generated_at DESC LIMIT ?",(max(1,min(int(limit),200)),))
    def run_scheduled_reports(self, now=None):
        """Called by AutomationService's existing maintenance tick, never a new scheduler."""
        now = time.time() if now is None else now; generated = []
        for report_type, interval in (("daily", 86400), ("weekly", 604800)):
            with self._connect() as conn:
                end = (now // interval) * interval
                row = conn.execute("SELECT 1 FROM operational_reports WHERE report_type=? AND period_start=? AND period_end=?", (report_type,end-interval,end)).fetchone()
            if not row:
                generated.append(self.generate_report(report_type, now))
        return generated
    def report(self, report_id):
        with self._connect() as conn:
            cursor=conn.execute("SELECT * FROM operational_reports WHERE id=?",(report_id,)); result=self._record(cursor,cursor.fetchone())
            if not result: raise KeyError(report_id)
            result["payload"]=json.loads(result["payload"]); return result
    def deliver_report(self, report_id):
        report = self.report(report_id)
        try:
            config = self.automation_service._delivery_config() if self.automation_service else {}
            SmtpNotificationChannel(config).send(
                f"E13DB {report['report_type'].title()} Report",
                report["markdown"],
                config.get("default_recipients", []),
            )
            status = "SENT"
        except Exception as exc:
            status = "FAILED: " + str(redact_secrets(str(exc)))[:200]
        with self._connect() as conn:
            conn.execute("UPDATE operational_reports SET delivery_status=?,delivered_at=? WHERE id=?", (status, time.time(), report_id))
        return {"id": report_id, "delivery_status": status}
