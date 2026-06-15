import os
import tempfile
from pathlib import Path


def _is_writable_dir(path: Path) -> bool:
    probe = path / ".oracle_audit_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _candidate_dirs():
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        yield Path(local_appdata) / "OracleAudit"
    yield Path(tempfile.gettempdir()) / "OracleAudit"
    yield Path(tempfile.gettempdir())


def resolve_sqlite_path(env_var_name: str, default_filename: str) -> str:
    configured = os.environ.get(env_var_name)
    if configured:
        return configured
    for base_dir in _candidate_dirs():
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
            if not _is_writable_dir(base_dir):
                continue
            return str(base_dir / default_filename)
        except OSError:
            continue
    return str(Path(tempfile.gettempdir()) / default_filename)
