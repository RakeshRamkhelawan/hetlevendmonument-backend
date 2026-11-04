from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.copilot.api.schemas import AuditReportSummary
from src.core.copilot.council.models import CouncilDecisionRow

logger = logging.getLogger(__name__)


async def build_report_summary(
    db: AsyncSession,
    tenant_id: int,
    from_date: datetime,
    to_date: datetime,
) -> AuditReportSummary:
    """Build structured summary for audit report."""
    result = await db.execute(
        select(CouncilDecisionRow)
        .where(
            CouncilDecisionRow.tenant_id == tenant_id,
            CouncilDecisionRow.timestamp >= from_date,
            CouncilDecisionRow.timestamp <= to_date,
        )
        .order_by(CouncilDecisionRow.timestamp.asc())
    )
    rows = result.scalars().all()

    total = len(rows)
    by_verdict: dict[str, int] = {}
    by_action_type: dict[str, int] = {}
    latencies: list[int] = []
    hash_chain_valid = True
    previous_hash: str | None = None

    for row in rows:
        by_verdict[row.verdict] = by_verdict.get(row.verdict, 0) + 1
        by_action_type[row.action_type] = by_action_type.get(row.action_type, 0) + 1
        latencies.append(row.deliberation_ms)
        if previous_hash is not None and row.previous_decision_hash != previous_hash:
            hash_chain_valid = False
        previous_hash = row.decision_hash

    latencies_sorted = sorted(latencies) if latencies else [0]
    p50 = _percentile(latencies_sorted, 0.5)
    p95 = _percentile(latencies_sorted, 0.95)
    p99 = _percentile(latencies_sorted, 0.99)

    return AuditReportSummary(
        total_decisions=total,
        by_verdict=by_verdict,
        by_action_type=by_action_type,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        latency_p99_ms=p99,
        hash_chain_valid=hash_chain_valid,
    )


def _percentile(sorted_values: list[int], q: float) -> float:
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    idx = q * (n - 1)
    lower = int(idx)
    upper = lower + 1
    if upper >= n:
        return float(sorted_values[-1])
    weight = idx - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def render_report_pdf(
    summary: AuditReportSummary,
    tenant_id: int,
    from_date: datetime,
    to_date: datetime,
) -> bytes:
    """Render a PDF audit report using reportlab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import (
            Flowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("reportlab is required for PDF rendering") from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story: list[Flowable] = []

    story.append(Paragraph("SanskritiSetu Audit Report", styles["Title"]))
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            f"Tenant: {tenant_id} | Range: {from_date.date()} to {to_date.date()}",
            styles["Normal"],
        )
    )
    story.append(
        Paragraph(
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"Total decisions: {summary.total_decisions}", styles["Heading2"]))
    story.append(Spacer(1, 6))

    verdict_data = [["Verdict", "Count"]] + [[k, str(v)] for k, v in summary.by_verdict.items()]
    if len(verdict_data) > 1:
        verdict_table = Table(verdict_data)
        verdict_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )
        story.append(verdict_table)
    story.append(Spacer(1, 12))

    story.append(
        Paragraph(
            f"Latency (ms) - P50: {summary.latency_p50_ms:.1f}, "
            f"P95: {summary.latency_p95_ms:.1f}, P99: {summary.latency_p99_ms:.1f}",
            styles["Normal"],
        )
    )
    story.append(
        Paragraph(
            f"Hash chain valid: {'Yes' if summary.hash_chain_valid else 'No'}",
            styles["Normal"],
        )
    )

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


async def render_report_pdf_async(
    summary: AuditReportSummary,
    tenant_id: int,
    from_date: datetime,
    to_date: datetime,
) -> bytes:
    """Async wrapper for PDF rendering to avoid blocking the event loop."""
    return await asyncio.to_thread(render_report_pdf, summary, tenant_id, from_date, to_date)
