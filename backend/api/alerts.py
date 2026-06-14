"""Alerts REST endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, require_role
from backend.db.database import get_db
from backend.db.models import Alert
from backend.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/v1", tags=["alerts"])


@router.get("/alerts")
@limiter.limit("30/minute")
async def list_alerts(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
    severity: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """List alerts, most recent first."""
    stmt = select(Alert).order_by(Alert.fired_at.desc()).limit(limit)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if acknowledged is not None:
        stmt = stmt.where(Alert.acknowledged == acknowledged)
    rows = (await db.execute(stmt)).scalars().all()
    data = [
        {
            "id": str(a.id),
            "rule_name": a.rule_name,
            "severity": a.severity,
            "message": a.message,
            "zone": a.zone,
            "floor": a.floor,
            "fired_at": a.fired_at.isoformat(),
            "acknowledged": a.acknowledged,
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        }
        for a in rows
    ]
    return {"data": data}


@router.put("/alerts/{alert_id}/acknowledge")
@limiter.limit("30/minute")
async def acknowledge_alert(
    request: Request,
    alert_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """Mark alert as acknowledged."""
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail={"error": "Alert not found", "code": "NOT_FOUND"})
    alert.acknowledged = True
    alert.acknowledged_by = user.id
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "data": {
            "id": str(alert.id),
            "acknowledged": True,
            "acknowledged_at": alert.acknowledged_at.isoformat(),
        }
    }
