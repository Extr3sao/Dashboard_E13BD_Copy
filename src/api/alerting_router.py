from fastapi import APIRouter, Body, Depends, HTTPException, Query
from src.api.security import require_csrf, require_user

def create_alerting_router(service, sessions, cookie):
    router=APIRouter(prefix="/api/alerting", tags=["alerting"]); user=require_user(sessions,cookie); csrf=require_csrf(sessions,cookie)
    @router.get("/alerts")
    async def alerts(status: str|None=None, priority: str|None=None, database: str|None=None, limit:int=100, _=Depends(user)): return {"items":service.list_alerts(status=status,priority=priority,database=database,limit=limit)}
    @router.get("/alerts/{alert_id}")
    async def alert(alert_id:int,_=Depends(user)):
        try:return service.alert(alert_id)
        except KeyError: raise HTTPException(404,"Alert not found")
    @router.post("/alerts/{alert_id}/{action}")
    async def action(alert_id:int,action:str,payload:dict=Body(...),principal=Depends(user),_=Depends(csrf)):
        try:return service.action(alert_id,action.upper(),principal.subject,payload.get("reason", ""))
        except KeyError: raise HTTPException(404,"Alert not found")
        except ValueError as exc: raise HTTPException(400,str(exc))
    @router.get("/notification-health")
    async def health(_=Depends(user)): return service.notification_health()
    @router.post("/maintenance")
    async def maintenance(payload:dict=Body(...),principal=Depends(user),_=Depends(csrf)):
        try:return service.add_maintenance(payload["database_id"],float(payload["starts_at"]),float(payload["ends_at"]),str(payload.get("reason") or ""),principal.subject)
        except (KeyError,ValueError) as exc: raise HTTPException(400,str(exc))
    @router.get("/reports")
    async def reports(limit:int=50,_=Depends(user)): return {"items":service.list_reports(limit)}
    @router.post("/reports/{report_type}")
    async def generate(report_type:str,_=Depends(user)):
        if report_type not in {"daily","weekly"}: raise HTTPException(400,"Unknown report type")
        return service.generate_report(report_type)
    @router.get("/reports/{report_id}")
    async def report(report_id:int,_=Depends(user)):
        try:return service.report(report_id)
        except KeyError: raise HTTPException(404,"Report not found")
    @router.post("/reports/{report_id}/deliver")
    async def deliver_report(report_id:int,_=Depends(user),__=Depends(csrf)):
        try:return service.deliver_report(report_id)
        except KeyError: raise HTTPException(404,"Report not found")
    return router
