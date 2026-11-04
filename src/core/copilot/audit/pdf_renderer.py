import html
from typing import cast
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

try:
    import weasyprint  # type: ignore[import-untyped]

    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    logger.warning(
        "WeasyPrint or its dependencies (like pango) not available, PDF rendering will return a dummy string: %s",
        e,
    )
    WEASYPRINT_AVAILABLE = False

from src.core.copilot.api.schemas import AuditReportSummary


def render_report_pdf(
    summary: AuditReportSummary,
    tenant_id: int,
    from_date: datetime,
    to_date: datetime,
) -> bytes:
    """Render a PDF audit report using WeasyPrint."""

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>SanskritiSetu Audit Report</title>
        <style>
            @page {{
                size: A4;
                margin: 2cm;
                @bottom-right {{
                    content: "Page " counter(page) " of " counter(pages);
                }}
            }}
            body {{
                font-family: Arial, sans-serif;
                color: #333;
                line-height: 1.5;
            }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 10px; }}
            h2 {{ color: #34495e; margin-top: 30px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background-color: #f8f9fa; color: #2c3e50; }}
            .metadata {{ background: #ecf0f1; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .metadata p {{ margin: 5px 0; }}
        </style>
    </head>
    <body>
        <h1>SanskritiSetu Audit Report</h1>
        
        <div class="metadata">
            <p><strong>Tenant ID:</strong> {tenant_id}</p>
            <p><strong>Period:</strong> {from_date.date()} to {to_date.date()}</p>
            <p><strong>Generated At:</strong> {datetime.now(timezone.utc).isoformat()}</p>
        </div>

        <h2>Executive Summary</h2>
        <p><strong>Total Decisions:</strong> {summary.total_decisions}</p>
        
        <h2>Verdicts Breakdown</h2>
        <table>
            <thead>
                <tr><th>Verdict</th><th>Count</th></tr>
            </thead>
            <tbody>
                {"".join(f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>" for k, v in summary.by_verdict.items())}
            </tbody>
        </table>

        <h2>Action Types Breakdown</h2>
        <table>
            <thead>
                <tr><th>Action Type</th><th>Count</th></tr>
            </thead>
            <tbody>
                {"".join(f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>" for k, v in summary.by_action_type.items())}
            </tbody>
        </table>

        <h2>Performance Metrics</h2>
        <ul>
            <li><strong>P50 Latency:</strong> {summary.latency_p50_ms:.1f} ms</li>
            <li><strong>P95 Latency:</strong> {summary.latency_p95_ms:.1f} ms</li>
            <li><strong>P99 Latency:</strong> {summary.latency_p99_ms:.1f} ms</li>
        </ul>

        <h2>Compliance Validation</h2>
        <p><strong>Hash Chain Valid:</strong> {"Yes" if summary.hash_chain_valid else "No"}</p>
    </body>
    </html>
    """

    if not WEASYPRINT_AVAILABLE:
        return b"%PDF-1.4\n%Dummy PDF for testing without pango\n%%EOF"

    pdf_bytes = weasyprint.HTML(  # pyright: ignore[reportPossiblyUnboundVariable]
        string=html_content
    ).write_pdf()
    return cast(bytes, pdf_bytes)
