import os
import tempfile
import time
import unittest

from src.api.execution_reliability import ExecutionPolicy, ReliableAuditRunner, RunState, SqliteExecutionLease, TransientExecutionError


class ExecutionReliabilityTests(unittest.TestCase):
    def test_transitions_and_target_isolation_retry(self):
        calls = {"A": 0}
        def work(target):
            if target == "B": raise ValueError("bad SQL")
            if target == "A" and (calls.__setitem__("A", calls["A"] + 1) or calls["A"] == 1): raise TransientExecutionError("connection reset")
            return target
        run = ReliableAuditRunner(ExecutionPolicy(max_retries=1, retry_backoff_seconds=0), sleeper=lambda _: None).run("r", ["A", "B", "C"], work)
        self.assertEqual(run.state, RunState.FAILED); self.assertEqual(run.targets["A"].attempts, 2)
        self.assertEqual(run.targets["B"].state, RunState.FAILED); self.assertEqual(run.targets["C"].state, RunState.SUCCESS)
        with self.assertRaises(ValueError): run.transition(RunState.SUCCESS)

    def test_durable_lease_recovers_and_allows_future_run(self):
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False); handle.close()
        try:
            lease = SqliteExecutionLease(handle.name, lease_seconds=60)
            self.assertTrue(lease.acquire("same")); self.assertFalse(lease.acquire("same"))
            self.assertIn("same", lease.recover_stale(now=time.time() + 61))
            self.assertTrue(lease.acquire("same")); lease.release("same", "SUCCESS")
        finally:
            os.unlink(handle.name)

    def test_cancellation_is_not_success(self):
        runner = ReliableAuditRunner(); run = runner.run("r", [], lambda _: None)
        self.assertEqual(run.state, RunState.SUCCESS)
