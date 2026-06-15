import os
import re
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class QueryCategory(str, Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


DEFAULT_CHECK_CATEGORIES = {
    "CHECK_01": QueryCategory.MEDIUM,
    "CHECK_02": QueryCategory.LIGHT,
    "CHECK_03": QueryCategory.MEDIUM,
    "CHECK_04": QueryCategory.HEAVY,
    "CHECK_05": QueryCategory.LIGHT,
    "CHECK_06": QueryCategory.HEAVY,
    "CHECK_07": QueryCategory.MEDIUM,
    "CHECK_08": QueryCategory.LIGHT,
    "CHECK_09": QueryCategory.MEDIUM,
    "CHECK_10": QueryCategory.LIGHT,
    "CHECK_11": QueryCategory.HEAVY,
    "CHECK_12": QueryCategory.HEAVY,
}

TRANSIENT_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "call timeout",
    "ora-12170",
    "ora-03113",
    "ora-03114",
    "ora-12541",
    "ora-12514",
    "connection reset",
    "temporarily unavailable",
)

SATURATION_ERROR_MARKERS = (
    "ora-00018",
    "ora-00020",
    "ora-04021",
    "ora-04031",
    "resource busy",
    "timeout",
    "call timeout",
)


@dataclass
class SchedulerConfig:
    max_concurrency_global: int
    max_concurrency_upper_bound: int
    max_heavy_concurrency: int
    max_medium_concurrency: int
    max_light_concurrency: int
    max_retries: int
    light_timeout_seconds: int
    medium_timeout_seconds: int
    heavy_timeout_seconds: int
    enable_auto_throttle: bool
    degraded_max_concurrency: int
    queue_policy: str = "weighted_fifo"


@dataclass
class SchedulerTask:
    index: int
    check_id: str
    category: QueryCategory
    timeout_seconds: int
    payload: Dict[str, Any]
    retries_used: int = 0
    enqueued_at: float = 0.0


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _parse_category_overrides(raw: str) -> Dict[str, QueryCategory]:
    overrides: Dict[str, QueryCategory] = {}
    for chunk in (raw or "").split(","):
        if ":" not in chunk:
            continue
        check_id, category = [part.strip().upper() for part in chunk.split(":", 1)]
        if category == "HEAVY":
            overrides[check_id] = QueryCategory.HEAVY
        elif category == "MEDIUM":
            overrides[check_id] = QueryCategory.MEDIUM
        elif category == "LIGHT":
            overrides[check_id] = QueryCategory.LIGHT
    return overrides


def resolve_scheduler_config(overrides: Optional[Dict[str, Any]] = None) -> SchedulerConfig:
    payload = dict(overrides or {})
    upper_bound = max(1, int(payload.get("max_concurrency_upper_bound") or _int_env("POST_CRQ_MAX_CONCURRENCY_UPPER_BOUND", 4)))
    configured_global = int(
        payload.get("max_concurrency")
        or payload.get("max_concurrency_global")
        or os.getenv("POST_CRQ_MAX_CONCURRENCY")
        or os.getenv("POST_CRQ_MAX_WORKERS")
        or 2
    )
    global_limit = max(1, min(configured_global, upper_bound))
    degraded_limit = max(1, min(int(payload.get("degraded_max_concurrency") or 1), global_limit))
    return SchedulerConfig(
        max_concurrency_global=global_limit,
        max_concurrency_upper_bound=upper_bound,
        max_heavy_concurrency=max(1, min(int(payload.get("max_heavy_concurrency") or _int_env("POST_CRQ_MAX_HEAVY_CONCURRENCY", 1)), global_limit)),
        max_medium_concurrency=max(1, min(int(payload.get("max_medium_concurrency") or _int_env("POST_CRQ_MAX_MEDIUM_CONCURRENCY", max(2, global_limit))), global_limit)),
        max_light_concurrency=max(1, min(int(payload.get("max_light_concurrency") or _int_env("POST_CRQ_MAX_LIGHT_CONCURRENCY", max(2, global_limit))), global_limit)),
        max_retries=max(0, int(payload.get("max_retries") or _int_env("POST_CRQ_SCHEDULER_MAX_RETRIES", 1))),
        light_timeout_seconds=max(30, int(payload.get("light_timeout_seconds") or _int_env("POST_CRQ_LIGHT_TIMEOUT_SECONDS", 90))),
        medium_timeout_seconds=max(30, int(payload.get("medium_timeout_seconds") or _int_env("POST_CRQ_MEDIUM_TIMEOUT_SECONDS", 180))),
        heavy_timeout_seconds=max(30, int(payload.get("heavy_timeout_seconds") or _int_env("POST_CRQ_HEAVY_TIMEOUT_SECONDS", 420))),
        enable_auto_throttle=bool(payload.get("enable_auto_throttle")) if "enable_auto_throttle" in payload else _bool_env("POST_CRQ_ENABLE_AUTO_THROTTLE", True),
        degraded_max_concurrency=degraded_limit,
    )


