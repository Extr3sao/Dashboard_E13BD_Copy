"""Explicit, isolated audit execution primitives (E13DB-002)."""
from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Optional


class RunState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


_TRANSITIONS = {
    RunState.PENDING: {RunState.RUNNING, RunState.INTERRUPTED},
    RunState.RUNNING: {RunState.SUCCESS, RunState.FAILED, RunState.INTERRUPTED},
    RunState.SUCCESS: set(), RunState.FAILED: set(), RunState.INTERRUPTED: set(),
}


class TransientExecutionError(RuntimeError):
    pass


@dataclass
class ExecutionPolicy:
    connection_timeout_seconds: float = 30.0
    check_timeout_seconds: float = 180.0
    run_timeout_seconds: Optional[float] = None
    max_retries: int = 1
    retry_backoff_seconds: float = 0.1


@dataclass
class TargetOutcome:
    target_id: str
    state: RunState
    attempts: int = 0
    result: Any = None
    error: Optional[str] = None


@dataclass
class AuditExecution:
    run_id: str
    state: RunState = RunState.PENDING
    targets: Dict[str, TargetOutcome] = field(default_factory=dict)
    cancellation_requested: bool = False

    def transition(self, state: RunState) -> None:
        if state not in _TRANSITIONS[self.state]:
            raise ValueError(f"invalid run transition: {self.state.value} -> {state.value}")
        self.state = state


def is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (TransientExecutionError, TimeoutError, ConnectionError)):
        return True
    text = str(exc).lower()
    return any(marker in text for marker in ("timeout", "temporarily unavailable", "connection reset", "ora-12170", "ora-12541", "ora-03113", "ora-03114"))


class ReliableAuditRunner:
    """Runs targets independently; a callable lease provider prevents duplicate work."""
    def __init__(self, policy: Optional[ExecutionPolicy] = None, lease_provider: Any = None, sleeper: Callable[[float], None] = time.sleep):
        self.policy = policy or ExecutionPolicy()
        self.lease_provider = lease_provider
        self._sleep = sleeper

    def recover(self, now: Optional[float] = None) -> list[str]:
        if not self.lease_provider or not hasattr(self.lease_provider, "recover_stale"):
            return []
        return list(self.lease_provider.recover_stale(now=now) or [])

    def cancel(self, execution: AuditExecution) -> None:
        execution.cancellation_requested = True

    def run(self, run_id: str, targets: Iterable[str], execute: Callable[[str], Any]) -> AuditExecution:
        execution = AuditExecution(run_id=run_id)
        if self.lease_provider and not self.lease_provider.acquire(run_id):
            execution.transition(RunState.INTERRUPTED)
            return execution
        started = time.monotonic()
        execution.transition(RunState.RUNNING)
        try:
            for target_id in targets:
                if execution.cancellation_requested or self._expired(started):
                    execution.targets[str(target_id)] = TargetOutcome(str(target_id), RunState.INTERRUPTED, error="run_cancelled_or_timed_out")
                    continue
                execution.targets[str(target_id)] = self._run_target(str(target_id), execute)
            states = {item.state for item in execution.targets.values()}
            execution.transition(RunState.INTERRUPTED if execution.cancellation_requested or RunState.INTERRUPTED in states else (RunState.FAILED if RunState.FAILED in states else RunState.SUCCESS))
        finally:
            if self.lease_provider:
                self.lease_provider.release(run_id, execution.state.value)
        return execution

    def _expired(self, started: float) -> bool:
        return self.policy.run_timeout_seconds is not None and time.monotonic() - started >= self.policy.run_timeout_seconds

    def _run_target(self, target_id: str, execute: Callable[[str], Any]) -> TargetOutcome:
        for attempt in range(1, self.policy.max_retries + 2):
            try:
                pool = ThreadPoolExecutor(max_workers=1)
                future = pool.submit(execute, target_id)
                try:
                    result = future.result(timeout=self.policy.check_timeout_seconds)
                finally:
                    # A timed-out Python worker cannot safely be killed; don't block the
                    # audit state transition waiting for it. Real DB calls also receive a
                    # driver-level timeout from their adapter.
                    pool.shutdown(wait=False, cancel_futures=True)
                return TargetOutcome(target_id, RunState.SUCCESS, attempt, result=result)
            except TimeoutError:
                error: BaseException = TimeoutError("check_timeout")
            except BaseException as exc:  # isolate target failures
                error = exc
            if attempt <= self.policy.max_retries and is_transient_error(error):
                self._sleep(self.policy.retry_backoff_seconds * (2 ** (attempt - 1)))
                continue
            return TargetOutcome(target_id, RunState.FAILED, attempt, error=str(error))
        raise AssertionError("unreachable")


class SqliteExecutionLease:
    """Durable, atomic lease suitable for scheduler/restart idempotency."""
    def __init__(self, path: str, lease_seconds: float = 300.0):
        self.path, self.lease_seconds = path, lease_seconds
        conn = self._connect()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS audit_execution_leases (run_id TEXT PRIMARY KEY, state TEXT NOT NULL, expires_at REAL NOT NULL)")
            conn.commit()
        finally:
            conn.close()

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10, isolation_level="IMMEDIATE")

    def acquire(self, run_id: str) -> bool:
        now = time.time()
        conn = self._connect()
        try:
            row = conn.execute("SELECT state, expires_at FROM audit_execution_leases WHERE run_id = ?", (run_id,)).fetchone()
            if row and row[0] == RunState.RUNNING.value and row[1] > now:
                return False
            conn.execute("INSERT INTO audit_execution_leases(run_id,state,expires_at) VALUES(?,?,?) ON CONFLICT(run_id) DO UPDATE SET state=excluded.state, expires_at=excluded.expires_at", (run_id, RunState.RUNNING.value, now + self.lease_seconds))
            conn.commit()
            return True
        finally:
            conn.close()

    def release(self, run_id: str, state: str) -> None:
        conn = self._connect()
        try:
            conn.execute("UPDATE audit_execution_leases SET state = ?, expires_at = ? WHERE run_id = ?", (state, time.time(), run_id))
            conn.commit()
        finally:
            conn.close()

    def recover_stale(self, now: Optional[float] = None) -> list[str]:
        now = time.time() if now is None else now
        conn = self._connect()
        try:
            rows = conn.execute("SELECT run_id FROM audit_execution_leases WHERE state = ? AND expires_at <= ?", (RunState.RUNNING.value, now)).fetchall()
            conn.execute("UPDATE audit_execution_leases SET state = ?, expires_at = ? WHERE state = ? AND expires_at <= ?", (RunState.INTERRUPTED.value, now, RunState.RUNNING.value, now))
            conn.commit()
            return [row[0] for row in rows]
        finally:
            conn.close()
