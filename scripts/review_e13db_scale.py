"""Reproducible synthetic review-scale probe; writes only into a temp directory."""
import argparse
import json
import gc
import tempfile
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.api.alerting_engine import AlertingService
from src.api.finding_engine import FindingStore, finding_fingerprint
from src.api.investigation_engine import InvestigationStore
from src.core.automation_store import AutomationStore
from src.core.internal_db import InternalDBManager


@contextmanager
def connection(store):
    conn=store._get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",help="Optional path for a machine-readable result receipt")
    args=parser.parse_args()
    target_count = 100
    days = 365
    audits_per_day = 2
    rules_per_audit = 4
    finding_count = 5000
    occurrences_per_finding = 5
    alert_count = 2000
    investigation_count = 500
    epoch = time.time()
    timings = {}

    with tempfile.TemporaryDirectory(prefix="e13db-review-scale-") as temp:
        root = Path(temp)
        internal = InternalDBManager(str(root / "internal.db"))
        automation = AutomationStore(str(root / "automation.db"))
        findings = FindingStore(internal)
        alerts = AlertingService(findings)
        investigations = InvestigationStore(findings, auto_open=False)

        targets = [f"SCALE-{index:03d}" for index in range(target_count)]
        with connection(internal) as conn:
            conn.executemany("INSERT INTO target_contexts(database_id,environment,criticality,owner,tags,updated_at) VALUES(?,?,?,?,?,?)", [(target,"production","high","review-simulation","[]",epoch) for target in targets])
            audit_rows=[]
            for day in range(days):
                for tick in range(audits_per_day):
                    completed=epoch-(days-day)*86400+tick*3600
                    for target in targets:
                        run=f"{target}-D{day:03d}-T{tick}"
                        audit_rows.append((run,target,"SUCCESS",completed-20,completed,20,rules_per_audit,rules_per_audit,0,0,0,0,"FULL",1.0,0,0,0,None))
            conn.executemany("INSERT INTO audit_runs(audit_run_id,database_id,state,started_at,completed_at,duration_seconds,checks_total,checks_pass,checks_warn,checks_fail,checks_error,checks_skipped,coverage_state,coverage_ratio,findings_created,findings_resolved,red_flags_generated,error_summary) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",audit_rows)
            contexts={target:0 for target in targets}
            find_rows=[]
            for index in range(finding_count):
                target=targets[index%target_count]
                rule=f"RULE-{index%rules_per_audit:02d}"
                owner=f"APP_{index%10:02d}"
                obj=f"OBJECT_{index:05d}"
                first=epoch-(days-(index%days))*86400
                fingerprint=finding_fingerprint(target,rule,"TABLE",owner,obj)
                find_rows.append((fingerprint,target,rule,"TABLE",owner,obj,"CRITICAL","OPEN","WORSENING",first,first+occurrences_per_finding*3600,occurrences_per_finding,json.dumps(index+100),json.dumps(index),f"Synthetic capacity/performance Finding {index}",json.dumps({"summary":"synthetic; no production values","metrics":{"value":index+100}}),"Review stored evidence",first,first))
            conn.executemany("INSERT INTO findings(fingerprint,database_id,rule_id,object_type,owner,object_name,severity,status,delta,first_seen,last_seen,occurrences,current_value,previous_value,summary,evidence,recommendation,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",find_rows)
            finding_ids=[row[0] for row in conn.execute("SELECT id FROM findings ORDER BY id")]
            occ_rows=[]
            for finding_id in finding_ids:
                row=conn.execute("SELECT database_id,last_seen FROM findings WHERE id=?",(finding_id,)).fetchone()
                for occurrence in range(occurrences_per_finding):
                    observed=row[1]-occurrence*3600
                    audit=f"{row[0]}-O{occurrence}"
                    occ_rows.append((finding_id,audit,observed,"CRITICAL",json.dumps(10+occurrence),"WORSENING","Synthetic observed metric; no raw SQL.",json.dumps({"elapsed_seconds":2+occurrence,"unit":"s"})))
            conn.executemany("INSERT INTO finding_occurrences(finding_id,audit_run_id,observed_at,severity,value,delta,summary,evidence) VALUES(?,?,?,?,?,?,?,?)",occ_rows)
            flag_rows=[]
            for index,finding_id in enumerate(finding_ids[:alert_count]):
                finding=conn.execute("SELECT database_id,last_seen,summary FROM findings WHERE id=?",(finding_id,)).fetchone()
                at=finding[1]; key=f"SCALE-ALERT-{index:05d}"
                flag_rows.append((key,finding_id,finding[0],"WORSENING_FINDING","P2","OPEN","synthetic same-window Finding","Review evidence",at,at,1,at,at))
            conn.executemany("INSERT INTO red_flags(dedupe_key,finding_id,database_id,flag_type,priority,status,explanation,recommendation,first_seen,last_seen,occurrences,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",flag_rows)

            alert_rows=[]
            for index,finding_id in enumerate(finding_ids[:alert_count]):
                finding=conn.execute("SELECT database_id,last_seen,summary FROM findings WHERE id=?",(finding_id,)).fetchone()
                at=finding[1]; key=f"SCALE-EVENT-{index:05d}"
                alert_rows.append((key,finding[0],finding_id,None,"WORSENING_CRITICAL_FINDING","P2","CRITICAL","Synthetic alert",finding[2],"Synthetic review dataset","Review evidence",at,at,0,"OPEN",None,None,None,at,at))
            conn.executemany("INSERT INTO alert_events(alert_key,database_id,finding_id,red_flag_id,type,priority,severity,title,summary,reason,recommended_action,first_triggered_at,last_triggered_at,notification_count,status,linked_alert_id,actor,action_reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",alert_rows)

            case_rows=[]
            for index,finding_id in enumerate(finding_ids[:investigation_count]):
                finding=conn.execute("SELECT database_id,first_seen,last_seen,fingerprint,summary FROM findings WHERE id=?",(finding_id,)).fetchone()
                at=finding[2]; case_rows.append((finding[0],finding_id,"OPEN",at-60,at,"Synthetic bounded investigation", "automatic","E13DB",finding[1]-1800,at+1800,finding[3]))
            conn.executemany("INSERT INTO investigations(database_id,primary_finding_id,status,opened_at,updated_at,summary,source,actor,time_window_start,time_window_end,fingerprint) VALUES(?,?,?, ?,?,?,?,?,?,?,?)",case_rows)
            case_ids=[row[0] for row in conn.execute("SELECT id FROM investigations ORDER BY id")]
            ev_rows=[]
            for case_id in case_ids:
                case=conn.execute("SELECT database_id,primary_finding_id,opened_at FROM investigations WHERE id=?",(case_id,)).fetchone()
                for j in range(10):
                    ev_rows.append((case_id,case[0],case[1],None,f"SCALE-AUDIT-{j}","RULE-00","PERFORMANCE",case[2]+j,"elapsed_seconds",json.dumps(2+j),"s","TABLE","APP_00",f"OBJECT_{case[1]:05d}","Synthetic elapsed-time observation", "finding_occurrence","REDACTED",json.dumps({"sql_id":f"SCALE-SQL-{case[1]}"})))
            conn.executemany("INSERT INTO investigation_evidence(investigation_id,database_id,finding_id,occurrence_id,audit_run_id,rule_id,category,observed_at,metric_name,value_json,unit,object_type,owner,object_name,summary,source,sensitivity,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",ev_rows)

        # Populate the second durable store with historical automation runs and
        # audit rule facts so the probe includes the actual split-store schema.
        jobs=[]
        for target in targets:
            jobs.append(automation.create_job({"name":f"Scale {target}","audit_type":"post_crq","profile":target}))
        now_iso=datetime.now(timezone.utc)
        run_rows=[]
        fact_rows=[]
        run_seq=0
        for day in range(days):
            for tick in range(audits_per_day):
                started=(now_iso-timedelta(days=days-day, hours=tick)).isoformat()
                for job in jobs:
                    run_seq+=1; run_id=run_seq
                    run_rows.append((run_id,job["id"],started,started,"success",20,"{}"))
                    for check in range(rules_per_audit):
                        fact_rows.append((run_id,job["id"],f"SCALE-{run_id}",started,f"RULE-{check:02d}",f"Synthetic Rule {check}","MEDIUM","PASS",0,0,0,0,"{}"))
        with connection(automation) as conn:
            conn.executemany("INSERT INTO job_runs(id,job_id,started_at,finished_at,status,duration_ms,summary_json) VALUES(?,?,?,?,?,?,?)",run_rows)
            conn.executemany("INSERT INTO audit_check_facts(run_id,job_id,execution_id,executed_at,check_id,title,severity,status,row_count,finding_count,affected_lots,affected_schemas,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",fact_rows)

        def measure(name, callback):
            started=time.perf_counter(); callback(); timings[name]=round(time.perf_counter()-started,4)
        measure("fleet_dashboard_100_targets",lambda:findings.fleet(now=epoch))
        measure("finding_list_5000",lambda:findings.list_findings(resolved=None))
        measure("audit_history_365d_target",lambda:findings.audit_history(targets[0],limit=200))
        measure("alert_list_2000",lambda:alerts.list_alerts(limit=200))
        measure("report_list",lambda:alerts.list_reports(limit=50))
        measure("investigation_list_500",lambda:investigations.list(limit=100))
        sample=investigations.list(limit=1)["items"][0]
        measure("investigation_detail_with_timeline_and_correlation",lambda:investigations.get(sample["id"]))
        with connection(internal) as conn:
            counts={table:conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("audit_runs","findings","finding_occurrences","red_flags","alert_events","investigations","investigation_evidence")}
        with connection(automation) as conn:
            counts["automation_job_runs"]=conn.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0]
            counts["rule_results"]=conn.execute("SELECT COUNT(*) FROM audit_check_facts").fetchone()[0]
        result={"schema":"E13DB_ARCH_REVIEW_SCALE_V1","synthetic":True,"production_data":False,"targets":target_count,"days":days,"audits_per_day_per_target":audits_per_day,"rules_per_audit":rules_per_audit,"configured_findings":finding_count,"configured_alerts":alert_count,"configured_investigations":investigation_count,"counts":counts,"timings_seconds":timings,"limitations":["Synthetic SQLite rows exercise repository schemas and query surfaces, not Oracle connection/driver latency.","One local Windows host and SQLite files; timings are evidence for relative query cost only, not production capacity SLOs.","No SQL text, credentials or production data are inserted."]}
        rendered=json.dumps(result,indent=2)
        print(rendered)
        if args.output:
            output=ROOT/args.output
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(rendered+"\n",encoding="utf-8")
        del sample, investigations, alerts, findings, internal, automation
        gc.collect()


if __name__=="__main__":
    main()
