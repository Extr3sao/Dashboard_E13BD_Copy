from __future__ import annotations

from src.core.checks_document_backfill import backfill_check_states_from_documents


def main() -> None:
    stats = backfill_check_states_from_documents()
    print("Backfill completat.")
    print(f"Checks processats: {stats['checks_seen']}")
    print(f"Explicacions marcades com a vigents: {stats['explanations_upserted']}")
    print(f"Files de sync actualitzades: {stats['sync_rows_updated']}")


if __name__ == "__main__":
    main()
