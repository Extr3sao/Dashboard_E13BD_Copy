
import sys
import os

# Afegim el directori src al path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from api.post_crq_lot_status import normalize_distribution_job_config, build_post_crq_lot_execution_matrix

def test_normalization():
    print("Testing normalization...")
    # Simulem el que enviaria el frontend
    raw_config = {
        "lot_scope": {
            "mode": "selected",
            "selected_lots": [
                {
                    "code": "AM05",
                    "emails": [
                        {"email": "user1@example.com", "enabled": True},
                        {"email": "user2@example.com", "enabled": False}
                    ]
                },
                "BQ22" # Compatibilitat amb format antic (string)
            ]
        }
    }
    
    normalized = normalize_distribution_job_config(raw_config)
    lots = normalized.get('lot_scope', {}).get('selected_lots', [])
    
    assert len(lots) == 2
    assert lots[0]['code'] == 'AM05'
    assert len(lots[0]['emails']) == 2
    assert lots[1]['code'] == 'BQ22'
    print("Normalization test PASSED")

def test_execution_matrix():
    print("Testing execution matrix...")
    
    # Mock report_data buit
    report_data = {
        "context": {"schemas": []},
        "results_by_check": [],
        "report_model": {"lot_summary": []}
    }
    
    # Config del Job amb mode "selected"
    job_config = {
        "lot_scope": {
            "mode": "selected",
            "selected_lots": [
                {
                    "code": "AM05",
                    "emails": [
                        {"email": "job_user@example.com", "enabled": True},
                        {"email": "inactive@example.com", "enabled": False}
                    ]
                }
            ]
        }
    }
    
    # Rutes globals
    delivery_routes = {
        "providers": [
            {"provider_code": "AM05", "emails": ["global_user@example.com"], "enabled": True},
            {"provider_code": "BQ22", "emails": ["bq_user@example.com"], "enabled": True}
        ]
    }
    
    # Cas 1: El lot està en el job (mode "selected"), hauria d'usar només el correu ACTIU del job
    matrix_res = build_post_crq_lot_execution_matrix(
        report_data, 
        job_config=job_config, 
        delivery_routes=delivery_routes
    )
    
    rows = {item['lot']: item for item in matrix_res['items']}
    am05_row = rows.get("AM05")
    assert am05_row is not None
    assert "job_user@example.com" in am05_row["route_emails"]
    assert "inactive@example.com" not in am05_row["route_emails"]
    assert "global_user@example.com" not in am05_row["route_emails"]
    
    # BQ22 NO hauria de sortir perquè no està a 'selected_lots'
    assert "BQ22" not in rows
    
    # Cas 2: Mode "all". BQ22 hauria de sortir amb rutes globals.
    job_config["lot_scope"]["mode"] = "all"
    matrix_res_2 = build_post_crq_lot_execution_matrix(
        report_data, 
        job_config=job_config, 
        delivery_routes=delivery_routes
    )
    rows_2 = {item['lot']: item for item in matrix_res_2['items']}
    assert "BQ22" in rows_2
    assert "bq_user@example.com" in rows_2["BQ22"]["route_emails"]
    
    # Fins i tot en mode "all", si el lot AM05 està a 'selected_lots', hauria de seguir usant la config del job
    # (això és degut a com hem implementat la prioritat a post_crq_lot_status.py:268)
    assert "job_user@example.com" in rows_2["AM05"]["route_emails"]
    assert "global_user@example.com" not in rows_2["AM05"]["route_emails"]
    
    print("Execution matrix test PASSED")

if __name__ == "__main__":
    try:
        test_normalization()
        test_execution_matrix()
        print("\nALL TESTS PASSED SUCCESSFULLY")
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
