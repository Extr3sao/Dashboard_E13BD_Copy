"""Consolidate the per-file vitest logs produced during the DEV Agent audit run.

The OneDrive-hosted checkout cannot complete a single-process run of the whole
frontend suite inside a bounded wall-clock budget (module import alone took
~159s for a single heavy file), so the suite was executed file-by-file under
`--no-file-parallelism`. This script merges those logs into one summary:
the LAST observed result per test file wins (logs are ordered by mtime).

Usage: py output/devagent_evidence/tally_frontend_runs.py <log-dir> ...
"""

from __future__ import annotations

import glob
import os
import re
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*m")
FILE_MARK = re.compile(r"^###FILE (.+?)\s*$")
PASSED = re.compile(r"Tests\s+(\d+) passed")
FAILED = re.compile(r"Tests\s+(\d+) failed")
RC = re.compile(r"^RC=(\d+)\s*$")
TEST_FILE = re.compile(r"\.test\.(js|jsx)$")


def main() -> int:
    dirs = sys.argv[1:] or ["."]
    logs: list[str] = []
    for d in dirs:
        logs.extend(glob.glob(os.path.join(d, "fe_*.log")))
    # Chronological order: the last observed result for a test file wins.
    logs.sort(key=os.path.getmtime)

    results: dict[str, dict[str, object]] = {}
    for log in logs:
        current: str | None = None
        with open(log, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = ANSI.sub("", raw)
                mark = FILE_MARK.match(line)
                if mark:
                    current = mark.group(1).strip()
                    continue
                if not current:
                    continue
                passed = PASSED.search(line)
                if passed:
                    entry = results.setdefault(current, {})
                    entry["passed"] = int(passed.group(1))
                    entry["failed"] = 0
                    entry["log"] = os.path.basename(log)
                failed = FAILED.search(line)
                if failed:
                    entry = results.setdefault(current, {})
                    entry["failed"] = int(failed.group(1))
                    entry["log"] = os.path.basename(log)
                rc = RC.match(line)
                if rc:
                    results.setdefault(current, {})["rc"] = int(rc.group(1))

    total_passed = 0
    total_failed = 0
    for path in sorted(results):
        if not TEST_FILE.search(path):
            print(f"(aggregate run) {path}: {results[path]}")
            continue
        entry = results[path]
        passed = int(entry.get("passed", 0))
        failed = int(entry.get("failed", 0))
        total_passed += passed
        total_failed += failed
        print(
            f"{path}: passed={passed} failed={failed} rc={entry.get('rc')} "
            f"[{entry.get('log')}]"
        )

    counted = [p for p in results if TEST_FILE.search(p)]
    print("-" * 60)
    print(
        f"FILES={len(counted)} TESTS_PASSED={total_passed} "
        f"TESTS_FAILED={total_failed}"
    )
    return 0 if total_failed == 0 and len(counted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
