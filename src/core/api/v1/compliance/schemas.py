"""
Pydantic schemas for Compliance API.

Sprint 7, Task 1.2 and 2.2
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ComplianceScoreResponse(BaseModel):
    """
    Response model for compliance score endpoint.

    Contains overall and component scores for GDPR, AI Act, and audit compliance.
    """

    overall_score: float = Field(
        ...,  # Required field
        ge=0.0,  # Greater than or equal to 0
        le=100.0,  # Less than or equal to 100
        description="Weighted overall compliance score (0-100)",
        examples=[87.5],
    )
    gdpr_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="GDPR compliance score (0-100)",
        examples=[90.0],
    )
    ai_act_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="AI Act compliance score (0-100)",
        examples=[85.0],
    )
    audit_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Audit log integrity score (0-100)",
        examples=[88.0],
    )
    calculated_at: datetime = Field(
        ...,
        description="Timestamp when scores were calculated",
        examples=["2026-04-12T18:30:00Z"],
    )
    tenant_id: int = Field(
        ...,
        description="ID of the tenant these scores belong to",
        examples=[123],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "overall_score": 87.5,
                "gdpr_score": 90.0,
                "ai_act_score": 85.0,
                "audit_score": 88.0,
                "calculated_at": "2026-04-12T18:30:00Z",
                "tenant_id": 123,
            }
        }
    }


class ComplianceScoreHistoryResponse(BaseModel):
    """
    Response model for compliance score history endpoint.

    Contains a list of historical compliance scores and metadata.
    """

    history: list[ComplianceScoreResponse] = Field(
        default_factory=list,
        description="List of historical compliance scores",
    )
    count: int = Field(
        ...,
        ge=0,
        description="Number of history entries returned",
    )
    days_requested: int = Field(
        ...,
        ge=1,
        le=365,
        description="Number of days of history requested",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum number of results returned",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results skipped",
    )
    total_count: int = Field(
        default=0,
        ge=0,
        description="Total number of results available",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "history": [
                    {
                        "overall_score": 87.5,
                        "gdpr_score": 90.0,
                        "ai_act_score": 85.0,
                        "audit_score": 88.0,
                        "calculated_at": "2026-04-12T18:30:00Z",
                        "tenant_id": 123,
                    },
                    {
                        "overall_score": 85.0,
                        "gdpr_score": 88.0,
                        "ai_act_score": 84.0,
                        "audit_score": 83.0,
                        "calculated_at": "2026-04-11T18:30:00Z",
                        "tenant_id": 123,
                    },
                ],
                "count": 2,
                "days_requested": 30,
            }
        }
    }


# =============================================================================
# Sprint 7, Task 2.2 - GDPR Reporting Schemas
# =============================================================================


class GDPRSummaryResponse(BaseModel):
    """
    Response model for GDPR compliance summary endpoint.

    Contains aggregated GDPR compliance metrics for reporting dashboards.
    """

    total_data_subjects: int = Field(
        ...,
        ge=0,
        description="Total number of unique data subjects",
        examples=[1500],
    )
    dsar_requests_count: int = Field(
        ...,
        ge=0,
        description="Number of DSAR requests in the period",
        examples=[42],
    )
    dsar_avg_response_time_hours: float = Field(
        ...,
        ge=0.0,
        description="Average DSAR response time in hours",
        examples=[48.5],
    )
    consent_records_count: int = Field(
        ...,
        ge=0,
        description="Number of consent records",
        examples=[1500],
    )
    data_retention_violations: int = Field(
        ...,
        ge=0,
        description="Number of data retention policy violations",
        examples=[3],
    )
    period_days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Number of days covered by the report",
        examples=[30],
    )
    tenant_id: int = Field(
        ...,
        description="ID of the tenant this report belongs to",
        examples=[123],
    )
    generated_at: datetime = Field(
        ...,
        description="Timestamp when the report was generated",
        examples=["2026-04-12T18:30:00Z"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_data_subjects": 1500,
                "dsar_requests_count": 42,
                "dsar_avg_response_time_hours": 48.5,
                "consent_records_count": 1500,
                "data_retention_violations": 3,
                "period_days": 30,
                "tenant_id": 123,
                "generated_at": "2026-04-12T18:30:00Z",
            }
        }
    }


class DSARRequestItem(BaseModel):
    """
    Individual DSAR request item in the report.

    Represents a single Data Subject Access Request with status and timing.
    """

    id: str = Field(
        ...,
        description="Unique identifier for the DSAR request",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    type: str = Field(
        ...,
        description="Type of DSAR request (access, delete, portability)",
        examples=["access"],
    )
    status: str = Field(
        ...,
        description="Current status (pending, completed, overdue)",
        examples=["completed"],
    )
    requested_at: str = Field(
        ...,
        description="ISO timestamp when the request was made",
        examples=["2026-04-10T10:00:00Z"],
    )
    completed_at: str | None = Field(
        None,
        description="ISO timestamp when the request was completed (if applicable)",
        examples=["2026-04-11T14:00:00Z"],
    )
    response_time_hours: float = Field(
        ...,
        ge=0.0,
        description="Response time in hours (0 if not completed)",
        examples=[28.0],
    )
    data_subject_id: str = Field(
        ...,
        description="Identifier of the data subject who made the request",
        examples=["user-123"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "type": "access",
                "status": "completed",
                "requested_at": "2026-04-10T10:00:00Z",
                "completed_at": "2026-04-11T14:00:00Z",
                "response_time_hours": 28.0,
                "data_subject_id": "user-123",
            }
        }
    }


class DSARReportResponse(BaseModel):
    """
    Response model for DSAR report endpoint.

    Contains a list of DSAR requests with filtering and aggregation.
    """

    requests: list[DSARRequestItem] = Field(
        default_factory=list,
        description="List of DSAR requests matching the filter criteria",
    )
    count: int = Field(
        ...,
        ge=0,
        description="Total number of requests returned",
    )
    by_status: dict[str, int] = Field(
        default_factory=dict,
        description="Count of requests grouped by status",
    )
    period_days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Number of days covered by the report",
        examples=[30],
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum number of results returned",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results skipped",
    )
    total_count: int = Field(
        default=0,
        ge=0,
        description="Total number of results available",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "requests": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "type": "access",
                        "status": "completed",
                        "requested_at": "2026-04-10T10:00:00Z",
                        "completed_at": "2026-04-11T14:00:00Z",
                        "response_time_hours": 28.0,
                        "data_subject_id": "user-123",
                    }
                ],
                "count": 42,
                "by_status": {
                    "pending": 5,
                    "completed": 35,
                    "overdue": 2,
                },
                "period_days": 30,
            }
        }
    }


# =============================================================================
# Sprint 7, Task 3.2 - Integrity Check Schemas
# =============================================================================


class ChainPeriod(BaseModel):
    """Period specification for chain verification."""

    start_date: str | None = Field(
        None,
        description="Start date in ISO format",
        examples=["2026-01-01T00:00:00Z"],
    )
    end_date: str | None = Field(
        None,
        description="End date in ISO format",
        examples=["2026-04-12T23:59:59Z"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "start_date": "2026-01-01T00:00:00Z",
                "end_date": "2026-04-12T23:59:59Z",
            }
        }
    }


class ChainVerificationResponse(BaseModel):
    """Response model for chain verification endpoint.

    Contains verification results for the entire hash chain.
    """

    is_valid: bool = Field(
        ...,
        description=(
            "Whether the entire chain is sound: no tampering AND no unexplained coverage "
            "gaps. False when tampering_detected is true, OR when "
            "unhashed_after_watermark > 0 -- an unhashed row dated after the OP-108 fix "
            "date is indistinguishable from a row whose hash was stripped after the "
            "content was altered. Gaps dated before that fix date are known legacy gaps "
            "and no longer make this false (ADR-036 OP-108/OP-118)."
        ),
        examples=[True],
    )
    tampering_detected: bool = Field(
        False,
        description=(
            "A hashed entry failed recomputation or its previous_hash link. This is the "
            "P0 signal; unhashed_entries alone is a known, tracked coverage gap."
        ),
        examples=[False],
    )
    unhashed_entries: int = Field(
        0,
        ge=0,
        description=(
            "Entries with audit_hash IS NULL, skipped during verification. Written by "
            "legacy paths that did not populate the chain (ADR-036 OP-108, open). This is "
            "the TOTAL; see the watermark split below for which of them affect is_valid."
        ),
        examples=[0],
    )
    unhashed_before_watermark: int = Field(
        0,
        ge=0,
        description=(
            "Unhashed entries dated BEFORE the OP-108 fix date (2026-08-10). These are the "
            "known, registered legacy gaps for which no backfill is possible; they no longer "
            "make is_valid false (ADR-036 OP-108, watermark proposed under OP-118)."
        ),
        examples=[0],
    )
    unhashed_after_watermark: int = Field(
        0,
        ge=0,
        description=(
            "Unhashed entries dated ON OR AFTER the OP-108 fix date. Since every writer now "
            "populates the chain, such a row should not exist and is treated as suspect: any "
            "value above zero makes is_valid false. An entry without a usable timestamp is "
            "counted here, fail-secure."
        ),
        examples=[0],
    )
    total_entries: int = Field(
        ...,
        ge=0,
        description="Total number of entries checked",
        examples=[1500],
    )
    verified_entries: int = Field(
        ...,
        ge=0,
        description="Number of entries successfully verified",
        examples=[1500],
    )
    broken_at_entry_id: int | None = Field(
        None,
        description="ID of the first broken entry (null if all valid)",
        examples=[None],
    )
    broken_at_index: int | None = Field(
        None,
        description="Index of the first broken entry (null if all valid)",
        examples=[None],
    )
    expected_hash: str | None = Field(
        None,
        description="Expected hash at break point (null if all valid)",
        examples=[None],
    )
    actual_hash: str | None = Field(
        None,
        description="Actual hash at break point (null if all valid)",
        examples=[None],
    )
    verification_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Time taken for verification in milliseconds",
        examples=[245.5],
    )
    tenant_id: int = Field(
        ...,
        description="ID of the tenant whose chain was verified",
        examples=[123],
    )
    checked_at: datetime = Field(
        ...,
        description="Timestamp when verification was performed",
        examples=["2026-04-12T18:30:00Z"],
    )
    period: ChainPeriod = Field(
        default_factory=lambda: ChainPeriod(start_date=None, end_date=None),
        description="Period covered by the verification",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "is_valid": True,
                "total_entries": 1500,
                "verified_entries": 1500,
                "broken_at_entry_id": None,
                "broken_at_index": None,
                "expected_hash": None,
                "actual_hash": None,
                "verification_time_ms": 245.5,
                "tenant_id": 123,
                "checked_at": "2026-04-12T18:30:00Z",
                "period": {
                    "start_date": "2026-01-01T00:00:00Z",
                    "end_date": "2026-04-12T23:59:59Z",
                },
            }
        }
    }


class ChainStatusResponse(BaseModel):
    """Response model for chain status endpoint.

    Contains overall chain health status.
    """

    status: str = Field(
        ...,
        description="Chain health status (healthy, broken, unverified)",
        examples=["healthy"],
    )
    last_verified_at: datetime | None = Field(
        None,
        description="Timestamp of last verification (null if never verified)",
        examples=["2026-04-12T18:30:00Z"],
    )
    total_entries: int = Field(
        ...,
        ge=0,
        description="Total number of entries in the chain",
        examples=[1500],
    )
    broken_entries_count: int = Field(
        ...,
        ge=0,
        description="Number of entries with hash mismatches (tampering)",
        examples=[0],
    )
    unhashed_entries: int = Field(
        0,
        ge=0,
        description=(
            "Entries with audit_hash IS NULL. Not counted as broken -- a gap is not "
            "tampering -- but the status becomes 'unverified' when any exist "
            "(ADR-036 OP-108)."
        ),
        examples=[0],
    )
    health_percentage: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of healthy entries (0-100)",
        examples=[100.0],
    )
    tenant_id: int = Field(
        ...,
        description="ID of the tenant whose chain status is reported",
        examples=[123],
    )
    generated_at: datetime = Field(
        ...,
        description="Timestamp when the status was generated",
        examples=["2026-04-12T18:30:00Z"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "last_verified_at": "2026-04-12T18:30:00Z",
                "total_entries": 1500,
                "broken_entries_count": 0,
                "health_percentage": 100.0,
                "tenant_id": 123,
                "generated_at": "2026-04-12T18:30:00Z",
            }
        }
    }


class VerifyEntryRequest(BaseModel):
    """Request model for entry verification endpoint.

    Contains the entry ID to verify.
    """

    entry_id: int = Field(
        ...,
        ge=1,
        description="ID of the audit log entry to verify",
        examples=[12345],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "entry_id": 12345,
            }
        }
    }


class EntryVerificationResponse(BaseModel):
    """Response model for entry verification endpoint.

    Contains verification results for a single entry.
    """

    entry_id: int = Field(
        ...,
        description="ID of the verified entry",
        examples=[12345],
    )
    is_valid: bool = Field(
        ...,
        description="Whether the entry is valid",
        examples=[True],
    )
    hash_matches: bool = Field(
        ...,
        description="Whether stored hash matches computed hash",
        examples=[True],
    )
    previous_hash_matches: bool = Field(
        ...,
        description="Whether previous_hash link is valid",
        examples=[True],
    )
    computed_hash: str = Field(
        ...,
        description="Computed SHA-256 hash of the entry",
        examples=["abc123def456789..."],
    )
    stored_hash: str = Field(
        ...,
        description="Stored hash from the entry",
        examples=["abc123def456789..."],
    )
    tenant_id: int = Field(
        ...,
        description="ID of the tenant whose entry was verified",
        examples=[123],
    )
    verified_at: datetime = Field(
        ...,
        description="Timestamp when verification was performed",
        examples=["2026-04-12T18:30:00Z"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "entry_id": 12345,
                "is_valid": True,
                "hash_matches": True,
                "previous_hash_matches": True,
                "computed_hash": "abc123def456789...",
                "stored_hash": "abc123def456789...",
                "tenant_id": 123,
                "verified_at": "2026-04-12T18:30:00Z",
            }
        }
    }


# =============================================================================
# Sprint 7, Task 2.3 - AI Act Reporting Schemas
# =============================================================================


class AIActSummaryResponse(BaseModel):
    """
    Response model for AI Act compliance summary endpoint.

    Contains aggregated AI Act compliance metrics for reporting dashboards.
    """

    total_ai_decisions: int = Field(
        ...,
        ge=0,
        description="Total number of AI decisions in the period",
        examples=[1250],
    )
    high_risk_decisions: int = Field(
        ...,
        ge=0,
        description="Number of high-risk AI decisions",
        examples=[45],
    )
    human_oversight_rate: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of decisions with human oversight (0-100)",
        examples=[98.5],
    )
    explainability_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Average explainability score (0-100)",
        examples=[92.0],
    )
    bias_audit_count: int = Field(
        ...,
        ge=0,
        description="Number of bias audits conducted",
        examples=[12],
    )
    period_days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Number of days covered by the report",
        examples=[30],
    )
    tenant_id: int = Field(
        ...,
        description="ID of the tenant this report belongs to",
        examples=[123],
    )
    generated_at: datetime = Field(
        ...,
        description="Timestamp when the report was generated",
        examples=["2026-04-12T18:30:00Z"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_ai_decisions": 1250,
                "high_risk_decisions": 45,
                "human_oversight_rate": 98.5,
                "explainability_score": 92.0,
                "bias_audit_count": 12,
                "period_days": 30,
                "tenant_id": 123,
                "generated_at": "2026-04-12T18:30:00Z",
            }
        }
    }


class AIActDecisionItem(BaseModel):
    """
    Individual AI decision item in the report.

    Represents a single AI decision with risk level and oversight information.
    """

    id: str = Field(
        ...,
        description="Unique identifier for the AI decision",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    decision_type: str = Field(
        ...,
        description="Type of AI decision (credit_approval, job_screening, etc.)",
        examples=["credit_approval"],
    )
    risk_level: str = Field(
        ...,
        description="Risk level (low, medium, high)",
        examples=["high"],
    )
    human_reviewed: bool = Field(
        ...,
        description="Whether the decision was reviewed by a human",
        examples=[True],
    )
    explainability_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Explainability score for this decision (0-100)",
        examples=[85.5],
    )
    decided_at: str = Field(
        ...,
        description="ISO timestamp when the decision was made",
        examples=["2026-04-10T10:00:00Z"],
    )
    outcome: str = Field(
        ...,
        description="Outcome of the decision (approved, rejected, flagged)",
        examples=["approved"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "decision_type": "credit_approval",
                "risk_level": "high",
                "human_reviewed": True,
                "explainability_score": 85.5,
                "decided_at": "2026-04-10T10:00:00Z",
                "outcome": "approved",
            }
        }
    }


class AIActDecisionsReportResponse(BaseModel):
    """
    Response model for AI Act decisions report endpoint.

    Contains a list of AI decisions with filtering and aggregation.
    """

    decisions: list[AIActDecisionItem] = Field(
        default_factory=list,
        description="List of AI decisions matching the filter criteria",
    )
    count: int = Field(
        ...,
        ge=0,
        description="Total number of decisions returned",
    )
    by_risk_level: dict[str, int] = Field(
        default_factory=dict,
        description="Count of decisions grouped by risk level",
    )
    human_oversight_rate: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of decisions with human oversight (0-100)",
        examples=[98.5],
    )
    period_days: int = Field(
        ...,
        ge=1,
        le=365,
        description="Number of days covered by the report",
        examples=[30],
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum number of results returned",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results skipped",
    )
    total_count: int = Field(
        default=0,
        ge=0,
        description="Total number of results available",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "decisions": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "decision_type": "credit_approval",
                        "risk_level": "high",
                        "human_reviewed": True,
                        "explainability_score": 85.5,
                        "decided_at": "2026-04-10T10:00:00Z",
                        "outcome": "approved",
                    }
                ],
                "count": 1250,
                "by_risk_level": {
                    "low": 800,
                    "medium": 405,
                    "high": 45,
                },
                "human_oversight_rate": 98.5,
                "period_days": 30,
            }
        }
    }
