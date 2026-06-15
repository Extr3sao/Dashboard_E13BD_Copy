import pandas as pd
import cx_Oracle
from sqlalchemy import create_engine
from core.adapters.base import BaseAdapter
import os

class OracleAdapter(BaseAdapter):
    def connect(self):
        # Oracle connection string format: oracle+cx_oracle://user:password@host:port/?service_name=service
        db_url = f"oracle+cx_oracle://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/?service_name={os.getenv('DB_SERVICE')}"
        self.engine = create_engine(db_url)
        self.connection = self.engine.connect()

    def execute_query(self, query: str) -> pd.DataFrame:
        return pd.read_sql(query, self.engine)

    def get_table_metadata(self) -> pd.DataFrame:
        # Specialized Oracle metadata query for DBA Auditor role
        query = """
        SELECT 
            owner as schema, 
            table_name, 
            'TABLE' as type,
            num_rows as row_count,
            last_analyzed as last_dml,
            (SELECT SUM(bytes)/1024/1024/1024 FROM dba_segments s WHERE s.owner = t.owner AND s.segment_name = t.table_name) as size_gb
        FROM dba_tables t
        WHERE owner NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP')
        """
        return self.execute_query(query)

    def get_grants_info(self) -> pd.DataFrame:
        query = """
        SELECT 
            grantee, 
            owner as schema, 
            table_name as object_name, 
            privilege
        FROM dba_tab_privs
        WHERE owner NOT IN ('SYS', 'SYSTEM')
        """
        return self.execute_query(query)
