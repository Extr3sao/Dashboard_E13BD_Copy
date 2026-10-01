from fastapi import APIRouter, Depends, HTTPException
from src.api.security import require_user, require_csrf


def create_cpd_router(runtime, sessions, cookie):
    user = require_user(sessions, cookie)
    csrf = require_csrf(sessions, cookie)
    router = APIRouter(prefix="/api/operations", tags=["service-operations"], dependencies=[Depends(user)])

    @router.get("/summary")
    def summary(_=Depends(user)):
        return runtime.summary()

    @router.get("/components")
    def components(_=Depends(user)):
        return runtime.summary().get("components", {})

    @router.get("/scheduler")
    def scheduler(_=Depends(user)):
        return runtime.summary().get("scheduler", {})

    @router.get("/storage")
    def storage(_=Depends(user)):
        return {"items": runtime.summary().get("storage", []), "integrity": runtime.last_integrity}

    @router.get("/backups")
    def backups(_=Depends(user)):
        return {"items": runtime.backups(), "next_scheduled_backup": runtime.summary().get("next_scheduled_backup")}

    @router.get("/timeline")
    def timeline(_=Depends(user)):
        return {"items": runtime.timeline()}

    @router.get("/retention/preview")
    def preview(_=Depends(user)):
        return runtime.retention()

    def action(call):
        try:
            return call()
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from None
        except Exception:
            raise HTTPException(503, detail="Operational action failed. Verify storage availability, disk space and service account permissions.") from None

    @router.post("/health-check")
    def health_check(_=Depends(csrf)):
        return action(runtime.refresh)

    @router.post("/integrity-check")
    def integrity(_=Depends(csrf)):
        return action(runtime.integrity)

    @router.post("/backups")
    def backup(_=Depends(csrf)):
        return action(runtime.backup)

    return router
