import asyncio
import calendar
import datetime as dt
import json
import logging
import os
import re
import smtplib
import threading
import time
import zipfile
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.api.audit_engine import AuditEngine
from src.api.post_crq_audit import (
    run_post_crq_audit,
    build_post_crq_markdown_report,
    build_post_crq_pdf_report,
)
from src.api.post_crq_delivery_reports import build_post_crq_general_artifact, build_post_crq_provider_artifact
from src.api.post_crq_analytics import build_post_crq_analytics_payload
from src.api.post_crq_lot_status import (
    LOT_STATUS_NOT_APPLICABLE,
    LOT_STATUS_QUERY_ERROR,
    LOT_STATUS_UNMAPPED,
    LOT_STATUS_WITH_FINDINGS,
    LOT_STATUS_WITHOUT_FINDINGS,
    build_post_crq_lot_execution_matrix,
    normalize_distribution_job_config,
)
from src.api.report_builder import (
    build_standard_markdown, 
    build_standard_pdf,
)
from src.core.automation_store import AutomationStore
from src.core.config_loader import ConfigLoader
from src.core.db_manager import OracleDBManager
from src.core.sqlite_paths import resolve_sqlite_path
from src.core.time_utils import utc_isoformat, utc_now_naive


SEVERITY_OPTIONS = ["BAIX", "MITJA", "ALT", "CRITIC", "STOPPER"]
RETRY_BACKOFF_MINUTES = [5, 15, 60]
RETRY_STALE_LOCK_MINUTES = 10
RETRY_BATCH_SIZE = 10
DELIVERY_RESULT_SENT = "sent"
DELIVERY_RESULT_RETRY_PENDING = "retry_pending"
DELIVERY_RESULT_DELIVERY_ERROR = "delivery_error"
DELIVERY_RESULT_NO_ROUTE = "no_route"
DELIVERY_RESULT_ATTACHMENT_ERROR = "attachment_error"
DELIVERY_RESULT_SKIPPED_NO_FINDINGS = "skipped_no_findings"
DELIVERY_RESULT_SKIPPED_NOT_APPLICABLE = "skipped_not_applicable"
DELIVERY_RESULT_MANUAL_REVIEW = "manual_review"
logger = logging.getLogger(__name__)


class DeliverySendError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_class: str = DELIVERY_RESULT_DELIVERY_ERROR,
        retryable: bool = False,
        queued_retry: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.retryable = retryable
        self.queued_retry = queued_retry


DELIVERY_RUNTIME_EXCEPTIONS = (
    DeliverySendError,
    OSError,
    RuntimeError,
    TimeoutError,
    ValueError,
    TypeError,
    smtplib.SMTPException,
)


def utc_now() -> dt.datetime:
    return utc_now_naive()


def iso_utc(value: dt.datetime) -> str:
    return utc_isoformat(value)


def _local_timezone() -> dt.tzinfo:
    return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


