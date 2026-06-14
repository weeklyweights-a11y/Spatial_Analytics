"""Sponsor PDF generation with WeasyPrint and matplotlib."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.responses import StreamingResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.core.sponsor_report import build_sponsor_report, build_team_size_breakdown_for_pdf

matplotlib = None
plt = None


def _ensure_matplotlib() -> None:
    global matplotlib, plt
    if matplotlib is None:
        import matplotlib as mpl

        mpl.use("Agg")
        import matplotlib.pyplot as pyplot

        matplotlib = mpl
        plt = pyplot


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "sponsor"


def _svg_bar_chart(hourly_traffic: list[dict[str, Any]]) -> str:
    _ensure_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 3))
    hours = [h.get("hour", "") for h in hourly_traffic] or ["00:00"]
    visitors = [h.get("visitors", 0) for h in hourly_traffic] or [0]
    ax.bar(hours, visitors, color="#3b82f6")
    ax.set_ylabel("Visitors")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue().decode("utf-8")


def _svg_pie(data: dict[str, int], title: str) -> str:
    _ensure_matplotlib()
    fig, ax = plt.subplots(figsize=(3.5, 3.5))
    if not data:
        data = {"none": 1}
    labels = list(data.keys())
    values = list(data.values())
    ax.pie(values, labels=labels, autopct="%1.0f%%", startangle=90)
    ax.set_title(title)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue().decode("utf-8")


def render_sponsor_report_html(report: dict[str, Any], team_size: dict[str, int]) -> str:
    """Render Jinja2 HTML for WeasyPrint."""
    settings = get_settings()
    templates_dir = Path(__file__).resolve().parents[1] / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("sponsor_report.html")
    metrics = report.get("metrics", {})
    breakdown = report.get("visitor_breakdown", {})
    return template.render(
        event_name=settings.EVENT_NAME,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        sponsor=report.get("sponsor", {}),
        metrics=metrics,
        hourly_traffic=report.get("hourly_traffic", []),
        traffic_chart_svg=_svg_bar_chart(report.get("hourly_traffic", [])),
        track_pie_svg=_svg_pie(breakdown.get("by_track", {}), "By Track"),
        team_pie_svg=_svg_pie(team_size, "By Team Size"),
        top_visitors=report.get("top_visitors", []),
        logo_path=str(Path(__file__).resolve().parents[1] / "static" / "spatialscore_logo.png"),
    )


def html_to_pdf(html: str) -> bytes:
    """Convert HTML string to PDF bytes via WeasyPrint."""
    from weasyprint import HTML

    return HTML(string=html).write_pdf()


async def generate_sponsor_pdf_response(db: AsyncSession, sponsor_id: UUID) -> StreamingResponse:
    """Build PDF StreamingResponse for sponsor report endpoint."""
    report = await build_sponsor_report(db, sponsor_id)
    if report is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"error": "Sponsor not found", "code": "NOT_FOUND"})

    team_size = await build_team_size_breakdown_for_pdf(db, sponsor_id)
    html = render_sponsor_report_html(report, team_size)
    try:
        pdf_bytes = html_to_pdf(html)
    except Exception as exc:
        sponsor_name = report.get("sponsor", {}).get("name", str(sponsor_id))
        logger.error(f"Sponsor PDF generation failed: sponsor={sponsor_name}, error={exc}")
        from fastapi import HTTPException

        raise HTTPException(
            status_code=500,
            detail={"error": "PDF generation failed", "code": "PDF_ERROR"},
        ) from exc

    sponsor_name = report.get("sponsor", {}).get("name", "sponsor")
    slug = _slugify(sponsor_name)
    size_kb = len(pdf_bytes) / 1024
    logger.info(f"Sponsor PDF generated: sponsor={sponsor_name}, pages=1, size={size_kb:.0f}KB")

    filename = f"spatialscore_{slug}_report.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
