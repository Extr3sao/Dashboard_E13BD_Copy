from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.automation_store import AutomationStore
from src.core.internal_db import InternalDBManager

DEFAULT_DATA_PATH = PROJECT_ROOT / "resources" / "bootstrap" / "initial_data.json"


def _load_payload(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Bootstrap data must be a JSON object: {path}")
    return payload


def _is_empty_state(internal_db: InternalDBManager, store: AutomationStore) -> bool:
    return (
        not internal_db.list_schema_lots()
        and not store.list_jobs()
        and not store.list_master_lots()
        and not store.list_lot_routes()
    )


def bootstrap(data_path: Path, *, force: bool = False) -> Dict[str, int | str | bool]:
    payload = _load_payload(data_path)
    internal_db = InternalDBManager()
    store = AutomationStore()

    empty_before = _is_empty_state(internal_db, store)
    if not force and not empty_before:
        return {
            "status": "skipped",
            "reason": "existing_data",
            "empty_before": False,
            "schema_lots": len(internal_db.list_schema_lots()),
            "jobs": len(store.list_jobs()),
            "master_lots": len(store.list_master_lots()),
            "lot_routes": len(store.list_lot_routes()),
        }

    schema_lots = payload.get("schema_lots") or []
    master_lots = payload.get("master_lots") or []
    delivery_config = payload.get("delivery_config") or {}
    delivery_routes = payload.get("delivery_routes") or {}
    delivery_templates = payload.get("delivery_templates") or []
    jobs = payload.get("jobs") or []

    if schema_lots:
        internal_db.upsert_schema_lots(schema_lots)
    if delivery_config:
        safe_delivery_config = {
            key: value
            for key, value in delivery_config.items()
            if key not in {"smtp_password"}
        }
        safe_delivery_config["smtp_password"] = ""
        store.update_delivery_config(safe_delivery_config)
    if master_lots:
        store.upsert_master_lots(
            master_lots,
            actor="bootstrap",
            reason=f"Initial data from {data_path.name}",
        )
    if delivery_routes:
        store.update_delivery_routes(delivery_routes)
    if delivery_templates:
        store.upsert_delivery_templates(
            delivery_templates,
            actor="bootstrap",
            reason=f"Initial data from {data_path.name}",
        )
    for job in jobs:
        store.create_job(job)

    return {
        "status": "loaded",
        "empty_before": empty_before,
        "schema_lots": len(internal_db.list_schema_lots()),
        "jobs": len(store.list_jobs()),
        "master_lots": len(store.list_master_lots()),
        "lot_routes": len(store.list_lot_routes()),
        "data_path": str(data_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Load starter data into empty local SQLite stores.")
    parser.add_argument(
        "--data",
        default=os.environ.get("BOOTSTRAP_DATA_PATH") or str(DEFAULT_DATA_PATH),
        help="Path to the bootstrap JSON file.",
    )
    parser.add_argument("--force", action="store_true", help="Load data even when local stores already contain data.")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = PROJECT_ROOT / data_path
    if not data_path.exists():
        print(json.dumps({"status": "skipped", "reason": "missing_data_file", "data_path": str(data_path)}))
        return 0

    result = bootstrap(data_path, force=args.force)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