def classify_check_category(check_id: str, sql: str = "") -> QueryCategory:
    env_overrides = _parse_category_overrides(os.getenv("POST_CRQ_CHECK_CATEGORY_OVERRIDES", ""))
    if check_id in env_overrides:
        return env_overrides[check_id]
    if check_id in DEFAULT_CHECK_CATEGORIES:
        return DEFAULT_CHECK_CATEGORIES[check_id]

    lowered = str(sql or "").lower()
    score = 0
    score += len(re.findall(r"\bjoin\b", lowered))
    score += 2 * len(re.findall(r"\b(select|with)\b", lowered)) - 1
    score += 2 if "dba_source" in lowered else 0
    score += 2 if "dba_dependencies" in lowered else 0
    score += 1 if "dba_objects" in lowered else 0
    score += 1 if "group by" in lowered else 0
    score += 1 if "distinct" in lowered else 0
    score += 1 if "listagg" in lowered or "regexp_" in lowered else 0

    if score >= 6:
        return QueryCategory.HEAVY
    if score >= 3:
        return QueryCategory.MEDIUM
    return QueryCategory.LIGHT


def timeout_for_category(config: SchedulerConfig, category: QueryCategory) -> int:
    if category == QueryCategory.HEAVY:
        return config.heavy_timeout_seconds
    if category == QueryCategory.MEDIUM:
        return config.medium_timeout_seconds
    return config.light_timeout_seconds


def _category_capacity(config: SchedulerConfig, category: QueryCategory) -> int:
    if category == QueryCategory.HEAVY:
        return config.max_heavy_concurrency
    if category == QueryCategory.MEDIUM:
        return config.max_medium_concurrency
    return config.max_light_concurrency


def _result_error_text(result: Dict[str, Any]) -> str:
    return str(result.get("error") or "").strip().lower()


def should_retry_result(result: Dict[str, Any], task: SchedulerTask, config: SchedulerConfig) -> bool:
    if task.retries_used >= config.max_retries:
        return False
    if str(result.get("status") or "").lower() != "error":
        return False
    error_text = _result_error_text(result)
    return any(marker in error_text for marker in TRANSIENT_ERROR_MARKERS)


def should_degrade_after_result(result: Dict[str, Any], task: SchedulerTask, config: SchedulerConfig) -> bool:
    if not config.enable_auto_throttle:
        return False
    error_text = _result_error_text(result)
    if any(marker in error_text for marker in SATURATION_ERROR_MARKERS):
        return True
    if task.category == QueryCategory.HEAVY and int(result.get("duration_ms") or 0) >= int(task.timeout_seconds * 1000 * 0.8):
        return True
    return False


def run_scheduled_tasks(
    tasks: List[SchedulerTask],
    execute_task: Callable[[SchedulerTask], Dict[str, Any]],
    config: SchedulerConfig,
) -> Dict[str, Any]:
    if not tasks:
        return {"results": [], "metrics": {"configured_max_concurrency": config.max_concurrency_global}}

    pending = list(tasks)
    for task in pending:
        task.enqueued_at = time.perf_counter()
    results: List[Optional[Dict[str, Any]]] = [None] * len(tasks)
    inflight: Dict[Any, SchedulerTask] = {}
    running_counts = {category: 0 for category in QueryCategory}
    degraded_mode = False
    effective_limit = config.max_concurrency_global
    max_parallel_observed = 0
    max_parallel_by_category = {category.value: 0 for category in QueryCategory}
    retries_used = 0

    def can_dispatch(task: SchedulerTask) -> bool:
        if len(inflight) >= effective_limit:
            return False
        return running_counts[task.category] < _category_capacity(config, task.category)

    def pick_next_task() -> Optional[int]:
        for index, candidate in enumerate(pending):
            if can_dispatch(candidate):
                return index
        return None

    with ThreadPoolExecutor(max_workers=config.max_concurrency_global) as executor:
        while pending or inflight:
            submitted = False
            while len(inflight) < effective_limit:
                next_index = pick_next_task()
                if next_index is None:
                    break
                task = pending.pop(next_index)
                running_counts[task.category] += 1
                future = executor.submit(execute_task, task)
                inflight[future] = task
                submitted = True
                max_parallel_observed = max(max_parallel_observed, len(inflight))
                max_parallel_by_category[task.category.value] = max(
                    max_parallel_by_category[task.category.value],
                    running_counts[task.category],
                )

            if not inflight:
                break

            done, _ = wait(list(inflight.keys()), return_when=FIRST_COMPLETED)
            for future in done:
                task = inflight.pop(future)
                running_counts[task.category] -= 1
                result = future.result()
                queue_wait_ms = int((time.perf_counter() - task.enqueued_at) * 1000) - int(result.get("duration_ms") or 0)
                result["scheduler"] = {
                    "query_category": task.category.value,
                    "queue_wait_ms": max(0, queue_wait_ms),
                    "attempt": task.retries_used + 1,
                    "timeout_seconds": task.timeout_seconds,
                }

                if should_retry_result(result, task, config):
                    task.retries_used += 1
                    task.enqueued_at = time.perf_counter()
                    pending.insert(0, task)
                    retries_used += 1
                    continue

                if should_degrade_after_result(result, task, config):
                    degraded_mode = True
                    effective_limit = config.degraded_max_concurrency

                results[task.index] = result

            if not submitted and degraded_mode and pending and not inflight:
                effective_limit = config.degraded_max_concurrency

    return {
        "results": [item for item in results if item is not None],
        "metrics": {
            "configured_max_concurrency": config.max_concurrency_global,
            "effective_max_concurrency": effective_limit,
            "max_parallel_observed": max_parallel_observed,
            "max_parallel_by_category": max_parallel_by_category,
            "degraded_mode_triggered": degraded_mode,
            "retries_used": retries_used,
            "queue_policy": config.queue_policy,
            "auto_throttle_enabled": config.enable_auto_throttle,
            "category_distribution": {
                category.value: sum(1 for task in tasks if task.category == category)
                for category in QueryCategory
            },
        },
    }
