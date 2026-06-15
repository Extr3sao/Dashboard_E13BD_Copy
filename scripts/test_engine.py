import asyncio
import sys
import os

# Configurar path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.api.audit_engine import AuditEngine

class MockDBM:
    def execute_query(self, query, params=None):
        print(f"Executing: {query[:50]}...")
        # Simulem error de connexió DPY-3015 que retorna None, None
        return None, None

async def test():
    engine = AuditEngine(MockDBM())
    print("Testing DUPLIXTEC...")
    try:
        res = await engine.get_deep_schema_audit("DUPLIXTEC")
        print(f"Resultat: {res['obsolescence_score']}%")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
