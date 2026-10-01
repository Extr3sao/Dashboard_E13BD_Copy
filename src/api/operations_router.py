from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from src.api.finding_engine import FindingStore
from src.api.security import require_user

def create_operations_router(store: FindingStore, sessions: Any, cookie: str) -> APIRouter:
    router = APIRouter(prefix="/api/operations", tags=["operations"])
    user = require_user(sessions, cookie)
    @router.get("/fleet")
    async def fleet(_=Depends(user)): return store.fleet()
    @router.get("/targets/{database_id}")
    async def target(database_id: str, _=Depends(user)):
        health = store.health(database_id)
        return {"health": health, "findings": store.list_findings(database=database_id), "red_flags": store.list_red_flags(database_id=database_id), "history": store.audit_history(database_id), "trends": store.trends(database_id)}
    @router.get("/trends")
    async def trends(hours: int = 168, database: Optional[str] = None, _=Depends(user)): return {"items": store.trends(database, hours)}
    @router.get("/audits")
    async def audits(database: Optional[str] = None, limit: int = 50, _=Depends(user)): return {"items": store.audit_history(database, limit)}
    return router
