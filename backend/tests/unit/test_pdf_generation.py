"""Unit tests for sponsor PDF HTML rendering."""

from __future__ import annotations

from backend.core.pdf_reports import render_sponsor_report_html


def test_html_template_renders(monkeypatch) -> None:
    from backend.core import pdf_reports

    monkeypatch.setattr(pdf_reports, "_svg_bar_chart", lambda _data: "<svg>bar</svg>")
    monkeypatch.setattr(pdf_reports, "_svg_pie", lambda _data, _title: "<svg>pie</svg>")
    report = {
        "sponsor": {"name": "Lovable", "tier": "gold", "logo_url": "/static/sponsors/lovable.png"},
        "metrics": {
            "unique_visitors": 10,
            "avg_dwell_seconds": 120,
            "return_rate_pct": 15.0,
            "peak_hour": "14:00",
        },
        "hourly_traffic": [{"hour": "14:00", "visitors": 5, "entries": 6}],
        "visitor_breakdown": {"by_track": {"ai_ml": 5, "other": 5}, "by_floor": {"ground": 10}},
        "top_visitors": [{"name": "Alex", "visits": 2, "total_dwell_minutes": 10}],
    }
    html = render_sponsor_report_html(report, {"solo": 3, "team": 7})
    assert "Lovable" in html
    assert "Unique Visitors" in html
    assert "Alex" in html


def test_weasyprint_pdf_bytes(monkeypatch) -> None:
    """Verify PDF pipeline returns bytes starting with %PDF."""
    from backend.core import pdf_reports

    monkeypatch.setattr(pdf_reports, "html_to_pdf", lambda _html: b"%PDF-1.4 fake")
    pdf = pdf_reports.html_to_pdf("<html></html>")
    assert pdf.startswith(b"%PDF")
