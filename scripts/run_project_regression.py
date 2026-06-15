from __future__ import annotations

import subprocess
import sys
from shutil import which
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "src" / "web-app"
ORACLE_REQUIRED_ENV_VARS = (
    "ORACLE_SMOKE_CONNECTIONS_FILE",
    "ORACLE_SMOKE_PROFILE",
    "ORACLE_SMOKE_SCHEMA",
)
BACKEND_REGRESSION_RUNNERS = {
    "stable": "scripts/run_backend_regression.py",
    "full": "scripts/run_backend_regression_full.py",
}


def _resolve_command(name: str) -> str:
    if sys.platform.startswith("win"):
        cmd_variant = f"{name}.cmd"
        resolved = which(cmd_variant)
        if resolved:
            return resolved
    resolved = which(name)
    if resolved:
        return resolved
    raise FileNotFoundError(f"No s'ha trobat l'executable requerit: {name}")


def run_step(label: str, command: list[str], *, cwd: Path) -> None:
    print(f"[project-regression] {label}")
    print("  " + " ".join(command))
    completed = subprocess.run(command, cwd=cwd)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _missing_oracle_env_vars() -> list[str]:
    return [name for name in ORACLE_REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]


def _resolve_backend_regression_runner() -> tuple[str, str]:
    mode = str(os.environ.get("BACKEND_REGRESSION_MODE", "stable")).strip().lower() or "stable"
    runner = BACKEND_REGRESSION_RUNNERS.get(mode)
    if not runner:
        valid_modes = ", ".join(sorted(BACKEND_REGRESSION_RUNNERS))
        raise SystemExit(f"BACKEND_REGRESSION_MODE invàlid: {mode}. Valors admesos: {valid_modes}")
    return mode, runner


def main() -> int:
    backend_mode, backend_runner = _resolve_backend_regression_runner()
    run_step(
        f"backend ({backend_mode})",
        [sys.executable, backend_runner],
        cwd=ROOT,
    )
    npm = _resolve_command("npm")
    npx = _resolve_command("npx")
    run_step("frontend lint", [npm, "run", "lint"], cwd=WEB_APP)
    run_step("frontend vitest", [npx, "vitest", "run", "--reporter=dot"], cwd=WEB_APP)
    run_step("frontend build", [npm, "run", "build"], cwd=WEB_APP)
    run_step("frontend smoke mocked", [npm, "run", "smoke:ui"], cwd=WEB_APP)
    run_step("frontend smoke real", [npm, "run", "smoke:ui:real"], cwd=WEB_APP)
    missing_oracle_env_vars = _missing_oracle_env_vars()
    if missing_oracle_env_vars:
        print("[project-regression] frontend smoke oracle skipped")
        print("  missing env vars: " + ", ".join(missing_oracle_env_vars))
    else:
        run_step("frontend smoke oracle", [npm, "run", "smoke:ui:oracle"], cwd=WEB_APP)
    print("[project-regression] all stable checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
