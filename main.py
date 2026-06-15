import os
import yaml
import argparse
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd

from core.parser import FileParser
from core.adapters.postgres import PostgresAdapter
from core.scoring import ScoringEngine
from utils.report_gen import ReportGenerator
from utils.logger import setup_logger

def main():
    load_dotenv()
    
    # 1. Load Config
    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    logger = setup_logger(config['paths']['logs'])
    logger.info("Iniciant procés de neteja de BBDD")

    # 2. Setup DB Adapter
    # For this demo, we assume Postgres. In real use, would switch based on config['database']['type']
    adapter = PostgresAdapter(config)
    
    try:
        # adapter.connect() # Uncomment when credentials are ready
        logger.info("Connectat a la base de dades")

        # 3. Read Queries (Mocking behavior since files are not yet provided)
        # parser = FileParser()
        # queries_metrics = parser.parse_sql_file("data/inputs/queries_metrics.txt")
        # queries_grants = parser.parse_sql_file("data/inputs/queries_grants.txt")

        # 4. Mock Data Generation for Demo/Skeleton
        # In real execution, these would come from adapter.get_table_metadata()
        mock_data = {
            "schema": ["public", "public", "legacy", "temp_schema"],
            "table_name": ["users", "orders", "old_logs_2019", "tmp_data_test"],
            "size_gb": [0.5, 1.2, 5.5, 0.1],
            "days_inactive": [10, 5, 500, 20],
        }
        df_inventory = pd.DataFrame(mock_data)

        # 5. Scoring
        engine = ScoringEngine(config)
        df_backlog = engine.process_inventory(df_inventory)
        logger.info("Scoring completat")

        # 6. Save Snapshot
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        snapshot_path = os.path.join(config['paths']['snapshots'], f"snapshot_{ts}.parquet")
        df_backlog.to_parquet(snapshot_path)
        logger.info(f"Snapshot guardat a {snapshot_path}")

        # 7. Generate Report
        repo_gen = ReportGenerator(config['paths']['reports'])
        report_path = repo_gen.generate_html(df_backlog)
        print(f"Informe generat: {report_path}")

    except Exception as e:
        logger.error(f"Error en l'execució: {str(e)}")
    finally:
        # adapter.disconnect()
        pass

if __name__ == "__main__":
    main()
