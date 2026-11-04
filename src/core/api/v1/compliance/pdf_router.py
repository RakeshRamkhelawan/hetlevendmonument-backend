"""
PDF Compliance Report sub-router (ADR-033 Laag 1).

Routes:
- GET /report/pdf
"""
# orphan:exempt reason: single-responsibility handler, fpdf2 integration requires verbose setup

import time as _time
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from loguru import logger
from opentelemetry import trace

from src.core.api.v1.compliance.dependencies import (
    AuditService,
    ComplianceAggregationService,
    ComplianceScoreCalculator,
    ai_transparency_limit,
    get_aggregation_service,
    get_current_user,
    get_score_service,
)
from src.core.i18n.compliance_pdf import get_labels, parse_lang
from src.core.models.rbac_models import User
from src.core.observability.compliance_metrics import (
    compliance_pdf_exports_total,
    compliance_pdf_generation_duration_seconds,
)
from src.core.utils.best_effort import best_effort

pdf_router = APIRouter()


@pdf_router.get("/report/pdf")
@ai_transparency_limit
async def download_compliance_report(
    request: Request,
    current_user: User = Depends(get_current_user),
    calculator: ComplianceScoreCalculator = Depends(get_score_service),
    agg_svc: ComplianceAggregationService = Depends(get_aggregation_service),
) -> StreamingResponse:
    """Genereer een AI Act compliance rapport als PDF (audit-logged)."""
    tenant_id = current_user.tenant_id
    lang = parse_lang(request.headers.get("accept-language", ""))
    labels = get_labels(lang)

    logger.info(
        "compliance PDF export started",
        tenant_id=tenant_id,
        user_id=current_user.id,
        language=lang,
    )

    with trace.get_tracer(__name__).start_as_current_span("compliance.pdf_export") as span:
        span.set_attribute("tenant_id", tenant_id)
        span.set_attribute("user_id", current_user.id)
        span.set_attribute("language", lang)

        try:
            start_time = _time.perf_counter()

            overall_score = await calculator.calculate_overall_score(tenant_id=tenant_id)

            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            decisions = await agg_svc.get_ai_decisions(tenant_id=tenant_id, since=thirty_days_ago)
            total_decisions = len(decisions)
            high_risk = sum(1 for d in decisions if getattr(d, "risk_level", "") == "high")

            # PDF opbouwen -- fpdf2 2.7.9: geen ln=True, gebruik pdf.ln(h) apart
            pdf = FPDF()

            fonts_dir = Path(__file__).resolve().parents[5] / "assets" / "fonts"
            if not fonts_dir.exists():
                fonts_dir = Path("/app/assets/fonts")

            pdf.add_font("DejaVu", "", str(fonts_dir / "DejaVuSans.ttf"))
            pdf.add_font("DejaVu", "B", str(fonts_dir / "DejaVuSans-Bold.ttf"))

            pdf.set_title(f"{labels['cover_title']} - Tenant {tenant_id}")
            pdf.set_author("SanskritiSetu Compliance Engine")
            pdf.set_creator("SanskritiSetu Enterprise AI Agent OS")
            pdf.set_subject(labels["meta_subject"])
            pdf.set_creation_date(datetime.now(timezone.utc))

            pdf.add_page()
            pdf.set_font("DejaVu", "B", 24)
            pdf.set_y(60)
            pdf.cell(0, 12, labels["cover_title"], align="C")
            pdf.ln(20)

            pdf.set_font("DejaVu", "", 14)
            pdf.cell(0, 10, f"Tenant {tenant_id}", align="C")
            pdf.ln(8)
            generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            pdf.cell(0, 10, labels["generated_at"].format(generated_at), align="C")
            pdf.ln(40)

            pdf.set_font("DejaVu", "B", 18)
            score_pct = (
                f"{overall_score.overall_score * 100:.1f}%" if overall_score is not None else "N/B"
            )
            pdf.cell(0, 12, labels["overall_score"].format(score_pct), align="C")

            per_policy = getattr(overall_score, "per_policy", {}) or {}
            for policy_name, policy_score in sorted(per_policy.items()):
                pdf.add_page()
                pdf.set_font("DejaVu", "B", 18)
                pdf.cell(
                    0, 12, labels["policy_header"].format(policy_name.replace("_", " ").title())
                )
                pdf.ln(15)

                pdf.set_font("DejaVu", "", 12)
                pct = f"{policy_score * 100:.1f}%"
                pdf.cell(0, 8, labels["score"].format(pct))
                pdf.ln(8)
                pdf.cell(0, 8, labels["category"].format(policy_name))
                pdf.ln(8)

                if policy_score >= 0.9:
                    policy_status = labels["status_fully"]
                elif policy_score >= 0.7:
                    policy_status = labels["status_mostly"]
                else:
                    policy_status = labels["status_attention"]
                pdf.cell(0, 8, f"Status: {policy_status}")
                pdf.ln(15)

            pdf.add_page()
            pdf.set_font("DejaVu", "B", 16)
            pdf.cell(0, 12, labels["decisions_header"])
            pdf.ln(15)
            pdf.set_font("DejaVu", "", 12)
            pdf.cell(0, 8, labels["total_decisions"].format(total_decisions))
            pdf.ln(8)
            pdf.cell(0, 8, labels["high_risk_decisions"].format(high_risk))
            pdf.ln(8)

            # pdf.output() retourneert bytearray in fpdf2 2.7.9 -- bytes() cast is correct
            # GEEN dest="S" -- dat is de oude fpdf v1 API
            buffer = BytesIO(bytes(pdf.output()))
            buffer.seek(0)

            duration = _time.perf_counter() - start_time
            compliance_pdf_generation_duration_seconds.labels(
                tenant_id=str(tenant_id), language=lang
            ).observe(duration)

            span.set_attribute("score_value", overall_score.overall_score if overall_score else 0.0)
            span.set_attribute("decisions_count", total_decisions)
            span.set_attribute("high_risk_count", high_risk)

            compliance_pdf_exports_total.labels(
                tenant_id=str(tenant_id), language=lang, status="success"
            ).inc()

        except Exception as exc:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            compliance_pdf_exports_total.labels(
                tenant_id=str(tenant_id), language=lang, status="error"
            ).inc()
            logger.error(
                "compliance PDF export failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                tenant_id=tenant_id,
            )
            raise HTTPException(status_code=500, detail="Internal error") from exc

    # Audit log -- never block the primary response
    async with best_effort("compliance pdf export audit log", db_session=agg_svc.db_session):
        client_ip = request.client.host if request.client else "unknown"
        await AuditService.log_action(
            tenant_id=tenant_id,
            action="compliance_pdf_export",
            resource="compliance_report",
            user_id=current_user.id,
            details={
                "overall_score": overall_score.overall_score if overall_score else None,
                "decisions_count": total_decisions,
                "high_risk_count": high_risk,
                "language": lang,
                "user_agent": request.headers.get("user-agent", "unknown"),
            },
            session=agg_svc.db_session,
            event_type="DATA_EXPORT",
            threat_level="INFO",
            client_ip=client_ip,
            endpoint="/api/v1/compliance/report/pdf",
            description=f"PDF compliance report generated for tenant {tenant_id}",
        )
        await agg_svc.db_session.flush()

    filename = f"ai-act-compliance-{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
