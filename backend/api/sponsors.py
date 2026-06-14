"""Sponsor report and list endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, require_role
from backend.core.sponsor_report import build_sponsor_report, list_sponsors_summary
from backend.db.database import get_db
from backend.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/v1/sponsors", tags=["sponsors"])


@router.get("")
async def list_sponsors(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """List sponsors with summary metrics for dashboard."""
    items = await list_sponsors_summary(db)
    return {"data": items}


@router.get("/{sponsor_id}/report")
async def get_sponsor_report(
    sponsor_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """Comprehensive sponsor engagement report JSON."""
    report = await build_sponsor_report(db, sponsor_id)
    if report is None:
        raise HTTPException(status_code=404, detail={"error": "Sponsor not found", "code": "NOT_FOUND"})
    return {"data": report}


@router.get("/{sponsor_id}/report/pdf")
@limiter.limit("10/minute")
async def get_sponsor_report_pdf(
    request: Request,
    sponsor_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin"])),
):
    """Download sponsor report PDF — wired in pdf_reports module."""
    from backend.core.pdf_reports import generate_sponsor_pdf_response

    return await generate_sponsor_pdf_response(db, sponsor_id)
