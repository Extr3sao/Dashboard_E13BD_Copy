import pandas as pd
import psycopg2
from sqlalchemy import create_engine
from core.adapters.base import BaseAdapter
import os

class PostgresAdapter(BaseAdapter):
    def connect(self):
        db_url = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        self.engine = create_engine(db_url)
        self.connection = self.engine.connect()

    def execute_query(self, query: str) -> pd.DataFrame:
        return pd.read_sql(query, self.engine)

    def get_table_metadata(self) -> pd.DataFrame:
        # Standard Postgres metadata query
        query = """
        SELECT 
            schemaname as schema, 
            relname as table_name, 
            'TABLE' as type,
            pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(relname)) / 1024.0 / 1024.0 / 1024.0 as size_gb,
            n_live_tup as row_count,
            last_vacuum as last_access, -- Proxy for last maintenance
            last_analyze as last_dml   -- Proxy for activity
        FROM pg_stat_user_tables
        """
        return self.execute_query(query)

    def get_grants_info(self) -> pd.DataFrame:
        query = """
        SELECT 
            grantee, 
            table_schema as schema, 
            table_name as object_name, 
            privilege_type as privilege
        FROM information_schema.role_table_grants
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        """
        return self.execute_query(query)
