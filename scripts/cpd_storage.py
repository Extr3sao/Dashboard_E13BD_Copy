"""Offline restore preparation and bounded retention CLI."""
import argparse
import json
import sqlite3
import time

from src.api.cpd_operations import OperationsConfig, OperationsRuntime, prepare_restore, validate_backup
from src.core.internal_db import InternalDBManager
from src.core.automation_store import AutomationStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "restore"):
        command = sub.add_parser(name)
        command.add_argument("--backup-root", required=True)
        command.add_argument("--backup-id", required=True)
        command.add_argument("--checksum", required=True, help="Manifest checksum recorded by backup creation")
        if name == "restore":
            command.add_argument("--destination", required=True, help="New offline restore directory")
            command.add_argument("--confirm-service-stopped", action="store_true", required=True)
    command = sub.add_parser("purge")
    command.add_argument("--internal", required=True)
    command.add_argument("--automation", required=True)
    command.add_argument("--execute", action="store_true")
    command.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    if args.command == "validate":
        validate_backup(args.backup_root, args.backup_id, args.checksum)
        result = {"status": "VALIDATED", "backup_id": args.backup_id}
    elif args.command == "restore":
        result = prepare_restore(args.backup_root, args.backup_id, args.destination, args.checksum)
    else:
        # Refuse destructive CLI work while the service still owns storage.
        with sqlite3.connect(args.internal) as conn:
            if args.execute and conn.execute("SELECT 1 FROM operations_lease WHERE expires_at>?", (time.time(),)).fetchone():
                parser.error("Stop the service before executing offline retention")
        runtime = OperationsRuntime(InternalDBManager(args.internal), AutomationStore(args.automation), None, None, OperationsConfig())
        result = runtime.retention(execute=args.execute, limit=args.limit)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