def parse_iso_utc(value: Optional[str]) -> Optional[dt.datetime]:
    if not value or not str(value).strip():
        return None
    cleaned = str(value).strip().replace(" ", "T").replace("Z", "+00:00")
    try:
        if "T" in cleaned:
            # Intents per formats horaris
            try:
                if len(cleaned) >= 16:
                    # YYYY-MM-DDTHH:MM
                    parsed = dt.datetime.strptime(cleaned[:16], "%Y-%m-%dT%H:%M")
                else:
                    parsed = dt.datetime.fromisoformat(cleaned[:19] if len(cleaned) > 19 and "+" not in cleaned else cleaned)
            except ValueError:
                # Fallback al format ISO estàndard segur
                parsed = dt.datetime.fromisoformat(cleaned[:19] if len(cleaned) > 19 and "+" not in cleaned else cleaned)
        else:
            # Format data simple
            parsed = dt.datetime.combine(dt.date.fromisoformat(cleaned[:10]), dt.time.min)
        
        if parsed.tzinfo:
            parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
        else:
            parsed = parsed.replace(tzinfo=_local_timezone()).astimezone(dt.timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        # Fallback llat? final (nom?s data prefix)
        try:
            d = dt.date.fromisoformat(str(value)[:10])
            parsed = dt.datetime.combine(d, dt.time.min)
            return parsed.replace(tzinfo=_local_timezone()).astimezone(dt.timezone.utc).replace(tzinfo=None)
        except ValueError:
            return None


def normalize_severity(value: str) -> str:
    raw = (value or "").strip().upper()
    if "STOPPER" in raw:
        return "STOPPER"
    if "CRIT" in raw:
        return "CRITIC"
    if "ALT" in raw:
        return "ALT"
    if "MITJ" in raw:
        return "MITJA"
    return "BAIX"


def compute_next_run(schedule_type: str, schedule_config: Optional[Dict[str, Any]], now: Optional[dt.datetime] = None) -> Optional[str]:
    now = now or utc_now()
    config = schedule_config or {}
    start_at = parse_iso_utc(config.get("start_at"))
    if not start_at:
        return None

    schedule_type = (schedule_type or "once").lower()
    current = start_at

    if schedule_type == "once":
        return iso_utc(current) if current >= now else None

    if schedule_type == "daily":
        while current < now:
            current += dt.timedelta(days=1)
        return iso_utc(current)

    if schedule_type == "weekly":
        while current < now:
            current += dt.timedelta(days=7)
        return iso_utc(current)

    if schedule_type == "monthly":
        while current < now:
            current = _add_month(current)
        return iso_utc(current)

    return None


def next_after_reference(schedule_type: str, schedule_config: Optional[Dict[str, Any]], reference_iso: Optional[str]) -> Optional[str]:
    schedule_type = (schedule_type or "once").lower()
    reference = parse_iso_utc(reference_iso) or parse_iso_utc((schedule_config or {}).get("start_at"))
    if not reference:
        return None

    if schedule_type == "once":
        return None
    if schedule_type == "daily":
        return iso_utc(reference + dt.timedelta(days=1))
    if schedule_type == "weekly":
        return iso_utc(reference + dt.timedelta(days=7))
    if schedule_type == "monthly":
        return iso_utc(_add_month(reference))
    return None


def _add_month(value: dt.datetime) -> dt.datetime:
    month = value.month + 1
    year = value.year
    if month > 12:
        month = 1
        year += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


class AutomationService:
    def __init__(self, store: AutomationStore, config_loader: ConfigLoader, reports_dir: str = "resources/automation_reports"):
        self.store = store
        self.config_loader = config_loader
        self.reports_dir = reports_dir
        Path(self.reports_dir).mkdir(parents=True, exist_ok=True)
        self._running_jobs = set()
        self._job_threads: set[threading.Thread] = set()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="automation-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning("Automation scheduler thread did not stop within timeout")
        with self._lock:
            active_threads = list(self._job_threads)
        for thread in active_threads:
            thread.join(timeout=5)
            if thread.is_alive():
                logger.warning("Automation job thread still running during shutdown: %s", thread.name)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Unhandled error in automation scheduler tick")
            self._stop_event.wait(15)

    def tick(self) -> None:
        for job in self.store.get_due_jobs():
            self.run_job(job["id"], manual=False, scheduled_reference=job.get("next_run_at"))
        self.process_due_retry_queue()
        self.run_scheduled_maintenance()

    def run_scheduled_maintenance(self) -> Optional[Dict[str, Any]]:
        config = self.store.get_delivery_config()
        if not bool(config.get("auto_purge_enabled", True)):
            return None

        now_value = utc_now()
        today = now_value.date()
        last_purge_at = parse_iso_utc(config.get("last_auto_purge_at"))
        if last_purge_at and last_purge_at.date() >= today:
            return None

        history_retention_days = max(1, int(config.get("history_retention_days") or 30))
        retry_retention_days = max(1, int(config.get("retry_retention_days") or 30))

        history_result = self.store.purge_history(retain_days=history_retention_days)
        retry_result = self.store.purge_retry_queue_older(retain_days=retry_retention_days)
        self.store.update_delivery_config({"last_auto_purge_at": iso_utc(now_value)})
        return {
            "executed_at": iso_utc(now_value),
            "history": history_result,
            "retry_queue": retry_result,
        }

    def run_job(self, job_id: int, manual: bool = True, scheduled_reference: Optional[str] = None) -> bool:
        with self._lock:
            if self._stop_event.is_set():
                return False
            if int(job_id) in self._running_jobs:
                return False
            self._running_jobs.add(int(job_id))

        thread = threading.Thread(
            target=self._execute_job_thread,
            args=(int(job_id), manual, scheduled_reference),
            name=f"automation-job-{job_id}",
            daemon=True,
        )
        with self._lock:
            self._job_threads.add(thread)
        try:
            thread.start()
        except RuntimeError:
            with self._lock:
                self._running_jobs.discard(int(job_id))
                self._job_threads.discard(thread)
            raise
        return True

    def _execute_job_thread(self, job_id: int, manual: bool, scheduled_reference: Optional[str]) -> None:
        try:
            self.execute_job(job_id, manual=manual, scheduled_reference=scheduled_reference)
        finally:
            with self._lock:
                self._running_jobs.discard(int(job_id))
                self._job_threads.discard(threading.current_thread())

    def execute_job(self, job_id: int, manual: bool = False, scheduled_reference: Optional[str] = None) -> Dict[str, Any]:
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} no trobat")

        start = utc_now()
        run_id = self.store.create_run(job_id, started_at=iso_utc(start))
        report_path = None
        report_data = None
        deliveries: List[Dict[str, Any]] = []
        created_tasks: List[Dict[str, Any]] = []
        lot_execution: Optional[Dict[str, Any]] = None
        analytics_persisted = False

        try:
            report_data = self._run_audit(job)
            if (job.get("audit_type") or "").lower() == "post_crq_distribution":
                lot_execution = self._build_distribution_execution(job, report_data)
            generation_failure = self._detect_report_generation_failure(job, report_data)
            if generation_failure:
                if lot_execution:
                    self._mark_lot_execution_generation_failure(lot_execution, generation_failure)
                deliveries.extend(
                    self._send_failure_notification(
                        job,
                        run_id=run_id,
                        failure_reason=str(generation_failure.get("message") or "No s'ha pogut generar l'informe."),
                        report_data=report_data,
                    )
                )
                duration_ms = int((utc_now() - start).total_seconds() * 1000)
                summary = report_data.get("summary") if isinstance(report_data, dict) else {}
                if lot_execution:
                    summary = {
                        **summary,
                        "lot_execution": lot_execution.get("summary") or {},
                    }
                self.store.complete_run(
                    run_id,
                    status="error",
                    duration_ms=duration_ms,
                    summary=summary,
                    error_message=str(generation_failure.get("message") or "generation_failed"),
                    report_path=None,
                    deliveries=deliveries,
                    created_tasks=created_tasks,
                )
                if lot_execution:
                    self.store.replace_run_lot_statuses(
                        run_id,
                        job_id,
                        lot_execution.get("items") or [],
                        execution_id=f"job-{job_id}-run-{run_id}",
                        executed_at=iso_utc(start),
                    )
                self._persist_post_crq_analytics(run_id, job, report_data, executed_at=iso_utc(start), lot_execution=lot_execution)
                analytics_persisted = True
                if not manual:
                    self.store.touch_job_schedule(
                        job_id,
                        next_run_at=next_after_reference(job.get("schedule_type"), job.get("schedule_config"), scheduled_reference or job.get("next_run_at")),
                        last_run_at=iso_utc(utc_now()),
                    )
                return self.store.get_run(run_id)
            report_output = self._write_report(job, run_id, report_data, lot_execution=lot_execution)
            deliveries.extend(self._deliver_targets(job, report_data, report_output, run_id=run_id, lot_execution=lot_execution))
            report_path = self._finalize_report_output(job, report_output, report_data, deliveries, lot_execution=lot_execution)
            created_tasks.extend(self._apply_rules(job, run_id, report_data, report_path))

            status = "success"
            if any(item.get("status") == "error" for item in deliveries):
                status = "partial_error"

            duration_ms = int((utc_now() - start).total_seconds() * 1000)
            summary = report_data.get("summary") if isinstance(report_data, dict) else {"items": len(report_data or [])}
            if lot_execution:
                summary = {
                    **summary,
                    "lot_execution": lot_execution.get("summary") or {},
                }
            self.store.complete_run(
                run_id,
                status=status,
                duration_ms=duration_ms,
                summary=summary,
                report_path=report_path,
                deliveries=deliveries,
                created_tasks=created_tasks,
            )
            if lot_execution:
                self.store.replace_run_lot_statuses(
                    run_id,
                    job_id,
                    lot_execution.get("items") or [],
                    execution_id=f"job-{job_id}-run-{run_id}",
                    executed_at=iso_utc(start),
                )
            self._persist_post_crq_analytics(run_id, job, report_data, executed_at=iso_utc(start), lot_execution=lot_execution)
            analytics_persisted = True
            if manual:
                self.store.touch_job_schedule(job_id, next_run_at=job.get("next_run_at"), last_run_at=iso_utc(utc_now()))
            else:
                self.store.touch_job_schedule(
                    job_id,
                    next_run_at=next_after_reference(job.get("schedule_type"), job.get("schedule_config"), scheduled_reference or job.get("next_run_at")),
                    last_run_at=iso_utc(utc_now()),
                )
            return self.store.get_run(run_id)
        except Exception as exc:
            logger.warning(
                "Automation job execution failed",
                exc_info=exc,
                extra={"job_id": job_id, "run_id": run_id, "manual": manual},
            )
            duration_ms = int((utc_now() - start).total_seconds() * 1000)
            failure_message = self._build_failure_reason_from_exception(exc)
            if lot_execution:
                self._mark_lot_execution_generation_failure(lot_execution, {"message": failure_message})
            deliveries.extend(
                self._send_failure_notification(
                    job,
                    run_id=run_id,
                    failure_reason=failure_message,
                    report_data=report_data,
                )
            )
            if lot_execution:
                self.store.replace_run_lot_statuses(
                    run_id,
                    job_id,
                    lot_execution.get("items") or [],
                    execution_id=f"job-{job_id}-run-{run_id}",
                    executed_at=iso_utc(start),
                )
            if report_data is not None and not analytics_persisted:
                self._persist_post_crq_analytics_safely(
                    run_id,
                    job,
                    report_data,
                    executed_at=iso_utc(start),
                    lot_execution=lot_execution,
                )
            self.store.complete_run(
                run_id,
                status="error",
                duration_ms=duration_ms,
                summary={},
                error_message=failure_message,
                report_path=report_path,
                deliveries=deliveries,
                created_tasks=created_tasks,
            )
            if not manual:
                self.store.touch_job_schedule(
                    job_id,
                    next_run_at=next_after_reference(job.get("schedule_type"), job.get("schedule_config"), scheduled_reference or job.get("next_run_at")),
                    last_run_at=iso_utc(utc_now()),
                )
            raise

    def _persist_post_crq_analytics(
        self,
        run_id: int,
        job: Dict[str, Any],
        report_data: Any,
        *,
        executed_at: str,
        lot_execution: Optional[Dict[str, Any]] = None,
    ) -> None:
        audit_type = (job.get("audit_type") or "").lower()
        if audit_type not in {"post_crq", "post_crq_distribution"}:
            return
        if not isinstance(report_data, dict):
            return
        payload = build_post_crq_analytics_payload(
            report_data,
            run_id=int(run_id),
            job_id=int(job.get("id")),
            execution_id=f"job-{job.get('id')}-run-{run_id}",
            executed_at=executed_at,
            audit_type=audit_type,
            profile=str(job.get("profile") or ""),
            lot_execution=lot_execution,
            mapping_db_path=resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db"),
        )
        self.store.replace_post_crq_analytics(int(run_id), int(job.get("id")), payload)

    def _persist_post_crq_analytics_safely(
        self,
        run_id: int,
        job: Dict[str, Any],
        report_data: Any,
        *,
        executed_at: str,
        lot_execution: Optional[Dict[str, Any]] = None,
    ) -> bool:
        try:
            self._persist_post_crq_analytics(
                run_id,
                job,
                report_data,
                executed_at=executed_at,
                lot_execution=lot_execution,
            )
            return True
        except Exception as exc:
            logger.warning(
                "Post-CRQ analytics persistence failed for run %s job %s",
                run_id,
                job.get("id"),
                exc_info=exc,
            )
            return False

    def _build_distribution_execution(self, job: Dict[str, Any], report_data: Dict[str, Any]) -> Dict[str, Any]:
        routes = self.store.get_delivery_routes()
        master_lots = self.store.list_master_lots(enabled_only=True)
        matrix = build_post_crq_lot_execution_matrix(
            report_data,
            job_config=job.get("job_config") or {},
            delivery_routes=routes,
            master_lots=master_lots,
            mapping_db_path=resolve_sqlite_path("INTERNAL_DB_PATH", "internal.db"),
        )
        matrix["routes"] = routes
        matrix["master_lots"] = master_lots
        matrix["job_config"] = normalize_distribution_job_config(job.get("job_config") or {})
        self._apply_lot_delivery_defaults(matrix)
        return matrix

    def _resolve_profile_config(self, profile_name: str, timeout_seconds: int) -> Dict[str, Any]:
        profiles = self.config_loader.load_connections()
        resolved = self.config_loader.resolve_profile_name(profile_name, profiles)
        if not resolved or resolved not in profiles:
            raise ValueError(f"Perfil no trobat: {profile_name}")
        params = dict(profiles[resolved])
        params["PROFILE_NAME"] = resolved
        params["ORACLE_CLIENT_LIB_DIR"] = self.config_loader.get_env_var("ORACLE_CLIENT_LIB_DIR")
        params["CALL_TIMEOUT_MS"] = int(timeout_seconds or 300) * 1000
        return params

    def _artifact_dir_from_report_path(self, report_path: str) -> str:
        path = Path(str(report_path))
        return str(path.with_name(f"{path.stem}_artifacts"))

    def _build_post_crq_effective_config(self, job: Dict[str, Any], report_data: Any) -> Dict[str, Any]:
        payload = report_data if isinstance(report_data, dict) else {}
        context = payload.get("context") or {}
        report_model = payload.get("report_model") or {}
        execution_parameters = report_model.get("execution_parameters") or {}
        enabled_checks = report_model.get("enabled_checks") or []
        executed_checks = payload.get("executed_checks") or []

        final_criticality_by_check: Dict[str, str] = {}
        for item in enabled_checks:
            check_id = str(item.get("check_id") or "").strip()
            criticality = str(item.get("criticality") or item.get("criticitat") or "").strip()
            if check_id and criticality:
                final_criticality_by_check[check_id] = criticality
        for item in executed_checks:
            check_id = str(item.get("check_id") or "").strip()
            criticality = str(item.get("criticality") or item.get("criticitat") or item.get("severitat") or "").strip()
            if check_id and criticality and check_id not in final_criticality_by_check:
                final_criticality_by_check[check_id] = criticality

        selected_checks = [str(item).strip() for item in (job.get("checks") or []) if str(item).strip()]
        time_filter = dict(job.get("time_filter") or context.get("time_filter") or {})
        criticality_overrides = dict(job.get("criticality_overrides") or {})
        scheduler_options = dict(job.get("scheduler_options") or {})

        return {
            "selected_checks": selected_checks,
            "selected_checks_count": len(selected_checks),
            "time_filter": time_filter,
            "criticality_overrides": criticality_overrides,
            "scheduler_options": scheduler_options,
            "source_file": context.get("source_file"),
            "generated_at": execution_parameters.get("generated_at") or context.get("generated_at") or iso_utc(utc_now()),
            "final_criticality_by_check": final_criticality_by_check,
        }

    def _write_post_crq_snapshot_files(
        self,
        artifacts_dir: str,
        *,
        job: Dict[str, Any],
        report_data: Any,
        deliveries: Optional[List[Dict[str, Any]]] = None,
        lot_execution: Optional[Dict[str, Any]] = None,
        profile: Optional[str] = None,
    ) -> None:
        Path(artifacts_dir).mkdir(parents=True, exist_ok=True)
        if not isinstance(report_data, dict):
            return

        effective_config = self._build_post_crq_effective_config(job, report_data)
        snapshot_report_data = {
            **report_data,
            "snapshot_metadata": effective_config,
        }
        report_data_path = os.path.join(artifacts_dir, "report_data.json")
        with open(report_data_path, "w", encoding="utf-8") as handle:
            json.dump(snapshot_report_data, handle, ensure_ascii=False, indent=2)

        manifest = {
            "job_id": job["id"],
            "job_name": job.get("name"),
            "profile": profile or job.get("profile"),
            "generated_at": effective_config.get("generated_at"),
            "summary": report_data.get("summary") or {},
            "deliveries": deliveries or [],
            "lot_execution": (lot_execution or {}).get("summary") or {},
            "lot_items": (lot_execution or {}).get("items") or [],
            **effective_config,
        }
        manifest_path = os.path.join(artifacts_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)

    def _run_audit(self, job: Dict[str, Any]) -> Any:
        audit_type = (job.get("audit_type") or "").lower()
        timeout_seconds = int(job.get("timeout_seconds") or 300)
        params = self._resolve_profile_config(job["profile"], timeout_seconds)

        if audit_type in {"post_crq", "post_crq_distribution"}:
            dbm = OracleDBManager(params)
            try:
                return run_post_crq_audit(
                    db_manager=dbm,
                    selected_checks=job.get("checks") or [],
                    schemas=job.get("schemas") or [],
                    time_filter=job.get("time_filter") or {},
                    profile=params["PROFILE_NAME"],
                    criticality_overrides=job.get("criticality_overrides") or {},
                    scheduler_options=job.get("scheduler_options") or {},
                )
            finally:
                dbm.close()

        if audit_type in {"deep_scan", "obsolets"}:
            dbm = OracleDBManager(params)
            try:
                engine = AuditEngine(dbm)
                result = asyncio.run(engine.run_plan_audit(job.get("schemas") or []))
                return result.get("audits") or []
            finally:
                dbm.close()

        raise ValueError(f"Tipus d'auditoria no suportat: {job.get('audit_type')}")

    def _write_report(
        self,
        job: Dict[str, Any],
        run_id: int,
        report_data: Any,
        *,
        lot_execution: Optional[Dict[str, Any]] = None,
    ) -> Any:
        profile = job.get("profile") or "N_A"
        fmt = (job.get("report_format") or "markdown").lower()
        timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
        base_name = f"job_{job['id']}_run_{run_id}_{timestamp}"
        path = os.path.join(self.reports_dir, f"{base_name}.{'pdf' if fmt == 'pdf' else 'md'}")
        audit_type = (job.get("audit_type") or "").lower()

        if audit_type == "post_crq_distribution":
            current_execution = lot_execution or self._build_distribution_execution(job, report_data)
            job_config = current_execution.get("job_config") or normalize_distribution_job_config(job.get("job_config") or {})
            workdir = os.path.join(self.reports_dir, f"{base_name}_artifacts")
            Path(workdir).mkdir(parents=True, exist_ok=True)
            provider_paths: Dict[str, str] = {}
            general_attachment_path = None
            if job_config.get("report_options", {}).get("include_summary", True):
                artifact = build_post_crq_general_artifact(profile, report_data)
                general_attachment_path = os.path.join(workdir, artifact["filename"])
                with open(general_attachment_path, "wb") as handle:
                    handle.write(artifact["content"])
            if job_config.get("report_options", {}).get("include_lot_reports", True):
                for item in current_execution.get("items") or []:
                    if item.get("detection_status") != LOT_STATUS_WITH_FINDINGS:
                        continue
                    try:
                        artifact = build_post_crq_provider_artifact(profile, report_data, item["lot"])
                        artifact_path = os.path.join(workdir, artifact["filename"])
                        with open(artifact_path, "wb") as handle:
                            handle.write(artifact["content"])
                        provider_paths[str(item["lot"])] = artifact_path
                        item["report_generated"] = True
                    except Exception as exc:
                        logger.warning(
                            "Provider report generation failed for lot %s in job %s run %s",
                            item.get("lot"),
                            job.get("id"),
                            run_id,
                            exc_info=exc,
                        )
                        item["report_generated"] = False
                        item["motivo_sin_envio"] = f"Error generant report individual: {exc}"
                        item["observaciones"] = f"{item.get('observaciones') or ''} Error generant PDF individual.".strip()
            for item in current_execution.get("items") or []:
                if item.get("detection_status") == LOT_STATUS_WITH_FINDINGS and not item.get("report_generated") and not job_config.get("report_options", {}).get("include_lot_reports", True):
                    item["motivo_sin_envio"] = "La generacio de reports individuals esta deshabilitada per aquest job."
            lot_status_path = os.path.join(workdir, "lot_statuses.json")
            with open(lot_status_path, "w", encoding="utf-8") as handle:
                json.dump(current_execution.get("items") or [], handle, ensure_ascii=False, indent=2)
            bundle_path = os.path.join(self.reports_dir, f"{base_name}.zip")
            return {
                "report_path": bundle_path,
                "workdir": workdir,
                "profile": profile,
                "report_data": report_data,
                "general_attachment_path": general_attachment_path,
                "provider_paths": provider_paths,
                "lot_execution": current_execution,
            }

        if audit_type == "post_crq":
            if fmt == "pdf":
                content = build_post_crq_pdf_report(profile, report_data)
                with open(path, "wb") as handle:
                    handle.write(content)
            else:
                text = build_post_crq_markdown_report(profile, report_data)
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(text)
            return path

        if fmt == "pdf":
            content = build_standard_pdf(profile, report_data)
            with open(path, "wb") as handle:
                handle.write(content)
        else:
            text = build_standard_markdown(profile, report_data)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        return path

    def _finalize_report_output(
        self,
        job: Dict[str, Any],
        report_output: Any,
        report_data: Any,
        deliveries: List[Dict[str, Any]],
        *,
        lot_execution: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        audit_type = (job.get("audit_type") or "").lower()
        if audit_type == "post_crq":
            artifacts_dir = self._artifact_dir_from_report_path(str(report_output))
            self._write_post_crq_snapshot_files(
                artifacts_dir,
                job=job,
                report_data=report_data,
                deliveries=deliveries,
                lot_execution=lot_execution,
                profile=job.get("profile"),
            )
            return report_output

        if audit_type != "post_crq_distribution":
            return report_output

        report_path = report_output["report_path"]
        current_execution = lot_execution or report_output.get("lot_execution") or {}
        self._write_post_crq_snapshot_files(
            report_output["workdir"],
            job=job,
            report_data=report_data,
            deliveries=deliveries,
            lot_execution=current_execution,
            profile=report_output["profile"],
        )
        with zipfile.ZipFile(report_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(Path(report_output["workdir"]).glob("*")):
                if file_path.is_file():
                    archive.write(file_path, arcname=file_path.name)
        return report_path

    def _report_summary(self, job: Dict[str, Any], report_data: Any) -> Tuple[str, Dict[str, int]]:
        audit_type = (job.get("audit_type") or "").lower()
        if audit_type in {"post_crq", "post_crq_distribution"}:
            summary = report_data.get("summary") or {}
            return (
                f"Checks executats: {summary.get('executed_checks', 0)} | "
                f"Troballes: {summary.get('total_findings', 0)} | "
                f"Errors: {summary.get('checks_with_errors', 0)}",
                {
                    normalize_severity(severity): int(count)
                    for severity, count in (summary.get("findings_by_severity") or {}).items()
                },
            )

        counts: Dict[str, int] = {}
        for item in report_data or []:
            score = float(item.get("obsolescence_score") or 0)
            if score >= 90:
                severity = "STOPPER"
            elif score >= 80:
                severity = "CRITIC"
            elif score >= 65:
                severity = "ALT"
            elif score >= 40:
                severity = "MITJA"
            else:
                severity = "BAIX"
            counts[severity] = counts.get(severity, 0) + 1
        return (
            f"Esquemes auditats: {len(report_data or [])} | Severitats detectades: {sum(counts.values())}",
            counts,
        )

    def _build_failure_reason_from_exception(self, exc: Exception) -> str:
        raw = str(exc or "").strip() or "S'ha produït un error desconegut."
        lowered = raw.lower()
        connectivity_tokens = (
            "ora-",
            "tns",
            "listener",
            "connect",
            "connection",
            "timeout",
            "database",
            "bdd",
            "query_execution_failed",
        )
        if any(token in lowered for token in connectivity_tokens):
            return f"No s'ha pogut connectar correctament a la BBDD: {raw}"
        return f"No s'ha pogut generar l'informe: {raw}"

    def _detect_report_generation_failure(self, job: Dict[str, Any], report_data: Any) -> Optional[Dict[str, Any]]:
        audit_type = str(job.get("audit_type") or "").strip().lower()
        if audit_type not in {"post_crq", "post_crq_distribution"} or not isinstance(report_data, dict):
            return None

        summary = report_data.get("summary") or {}
        checks_with_errors = int(summary.get("checks_with_errors") or 0)
        errors = report_data.get("errors") or []
        executed_errors = [
            item for item in (report_data.get("executed_checks") or [])
            if str(item.get("status") or "").strip().lower() == "error"
        ]
        blocking_errors = (
            ((report_data.get("report_model") or {}).get("final_observations") or {}).get("blocking_errors")
            or []
        )
        if checks_with_errors <= 0 and not errors and not executed_errors and not blocking_errors:
            return None

        detail = None
        if errors:
            first = errors[0]
            if isinstance(first, dict):
                detail = first.get("message") or first.get("error") or first.get("detail")
            else:
                detail = str(first)
        if not detail and executed_errors:
            first = executed_errors[0]
            detail = first.get("error") or first.get("message") or first.get("check_id")
        if not detail and blocking_errors:
            first = blocking_errors[0]
            if isinstance(first, dict):
                detail = first.get("error") or first.get("message") or first.get("check_id")
            else:
                detail = str(first)
        detail = str(detail or "").strip()
        lowered = detail.lower()
        connectivity_tokens = (
            "ora-",
            "tns",
            "listener",
            "connect",
            "connection",
            "timeout",
            "database",
            "bdd",
            "query_execution_failed",
            "simulated_post_crq_failure",
        )
        if detail and any(token in lowered for token in connectivity_tokens):
            message = f"No s'ha pogut connectar correctament a la BBDD: {detail}"
        elif detail:
            message = f"No s'ha pogut generar l'informe perquè l'auditoria ha retornat errors: {detail}"
        else:
            total_errors = checks_with_errors or len(executed_errors) or len(blocking_errors)
            message = f"No s'ha pogut generar l'informe perquè l'auditoria ha retornat {total_errors} checks amb error."
        return {"checks_with_errors": checks_with_errors, "message": message}

    def _mark_lot_execution_generation_failure(self, lot_execution: Optional[Dict[str, Any]], failure: Optional[Dict[str, Any]]) -> None:
        if not lot_execution:
            return
        reason = str((failure or {}).get("message") or "No s'ha pogut generar l'informe.").strip()
        for item in lot_execution.get("items") or []:
            item["report_generated"] = False
            item["email_sent"] = False
            item["delivery_result"] = DELIVERY_RESULT_MANUAL_REVIEW
            item["motivo_sin_envio"] = reason
            current = str(item.get("observaciones") or "").strip()
            suffix = "Distribució aturada perquè la generació de l'informe ha fallat."
            item["observaciones"] = f"{current} {suffix}".strip()

    def _status_label(self, status: Optional[str]) -> str:
        catalog = {
            LOT_STATUS_WITH_FINDINGS: "Amb troballes",
            LOT_STATUS_WITHOUT_FINDINGS: "Sense troballes",
            LOT_STATUS_NOT_APPLICABLE: "No aplica",
            LOT_STATUS_QUERY_ERROR: "Error de consulta",
            LOT_STATUS_UNMAPPED: "Sense mapatge",
            "SUMMARY": "Resum general",
            "RETRY": "Reintent",
        }
        normalized = str(status or "").strip()
        return catalog.get(normalized, normalized or "-")

    def _collect_lot_technical_context(self, report_data: Dict[str, Any], lot: Optional[str]) -> Dict[str, List[str]]:
        target_lot = str(lot or "").strip().upper()
        if not target_lot:
            return {"queries": [], "schemas": []}

        queries: List[str] = []
        schemas: List[str] = []
        seen_queries = set()
        seen_schemas = set()

        def add_query(check_id: Any, title: Any = None) -> None:
            raw_id = str(check_id or "").strip().upper()
            if not raw_id:
                return
            raw_title = str(title or "").strip()
            label = f"{raw_id} - {raw_title}" if raw_title and raw_title.upper() != raw_id else raw_id
            if label in seen_queries:
                return
            seen_queries.add(label)
            queries.append(label)

        def add_schema(schema_name: Any) -> None:
            value = str(schema_name or "").strip().upper()
            if not value or value in seen_schemas:
                return
            seen_schemas.add(value)
            schemas.append(value)

        report_model = (report_data or {}).get("report_model") or {}
        for group in report_model.get("lot_incident_groups") or []:
            if str(group.get("lot") or "").strip().upper() != target_lot:
                continue
            add_query(group.get("check") or group.get("check_id"), group.get("title"))
            for schema_entry in group.get("schemas") or []:
                add_schema(
                    schema_entry.get("nom")
                    or schema_entry.get("schema")
                    or schema_entry.get("ESQUEMA")
                )

        if not queries and not schemas:
            for item in report_model.get("lot_summary") or []:
                if str(item.get("lot") or "").strip().upper() != target_lot:
                    continue
                for check_id in item.get("checks") or []:
                    add_query(check_id)
                for schema_name in item.get("schemas") or []:
                    add_schema(schema_name)

        if not queries and not schemas:
            for finding in (report_data or {}).get("finding_envelopes") or []:
                assignment = finding.get("lot_assignment") or {}
                if str(assignment.get("lot") or "").strip().upper() != target_lot:
                    continue
                add_query(finding.get("check_id"), finding.get("title"))
                add_schema(finding.get("schema"))

        return {"queries": queries, "schemas": schemas}

    def _build_technical_legend(self, report_data: Dict[str, Any], lot: Optional[str]) -> Dict[str, str]:
        context = self._collect_lot_technical_context(report_data, lot)
        queries = list(context.get("queries") or [])
        schemas = list(context.get("schemas") or [])

        queries_text = "\n".join(f"- {item}" for item in queries) if queries else "- No s'han identificat consultes afectades."
        schemas_text = "\n".join(f"- {item}" for item in schemas) if schemas else "- No s'han identificat esquemes afectats."
        legend = (
            "Consultes afectades:\n"
            f"{queries_text}\n\n"
            "Esquemes afectats:\n"
            f"{schemas_text}"
        )
        return {
            "affected_queries": queries_text,
            "affected_schemas": schemas_text,
            "technical_legend": legend,
        }

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        class _SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"

        return str(template or "").format_map(_SafeDict(context))

    def _safe_provider_code(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", str(value or "").strip() or "SENSE_LOT")

    def _delivery_templates(self) -> Dict[str, Dict[str, Any]]:
        templates: Dict[str, Dict[str, Any]] = {}
        for item in self.store.list_delivery_templates():
            if item.get("enabled", True):
                templates[str(item.get("template_key"))] = item
        return templates

    def _resolve_tic_recipients(self, routes: Dict[str, Any]) -> List[str]:
        recipients: List[str] = []
        seen = set()

        def add_many(values: Any) -> None:
            for value in values or []:
                if isinstance(value, dict):
                    if not value.get("enabled", True):
                        continue
                    email = str(value.get("email") or "").strip()
                else:
                    email = str(value or "").strip()
                
                if not email:
                    continue
                normalized = email.lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                recipients.append(email)

        add_many(routes.get("tic_summary_recipients") or [])
        for route in routes.get("providers") or []:
            provider_code = str((route or {}).get("provider_code") or "").strip().upper()
            if provider_code == "TIC":
                add_many((route or {}).get("emails") or [])
        return recipients

    def _resolve_distribution_delivery(self, job_config: Dict[str, Any]) -> Dict[str, Any]:
        delivery = job_config.get("delivery") or {}
        targets = {
            str(item or "").strip().lower()
            for item in (delivery.get("targets") or [])
            if str(item or "").strip().lower() in {"lots", "tic"}
        }
        test_mode = bool(delivery.get("test_mode", False))
        override_recipients: List[str] = []
        seen = set()
        for item in delivery.get("override_recipients") or []:
            email = str(item or "").strip()
            normalized = email.lower()
            if not email or normalized in seen:
                continue
            seen.add(normalized)
            override_recipients.append(email)
        # In test mode, "Proves" is meant to simulate the full distribution
        # even when no explicit real audiences were selected in the job form.
        if test_mode and not targets:
            targets = {"lots", "tic"}
        return {
            "send_to_lots": "lots" in targets,
            "send_to_tic": "tic" in targets,
            "test_mode": test_mode,
            "override_recipients": override_recipients if test_mode else [],
        }

    def _select_template(self, audience: str, *, template_key: Optional[str] = None) -> Dict[str, Any]:
        templates = self._delivery_templates()
        if template_key and template_key in templates:
            return templates[template_key]
        by_audience = {
            "failure": "job_generation_failure",
            "tic": "tic_summary",
            "provider": "provider_with_findings",
            "retry": "manual_resend",
        }
        selected_key = by_audience.get(audience, "provider_with_findings")
        if template_key:
            selected_key = template_key
        if selected_key == "job_generation_failure":
            return templates.get(selected_key) or {
                "template_key": selected_key,
                "audience": audience,
                "subject_template": "[Oracle Audit] Error generant l'informe - {job_name} - {profile}",
                "body_template": (
                    "Bon dia,\n\n"
                    "No s'ha pogut generar l'informe \"{report_name}\".\n\n"
                    "Resum de la incidència\n"
                    "- Job: {job_name}\n"
                    "- Perfil: {profile}\n"
                    "- Identificador d'execució: {execution_id}\n"
                    "- Estat: {status}\n\n"
                    "Motiu\n"
                    "{failure_reason}\n\n"
                    "Observacions\n"
                    "{observations}\n\n"
                    "No s'ha enviat cap informe adjunt perquè la generació no s'ha completat correctament.\n\n"
                    "Salutacions,\n"
                    "Sistema d'auditoria BBDD"
                ),
                "enabled": True,
            }
        return templates.get(selected_key) or {
            "template_key": selected_key,
            "audience": audience,
            "subject_template": "[Oracle Audit] {job_name} - {lot}" if selected_key != "provider_without_findings" else "[Oracle Audit] {job_name} - {lot} - sense troballes",
            "body_template": (
                "Bon dia,\n\n"
                "S'ha executat correctament l'auditoria automàtica del lot {lot} i no s'hi han detectat anomalies.\n\n"
                "Resum de l'execució\n"
                "- Perfil: {profile}\n"
                "- Lot: {lot}\n"
                "- Estat: {status}\n"
                "- Nombre de troballes: {findings}\n"
                "- Identificador d'execució: {execution_id}\n\n"
                "Observacions\n"
                "{observations}\n\n"
                "Llegenda tècnica\n"
                "{technical_legend}\n\n"
                "No s'adjunta cap informe individual perquè el lot s'ha avaluat sense troballes.\n\n"
                "Salutacions,\n"
                "Sistema d'auditoria BBDD"
            ) if selected_key == "provider_without_findings" else (
                "Bon dia,\n\n"
                "S'ha executat correctament l'auditoria automàtica del lot {lot}.\n\n"
                "Resum de l'execució\n"
                "- Perfil: {profile}\n"
                "- Lot: {lot}\n"
                "- Estat: {status}\n"
                "- Nombre de troballes: {findings}\n"
                "- Identificador d'execució: {execution_id}\n\n"
                "Observacions\n"
                "{observations}\n\n"
                "Llegenda tècnica\n"
                "{technical_legend}\n\n"
                "Trobaràs el detall complet a l'informe adjunt.\n\n"
                "Salutacions,\n"
                "Sistema d'auditoria BBDD"
            ),
            "enabled": True,
        }

    def _send_failure_notification(
        self,
        job: Dict[str, Any],
        *,
        run_id: Optional[int],
        failure_reason: str,
        report_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        config = self._delivery_config()
        recipients = config.get("failure_notification_recipients") or []
        template = self._select_template("failure", template_key="job_generation_failure")
        context = {
            "job_name": job.get("name"),
            "report_name": job.get("name"),
            "profile": job.get("profile"),
            "lot": "N/A",
            "status": "Error de generació",
            "findings": ((report_data or {}).get("summary") or {}).get("total_findings", 0) if isinstance(report_data, dict) else 0,
            "execution_id": f"job-{job.get('id')}-run-{run_id or 'pending'}",
            "observations": "No s'ha enviat cap informe perquè la generació ha fallat.",
            "summary": "",
            "failure_reason": failure_reason,
            "affected_queries": "- No disponible.",
            "affected_schemas": "- No disponible.",
            "technical_legend": "Consultes afectades:\n- No disponible.\n\nEsquemes afectats:\n- No disponible.",
        }
        if not recipients:
            return [
                {
                    "type": "email",
                    "audience": "failure",
                    "status": "error",
                    "error": "No hi ha destinataris configurats per a les fallades de generació.",
                    "recipients": [],
                    "attachment_name": None,
                }
            ]
        try:
            self._send_email_with_tracking(
                run_id=run_id,
                job_id=job.get("id"),
                lot=None,
                audience="failure",
                recipients=recipients,
                subject=self._render_template(template.get("subject_template") or "", context),
                body=self._render_template(template.get("body_template") or "", context),
                attachment_path=None,
                config=config,
                template=template,
                queue_on_failure=False,
            )
            return [
                {
                    "type": "email",
                    "audience": "failure",
                    "status": "ok",
                    "recipients": recipients,
                    "attachment_name": None,
                }
            ]
        except (DeliverySendError, OSError, RuntimeError, TimeoutError, ValueError, smtplib.SMTPException) as exc:
            logger.warning(
                "Failure notification delivery failed for run %s job %s",
                run_id,
                job.get("id"),
                exc_info=exc,
            )
            return [
                {
                    "type": "email",
                    "audience": "failure",
                    "status": "error",
                    "error": str(exc),
                    "recipients": recipients,
                    "attachment_name": None,
                }
            ]

    def _record_delivery_attempt(
        self,
        *,
        run_id: Optional[int],
        job_id: Optional[int],
        lot: Optional[str],
        audience: str,
        attempt_no: int,
        status: str,
        recipients: List[str],
        attachment_name: Optional[str],
        template: Dict[str, Any],
        error_message: Optional[str] = None,
    ) -> None:
        self.store.create_delivery_attempt(
            {
                "run_id": run_id,
                "job_id": job_id,
                "lot": lot,
                "audience": audience,
                "attempt_no": attempt_no,
                "status": status,
                "error_message": error_message,
                "recipients": recipients,
                "attachment_name": attachment_name,
                "template_key": template.get("template_key"),
                "template_snapshot": template,
            }
        )

    def _retry_dedupe_key(self, *, run_id: Optional[int], lot: Optional[str], audience: str) -> str:
        lot_token = str(lot or "TIC").strip().upper() or "TIC"
        return f"run:{run_id or 'none'}|audience:{audience}|lot:{lot_token}"

    def _classify_delivery_error(self, error_text: str) -> Tuple[str, bool]:
        lowered = str(error_text or "").strip().lower()
        if not lowered:
            return DELIVERY_RESULT_DELIVERY_ERROR, False
        if "destinatar" in lowered or "no hi ha destinataris" in lowered or "no route" in lowered:
            return DELIVERY_RESULT_NO_ROUTE, False
        if "adjunt" in lowered or "attachment" in lowered:
            return DELIVERY_RESULT_ATTACHMENT_ERROR, False
        if "smtp_host" in lowered or "remitent" in lowered or "autentic" in lowered or "login" in lowered:
            return DELIVERY_RESULT_DELIVERY_ERROR, False
        retryable = self._is_transient_delivery_error(lowered)
        return DELIVERY_RESULT_DELIVERY_ERROR, retryable

    def _next_retry_at(self, attempts_made: int, *, from_time: Optional[dt.datetime] = None) -> Optional[str]:
        if attempts_made >= len(RETRY_BACKOFF_MINUTES) + 1:
            return None
        base_time = from_time or utc_now()
        delay_minutes = RETRY_BACKOFF_MINUTES[max(0, min(attempts_made - 1, len(RETRY_BACKOFF_MINUTES) - 1))]
        return iso_utc(base_time + dt.timedelta(minutes=delay_minutes))

    def _apply_lot_delivery_defaults(self, lot_execution: Optional[Dict[str, Any]]) -> None:
        if not lot_execution:
            return
        for item in lot_execution.get("items") or []:
            detection_status = str(item.get("detection_status") or "").strip()
            item["delivery_audience"] = "provider" if item.get("lot") and detection_status != LOT_STATUS_UNMAPPED else "none"
            if detection_status == LOT_STATUS_WITH_FINDINGS:
                item["delivery_result"] = DELIVERY_RESULT_DELIVERY_ERROR
            elif detection_status == LOT_STATUS_WITHOUT_FINDINGS:
                item["delivery_result"] = DELIVERY_RESULT_SKIPPED_NO_FINDINGS
            elif detection_status == LOT_STATUS_NOT_APPLICABLE:
                item["delivery_result"] = DELIVERY_RESULT_SKIPPED_NOT_APPLICABLE
            else:
                item["delivery_result"] = DELIVERY_RESULT_MANUAL_REVIEW

    def _queue_retry(
        self,
        *,
        run_id: Optional[int],
        job_id: Optional[int],
        lot: Optional[str],
        audience: str,
        error_message: str,
        retry_mode: str = "manual",
        requested_by: str = "system",
        error_class: Optional[str] = None,
        next_attempt_at: Optional[str] = None,
        max_attempts: int = 4,
        force_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        dedupe_key = self._retry_dedupe_key(run_id=run_id, lot=lot, audience=audience)
        existing = [
            item
            for item in self.store.list_retry_queue(run_id=run_id, limit=200)
            if str(item.get("dedupe_key") or "") == dedupe_key and str(item.get("status") or "") in {"pending", "in_progress", "failed"}
        ]
        if existing:
            current = existing[0]
            merged = {
                "status": force_status or ("pending" if retry_mode == "auto" else current.get("status") or "failed"),
                "requested_by": requested_by,
                "error_message": error_message,
                "retry_mode": retry_mode,
                "error_class": error_class,
                "next_attempt_at": next_attempt_at if retry_mode == "auto" else None,
                "max_attempts": max_attempts,
                "dedupe_key": dedupe_key,
                "lock_token": None,
                "locked_at": None,
            }
            return self.store.update_retry_queue_item(int(current["id"]), merged) or current
        return self.store.create_retry_queue_item(
            {
                "run_id": run_id,
                "job_id": job_id,
                "lot": lot,
                "audience": audience,
                "status": force_status or ("pending" if retry_mode == "auto" else "failed"),
                "requested_by": requested_by,
                "error_message": error_message,
                "next_attempt_at": next_attempt_at if retry_mode == "auto" else None,
                "max_attempts": max_attempts,
                "retry_mode": retry_mode,
                "error_class": error_class,
                "dedupe_key": dedupe_key,
            }
        )

    def _is_transient_delivery_error(self, error_text: str) -> bool:
        lowered = str(error_text or "").strip().lower()
        markers = ("timeout", "temporarily", "connection", "disconnected", "reset", "refused", "unavailable")
        return any(marker in lowered for marker in markers)

    def _send_email_with_tracking(
        self,
        *,
        run_id: Optional[int],
        job_id: Optional[int],
        lot: Optional[str],
        audience: str,
        recipients: List[str],
        subject: str,
        body: str,
        attachment_path: Optional[str],
        config: Dict[str, Any],
        template: Dict[str, Any],
        max_attempts: int = 2,
        queue_on_failure: bool = True,
    ) -> None:
        attachment_name = os.path.basename(attachment_path) if attachment_path else None
        attempt = 0
        last_error: Optional[Exception] = None
        while attempt < max(1, max_attempts):
            attempt += 1
            try:
                self._send_email(
                    recipients=recipients,
                    subject=subject,
                    body=body,
                    attachment_path=attachment_path,
                    config=config,
                )
                self._record_delivery_attempt(
                    run_id=run_id,
                    job_id=job_id,
                    lot=lot,
                    audience=audience,
                    attempt_no=attempt,
                    status="ok",
                    recipients=recipients,
                    attachment_name=attachment_name,
                    template=template,
                )
                return
            except (OSError, RuntimeError, TimeoutError, ValueError, smtplib.SMTPException) as exc:
                error_class, retryable = self._classify_delivery_error(str(exc))
                last_error = exc
                self._record_delivery_attempt(
                    run_id=run_id,
                    job_id=job_id,
                    lot=lot,
                    audience=audience,
                    attempt_no=attempt,
                    status="error",
                    recipients=recipients,
                    attachment_name=attachment_name,
                    template=template,
                    error_message=str(exc),
                )
                if attempt >= max_attempts or not retryable:
                    break
        if queue_on_failure:
            error_class, retryable = self._classify_delivery_error(str(last_error or "delivery_failed"))
            if retryable:
                self._queue_retry(
                    run_id=run_id,
                    job_id=job_id,
                    lot=lot,
                    audience=audience,
                    error_message=str(last_error or "delivery_failed"),
                    retry_mode="auto",
                    requested_by="system",
                    error_class=error_class,
                    next_attempt_at=self._next_retry_at(1),
                    max_attempts=4,
                )
                raise DeliverySendError(
                    str(last_error or "delivery_failed"),
                    error_class=error_class,
                    retryable=True,
                    queued_retry=True,
                )
        if last_error:
            error_class, retryable = self._classify_delivery_error(str(last_error))
            raise DeliverySendError(
                str(last_error),
                error_class=error_class,
                retryable=retryable,
                queued_retry=False,
            ) from last_error

    def _delivery_config(self) -> Dict[str, Any]:
        config = self.store.get_delivery_config()
        config["smtp_host"] = config.get("smtp_host") or self.config_loader.get_env_var("SMTP_HOST", "")
        config["smtp_port"] = int(config.get("smtp_port") or self.config_loader.get_env_var("SMTP_PORT", 587) or 587)
        config["smtp_username"] = config.get("smtp_username") or self.config_loader.get_env_var("SMTP_USERNAME", "")
        config["smtp_password"] = config.get("smtp_password") or self.config_loader.get_env_var("SMTP_PASSWORD", "")
        config["from_email"] = config.get("from_email") or self.config_loader.get_env_var("SMTP_FROM_EMAIL", "")
        if not config.get("default_recipients"):
            raw = self.config_loader.get_env_var("SMTP_DEFAULT_RECIPIENTS", "")
            config["default_recipients"] = [item.strip() for item in raw.split(",") if item.strip()]
        return config

    def send_test_email(self, recipient: str) -> Dict[str, Any]:
        config = self._delivery_config()
        self._send_email(
            recipients=[recipient],
            subject="Prova de configuracio SMTP - Oracle Audit",
            body="Aquest es un correu de prova enviat des del modul d'automatitzacions.",
            attachment_path=None,
            config=config,
        )
        return {"status": "success", "message": f"Correu de prova enviat a {recipient}"}

    def _send_email(
        self,
        *,
        recipients: List[str],
        subject: str,
        body: str,
        attachment_path: Optional[str],
        config: Dict[str, Any],
    ) -> None:
        if not recipients:
            raise ValueError("No hi ha destinataris per al correu")
        if not config.get("smtp_host"):
            raise ValueError("SMTP_HOST no configurat")
        if not config.get("from_email"):
            raise ValueError("Correu remitent no configurat")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = config["from_email"]
        message["To"] = ", ".join(recipients)
        message.set_content(body)

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as handle:
                data = handle.read()
            maintype, subtype = ("application", "pdf") if attachment_path.lower().endswith(".pdf") else ("text", "markdown")
            message.add_attachment(data, maintype=maintype, subtype=subtype, filename=os.path.basename(attachment_path))

        if config.get("smtp_use_tls", True):
            with smtplib.SMTP(config["smtp_host"], int(config.get("smtp_port") or 587), timeout=30) as server:
                server.starttls()
                if config.get("smtp_username"):
                    server.login(config.get("smtp_username"), config.get("smtp_password"))
                server.send_message(message)
            return

        with smtplib.SMTP(config["smtp_host"], int(config.get("smtp_port") or 587), timeout=30) as server:
            if config.get("smtp_username"):
                server.login(config.get("smtp_username"), config.get("smtp_password"))
            server.send_message(message)

    def _deliver_targets(
        self,
        job: Dict[str, Any],
        report_data: Any,
        report_output: Any,
        *,
        run_id: Optional[int] = None,
        lot_execution: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        summary_text, _ = self._report_summary(job, report_data)
        results: List[Dict[str, Any]] = []
        config = self._delivery_config()
        audit_type = (job.get("audit_type") or "").lower()

        if audit_type == "post_crq_distribution":
            current_execution = lot_execution or report_output.get("lot_execution") or self._build_distribution_execution(job, report_data)
            job_config = current_execution.get("job_config") or normalize_distribution_job_config(job.get("job_config") or {})
            delivery_config = self._resolve_distribution_delivery(job_config)
            routes = current_execution.get("routes") or self.store.get_delivery_routes()
            general_attachment_path = report_output.get("general_attachment_path")
            provider_paths = report_output.get("provider_paths") or {}
            tic_recipients = self._resolve_tic_recipients(routes)
            resolved_tic_recipients = delivery_config["override_recipients"] or tic_recipients
            if (
                delivery_config["send_to_tic"]
                and job_config.get("report_options", {}).get("include_summary", True)
                and general_attachment_path
                and resolved_tic_recipients
            ):
                tic_template = self._select_template("tic")
                tic_context = {
                    "job_name": job.get("name"),
                    "profile": job.get("profile"),
                    "lot": "TIC",
                    "status": self._status_label("SUMMARY"),
                    "findings": (report_data.get("summary") or {}).get("total_findings", 0),
                    "execution_id": f"job-{job.get('id')}-run-{run_id or 'pending'}",
                    "observations": "Resum general per a l'area TIC.",
                    "summary": summary_text,
                    "affected_queries": "- No aplica al resum general.",
                    "affected_schemas": "- No aplica al resum general.",
                    "technical_legend": "Consultes afectades:\n- No aplica al resum general.\n\nEsquemes afectats:\n- No aplica al resum general.",
                }
                try:
                    self._send_email_with_tracking(
                        run_id=run_id,
                        job_id=job.get("id"),
                        lot="TIC",
                        audience="tic",
                        recipients=resolved_tic_recipients,
                        subject=self._render_template(tic_template.get("subject_template") or "", tic_context),
                        body=self._render_template(tic_template.get("body_template") or summary_text, tic_context),
                        attachment_path=general_attachment_path,
                        config=config,
                        template=tic_template,
                    )
                    results.append(
                        {
                            "type": "email",
                            "audience": "tic",
                            "status": "ok",
                            "recipients": resolved_tic_recipients,
                            "attachment_name": os.path.basename(general_attachment_path) if general_attachment_path else None,
                        }
                    )
                except Exception as exc:
                    logger.warning(
                        "TIC summary delivery failed for run %s job %s",
                        run_id,
                        job.get("id"),
                        exc_info=exc,
                    )
                    results.append(
                        {
                            "type": "email",
                            "audience": "tic",
                            "status": "error",
                            "error": str(exc),
                            "recipients": resolved_tic_recipients,
                            "attachment_name": os.path.basename(general_attachment_path) if general_attachment_path else None,
                        }
                    )
            elif delivery_config["send_to_tic"] and job_config.get("report_options", {}).get("include_summary", True):
                self._queue_retry(
                    run_id=run_id,
                    job_id=job.get("id"),
                    lot="TIC",
                    audience="tic",
                    error_message="No hi ha destinataris TIC configurats",
                    retry_mode="manual",
                    requested_by="system",
                    error_class=DELIVERY_RESULT_NO_ROUTE,
                    force_status="failed",
                )
                results.append(
                    {
                        "type": "email",
                        "audience": "tic",
                        "status": "error",
                        "error": "No hi ha destinataris TIC configurats",
                        "recipients": [],
                        "attachment_name": os.path.basename(general_attachment_path) if general_attachment_path else None,
                    }
                )

            provider_routes = {
                str(item.get("provider_code")): item
                for item in (routes.get("providers") or [])
                if item.get("enabled", True)
            }
            send_without_findings = bool(job_config.get("send_policy", {}).get("send_without_findings", False))
            for item in current_execution.get("items") or []:
                detection_status = item.get("detection_status")
                if detection_status not in {LOT_STATUS_WITH_FINDINGS, LOT_STATUS_WITHOUT_FINDINGS}:
                    item["email_sent"] = False
                    continue
                if not delivery_config["send_to_lots"]:
                    item["email_sent"] = False
                    item["motivo_sin_envio"] = "L'enviament a lots esta desactivat en aquest job."
                    continue
                if detection_status == LOT_STATUS_WITHOUT_FINDINGS and not send_without_findings:
                    item["email_sent"] = False
                    item["delivery_result"] = DELIVERY_RESULT_SKIPPED_NO_FINDINGS
                    item["motivo_sin_envio"] = item.get("motivo_sin_envio") or "No està activat l'enviament de lots sense troballes."
                    continue
                provider_code = str(item.get("lot") or "").strip()
                item["delivery_audience"] = "provider"
                attachment_path = provider_paths.get(provider_code) if detection_status == LOT_STATUS_WITH_FINDINGS else None
                route = provider_routes.get(provider_code)
                configured_recipients = (route or {}).get("emails") or item.get("route_emails") or []
                recipients = delivery_config["override_recipients"] or configured_recipients
                label = (route or {}).get("label") or item.get("route_label") or provider_code
                legend_context = self._build_technical_legend(report_data, provider_code)
                template_context = {
                    "job_name": job.get("name"),
                    "profile": job.get("profile"),
                    "lot": provider_code,
                    "status": self._status_label(item.get("detection_status")),
                    "findings": item.get("num_findings") if item.get("num_findings") is not None else "-",
                    "execution_id": f"job-{job.get('id')}-run-{run_id or 'pending'}",
                    "observations": item.get("observaciones") or "",
                    "summary": summary_text,
                    **legend_context,
                }
                provider_template = self._select_template(
                    "provider",
                    template_key="provider_with_findings" if detection_status == LOT_STATUS_WITH_FINDINGS else "provider_without_findings",
                )
                if detection_status == LOT_STATUS_WITH_FINDINGS and not attachment_path:
                    item["email_sent"] = False
                    item["delivery_result"] = DELIVERY_RESULT_ATTACHMENT_ERROR
                    item["motivo_sin_envio"] = item.get("motivo_sin_envio") or "No s'ha pogut generar l'adjunt del lot."
                    self._queue_retry(
                        run_id=run_id,
                        job_id=job.get("id"),
                        lot=provider_code,
                        audience="provider",
                        error_message=item["motivo_sin_envio"],
                        retry_mode="manual",
                        requested_by="system",
                        error_class=DELIVERY_RESULT_ATTACHMENT_ERROR,
                        force_status="failed",
                    )
                    results.append(
                        {
                            "type": "email",
                            "audience": "provider",
                            "provider_code": provider_code,
                            "provider_label": label,
                            "status": "error",
                            "error": item["motivo_sin_envio"],
                            "recipients": recipients,
                            "attachment_name": None,
                        }
                    )
                    continue
                if not recipients:
                    item["email_sent"] = False
                    item["delivery_result"] = DELIVERY_RESULT_NO_ROUTE
                    item["motivo_sin_envio"] = "No hi ha destinataris configurats per al lot."
                    self._queue_retry(
                        run_id=run_id,
                        job_id=job.get("id"),
                        lot=provider_code,
                        audience="provider",
                        error_message=item["motivo_sin_envio"],
                        retry_mode="manual",
                        requested_by="system",
                        error_class=DELIVERY_RESULT_NO_ROUTE,
                        force_status="failed",
                    )
                    results.append(
                        {
                            "type": "email",
                            "audience": "provider",
                            "provider_code": provider_code,
                            "provider_label": label,
                            "status": "error",
                            "error": "No hi ha destinataris configurats per al proveidor",
                            "recipients": [],
                            "attachment_name": os.path.basename(attachment_path),
                        }
                    )
                    continue
                try:
                    self._send_email_with_tracking(
                        run_id=run_id,
                        job_id=job.get("id"),
                        lot=provider_code,
                        audience="provider",
                        recipients=recipients,
                        subject=self._render_template((provider_template.get("subject_template") or job_config.get("email_template", {}).get("subject") or ""), template_context),
                        body=self._render_template((provider_template.get("body_template") or job_config.get("email_template", {}).get("body") or summary_text), template_context),
                        attachment_path=attachment_path,
                        config=config,
                        template=provider_template,
                    )
                    item["email_sent"] = True
                    item["delivery_result"] = DELIVERY_RESULT_SENT
                    item["motivo_sin_envio"] = None
                    results.append(
                        {
                            "type": "email",
                            "audience": "provider",
                            "provider_code": provider_code,
                            "provider_label": label,
                            "status": "ok",
                            "recipients": recipients,
                            "attachment_name": os.path.basename(attachment_path) if attachment_path else None,
                        }
                    )
                except Exception as exc:
                    queued_retry = isinstance(exc, DeliverySendError) and exc.queued_retry
                    error_class = exc.error_class if isinstance(exc, DeliverySendError) else DELIVERY_RESULT_DELIVERY_ERROR
                    logger.warning(
                        "Provider delivery failed",
                        exc_info=exc,
                        extra={"run_id": run_id, "job_id": job.get("id"), "lot": provider_code},
                    )
                    item["email_sent"] = False
                    item["delivery_result"] = DELIVERY_RESULT_RETRY_PENDING if queued_retry else error_class
                    item["motivo_sin_envio"] = str(exc)
                    results.append(
                        {
                            "type": "email",
                            "audience": "provider",
                            "provider_code": provider_code,
                            "provider_label": label,
                            "status": "error",
                            "error": str(exc),
                            "recipients": recipients,
                            "attachment_name": os.path.basename(attachment_path) if attachment_path else None,
                            "delivery_result": item["delivery_result"],
                        }
                    )
            return results

        report_path = report_output
        for target in job.get("delivery_targets") or []:
            target_type = (target.get("type") or "").lower()
            if not target.get("enabled", True):
                continue
            if target_type == "email":
                recipients = target.get("config", {}).get("recipients") or config.get("default_recipients") or []
                try:
                    self._send_email(
                        recipients=recipients,
                        subject=f"[Oracle Audit] {job.get('name')} - {job.get('profile')}",
                        body=summary_text,
                        attachment_path=report_path,
                        config=config,
                    )
                    results.append({"type": "email", "status": "ok", "recipients": recipients})
                except Exception as exc:
                    logger.warning(
                        "Generic delivery target failed",
                        exc_info=exc,
                        extra={"run_id": run_id, "job_id": job.get("id"), "target_type": target_type},
                    )
                    results.append({"type": "email", "status": "error", "error": str(exc), "recipients": recipients})
                continue

            results.append({"type": target_type, "status": "disabled", "message": "Fase 2 pendent d'implementacio"})
        return results

    def _apply_rules(self, job: Dict[str, Any], run_id: int, report_data: Any, report_path: Optional[str]) -> List[Dict[str, Any]]:
        summary_text, severity_counts = self._report_summary(job, report_data)
        rules = job.get("severity_rules") or self.store.list_severity_rules(scope="global")
        created: List[Dict[str, Any]] = []
        delivery_config = self._delivery_config()

        for rule in rules:
            if not rule.get("enabled", True):
                continue
            severity = normalize_severity(rule.get("severity", "BAIX"))
            count = int(severity_counts.get(severity, 0))
            conditions = rule.get("conditions") or {}
            minimum = int(conditions.get("min_findings", 1) or 1)
            only_when_findings = bool(conditions.get("only_when_findings", True))
            if only_when_findings and count < minimum:
                continue

            if rule.get("create_task"):
                task = self.store.create_task(
                    source_run_id=run_id,
                    source_job_id=job["id"],
                    title=f"[{severity}] {job['name']}",
                    severity=severity,
                    priority=rule.get("task_priority", "normal"),
                    description=f"{summary_text}\nInforme: {report_path or 'N/A'}",
                    metadata={"rule_id": rule["id"], "findings": count, "report_path": report_path},
                )
                created.append(task)

            if rule.get("send_email"):
                recipients = rule.get("recipients") or delivery_config.get("default_recipients") or []
                if recipients:
                    try:
                        self._send_email(
                            recipients=recipients,
                            subject=f"[Oracle Audit] Regla {severity} - {job['name']}",
                            body=f"Severitat activada: {severity}\nTroballes: {count}\n{summary_text}",
                            attachment_path=report_path if rule.get("attach_report", True) else None,
                            config=delivery_config,
                        )
                    except DELIVERY_RUNTIME_EXCEPTIONS as exc:
                        logger.warning(
                            "Severity rule email delivery failed",
                            exc_info=exc,
                            extra={
                                "job_id": job.get("id"),
                                "rule_id": rule.get("id"),
                                "severity": severity,
                            },
                        )
        return created

    def _extract_retry_attachment(self, run: Dict[str, Any], audience: str, lot: Optional[str]) -> Optional[str]:
        report_path = run.get("report_path")
        if not report_path or not os.path.exists(report_path):
            return None
        if not str(report_path).lower().endswith(".zip"):
            return report_path
        attachment_name = "general.pdf" if audience == "tic" else f"provider_{self._safe_provider_code(str(lot or ''))}.pdf"
        retry_dir = os.path.join(self.reports_dir, "retry_cache", f"run_{run['id']}")
        Path(retry_dir).mkdir(parents=True, exist_ok=True)
        extracted_path = os.path.join(retry_dir, attachment_name)
        with zipfile.ZipFile(report_path, "r") as archive:
            if attachment_name not in archive.namelist():
                return None
            with archive.open(attachment_name) as source, open(extracted_path, "wb") as target:
                target.write(source.read())
        return extracted_path

    def _build_retry_payload(
        self,
        queue_item: Dict[str, Any],
        *,
        run: Dict[str, Any],
        job: Dict[str, Any],
    ) -> Tuple[List[str], Dict[str, Any], Optional[str]]:
        config = self._delivery_config()
        routes = self.store.get_delivery_routes()
        audience = str(queue_item.get("audience") or "provider")
        lot = queue_item.get("lot")
        job_config = normalize_distribution_job_config(job.get("job_config") or {})
        delivery_config = self._resolve_distribution_delivery(job_config)
        template = self._select_template("retry", template_key="manual_resend")
        attachment_path = self._extract_retry_attachment(run, audience, lot)

        if audience == "tic":
            recipients = delivery_config["override_recipients"] or self._resolve_tic_recipients(routes)
            context = {
                "job_name": job.get("name"),
                "profile": job.get("profile"),
                "lot": "TIC",
                "status": self._status_label("RETRY"),
                "findings": (run.get("summary") or {}).get("total_findings", 0),
                "execution_id": f"job-{job.get('id')}-run-{run.get('id')}",
                "observations": "Reenviament programat o manual del resum TIC.",
                "summary": (run.get("summary") or {}).get("lot_execution") or {},
                "affected_queries": "- No aplica al resum general.",
                "affected_schemas": "- No aplica al resum general.",
                "technical_legend": "Consultes afectades:\n- No aplica al resum general.\n\nEsquemes afectats:\n- No aplica al resum general.",
            }
            return recipients, {
                "config": config,
                "template": template,
                "subject": self._render_template(template.get("subject_template") or "", context),
                "body": self._render_template(template.get("body_template") or "", context),
                "attachment_required": True,
            }, attachment_path

        route = next((item for item in self.store.list_lot_routes(audience="provider") if item.get("lot_code") == lot), None)
        if not route:
            route = next((item for item in (routes.get("providers") or []) if item.get("provider_code") == lot), None)
        recipients = delivery_config["override_recipients"] or (route or {}).get("emails") or []
        lot_row = next((item for item in self.store.list_run_lot_statuses(run["id"]) if item.get("lot") == lot), None) or {}
        detection_status = str(lot_row.get("detection_status") or "").strip()
        legend_context = self._build_technical_legend({}, lot)
        context = {
            "job_name": job.get("name"),
            "profile": job.get("profile"),
            "lot": lot,
            "status": self._status_label(detection_status or "RETRY"),
            "findings": lot_row.get("num_findings") if lot_row.get("num_findings") is not None else "-",
            "execution_id": f"job-{job.get('id')}-run-{run.get('id')}",
            "observations": lot_row.get("observaciones") or "Reenviament programat o manual.",
            "summary": (run.get("summary") or {}).get("lot_execution") or {},
            **legend_context,
        }
        return recipients, {
            "config": config,
            "template": template,
            "subject": self._render_template(template.get("subject_template") or "", context),
            "body": self._render_template(template.get("body_template") or "", context),
            "attachment_required": detection_status == LOT_STATUS_WITH_FINDINGS,
        }, attachment_path

    def _sync_retry_delivery_result(self, queue_item: Dict[str, Any], delivery_result: str, error_message: Optional[str]) -> None:
        run_id = queue_item.get("run_id")
        lot = queue_item.get("lot")
        if run_id is None or not lot or str(lot).upper() == "TIC":
            return
        rows = self.store.list_run_lot_statuses(int(run_id))
        updated = False
        for item in rows:
            if item.get("lot") == lot:
                item["delivery_result"] = delivery_result
                item["email_sent"] = delivery_result == DELIVERY_RESULT_SENT
                item["motivo_sin_envio"] = None if delivery_result == DELIVERY_RESULT_SENT else (error_message or item.get("motivo_sin_envio"))
                updated = True
                break
        if updated:
            run = self.store.get_run(int(run_id))
            if run:
                self.store.replace_run_lot_statuses(
                    int(run_id),
                    int(run.get("job_id")),
                    rows,
                    execution_id=next((row.get("execution_id") for row in rows if row.get("execution_id")), f"job-{run.get('job_id')}-run-{run_id}"),
                    executed_at=next((row.get("executed_at") for row in rows if row.get("executed_at")), run.get("started_at")),
                )

    def _mark_retry_queue_item_failed(
        self,
        queue_id: int,
        *,
        queue_item: Dict[str, Any],
        attempts_made: int,
        error_message: str,
        error_class: str,
    ) -> Dict[str, Any]:
        return self.store.update_retry_queue_item(
            queue_id,
            {
                "status": "failed",
                "attempts_made": attempts_made,
                "last_attempt_at": iso_utc(utc_now()),
                "error_message": error_message,
                "error_class": error_class,
                "next_attempt_at": None,
                "lock_token": None,
                "locked_at": None,
            },
        ) or queue_item

    def process_due_retry_queue(self, limit: int = RETRY_BATCH_SIZE) -> List[Dict[str, Any]]:
        now_value = utc_now()
        stale_lock_before = iso_utc(now_value - dt.timedelta(minutes=RETRY_STALE_LOCK_MINUTES))
        items = self.store.claim_due_retry_queue_items(
            limit=limit,
            now_iso=iso_utc(now_value),
            stale_lock_before=stale_lock_before,
        )
        processed: List[Dict[str, Any]] = []
        for item in items:
            try:
                processed.append(self.process_retry_queue_item(int(item["id"]), auto_claimed=True))
            except DELIVERY_RUNTIME_EXCEPTIONS as exc:
                logger.warning(
                    "Retry queue item processing failed",
                    exc_info=exc,
                    extra={"queue_id": item.get("id"), "run_id": item.get("run_id"), "job_id": item.get("job_id")},
                )
                processed.append(
                    self._mark_retry_queue_item_failed(
                        int(item["id"]),
                        queue_item=item,
                        attempts_made=int(item.get("attempts_made") or 0) + 1,
                        error_message=str(exc),
                        error_class=DELIVERY_RESULT_MANUAL_REVIEW,
                    )
                )
        return processed

    def enqueue_manual_retry(
        self,
        *,
        run_id: int,
        lot: Optional[str],
        audience: str,
        requested_by: str = "manual",
    ) -> Dict[str, Any]:
        run = self.store.get_run(run_id)
        if not run:
            raise ValueError("Execucio no trobada")
        return self._queue_retry(
            run_id=run_id,
            job_id=run.get("job_id"),
            lot=lot,
            audience=audience,
            error_message="Reenviament manual pendent",
            retry_mode="manual",
            requested_by=requested_by,
            error_class=DELIVERY_RESULT_DELIVERY_ERROR,
            force_status="pending",
        )

    def process_retry_queue_item(self, queue_id: int, *, auto_claimed: bool = False) -> Dict[str, Any]:
        items = self.store.list_retry_queue(queue_id=queue_id)
        if not items:
            raise ValueError("Element de cua no trobat")
        queue_item = items[0]
        run = self.store.get_run(int(queue_item["run_id"])) if queue_item.get("run_id") else None
        if not run:
            raise ValueError("Execucio associada no trobada")
        job = self.store.get_job(int(queue_item["job_id"])) if queue_item.get("job_id") else None
        if not job:
            raise ValueError("Job associat no trobat")
        audience = str(queue_item.get("audience") or "provider")
        lot = queue_item.get("lot")
        attempts_made = int(queue_item.get("attempts_made") or 0) + 1
        retry_mode = str(queue_item.get("retry_mode") or "manual")
        max_attempts = int(queue_item.get("max_attempts") or 4)
        if not auto_claimed:
            self.store.update_retry_queue_item(
                queue_id,
                {
                    "status": "in_progress",
                    "lock_token": f"manual-lock-{iso_utc(utc_now())}",
                    "locked_at": iso_utc(utc_now()),
                },
            )
        recipients, dispatch, attachment_path = self._build_retry_payload(queue_item, run=run, job=job)
        if dispatch.get("attachment_required", True) and not attachment_path:
            result = self._mark_retry_queue_item_failed(
                queue_id,
                queue_item=queue_item,
                attempts_made=attempts_made,
                error_message="No s'ha trobat l'adjunt del reenvio",
                error_class=DELIVERY_RESULT_ATTACHMENT_ERROR,
            )
            self._sync_retry_delivery_result(queue_item, DELIVERY_RESULT_ATTACHMENT_ERROR, "No s'ha trobat l'adjunt del reenvio")
            return result
        if not recipients:
            result = self._mark_retry_queue_item_failed(
                queue_id,
                queue_item=queue_item,
                attempts_made=attempts_made,
                error_message="No hi ha destinataris configurats",
                error_class=DELIVERY_RESULT_NO_ROUTE,
            )
            self._sync_retry_delivery_result(queue_item, DELIVERY_RESULT_NO_ROUTE, "No hi ha destinataris configurats")
            return result
        try:
            self._send_email_with_tracking(
                run_id=run.get("id"),
                job_id=job.get("id"),
                lot=lot,
                audience=audience,
                recipients=recipients,
                subject=dispatch["subject"],
                body=dispatch["body"],
                attachment_path=attachment_path,
                config=dispatch["config"],
                template=dispatch["template"],
                max_attempts=1,
                queue_on_failure=False,
            )
            result = self.store.update_retry_queue_item(
                queue_id,
                {
                    "status": "done",
                    "attempts_made": attempts_made,
                    "last_attempt_at": iso_utc(utc_now()),
                    "error_message": None,
                    "next_attempt_at": None,
                    "lock_token": None,
                    "locked_at": None,
                },
            ) or queue_item
            self._sync_retry_delivery_result(queue_item, DELIVERY_RESULT_SENT, None)
            return result
        except DELIVERY_RUNTIME_EXCEPTIONS as exc:
            logger.warning(
                "Retry queue delivery failed",
                exc_info=exc,
                extra={
                    "queue_id": queue_id,
                    "run_id": run.get("id"),
                    "job_id": job.get("id"),
                    "lot": lot,
                    "audience": audience,
                },
            )
            error_class = exc.error_class if isinstance(exc, DeliverySendError) else DELIVERY_RESULT_DELIVERY_ERROR
            retryable = isinstance(exc, DeliverySendError) and exc.retryable and retry_mode == "auto"
            next_attempt_at = self._next_retry_at(attempts_made) if retryable and attempts_made < max_attempts else None
            status = "pending" if next_attempt_at else ("exhausted" if retry_mode == "auto" else "failed")
            delivery_result = DELIVERY_RESULT_RETRY_PENDING if next_attempt_at else error_class
            result = self.store.update_retry_queue_item(
                queue_id,
                {
                    "status": status,
                    "attempts_made": attempts_made,
                    "last_attempt_at": iso_utc(utc_now()),
                    "error_message": str(exc),
                    "error_class": error_class,
                    "next_attempt_at": next_attempt_at,
                    "lock_token": None,
                    "locked_at": None,
                },
            ) or queue_item
            self._sync_retry_delivery_result(queue_item, delivery_result, str(exc))
            return result
