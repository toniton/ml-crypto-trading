from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.agent.runtime_debug.models import (
    IncidentStatus,
)
from src.agent.runtime_debug.service import RuntimeDebugService
from src.core.severity import Severity


class StatusUpdateRequest(BaseModel):
    notes: Optional[str] = Field(default=None, description="Optional operator notes")


def create_runtime_debug_router(debug_service: RuntimeDebugService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/runtime", tags=["runtime-debug"])

    @router.get("/incidents")
    def list_incidents(
            status: Optional[str] = None,
            severity: Optional[str] = None,
            asset: Optional[str] = None,
            exchange: Optional[str] = None,
            limit: int = 50,
            offset: int = 0,
    ):
        status_enum = IncidentStatus(status) if status else None
        sev_enum = Severity.from_value(severity) if severity else None

        incidents = debug_service.list_incidents(
            status=status_enum,
            severity=sev_enum,
            asset=asset,
            exchange=exchange,
            limit=limit,
            offset=offset,
        )
        return {"incidents": [i.to_dict() for i in incidents]}

    @router.get("/incidents/active")
    def list_active_incidents():
        incidents = debug_service.list_active_incidents()
        return {"active_incidents": [i.to_dict() for i in incidents]}

    @router.get("/incidents/{incident_id}")
    def get_incident(incident_id: str):
        incident = debug_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        events = debug_service._toolbox.get_error_events(incident_id)
        data = incident.to_dict()
        data["events"] = [e.to_dict() for e in events]
        return data

    @router.get("/exchange/{exchange}/instruments/{ticker_symbol}")
    def get_exchange_instrument_constraints(exchange: str, ticker_symbol: str):
        return debug_service.get_exchange_constraints(exchange, ticker_symbol)

    @router.post("/incidents/{incident_id}/investigate")
    def investigate_incident(incident_id: str):
        incident = debug_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        result = debug_service.investigate_incident(incident_id)
        updated = debug_service.get_incident(incident_id)
        approval = result.get("approval_request")
        return {
            "incident": updated.to_dict() if updated else None,
            "diagnosis": result.get("diagnosis").to_dict() if result.get("diagnosis") else None,
            "suggestion": result.get("suggestion").to_dict() if result.get("suggestion") else None,
            "approval_request": approval.model_dump(mode="json") if approval is not None else None,
        }

    @router.post("/incidents/{incident_id}/propose-fix")
    def propose_incident_fix(incident_id: str):
        incident = debug_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        constraints = (
            debug_service.get_exchange_constraints(incident.exchange, incident.asset)
            if incident.exchange and incident.asset
            else None
        )
        result = debug_service.investigate_incident(incident_id)
        updated = debug_service.get_incident(incident_id)
        approval = result.get("approval_request")
        return {
            "incident": updated.to_dict() if updated else None,
            "exchange_constraints": constraints,
            "diagnosis": result.get("diagnosis").to_dict() if result.get("diagnosis") else None,
            "suggestion": result.get("suggestion").to_dict() if result.get("suggestion") else None,
            "approval_request": approval.model_dump(mode="json") if approval is not None else None,
        }

    @router.post("/incidents/{incident_id}/acknowledge")
    def acknowledge_incident(incident_id: str, body: Optional[StatusUpdateRequest] = None):
        incident = debug_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        notes = body.notes if body else None
        debug_service.set_incident_status(incident_id, IncidentStatus.ACKNOWLEDGED, notes=notes)
        return {"status": "ok", "incident_id": incident_id, "new_status": IncidentStatus.ACKNOWLEDGED.value}

    @router.post("/incidents/{incident_id}/resolve")
    def resolve_incident(incident_id: str, body: Optional[StatusUpdateRequest] = None):
        incident = debug_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        notes = body.notes if body else None
        debug_service.set_incident_status(incident_id, IncidentStatus.RESOLVED, notes=notes)
        return {"status": "ok", "incident_id": incident_id, "new_status": IncidentStatus.RESOLVED.value}

    @router.post("/incidents/{incident_id}/ignore")
    def ignore_incident(incident_id: str, body: Optional[StatusUpdateRequest] = None):
        incident = debug_service.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
        notes = body.notes if body else None
        debug_service.set_incident_status(incident_id, IncidentStatus.IGNORED, notes=notes)
        return {"status": "ok", "incident_id": incident_id, "new_status": IncidentStatus.IGNORED.value}

    return router
