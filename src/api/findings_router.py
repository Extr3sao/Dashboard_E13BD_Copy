"""Authenticated HTTP surface for E13DB finding intelligence."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from src.api.finding_engine import FindingStore
from src.api.security import require_csrf, require_user


def create_findings_router(store: FindingStore, session_store: Any, cookie_name: str) -> APIRouter:
    router = APIRouter(prefix="/api/findings", tags=["findings"])
    user = require_user(session_store, cookie_name)
    csrf = require_csrf(session_store, cookie_name)

    @router.get("")
    async def active_findings(
        database: Optional[str] = None, severity: Optional[str] = None, status: Optional[str] = None,
        delta: Optional[str] = None, rule: Optional[str] = None,
        _principal=Depends(user),
    ):
        return {"items": store.list_findings(database=database, severity=severity, status=status, delta=delta, rule=rule)}

    @router.get("/resolved")
    async def resolved_findings(database: Optional[str] = None, _principal=Depends(user)):
        return {"items": store.list_findings(resolved=True, database=database)}

    @router.get("/red-flags")
    async def red_flags(database: Optional[str] = None, priority: Optional[str] = None, _principal=Depends(user)):
        return {"items": store.list_red_flags(database_id=database, priority=priority)}

    @router.get("/needs-attention")
    async def needs_attention(database: Optional[str] = None, priority: Optional[str] = None, _principal=Depends(user)):
        return {"items": store.list_red_flags(database_id=database, priority=priority), "summary": store.summary(database)}

    @router.get("/summary")
    async def audit_summary(database: Optional[str] = None, _principal=Depends(user)):
        return store.summary(database)

    @router.get("/{finding_id}")
    async def finding_detail(finding_id: int, _principal=Depends(user)):
        try:
            return store.get_finding(finding_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Finding not found") from exc

    @router.get("/{finding_id}/history")
    async def finding_history(finding_id: int, _principal=Depends(user)):
        try:
            finding = store.get_finding(finding_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Finding not found") from exc
        return {"items": finding["history"]}

    @router.post("/{finding_id}/acknowledge")
    async def acknowledge(finding_id: int, payload: dict = Body(...), principal=Depends(user), _csrf=Depends(csrf)):
        return _apply_action(store, finding_id, "ACKNOWLEDGED", principal.subject, payload)

    @router.post("/{finding_id}/accept-risk")
    async def accept_risk(finding_id: int, payload: dict = Body(...), principal=Depends(user), _csrf=Depends(csrf)):
        return _apply_action(store, finding_id, "ACCEPTED_RISK", principal.subject, payload)

    @router.post("/{finding_id}/false-positive")
    async def false_positive(finding_id: int, payload: dict = Body(...), principal=Depends(user), _csrf=Depends(csrf)):
        return _apply_action(store, finding_id, "FALSE_POSITIVE", principal.subject, payload)

    return router


def _apply_action(store: FindingStore, finding_id: int, action: str, actor: str, payload: dict) -> dict:
    try:
        return store.action(finding_id, action, actor, str(payload.get("reason") or ""), payload.get("review_date"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Finding not found") from exc
