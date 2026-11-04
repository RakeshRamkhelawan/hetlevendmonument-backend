"""
Golden Demo Capability Contracts

Capabilities voor D1, D2, en D3 demo templates.
Alle capabilities zijn no-cost (geen betaalde API's).
"""

from typing import Dict, List

from src.core.contracts import (
    AuditPolicy,
    CapabilityContract,
    CapabilityRegistry,
    FallbackPolicy,
    RetryPolicy,
)

# ============================================================================
# D1: Intake -> Offerte -> Review (Sales)
# ============================================================================

D1_CAPABILITIES: dict[str, CapabilityContract] = {
    "d1_intake_lead": CapabilityContract(
        capability_key="d1_intake_lead",
        input_schema={
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "contact_name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
                "phone": {"type": ["string", "null"]},
                "requirements": {"type": "string"},
                "budget_indication": {"type": ["number", "null"]},
                "timeline": {"type": "string"},
            },
            "required": ["company_name", "contact_name", "email", "requirements"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "intake_date": {"type": "string", "format": "date-time"},
                "status": {"type": "string", "enum": ["new", "qualified", "rejected"]},
            },
        },
        retry_policy=RetryPolicy(max_retries=2),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=365),
    ),
    "d1_generate_quote": CapabilityContract(
        capability_key="d1_generate_quote",
        input_schema={
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                        },
                        "required": ["description", "quantity", "unit_price"],
                    },
                },
                "discount_percentage": {"type": "number", "minimum": 0, "maximum": 50},
                "validity_days": {"type": "number", "default": 30},
            },
            "required": ["lead_id", "line_items"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "quote_id": {"type": "string"},
                "quote_number": {"type": "string"},
                "total_amount": {"type": "number"},
                "valid_until": {"type": "string", "format": "date"},
                "status": {
                    "type": "string",
                    "enum": ["draft", "pending_approval", "approved", "rejected"],
                },
            },
        },
        retry_policy=RetryPolicy(max_retries=1),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=365),
    ),
    "d1_review_quote": CapabilityContract(
        capability_key="d1_review_quote",
        input_schema={
            "type": "object",
            "properties": {
                "quote_id": {"type": "string"},
                "reviewer_id": {"type": "string"},
                "decision": {"type": "string", "enum": ["approve", "reject", "request_revision"]},
                "comments": {"type": "string"},
            },
            "required": ["quote_id", "reviewer_id", "decision"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "review_id": {"type": "string"},
                "quote_id": {"type": "string"},
                "decision": {"type": "string"},
                "reviewed_at": {"type": "string", "format": "date-time"},
            },
        },
        retry_policy=RetryPolicy(max_retries=0),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=365),  # 7 jaar
    ),
    "d1_notify_customer": CapabilityContract(
        capability_key="d1_notify_customer",
        input_schema={
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "quote_id": {"type": "string"},
                "channel": {"type": "string", "enum": ["email", "sms", "internal"]},
                "template": {"type": "string"},
            },
            "required": ["lead_id", "quote_id", "channel"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "notification_id": {"type": "string"},
                "sent_at": {"type": "string", "format": "date-time"},
                "status": {"type": "string", "enum": ["sent", "failed", "pending"]},
            },
        },
        retry_policy=RetryPolicy(max_retries=3, retry_on=["timeout", "rate_limit"]),
        fallback_policy=FallbackPolicy(fallback_capability="d1_notify_customer_internal"),
        audit_policy=AuditPolicy(log_input=True, log_output=False, retention_days=90),
    ),
}


# ============================================================================
# D2: Order -> Fulfilment simulatie (Operations)
# ============================================================================

D2_CAPABILITIES: dict[str, CapabilityContract] = {
    "d2_ingest_orders": CapabilityContract(
        capability_key="d2_ingest_orders",
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["csv", "json", "manual"]},
                "data": {"type": "array"},
                "batch_id": {"type": "string"},
            },
            "required": ["source", "data"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "orders_processed": {"type": "number"},
                "orders_failed": {"type": "number"},
                "errors": {"type": "array"},
            },
        },
        retry_policy=RetryPolicy(max_retries=1),
        audit_policy=AuditPolicy(log_input=False, log_output=True, retention_days=365),
    ),
    "d2_generate_picking_list": CapabilityContract(
        capability_key="d2_generate_picking_list",
        input_schema={
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "warehouse_zone": {"type": "string"},
                "priority": {"type": "string", "enum": ["high", "normal", "low"]},
            },
            "required": ["batch_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "picking_list_id": {"type": "string"},
                "items": {"type": "array"},
                "total_items": {"type": "number"},
                "estimated_time_minutes": {"type": "number"},
            },
        },
        retry_policy=RetryPolicy(max_retries=2),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=180),
    ),
    "d2_simulate_fulfilment": CapabilityContract(
        capability_key="d2_simulate_fulfilment",
        input_schema={
            "type": "object",
            "properties": {
                "picking_list_id": {"type": "string"},
                "simulation_speed": {"type": "string", "enum": ["realtime", "fast"]},
                "failure_scenario": {
                    "type": "string",
                    "enum": ["none", "stock_mismatch", "system_error"],
                },
            },
            "required": ["picking_list_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "simulation_id": {"type": "string"},
                "status": {"type": "string", "enum": ["completed", "failed", "in_progress"]},
                "events": {"type": "array"},
                "duration_seconds": {"type": "number"},
            },
        },
        retry_policy=RetryPolicy(max_retries=0),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=90),
    ),
    "d2_update_stakeholders": CapabilityContract(
        capability_key="d2_update_stakeholders",
        input_schema={
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "update_type": {"type": "string", "enum": ["team", "customer", "both"]},
                "status": {"type": "string"},
            },
            "required": ["batch_id", "update_type"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "updates_sent": {"type": "number"},
                "failed_deliveries": {"type": "number"},
            },
        },
        retry_policy=RetryPolicy(max_retries=3),
        fallback_policy=FallbackPolicy(fallback_capability="d2_log_update_failure"),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=180),
    ),
}


