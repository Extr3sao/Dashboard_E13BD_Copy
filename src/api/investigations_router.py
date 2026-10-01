"""Authenticated APIs for deterministic DBA investigation cases."""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from src.api.security import require_csrf, require_user


def create_investigations_router(store, sessions, cookie):
    user = require_user(sessions, cookie)
    csrf = require_csrf(sessions, cookie)
    router = APIRouter(prefix="/api/investigations", tags=["investigations"], dependencies=[Depends(user)])

    def invoke(call):
        try:
            return call()
        except KeyError:
            raise HTTPException(404, detail="Investigation or related record not found") from None
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from None

    @router.get("")
    def investigations(database: str | None = None, status: str | None = None, rule: str | None = None,
                       category: str | None = None, object_name: str | None = None, cause: str | None = None,
                       opened_from: float | None = None, opened_to: float | None = None,
                       limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return invoke(lambda: store.list(database_id=database, status=status, rule=rule, category=category, object_name=object_name, cause=cause, opened_from=opened_from, opened_to=opened_to, limit=limit, offset=offset))

    @router.get("/capabilities")
    def capabilities():
        return store.capabilities_status()

    @router.get("/rule-relationships")
    def rule_relationships():
        return {"items": store.rule_relationships()}

    @router.post("/rule-relationships")
    def declare_relationship(payload: dict = Body(...), _principal=Depends(user), _csrf=Depends(csrf)):
        return invoke(lambda: (store.declare_rule_relationship(payload.get("source_category"), payload.get("target_category"), payload.get("reason"), source_rule=payload.get("source_rule") or "", target_rule=payload.get("target_rule") or "") or {"status": "saved"}))

    @router.get("/resolved")
    def resolved(database: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        first = store.list(database_id=database, status="RESOLVED", limit=limit, offset=offset)
        second = store.list(database_id=database, status="CLOSED", limit=limit, offset=offset)
        items = sorted(first["items"] + second["items"], key=lambda item: item["updated_at"], reverse=True)[:limit]
        return {"items": items, "total": first["total"] + second["total"], "limit": limit, "offset": offset}

    @router.post("", status_code=201)
    def open_case(payload: dict = Body(...), principal=Depends(user), _csrf=Depends(csrf)):
        if not payload.get("database_id") or not payload.get("finding_id"):
            raise HTTPException(400, detail="database_id and finding_id are required")
        return invoke(lambda: store.open_manual(str(payload["database_id"]), int(payload["finding_id"]), principal.subject))

    @router.get("/{investigation_id}")
    def detail(investigation_id: int):
        return invoke(lambda: store.get(investigation_id))

    @router.get("/{investigation_id}/timeline")
    def timeline(investigation_id: int):
        return invoke(lambda: {"items": store.timeline(investigation_id)})

    @router.get("/{investigation_id}/evidence")
    def evidence(investigation_id: int):
        return invoke(lambda: {"items": store.evidence(investigation_id)})

    @router.get("/{investigation_id}/related-findings")
    def related(investigation_id: int):
        return invoke(lambda: {"items": store.correlations(investigation_id)})

    @router.get("/{investigation_id}/hypotheses")
    def hypotheses(investigation_id: int):
        return invoke(lambda: {"items": store.hypotheses(investigation_id)})

    @router.get("/{investigation_id}/recommended-checks")
    def recommended_checks(investigation_id: int):
        return invoke(lambda: {"items": store.checks(investigation_id)})

    @router.get("/{investigation_id}/lock-chain")
    def lock_chain(investigation_id: int):
        return invoke(lambda: {"items": store.lock_chain(investigation_id)})

    @router.get("/{investigation_id}/capacity-projection/{evidence_id}")
    def capacity_projection(investigation_id: int, evidence_id: int):
        return invoke(lambda: store.capacity_projection(investigation_id, evidence_id))

    @router.post("/{investigation_id}/status")
    def set_status(investigation_id: int, payload: dict = Body(...), principal=Depends(user), _csrf=Depends(csrf)):
        return invoke(lambda: store.set_status(investigation_id, str(payload.get("status") or ""), actor=principal.subject))

    @router.post("/{investigation_id}/cause")
    def confirm_cause(investigation_id: int, payload: dict = Body(...), principal=Depends(user), _csrf=Depends(csrf)):
        return invoke(lambda: store.confirm_cause(investigation_id, actor=principal.subject, description=str(payload.get("description") or ""), evidence=payload.get("evidence")))

    @router.post("/{investigation_id}/resolution")
    def resolution(investigation_id: int, payload: dict = Body(...), principal=Depends(user), _csrf=Depends(csrf)):
        return invoke(lambda: store.record_resolution(investigation_id, actor=principal.subject, resolution=str(payload.get("resolution") or ""), actions_taken=str(payload.get("actions_taken") or "")))

    @router.post("/{investigation_id}/hypotheses/{hypothesis_id}")
    def hypothesis_status(investigation_id: int, hypothesis_id: int, payload: dict = Body(...), principal=Depends(user), _csrf=Depends(csrf)):
        return invoke(lambda: store.update_hypothesis(investigation_id, hypothesis_id, actor=principal.subject, status=str(payload.get("status") or "")))

    @router.post("/{investigation_id}/checks/{check_id}")
    def check_status(investigation_id: int, check_id: int, payload: dict = Body(...), principal=Depends(user), _csrf=Depends(csrf)):
        return invoke(lambda: store.update_check(investigation_id, check_id, actor=principal.subject, status=str(payload.get("status") or ""), result_summary=str(payload.get("result_summary") or "")))

    return router
