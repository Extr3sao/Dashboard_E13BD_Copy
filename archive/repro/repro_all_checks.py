
import os
import json
from unittest.mock import MagicMock
from src.api.post_crq_audit import run_post_crq_audit, parse_post_crq_checks

def test_run_all_checks_repro():
    # Mock DB Manager
    db_mock = MagicMock()
    # Simulate some rows for each query
    def mock_execute(sql, binds=None):
        return [
            ('SCHEMA_A', 'OBJ_1', 'TABLE', '2024-03-12 10:00', 'Incidència', 'CRITIC')
        ], ['ESQUEMA', 'OBJECTE', 'TIPUS', 'DATA_MODIFICACIO', 'RECOMANACIO', 'SEVERITAT']
    
    db_mock.execute_query.side_effect = mock_execute
    db_mock.config = {"user": "test"}
    
    # Path to real markdown file
    md_path = os.path.join(os.getcwd(), "auditoria_post_crq.md")
    
    # Get all check IDs
    all_checks = [c["check_id"] for c in parse_post_crq_checks(md_path)]
    print(f"Executing {len(all_checks)} checks: {all_checks}")
    
    try:
        # Run audit with ALL checks
        result = run_post_crq_audit(
            db_manager=db_mock,
            selected_checks=all_checks,
            schemas=["SCHEMA_A"],
            time_filter={"mode": "preset", "preset": "last_24h"},
            profile="REPRO_TEST",
            markdown_path=md_path
        )
        print("Success!")
        # print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"FAILED with error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise e

if __name__ == "__main__":
    test_run_all_checks_repro()
