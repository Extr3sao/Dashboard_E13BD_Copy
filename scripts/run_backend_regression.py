from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTEST_BASETEMP_ROOT = ROOT / "output" / "pytest-regression"

TEST_BLOCKS = [
    [
        "tests/test_main_runtime.py",
        "tests/test_post_crq_audit.py",
        "tests/test_post_crq_wrapped_sql.py",
        "tests/test_check11_ai.py",
    ],
    [
        "tests/test_report_generation.py",
    ],
    [
        "tests/test_automation.py",
        "tests/test_checks_admin_router.py",
        "tests/test_ai_assistant.py",
        "tests/test_ai_integration.py",
    ],
    [
        "tests/test_query_sync_service.py",
        "tests/test_internal_db.py",
        "tests/test_db_manager.py",
        "tests/test_config_loader.py",
        "tests/test_audit_plan_engine.py",
        "tests/test_post_crq_pipeline.py",
    ],
]


def run_block(index: int, tests: list[str]) -> None:
    basetemp = PYTEST_BASETEMP_ROOT / f"block-{index}"
    basetemp.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "pytest", *tests, "-q", f"--basetemp={basetemp}"]
    print(f"[backend-regression] block {index}/{len(TEST_BLOCKS)}")
    print("  " + " ".join(command))
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> int:
    for index, tests in enumerate(TEST_BLOCKS, start=1):
        run_block(index, tests)
    print("[backend-regression] all blocks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
