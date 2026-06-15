import re
from typing import Any, Dict, List, Optional, Tuple

from src.analytics.deep_audit_plan_queries import DeepAuditPlanQueries


class AuditEngine:
    """Motor d'auditoria profunda d'esquemes Oracle basat en el pla Q01-Q19."""

    def __init__(self, db_manager=None):
        self.dbm = db_manager

    def _safe_unpack(self, result: Any) -> Tuple[Any, Any]:
        if isinstance(result, tuple) and len(result) == 2:
            return result
        return None, None

    def _run_query(self, name: str, sql: str, params: Dict[str, Any], optional: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not self.dbm:
            return [], {"query": name, "status": "skipped", "rows": 0, "optional": optional, "error": "no_db_manager"}

        bind_names = set(re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", sql or ""))
        safe_params = {k: v for k, v in (params or {}).items() if k in bind_names}
        raw_data, raw_cols = self._safe_unpack(self.dbm.execute_query(sql, safe_params))
        if raw_data is None or raw_cols is None:
            status = "optional_error" if optional else "error"
            err = getattr(self.dbm, "last_error", None) or "query_execution_failed"
            return [], {"query": name, "status": status, "rows": 0, "optional": optional, "error": err}

        rows = [dict(zip(raw_cols, row)) for row in raw_data if row is not None]
        return rows, {"query": name, "status": "ok", "rows": len(rows), "optional": optional}

    @staticmethod
    def _query_health(executed_queries: List[Dict[str, Any]]) -> Dict[str, int]:
        mandatory_errors = len([
            q for q in executed_queries
            if not q.get("optional") and q.get("status") in ("error", "skipped")
        ])
        optional_errors = len([q for q in executed_queries if q.get("status") == "optional_error"])
        ok_queries = len([q for q in executed_queries if q.get("status") == "ok"])
        return {
            "mandatory_errors": mandatory_errors,
            "optional_errors": optional_errors,
            "ok_queries": ok_queries,
            "total_queries": len(executed_queries),
        }

    @staticmethod
    def _as_number(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _derive_final_decision(self, data: Dict[str, Any]) -> str:
        summary = data.get("summary") or {}

        blockers = [
            self._as_number(summary.get("INBOUND_REFERENCES"), 0) > 0,
            self._as_number(summary.get("ACTIVE_JOBS"), 0) > 0,
            self._as_number(summary.get("JOBS_STARTED_RECENT"), 0) > 0,
            self._as_number(summary.get("APEX_APPLICATIONS"), 0) > 0,
            self._as_number(summary.get("ENABLED_TRIGGERS"), 0) > 0,
            len(data.get("code_refs") or []) > 0,
        ]
        if any(blockers):
            return "NO ELIMINAR"

        if self._as_number(summary.get("ALARM_1_ACTIVITY_RECENT"), 0) > 0:
            return "PRECAUCIO"

        if self._as_number(summary.get("DAYS_SINCE_NEWEST_DDL"), 999) <= 180:
            return "PRECAUCIO"

        return "ELIMINAR"

    def _calculate_score_v4(self, data: Dict[str, Any]) -> Tuple[int, List[Dict[str, Any]], Dict[str, Any]]:
        summary = data.get("summary") or {}
        breakdown: List[Dict[str, Any]] = []
        score = 0

        inbound = self._as_number(summary.get("INBOUND_REFERENCES"), 0)
        outbound = self._as_number(summary.get("EXTERNAL_DEPENDENCIES_OUT"), 0)
        active_jobs = self._as_number(summary.get("ACTIVE_JOBS"), 0)
        triggers = self._as_number(summary.get("ENABLED_TRIGGERS"), 0)
        apex_apps = self._as_number(summary.get("APEX_APPLICATIONS"), 0)
        dml_mods = self._as_number(summary.get("TABLES_WITH_MODS_30D"), 0)
        stats_recent = self._as_number(summary.get("TABLES_STATS_RECENT_30D"), 0)
        login_days = self._as_number(summary.get("LAST_LOGIN_DAYS"), 999)
        size_gb = self._as_number(summary.get("SIZE_GB"), 0)

        if dml_mods == 0 and stats_recent == 0:
            score += 25
            breakdown.append({"factor": "Activitat DML", "pts": 25, "desc": "Sense modificacions ni estadistiques recents"})
        else:
            breakdown.append({"factor": "Activitat DML", "pts": 0, "desc": "Activitat recent detectada"})

        dep_penalty = min(30, int(inbound * 10 + outbound * 2))
        dep_pts = max(0, 30 - dep_penalty)
        score += dep_pts
        breakdown.append({"factor": "Dependencies", "pts": dep_pts, "desc": f"Entrants={int(inbound)}, sortints={int(outbound)}"})

        if login_days > 180:
            score += 10
            breakdown.append({"factor": "Login", "pts": 10, "desc": "Inactiu >180 dies"})
        else:
            breakdown.append({"factor": "Login", "pts": 0, "desc": "Login recent"})

        if size_gb < 0.05:
            score += 20
            breakdown.append({"factor": "Mida", "pts": 20, "desc": "<50MB"})
        elif size_gb < 1:
            score += 10
            breakdown.append({"factor": "Mida", "pts": 10, "desc": "<1GB"})
        else:
            breakdown.append({"factor": "Mida", "pts": 0, "desc": "Mida significativa"})

        blockers = 0
        if active_jobs > 0:
            blockers += 1
        if triggers > 0:
            blockers += 1
        if apex_apps > 0:
            blockers += 1
        if len(data.get("code_refs") or []) > 0:
            blockers += 1

        if blockers == 0:
            score += 15
            breakdown.append({"factor": "Automatismes/Codi", "pts": 15, "desc": "Sense jobs/triggers/APEX/code refs"})
        else:
            score -= min(40, blockers * 10)
            breakdown.append({"factor": "Automatismes/Codi", "pts": -min(40, blockers * 10), "desc": "Hi ha bloquejadors operatius"})

        raw_score = int(score)
        final_score = max(0, min(100, raw_score))
        score_meta = {"raw_score": raw_score, "min": 0, "max": 100, "clamped": final_score != raw_score}
        return final_score, breakdown, score_meta

    async def get_deep_schema_audit(self, username: str) -> Dict[str, Any]:
        username = (username or "SYSTEM").upper()
        params = DeepAuditPlanQueries.common_params(username)

        results: Dict[str, Any] = {
            "username": username,
            "summary": {"STATUS": "NO_DATA"},
            "activity": {"ddl": [], "dml": []},
            "dependencies": {"incoming": [], "outgoing": []},
            "active_jobs": [],
            "score_breakdown": [],
            "score_meta": {"raw_score": 0, "min": 0, "max": 100, "clamped": False},
            "obsolescence_score": 0,
            "audit_result": "PRECAUCIO",
            "executed_queries": [],
        }

        if not self.dbm:
            results["executed_queries"] = [{"query": "Q01-Q19", "status": "skipped", "rows": 0, "optional": False, "error": "no_db_manager"}]
            results["score_breakdown"] = [{"factor": "Qualitat de dades", "pts": 0, "desc": "Sense connexio a base de dades"}]
            results["score_meta"] = {
                "raw_score": 0,
                "min": 0,
                "max": 100,
                "clamped": False,
                "data_quality": "insufficient",
                "mandatory_errors": 1,
                "optional_errors": 0,
                "ok_queries": 0,
                "total_queries": 1,
            }
            results["summary"]["STATUS"] = "NO_DB_CONNECTION"
            results["obsolescence_score"] = 0
            results["audit_result"] = "PRECAUCIO"
            return results

        summary_rows, meta = self._run_query("Q01_SUMMARY_360", DeepAuditPlanQueries.Q01_SUMMARY_360, params, optional=False)
        results["executed_queries"].append(meta)
        if summary_rows:
            results["summary"] = summary_rows[0]

        size_rows, meta = self._run_query("Q02_SIZE", DeepAuditPlanQueries.Q02_SIZE, params, optional=False)
        results["executed_queries"].append(meta)
        results["size_segments"] = size_rows

        user_rows, meta = self._run_query("Q03_USER_ACCOUNT", DeepAuditPlanQueries.Q03_USER_ACCOUNT, params, optional=False)
        results["executed_queries"].append(meta)
        results["account"] = user_rows[0] if user_rows else {}

        activity_class_rows, meta = self._run_query("Q04_ACTIVITY_CLASS", DeepAuditPlanQueries.Q04_ACTIVITY_CLASS, params, optional=False)
        results["executed_queries"].append(meta)
        results["activity_classification"] = activity_class_rows[0] if activity_class_rows else {}

        object_types, meta = self._run_query("Q05_OBJECTS_BY_TYPE", DeepAuditPlanQueries.Q05_OBJECTS_BY_TYPE, params, optional=False)
        results["executed_queries"].append(meta)
        results["object_types"] = object_types

        recent_ddl, meta = self._run_query("Q06_RECENT_DDL", DeepAuditPlanQueries.Q06_RECENT_DDL, params, optional=False)
        results["executed_queries"].append(meta)
        results["activity"]["ddl"] = recent_ddl

        table_stats, meta = self._run_query("Q07_TABLE_STATS", DeepAuditPlanQueries.Q07_TABLE_STATS, params, optional=False)
        results["executed_queries"].append(meta)
        results["table_stats"] = table_stats

        incoming, meta = self._run_query("Q08_DEPS_INCOMING", DeepAuditPlanQueries.Q08_DEPS_INCOMING, params, optional=False)
        results["executed_queries"].append(meta)
        results["dependencies"]["incoming"] = incoming

        outgoing, meta = self._run_query("Q09_DEPS_OUTGOING", DeepAuditPlanQueries.Q09_DEPS_OUTGOING, params, optional=False)
        results["executed_queries"].append(meta)
        results["dependencies"]["outgoing"] = outgoing

        synonyms, meta = self._run_query("Q10_SYNONYMS", DeepAuditPlanQueries.Q10_SYNONYMS, params, optional=False)
        results["executed_queries"].append(meta)
        results["synonyms"] = synonyms
        results["synonyms_incoming"] = [s for s in synonyms if s.get("TABLE_OWNER") == username and s.get("OWNER") != username]

        grants_given, meta = self._run_query("Q11_GRANTS_GIVEN", DeepAuditPlanQueries.Q11_GRANTS_GIVEN, params, optional=False)
        results["executed_queries"].append(meta)
        results["grants_given"] = grants_given

        grants_received, meta = self._run_query("Q12_GRANTS_RECEIVED", DeepAuditPlanQueries.Q12_GRANTS_RECEIVED, params, optional=False)
        results["executed_queries"].append(meta)
        results["grants_received"] = grants_received

        sys_privs, meta = self._run_query("Q13_SYS_PRIVS", DeepAuditPlanQueries.Q13_SYS_PRIVS, params, optional=False)
        results["executed_queries"].append(meta)
        results["sys_privs"] = sys_privs

        code_refs_source, meta = self._run_query("Q14_CODE_REFS_SOURCE", DeepAuditPlanQueries.Q14_CODE_REFS_SOURCE, params, optional=False)
        results["executed_queries"].append(meta)
        code_refs_views, meta = self._run_query("Q14_CODE_REFS_VIEWS", DeepAuditPlanQueries.Q14_CODE_REFS_VIEWS, params, optional=False)
        results["executed_queries"].append(meta)
        code_refs_triggers, meta = self._run_query("Q14_CODE_REFS_TRIGGERS", DeepAuditPlanQueries.Q14_CODE_REFS_TRIGGERS, params, optional=False)
        results["executed_queries"].append(meta)
        results["code_refs"] = code_refs_source + code_refs_views + code_refs_triggers

        jobs, meta = self._run_query("Q15_JOBS", DeepAuditPlanQueries.Q15_JOBS, params, optional=False)
        results["executed_queries"].append(meta)
        results["active_jobs"] = jobs

        enabled_triggers, meta = self._run_query("Q16_TRIGGERS_ENABLED", DeepAuditPlanQueries.Q16_TRIGGERS_ENABLED, params, optional=False)
        results["executed_queries"].append(meta)
        results["enabled_triggers"] = enabled_triggers

        apex_apps, meta = self._run_query("Q17_APEX_APPS", DeepAuditPlanQueries.Q17_APEX_APPS, params, optional=True)
        results["executed_queries"].append(meta)
        results["apex_apps"] = apex_apps

        db_links, meta = self._run_query("Q18_DB_LINKS", DeepAuditPlanQueries.Q18_DB_LINKS, params, optional=False)
        results["executed_queries"].append(meta)
        results["db_links"] = db_links

        invalid_objects, meta = self._run_query("Q19_INVALID_OBJECTS", DeepAuditPlanQueries.Q19_INVALID_OBJECTS, params, optional=False)
        results["executed_queries"].append(meta)
        results["invalid_objects"] = invalid_objects

        health = self._query_health(results["executed_queries"])
        if health["mandatory_errors"] > 0:
            results["obsolescence_score"] = 0
            results["score_breakdown"] = [{
                "factor": "Qualitat de dades",
                "pts": 0,
                "desc": f"{health['mandatory_errors']} consultes obligatories han fallat. Score invalidat."
            }]
            results["score_meta"] = {
                "raw_score": 0,
                "min": 0,
                "max": 100,
                "clamped": False,
                "data_quality": "insufficient",
                **health,
            }
            results["summary"]["STATUS"] = "QUERY_ERRORS"
            results["audit_result"] = "PRECAUCIO"
            return results

        # Compatibilitat amb estructura antiga de DML
        dml_rows = []
        for row in table_stats[:10]:
            dml_rows.append({
                "TABLE_NAME": row.get("TABLE_NAME"),
                "TIMESTAMP": row.get("LAST_ANALYZED"),
                "INFERRED_ACTIVITY": "STATS_RECENT" if self._as_number(row.get("DAYS_SINCE_ANALYZED"), 999) <= 30 else "OLD_STATS",
            })
        results["activity"]["dml"] = dml_rows

        score, breakdown, score_meta = self._calculate_score_v4(results)
        results["obsolescence_score"] = score
        results["score_breakdown"] = breakdown
        results["score_meta"] = {**score_meta, "data_quality": "ok", **health}
        results["audit_result"] = self._derive_final_decision(results)

        return results

    async def run_plan_audit(self, schemas: List[str]) -> Dict[str, Any]:
        clean_schemas = [s.strip().upper() for s in schemas if s and s.strip()]
        if not clean_schemas:
            clean_schemas = ["SYSTEM"]

        audits = []
        for schema in clean_schemas:
            audits.append(await self.get_deep_schema_audit(schema))

        totals = {
            "schemas": len(audits),
            "total_size_gb": 0.0,
            "decision_counts": {"NO ELIMINAR": 0, "PRECAUCIO": 0, "ELIMINAR": 0},
            "avg_score": 0.0,
        }

        for item in audits:
            summary = item.get("summary") or {}
            totals["total_size_gb"] += self._as_number(summary.get("SIZE_GB"), 0)
            decision = item.get("audit_result", "PRECAUCIO")
            if decision not in totals["decision_counts"]:
                totals["decision_counts"][decision] = 0
            totals["decision_counts"][decision] += 1

        if audits:
            totals["avg_score"] = round(sum(a.get("obsolescence_score", 0) for a in audits) / len(audits), 2)
            totals["total_size_gb"] = round(totals["total_size_gb"], 3)

        return {
            "plan": "Q01-Q19",
            "audits": audits,
            "totals": totals,
        }

    def _get_mock_data(self, username: str) -> Dict[str, Any]:
        return {
            "username": username.upper(),
            "summary": {
                "USERNAME": username.upper(),
                "SIZE_GB": 0.05,
                "OBJECT_COUNT": 10,
                "LAST_LOGIN_DAYS": 999,
                "INBOUND_REFERENCES": 0,
                "ACTIVE_JOBS": 0,
                "APEX_APPLICATIONS": 0,
                "ENABLED_TRIGGERS": 0,
                "TABLES_WITH_MODS_30D": 0,
                "TABLES_STATS_RECENT_30D": 0,
                "DAYS_SINCE_NEWEST_DDL": 999,
                "ALARM_1_ACTIVITY_RECENT": 0,
            },
            "activity": {"ddl": [], "dml": []},
            "dependencies": {"incoming": [], "outgoing": []},
            "active_jobs": [],
            "apex_apps": [],
            "score_breakdown": [{"factor": "Mock", "pts": 95, "desc": "Mode demostracio"}],
            "score_meta": {"raw_score": 95, "min": 0, "max": 100, "clamped": False},
            "obsolescence_score": 95,
            "audit_result": "ELIMINAR",
            "executed_queries": [{"query": "Q01-Q19", "status": "mock", "rows": 0}],
        }


