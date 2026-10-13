"""Bounded, read-only Oracle operational diagnostics for E13DB-013."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from datetime import datetime

from src.api.audit_evidence import PROBE_VIEWS, discover_oracle_capabilities, rule_capability_skip_reason, rule_pack_identity, runtime_identity
from src.api.check_engine import RuleDefinition, RuleResult, RuleStatus, redact_evidence

MAX_ROWS = 200
MAX_SESSION_ROWS = 80
MAX_BLOCKING_EDGES = 80
MAX_BLOCKING_ROOTS = 50
MAX_SQL_ROWS = 60
MAX_STATS_ROWS = 50
MAX_SEGMENT_ROWS = 50
MAX_TABLESPACE_ROWS = 100
MAX_TEMP_ROWS = 50
MAX_PLAN_STEPS = 100
SQL_HISTORY_WINDOW_DAYS = 1
DEFAULT_THRESHOLDS = {"long_session_seconds": 300, "blocking_warning_seconds": 30, "blocking_critical_seconds": 300, "blocking_critical_sessions": 3, "sql_elapsed_warning_seconds": 2.0, "sql_elapsed_critical_seconds": 10.0, "sql_regression_percent": 25.0, "segment_growth_warning_percent": 10.0, "segment_growth_warning_bytes": 67108864, "segment_growth_critical_percent": 50.0, "segment_growth_critical_bytes": 1073741824, "tablespace_warning_percent": 80.0, "tablespace_critical_percent": 95.0, "min_sql_executions": 3}

CAPABILITY_RULES = {
    "ORACLE_SESSIONS": ("SESSION_VISIBILITY",),
    "ORACLE_BLOCKING": ("SESSION_VISIBILITY", "LOCK_VISIBILITY"),
    "ORACLE_SQL_PERFORMANCE": ("SQL_STATS_VISIBILITY",),
    "ORACLE_PLAN_CHANGES": ("SQL_STATS_VISIBILITY",),
    "ORACLE_PLAN_DETAILS": ("SQL_PLAN_VISIBILITY",),
    "ORACLE_OBJECT_STATISTICS": ("SQL_PLAN_VISIBILITY", "STATISTICS_VISIBILITY"),
    "ORACLE_CAPACITY": ("STORAGE_VISIBILITY",),
    "ORACLE_TEMP_CAPACITY": ("TEMP_STORAGE_VISIBILITY", "TEMPFILE_VISIBILITY"),
    "ORACLE_SEGMENT_GROWTH": ("SEGMENT_VISIBILITY",),
    "ORACLE_RAC_SCOPE": ("RAC_VISIBILITY",),
    "ORACLE_CONTAINER_SCOPE": ("CDB_VISIBILITY",),
}

RULE_TITLES = {
    "ORACLE_SESSIONS": "Observed Oracle sessions",
    "ORACLE_BLOCKING": "Oracle blocking chains",
    "ORACLE_SQL_PERFORMANCE": "Oracle SQL performance",
    "ORACLE_PLAN_CHANGES": "Oracle execution-plan changes",
    "ORACLE_PLAN_DETAILS": "Oracle execution-plan steps",
    "ORACLE_OBJECT_STATISTICS": "Statistics for workload-related objects",
    "ORACLE_CAPACITY": "Oracle tablespace capacity",
    "ORACLE_TEMP_CAPACITY": "Oracle temporary tablespace capacity",
    "ORACLE_SEGMENT_GROWTH": "Observed Oracle segment growth",
    "ORACLE_RAC_SCOPE": "Oracle RAC visibility scope",
    "ORACLE_CONTAINER_SCOPE": "Oracle CDB/PDB visibility scope",
}

def _number(value, default=0.0):
    try:
        result=float(value)
        return result if math.isfinite(result) else default
    except (TypeError,ValueError):
        return default


def _int(value, default=0):
    try: return int(value) if value is not None else default
    except (TypeError,ValueError): return default


def _oracle_time(value):
    if isinstance(value,datetime): return value.isoformat(timespec="seconds")
    if value is None: return None
    return str(value)[:64]


def _safe_name(value, limit=128):
    text=str(value or "").strip()
    if not text or len(text)>limit or not re.fullmatch(r"[A-Za-z0-9_$#.-]+",text): return ""
    return text.upper()


def _safe_sql_id(value):
    text=str(value or "").strip()
    return text.lower() if re.fullmatch(r"[A-Za-z0-9_$#-]{1,64}",text) else ""


def _row_dicts(rows, columns):
    if not rows or not columns: return []
    names=[str(column).strip().lower() for column in columns]
    return [dict(zip(names,row)) for row in rows]


def _query(db_manager, sql, binds, *, max_rows=MAX_ROWS, timeout_ms=3000):
    started=time.perf_counter()
    connection=getattr(db_manager,"connection",None); previous_timeout=getattr(connection,"call_timeout",None) if connection is not None else None
    try:
        if connection is not None and hasattr(connection,"call_timeout"):
            connection.call_timeout=min(int(previous_timeout or timeout_ms),int(timeout_ms))
        rows,columns=db_manager.execute_query(sql,binds)
        duration=max(0.0,time.perf_counter()-started)
        if rows is None:
            return None,str(getattr(db_manager,"last_error",None) or "oracle_query_failed"),duration
        return _row_dicts(rows[:max_rows],columns),None,duration
    except Exception as exc:
        return None,str(exc),max(0.0,time.perf_counter()-started)
    finally:
        connection=getattr(db_manager,"connection",None)
        if connection is not None and hasattr(connection,"call_timeout"):
            try: connection.call_timeout=previous_timeout
            except Exception: pass


def _rule(rule_id, query_identity, *, severity="MEDIUM", required_capabilities=None, recommendation=""):
    digest=hashlib.sha256(str(query_identity).encode("utf-8")).hexdigest()
    return RuleDefinition(
        rule_id=rule_id,name=RULE_TITLES[rule_id],description="Bounded read-only Oracle operational diagnostic.",
        category="oracle_diagnostics",default_severity=severity,supported_engine=("oracle",),
        required_capabilities=tuple(required_capabilities or CAPABILITY_RULES[rule_id]),
        version="oracle-diagnostics-v1",definition_hash=digest,recommendation=recommendation,
        tags=("oracle", "read-only", "diagnostics"),evidence_sensitivity="redacted",
    )


def _result(definition,database_id,status,started,duration,summary,metrics=None,evidence=None,error=None):
    finished=started+max(0.0,duration)
    return RuleResult(
        rule_id=definition.rule_id,database_id=database_id,status=status,severity=definition.default_severity,
        started_at=started,finished_at=finished,duration=max(0.0,duration),summary=str(summary or "")[:500],
        metrics=metrics or {},evidence=redact_evidence(evidence or {}),error=redact_evidence(error) if error else None,
        recommendation=definition.recommendation,rule_version=definition.version,definition_hash=definition.definition_hash,
        coverage_meaning="not_evaluated" if status is RuleStatus.SKIPPED else "evaluation_error" if status is RuleStatus.ERROR else "evaluated",
    ).to_dict()


def _envelope(rule_id,title,*,owner="",object_name="",object_type="",severity="MITJA",evidence=None,index=0):
    return {"check_id":rule_id,"title":str(title)[:220],"schema":owner,"object_name":object_name,"object_type":object_type,"sql_severity":severity,"runtime_status":"ok","evidence":redact_evidence(evidence or {}),"row_index":index}


def _observation(category,identity,*,now,inst_id=None,con_id=None,sql_id=None,plan_hash=None,owner=None,object_name=None,metrics=None,evidence=None):
    return {"category":category,"identity_key":str(identity)[:256],"observed_at":float(now),"inst_id":_int(inst_id,None),"con_id":_int(con_id,None),"sql_id":_safe_sql_id(sql_id),"plan_hash":str(plan_hash or "")[:64],"owner":_safe_name(owner),"object_name":_safe_name(object_name,256),"metrics":metrics or {},"evidence":evidence or {}}


def _query_error_status(error, capabilities, required):
    text=str(error or "").upper()
    if "ORA-01031" in text:
        for key in required: capabilities[key]="INSUFFICIENT_PRIVILEGES"
        return RuleStatus.SKIPPED,"INSUFFICIENT_PRIVILEGES"
    if "ORA-00904" in text or "ORA-00942" in text:
        for key in required:
            if capabilities.get(key)=="AVAILABLE": capabilities[key]="UNKNOWN"
        return RuleStatus.ERROR,"ORACLE_VIEW_OR_COLUMN_UNAVAILABLE"
    if "TIMEOUT" in text or "ORA-01013" in text:
        return RuleStatus.ERROR,"ORACLE_QUERY_TIMEOUT"
    return RuleStatus.ERROR,"ORACLE_QUERY_FAILED"


def _thresholds(options):
    values={**DEFAULT_THRESHOLDS,**(options or {})}
    values["long_session_seconds"]=max(30,min(86400,_int(values.get("long_session_seconds"),300)))
    values["blocking_warning_seconds"]=max(5,min(86400,_int(values.get("blocking_warning_seconds"),30)))
    values["blocking_critical_seconds"]=max(values["blocking_warning_seconds"]+1,min(604800,_int(values.get("blocking_critical_seconds"),300)))
    values["blocking_critical_sessions"]=max(2,min(100,_int(values.get("blocking_critical_sessions"),3)))
    values["sql_regression_percent"]=max(5.0,min(1000.0,_number(values.get("sql_regression_percent"),25)))
    values["sql_elapsed_warning_seconds"]=max(0.1,min(3600.0,_number(values.get("sql_elapsed_warning_seconds"),2)))
    values["sql_elapsed_critical_seconds"]=max(values["sql_elapsed_warning_seconds"]+0.1,min(86400.0,_number(values.get("sql_elapsed_critical_seconds"),10)))
    values["segment_growth_warning_percent"]=max(1.0,min(1000.0,_number(values.get("segment_growth_warning_percent"),10)))
    values["segment_growth_critical_percent"]=max(values["segment_growth_warning_percent"]+1,min(10000.0,_number(values.get("segment_growth_critical_percent"),50)))
    values["segment_growth_warning_bytes"]=max(1_048_576,min(2**50,_int(values.get("segment_growth_warning_bytes"),67_108_864)))
    values["segment_growth_critical_bytes"]=max(values["segment_growth_warning_bytes"]+1,min(2**50,_int(values.get("segment_growth_critical_bytes"),1_073_741_824)))
    for key,default in (("sql_elapsed_warning_seconds",2),("sql_elapsed_critical_seconds",10),("tablespace_warning_percent",80),("tablespace_critical_percent",95)):
        values[key]=max(0.0,min(1000000.0,_number(values.get(key),default)))
    if values["tablespace_warning_percent"]>=values["tablespace_critical_percent"]:
        values["tablespace_warning_percent"],values["tablespace_critical_percent"]=80.0,95.0
    values["min_sql_executions"]=max(1,min(100000,_int(values.get("min_sql_executions"),3)))
    return values


def _session_query(capabilities,thresholds,container_id=None):
    rac=capabilities.get("RAC_VISIBILITY")=="AVAILABLE" and capabilities.get("GV_SESSION_VISIBILITY")=="AVAILABLE"
    cdb=capabilities.get("CDB_VISIBILITY")=="AVAILABLE"
    session_view="gv$session" if rac else "v$session"
    instance_expr="s.inst_id" if rac else "(SELECT instance_number FROM v$instance)"
    con_expr="s.con_id" if cdb else "CAST(NULL AS NUMBER)"
    container_filter=" AND s.con_id=:current_con_id" if cdb and container_id is not None else ""
    transaction_join=""
    transaction_select="CAST(NULL AS VARCHAR2(30)) AS transaction_start,CAST(NULL AS NUMBER) AS undo_blocks,CAST(NULL AS NUMBER) AS undo_records"
    transaction_cap="GV_TRANSACTION_VISIBILITY" if rac else "TRANSACTION_VISIBILITY"
    if capabilities.get(transaction_cap)=="AVAILABLE":
        transaction_view="gv$transaction" if rac else "v$transaction"
        transaction_join=f" LEFT JOIN {transaction_view} t ON t.addr=s.taddr"+(" AND t.inst_id=s.inst_id" if rac else "")+(" AND t.con_id=s.con_id" if cdb else "")
        transaction_select="t.start_time AS transaction_start,t.used_ublk AS undo_blocks,t.used_urec AS undo_records"
    sql=f"""SELECT * FROM (
      SELECT {instance_expr} AS inst_id,{con_expr} AS con_id,s.sid,s.serial# AS serial_num,
             s.username,s.status,s.last_call_et,s.sql_id,s.prev_sql_id,s.wait_class,s.event,
             s.seconds_in_wait,s.blocking_instance,s.blocking_session,s.blocking_session_status,
             s.module,{transaction_select}
      FROM {session_view} s {transaction_join}
      WHERE s.type='USER' AND s.username IS NOT NULL
        AND (s.status='ACTIVE' OR s.last_call_et>=:long_idle OR s.blocking_session_status='VALID'
             OR EXISTS (SELECT 1 FROM {session_view} b WHERE b.blocking_session=s.sid
                        AND NVL(b.blocking_instance,{instance_expr})={instance_expr}
                        AND b.blocking_session_status='VALID')){container_filter}
      ORDER BY CASE WHEN s.blocking_session_status='VALID' THEN 0 WHEN s.status='ACTIVE' THEN 1 ELSE 2 END,
               NVL(s.seconds_in_wait,0) DESC,s.last_call_et DESC
    ) WHERE ROWNUM<=:max_rows"""
    binds={"long_idle":thresholds["long_session_seconds"],"max_rows":MAX_SESSION_ROWS}
    if cdb and container_id is not None: binds["current_con_id"]=int(container_id)
    return sql,binds


def _lock_edges_query(capabilities,container_id=None):
    rac=capabilities.get("RAC_VISIBILITY")=="AVAILABLE" and capabilities.get("GV_LOCK_VISIBILITY")=="AVAILABLE"
    view="gv$lock" if rac else "v$lock"
    session_view="gv$session" if rac else "v$session"
    instance="l.inst_id" if rac else "(SELECT instance_number FROM v$instance)"
    blocked_instance="b.inst_id" if rac else "(SELECT instance_number FROM v$instance)"
    blocker_con="ls.con_id" if capabilities.get("CDB_VISIBILITY")=="AVAILABLE" else "CAST(NULL AS NUMBER)"
    blocked_con="bs.con_id" if capabilities.get("CDB_VISIBILITY")=="AVAILABLE" else "CAST(NULL AS NUMBER)"
    container_filter=" AND ls.con_id=bs.con_id AND bs.con_id=:current_con_id" if capabilities.get("CDB_VISIBILITY")=="AVAILABLE" and container_id is not None else ""
    blocker_instance_join=" AND ls.inst_id=l.inst_id" if rac else ""
    blocked_instance_join=" AND bs.inst_id=b.inst_id" if rac else ""
    sql=f"""SELECT * FROM (
      SELECT {instance} AS blocking_instance,l.sid AS blocking_session,{blocker_con} AS blocking_con_id,
             {blocked_instance} AS blocked_instance,b.sid AS blocked_session,{blocked_con} AS blocked_con_id,
             b.type AS lock_type,b.ctime AS lock_wait_seconds
      FROM {view} b JOIN {view} l ON l.type=b.type AND l.id1=b.id1 AND l.id2=b.id2
      JOIN {session_view} bs ON bs.sid=b.sid{blocked_instance_join}
      JOIN {session_view} ls ON ls.sid=l.sid{blocker_instance_join}
      WHERE b.request>0 AND l.request=0 AND l.block>0
        {container_filter}
      ORDER BY b.ctime DESC
    ) WHERE ROWNUM<=:max_rows"""
    binds={"max_rows":MAX_BLOCKING_EDGES}
    if container_id is not None and capabilities.get("CDB_VISIBILITY")=="AVAILABLE": binds["current_con_id"]=int(container_id)
    return sql,binds


def _build_blocking_chains(sessions, lock_rows, previous_lookup, now, thresholds):
    node_map={}
    edges=[]
    explicit_locks={( _int(row.get("blocking_instance")),_int(row.get("blocking_session")),_int(row.get("blocked_instance")),_int(row.get("blocked_session"))) for row in (lock_rows or [])}
    for row in sessions:
        inst=_int(row.get("inst_id")); con=_int(row.get("con_id"),None); sid=_int(row.get("sid"),-1); serial=_int(row.get("serial_num"),-1)
        if sid<0: continue
        key=(inst,con,sid,serial); node_map[key]=row
        blocker=_int(row.get("blocking_session"),-1)
        if blocker<0 or str(row.get("blocking_session_status") or "").upper()!="VALID": continue
        blocker_inst=_int(row.get("blocking_instance"),inst)
        if lock_rows is not None and (blocker_inst,blocker,inst,sid) not in explicit_locks: continue
        root=(blocker_inst,con,blocker,-1)
        edges.append((root,key))
    if not edges: return [],[]
    source_keys={edge[0][:3] for edge in edges}; blocked_keys={edge[1][:3] for edge in edges}
    roots=sorted(source_keys-blocked_keys) or sorted(source_keys)
    chains=[]; observations=[]
    for root_short in roots[:MAX_BLOCKING_ROOTS]:
        root_row=next((row for key,row in node_map.items() if key[:3]==root_short),None)
        root_serial=_int((root_row or {}).get("serial_num"),-1)
        root=(root_short[0],root_short[1],root_short[2],root_serial)
        queue=[(root,0)]; seen=set(); chain_edges=[]; affected=set(); depth=0
        while queue and len(chain_edges)<MAX_BLOCKING_EDGES:
            current,current_depth=queue.pop(0)
            if current in seen: continue
            seen.add(current)
            for source,target in edges:
                if source[:3]!=current[:3]: continue
                blocked=node_map.get(target,{})
                edge={"blocking_instance":source[0],"blocking_session":source[2],"blocking_serial":current[3] if current[3]>=0 else None,"blocked_instance":target[0],"blocked_session":target[2],"blocked_serial":target[3],"con_id":target[1],"sql_id":_safe_sql_id(blocked.get("sql_id")),"wait_class":str(blocked.get("wait_class") or "")[:80],"event":str(blocked.get("event") or "")[:160],"wait_seconds":_number(blocked.get("seconds_in_wait")),"depth":current_depth+1}
                chain_edges.append(edge); affected.add(target); depth=max(depth,current_depth+1)
                queue.append((target,current_depth+1))
        root_key=f"inst={root[0]}:con={root[1] or 0}:sid={root[2]}:serial={root[3] if root[3]>=0 else 'unknown'}"
        previous=previous_lookup("BLOCKING",root_key) if previous_lookup else None
        continuous=bool(previous and 0<=float(now)-float(previous.get("observed_at",now))<=86400)
        first=float((previous or {}).get("evidence",{}).get("first_observed_epoch",now)) if continuous else float(now)
        samples=_int((previous or {}).get("metrics",{}).get("sample_count"),0)+1 if continuous else 1
        observed_duration=max(0.0,float(now)-first) if continuous else 0.0
        root_metric=root_row or {}
        max_wait=max((_number(edge.get("wait_seconds")) for edge in chain_edges),default=0.0)
        root_evidence={"root_blocker":root_key,"root_blocker_name":_safe_name(root_metric.get("username")),"root_transaction_start":_oracle_time(root_metric.get("transaction_start")),"undo_blocks":_int(root_metric.get("undo_blocks")),"undo_records":_int(root_metric.get("undo_records")),"chain_integrity":"OBSERVED_LOCK_AND_SESSION_EDGES","chain":chain_edges,"first_observed_epoch":first,"value":len(affected),"comparison_direction":"higher_is_worse","observation_note":"Observed across scheduled snapshots; sample interval is not proof of continuous blocking."}
        metrics={"affected_sessions":len(affected),"chain_depth":depth,"observed_duration_seconds":observed_duration,"seconds_in_wait":max_wait,"sample_count":samples,"value":len(affected),"comparison_direction":"higher_is_worse"}
        chains.append({"identity_key":root_key,"root":root,"root_row":root_row,"edges":chain_edges,"affected":len(affected),"depth":depth,"duration":observed_duration,"sample_count":samples,"evidence":root_evidence,"metrics":metrics})
        observations.append(_observation("BLOCKING",root_key,now=now,inst_id=root[0],con_id=root[1],metrics=metrics,evidence=root_evidence))
    return chains,observations


def _sql_stats_query(capabilities,multi_instance=False,container_id=None):
    cdb=capabilities.get("CDB_VISIBILITY")=="AVAILABLE"
    if multi_instance and capabilities.get("GV_SQL_STATS_VISIBILITY")=="AVAILABLE":
        source="gv$sqlstats"; instance_expr="s.inst_id"; group_inst="s.inst_id"; from_sql="gv$sqlstats s"
    elif not multi_instance and capabilities.get("SQL_STATS_VISIBILITY")=="AVAILABLE":
        source="v$sqlstats"; instance_expr="i.instance_number"; group_inst="i.instance_number"; from_sql="v$sqlstats s CROSS JOIN v$instance i"
    elif multi_instance and capabilities.get("GV_SQL_VISIBILITY")=="AVAILABLE":
        source="gv$sql"; instance_expr="s.inst_id"; group_inst="s.inst_id"; from_sql="gv$sql s"
    elif not multi_instance and capabilities.get("SQL_VISIBILITY")=="AVAILABLE":
        source="v$sql"; instance_expr="i.instance_number"; group_inst="i.instance_number"; from_sql="v$sql s CROSS JOIN v$instance i"
    else:
        source="gv$sqlstats" if multi_instance else "v$sqlstats"
        instance_expr="s.inst_id" if multi_instance else "i.instance_number"; group_inst=instance_expr
        from_sql=f"{source} s" if multi_instance else f"{source} s CROSS JOIN v$instance i"
    con="s.con_id" if cdb else "CAST(NULL AS NUMBER)"
    container_filter=" AND s.con_id=:current_con_id" if cdb and container_id is not None else ""
    sql=f"""SELECT * FROM (
      SELECT {instance_expr} AS inst_id,{con} AS con_id,s.sql_id,
             MAX(s.plan_hash_value) KEEP (DENSE_RANK LAST ORDER BY s.last_active_time) AS plan_hash_value,
             COUNT(DISTINCT s.plan_hash_value) AS plan_variant_count,SUM(NVL(s.executions,0)) AS executions,
             SUM(NVL(s.elapsed_time,0)) AS elapsed_microseconds,SUM(NVL(s.cpu_time,0)) AS cpu_microseconds,
             SUM(NVL(s.buffer_gets,0)) AS buffer_gets,SUM(NVL(s.disk_reads,0)) AS disk_reads,
             SUM(NVL(s.rows_processed,0)) AS rows_processed,SUM(NVL(s.parse_calls,0)) AS parse_calls,
             MAX(s.last_active_time) AS last_active_time
      FROM {from_sql}
      WHERE s.sql_id IS NOT NULL AND s.last_active_time>=SYSDATE-:window_days AND NVL(s.executions,0)>0{container_filter}
      GROUP BY {group_inst},{con},s.sql_id
      ORDER BY SUM(NVL(s.elapsed_time,0)) DESC
    ) WHERE ROWNUM<=:max_rows"""
    required=("GV_SQL_STATS_VISIBILITY",) if multi_instance and source=="gv$sqlstats" else ("GV_SQL_VISIBILITY",) if multi_instance else ("SQL_STATS_VISIBILITY",) if source=="v$sqlstats" else ("SQL_VISIBILITY",)
    binds={"window_days":SQL_HISTORY_WINDOW_DAYS,"max_rows":MAX_SQL_ROWS}
    if cdb and container_id is not None: binds["current_con_id"]=int(container_id)
    return sql,source,binds,required


def _plan_detail_query(changes,capabilities,multi_instance=False):
    if not changes: return None,{}
    view="gv$sql_plan" if multi_instance else "v$sql_plan"
    binds={}; sql_slots=[]; plan_slots=[]
    for index,item in enumerate(changes[:25]):
        binds[f"sql{index}"]=item["sql_id"]; sql_slots.append(f":sql{index}")
        binds[f"plan{index}"]=item["plan_hash"]; plan_slots.append(f":plan{index}")
    binds["max_rows"]=MAX_PLAN_STEPS
    con="con_id" if capabilities.get("CDB_VISIBILITY")=="AVAILABLE" else "CAST(NULL AS NUMBER)"
    inst="inst_id" if multi_instance else "(SELECT instance_number FROM v$instance)"
    sql=f"""SELECT * FROM (
      SELECT {inst} AS inst_id,{con} AS con_id,sql_id,plan_hash_value,id,parent_id,operation,options,
             object_owner,object_name,object_type,cardinality,cost
      FROM {view} WHERE sql_id IN ({','.join(sql_slots)}) AND plan_hash_value IN ({','.join(plan_slots)})
      ORDER BY sql_id,plan_hash_value,id
    ) WHERE ROWNUM<=:max_rows"""
    return sql,binds


def _statistics_query(sql_ids,capabilities,multi_instance=False,container_id=None):
    if not sql_ids: return None,{}
    plan_view="gv$sql_plan" if multi_instance else "v$sql_plan"
    con="p.con_id" if capabilities.get("CDB_VISIBILITY")=="AVAILABLE" else "CAST(NULL AS NUMBER)"
    inst="p.inst_id" if plan_view.startswith("gv$") else "(SELECT instance_number FROM v$instance)"
    binds={f"sql{i}":value for i,value in enumerate(sql_ids[:50])}; binds["max_rows"]=MAX_STATS_ROWS
    slots=",".join(f":sql{i}" for i in range(min(len(sql_ids),50)))
    container_filter=" AND p.con_id=:current_con_id" if capabilities.get("CDB_VISIBILITY")=="AVAILABLE" and container_id is not None else ""
    if capabilities.get("CDB_VISIBILITY")=="AVAILABLE" and container_id is not None: binds["current_con_id"]=int(container_id)
    sql=f"""SELECT * FROM (
      SELECT DISTINCT {inst} AS inst_id,{con} AS con_id,p.sql_id,p.object_owner,p.object_name,p.object_type,s.partition_name,
             s.last_analyzed,s.stale_stats,s.num_rows,s.blocks,s.sample_size
      FROM {plan_view} p JOIN dba_tab_statistics s
        ON s.owner=p.object_owner AND s.table_name=p.object_name
      WHERE p.sql_id IN ({slots}) AND p.object_owner IS NOT NULL AND p.object_name IS NOT NULL
        AND p.object_type='TABLE' AND p.object_owner NOT IN ('SYS','SYSTEM','DBSNMP','SYSMAN'){container_filter}
      ORDER BY p.object_owner,p.object_name,p.sql_id
    ) WHERE ROWNUM<=:max_rows"""
    return sql,binds


def _tablespace_query(capabilities):
    con="TO_NUMBER(SYS_CONTEXT('USERENV','CON_ID'))" if capabilities.get("CDB_VISIBILITY")=="AVAILABLE" else "CAST(NULL AS NUMBER)"
    sql=f"""SELECT * FROM (
      SELECT {con} AS con_id,t.tablespace_name,t.contents,
             NVL(df.allocated_bytes,0) AS allocated_bytes,NVL(df.max_bytes,0) AS max_bytes,
             NVL(fs.free_bytes,0) AS free_bytes,
             GREATEST(NVL(df.allocated_bytes,0)-NVL(fs.free_bytes,0),0) AS used_bytes,
             CASE WHEN NVL(df.allocated_bytes,0)>0 THEN ROUND(100*(df.allocated_bytes-NVL(fs.free_bytes,0))/df.allocated_bytes,2) ELSE 0 END AS used_percent,
             CASE WHEN NVL(df.max_bytes,0)>0 THEN ROUND(100*(df.allocated_bytes-NVL(fs.free_bytes,0))/df.max_bytes,2) ELSE 0 END AS max_capacity_percent,
             NVL(df.file_count,0) AS file_count,NVL(df.autoextend_files,0) AS autoextend_files
      FROM dba_tablespaces t
      LEFT JOIN (SELECT tablespace_name,SUM(bytes) allocated_bytes,
                 SUM(CASE WHEN autoextensible='YES' THEN GREATEST(maxbytes,bytes) ELSE bytes END) max_bytes,
                 COUNT(*) file_count,SUM(CASE WHEN autoextensible='YES' THEN 1 ELSE 0 END) autoextend_files
                 FROM dba_data_files GROUP BY tablespace_name) df ON df.tablespace_name=t.tablespace_name
      LEFT JOIN (SELECT tablespace_name,SUM(bytes) free_bytes FROM dba_free_space GROUP BY tablespace_name) fs ON fs.tablespace_name=t.tablespace_name
      WHERE t.contents IN ('PERMANENT','UNDO')
      ORDER BY used_percent DESC
    ) WHERE ROWNUM<=:max_rows"""
    return sql,{"max_rows":MAX_TABLESPACE_ROWS}


def _segment_query(object_refs):
    refs=[]; seen=set()
    for row in object_refs or []:
        owner=_safe_name(row.get("object_owner")); name=_safe_name(row.get("object_name"),256); partition=_safe_name(row.get("partition_name"),128)
        identity=(owner,name,partition)
        if owner and name and identity not in seen:
            refs.append(identity); seen.add(identity)
        if len(refs)>=50: break
    if not refs: return None,{}
    binds={"max_rows":MAX_SEGMENT_ROWS}; predicates=[]
    for index,(owner,name,partition) in enumerate(refs):
        binds[f"owner{index}"]=owner; binds[f"name{index}"]=name; binds[f"partition{index}"]=partition or None
        predicates.append(f"(owner=:owner{index} AND segment_name=:name{index} AND NVL(partition_name,'~')=NVL(:partition{index},'~'))")
    sql=f"""SELECT * FROM (
      SELECT owner,segment_name,partition_name,segment_type,tablespace_name,bytes AS segment_bytes
      FROM dba_segments
      WHERE segment_type IN ('TABLE','TABLE PARTITION','INDEX','INDEX PARTITION')
        AND ({' OR '.join(predicates)})
      ORDER BY bytes DESC
    ) WHERE ROWNUM<=:max_rows"""
    return sql,binds


def _temporary_tablespace_query(capabilities):
    con="TO_NUMBER(SYS_CONTEXT('USERENV','CON_ID'))" if capabilities.get("CDB_VISIBILITY")=="AVAILABLE" else "CAST(NULL AS NUMBER)"
    sql=f"""SELECT * FROM (
      SELECT {con} AS con_id,t.tablespace_name,t.tablespace_size AS allocated_bytes,
             NVL(f.max_bytes,t.tablespace_size) AS max_bytes,t.free_space AS free_bytes,
             GREATEST(t.tablespace_size-t.free_space,0) AS used_bytes,
             CASE WHEN t.tablespace_size>0 THEN ROUND(100*(t.tablespace_size-t.free_space)/t.tablespace_size,2) ELSE 0 END AS used_percent,
             CASE WHEN NVL(f.max_bytes,0)>0 THEN ROUND(100*(t.tablespace_size-t.free_space)/f.max_bytes,2) ELSE 0 END AS max_capacity_percent,
             t.allocated_space,f.file_count,f.autoextend_files
      FROM dba_temp_free_space t
      LEFT JOIN (SELECT tablespace_name,SUM(CASE WHEN autoextensible='YES' THEN GREATEST(maxbytes,bytes) ELSE bytes END) max_bytes,
                 COUNT(*) file_count,SUM(CASE WHEN autoextensible='YES' THEN 1 ELSE 0 END) autoextend_files
                 FROM dba_temp_files GROUP BY tablespace_name) f ON f.tablespace_name=t.tablespace_name
      ORDER BY used_percent DESC
    ) WHERE ROWNUM<=:max_rows"""
    return sql,{"max_rows":MAX_TEMP_ROWS}


def run_oracle_diagnostics(db_manager,database_id,*,audit_context=None,options=None,evidence_service=None,clock=time.time):
    """Run six isolated diagnostics and return the E13DB-012 normalized report contract."""
    context=audit_context or {}; now=float(clock()); thresholds=_thresholds(options)
    query_timeout_ms=max(250,min(30000,_int((options or {}).get("query_timeout_ms"),3000)))
    flags={"awr_license":str(os.getenv("E13DB_ORACLE_AWR_LICENSED","false")).lower()=="true","awr_privilege":str(os.getenv("E13DB_ORACLE_AWR_PRIVILEGE","false")).lower()=="true","ash_license":str(os.getenv("E13DB_ORACLE_ASH_LICENSED","false")).lower()=="true","ash_privilege":str(os.getenv("E13DB_ORACLE_ASH_PRIVILEGE","false")).lower()=="true"}
    required_privileges=sorted({"SELECT ANY DICTIONARY"})
    capability_started=time.perf_counter()
    capabilities=discover_oracle_capabilities(db_manager,database_id,license_flags=flags,required_privileges=required_privileges,timeout_ms=min(2000,query_timeout_ms))
    capability_discovery_seconds=max(0.0,time.perf_counter()-capability_started)
    capability_map=capabilities["capabilities"]
    multi_instance=_int(capabilities.get("rac_instance_count"))>1
    cluster_scope_unknown=capability_map.get("RAC_VISIBILITY")!="AVAILABLE"
    major_match=re.match(r"\s*(\d+)",str(capabilities.get("engine_version") or "")); major=int(major_match.group(1)) if major_match else None
    cdb_scope_unknown=(capabilities.get("cdb_mode")=="CDB" and capabilities.get("current_container_id") is None) or (major is not None and major>=12 and capabilities.get("cdb_mode")=="UNKNOWN" and capability_map.get("CDB_VISIBILITY") in {"UNKNOWN","INSUFFICIENT_PRIVILEGES"})
    definitions=[]; results=[]; envelopes=[]; observations=[]; query_metrics=[]; errors=[]
    def previous(category,identity): return evidence_service.previous_diagnostic(database_id,category,identity) if evidence_service else None
    def add_skip(rule_id,reason,definition=None):
        definition=definition or _rule(rule_id,"capability-gated-oracle-diagnostics-v1",required_capabilities=CAPABILITY_RULES[rule_id])
        if definition not in definitions: definitions.append(definition)
        started=time.time(); results.append(_result(definition,database_id,RuleStatus.SKIPPED,started,0,reason,metrics={"row_count":0},evidence={"capability":reason}))
    def add_error(rule_id,error,required,definition):
        state,reason=_query_error_status(error,capabilities["capabilities"],required)
        started=time.time(); results.append(_result(definition,database_id,state,started,0,reason,metrics={},evidence={"capability":reason},error=reason))
        errors.append({"rule_id":rule_id,"error_class":reason})
    def execute(rule_id,definition,sql,binds,required,max_rows=MAX_ROWS):
        if definition not in definitions: definitions.append(definition)
        reason=rule_capability_skip_reason(definition,capabilities,flags)
        if reason:
            add_skip(rule_id,reason,definition); return None
        rows,error,duration=_query(db_manager,sql,binds,max_rows=max_rows,timeout_ms=query_timeout_ms)
        query_metrics.append({"rule_id":rule_id,"duration_seconds":duration,"row_count":len(rows or []),"status":"ERROR" if error else "AVAILABLE"})
        if error:
            add_error(rule_id,error,required,definition); return None
        return rows or []

    scope_started=time.time()
    rac_scope=_rule("ORACLE_RAC_SCOPE","gv-instance-probe-v1",required_capabilities=CAPABILITY_RULES["ORACLE_RAC_SCOPE"])
    if capability_map.get("RAC_VISIBILITY")=="AVAILABLE":
        results.append(_result(rac_scope,database_id,RuleStatus.PASS,scope_started,0,f"Cluster-wide instance metadata is visible; {capabilities.get('rac_instance_count') or 0} instance(s) observed.",metrics={"row_count":_int(capabilities.get("rac_instance_count"))},evidence={"instance_scope":"ALL_INSTANCES","rac_instance_count":capabilities.get("rac_instance_count")}))
    else:
        add_skip("ORACLE_RAC_SCOPE",f"CAPABILITY_{capability_map.get('RAC_VISIBILITY','UNKNOWN')}",rac_scope)
    container_scope=_rule("ORACLE_CONTAINER_SCOPE","cdb-mode-probe-v1",required_capabilities=CAPABILITY_RULES["ORACLE_CONTAINER_SCOPE"])
    if capabilities.get("cdb_mode") in {"NON_CDB","PRE_12C_NON_CDB"}:
        results.append(_result(container_scope,database_id,RuleStatus.PASS,scope_started,0,"Target reports a non-CDB/Oracle version without multitenant support; container identity is not applicable.",metrics={"row_count":1},evidence={"container_scope":capabilities.get("cdb_mode")}))
    elif capability_map.get("CDB_VISIBILITY")=="AVAILABLE":
        results.append(_result(container_scope,database_id,RuleStatus.PASS,scope_started,0,"CDB container metadata is visible for the connected container.",metrics={"row_count":1},evidence={"container_scope":"CDB/PDB","cdb_mode":capabilities.get("cdb_mode")}))
    else:
        add_skip("ORACLE_CONTAINER_SCOPE",f"CAPABILITY_{capability_map.get('CDB_VISIBILITY','UNKNOWN')}",container_scope)

    # Session and lock visibility share one bounded result set; long active/idle
    # sessions are observations only unless an explicit blocking edge exists.
    session_caps=["GV_SESSION_VISIBILITY"] if multi_instance else ["SESSION_VISIBILITY"]
    blocking_caps=["GV_SESSION_VISIBILITY","GV_LOCK_VISIBILITY"] if multi_instance else ["SESSION_VISIBILITY","LOCK_VISIBILITY"]
    if cluster_scope_unknown:
        session_caps.append("RAC_VISIBILITY"); blocking_caps.append("RAC_VISIBILITY")
    if cdb_scope_unknown:
        session_caps.append("CDB_VISIBILITY"); blocking_caps.append("CDB_VISIBILITY")
    session_def=_rule("ORACLE_SESSIONS",str(PROBE_VIEWS)+"|long-session-identity-v1",required_capabilities=session_caps,recommendation="Take a second observation before concluding that a long-running session is stalled.")
    blocking_def=_rule("ORACLE_BLOCKING",str(PROBE_VIEWS)+"|blocking-edges-v1",severity="CRITICAL",required_capabilities=blocking_caps,recommendation="Inspect the root transaction owner, affected SQL and expected application activity; E13DB does not terminate sessions.")
    session_started=time.time(); session_sql,session_binds=_session_query(capabilities["capabilities"],thresholds,capabilities.get("current_container_id"))
    session_rows=execute("ORACLE_SESSIONS",session_def,session_sql,session_binds,session_caps,max_rows=MAX_SESSION_ROWS)
    blocked=[]; long_active_unblocked=[]; long_idle_unblocked=[]; active_count=0
    if session_rows is not None:
        for row in session_rows:
            status=str(row.get("status") or "").upper(); is_blocked=str(row.get("blocking_session_status") or "").upper()=="VALID"
            if status=="ACTIVE": active_count+=1
            if is_blocked: blocked.append(row)
            elif status=="ACTIVE" and _int(row.get("last_call_et"))>=thresholds["long_session_seconds"]: long_active_unblocked.append(row)
            elif status=="INACTIVE" and _int(row.get("last_call_et"))>=thresholds["long_session_seconds"]: long_idle_unblocked.append(row)
            inst=_int(row.get("inst_id")); con=_int(row.get("con_id"),None); sid=_int(row.get("sid"),-1); serial=_int(row.get("serial_num"),-1)
            if sid>=0:
                identity=f"session:inst={inst}:con={con or 0}:sid={sid}:serial={serial}"
                prior_session=previous("SESSION",identity); prior_evidence=(prior_session or {}).get("evidence",{}); prior_metrics=(prior_session or {}).get("metrics",{})
                current_sql=_safe_sql_id(row.get("sql_id")); prior_sql=_safe_sql_id(prior_evidence.get("sql_id"))
                if is_blocked: progress="WAITING_WITH_BLOCKER_REFERENCE"
                elif not prior_session: progress="NO_PRIOR_SAMPLE_PROGRESS_UNKNOWN"
                elif current_sql and prior_sql and current_sql!=prior_sql: progress="SQL_ID_CHANGED_BETWEEN_SAMPLES"
                elif _int(row.get("last_call_et"))<_int(prior_metrics.get("last_call_et"),0): progress="CALL_AGE_RESET_OR_CALL_CHANGED"
                else: progress="SAME_CALL_OR_IDLE_AGE_INCREASED_PROGRESS_UNKNOWN"
                first_observed=float(prior_evidence.get("first_observed_epoch",prior_session.get("observed_at",now))) if prior_session else now
                samples=_int(prior_metrics.get("sample_count"),0)+1 if prior_session else 1
                session_metrics={"last_call_et":_int(row.get("last_call_et")),"seconds_in_wait":_number(row.get("seconds_in_wait")),"sample_count":samples}
                session_evidence={"session_id":sid,"serial_num":serial,"username":_safe_name(row.get("username")),"session_status":status,"wait_class":str(row.get("wait_class") or "")[:80],"event":str(row.get("event") or "")[:160],"module":str(row.get("module") or "")[:120],"transaction_start":_oracle_time(row.get("transaction_start")),"undo_blocks":_int(row.get("undo_blocks")),"undo_records":_int(row.get("undo_records")),"sql_id":current_sql,"blocking_session":_int(row.get("blocking_session"),None),"blocking_instance":_int(row.get("blocking_instance"),None),"progress_observation":progress,"first_observed_epoch":first_observed}
                observations.append(_observation("SESSION",identity,now=now,inst_id=inst,con_id=con,sql_id=current_sql,metrics=session_metrics,evidence=session_evidence))
        if not any(result["rule_id"]=="ORACLE_SESSIONS" for result in results):
            metrics={"active_sessions":active_count,"long_running_sessions":len(long_active_unblocked),"long_idle_sessions":len(long_idle_unblocked),"blocked_sessions":len(blocked),"row_count":len(session_rows),"value":len(blocked),"comparison_direction":"higher_is_worse"}
            results.append(_result(session_def,database_id,RuleStatus.PASS,session_started,sum(item["duration_seconds"] for item in query_metrics if item["rule_id"]=="ORACLE_SESSIONS"),f"Observed {active_count} active, {len(long_active_unblocked)} long active calls, {len(long_idle_unblocked)} long-idle sessions, and {len(blocked)} explicitly blocked user session(s). A single sample cannot prove progress or a stall.",metrics=metrics,evidence={"sampled_sessions":len(session_rows),"row_limit":MAX_SESSION_ROWS,"long_session_threshold_seconds":thresholds["long_session_seconds"],"last_call_et_meaning":"call duration for ACTIVE sessions; idle duration for INACTIVE sessions","blocked_sessions_are_reported_by":"ORACLE_BLOCKING"}))
    if session_rows is None:
        if not any(result["rule_id"]=="ORACLE_SESSIONS" for result in results): add_skip("ORACLE_SESSIONS","CAPABILITY_UNAVAILABLE",session_def)
    chains=[]; block_obs=[]
    if session_rows is not None:
        lock_sql,lock_binds=_lock_edges_query(capability_map,capabilities.get("current_container_id"))
        lock_rows=execute("ORACLE_BLOCKING",blocking_def,lock_sql,lock_binds,blocking_caps,max_rows=MAX_BLOCKING_EDGES)
        if lock_rows is not None:
            chains,block_obs=_build_blocking_chains(session_rows,lock_rows,previous,now,thresholds); observations.extend(block_obs)
            block_started=session_started; status=RuleStatus.FAIL if chains else RuleStatus.PASS
            for index,chain in enumerate(chains):
                root_row=chain.get("root_row") or {}; critical=chain["affected"]>=thresholds["blocking_critical_sessions"] or chain["metrics"]["seconds_in_wait"]>=thresholds["blocking_critical_seconds"]
                severity="CRITIC" if critical else "MITJA"
                title=f"Root blocker {chain['identity_key']} affects {chain['affected']} session(s)"
                envelopes.append(_envelope("ORACLE_BLOCKING",title,owner=_safe_name(root_row.get("username")) or "ORACLE_SESSION",object_name=chain["identity_key"],object_type="SESSION_CHAIN",severity=severity,evidence=chain["evidence"],index=index))
            metrics={"blocked_sessions":len(blocked),"affected_sessions":sum(item["affected"] for item in chains),"chain_depth":max((item["depth"] for item in chains),default=0),"row_count":len(chains),"value":max((item["affected"] for item in chains),default=0),"comparison_direction":"higher_is_worse"}
            query_count=sum(item["duration_seconds"] for item in query_metrics if item["rule_id"] in {"ORACLE_SESSIONS","ORACLE_BLOCKING"})
            results.append(_result(blocking_def,database_id,status,block_started,query_count,f"Observed {len(chains)} root blocking chain(s) affecting {metrics['affected_sessions']} session(s); only edges confirmed by GV$LOCK/V$LOCK and GV$SESSION/V$SESSION are represented.",metrics=metrics,evidence={"chains":len(chains),"row_limit":MAX_BLOCKING_EDGES,"warning_seconds":thresholds["blocking_warning_seconds"],"critical_seconds":thresholds["blocking_critical_seconds"],"identity_includes":["instance","container","SID","SERIAL#"]}))
    elif not any(result["rule_id"]=="ORACLE_BLOCKING" for result in results): add_skip("ORACLE_BLOCKING","SESSION_QUERY_UNAVAILABLE",blocking_def)

    sql_started=time.time(); sql_query,sql_source,sql_binds,stats_caps=_sql_stats_query(capability_map,multi_instance,capabilities.get("current_container_id"))
    if cluster_scope_unknown: stats_caps=stats_caps+("RAC_VISIBILITY",)
    if cdb_scope_unknown: stats_caps=stats_caps+("CDB_VISIBILITY",)
    stats_definition=_rule("ORACLE_SQL_PERFORMANCE","bounded-sql-stats-cumulative-counter-v2",severity="MEDIUM",required_capabilities=stats_caps,recommendation="Compare normalized per-execution deltas over matching workload windows; do not treat lifetime counters as rates.")
    plan_definition=_rule("ORACLE_PLAN_CHANGES","plan-hash-snapshot-v2",severity="LOW",required_capabilities=stats_caps,recommendation="Compare the plans for the same SQL_ID and container; an observed plan change is not proof of a regression.")
    plan_detail_cap="GV_SQL_PLAN_VISIBILITY" if multi_instance else "SQL_PLAN_VISIBILITY"
    plan_detail_caps=(plan_detail_cap,)+( ("RAC_VISIBILITY",) if cluster_scope_unknown else ())+( ("CDB_VISIBILITY",) if cdb_scope_unknown else ())
    plan_details_definition=_rule("ORACLE_PLAN_DETAILS","bounded-plan-steps-without-predicates-v1",severity="LOW",required_capabilities=plan_detail_caps,recommendation="Review operations and object access paths; predicate literals and SQL text are not captured.")
    sql_rows=execute("ORACLE_SQL_PERFORMANCE",stats_definition,sql_query,sql_binds,stats_caps,max_rows=MAX_SQL_ROWS)
    perf_findings=[]; plan_findings=[]; sql_observations=[]; sql_ids=[]
    if sql_rows is not None:
        for index,row in enumerate(sql_rows):
            sql_id=_safe_sql_id(row.get("sql_id"));
            if not sql_id: continue
            inst=_int(row.get("inst_id")); con=_int(row.get("con_id"),None); executions=_int(row.get("executions"))
            elapsed=_number(row.get("elapsed_microseconds")); cpu=_number(row.get("cpu_microseconds")); gets=_number(row.get("buffer_gets")); reads=_number(row.get("disk_reads")); processed=_number(row.get("rows_processed")); plan_hash=_int(row.get("plan_hash_value"),0); variants=_int(row.get("plan_variant_count"),0)
            identity=f"sql:inst={inst}:con={con or 0}:sql_id={sql_id}"
            prior=previous("SQL_PERFORMANCE",identity); pmetrics=(prior or {}).get("metrics",{})
            exec_delta=executions-_int(pmetrics.get("executions")) if prior else 0
            counters=(elapsed,cpu,gets,reads,processed)
            old_counters=tuple(_number(pmetrics.get(name),-1) for name in ("elapsed_microseconds","cpu_microseconds","buffer_gets","disk_reads","rows_processed")) if prior else ()
            prior_plan_hash=_int((prior or {}).get("plan_hash"),0)
            prior_variant_count=_int(pmetrics.get("plan_variant_count"),0)
            plan_metrics_comparable=bool(prior and plan_hash and prior_plan_hash==plan_hash and variants<=1 and prior_variant_count<=1)
            counters_comparable=bool(plan_metrics_comparable and exec_delta>0 and all(old>=0 and current>=old for current,old in zip(counters,old_counters)))
            elapsed_per_exec=elapsed/executions/1e6 if executions else 0
            delta_elapsed=(elapsed-old_counters[0])/exec_delta/1e6 if counters_comparable else None
            previous_interval=_number(pmetrics.get("interval_elapsed_per_execution_seconds"),-1) if prior else -1
            interval_comparable=bool(counters_comparable and previous_interval>=0 and delta_elapsed is not None)
            previous_interval_state=str((prior or {}).get("evidence",{}).get("comparison_status") or "")
            comparable_pair=bool(interval_comparable and previous_interval_state=="COMPARABLE_INTERVALS")
            regression_percent=((delta_elapsed-previous_interval)/previous_interval*100) if comparable_pair and previous_interval>0 else None
            sql_metrics={"executions":executions,"plan_variant_count":variants,"elapsed_microseconds":elapsed,"cpu_microseconds":cpu,"buffer_gets":gets,"disk_reads":reads,"rows_processed":processed,"parse_calls":_int(row.get("parse_calls")),"execution_seconds":elapsed_per_exec,"elapsed_per_exec_seconds":elapsed_per_exec,"interval_elapsed_per_execution_seconds":delta_elapsed if counters_comparable else None,"execution_cpu_seconds":cpu/executions/1e6 if executions else 0,"buffer_gets_per_execution":gets/executions if executions else 0,"disk_reads_per_execution":reads/executions if executions else 0,"rows_per_execution":processed/executions if executions else 0,"comparison_comparable":comparable_pair,"metric_delta_percent":regression_percent or 0,"value":delta_elapsed if counters_comparable else elapsed_per_exec,"comparison_direction":"higher_is_worse" if comparable_pair else "none"}
            compare_state="COMPARABLE_INTERVALS" if comparable_pair else "INTERVAL_BASELINE_CAPTURED" if interval_comparable else "COUNTERS_INCREASED_FIRST_INTERVAL_ONLY" if counters_comparable else "NOT_COMPARABLE_COUNTER_RESET_OR_NO_NEW_EXECUTIONS" if prior else "NO_PRIOR_SNAPSHOT"
            sql_evidence={"sql_id":sql_id,"plan_hash":plan_hash or None,"plan_variant_count":variants,"last_active_time":_oracle_time(row.get("last_active_time")),"comparison_window_days":SQL_HISTORY_WINDOW_DAYS,"metric_basis":"new counter delta per new execution" if counters_comparable else "lifetime average; not a rate","comparison_status":compare_state,"prior_audit_run_id":(prior or {}).get("audit_run_id")}
            sql_observations.append(_observation("SQL_PERFORMANCE",identity,now=now,inst_id=inst,con_id=con,sql_id=sql_id,plan_hash=plan_hash or None,metrics={**sql_metrics,"value":elapsed,"elapsed_per_exec_seconds":elapsed_per_exec},evidence=sql_evidence))
            sql_ids.append(sql_id)
            high_absolute=executions>=thresholds["min_sql_executions"] and elapsed_per_exec>=thresholds["sql_elapsed_warning_seconds"]
            regressed=bool(comparable_pair and regression_percent is not None and regression_percent>=thresholds["sql_regression_percent"] and delta_elapsed>=thresholds["sql_elapsed_warning_seconds"])
            if high_absolute or regressed:
                critical=elapsed_per_exec>=thresholds["sql_elapsed_critical_seconds"] or (regressed and regression_percent>=100)
                perf_findings.append({"sql_id":sql_id,"inst_id":inst,"con_id":con,"plan_hash":plan_hash,"metrics":sql_metrics,"evidence":sql_evidence,"severity":"CRITIC" if critical else "MITJA","title":f"SQL {sql_id} has high average elapsed time" if high_absolute else f"SQL {sql_id} elapsed time regressed in comparable samples"})
            plan_identity=f"plan:inst={inst}:con={con or 0}:sql_id={sql_id}"
            prior_plan=previous("PLAN",plan_identity); previous_hash=_int((prior_plan or {}).get("plan_hash"),0)
            prior_plan_variants=_int((prior_plan or {}).get("metrics",{}).get("plan_variant_count"),0)
            plan_comparable=bool(previous_hash and plan_hash and variants<=1 and prior_plan_variants<=1)
            plan_evidence={**sql_evidence,"plan_hash":plan_hash or None,"previous_plan_hash":previous_hash or None,"plan_change_observed":bool(plan_comparable and previous_hash!=plan_hash),"plan_comparison_status":"COMPARABLE_PLAN_SNAPSHOTS" if plan_comparable else "NO_PRIOR_OR_MULTIPLE_PLAN_VARIANTS","plan_variant_count":variants}
            plan_observation=_observation("PLAN",plan_identity,now=now,inst_id=inst,con_id=con,sql_id=sql_id,plan_hash=plan_hash or None,metrics={"executions":executions,"elapsed_microseconds":elapsed,"cpu_microseconds":cpu,"buffer_gets":gets,"disk_reads":reads,"rows_processed":processed,"plan_variant_count":variants},evidence=plan_evidence)
            sql_observations.append(plan_observation)
            if plan_evidence["plan_change_observed"]:
                plan_findings.append({"sql_id":sql_id,"inst_id":inst,"con_id":con,"plan_hash":plan_hash,"previous_plan_hash":previous_hash,"metrics":sql_metrics,"evidence":plan_evidence,"observation":plan_observation,"title":f"SQL {sql_id} execution plan changed","severity":"MITJA"})
        plan_detail_error=None; plan_detail_rows=[]; plan_detail_requested=set()
        plan_detail_skip_reason=rule_capability_skip_reason(plan_details_definition,capabilities,flags)
        if plan_findings and not plan_detail_skip_reason:
            plan_detail_requested={item["sql_id"] for item in plan_findings[:25]}
            detail_sql,detail_binds=_plan_detail_query(plan_findings,capability_map,multi_instance)
            detail_rows,detail_error,detail_duration=_query(db_manager,detail_sql,detail_binds,max_rows=MAX_PLAN_STEPS,timeout_ms=query_timeout_ms)
            plan_detail_error=detail_error; plan_detail_rows=detail_rows or []
            query_metrics.append({"rule_id":"ORACLE_PLAN_CHANGES","duration_seconds":detail_duration,"row_count":len(detail_rows or []),"status":"ERROR" if detail_error else "AVAILABLE"})
            grouped={}
            for step in detail_rows or []:
                key=_safe_sql_id(step.get("sql_id"))
                grouped.setdefault(key,[]).append({"id":_int(step.get("id")),"parent_id":_int(step.get("parent_id"),None),"operation":str(step.get("operation") or "")[:80],"options":str(step.get("options") or "")[:80],"object_owner":_safe_name(step.get("object_owner")),"object_name":_safe_name(step.get("object_name"),256),"object_type":str(step.get("object_type") or "")[:40],"cardinality":_int(step.get("cardinality"),None),"cost":_int(step.get("cost"),None),"plan_hash":_int(step.get("plan_hash_value"))})
            if detail_error:
                capabilities["capabilities"][plan_detail_cap]="INSUFFICIENT_PRIVILEGES" if "ORA-01031" in detail_error.upper() else "UNKNOWN"
                errors.append({"rule_id":"ORACLE_PLAN_CHANGES","error_class":"PLAN_STEP_QUERY_FAILED"})
            for item in plan_findings:
                item["evidence"]["plan_steps_status"]="ERROR" if detail_error else "AVAILABLE" if grouped.get(item["sql_id"]) else "NO_ROWS_OR_OUTSIDE_DETAIL_BUDGET" if item["sql_id"] not in plan_detail_requested else "NO_PLAN_ROWS_FOR_HASH"
                item["evidence"]["plan_steps"]=grouped.get(item["sql_id"],[])[:MAX_PLAN_STEPS]
                item["observation"]["evidence"]=item["evidence"]
        elif plan_findings:
            for item in plan_findings: item["evidence"]["plan_steps_status"]=capabilities["capabilities"].get(plan_detail_cap,"UNKNOWN")
        if not plan_findings:
            results.append(_result(plan_details_definition,database_id,RuleStatus.PASS,sql_started,0,"No SQL plan-hash change candidate required plan-step inspection in this sample.",metrics={"row_count":0},evidence={"query_performed":False,"reason":"no_plan_change_candidate"}))
        elif plan_detail_error:
            add_error("ORACLE_PLAN_DETAILS",plan_detail_error,(plan_detail_cap,),plan_details_definition)
        elif plan_detail_skip_reason:
            add_skip("ORACLE_PLAN_DETAILS",plan_detail_skip_reason,plan_details_definition)
        elif len(plan_detail_requested)!=len(plan_findings) or any(not item["evidence"].get("plan_steps") for item in plan_findings):
            add_skip("ORACLE_PLAN_DETAILS","PLAN_STEPS_NOT_AVAILABLE_OR_DETAIL_BUDGET_EXCEEDED",plan_details_definition)
        else:
            results.append(_result(plan_details_definition,database_id,RuleStatus.PASS,sql_started,sum(item["duration_seconds"] for item in query_metrics if item["rule_id"]=="ORACLE_PLAN_CHANGES"),f"Captured {len(plan_detail_rows)} bounded plan-step row(s) without predicates or SQL text.",metrics={"row_count":len(plan_detail_rows)},evidence={"row_limit":MAX_PLAN_STEPS,"captured_fields":["operation","options","object owner/name/type","cardinality","cost"]}))
        observations.extend(sql_observations)
        for rule_id,definition,items,status in (("ORACLE_SQL_PERFORMANCE",stats_definition,perf_findings,RuleStatus.WARN if perf_findings else RuleStatus.PASS),("ORACLE_PLAN_CHANGES",plan_definition,plan_findings,RuleStatus.WARN if plan_findings else RuleStatus.PASS)):
            for index,item in enumerate(items):
                severity=item["severity"]
                title=item["title"]
                evidence={**item["evidence"],"sql_id":item["sql_id"],"inst_id":item["inst_id"],"con_id":item["con_id"],"plan_hash":item.get("plan_hash"),"previous_plan_hash":item.get("previous_plan_hash"),**item["metrics"]}
                envelopes.append(_envelope(rule_id,title,owner="SQL",object_name=f"SQL_ID:{item['sql_id']}:INST:{item['inst_id']}:CON:{item['con_id'] or 0}",object_type="SQL",severity=severity,evidence=evidence,index=index))
            total_elapsed=sum(_number(item.get("elapsed_microseconds")) for item in (row for row in sql_rows))
            result_metrics={"row_count":len(items),"executions":sum(_int(row.get("executions")) for row in sql_rows),"elapsed_microseconds":total_elapsed,"value":len(items),"comparison_direction":"higher_is_worse"}
            results.append(_result(definition,database_id,status,sql_started,sum(item["duration_seconds"] for item in query_metrics if item["rule_id"]==rule_id),f"Observed {len(sql_rows)} bounded SQL aggregate(s); {len(items)} performance/plan observation(s) crossed the configured diagnostic criteria.",metrics=result_metrics,evidence={"sql_source_view":sql_source,"row_limit":MAX_ROWS,"comparison_policy":"cumulative counters are compared only when executions increase and no counter resets"}))
    elif not any(result["rule_id"]=="ORACLE_SQL_PERFORMANCE" for result in results):
        add_skip("ORACLE_SQL_PERFORMANCE",rule_capability_skip_reason(stats_definition,capabilities,flags) or "SQL_STATS_UNAVAILABLE",stats_definition)
        add_skip("ORACLE_PLAN_CHANGES",rule_capability_skip_reason(plan_definition,capabilities,flags) or "SQL_STATS_UNAVAILABLE",plan_definition)
        add_skip("ORACLE_PLAN_DETAILS","SQL_STATS_UNAVAILABLE",plan_details_definition)

    stats_caps=("GV_SQL_PLAN_VISIBILITY","STATISTICS_VISIBILITY") if multi_instance else CAPABILITY_RULES["ORACLE_OBJECT_STATISTICS"]
    if cluster_scope_unknown: stats_caps=stats_caps+("RAC_VISIBILITY",)
    if cdb_scope_unknown: stats_caps=stats_caps+("CDB_VISIBILITY",)
    stats_definition=_rule("ORACLE_OBJECT_STATISTICS","sql-plan-object-statistics-v1",severity="MEDIUM",required_capabilities=stats_caps,recommendation="Review statistics for workload-implicated objects with the DBA maintenance policy; do not infer a plan cause from staleness alone.")
    stats_started=time.time(); stats_sql,stats_binds=_statistics_query(sql_ids,capabilities["capabilities"],multi_instance,capabilities.get("current_container_id"))
    stats_rows=execute("ORACLE_OBJECT_STATISTICS",stats_definition,stats_sql,stats_binds,stats_caps,max_rows=MAX_STATS_ROWS) if stats_sql else []
    if stats_sql is None and not any(result["rule_id"]=="ORACLE_OBJECT_STATISTICS" for result in results):
        add_skip("ORACLE_OBJECT_STATISTICS","NO_SQL_PLAN_OBJECTS_TO_CORRELATE",stats_definition)
    elif stats_rows is not None:
        stale=[]
        for index,row in enumerate(stats_rows):
            owner=_safe_name(row.get("object_owner")); obj=_safe_name(row.get("object_name"),256); partition=_safe_name(row.get("partition_name"),128); sql_id=_safe_sql_id(row.get("sql_id")); inst=_int(row.get("inst_id")); con=_int(row.get("con_id"),None)
            if not owner or not obj: continue
            analyzed=row.get("last_analyzed"); age_days=max(0.0,(datetime.now().replace(tzinfo=None)-analyzed.replace(tzinfo=None)).total_seconds()/86400) if isinstance(analyzed,datetime) else 0.0
            stale_value=str(row.get("stale_stats") or "").upper() in {"YES","TRUE","STALE"}
            identity=f"stats:con={con or 0}:owner={owner}:object={obj}:partition={partition}"
            metrics={"statistics_age_days":age_days,"num_rows":_int(row.get("num_rows")),"blocks":_int(row.get("blocks")),"sample_size":_int(row.get("sample_size")),"value":age_days,"comparison_direction":"higher_is_worse"}
            evidence={"object_owner":owner,"object_name":obj,"partition_name":partition,"object_type":str(row.get("object_type") or ("TABLE PARTITION" if partition else "TABLE"))[:32],"sql_id":sql_id,"con_id":con,"last_analyzed":_oracle_time(analyzed),"stale_stats":stale_value,"sample_size":metrics["sample_size"],"plan_related":True}
            observations.append(_observation("STATISTICS",identity,now=now,inst_id=inst,con_id=con,sql_id=sql_id,owner=owner,object_name=obj,metrics=metrics,evidence=evidence))
            if stale_value:
                stale.append({"owner":owner,"object_name":obj,"sql_id":sql_id,"con_id":con,"metrics":metrics,"evidence":evidence})
        for index,item in enumerate(stale):
            diagnostic_object=item["object_name"]+(f"@{_safe_name(item['evidence'].get('partition_name'),128)}" if item["evidence"].get("partition_name") else "")+(f"@CON{item['con_id']}" if item.get("con_id") is not None else "")
            envelopes.append(_envelope("ORACLE_OBJECT_STATISTICS",f"Stale statistics observed for workload-related object {item['owner']}.{item['object_name']}",owner=item["owner"],object_name=diagnostic_object,object_type=item["evidence"].get("object_type") or "TABLE",severity="MITJA",evidence={**item["evidence"],**item["metrics"]},index=index))
        results.append(_result(stats_definition,database_id,RuleStatus.WARN if stale else RuleStatus.PASS,stats_started,sum(item["duration_seconds"] for item in query_metrics if item["rule_id"]=="ORACLE_OBJECT_STATISTICS"),f"Observed {len(stats_rows)} object-statistics row(s) for SQL-plan-referenced objects; {len(stale)} were explicitly marked stale.",metrics={"row_count":len(stats_rows),"stale_statistics":len(stale),"value":len(stale),"comparison_direction":"higher_is_worse"},evidence={"sql_ids_correlated":len(set(sql_ids)),"row_limit":MAX_ROWS}))

    segment_caps=CAPABILITY_RULES["ORACLE_SEGMENT_GROWTH"]+(("CDB_VISIBILITY",) if cdb_scope_unknown else ())
    segment_definition=_rule("ORACLE_SEGMENT_GROWTH","bounded-top-segment-size-history-v1",severity="MEDIUM",required_capabilities=segment_caps,recommendation="Confirm whether the observed segment growth is expected; size deltas are snapshots, not forecasts.")
    segment_started=time.time(); segment_sql,segment_binds=_segment_query(stats_rows or [])
    if segment_sql is None:
        add_skip("ORACLE_SEGMENT_GROWTH","NO_WORKLOAD_REFERENCED_OBJECTS",segment_definition); segment_rows=None
    else:
        segment_rows=execute("ORACLE_SEGMENT_GROWTH",segment_definition,segment_sql,segment_binds,segment_caps,max_rows=MAX_SEGMENT_ROWS)
    if segment_rows is not None:
        growth_findings=[]
        for index,row in enumerate(segment_rows):
            owner=_safe_name(row.get("owner")); name=_safe_name(row.get("segment_name"),256)
            if not owner or not name: continue
            partition=_safe_name(row.get("partition_name"),128); segment_type=str(row.get("segment_type") or "")[:48]
            tablespace=_safe_name(row.get("tablespace_name")); segment_bytes=max(0,_number(row.get("segment_bytes")))
            segment_con=capabilities.get("current_container_id") if capabilities.get("cdb_mode")=="CDB" else None
            identity=f"segment:con={segment_con or 0}:owner={owner}:name={name}:partition={partition}:type={segment_type}"
            prior_segment=previous("SEGMENT_GROWTH",identity); old_bytes=_number((prior_segment or {}).get("metrics",{}).get("segment_bytes"),-1)
            comparable=bool(prior_segment and old_bytes>=0 and segment_bytes>=old_bytes)
            growth=max(0,segment_bytes-old_bytes) if comparable else 0; growth_percent=(growth/old_bytes*100) if comparable and old_bytes>0 else 0
            metrics={"segment_bytes":segment_bytes,"segment_growth_bytes":growth,"growth_bytes":growth,"growth_percent":growth_percent,"comparison_comparable":comparable,"sample_count":_int((prior_segment or {}).get("metrics",{}).get("sample_count"))+1,"value":growth,"comparison_direction":"higher_is_worse"}
            evidence={"object_owner":owner,"object_name":name,"partition_name":partition,"segment_type":segment_type,"tablespace":tablespace,"comparison_status":"COMPARABLE_SNAPSHOTS" if comparable else "BASELINE_ONLY","prior_audit_run_id":(prior_segment or {}).get("audit_run_id"),"first_observed_at":(prior_segment or {}).get("evidence",{}).get("first_observed_at",now),"last_observed_at":now}
            observations.append(_observation("SEGMENT_GROWTH",identity,now=now,con_id=segment_con,owner=owner,object_name=name,metrics=metrics,evidence=evidence))
            if comparable and growth>=thresholds["segment_growth_warning_bytes"] and growth_percent>=thresholds["segment_growth_warning_percent"]:
                severity="CRITIC" if growth>=thresholds["segment_growth_critical_bytes"] and growth_percent>=thresholds["segment_growth_critical_percent"] else "MITJA"
                growth_findings.append({"owner":owner,"name":name,"partition":partition,"type":segment_type,"con_id":segment_con,"metrics":metrics,"evidence":evidence,"severity":severity})
        for index,item in enumerate(growth_findings):
            object_name=item["name"]+(f"@{item['partition']}" if item["partition"] else "")
            if item.get("con_id") is not None: object_name+=f"@CON{item['con_id']}"
            envelopes.append(_envelope("ORACLE_SEGMENT_GROWTH",f"Segment {item['owner']}.{item['name']} grew {item['metrics']['growth_bytes']:.0f} bytes between comparable audits",owner=item["owner"],object_name=object_name,object_type=item["type"],severity=item["severity"],evidence={**item["evidence"],**item["metrics"],"con_id":item.get("con_id")},index=index))
        results.append(_result(segment_definition,database_id,RuleStatus.FAIL if any(item["severity"]=="CRITIC" for item in growth_findings) else RuleStatus.WARN if growth_findings else RuleStatus.PASS,segment_started,sum(item["duration_seconds"] for item in query_metrics if item["rule_id"]=="ORACLE_SEGMENT_GROWTH"),f"Observed {len(segment_rows)} bounded top segments; {len(growth_findings)} grew beyond configured criteria across comparable audit snapshots.",metrics={"row_count":len(segment_rows),"growth_findings":len(growth_findings),"value":sum(item["metrics"]["growth_bytes"] for item in growth_findings),"comparison_direction":"higher_is_worse"},evidence={"row_limit":MAX_ROWS,"growth_warning_bytes":thresholds["segment_growth_warning_bytes"],"growth_warning_percent":thresholds["segment_growth_warning_percent"],"growth_critical_bytes":thresholds["segment_growth_critical_bytes"],"growth_critical_percent":thresholds["segment_growth_critical_percent"],"forecasting":"not performed"}))

    capacity_caps=CAPABILITY_RULES["ORACLE_CAPACITY"]+(("CDB_VISIBILITY",) if cdb_scope_unknown else ())
    capacity_definition=_rule("ORACLE_CAPACITY","bounded-tablespace-capacity-v1",severity="MEDIUM",required_capabilities=capacity_caps,recommendation="Review available space, datafile autoextend limits and approved capacity plans; E13DB does not resize files.")
    capacity_started=time.time(); capacity_sql,capacity_binds=_tablespace_query(capabilities["capabilities"])
    capacity_rows=execute("ORACLE_CAPACITY",capacity_definition,capacity_sql,capacity_binds,capacity_caps,max_rows=MAX_TABLESPACE_ROWS)
    capacity_findings=[]
    if capacity_rows is not None:
        for index,row in enumerate(capacity_rows):
            name=_safe_name(row.get("tablespace_name")); con=_int(row.get("con_id"),None)
            if not name: continue
            allocated=_number(row.get("allocated_bytes")); free=_number(row.get("free_bytes")); used=max(0,allocated-free)
            used_percent=100*used/allocated if allocated>0 else 0.0
            max_bytes=_number(row.get("max_bytes")); max_capacity_percent=100*used/max_bytes if max_bytes>0 else used_percent
            identity=f"capacity:con={con or 0}:tablespace={name}"
            previous_capacity=previous("CAPACITY",identity); old_used=_number((previous_capacity or {}).get("metrics",{}).get("used_bytes"),-1)
            comparable=bool(previous_capacity and used>=0 and old_used>=0)
            metrics={"allocated_bytes":allocated,"used_bytes":used,"free_bytes":free,"max_bytes":max_bytes,"used_percent":used_percent,"max_capacity_percent":max_capacity_percent,"file_count":_int(row.get("file_count")),"autoextend_files":_int(row.get("autoextend_files")),"growth_bytes":max(0,used-old_used) if comparable else 0,"sample_count":_int((previous_capacity or {}).get("metrics",{}).get("sample_count"))+1,"value":used_percent,"comparison_direction":"higher_is_worse"}
            evidence={"tablespace":name,"con_id":con if con is not None else capabilities.get("current_container_id"),"contents":str(row.get("contents") or "")[:32],"autoextensible":metrics["autoextend_files"]>0,"capacity_comparable":comparable,"prior_audit_run_id":(previous_capacity or {}).get("audit_run_id"),"first_observed_at":(previous_capacity or {}).get("evidence",{}).get("first_observed_at",now),"last_observed_at":now}
            observations.append(_observation("CAPACITY",identity,now=now,con_id=con if con is not None else capabilities.get("current_container_id"),owner="TABLESPACE",object_name=name,metrics=metrics,evidence=evidence))
            if used_percent>=thresholds["tablespace_warning_percent"]:
                capacity_findings.append({"name":name,"metrics":metrics,"evidence":evidence,"severity":"CRITIC" if used_percent>=thresholds["tablespace_critical_percent"] else "MITJA"})
        for index,item in enumerate(capacity_findings):
            object_name=item["name"]+(f"@CON{item['evidence'].get('con_id')}" if item["evidence"].get("con_id") is not None else "")
            envelopes.append(_envelope("ORACLE_CAPACITY",f"Tablespace {item['name']} is {item['metrics']['used_percent']:.1f}% allocated",owner="TABLESPACE",object_name=object_name,object_type="TABLESPACE",severity=item["severity"],evidence={"tablespace":item["name"],**item["metrics"],**item["evidence"]},index=index))
        results.append(_result(capacity_definition,database_id,RuleStatus.FAIL if any(item["severity"]=="CRITIC" for item in capacity_findings) else RuleStatus.WARN if capacity_findings else RuleStatus.PASS,capacity_started,sum(item["duration_seconds"] for item in query_metrics if item["rule_id"]=="ORACLE_CAPACITY"),f"Observed {len(capacity_rows)} permanent/undo tablespaces; {len(capacity_findings)} crossed configured capacity warning/critical thresholds.",metrics={"row_count":len(capacity_rows),"tablespaces_over_warning":len(capacity_findings),"value":max((item["metrics"]["used_percent"] for item in capacity_findings),default=0),"comparison_direction":"higher_is_worse"},evidence={"warning_percent":thresholds["tablespace_warning_percent"],"critical_percent":thresholds["tablespace_critical_percent"],"includes":"PERMANENT and UNDO; TEMP not included in this rule version"}))
    elif not any(result["rule_id"]=="ORACLE_CAPACITY" for result in results): add_skip("ORACLE_CAPACITY","STORAGE_UNAVAILABLE",capacity_definition)

    temp_caps=CAPABILITY_RULES["ORACLE_TEMP_CAPACITY"]+(("CDB_VISIBILITY",) if cdb_scope_unknown else ())
    temp_definition=_rule("ORACLE_TEMP_CAPACITY","bounded-dba-temp-free-space-v1",severity="MEDIUM",required_capabilities=temp_caps,recommendation="Review active temporary-space consumers and tempfile limits; E13DB does not resize files or cancel sessions.")
    temp_sql,temp_binds=_temporary_tablespace_query(capability_map)
    temp_started=time.time(); temp_rows=execute("ORACLE_TEMP_CAPACITY",temp_definition,temp_sql,temp_binds,temp_caps,max_rows=MAX_TEMP_ROWS)
    if temp_rows is not None:
        temp_findings=[]
        for index,row in enumerate(temp_rows):
            name=_safe_name(row.get("tablespace_name")); con=_int(row.get("con_id"),None)
            if not name: continue
            size=_number(row.get("allocated_bytes")); free=_number(row.get("free_bytes")); used=max(0,size-free)
            used_percent=100*used/size if size>0 else 0.0
            max_bytes=_number(row.get("max_bytes"),size); max_capacity_percent=100*used/max_bytes if max_bytes>0 else used_percent
            identity=f"capacity:con={con or 0}:temp_tablespace={name}"
            metrics={"allocated_bytes":size,"used_bytes":used,"free_bytes":free,"max_bytes":max_bytes,"used_percent":used_percent,"max_capacity_percent":max_capacity_percent,"file_count":_int(row.get("file_count")),"autoextend_files":_int(row.get("autoextend_files")),"growth_bytes":0,"value":used_percent,"comparison_direction":"higher_is_worse"}
            evidence={"tablespace":name,"con_id":con if con is not None else capabilities.get("current_container_id"),"contents":"TEMPORARY","capacity_basis":"DBA_TEMP_FREE_SPACE","allocated_space_bytes":_number(row.get("allocated_space")),"autoextensible":metrics["autoextend_files"]>0}
            observations.append(_observation("CAPACITY",identity,now=now,con_id=con if con is not None else capabilities.get("current_container_id"),owner="TABLESPACE",object_name=name,metrics=metrics,evidence=evidence))
            if used_percent>=thresholds["tablespace_warning_percent"]:
                temp_findings.append({"name":name,"metrics":metrics,"evidence":evidence,"severity":"CRITIC" if used_percent>=thresholds["tablespace_critical_percent"] else "MITJA"})
        for index,item in enumerate(temp_findings):
            object_name=item["name"]+(f"@CON{item['evidence'].get('con_id')}" if item["evidence"].get("con_id") is not None else "")
            envelopes.append(_envelope("ORACLE_TEMP_CAPACITY",f"Temporary tablespace {item['name']} is {item['metrics']['used_percent']:.1f}% used",owner="TABLESPACE",object_name=object_name,object_type="TEMPORARY TABLESPACE",severity=item["severity"],evidence={"tablespace":item["name"],**item["metrics"],**item["evidence"]},index=index))
        results.append(_result(temp_definition,database_id,RuleStatus.FAIL if any(item["severity"]=="CRITIC" for item in temp_findings) else RuleStatus.WARN if temp_findings else RuleStatus.PASS,temp_started,sum(item["duration_seconds"] for item in query_metrics if item["rule_id"]=="ORACLE_TEMP_CAPACITY"),f"Observed {len(temp_rows)} temporary tablespace(s); {len(temp_findings)} crossed configured capacity thresholds.",metrics={"row_count":len(temp_rows),"tablespaces_over_warning":len(temp_findings),"value":max((item["metrics"]["used_percent"] for item in temp_findings),default=0),"comparison_direction":"higher_is_worse"},evidence={"warning_percent":thresholds["tablespace_warning_percent"],"critical_percent":thresholds["tablespace_critical_percent"],"tempfile_autoextend_limits":"observed through DBA_TEMP_FILES"}))

    rule_results=sorted(results,key=lambda item:item["rule_id"])
    rule_pack=hashlib.sha256(json.dumps({"rules":rule_pack_identity(definitions),"diagnostic_options":thresholds,"instance_scope":"RAC" if multi_instance else "CURRENT_INSTANCE","container_id":capabilities.get("current_container_id"),"capabilities":capability_map},sort_keys=True,separators=(",",":"),default=str).encode("utf-8")).hexdigest()
    summary={"checks_total":len(rule_results),"checks_pass":sum(item["status"]=="PASS" for item in rule_results),"checks_warn":sum(item["status"]=="WARN" for item in rule_results),"checks_fail":sum(item["status"]=="FAIL" for item in rule_results),"checks_error":sum(item["status"]=="ERROR" for item in rule_results),"checks_skipped":sum(item["status"]=="SKIPPED" for item in rule_results),"diagnostic_observations":len(observations),"finding_envelopes":len(envelopes),"query_count":len(query_metrics),"query_budget":8,"query_metrics":query_metrics,"capability_probe_count":capabilities.get("probe_count",0),"capability_discovery_seconds":round(capability_discovery_seconds,3)}
    connection_class=capabilities.get("connection_class","UNKNOWN")
    audit_state="SUCCESS" if capabilities.get("connection_status")=="AVAILABLE" else "FAILED"
    failure_class={"CONFIGURATION_ERROR":"CONFIGURATION_ERROR","UNREACHABLE":"UNREACHABLE"}.get(connection_class,"ORACLE_CONNECTION_UNKNOWN") if audit_state=="FAILED" else None
    return {"audit_type":"oracle_diagnostics","audit_state":audit_state,"failure_class":failure_class,"audit_run_id":str(context.get("audit_run_id") or ""),"trigger_type":str(context.get("trigger_type") or "MANUAL").upper(),"trigger_reference":str(context.get("trigger_reference") or ""),"runtime_identity":runtime_identity(),"rule_pack_identity":rule_pack,"capability_snapshot":capabilities,"context":{"profile":str(database_id),"generated_at":now,"diagnostic_options":thresholds,"scope":capabilities.get("cdb_scope") or "connected session's effective Oracle visibility"},"summary":summary,"rule_results":rule_results,"finding_envelopes":envelopes[:500],"diagnostic_observations":observations[:500],"diagnostic_errors":errors,"errors":errors,"executed_checks":[],"query_metrics":query_metrics,"coverage_state":"DEGRADED" if audit_state=="FAILED" or summary["checks_error"] or summary["checks_skipped"] or errors else "FULL"}


def render_diagnostic_markdown(report):
    """Operator report deliberately includes no SQL text, bind values or raw rows."""
    summary=report.get("summary") or {}; caps=(report.get("capability_snapshot") or {}).get("capabilities") or {}
    lines=["# Oracle operational diagnostics", "", f"Target: {report.get('context',{}).get('profile','UNKNOWN')}", f"AuditRun: {report.get('audit_run_id','UNKNOWN')}", f"Coverage: {report.get('coverage_state','UNKNOWN')}", "", "## Findings"]
    envelopes=report.get("finding_envelopes") or []
    if envelopes:
        lines.extend(f"- {item.get('sql_severity','INFO')}: {item.get('title') or item.get('check_id')} — {item.get('object_name') or item.get('schema') or 'database'}" for item in envelopes[:100])
    else: lines.append("- No diagnostic threshold or blocking condition was observed.")
    lines.extend(["", "## Diagnostic coverage"])
    for item in report.get("rule_results") or []:
        lines.append(f"- {item.get('rule_id')}: {item.get('status')} — {item.get('summary') or '-'}")
    lines.extend(["", "## Oracle capabilities"])
    for key,value in sorted(caps.items()): lines.append(f"- {key}: {value}")
    lines.extend(["", "## Audit summary", f"- Rules: {summary.get('checks_total',0)}; pass {summary.get('checks_pass',0)}, warn {summary.get('checks_warn',0)}, fail {summary.get('checks_fail',0)}, error {summary.get('checks_error',0)}, skipped {summary.get('checks_skipped',0)}.", f"- Bounded diagnostic observations: {summary.get('diagnostic_observations',0)}.", f"- Data-query budget: {summary.get('query_count',0)}/{summary.get('query_budget',0)}; capability probes: {summary.get('capability_probe_count',0)} in {summary.get('capability_discovery_seconds',0)} seconds.", "", "Blocking, plan and metric relationships are observed facts/correlations, not confirmed root causes. No remediation is executed."])
    return "\n".join(lines)
