"""Prometheus metrics for compliance PDF exports."""

from __future__ import annotations

from src.core.observability.metrics import _get_or_create_counter, _get_or_create_histogram

compliance_pdf_exports_total = _get_or_create_counter(
    "compliance_pdf_exports_total",
    "Number of compliance PDF exports per tenant, language and status",
    ["tenant_id", "language", "status"],
)

compliance_pdf_generation_duration_seconds = _get_or_create_histogram(
    "compliance_pdf_generation_duration_seconds",
    "Time to generate compliance PDF (from score calculation to bytes ready)",
    ["tenant_id", "language"],
)
