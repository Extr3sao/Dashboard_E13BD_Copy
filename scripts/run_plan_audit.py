import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

import pandas as pd

# Afegim arrel del projecte al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.api.audit_engine import AuditEngine
from src.core.config_loader import ConfigLoader
from src.core.db_manager import OracleDBManager


def parse_args():
    parser = argparse.ArgumentParser(description="Executa l'auditoria del pla Q01-Q19")
    parser.add_argument("--schemas", required=True, help="Llista d'esquemes separats per coma (ex: MGR_APP,CORE_DB)")
    parser.add_argument("--profile", default=None, help="Perfil Oracle del fitxer de connexions")
    parser.add_argument("--out", default="resources", help="Carpeta de sortida")
    return parser.parse_args()


async def main():
    args = parse_args()
    schemas = [s.strip().upper() for s in args.schemas.split(",") if s.strip()]

    cfg = ConfigLoader()
    profiles = cfg.load_connections()
    selected_profile = args.profile or cfg.get_env_var("DEFAULT_PROFILE")

    dbm = None
    try:
        if selected_profile in profiles:
            dbm = OracleDBManager(profiles[selected_profile])
        else:
            raise ValueError(f"Perfil '{selected_profile}' no trobat")

        engine = AuditEngine(dbm)
        report = await engine.run_plan_audit(schemas)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(args.out, exist_ok=True)
        json_path = os.path.join(args.out, f"audit_plan_{stamp}.json")
        csv_path = os.path.join(args.out, f"audit_plan_summary_{stamp}.csv")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, default=str, indent=2)

        summary_rows = []
        for item in report.get("audits", []):
            summary = item.get("summary") or {}
            summary_rows.append({
                "username": item.get("username"),
                "score": item.get("obsolescence_score"),
                "result": item.get("audit_result"),
                "size_gb": summary.get("SIZE_GB"),
                "inbound_refs": summary.get("INBOUND_REFERENCES"),
                "active_jobs": summary.get("ACTIVE_JOBS"),
                "apex_apps": summary.get("APEX_APPLICATIONS"),
                "enabled_triggers": summary.get("ENABLED_TRIGGERS"),
            })

        pd.DataFrame(summary_rows).to_csv(csv_path, index=False)

        print("Audit completada")
        print(f"JSON: {json_path}")
        print(f"CSV:  {csv_path}")
        print(f"Totals: {report.get('totals')}")
    finally:
        if dbm:
            dbm.close()


if __name__ == "__main__":
    asyncio.run(main())
