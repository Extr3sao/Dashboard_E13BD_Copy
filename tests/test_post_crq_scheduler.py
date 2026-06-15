import threading
import time
import unittest

from src.api.post_crq_scheduler import (
    QueryCategory,
    SchedulerTask,
    classify_check_category,
    resolve_scheduler_config,
    run_scheduled_tasks,
    timeout_for_category,
)


class TestPostCrqScheduler(unittest.TestCase):
    def test_default_scheduler_config_is_conservative(self):
        config = resolve_scheduler_config({})

        self.assertEqual(config.max_concurrency_global, 2)
        self.assertEqual(config.max_concurrency_upper_bound, 4)
        self.assertEqual(config.max_heavy_concurrency, 1)

    def test_scheduler_clamps_configured_parallelism_to_upper_bound(self):
        config = resolve_scheduler_config({"max_concurrency": 8, "max_concurrency_upper_bound": 4})
        self.assertEqual(config.max_concurrency_global, 4)

    def test_classification_uses_known_check_mapping(self):
        self.assertEqual(classify_check_category("CHECK_06").value, "heavy")
        self.assertEqual(classify_check_category("CHECK_08").value, "light")
        self.assertEqual(classify_check_category("CHECK_03").value, "medium")

    def test_scheduler_never_runs_two_heavy_queries_at_once(self):
        config = resolve_scheduler_config({"max_concurrency": 3, "max_concurrency_upper_bound": 4})
        tasks = [
            SchedulerTask(index=0, check_id="CHECK_06", category=QueryCategory.HEAVY, timeout_seconds=timeout_for_category(config, QueryCategory.HEAVY), payload={}),
            SchedulerTask(index=1, check_id="CHECK_11", category=QueryCategory.HEAVY, timeout_seconds=timeout_for_category(config, QueryCategory.HEAVY), payload={}),
            SchedulerTask(index=2, check_id="CHECK_08", category=QueryCategory.LIGHT, timeout_seconds=timeout_for_category(config, QueryCategory.LIGHT), payload={}),
        ]
        lock = threading.Lock()
        running = {"global": 0, "heavy": 0, "max_global": 0, "max_heavy": 0}

        def execute(task):
            with lock:
                running["global"] += 1
                running["max_global"] = max(running["max_global"], running["global"])
                if task.category == QueryCategory.HEAVY:
                    running["heavy"] += 1
                    running["max_heavy"] = max(running["max_heavy"], running["heavy"])
            time.sleep(0.03)
            with lock:
                running["global"] -= 1
                if task.category == QueryCategory.HEAVY:
                    running["heavy"] -= 1
            return {"check_id": task.check_id, "status": "ok", "duration_ms": 30}

        run_data = run_scheduled_tasks(tasks, execute, config)

        self.assertEqual(len(run_data["results"]), 3)
        self.assertLessEqual(running["max_heavy"], 1)
        self.assertLessEqual(run_data["metrics"]["max_parallel_observed"], 3)

    def test_scheduler_retries_transient_error_once(self):
        config = resolve_scheduler_config({"max_concurrency": 2, "max_retries": 1})
        task = SchedulerTask(index=0, check_id="CHECK_02", category=QueryCategory.LIGHT, timeout_seconds=timeout_for_category(config, QueryCategory.LIGHT), payload={})
        calls = {"count": 0}

        def execute(current_task):
            calls["count"] += 1
            if calls["count"] == 1:
                return {"check_id": current_task.check_id, "status": "error", "error": "timeout", "duration_ms": 10}
            return {"check_id": current_task.check_id, "status": "ok", "duration_ms": 10}

        run_data = run_scheduled_tasks([task], execute, config)

        self.assertEqual(calls["count"], 2)
        self.assertEqual(run_data["results"][0]["status"], "ok")
        self.assertEqual(run_data["metrics"]["retries_used"], 1)

    def test_scheduler_degrades_after_saturation_signal(self):
        config = resolve_scheduler_config({"max_concurrency": 3, "degraded_max_concurrency": 1})
        tasks = [
            SchedulerTask(index=0, check_id="CHECK_06", category=QueryCategory.HEAVY, timeout_seconds=timeout_for_category(config, QueryCategory.HEAVY), payload={}),
            SchedulerTask(index=1, check_id="CHECK_07", category=QueryCategory.MEDIUM, timeout_seconds=timeout_for_category(config, QueryCategory.MEDIUM), payload={}),
        ]
        first = {"done": False}

        def execute(task):
            if not first["done"]:
                first["done"] = True
                return {"check_id": task.check_id, "status": "error", "error": "ORA-00020: maximum number of processes exceeded", "duration_ms": 10}
            return {"check_id": task.check_id, "status": "ok", "duration_ms": 10}

        run_data = run_scheduled_tasks(tasks, execute, config)

        self.assertTrue(run_data["metrics"]["degraded_mode_triggered"])
        self.assertEqual(run_data["metrics"]["effective_max_concurrency"], 1)


if __name__ == "__main__":
    unittest.main()