# ============================================================================
# D3: Factuurcontrole -> Approval (Finance)
# ============================================================================

D3_CAPABILITIES: dict[str, CapabilityContract] = {
    "d3_ingest_invoices": CapabilityContract(
        capability_key="d3_ingest_invoices",
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["csv", "xml", "pdf_extract", "manual"]},
                "invoices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "invoice_number": {"type": "string"},
                            "vendor": {"type": "string"},
                            "amount": {"type": "number"},
                            "due_date": {"type": "string"},
                            "purchase_order": {"type": ["string", "null"]},
                        },
                        "required": ["invoice_number", "vendor", "amount"],
                    },
                },
            },
            "required": ["source", "invoices"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "processed": {"type": "number"},
                "failed": {"type": "number"},
                "total_amount": {"type": "number"},
            },
        },
        retry_policy=RetryPolicy(max_retries=1),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=365),  # 7 jaar
    ),
    "d3_detect_deviations": CapabilityContract(
        capability_key="d3_detect_deviations",
        input_schema={
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "tolerance_percentage": {"type": "number", "default": 5},
                "check_po_match": {"type": "boolean", "default": True},
            },
            "required": ["batch_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "check_id": {"type": "string"},
                "deviations_found": {"type": "number"},
                "deviations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "invoice_number": {"type": "string"},
                            "deviation_type": {"type": "string"},
                            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        },
                    },
                },
            },
        },
        retry_policy=RetryPolicy(max_retries=2),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=365),
    ),
    "d3_calculate_risk_score": CapabilityContract(
        capability_key="d3_calculate_risk_score",
        input_schema={
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string"},
                "vendor_history": {"type": "object"},
                "amount": {"type": "number"},
                "deviation_flags": {"type": "array"},
            },
            "required": ["invoice_number", "amount"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "risk_score": {"type": "number", "minimum": 0, "maximum": 100},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "factors": {"type": "array"},
            },
        },
        retry_policy=RetryPolicy(max_retries=1),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=365),
    ),
    "d3_route_for_approval": CapabilityContract(
        capability_key="d3_route_for_approval",
        input_schema={
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string"},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "amount": {"type": "number"},
                "requested_approver_role": {"type": "string"},
            },
            "required": ["invoice_number", "risk_level", "amount"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "approval_request_id": {"type": "string"},
                "assigned_approvers": {"type": "array"},
                "escalation_time_hours": {"type": "number"},
                "status": {"type": "string", "enum": ["pending", "auto_approved", "escalated"]},
            },
        },
        retry_policy=RetryPolicy(max_retries=3, retry_on=["timeout"]),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=365),
    ),
    "d3_generate_daily_report": CapabilityContract(
        capability_key="d3_generate_daily_report",
        input_schema={
            "type": "object",
            "properties": {
                "batch_id": {"type": "string"},
                "report_date": {"type": "string"},
                "include_approvals": {"type": "boolean", "default": True},
            },
            "required": ["batch_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "report_id": {"type": "string"},
                "total_invoices": {"type": "number"},
                "total_amount": {"type": "number"},
                "approved_count": {"type": "number"},
                "pending_count": {"type": "number"},
                "rejected_count": {"type": "number"},
                "generated_at": {"type": "string", "format": "date-time"},
            },
        },
        retry_policy=RetryPolicy(max_retries=2),
        audit_policy=AuditPolicy(log_input=True, log_output=True, retention_days=365),
    ),
}


# ============================================================================
# Combined Registry
# ============================================================================

ALL_DEMO_CAPABILITIES = {
    **D1_CAPABILITIES,
    **D2_CAPABILITIES,
    **D3_CAPABILITIES,
}


def register_demo_capabilities(registry: CapabilityRegistry) -> None:
    """Registreer alle demo capabilities in de gegeven registry."""
    for capability in ALL_DEMO_CAPABILITIES.values():
        registry.register(capability)
