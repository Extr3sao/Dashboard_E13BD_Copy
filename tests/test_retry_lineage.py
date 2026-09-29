import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api.automation_service import AutomationService, MANUAL_RETRY_ALLOWLIST
from src.core.automation_store import AutomationStore


class TestManualRetryLineage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="retry-lineage-")
        self.store = AutomationStore(str(Path(self.temp_dir) / "automation.db"))
        self.job = self.store.create_job(
            {
                "name": "Retry lineage",
                "enabled": True,
                "audit_type": "post_crq",
                "profile": "E13DB",
                "schemas": [],
                "checks": [],
                "time_filter": {},
                "report_format": "markdown",
                "schedule_type": "once",
                "schedule_config": {},
                "timeout_seconds": 60,
                "delivery_targets": [],
                "severity_rules": [],
            }
        )
        self.run_id = self.store.create_run(self.job["id"])
        self.service = AutomationService(self.store, None, reports_dir=self.temp_dir)

    def tearDown(self):
        self.store = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_attempt(self, status):
        return self.store.create_delivery_attempt(
            {
                "run_id": self.run_id,
                "job_id": self.job["id"],
                "lot": "LOT_P0",
                "audience": "provider",
                "status": status,
            }
        )

    def _queue_item(self):
        return self.store.create_retry_queue_item(
            {
                "run_id": self.run_id,
                "job_id": self.job["id"],
                "lot": "LOT_P0",
                "audience": "provider",
                "status": "pending",
                "requested_by": "test",
                "error_message": "direct fixture item",
                "retry_mode": "manual",
            }
        )

    def test_manual_retry_rejects_unverified_delivery_states_without_side_effects(self):
        self.assertEqual(MANUAL_RETRY_ALLOWLIST, {"failed"})
        for label, status in (
            ("no_attempt", None),
            ("empty_state", ""),
            ("unrecognized_state", "mystery"),
            ("sent", "sent"),
            ("in_progress", "in_progress"),
            ("unknown_delivery_outcome", "unknown_delivery_outcome"),
        ):
            with self.subTest(label=label):
                if status is not None:
                    original_attempt = self._create_attempt(status)
                else:
                    original_attempt = None
                queue_before = self.store.list_retry_queue(run_id=self.run_id)
                attempts_before = self.store.list_delivery_attempts(run_id=self.run_id, lot="LOT_P0", audience="provider")

                with self.assertRaises(ValueError):
                    self.service.enqueue_manual_retry(
                        run_id=self.run_id,
                        lot="LOT_P0",
                        audience="provider",
                        requested_by="test",
                    )

                self.assertEqual(self.store.list_retry_queue(run_id=self.run_id), queue_before)
                self.assertEqual(
                    self.store.list_delivery_attempts(run_id=self.run_id, lot="LOT_P0", audience="provider"),
                    attempts_before,
                )
                if original_attempt is not None:
                    self.assertEqual(
                        self.store.list_delivery_attempts(attempt_id=original_attempt["id"])[0],
                        original_attempt,
                    )

    def test_manual_retry_allows_verified_failed_delivery(self):
        self._create_attempt("failed")
        queue_before = self.store.list_retry_queue(run_id=self.run_id)

        queue_item = self.service.enqueue_manual_retry(
            run_id=self.run_id,
            lot="LOT_P0",
            audience="provider",
            requested_by="test",
        )

        self.assertEqual(queue_item["status"], "pending")
        self.assertEqual(len(self.store.list_retry_queue(run_id=self.run_id)), len(queue_before) + 1)

    def test_processing_gate_rejects_directly_queued_unsafe_item_without_smtp(self):
        original_attempt = self._create_attempt("sent")
        queue_item = self._queue_item()

        with patch.object(self.service, "_send_email_with_tracking") as send_email:
            result = self.service.process_retry_queue_item(queue_item["id"])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_class"], "manual_review")
        send_email.assert_not_called()
        self.assertEqual(self.store.list_delivery_attempts(attempt_id=original_attempt["id"])[0], original_attempt)

    def test_concurrent_manual_processors_atomically_claim_once(self):
        self._create_attempt("failed")
        queue_item = self._queue_item()
        barrier = threading.Barrier(2)
        calls = []
        results = []

        def send_email(**_kwargs):
            calls.append("smtp")

        def process():
            barrier.wait(timeout=5)
            results.append(self.service.process_retry_queue_item(queue_item["id"]))

        dispatch = {"attachment_required": False, "subject": "retry", "body": "retry", "config": {}, "template": {}}
        with patch.object(self.service, "_build_retry_payload", return_value=(["test@example.invalid"], dispatch, None)), patch.object(
            self.service, "_send_email_with_tracking", side_effect=send_email
        ):
            workers = [threading.Thread(target=process) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=10)

        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(calls, ["smtp"])
        self.assertEqual(len(results), 2)
        self.assertEqual(self.store.list_retry_queue(queue_id=queue_item["id"])[0]["status"], "done")
        self.assertEqual(self.store.list_retry_queue(queue_id=queue_item["id"])[0]["attempts_made"], 1)
