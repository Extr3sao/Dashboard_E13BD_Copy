import datetime as dt
import json
import logging
import os
import sqlite3
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.sqlite_paths import resolve_sqlite_path
from src.core.time_utils import utc_now_iso

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return utc_now_iso()


def _json_dumps(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Optional[str], default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        logger.warning("Invalid JSON payload in automation store", exc_info=exc)
        return default


class AutomationStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or resolve_sqlite_path("AUTOMATION_DB_PATH", "automation.db")
        self._memory_fallback_conn: Optional[sqlite3.Connection] = None
        self._ensure_dir()
        try:
            self._init_db()
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if not any(token in message for token in ("disk i/o error", "readonly", "attempt to write a readonly database")):
                raise
            fallback_filename = Path(str(self.db_path)).name or "automation.db"
            fallback_disk_path = resolve_sqlite_path("AUTOMATION_DB_PATH", fallback_filename)
            if fallback_disk_path != self.db_path:
                self.db_path = fallback_disk_path
                self._ensure_dir()
                try:
                    self._init_db()
                    return
                except sqlite3.OperationalError as retry_exc:
                    retry_message = str(retry_exc).lower()
                    if not any(token in retry_message for token in ("disk i/o error", "readonly", "attempt to write a readonly database")):
                        raise
            fallback_disk_path = self._build_fallback_path()
            if fallback_disk_path != self.db_path:
                self.db_path = fallback_disk_path
                self._ensure_dir()
                try:
                    self._init_db()
                    return
                except sqlite3.OperationalError as retry_exc:
                    retry_message = str(retry_exc).lower()
                    if not any(token in retry_message for token in ("disk i/o error", "readonly", "attempt to write a readonly database")):
                        raise
            memory_name = re.sub(r"[^a-zA-Z0-9_]+", "_", Path(str(self.db_path)).stem or "automation")
            self.db_path = f"file:oracle_audit_{memory_name}?mode=memory&cache=shared"
            self._memory_fallback_conn = sqlite3.connect(self.db_path, uri=True, check_same_thread=False)
            self._memory_fallback_conn.row_factory = sqlite3.Row
            self._init_db()

    def _ensure_dir(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)

    def _build_fallback_path(self) -> str:
        path = Path(str(self.db_path))
        if path.suffix:
            return str(path.with_name(f"{path.stem}_fallback{path.suffix}"))
        return str(path.with_name(f"{path.name}_fallback.db"))

    def _get_connection(self) -> sqlite3.Connection:
        if str(self.db_path).startswith("file:"):
            conn = sqlite3.connect(self.db_path, uri=True, check_same_thread=False)
        else:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
        known = {row["name"] for row in columns}
        if column not in known:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    audit_type TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    schemas_json TEXT DEFAULT '[]',
                    checks_json TEXT DEFAULT '[]',
                    time_filter_json TEXT DEFAULT '{}',
                    report_format TEXT DEFAULT 'markdown',
                    schedule_type TEXT DEFAULT 'once',
                    schedule_config_json TEXT DEFAULT '{}',
                    job_config_json TEXT DEFAULT '{}',
                    timeout_seconds INTEGER DEFAULT 300,
                    next_run_at TEXT,
                    last_run_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    config_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS severity_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL DEFAULT 'global',
                    job_id INTEGER,
                    severity TEXT NOT NULL,
                    create_task INTEGER DEFAULT 0,
                    task_priority TEXT DEFAULT 'normal',
                    send_email INTEGER DEFAULT 0,
                    attach_report INTEGER DEFAULT 1,
                    recipients_json TEXT DEFAULT '[]',
                    conditions_json TEXT DEFAULT '{}',
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS job_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT DEFAULT 'running',
                    duration_ms INTEGER,
                    summary_json TEXT DEFAULT '{}',
                    error_message TEXT,
                    report_path TEXT,
                    deliveries_json TEXT DEFAULT '[]',
                    created_tasks_json TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS job_run_lot_statuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    job_id INTEGER NOT NULL,
                    execution_id TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    lot TEXT NOT NULL,
                    detection_status TEXT NOT NULL,
                    num_findings INTEGER,
                    report_generated INTEGER DEFAULT 0,
                    email_sent INTEGER DEFAULT 0,
                    motivo_sin_envio TEXT,
                    observaciones TEXT,
                    payload_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES job_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS internal_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_run_id INTEGER,
                    source_job_id INTEGER,
                    title TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    priority TEXT DEFAULT 'normal',
                    status TEXT DEFAULT 'pendent',
                    assigned_to TEXT,
                    description TEXT,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TEXT,
                    FOREIGN KEY (source_run_id) REFERENCES job_runs(id) ON DELETE SET NULL,
                    FOREIGN KEY (source_job_id) REFERENCES scheduled_jobs(id) ON DELETE SET NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    smtp_host TEXT,
                    smtp_port INTEGER,
                    smtp_username TEXT,
                    smtp_password TEXT,
                    smtp_use_tls INTEGER DEFAULT 1,
                    from_email TEXT,
                    default_recipients_json TEXT DEFAULT '[]',
                    failure_notification_recipients_json TEXT DEFAULT '[]',
                    teams_webhook TEXT,
                    sharepoint_site TEXT,
                    sharepoint_library TEXT,
                    sharepoint_folder TEXT,
                    auto_purge_enabled INTEGER DEFAULT 1,
                    history_retention_days INTEGER DEFAULT 30,
                    retry_retention_days INTEGER DEFAULT 30,
                    last_auto_purge_at TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS master_lots (
                    code TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    description TEXT,
                    enabled INTEGER DEFAULT 1,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS lot_delivery_routes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lot_code TEXT NOT NULL,
                    audience TEXT NOT NULL DEFAULT 'provider',
                    label TEXT,
                    emails_json TEXT DEFAULT '[]',
                    enabled INTEGER DEFAULT 1,
                    source TEXT DEFAULT 'automation',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(lot_code, audience)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_key TEXT NOT NULL UNIQUE,
                    audience TEXT NOT NULL,
                    subject_template TEXT NOT NULL,
                    body_template TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    job_id INTEGER,
                    lot TEXT,
                    audience TEXT NOT NULL,
                    attempt_no INTEGER DEFAULT 1,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    recipients_json TEXT DEFAULT '[]',
                    attachment_name TEXT,
                    template_key TEXT,
                    template_snapshot_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES job_runs(id) ON DELETE SET NULL,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE SET NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_retry_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    job_id INTEGER,
                    lot TEXT,
                    audience TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    requested_by TEXT,
                    last_attempt_at TEXT,
                    attempts_made INTEGER DEFAULT 0,
                    error_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES job_runs(id) ON DELETE SET NULL,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE SET NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS master_lot_backfill_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL DEFAULT 'schema_lots',
                    source_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'preview',
                    actor TEXT,
                    reason TEXT,
                    summary_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    applied_at TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS master_lot_backfill_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backfill_run_id INTEGER NOT NULL,
                    lot_code TEXT NOT NULL,
                    proposed_label TEXT,
                    schema_names_json TEXT DEFAULT '[]',
                    action TEXT NOT NULL,
                    conflict_code TEXT,
                    selected INTEGER DEFAULT 1,
                    applied INTEGER DEFAULT 0,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (backfill_run_id) REFERENCES master_lot_backfill_runs(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_change_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT,
                    reason TEXT,
                    before_json TEXT DEFAULT '{}',
                    after_json TEXT DEFAULT '{}',
                    context_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_execution_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL UNIQUE,
                    job_id INTEGER NOT NULL,
                    execution_id TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    audit_type TEXT NOT NULL,
                    profile TEXT,
                    total_findings INTEGER DEFAULT 0,
                    checks_with_findings INTEGER DEFAULT 0,
                    checks_with_errors INTEGER DEFAULT 0,
                    lots_with_findings INTEGER DEFAULT 0,
                    schemas_in_scope INTEGER DEFAULT 0,
                    payload_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES job_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_lot_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    job_id INTEGER NOT NULL,
                    execution_id TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    lot TEXT NOT NULL,
                    detection_status TEXT,
                    finding_count INTEGER DEFAULT 0,
                    schema_count INTEGER DEFAULT 0,
                    check_count INTEGER DEFAULT 0,
                    payload_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES job_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_schema_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    job_id INTEGER NOT NULL,
                    execution_id TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    schema_name TEXT NOT NULL,
                    lot TEXT,
                    finding_count INTEGER DEFAULT 0,
                    check_count INTEGER DEFAULT 0,
                    payload_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES job_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_check_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    job_id INTEGER NOT NULL,
                    execution_id TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    check_id TEXT NOT NULL,
                    title TEXT,
                    severity TEXT,
                    status TEXT,
                    row_count INTEGER DEFAULT 0,
                    finding_count INTEGER DEFAULT 0,
                    affected_lots INTEGER DEFAULT 0,
                    affected_schemas INTEGER DEFAULT 0,
                    payload_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES job_runs(id) ON DELETE CASCADE,
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
                )
                """
            )
            self._ensure_column(conn, "scheduled_jobs", "job_config_json", "job_config_json TEXT DEFAULT '{}'")
            self._ensure_column(conn, "delivery_config", "tic_summary_recipients_json", "tic_summary_recipients_json TEXT DEFAULT '[]'")
            self._ensure_column(conn, "delivery_config", "provider_routes_json", "provider_routes_json TEXT DEFAULT '[]'")
            self._ensure_column(conn, "delivery_config", "failure_notification_recipients_json", "failure_notification_recipients_json TEXT DEFAULT '[]'")
            self._ensure_column(conn, "delivery_config", "auto_purge_enabled", "auto_purge_enabled INTEGER DEFAULT 1")
            self._ensure_column(conn, "delivery_config", "history_retention_days", "history_retention_days INTEGER DEFAULT 30")
            self._ensure_column(conn, "delivery_config", "retry_retention_days", "retry_retention_days INTEGER DEFAULT 30")
            self._ensure_column(conn, "delivery_config", "last_auto_purge_at", "last_auto_purge_at TEXT")
            self._ensure_column(conn, "delivery_retry_queue", "next_attempt_at", "next_attempt_at TEXT")
            self._ensure_column(conn, "delivery_retry_queue", "max_attempts", "max_attempts INTEGER DEFAULT 4")
            self._ensure_column(conn, "delivery_retry_queue", "retry_mode", "retry_mode TEXT DEFAULT 'manual'")
            self._ensure_column(conn, "delivery_retry_queue", "error_class", "error_class TEXT")
            self._ensure_column(conn, "delivery_retry_queue", "dedupe_key", "dedupe_key TEXT")
            self._ensure_column(conn, "delivery_retry_queue", "lock_token", "lock_token TEXT")
            self._ensure_column(conn, "delivery_retry_queue", "locked_at", "locked_at TEXT")
            self._ensure_column(conn, "job_run_lot_statuses", "delivery_audience", "delivery_audience TEXT")
            self._ensure_column(conn, "job_run_lot_statuses", "delivery_result", "delivery_result TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_run_lot_statuses_run_status ON job_run_lot_statuses(run_id, detection_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_run_lot_statuses_run_delivery ON job_run_lot_statuses(run_id, delivery_audience, delivery_result)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_delivery_retry_queue_due ON delivery_retry_queue(status, next_attempt_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_delivery_attempts_run_audience_status ON delivery_attempts(run_id, audience, status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_execution_facts_executed_at ON audit_execution_facts(executed_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_lot_facts_executed_at_lot ON audit_lot_facts(executed_at, lot)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_schema_facts_executed_at_schema ON audit_schema_facts(executed_at, schema_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_check_facts_executed_at_check ON audit_check_facts(executed_at, check_id)")
            cursor.execute(
                """
                INSERT OR IGNORE INTO delivery_config (
                    id, smtp_port, smtp_use_tls, default_recipients_json
                ) VALUES (1, 587, 1, '[]')
                """
            )
            cursor.executemany(
                """
                INSERT OR IGNORE INTO delivery_templates (
                    template_key, audience, subject_template, body_template, enabled
                ) VALUES (?, ?, ?, ?, 1)
                """,
                [
                    (
                        "job_generation_failure",
                        "failure",
                        "[Oracle Audit] Error generant l'informe - {job_name} - {profile}",
                        "Bon dia,\n\nNo s'ha pogut generar l'informe \"{report_name}\".\n\nResum de la incidència\n- Job: {job_name}\n- Perfil: {profile}\n- Identificador d'execució: {execution_id}\n- Estat: {status}\n\nMotiu\n{failure_reason}\n\nObservacions\n{observations}\n\nNo s'ha enviat cap informe adjunt perquè la generació no s'ha completat correctament.\n\nSalutacions,\nSistema d'auditoria BBDD",
                    ),
                    (
                        "tic_summary",
                        "tic",
                        "[Oracle Audit] Resum TIC - {job_name} - {profile}",
                        "Bon dia,\n\nS'ha executat correctament el resum general de l'auditoria.\n\nResum de l'execució\n- Perfil: {profile}\n- Estat: {status}\n- Nombre de troballes: {findings}\n- Identificador d'execució: {execution_id}\n\nObservacions\n{observations}\n\nResum global\n{summary}\n\nTrobaràs el detall complet a l'informe adjunt.\n\nSalutacions,\nSistema d'auditoria BBDD",
                    ),
                    (
                        "provider_with_findings",
                        "provider",
                        "[Oracle Audit] {job_name} - {lot}",
                        "Bon dia,\n\nS'ha executat correctament l'auditoria automàtica del lot {lot}.\n\nResum de l'execució\n- Perfil: {profile}\n- Lot: {lot}\n- Estat: {status}\n- Nombre de troballes: {findings}\n- Identificador d'execució: {execution_id}\n\nObservacions\n{observations}\n\nLlegenda tècnica\n{technical_legend}\n\nTrobaràs el detall complet a l'informe adjunt.\n\nSalutacions,\nSistema d'auditoria BBDD",
                    ),
                    (
                        "provider_without_findings",
                        "provider",
                        "[Oracle Audit] {job_name} - {lot} - sense troballes",
                        "Bon dia,\n\nS'ha executat correctament l'auditoria automàtica del lot {lot} i no s'hi han detectat anomalies.\n\nResum de l'execució\n- Perfil: {profile}\n- Lot: {lot}\n- Estat: {status}\n- Nombre de troballes: {findings}\n- Identificador d'execució: {execution_id}\n\nObservacions\n{observations}\n\nLlegenda tècnica\n{technical_legend}\n\nNo s'adjunta cap informe individual perquè el lot s'ha avaluat sense troballes.\n\nSalutacions,\nSistema d'auditoria BBDD",
                    ),
                    (
                        "manual_resend",
                        "retry",
                        "[Oracle Audit] Reenviament - {job_name} - {lot}",
                        "Bon dia,\n\nS'ha processat un reintent d'enviament per al lot {lot}.\n\nResum de l'execució\n- Perfil: {profile}\n- Lot: {lot}\n- Estat: {status}\n- Nombre de troballes: {findings}\n- Identificador d'execució: {execution_id}\n\nObservacions\n{observations}\n\nLlegenda tècnica\n{technical_legend}\n\nTrobaràs el detall complet a l'informe adjunt.\n\nSalutacions,\nSistema d'auditoria BBDD",
                    ),
                ],
            )
            cursor.execute(
                """
                UPDATE delivery_templates
                SET body_template = ?
                WHERE template_key = 'provider_with_findings'
                  AND body_template = ?
                """,
                (
                    "Bon dia,\n\nS'ha executat correctament l'auditoria automàtica del lot {lot}.\n\nResum de l'execució\n- Perfil: {profile}\n- Lot: {lot}\n- Estat: {status}\n- Nombre de troballes: {findings}\n- Identificador d'execució: {execution_id}\n\nObservacions\n{observations}\n\nLlegenda tècnica\n{technical_legend}\n\nTrobaràs el detall complet a l'informe adjunt.\n\nSalutacions,\nSistema d'auditoria BBDD",
                    "Execucio {execution_id}\nPerfil: {profile}\nLot: {lot}\nEstat: {status}\nTroballes: {findings}\nObservacions: {observations}",
                ),
            )
            cursor.execute(
                """
                UPDATE delivery_templates
                SET body_template = ?
                WHERE template_key = 'manual_resend'
                  AND body_template = ?
                """,
                (
                    "Bon dia,\n\nS'ha processat un reintent d'enviament per al lot {lot}.\n\nResum de l'execució\n- Perfil: {profile}\n- Lot: {lot}\n- Estat: {status}\n- Nombre de troballes: {findings}\n- Identificador d'execució: {execution_id}\n\nObservacions\n{observations}\n\nLlegenda tècnica\n{technical_legend}\n\nTrobaràs el detall complet a l'informe adjunt.\n\nSalutacions,\nSistema d'auditoria BBDD",
                    "Reenviament manual de l'execucio {execution_id}\nPerfil: {profile}\nLot: {lot}\nEstat: {status}\nTroballes: {findings}\nObservacions: {observations}",
                ),
            )
            cursor.execute(
                """
                UPDATE delivery_templates
                SET body_template = ?
                WHERE template_key = 'tic_summary'
                  AND body_template = ?
                """,
                (
                    "Bon dia,\n\nS'ha executat correctament el resum general de l'auditoria.\n\nResum de l'execució\n- Perfil: {profile}\n- Estat: {status}\n- Nombre de troballes: {findings}\n- Identificador d'execució: {execution_id}\n\nObservacions\n{observations}\n\nResum global\n{summary}\n\nTrobaràs el detall complet a l'informe adjunt.\n\nSalutacions,\nSistema d'auditoria BBDD",
                    "Execucio {execution_id}\nPerfil: {profile}\nResum: {summary}\nObservacions: {observations}",
                ),
            )
            conn.commit()

    def _list_delivery_targets(self, conn: sqlite3.Connection, job_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT id, job_id, type, enabled, config_json, created_at, updated_at
            FROM delivery_targets
            WHERE job_id = ?
            ORDER BY id ASC
            """,
            (int(job_id),),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "type": row["type"],
                "enabled": bool(row["enabled"]),
                "config": _json_loads(row["config_json"], {}),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def _list_rules(self, conn: sqlite3.Connection, scope: Optional[str] = None, job_id: Optional[int] = None) -> List[Dict[str, Any]]:
        where = []
        params: List[Any] = []
        if scope:
            where.append("scope = ?")
            params.append(scope)
        if job_id is not None:
            where.append("job_id = ?")
            params.append(int(job_id))

        sql = """
            SELECT id, scope, job_id, severity, create_task, task_priority, send_email,
                   attach_report, recipients_json, conditions_json, enabled, created_at, updated_at
            FROM severity_rules
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id ASC"
        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "id": row["id"],
                "scope": row["scope"],
                "job_id": row["job_id"],
                "severity": row["severity"],
                "create_task": bool(row["create_task"]),
                "task_priority": row["task_priority"],
                "send_email": bool(row["send_email"]),
                "attach_report": bool(row["attach_report"]),
                "recipients": _json_loads(row["recipients_json"], []),
                "conditions": _json_loads(row["conditions_json"], {}),
                "enabled": bool(row["enabled"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def _hydrate_job(self, row: sqlite3.Row, targets: List[Dict[str, Any]], rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        job_config = _json_loads(row["job_config_json"], {})
        return {
            "id": row["id"],
            "name": row["name"],
            "enabled": bool(row["enabled"]),
            "audit_type": row["audit_type"],
            "profile": row["profile"],
            "schemas": _json_loads(row["schemas_json"], []),
            "checks": _json_loads(row["checks_json"], []),
            "time_filter": _json_loads(row["time_filter_json"], {}),
            "report_format": row["report_format"],
            "schedule_type": row["schedule_type"],
            "schedule_config": _json_loads(row["schedule_config_json"], {}),
            "job_config": job_config,
            "scheduler_options": job_config.get("scheduler_options") or {},
            "criticality_overrides": job_config.get("criticality_overrides") or {},
            "timeout_seconds": int(row["timeout_seconds"] or 300),
            "next_run_at": row["next_run_at"],
            "last_run_at": row["last_run_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "delivery_targets": targets,
            "severity_rules": rules,
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM scheduled_jobs ORDER BY created_at DESC, id DESC").fetchall()
            return [
                self._hydrate_job(
                    row,
                    self._list_delivery_targets(conn, row["id"]),
                    self._list_rules(conn, scope="job", job_id=row["id"]),
                )
                for row in rows
            ]

    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM scheduled_jobs WHERE id = ?", (int(job_id),)).fetchone()
            if not row:
                return None
            return self._hydrate_job(
                row,
                self._list_delivery_targets(conn, row["id"]),
                self._list_rules(conn, scope="job", job_id=row["id"]),
            )

    def _replace_delivery_targets(self, conn: sqlite3.Connection, job_id: int, targets: List[Dict[str, Any]]) -> None:
        now = _utc_now_iso()
        conn.execute("DELETE FROM delivery_targets WHERE job_id = ?", (int(job_id),))
        for item in targets:
            conn.execute(
                """
                INSERT INTO delivery_targets (job_id, type, enabled, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(job_id),
                    item.get("type", "email"),
                    int(bool(item.get("enabled", True))),
                    _json_dumps(item.get("config"), {}),
                    now,
                    now,
                ),
            )

    def _replace_job_rules(self, conn: sqlite3.Connection, job_id: int, rules: List[Dict[str, Any]]) -> None:
        now = _utc_now_iso()
        conn.execute("DELETE FROM severity_rules WHERE scope = 'job' AND job_id = ?", (int(job_id),))
        for rule in rules:
            conn.execute(
                """
                INSERT INTO severity_rules (
                    scope, job_id, severity, create_task, task_priority, send_email, attach_report,
                    recipients_json, conditions_json, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job",
                    int(job_id),
                    rule["severity"],
                    int(bool(rule.get("create_task", False))),
                    rule.get("task_priority", "normal"),
                    int(bool(rule.get("send_email", False))),
                    int(bool(rule.get("attach_report", True))),
                    _json_dumps(rule.get("recipients"), []),
                    _json_dumps(rule.get("conditions"), {}),
                    int(bool(rule.get("enabled", True))),
                    now,
                    now,
                ),
            )

    def create_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO scheduled_jobs (
                    name, enabled, audit_type, profile, schemas_json, checks_json, time_filter_json,
                    report_format, schedule_type, schedule_config_json, job_config_json, timeout_seconds, next_run_at,
                    last_run_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["name"],
                    int(bool(payload.get("enabled", True))),
                    payload["audit_type"],
                    payload["profile"],
                    _json_dumps(payload.get("schemas"), []),
                    _json_dumps(payload.get("checks"), []),
                    _json_dumps(payload.get("time_filter"), {}),
                    payload.get("report_format", "markdown"),
                    payload.get("schedule_type", "once"),
                    _json_dumps(payload.get("schedule_config"), {}),
                    _json_dumps(payload.get("job_config"), {}),
                    int(payload.get("timeout_seconds") or 300),
                    payload.get("next_run_at"),
                    payload.get("last_run_at"),
                    now,
                    now,
                ),
            )
            job_id = int(cursor.lastrowid)
            self._replace_delivery_targets(conn, job_id, payload.get("delivery_targets") or [])
            self._replace_job_rules(conn, job_id, payload.get("severity_rules") or [])
            conn.commit()
        return self.get_job(job_id)

    def update_job(self, job_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = self.get_job(job_id)
        if not current:
            return None

        merged = {**current, **payload}
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE scheduled_jobs
                SET name = ?, enabled = ?, audit_type = ?, profile = ?, schemas_json = ?, checks_json = ?,
                    time_filter_json = ?, report_format = ?, schedule_type = ?, schedule_config_json = ?,
                    job_config_json = ?, timeout_seconds = ?, next_run_at = ?, last_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged["name"],
                    int(bool(merged.get("enabled", True))),
                    merged["audit_type"],
                    merged["profile"],
                    _json_dumps(merged.get("schemas"), []),
                    _json_dumps(merged.get("checks"), []),
                    _json_dumps(merged.get("time_filter"), {}),
                    merged.get("report_format", "markdown"),
                    merged.get("schedule_type", "once"),
                    _json_dumps(merged.get("schedule_config"), {}),
                    _json_dumps(merged.get("job_config"), {}),
                    int(merged.get("timeout_seconds") or 300),
                    merged.get("next_run_at"),
                    merged.get("last_run_at"),
                    _utc_now_iso(),
                    int(job_id),
                ),
            )
            if "delivery_targets" in payload:
                self._replace_delivery_targets(conn, job_id, payload.get("delivery_targets") or [])
            if "severity_rules" in payload:
                self._replace_job_rules(conn, job_id, payload.get("severity_rules") or [])
            conn.commit()
        return self.get_job(job_id)

    def delete_job(self, job_id: int) -> bool:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM delivery_targets WHERE job_id = ?", (int(job_id),))
            conn.execute("DELETE FROM severity_rules WHERE scope = 'job' AND job_id = ?", (int(job_id),))
            cursor = conn.execute("DELETE FROM scheduled_jobs WHERE id = ?", (int(job_id),))
            conn.commit()
            return cursor.rowcount > 0

    def get_due_jobs(self, now_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        now_iso = now_iso or _utc_now_iso()
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM scheduled_jobs
                WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?
                ORDER BY next_run_at ASC, id ASC
                """,
                (now_iso,),
            ).fetchall()
            return [
                self._hydrate_job(
                    row,
                    self._list_delivery_targets(conn, row["id"]),
                    self._list_rules(conn, scope="job", job_id=row["id"]),
                )
                for row in rows
            ]

    def touch_job_schedule(self, job_id: int, *, next_run_at: Optional[str], last_run_at: Optional[str]) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE scheduled_jobs
                SET next_run_at = ?, last_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_run_at, last_run_at, _utc_now_iso(), int(job_id)),
            )
            conn.commit()

    def create_run(self, job_id: int, started_at: Optional[str] = None) -> int:
        started_at = started_at or _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO job_runs (job_id, started_at, status, summary_json, deliveries_json, created_tasks_json)
                VALUES (?, ?, 'running', '{}', '[]', '[]')
                """,
                (int(job_id), started_at),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def complete_run(
        self,
        run_id: int,
        *,
        status: str,
        finished_at: Optional[str] = None,
        duration_ms: Optional[int] = None,
        summary: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        report_path: Optional[str] = None,
        deliveries: Optional[List[Dict[str, Any]]] = None,
        created_tasks: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        finished_at = finished_at or _utc_now_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE job_runs
                SET finished_at = ?, status = ?, duration_ms = ?, summary_json = ?, error_message = ?,
                    report_path = ?, deliveries_json = ?, created_tasks_json = ?
                WHERE id = ?
                """,
                (
                    finished_at,
                    status,
                    duration_ms,
                    _json_dumps(summary, {}),
                    error_message,
                    report_path,
                    _json_dumps(deliveries, []),
                    _json_dumps(created_tasks, []),
                    int(run_id),
                ),
            )
            conn.commit()

    def replace_run_lot_statuses(
        self,
        run_id: int,
        job_id: int,
        items: List[Dict[str, Any]],
        *,
        execution_id: Optional[str] = None,
        executed_at: Optional[str] = None,
    ) -> None:
        now = executed_at or _utc_now_iso()
        current_execution_id = execution_id or f"job-{int(job_id)}-run-{int(run_id)}"
        with self._get_connection() as conn:
            conn.execute("DELETE FROM job_run_lot_statuses WHERE run_id = ?", (int(run_id),))
            for item in items or []:
                conn.execute(
                    """
                    INSERT INTO job_run_lot_statuses (
                        run_id, job_id, execution_id, executed_at, lot, detection_status, num_findings,
                        report_generated, email_sent, motivo_sin_envio, observaciones, payload_json,
                        delivery_audience, delivery_result, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(run_id),
                        int(job_id),
                        current_execution_id,
                        now,
                        str(item.get("lot") or "").strip(),
                        str(item.get("detection_status") or "").strip(),
                        item.get("num_findings"),
                        int(bool(item.get("report_generated", False))),
                        int(bool(item.get("email_sent", False))),
                        item.get("motivo_sin_envio"),
                        item.get("observaciones"),
                        _json_dumps(item, {}),
                        item.get("delivery_audience"),
                        item.get("delivery_result"),
                        now,
                    ),
                )
            conn.commit()

    def replace_post_crq_analytics(self, run_id: int, job_id: int, payload: Dict[str, Any]) -> None:
        execution = payload.get("execution") or {}
        lots = payload.get("lots") or []
        schemas = payload.get("schemas") or []
        checks = payload.get("checks") or []
        with self._get_connection() as conn:
            conn.execute("DELETE FROM audit_execution_facts WHERE run_id = ?", (int(run_id),))
            conn.execute("DELETE FROM audit_lot_facts WHERE run_id = ?", (int(run_id),))
            conn.execute("DELETE FROM audit_schema_facts WHERE run_id = ?", (int(run_id),))
            conn.execute("DELETE FROM audit_check_facts WHERE run_id = ?", (int(run_id),))
            if execution:
                conn.execute(
                    """
                    INSERT INTO audit_execution_facts (
                        run_id, job_id, execution_id, executed_at, audit_type, profile,
                        total_findings, checks_with_findings, checks_with_errors, lots_with_findings,
                        schemas_in_scope, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(run_id),
                        int(job_id),
                        execution.get("execution_id"),
                        execution.get("executed_at"),
                        execution.get("audit_type"),
                        execution.get("profile"),
                        int(execution.get("total_findings") or 0),
                        int(execution.get("checks_with_findings") or 0),
                        int(execution.get("checks_with_errors") or 0),
                        int(execution.get("lots_with_findings") or 0),
                        int(execution.get("schemas_in_scope") or 0),
                        _json_dumps(execution.get("payload"), {}),
                        execution.get("executed_at") or _utc_now_iso(),
                    ),
                )
            for item in lots:
                conn.execute(
                    """
                    INSERT INTO audit_lot_facts (
                        run_id, job_id, execution_id, executed_at, lot, detection_status,
                        finding_count, schema_count, check_count, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(run_id),
                        int(job_id),
                        item.get("execution_id"),
                        item.get("executed_at"),
                        item.get("lot"),
                        item.get("detection_status"),
                        int(item.get("finding_count") or 0),
                        int(item.get("schema_count") or 0),
                        int(item.get("check_count") or 0),
                        _json_dumps(item.get("payload"), {}),
                        item.get("executed_at") or _utc_now_iso(),
                    ),
                )
            for item in schemas:
                conn.execute(
                    """
                    INSERT INTO audit_schema_facts (
                        run_id, job_id, execution_id, executed_at, schema_name, lot,
                        finding_count, check_count, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(run_id),
                        int(job_id),
                        item.get("execution_id"),
                        item.get("executed_at"),
                        item.get("schema_name"),
                        item.get("lot"),
                        int(item.get("finding_count") or 0),
                        int(item.get("check_count") or 0),
                        _json_dumps(item.get("payload"), {}),
                        item.get("executed_at") or _utc_now_iso(),
                    ),
                )
            for item in checks:
                conn.execute(
                    """
                    INSERT INTO audit_check_facts (
                        run_id, job_id, execution_id, executed_at, check_id, title, severity,
                        status, row_count, finding_count, affected_lots, affected_schemas, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(run_id),
                        int(job_id),
                        item.get("execution_id"),
                        item.get("executed_at"),
                        item.get("check_id"),
                        item.get("title"),
                        item.get("severity"),
                        item.get("status"),
                        int(item.get("row_count") or 0),
                        int(item.get("finding_count") or 0),
                        int(item.get("affected_lots") or 0),
                        int(item.get("affected_schemas") or 0),
                        _json_dumps(item.get("payload"), {}),
                        item.get("executed_at") or _utc_now_iso(),
                    ),
                )
            conn.commit()

    def _date_range_for_month(self, month: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        if not month:
            return None, None
        try:
            year_str, month_str = str(month).split("-", 1)
            year = int(year_str)
            month_num = int(month_str)
            if month_num < 1 or month_num > 12:
                return None, None
            start = dt.datetime(year, month_num, 1)
            if month_num == 12:
                end = dt.datetime(year + 1, 1, 1)
            else:
                end = dt.datetime(year, month_num + 1, 1)
            return start.isoformat() + "Z", end.isoformat() + "Z"
        except (TypeError, ValueError):
            return None, None

    def get_post_crq_analytics_overview(self, *, month: Optional[str] = None) -> Dict[str, Any]:
        start_iso, end_iso = self._date_range_for_month(month)
        sql = "SELECT COUNT(*) AS runs, SUM(total_findings) AS findings, SUM(lots_with_findings) AS lots_with_findings, SUM(checks_with_errors) AS checks_with_errors FROM audit_execution_facts WHERE 1=1"
        params: List[Any] = []
        if start_iso:
            sql += " AND executed_at >= ?"
            params.append(start_iso)
        if end_iso:
            sql += " AND executed_at < ?"
            params.append(end_iso)
        with self._get_connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return {
                "month": month,
                "runs": int((row["runs"] or 0) if row else 0),
                "total_findings": int((row["findings"] or 0) if row else 0),
                "lots_with_findings": int((row["lots_with_findings"] or 0) if row else 0),
                "checks_with_errors": int((row["checks_with_errors"] or 0) if row else 0),
            }

    def list_post_crq_lot_analytics(self, *, month: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        start_iso, end_iso = self._date_range_for_month(month)
        sql = """
            SELECT lot, COUNT(DISTINCT run_id) AS runs, SUM(finding_count) AS total_findings,
                   SUM(CASE WHEN detection_status = 'CON_HALLAZGOS' THEN 1 ELSE 0 END) AS runs_with_findings
            FROM audit_lot_facts
            WHERE 1=1
        """
        params: List[Any] = []
        if start_iso:
            sql += " AND executed_at >= ?"
            params.append(start_iso)
        if end_iso:
            sql += " AND executed_at < ?"
            params.append(end_iso)
        sql += " GROUP BY lot ORDER BY total_findings DESC, lot ASC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "lot": row["lot"],
                    "runs": int(row["runs"] or 0),
                    "total_findings": int(row["total_findings"] or 0),
                    "runs_with_findings": int(row["runs_with_findings"] or 0),
                }
                for row in rows
            ]

    def list_post_crq_schema_analytics(self, *, month: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        start_iso, end_iso = self._date_range_for_month(month)
        sql = """
            SELECT schema_name, lot, COUNT(DISTINCT run_id) AS runs, SUM(finding_count) AS total_findings,
                   SUM(check_count) AS total_checks
            FROM audit_schema_facts
            WHERE 1=1
        """
        params: List[Any] = []
        if start_iso:
            sql += " AND executed_at >= ?"
            params.append(start_iso)
        if end_iso:
            sql += " AND executed_at < ?"
            params.append(end_iso)
        sql += " GROUP BY schema_name, lot ORDER BY total_findings DESC, schema_name ASC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "schema_name": row["schema_name"],
                    "lot": row["lot"],
                    "runs": int(row["runs"] or 0),
                    "total_findings": int(row["total_findings"] or 0),
                    "total_checks": int(row["total_checks"] or 0),
                }
                for row in rows
            ]

    def list_post_crq_check_analytics(self, *, month: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        start_iso, end_iso = self._date_range_for_month(month)
        sql = """
            SELECT check_id, title, severity, COUNT(DISTINCT run_id) AS runs,
                   SUM(finding_count) AS total_findings, SUM(affected_lots) AS affected_lots, SUM(affected_schemas) AS affected_schemas
            FROM audit_check_facts
            WHERE 1=1
        """
        params: List[Any] = []
        if start_iso:
            sql += " AND executed_at >= ?"
            params.append(start_iso)
        if end_iso:
            sql += " AND executed_at < ?"
            params.append(end_iso)
        sql += " GROUP BY check_id, title, severity ORDER BY total_findings DESC, check_id ASC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "check_id": row["check_id"],
                    "title": row["title"],
                    "severity": row["severity"],
                    "runs": int(row["runs"] or 0),
                    "total_findings": int(row["total_findings"] or 0),
                    "affected_lots": int(row["affected_lots"] or 0),
                    "affected_schemas": int(row["affected_schemas"] or 0),
                }
                for row in rows
            ]

    def list_run_lot_statuses(
        self,
        run_id: int,
        *,
        status: Optional[str] = None,
        search: Optional[str] = None,
        audience: Optional[str] = None,
        delivery_result: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            sql = """
                SELECT *
                FROM job_run_lot_statuses
                WHERE run_id = ?
            """
            params: List[Any] = [int(run_id)]
            if status:
                sql += " AND detection_status = ?"
                params.append(str(status))
            if audience:
                sql += " AND delivery_audience = ?"
                params.append(str(audience))
            if delivery_result:
                sql += " AND delivery_result = ?"
                params.append(str(delivery_result))
            if search:
                sql += " AND (lot LIKE ? OR observaciones LIKE ? OR motivo_sin_envio LIKE ?)"
                token = f"%{str(search).strip()}%"
                params.extend([token, token, token])
            sql += " ORDER BY lot ASC, id ASC"
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "job_id": row["job_id"],
                    "execution_id": row["execution_id"],
                    "executed_at": row["executed_at"],
                    "lot": row["lot"],
                    "detection_status": row["detection_status"],
                    "num_findings": row["num_findings"],
                    "report_generated": bool(row["report_generated"]),
                    "email_sent": bool(row["email_sent"]),
                    "motivo_sin_envio": row["motivo_sin_envio"],
                    "observaciones": row["observaciones"],
                    "delivery_audience": row["delivery_audience"] if "delivery_audience" in row.keys() else None,
                    "delivery_result": row["delivery_result"] if "delivery_result" in row.keys() else None,
                    "payload": _json_loads(row["payload_json"], {}),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def _hydrate_run(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "job_id": row["job_id"],
            "job_name": row["job_name"] if "job_name" in row.keys() else None,
            "audit_type": row["audit_type"] if "audit_type" in row.keys() else None,
            "profile": row["profile"] if "profile" in row.keys() else None,
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "status": row["status"],
            "duration_ms": row["duration_ms"],
            "summary": _json_loads(row["summary_json"], {}),
            "error_message": row["error_message"],
            "report_path": row["report_path"],
            "deliveries": _json_loads(row["deliveries_json"], []),
            "created_tasks": _json_loads(row["created_tasks_json"], []),
            "created_at": row["created_at"] if "created_at" in row.keys() else None,
        }

    def list_runs(self, job_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 100), 500))
        sql = """
            SELECT r.*, j.name AS job_name, j.audit_type AS audit_type, j.profile AS profile
            FROM job_runs r
            JOIN scheduled_jobs j ON j.id = r.job_id
        """
        params: List[Any] = []
        if job_id is not None:
            sql += " WHERE r.job_id = ?"
            params.append(int(job_id))
        sql += " ORDER BY r.started_at DESC, r.id DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._hydrate_run(row) for row in rows]

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT r.*, j.name AS job_name, j.audit_type AS audit_type, j.profile AS profile
                FROM job_runs r
                JOIN scheduled_jobs j ON j.id = r.job_id
                WHERE r.id = ?
                """,
                (int(run_id),),
            ).fetchone()
            return self._hydrate_run(row) if row else None

    def get_maintenance_summary(self, *, retain_days: int = 30) -> Dict[str, Any]:
        retain_days = max(1, int(retain_days or 30))
        cutoff_iso = utc_now_iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retain_days))
        with self._get_connection() as conn:
            old_runs = conn.execute(
                """
                SELECT id
                FROM job_runs
                WHERE COALESCE(finished_at, started_at) < ?
                """,
                (cutoff_iso,),
            ).fetchall()
            old_run_ids = [int(row["id"]) for row in old_runs]
            old_lot_statuses = 0
            old_delivery_attempts = 0
            old_retry_items = 0
            old_analytics = 0
            if old_run_ids:
                placeholders = ",".join("?" for _ in old_run_ids)
                old_lot_statuses = int(
                    conn.execute(
                        f"SELECT COUNT(*) AS total FROM job_run_lot_statuses WHERE run_id IN ({placeholders})",
                        old_run_ids,
                    ).fetchone()["total"]
                )
                old_delivery_attempts = int(
                    conn.execute(
                        f"SELECT COUNT(*) AS total FROM delivery_attempts WHERE run_id IN ({placeholders})",
                        old_run_ids,
                    ).fetchone()["total"]
                )
                old_retry_items = int(
                    conn.execute(
                        f"SELECT COUNT(*) AS total FROM delivery_retry_queue WHERE run_id IN ({placeholders})",
                        old_run_ids,
                    ).fetchone()["total"]
                )
                old_analytics = int(
                    conn.execute(
                        f"SELECT COUNT(*) AS total FROM audit_execution_facts WHERE run_id IN ({placeholders})",
                        old_run_ids,
                    ).fetchone()["total"]
                ) + int(
                    conn.execute(
                        f"SELECT COUNT(*) AS total FROM audit_lot_facts WHERE run_id IN ({placeholders})",
                        old_run_ids,
                    ).fetchone()["total"]
                ) + int(
                    conn.execute(
                        f"SELECT COUNT(*) AS total FROM audit_schema_facts WHERE run_id IN ({placeholders})",
                        old_run_ids,
                    ).fetchone()["total"]
                ) + int(
                    conn.execute(
                        f"SELECT COUNT(*) AS total FROM audit_check_facts WHERE run_id IN ({placeholders})",
                        old_run_ids,
                    ).fetchone()["total"]
                )
            retry_queue_total = int(conn.execute("SELECT COUNT(*) AS total FROM delivery_retry_queue").fetchone()["total"])
            pending_retry_total = int(
                conn.execute(
                    "SELECT COUNT(*) AS total FROM delivery_retry_queue WHERE status IN ('pending', 'in_progress')"
                ).fetchone()["total"]
            )
        return {
            "retain_days": retain_days,
            "cutoff_iso": cutoff_iso,
            "old_runs": len(old_run_ids),
            "old_lot_statuses": old_lot_statuses,
            "old_delivery_attempts": old_delivery_attempts,
            "old_retry_items": old_retry_items,
            "old_analytics_rows": old_analytics,
            "retry_queue_total": retry_queue_total,
            "retry_queue_pending": pending_retry_total,
        }

    def purge_history(self, *, retain_days: int = 30) -> Dict[str, Any]:
        retain_days = max(1, int(retain_days or 30))
        cutoff_iso = utc_now_iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retain_days))
        with self._get_connection() as conn:
            runs = conn.execute(
                """
                SELECT id, report_path
                FROM job_runs
                WHERE COALESCE(finished_at, started_at) < ?
                ORDER BY id ASC
                """,
                (cutoff_iso,),
            ).fetchall()
            run_ids = [int(row["id"]) for row in runs]
            report_paths = [str(row["report_path"]) for row in runs if row["report_path"]]
            if not run_ids:
                return {
                    "retain_days": retain_days,
                    "cutoff_iso": cutoff_iso,
                    "deleted_runs": 0,
                    "deleted_lot_statuses": 0,
                    "deleted_delivery_attempts": 0,
                    "deleted_retry_items": 0,
                    "deleted_tasks": 0,
                    "report_paths": [],
                }
            placeholders = ",".join("?" for _ in run_ids)
            deleted_lot_statuses = int(
                conn.execute(
                    f"SELECT COUNT(*) AS total FROM job_run_lot_statuses WHERE run_id IN ({placeholders})",
                    run_ids,
                ).fetchone()["total"]
            )
            deleted_delivery_attempts = int(
                conn.execute(
                    f"SELECT COUNT(*) AS total FROM delivery_attempts WHERE run_id IN ({placeholders})",
                    run_ids,
                ).fetchone()["total"]
            )
            deleted_retry_items = int(
                conn.execute(
                    f"SELECT COUNT(*) AS total FROM delivery_retry_queue WHERE run_id IN ({placeholders})",
                    run_ids,
                ).fetchone()["total"]
            )
            deleted_tasks = int(
                conn.execute(
                    f"SELECT COUNT(*) AS total FROM internal_tasks WHERE source_run_id IN ({placeholders})",
                    run_ids,
                ).fetchone()["total"]
            )
            deleted_analytics = int(
                conn.execute(
                    f"SELECT COUNT(*) AS total FROM audit_execution_facts WHERE run_id IN ({placeholders})",
                    run_ids,
                ).fetchone()["total"]
            ) + int(
                conn.execute(
                    f"SELECT COUNT(*) AS total FROM audit_lot_facts WHERE run_id IN ({placeholders})",
                    run_ids,
                ).fetchone()["total"]
            ) + int(
                conn.execute(
                    f"SELECT COUNT(*) AS total FROM audit_schema_facts WHERE run_id IN ({placeholders})",
                    run_ids,
                ).fetchone()["total"]
            ) + int(
                conn.execute(
                    f"SELECT COUNT(*) AS total FROM audit_check_facts WHERE run_id IN ({placeholders})",
                    run_ids,
                ).fetchone()["total"]
            )
            conn.execute(f"DELETE FROM audit_execution_facts WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM audit_lot_facts WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM audit_schema_facts WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM audit_check_facts WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM job_run_lot_statuses WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM delivery_attempts WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM delivery_retry_queue WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM internal_tasks WHERE source_run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM job_runs WHERE id IN ({placeholders})", run_ids)
            conn.commit()
        return {
            "retain_days": retain_days,
            "cutoff_iso": cutoff_iso,
            "deleted_runs": len(run_ids),
            "deleted_lot_statuses": deleted_lot_statuses,
            "deleted_delivery_attempts": deleted_delivery_attempts,
            "deleted_retry_items": deleted_retry_items,
            "deleted_tasks": deleted_tasks,
            "deleted_analytics_rows": deleted_analytics,
            "report_paths": report_paths,
        }

    def _hydrate_task(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "source_run_id": row["source_run_id"],
            "source_job_id": row["source_job_id"],
            "title": row["title"],
            "severity": row["severity"],
            "priority": row["priority"],
            "status": row["status"],
            "assigned_to": row["assigned_to"],
            "description": row["description"],
            "metadata": _json_loads(row["metadata_json"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "resolved_at": row["resolved_at"],
        }

    def create_task(
        self,
        *,
        source_run_id: Optional[int],
        source_job_id: Optional[int],
        title: str,
        severity: str,
        priority: str = "normal",
        description: str = "",
        assigned_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO internal_tasks (
                    source_run_id, source_job_id, title, severity, priority, status,
                    assigned_to, description, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'pendent', ?, ?, ?, ?, ?)
                """,
                (
                    source_run_id,
                    source_job_id,
                    title,
                    severity,
                    priority,
                    assigned_to,
                    description,
                    _json_dumps(metadata, {}),
                    now,
                    now,
                ),
            )
            conn.commit()
            task_id = int(cursor.lastrowid)
        return self.get_task(task_id)

    def list_tasks(self, status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 200), 500))
        sql = "SELECT * FROM internal_tasks"
        params: List[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._hydrate_task(row) for row in rows]

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM internal_tasks WHERE id = ?", (int(task_id),)).fetchone()
            return self._hydrate_task(row) if row else None

    def update_task(self, task_id: int, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = self.get_task(task_id)
        if not current:
            return None

        metadata = dict(current.get("metadata") or {})
        comment = str(fields.get("comment") or "").strip()
        if comment:
            comments = metadata.get("comments") or []
            comments.append({"text": comment, "created_at": _utc_now_iso()})
            metadata["comments"] = comments

        status = fields.get("status", current["status"])
        resolved_at = current["resolved_at"]
        if status in {"resolta", "descartada"}:
            resolved_at = _utc_now_iso()
        elif status not in {"resolta", "descartada"}:
            resolved_at = None

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE internal_tasks
                SET status = ?, assigned_to = ?, metadata_json = ?, updated_at = ?, resolved_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    fields.get("assigned_to", current.get("assigned_to")),
                    _json_dumps(metadata, {}),
                    _utc_now_iso(),
                    resolved_at,
                    int(task_id),
                ),
            )
            conn.commit()
        return self.get_task(task_id)

    def list_severity_rules(self, scope: Optional[str] = None, job_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            return self._list_rules(conn, scope=scope, job_id=job_id)

    def get_severity_rule(self, rule_id: int) -> Optional[Dict[str, Any]]:
        for item in self.list_severity_rules():
            if int(item["id"]) == int(rule_id):
                return item
        return None

    def create_severity_rule(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO severity_rules (
                    scope, job_id, severity, create_task, task_priority, send_email, attach_report,
                    recipients_json, conditions_json, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("scope", "global"),
                    payload.get("job_id"),
                    payload["severity"],
                    int(bool(payload.get("create_task", False))),
                    payload.get("task_priority", "normal"),
                    int(bool(payload.get("send_email", False))),
                    int(bool(payload.get("attach_report", True))),
                    _json_dumps(payload.get("recipients"), []),
                    _json_dumps(payload.get("conditions"), {}),
                    int(bool(payload.get("enabled", True))),
                    now,
                    now,
                ),
            )
            rule_id = int(cursor.lastrowid)
            conn.commit()
        return self.get_severity_rule(rule_id)

    def update_severity_rule(self, rule_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = self.get_severity_rule(rule_id)
        if not current:
            return None
        merged = {**current, **payload}
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE severity_rules
                SET severity = ?, create_task = ?, task_priority = ?, send_email = ?, attach_report = ?,
                    recipients_json = ?, conditions_json = ?, enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged["severity"],
                    int(bool(merged.get("create_task", False))),
                    merged.get("task_priority", "normal"),
                    int(bool(merged.get("send_email", False))),
                    int(bool(merged.get("attach_report", True))),
                    _json_dumps(merged.get("recipients"), []),
                    _json_dumps(merged.get("conditions"), {}),
                    int(bool(merged.get("enabled", True))),
                    _utc_now_iso(),
                    int(rule_id),
                ),
            )
            conn.commit()
        return self.get_severity_rule(rule_id)

    def get_delivery_config(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM delivery_config WHERE id = 1").fetchone()
            if not row:
                return {
                    "smtp_host": "",
                    "smtp_port": 587,
                    "smtp_username": "",
                    "smtp_password": "",
                    "smtp_use_tls": True,
                    "from_email": "",
                    "default_recipients": [],
                    "failure_notification_recipients": [],
                    "teams_webhook": "",
                    "sharepoint_site": "",
                    "sharepoint_library": "",
                    "sharepoint_folder": "",
                    "auto_purge_enabled": True,
                    "history_retention_days": 30,
                    "retry_retention_days": 30,
                    "last_auto_purge_at": None,
                }
            return {
                "smtp_host": row["smtp_host"] or "",
                "smtp_port": int(row["smtp_port"] or 587),
                "smtp_username": row["smtp_username"] or "",
                "smtp_password": row["smtp_password"] or "",
                "smtp_use_tls": bool(row["smtp_use_tls"]),
                "from_email": row["from_email"] or "",
                "default_recipients": _json_loads(row["default_recipients_json"], []),
                "failure_notification_recipients": _json_loads(row["failure_notification_recipients_json"], []),
                "teams_webhook": row["teams_webhook"] or "",
                "sharepoint_site": row["sharepoint_site"] or "",
                "sharepoint_library": row["sharepoint_library"] or "",
                "sharepoint_folder": row["sharepoint_folder"] or "",
                "auto_purge_enabled": bool(row["auto_purge_enabled"]) if "auto_purge_enabled" in row.keys() else True,
                "history_retention_days": int(row["history_retention_days"] or 30) if "history_retention_days" in row.keys() else 30,
                "retry_retention_days": int(row["retry_retention_days"] or 30) if "retry_retention_days" in row.keys() else 30,
                "last_auto_purge_at": row["last_auto_purge_at"] if "last_auto_purge_at" in row.keys() else None,
                "updated_at": row["updated_at"],
            }

    def update_delivery_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_delivery_config()
        merged = {**current, **payload}
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE delivery_config
                SET smtp_host = ?, smtp_port = ?, smtp_username = ?, smtp_password = ?, smtp_use_tls = ?,
                    from_email = ?, default_recipients_json = ?, failure_notification_recipients_json = ?, teams_webhook = ?, sharepoint_site = ?,
                    sharepoint_library = ?, sharepoint_folder = ?, auto_purge_enabled = ?, history_retention_days = ?,
                    retry_retention_days = ?, last_auto_purge_at = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    merged.get("smtp_host", ""),
                    int(merged.get("smtp_port") or 587),
                    merged.get("smtp_username", ""),
                    merged.get("smtp_password", ""),
                    int(bool(merged.get("smtp_use_tls", True))),
                    merged.get("from_email", ""),
                    _json_dumps(merged.get("default_recipients"), []),
                    _json_dumps(merged.get("failure_notification_recipients"), []),
                    merged.get("teams_webhook", ""),
                    merged.get("sharepoint_site", ""),
                    merged.get("sharepoint_library", ""),
                    merged.get("sharepoint_folder", ""),
                    int(bool(merged.get("auto_purge_enabled", True))),
                    max(1, int(merged.get("history_retention_days") or 30)),
                    max(1, int(merged.get("retry_retention_days") or 30)),
                    merged.get("last_auto_purge_at"),
                    _utc_now_iso(),
                ),
            )
            conn.commit()
        return self.get_delivery_config()

    def get_delivery_routes(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT tic_summary_recipients_json, provider_routes_json FROM delivery_config WHERE id = 1"
            ).fetchone()
            route_rows = conn.execute(
                """
                SELECT lot_code, label, emails_json, enabled
                FROM lot_delivery_routes
                WHERE audience = 'provider'
                ORDER BY lot_code ASC
                """
            ).fetchall()
            if not row:
                return {"tic_summary_recipients": [], "providers": []}
            providers = [
                {
                    "provider_code": route["lot_code"],
                    "label": route["label"] or route["lot_code"],
                    "emails": _json_loads(route["emails_json"], []),
                    "enabled": bool(route["enabled"]),
                }
                for route in route_rows
            ]
            if not providers:
                providers = _json_loads(row["provider_routes_json"], [])
            return {
                "tic_summary_recipients": _json_loads(row["tic_summary_recipients_json"], []),
                "providers": providers,
            }

    def update_delivery_routes(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get_delivery_routes()
        merged = {**current, **payload}
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE delivery_config
                SET tic_summary_recipients_json = ?, provider_routes_json = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    _json_dumps(merged.get("tic_summary_recipients"), []),
                    _json_dumps(merged.get("providers"), []),
                    _utc_now_iso(),
                ),
            )
            for item in merged.get("providers") or []:
                conn.execute(
                    """
                    INSERT INTO lot_delivery_routes (lot_code, audience, label, emails_json, enabled, source, created_at, updated_at)
                    VALUES (?, 'provider', ?, ?, ?, 'delivery_routes', ?, ?)
                    ON CONFLICT(lot_code, audience) DO UPDATE SET
                        label = excluded.label,
                        emails_json = excluded.emails_json,
                        enabled = excluded.enabled,
                        source = excluded.source,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(item.get("provider_code") or "").strip(),
                        str(item.get("label") or item.get("provider_code") or "").strip(),
                        _json_dumps(item.get("emails"), []),
                        int(bool(item.get("enabled", True))),
                        _utc_now_iso(),
                        _utc_now_iso(),
                    ),
                )
            conn.commit()
        return self.get_delivery_routes()

    def record_change_event(
        self,
        *,
        entity_type: str,
        entity_key: str,
        action: str,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO automation_change_events (
                    entity_type, entity_key, action, actor, reason, before_json, after_json, context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(entity_type),
                    str(entity_key),
                    str(action),
                    actor,
                    reason,
                    _json_dumps(before, {}),
                    _json_dumps(after, {}),
                    _json_dumps(context, {}),
                    now,
                ),
            )
            event_id = int(cursor.lastrowid)
            conn.commit()
        return self.list_change_events(event_id=event_id, limit=1)[0]

    def list_change_events(
        self,
        *,
        entity_type: Optional[str] = None,
        entity_key: Optional[str] = None,
        limit: int = 200,
        event_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM automation_change_events WHERE 1=1"
        params: List[Any] = []
        if event_id is not None:
            sql += " AND id = ?"
            params.append(int(event_id))
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(str(entity_type))
        if entity_key:
            sql += " AND entity_key = ?"
            params.append(str(entity_key))
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit or 200), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": row["id"],
                    "entity_type": row["entity_type"],
                    "entity_key": row["entity_key"],
                    "action": row["action"],
                    "actor": row["actor"],
                    "reason": row["reason"],
                    "before": _json_loads(row["before_json"], {}),
                    "after": _json_loads(row["after_json"], {}),
                    "context": _json_loads(row["context_json"], {}),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def create_master_lot_backfill_run(
        self,
        *,
        source_hash: str,
        summary: Dict[str, Any],
        actor: Optional[str] = None,
        reason: Optional[str] = None,
        source: str = "schema_lots",
        status: str = "preview",
    ) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO master_lot_backfill_runs (
                    source, source_hash, status, actor, reason, summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    source_hash,
                    status,
                    actor,
                    reason,
                    _json_dumps(summary, {}),
                    now,
                ),
            )
            run_id = int(cursor.lastrowid)
            conn.commit()
        return self.get_master_lot_backfill_run(run_id)

    def replace_master_lot_backfill_items(self, backfill_run_id: int, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = _utc_now_iso()
        with self._get_connection() as conn:
            conn.execute("DELETE FROM master_lot_backfill_items WHERE backfill_run_id = ?", (int(backfill_run_id),))
            for item in items or []:
                conn.execute(
                    """
                    INSERT INTO master_lot_backfill_items (
                        backfill_run_id, lot_code, proposed_label, schema_names_json, action, conflict_code,
                        selected, applied, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(backfill_run_id),
                        str(item.get("lot_code") or "").strip().upper(),
                        str(item.get("proposed_label") or item.get("lot_code") or "").strip(),
                        _json_dumps(item.get("schema_names"), []),
                        str(item.get("action") or "noop").strip(),
                        item.get("conflict_code"),
                        int(bool(item.get("selected", True))),
                        int(bool(item.get("applied", False))),
                        item.get("notes"),
                        now,
                    ),
                )
            conn.commit()
        return self.list_master_lot_backfill_items(backfill_run_id)

    def list_master_lot_backfill_items(self, backfill_run_id: int) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM master_lot_backfill_items
                WHERE backfill_run_id = ?
                ORDER BY lot_code ASC, id ASC
                """,
                (int(backfill_run_id),),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "backfill_run_id": row["backfill_run_id"],
                    "lot_code": row["lot_code"],
                    "proposed_label": row["proposed_label"],
                    "schema_names": _json_loads(row["schema_names_json"], []),
                    "action": row["action"],
                    "conflict_code": row["conflict_code"],
                    "selected": bool(row["selected"]),
                    "applied": bool(row["applied"]),
                    "notes": row["notes"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def list_master_lot_backfill_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM master_lot_backfill_runs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, min(int(limit or 20), 100)),),
            ).fetchall()
            return [self.get_master_lot_backfill_run(int(row["id"])) for row in rows]

    def get_master_lot_backfill_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM master_lot_backfill_runs WHERE id = ?",
                (int(run_id),),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "source": row["source"],
                "source_hash": row["source_hash"],
                "status": row["status"],
                "actor": row["actor"],
                "reason": row["reason"],
                "summary": _json_loads(row["summary_json"], {}),
                "created_at": row["created_at"],
                "applied_at": row["applied_at"],
                "items": self.list_master_lot_backfill_items(int(row["id"])),
            }

    def update_master_lot_backfill_run(
        self,
        run_id: int,
        *,
        status: Optional[str] = None,
        summary: Optional[Dict[str, Any]] = None,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
        applied_at: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        current = self.get_master_lot_backfill_run(run_id)
        if not current:
            return None
        merged_summary = summary if summary is not None else current.get("summary") or {}
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE master_lot_backfill_runs
                SET status = ?, actor = ?, reason = ?, summary_json = ?, applied_at = ?
                WHERE id = ?
                """,
                (
                    status or current.get("status"),
                    actor if actor is not None else current.get("actor"),
                    reason if reason is not None else current.get("reason"),
                    _json_dumps(merged_summary, {}),
                    applied_at if applied_at is not None else current.get("applied_at"),
                    int(run_id),
                ),
            )
            conn.commit()
        return self.get_master_lot_backfill_run(run_id)

    def mark_master_lot_backfill_items_applied(self, backfill_run_id: int, lot_codes: List[str]) -> None:
        normalized = [str(item or "").strip().upper() for item in lot_codes if str(item or "").strip()]
        if not normalized:
            return
        with self._get_connection() as conn:
            conn.executemany(
                """
                UPDATE master_lot_backfill_items
                SET applied = 1
                WHERE backfill_run_id = ? AND lot_code = ?
                """,
                [(int(backfill_run_id), item) for item in normalized],
            )
            conn.commit()

    def list_master_lots(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM master_lots"
        params: List[Any] = []
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY code ASC"
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "code": row["code"],
                    "label": row["label"],
                    "description": row["description"] or "",
                    "enabled": bool(row["enabled"]),
                    "metadata": _json_loads(row["metadata_json"], {}),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def upsert_master_lots(
        self,
        items: List[Dict[str, Any]],
        *,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        now = _utc_now_iso()
        events: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            for item in items or []:
                code = str(item.get("code") or "").strip().upper()
                if not code:
                    continue
                label = str(item.get("label") or code).strip() or code
                current_row = conn.execute("SELECT * FROM master_lots WHERE code = ?", (code,)).fetchone()
                before = None
                if current_row:
                    before = {
                        "code": current_row["code"],
                        "label": current_row["label"],
                        "description": current_row["description"] or "",
                        "enabled": bool(current_row["enabled"]),
                        "metadata": _json_loads(current_row["metadata_json"], {}),
                    }
                after = {
                    "code": code,
                    "label": label,
                    "description": str(item.get("description") or "").strip(),
                    "enabled": bool(item.get("enabled", True)),
                    "metadata": item.get("metadata") or {},
                }
                conn.execute(
                    """
                    INSERT INTO master_lots (code, label, description, enabled, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                        label = excluded.label,
                        description = excluded.description,
                        enabled = excluded.enabled,
                        metadata_json = excluded.metadata_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        code,
                        label,
                        str(item.get("description") or "").strip(),
                        int(bool(item.get("enabled", True))),
                        _json_dumps(item.get("metadata"), {}),
                        now,
                        now,
                    ),
                )
                if before != after:
                    events.append(
                        {
                            "entity_type": "master_lot",
                            "entity_key": code,
                            "action": "update" if before else "create",
                            "before": before,
                            "after": after,
                        }
                    )
            conn.commit()
        for event in events:
            self.record_change_event(
                entity_type=event["entity_type"],
                entity_key=event["entity_key"],
                action=event["action"],
                actor=actor,
                reason=reason,
                before=event["before"],
                after=event["after"],
                context=context,
            )
        return self.list_master_lots()

    def list_lot_routes(self, audience: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM lot_delivery_routes"
        params: List[Any] = []
        if audience:
            sql += " WHERE audience = ?"
            params.append(audience)
        sql += " ORDER BY lot_code ASC, audience ASC"
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": row["id"],
                    "lot_code": row["lot_code"],
                    "audience": row["audience"],
                    "label": row["label"] or row["lot_code"],
                    "emails": _json_loads(row["emails_json"], []),
                    "enabled": bool(row["enabled"]),
                    "source": row["source"] or "",
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def upsert_lot_routes(
        self,
        items: List[Dict[str, Any]],
        *,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        now = _utc_now_iso()
        events: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            for item in items or []:
                lot_code = str(item.get("lot_code") or item.get("provider_code") or "").strip().upper()
                audience = str(item.get("audience") or "provider").strip().lower()
                if not lot_code:
                    continue
                current_row = conn.execute(
                    "SELECT * FROM lot_delivery_routes WHERE lot_code = ? AND audience = ?",
                    (lot_code, audience),
                ).fetchone()
                before = None
                if current_row:
                    before = {
                        "lot_code": current_row["lot_code"],
                        "audience": current_row["audience"],
                        "label": current_row["label"] or current_row["lot_code"],
                        "emails": _json_loads(current_row["emails_json"], []),
                        "enabled": bool(current_row["enabled"]),
                        "source": current_row["source"] or "",
                    }
                after = {
                    "lot_code": lot_code,
                    "audience": audience,
                    "label": str(item.get("label") or lot_code).strip() or lot_code,
                    "emails": item.get("emails") or [],
                    "enabled": bool(item.get("enabled", True)),
                    "source": str(item.get("source") or "automation").strip() or "automation",
                }
                conn.execute(
                    """
                    INSERT INTO lot_delivery_routes (lot_code, audience, label, emails_json, enabled, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(lot_code, audience) DO UPDATE SET
                        label = excluded.label,
                        emails_json = excluded.emails_json,
                        enabled = excluded.enabled,
                        source = excluded.source,
                        updated_at = excluded.updated_at
                    """,
                    (
                        lot_code,
                        audience,
                        str(item.get("label") or lot_code).strip() or lot_code,
                        _json_dumps(item.get("emails"), []),
                        int(bool(item.get("enabled", True))),
                        str(item.get("source") or "automation").strip() or "automation",
                        now,
                        now,
                    ),
                )
                if before != after:
                    events.append(
                        {
                            "entity_type": "lot_route",
                            "entity_key": f"{lot_code}:{audience}",
                            "action": "update" if before else "create",
                            "before": before,
                            "after": after,
                        }
                    )
            conn.commit()
        for event in events:
            self.record_change_event(
                entity_type=event["entity_type"],
                entity_key=event["entity_key"],
                action=event["action"],
                actor=actor,
                reason=reason,
                before=event["before"],
                after=event["after"],
                context=context,
            )
        return self.list_lot_routes()

    def list_delivery_templates(self, audience: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM delivery_templates"
        params: List[Any] = []
        if audience:
            sql += " WHERE audience = ?"
            params.append(audience)
        sql += " ORDER BY template_key ASC"
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": row["id"],
                    "template_key": row["template_key"],
                    "audience": row["audience"],
                    "subject_template": row["subject_template"],
                    "body_template": row["body_template"],
                    "enabled": bool(row["enabled"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def upsert_delivery_templates(
        self,
        items: List[Dict[str, Any]],
        *,
        actor: Optional[str] = None,
        reason: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        now = _utc_now_iso()
        events: List[Dict[str, Any]] = []
        with self._get_connection() as conn:
            for item in items or []:
                template_key = str(item.get("template_key") or "").strip()
                if not template_key:
                    continue
                current_row = conn.execute(
                    "SELECT * FROM delivery_templates WHERE template_key = ?",
                    (template_key,),
                ).fetchone()
                before = None
                if current_row:
                    before = {
                        "template_key": current_row["template_key"],
                        "audience": current_row["audience"],
                        "subject_template": current_row["subject_template"],
                        "body_template": current_row["body_template"],
                        "enabled": bool(current_row["enabled"]),
                    }
                after = {
                    "template_key": template_key,
                    "audience": str(item.get("audience") or "provider").strip().lower(),
                    "subject_template": str(item.get("subject_template") or "").strip(),
                    "body_template": str(item.get("body_template") or "").strip(),
                    "enabled": bool(item.get("enabled", True)),
                }
                conn.execute(
                    """
                    INSERT INTO delivery_templates (template_key, audience, subject_template, body_template, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(template_key) DO UPDATE SET
                        audience = excluded.audience,
                        subject_template = excluded.subject_template,
                        body_template = excluded.body_template,
                        enabled = excluded.enabled,
                        updated_at = excluded.updated_at
                    """,
                    (
                        template_key,
                        str(item.get("audience") or "provider").strip().lower(),
                        str(item.get("subject_template") or "").strip(),
                        str(item.get("body_template") or "").strip(),
                        int(bool(item.get("enabled", True))),
                        now,
                        now,
                    ),
                )
                if before != after:
                    events.append(
                        {
                            "entity_type": "delivery_template",
                            "entity_key": template_key,
                            "action": "update" if before else "create",
                            "before": before,
                            "after": after,
                        }
                    )
            conn.commit()
        for event in events:
            self.record_change_event(
                entity_type=event["entity_type"],
                entity_key=event["entity_key"],
                action=event["action"],
                actor=actor,
                reason=reason,
                before=event["before"],
                after=event["after"],
                context=context,
            )
        return self.list_delivery_templates()

    def create_delivery_attempt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO delivery_attempts (
                    run_id, job_id, lot, audience, attempt_no, status, error_message, recipients_json,
                    attachment_name, template_key, template_snapshot_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("run_id"),
                    payload.get("job_id"),
                    payload.get("lot"),
                    payload.get("audience"),
                    int(payload.get("attempt_no") or 1),
                    payload.get("status"),
                    payload.get("error_message"),
                    _json_dumps(payload.get("recipients"), []),
                    payload.get("attachment_name"),
                    payload.get("template_key"),
                    _json_dumps(payload.get("template_snapshot"), {}),
                    now,
                ),
            )
            attempt_id = int(cursor.lastrowid)
            conn.commit()
        return self.list_delivery_attempts(attempt_id=attempt_id)[0]

    def list_delivery_attempts(
        self,
        *,
        run_id: Optional[int] = None,
        lot: Optional[str] = None,
        audience: Optional[str] = None,
        status: Optional[str] = None,
        attempt_id: Optional[int] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM delivery_attempts WHERE 1=1"
        params: List[Any] = []
        if attempt_id is not None:
            sql += " AND id = ?"
            params.append(int(attempt_id))
        if run_id is not None:
            sql += " AND run_id = ?"
            params.append(int(run_id))
        if lot:
            sql += " AND lot = ?"
            params.append(str(lot))
        if audience:
            sql += " AND audience = ?"
            params.append(str(audience))
        if status:
            sql += " AND status = ?"
            params.append(str(status))
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit or 200), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "job_id": row["job_id"],
                    "lot": row["lot"],
                    "audience": row["audience"],
                    "attempt_no": row["attempt_no"],
                    "status": row["status"],
                    "error_message": row["error_message"],
                    "recipients": _json_loads(row["recipients_json"], []),
                    "attachment_name": row["attachment_name"],
                    "template_key": row["template_key"],
                    "template_snapshot": _json_loads(row["template_snapshot_json"], {}),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def create_retry_queue_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO delivery_retry_queue (
                    run_id, job_id, lot, audience, status, requested_at, requested_by, last_attempt_at,
                    attempts_made, error_message, next_attempt_at, max_attempts, retry_mode, error_class,
                    dedupe_key, lock_token, locked_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("run_id"),
                    payload.get("job_id"),
                    payload.get("lot"),
                    payload.get("audience"),
                    payload.get("status", "pending"),
                    payload.get("requested_at", now),
                    payload.get("requested_by"),
                    payload.get("last_attempt_at"),
                    int(payload.get("attempts_made") or 0),
                    payload.get("error_message"),
                    payload.get("next_attempt_at"),
                    int(payload.get("max_attempts") or 4),
                    payload.get("retry_mode") or "manual",
                    payload.get("error_class"),
                    payload.get("dedupe_key"),
                    payload.get("lock_token"),
                    payload.get("locked_at"),
                    now,
                    now,
                ),
            )
            queue_id = int(cursor.lastrowid)
            conn.commit()
        return self.list_retry_queue(queue_id=queue_id)[0]

    def list_retry_queue(
        self,
        *,
        status: Optional[str] = None,
        run_id: Optional[int] = None,
        audience: Optional[str] = None,
        retry_mode: Optional[str] = None,
        due_only: bool = False,
        queue_id: Optional[int] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM delivery_retry_queue WHERE 1=1"
        params: List[Any] = []
        if queue_id is not None:
            sql += " AND id = ?"
            params.append(int(queue_id))
        if status:
            sql += " AND status = ?"
            params.append(str(status))
        if run_id is not None:
            sql += " AND run_id = ?"
            params.append(int(run_id))
        if audience:
            sql += " AND audience = ?"
            params.append(str(audience))
        if retry_mode:
            sql += " AND retry_mode = ?"
            params.append(str(retry_mode))
        if due_only:
            sql += " AND status = 'pending' AND retry_mode = 'auto' AND COALESCE(next_attempt_at, requested_at) <= ?"
            params.append(_utc_now_iso())
        sql += " ORDER BY COALESCE(next_attempt_at, requested_at) ASC, id ASC LIMIT ?"
        params.append(max(1, min(int(limit or 200), 500)))
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "job_id": row["job_id"],
                    "lot": row["lot"],
                    "audience": row["audience"],
                    "status": row["status"],
                    "requested_at": row["requested_at"],
                    "requested_by": row["requested_by"],
                    "last_attempt_at": row["last_attempt_at"],
                    "attempts_made": row["attempts_made"],
                    "error_message": row["error_message"],
                    "next_attempt_at": row["next_attempt_at"] if "next_attempt_at" in row.keys() else None,
                    "max_attempts": row["max_attempts"] if "max_attempts" in row.keys() else 4,
                    "retry_mode": row["retry_mode"] if "retry_mode" in row.keys() else "manual",
                    "error_class": row["error_class"] if "error_class" in row.keys() else None,
                    "dedupe_key": row["dedupe_key"] if "dedupe_key" in row.keys() else None,
                    "lock_token": row["lock_token"] if "lock_token" in row.keys() else None,
                    "locked_at": row["locked_at"] if "locked_at" in row.keys() else None,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def claim_due_retry_queue_items(
        self,
        *,
        limit: int = 10,
        now_iso: Optional[str] = None,
        stale_lock_before: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        now_value = str(now_iso or _utc_now_iso())
        stale_value = str(stale_lock_before or now_value)
        claimed_ids: List[int] = []
        token = f"retry-lock-{now_value}"
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM delivery_retry_queue
                WHERE
                    (
                        status = 'pending'
                        AND retry_mode = 'auto'
                        AND COALESCE(next_attempt_at, requested_at) <= ?
                    )
                    OR (
                        status = 'in_progress'
                        AND retry_mode = 'auto'
                        AND locked_at IS NOT NULL
                        AND locked_at <= ?
                    )
                ORDER BY COALESCE(next_attempt_at, requested_at) ASC, id ASC
                LIMIT ?
                """,
                (now_value, stale_value, max(1, min(int(limit or 10), 50))),
            ).fetchall()
            for row in rows:
                updated = conn.execute(
                    """
                    UPDATE delivery_retry_queue
                    SET status = 'in_progress', lock_token = ?, locked_at = ?, updated_at = ?
                    WHERE id = ? AND (
                        status = 'pending'
                        OR (status = 'in_progress' AND locked_at IS NOT NULL AND locked_at <= ?)
                    )
                    """,
                    (token, now_value, now_value, int(row["id"]), stale_value),
                )
                if updated.rowcount:
                    claimed_ids.append(int(row["id"]))
            conn.commit()
        return [self.list_retry_queue(queue_id=item_id)[0] for item_id in claimed_ids]

    def update_retry_queue_item(self, queue_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current_items = self.list_retry_queue(queue_id=queue_id)
        if not current_items:
            return None
        current = current_items[0]
        merged = {**current, **payload}
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE delivery_retry_queue
                SET status = ?, requested_by = ?, last_attempt_at = ?, attempts_made = ?, error_message = ?,
                    next_attempt_at = ?, max_attempts = ?, retry_mode = ?, error_class = ?, dedupe_key = ?,
                    lock_token = ?, locked_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged.get("status"),
                    merged.get("requested_by"),
                    merged.get("last_attempt_at"),
                    int(merged.get("attempts_made") or 0),
                    merged.get("error_message"),
                    merged.get("next_attempt_at"),
                    int(merged.get("max_attempts") or 4),
                    merged.get("retry_mode") or "manual",
                    merged.get("error_class"),
                    merged.get("dedupe_key"),
                    merged.get("lock_token"),
                    merged.get("locked_at"),
                    _utc_now_iso(),
                    int(queue_id),
                ),
            )
            conn.commit()
        return self.list_retry_queue(queue_id=queue_id)[0]

    def purge_retry_queue(self, *, statuses: Optional[List[str]] = None) -> Dict[str, Any]:
        normalized_statuses = [str(item).strip() for item in (statuses or []) if str(item).strip()]
        with self._get_connection() as conn:
            sql = "SELECT COUNT(*) AS total FROM delivery_retry_queue"
            params: List[Any] = []
            if normalized_statuses:
                placeholders = ",".join("?" for _ in normalized_statuses)
                sql += f" WHERE status IN ({placeholders})"
                params.extend(normalized_statuses)
            deleted = int(conn.execute(sql, params).fetchone()["total"])
            delete_sql = "DELETE FROM delivery_retry_queue"
            if normalized_statuses:
                placeholders = ",".join("?" for _ in normalized_statuses)
                delete_sql += f" WHERE status IN ({placeholders})"
            conn.execute(delete_sql, params)
            conn.commit()
        return {
            "deleted_retry_items": deleted,
            "statuses": normalized_statuses or None,
        }

    def purge_retry_queue_older(
        self,
        *,
        retain_days: int = 30,
        statuses: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        retain_days = max(1, int(retain_days or 30))
        cutoff_iso = utc_now_iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retain_days))
        normalized_statuses = [str(item).strip() for item in (statuses or ["done", "failed", "cancelled", "exhausted"]) if str(item).strip()]
        placeholders = ",".join("?" for _ in normalized_statuses)
        params: List[Any] = [cutoff_iso, *normalized_statuses]
        with self._get_connection() as conn:
            deleted = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM delivery_retry_queue
                    WHERE updated_at < ?
                      AND status IN ({placeholders})
                    """,
                    params,
                ).fetchone()["total"]
            )
            conn.execute(
                f"""
                DELETE FROM delivery_retry_queue
                WHERE updated_at < ?
                  AND status IN ({placeholders})
                """,
                params,
            )
            conn.commit()
        return {
            "deleted_retry_items": deleted,
            "retain_days": retain_days,
            "cutoff_iso": cutoff_iso,
            "statuses": normalized_statuses,
        }
