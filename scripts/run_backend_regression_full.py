from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTEST_BASETEMP = ROOT / "output" / "pytest-regression" / "full-suite"
DEFAULT_TIMEOUT_SECONDS = 1800


def _resolve_timeout_seconds() -> int:
    raw = str(os.environ.get("BACKEND_REGRESSION_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"BACKEND_REGRESSION_TIMEOUT_SECONDS no és un enter vàlid: {raw}") from exc
    if value <= 0:
        raise SystemExit("BACKEND_REGRESSION_TIMEOUT_SECONDS ha de ser major que 0")
    return value


def main() -> int:
    timeout_seconds = _resolve_timeout_seconds()
    PYTEST_BASETEMP.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--basetemp={PYTEST_BASETEMP}",
    ]
    print("[backend-regression-full] full backend suite")
    print("  " + " ".join(command))
    print(f"[backend-regression-full] timeout: {timeout_seconds}s")
    try:
        completed = subprocess.run(command, cwd=ROOT, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(
            f"[backend-regression-full] timeout després de {timeout_seconds}s executant pytest complet"
        ) from exc
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    print("[backend-regression-full] full suite passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
