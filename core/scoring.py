import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict

class ScoringEngine:
    def __init__(self, config: Dict):
        self.config = config
        self.thresholds = config['obsolescence_thresholds']['scoring']
        self.naming_patterns = config['naming_patterns']

    def calculate_score(self, table_row: pd.Series) -> Dict:
        """
        Calculates a score from 0 to 100 based on multiple signals.
        """
        score = 0
        evidences = []

        # 1. Size Signal
        size_gb = table_row.get('size_gb', 0)
        if size_gb > 1:
            size_score = min(100, size_gb * 10) # Heavy tables increase score
            score += size_score * self.thresholds['size_weight']
            evidences.append(f"Important size: {size_gb:.2f} GB")

        # 2. Last Activity Signal (Proxy for obsolescence)
        # Assuming last_dml/last_access are datetime objects or strings
        # For mock/logic, we'll assume days since last activity
        days_inactive = table_row.get('days_inactive', 0)
        if days_inactive > 180:
            activity_score = min(100, (days_inactive - 180) / 3.65)
            score += activity_score * self.thresholds['last_access_weight']
            evidences.append(f"Inactive for {days_inactive} days")

        # 3. Naming Patterns
        table_name = table_row.get('table_name', '').lower()
        pattern_hit = any(p in table_name for p in self.naming_patterns)
        if pattern_hit:
            score += 100 * self.thresholds['naming_pattern_weight']
            evidences.append("Matches legacy/temp naming patterns")

        # 4. Recommendation Mapping
        rec_thresholds = self.config['obsolescence_thresholds']['recommendation']
        recommendation = "KEEP"
        risk_level = "LOW"

        if score >= rec_thresholds['drop']:
            recommendation = "DROP"
            risk_level = "HIGH"
        elif score >= rec_thresholds['archive']:
            recommendation = "ARCHIVE"
            risk_level = "HIGH"
        elif score >= rec_thresholds['review']:
            recommendation = "REVIEW"
            risk_level = "MEDIUM"
        
        return {
            "score": round(min(100, score), 2),
            "recommendation": recommendation,
            "evidence": "; ".join(evidences),
            "risk_level": risk_level
        }

    def process_inventory(self, df_inventory: pd.DataFrame) -> pd.DataFrame:
        results = []
        for _, row in df_inventory.iterrows():
            scoring_result = self.calculate_score(row)
            results.append({**row.to_dict(), **scoring_result})
        
        return pd.DataFrame(results)
