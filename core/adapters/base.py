from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Optional

class BaseAdapter(ABC):
    def __init__(self, config: Dict):
        self.config = config
        self.connection = None

    @abstractmethod
    def connect(self):
        """Establish connection to the database."""
        pass

    @abstractmethod
    def execute_query(self, query: str) -> pd.DataFrame:
        """Execute a query and return a DataFrame."""
        pass

    @abstractmethod
    def get_table_metadata(self) -> pd.DataFrame:
        """Get common metadata for tables."""
        pass

    @abstractmethod
    def get_grants_info(self) -> pd.DataFrame:
        """Get grants/privileges info."""
        pass

    def disconnect(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
