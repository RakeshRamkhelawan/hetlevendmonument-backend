"""
Governance Models
Defines the schema for Audit Logs and Compliance records.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.database.database import Base


class AuditLog(Base):  # type: ignore[misc]
    """
    Immutable Audit Log for tracking all system actions.
    Required for GDPR and SOC2 compliance.
    Combines Security Audit (Legacy) and Governance Audit (Phase 4).
    """

    __tablename__ = "audit_logs"

    # Dezelfde partiele index als migratie 20260810_audit_chain_lookup_index. Hier OOK
    # declareren, anders meldt `alembic check` drift en wil autogenerate hem droppen
    # (ADR-036 OP-108). Dekt de ketenlookup die ELKE auditschrijving doet, onder een lock:
    # `WHERE tenant_id = ? AND audit_hash IS NOT NULL ORDER BY timestamp DESC, id DESC LIMIT 1`.
    __table_args__ = (
        Index(
            "ix_audit_logs_chain_lookup",
            "tenant_id",
            text("timestamp DESC"),
            text("id DESC"),
            postgresql_where=text("audit_hash IS NOT NULL"),
        ),
        # Geen `RETURNING` bij een insert (ADR-036 OP-246, migratie 20261024_audit_leesregel):
        # Postgres toetst de NIEUWE rij bij `RETURNING` ook tegen de leesregel, en een auditregel
        # voor een andere klant of zonder klant is voor de schrijver niet leesbaar. De primaire
        # sleutel wordt daarom vooraf uit de sequence gehaald. Zonder dit faalt elke schrijf-
        # actie onder de applicatierol met `new row violates row-level security policy`.
        {"implicit_returning": False},
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Phase 4 Governance Fields
    # GEEN vreemde sleutel naar `tenants` (migratie 20261012_audit_geen_tenant_fk, AVG C): het
    # auditlog blijft bewaard als de tenant wordt opgeheven. `tenant_id` zit in de hash.
    tenant_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    action: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    resource: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    details: Mapped[dict[str, object] | None] = mapped_column(JSON, default={})

    # Legacy Security Fields (Required by DB constraints)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    threat_level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    client_ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default={}, nullable=False)

    # Common Fields
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", use_alter=True), index=True, nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # ADR-019: SHA-256 hash chain for tamper-evidence (nullable for existing rows)
    audit_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Welk algoritme `audit_hash` heeft gemaakt (ADR-036 OP-120). `NULL` = legacy SHA-256,
    #: `"hmac-sha256-v1"` = gesleuteld. Deze waarde zit ZELF in de preimage -- anders zet een
    #: aanvaller hem terug op NULL, valt in de sleutelloze tak en rekent de rij opnieuw uit.
    hash_algorithm: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # No update/delete methods should be implemented for this model
    # It is append-only by design


class AuditChainAnchor(Base):  # type: ignore[misc]
    """De vorige gemeten toestand van de auditketen per tenant (ADR-036 OP-118/OP-119).

    **Waarom dit bestaat.** `verify_chain` leest alleen `audit_logs`, en afwezigheid heeft geen
    hash: verdwenen rijen zijn per constructie onzichtbaar voor een staatloze controle. Gemeten
    gevolg: `DELETE FROM audit_logs WHERE tenant_id = X` gaf `is_valid=True`, en een lege keten
    heet in `get_chain_status` letterlijk `status="healthy", health_percentage=100.0`.

    Deze rij onthoudt wat er de vorige keer stond, zodat een DALING zichtbaar wordt.

    **De grens, en die hoort ook in ADR-019 te staan.** Dit anker leeft in dezelfde database die
    een aanvaller kan schrijven. Het vangt een kapotte opruimjob, een ongeluk, en een aanvaller
    die het anker niet kent -- niet iemand die het meebijwerkt. Pas met een ondertekende ankerrij
    (OP-120) is dat laatste afgedekt, en zelfs dan blijft het VERWIJDEREN van alle ankers een
    reset van de nulmeting.
    """

    __tablename__ = "audit_chain_anchors"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    #: De laatste `audit_hash` die bij de vorige verificatie is gezien. `None` als de keten toen
    #: leeg was -- dat is iets anders dan "nooit gemeten", want dan bestaat deze rij niet.
    head_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    #: Het aantal auditregels bij de vorige verificatie. Een DALING is de kern van OP-119.
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Rijen zonder hash bij de vorige verificatie. Het bestaande aantal is een bekend gat
    #: (OP-108, geen backfill mogelijk); een TOENAME is dat niet en is het watermerk uit OP-118.
    unhashed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Het knippunt voor OP-120: vanaf welke auditregel de HMAC-variant geldt. Leeg tot die
    #: omschakeling; daarna is een ongesleutelde rij NA dit punt zelf een afwijking.
    chain_epoch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


# =============================================================================
# GDPR Compliance Models
# =============================================================================


class UserConsent(Base):  # type: ignore[misc]
    """
    User cookie consent preferences - GDPR Art. 7 compliance.

    Stores granular consent for different cookie categories:
    - Essential: Always required, cannot be disabled
    - Analytics: Usage tracking (opt-in)
    - Marketing: Promotional cookies (opt-in)
    - Personalization: AI recommendations (opt-in)
    """

    __tablename__ = "user_consents"

    # De migratie maakt deze constraint AL (ADR-036 OP-160).
    #
    # `20260404_gdpr_tables.py:58` zet `CONSTRAINT uq_user_tenant_consent UNIQUE (user_id,
    # tenant_id)`. Zonder hem in het model accepteert de testomgeving -- die het schema uit
    # de MODELLEN bouwt -- twee toestemmingsrijen voor dezelfde gebruiker in dezelfde
    # tenant, terwijl productie dat weigert. Bij toestemming is dat geen detail: bij twee
    # rijen is niet te zeggen welke geldt, en de nieuwste is niet per definitie de rij die
    # `_get_or_create_consent()` teruggeeft.
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant_consent"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Consent categories
    essential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    analytics: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    marketing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    personalization: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class AIDecision(Base):  # type: ignore[misc]
    """
    AI decision logging - GDPR Art. 13, 14, 22 compliance.

    Records automated decisions with explanations for transparency.
    Enables human review requests (Art. 22(3)).
    """

    __tablename__ = "ai_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Decision details
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    decision_type: Mapped[str] = mapped_column(String(100), nullable=False)
    input_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    output_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # GDPR transparency fields
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    profiling_involved: Mapped[bool] = mapped_column(Boolean, default=False)
    human_review_available: Mapped[bool] = mapped_column(Boolean, default=True)
    human_review_requested: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserProfilingOptOut(Base):  # type: ignore[misc]
    """
    User opt-out from profiling - GDPR Art. 21 compliance.

    Records user's right to object to automated profiling.
    """

    __tablename__ = "user_profiling_opt_outs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    profiling_type: Mapped[str] = mapped_column(String(50), nullable=False)

    opted_out: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Unique constraint: one opt-out per user/tenant/profiling_type
    __table_args__ = (
        UniqueConstraint(
            "user_id", "tenant_id", "profiling_type", name="uq_user_profiling_opt_out"
        ),
    )


class HumanReviewRequest(Base):  # type: ignore[misc]
    """
    Human review requests for AI decisions - GDPR Art. 22(3) compliance.

    Records user's request for human intervention on automated decisions.
    """

    __tablename__ = "human_review_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    decision_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Request details
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending, in_review, completed, rejected

    # Reviewer details (filled when reviewed)
    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DSARRequest(Base):  # type: ignore[misc]
    """
    Data Subject Access Request - GDPR Art. 15, 17, 20 compliance.

    Records requests for data export, deletion, or portability.
    """

    __tablename__ = "dsar_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Request details
    request_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # export, delete, portability
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending, processing, completed, failed

    # Timestamps
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # For export requests: URL to download data
    data_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_admin_request: Mapped[bool] = mapped_column(Boolean, default=False)


# =============================================================================
# Gatekeeper Models (ADR-017 Deterministic Policy Enforcement)
# =============================================================================


class GatekeeperDecision(Base):  # type: ignore[misc]
    """
    Gatekeeper decision records with SHA-256 hash chain for tamper evidence.

    Each decision is cryptographically linked to the previous decision
    within the same tenant, creating a per-tenant audit chain.

    ADR-019: Audit logging with SHA-256 hash chain
    ADR-005: tenant_id NOT NULL for strict isolation
    """

    __tablename__ = "gatekeeper_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # ADR-005: NOT NULL

    # Decision outcome
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # allow/block/hitl/defer
    risk_category: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)

    # ShadowCEO veto reference (JSON blob)
    shadow_ceo_veto: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    # Policy evaluation
    policy_rules_checked: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    policy_rules_failed: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    # HITL
    hitl_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hitl_ticket_ref: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    override_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # SHA-256 hash chain (PER TENANT - chain is tenant-scoped)
    decision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # NULL = genesis for this tenant

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HITLRequestModel(Base):  # type: ignore[misc]
    """
    Human-in-the-Loop request persistence.

    Stores pending, approved, and rejected HITL requests for audit trail.
    Linked to GatekeeperDecision via decision_id.
    """

    __tablename__ = "hitl_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # ADR-005: NOT NULL
    ticket_ref: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending/approved/rejected/expired
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Resolution details
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # HITL reason
    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Rejection reason from human

    # Link to decision
    decision_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # FK to gatekeeper_decisions.decision_id

    # SP-GOV-ARCH-7: which agent this ticket concerns, so approve_hitl() can record
    # the approval on THAT agent's GovernanceContract without trusting a client-
    # supplied, uncorrelated agent_id (server-derived, not request-body input).
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # ADR-036 OP-81: de MENS namens wie de agent deze aanvraag deed.
    #
    # `agent_id` hierboven legt vast WELKE agent handelde, en dat is niet dezelfde vraag.
    # Zonder deze kolom kon de goedkeurroute niet vaststellen of de beslisser dezelfde persoon is
    # als de aanvrager, en was het vierogenprincipe uit ADR-015 op dit pad een formaliteit: de
    # rolcheck uit OP-43 toetst een ROL, geen RELATIE. OWASP ASVS 5.0 8.3.3 eist dat het
    # autorisatiebesluit op het OORSPRONKELIJKE subject rust en niet op de tussenliggende service
    # die namens hem handelt -- dus op deze waarde en niet op `agent_id`.
    #
    # Het gebruikersNUMMER en niet een naam of adres, om dezelfde reden als bij `approved_by`
    # (OP-55): `PUT /api/v1/users/me` laat elke gebruiker zijn eigen adres wijzigen, dus een adres
    # is geen stabiele sleutel voor een identiteitsvergelijking. Een integer kan bovendien niet in
    # formaat afdrijven -- de JSONB-tegenhanger op het broker-pad kostte daar een aparte reparatie
    # (OP-106, isdigit vs isdecimal).
    #
    # NULLABLE, en dat is een keuze: bestaande rijen hebben geen aanvrager, en een aanvraag die
    # werkelijk zonder menselijke opdrachtgever ontstaat (een autonome planner) heeft er geen.
    # De zelf-goedkeuringscheck slaat dan over; de rolcheck blijft staan. Zelfde afweging en
    # zelfde motivering als `_refuse_self_approval` op het broker-pad: een ticket zonder bekende
    # aanvrager onbeoordeelbaar maken zou de wachtrij vastzetten.
    requested_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Metadata
    risk_factors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# =============================================================================
# Agent Governance Contract (ADR-031, SP-GOV-ARCH-7)
# =============================================================================


class AgentGovernanceContract(Base):  # type: ignore[misc]
    """Persisted state for a src.core.governance.governance_contract.GovernanceContract.

    Backs HITL approvals with durable storage (ADR-005/ADR-031): a HUMAN_IN_LOOP
    agent's evidence['approved_actions'] must survive process restarts, not just
    live in the in-memory dataclass for the lifetime of one agent instance.
    """

    __tablename__ = "agent_governance_contracts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # ADR-005: NOT NULL
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    autonomy_level: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_category: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "agent_id", name="uq_agent_governance_contracts_tenant_agent"
        ),
    )


# =============================================================================
# Tool Safety Models (ADR-015 Tool Allowlist & Audit Trail)
# =============================================================================


class ToolAuditLog(Base):  # type: ignore[misc]
    """
    Audit log for tool execution (ADR-015 compliant).

    Every tool invocation by any agent is recorded here with:
    - SHA-256 hash of the output (tamper detection)
    - Per-tenant hash chain (each tenant has independent chain)
    - Sanitized output (no PII stored)

    ADR-019: Audit logging with SHA-256 hash chain
    ADR-005: tenant_id NOT NULL for strict isolation
    """

    __tablename__ = "tool_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Core identifiers (ADR-005: tenant_id NOT NULL)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Tool details
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)  # low/medium/high
    tool_input: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    # Result
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # success/failed/blocked/pending_hitl
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tamper evidence
    output_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # SHA-256 of tool output
    previous_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # Chain link (per tenant)
    audit_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 of this record

    # HITL
    hitl_ticket_ref: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    hitl_approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timing
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    # Raw data for forensics (sanitized, no PII)
    tool_output: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


# =============================================================================
# GDPR Export Jobs
# =============================================================================


class ExportJob(Base):  # type: ignore[misc]
    """SQLAlchemy ORM model for GDPR data export jobs.

    Tracks the lifecycle of data export requests (GDPR Article 20 right to portability).
    Tenant-isolated via RLS + NOT NULL tenant_id constraint (ADR-005).
    """

    __tablename__ = "export_jobs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
    export_format: Mapped[str] = mapped_column(String(20), nullable=False)
    result_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        # NOTE: clock_timestamp() not now() -- serializable ordering under concurrent inserts
        # See CLAUDE.md pattern 11.5
        server_default=text("clock_timestamp()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# =============================================================================
# Pack Feedback Models (SP-A02)
# =============================================================================


class PackFeedback(Base):  # type: ignore[misc]
    """User feedback on pack template matches.

    Stores ratings (1-5) and optional comments for pack usage.
    Tenant-isolated via RLS + NOT NULL tenant_id (ADR-005).
    """

    __tablename__ = "pack_feedback"

    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="chk_pack_feedback_rating"),)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    pack_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class GlobalPack(Base):  # type: ignore[misc]
    """Community-contributed packs within a tenant scope.

    Despite the name, packs are tenant-scoped (tenant_id NOT NULL).
    The 'global' refers to sharing within the tenant community,
    not cross-tenant visibility. ADR-005 compliance enforced.
    """

    __tablename__ = "global_packs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contributor_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    pack_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class CollaborationSnapshot(Base):  # type: ignore[misc]
    """
    JSON workflow snapshot for real-time collaboration state.

    Stores React-Flow graph state (nodes, edges) per workflow.
    Multi-tenant with RLS. ADR-005 compliance enforced.
    """

    __tablename__ = "workflow_snapshots"
    __table_args__ = (Index("ix_workflow_snapshots_tenant_workflow", "tenant_id", "workflow_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    snapshot_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


# =============================================================================
# EU AI Act Compliance Models (ADR-031)
# =============================================================================


class IncidentReportDB(Base):  # type: ignore[misc]
    """
    Persistent EU AI Act incident reports (Article 62).

    Replaces in-memory _incident_store singleton. EU AI Act requires
    10-year retention; use soft-delete only (deleted_at), NEVER hard delete.

    ADR-005: tenant_id NOT NULL + RESTRICT FK (no cascade on tenant delete)
    ADR-031: EU AI Act governance audit evidence
    CLAUDE.md ss11.5: clock_timestamp() for ordered concurrent inserts
    """

    __tablename__ = "ai_act_incident_reports"

    __table_args__ = (
        Index("ix_incident_tenant_created", "tenant_id", "created_at"),
        Index("ix_incident_tenant_status", "tenant_id", "resolution_status"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # GEEN vreemde sleutel naar `tenants` (migratie 20261012_audit_geen_tenant_fk, AVG C): meldingen
    # van AI-incidenten blijven bewaard (mogelijke bewaarplicht, niet gemeten) en worden bij het
    # opheffen van een tenant geanonimiseerd, niet verwijderd.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    incident_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eu_reporting_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eu_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="open"
    )
    incident_data: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelProvenanceDB(Base):  # type: ignore[misc]
    """
    Persistent LLM call provenance records (Article 12 + Article 53).

    Replaces in-memory _provenance_store singleton. Records provider, model,
    version, input/output hashes for compliance evidence.

    ADR-005: tenant_id NOT NULL + RESTRICT FK (10-year retention)
    ADR-031: EU AI Act model provenance evidence
    CLAUDE.md ss11.5: clock_timestamp() for ordered concurrent inserts
    """

    __tablename__ = "model_provenance_records"

    __table_args__ = (Index("ix_provenance_tenant_registered", "tenant_id", "registered_at"),)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Council types moved from copilot.council (SP-DSM-005, ADR-027)
# governance -> copilot is FORBIDDEN per ADR-027; these types live here so
# governance modules (hash_chain, retention_cleanup) can import them
# without crossing the governance->copilot boundary.
# copilot modules re-export them via backward-compat re-exports.
# ---------------------------------------------------------------------------


class VerdictType(str, Enum):
    """Per-Officer verdict on a proposal."""

    APPROVE = "approve"
    APPROVE_WITH_MODIFICATION = "modify"
    REQUIRE_HITL = "require_hitl"
    REQUIRE_DEFERRAL = "defer"
    VETO = "veto"
    OVERRIDE_BUDGET = "override_budget"


@dataclass(frozen=True)
class OfficerVerdict:
    """A single Officer's verdict on a Proposal (EU AI Act art. 12, ISO 42001 A.6.2.8)."""

    officer_name: str
    officer_version: str
    verdict: VerdictType
    reason_code: str
    reason_text: str
    evidence: dict[str, object]
    deliberation_ms: int
    confidence: float
    used_cache: bool = False
    verdict_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


class CouncilDecisionRow(Base):  # type: ignore[misc]
    """SQLAlchemy ORM model for council decisions (moved from copilot.council.models, SP-DSM-005)."""

    __tablename__ = "council_decisions"

    decision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    proposal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    action_params: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data_classification: Mapped[str] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_for_user: Mapped[str] = mapped_column(Text, nullable=False)
    deliberation_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    hitl_request_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    modifications: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    officer_verdicts_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_decision_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="pending"
    )

    officer_verdicts: Mapped[list["OfficerVerdictRow"]] = relationship(
        "OfficerVerdictRow", back_populates="decision", cascade="all, delete-orphan"
    )


class OfficerVerdictRow(Base):  # type: ignore[misc]
    """SQLAlchemy ORM model for per-officer verdicts (moved from copilot.council.models, SP-DSM-005)."""

    __tablename__ = "officer_verdicts"

    verdict_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    decision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("council_decisions.decision_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), nullable=False)
    officer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    officer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    deliberation_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    used_cache: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    decision: Mapped["CouncilDecisionRow"] = relationship(
        "CouncilDecisionRow", back_populates="officer_verdicts"
    )


# =============================================================================
# Prana Economy Models (ADR-021 -- department-per-tenant internal token economy)
# =============================================================================


class PranaDepartmentBudget(Base):  # type: ignore[misc]
    """Per-(tenant, department) prana budget (ADR-021).

    ADR-005: tenant_id NOT NULL + FK CASCADE + RLS. The atomic spend is a conditional
    UPDATE guarded by ``(total_prana - spent_prana) >= cost`` (see PranaService.charge);
    the row-level lock of that UPDATE also serialises the per-(tenant, department) hash
    chain, so no separate lock is needed.
    """

    __tablename__ = "prana_department_budget"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department: Mapped[str] = mapped_column(String(50), nullable=False)

    # ADR-021: 10000 prana per department per tenant. spent_prana is the mutable counter
    # (charge += cost, refund -= cost, refill resets to 0). allocated_prana is reserved for
    # a future allocate/reserve flow. available = total_prana - spent_prana.
    total_prana: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10000"))
    allocated_prana: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    spent_prana: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    cycle_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # tenant_id already gets an index via the column (index=True); the
    # UNIQUE(tenant_id, department) additionally covers tenant_id-prefix lookups.
    __table_args__ = (
        UniqueConstraint("tenant_id", "department", name="uq_prana_dept_budget"),
        CheckConstraint("total_prana >= 0", name="ck_prana_total_non_negative"),
        {"extend_existing": True},
    )


class PranaTransaction(Base):  # type: ignore[misc]
    """Append-only prana transaction ledger with a per-(tenant, department) SHA-256 hash
    chain (ADR-019). Never UPDATE/DELETE a row -- append a compensating row instead.

    The unique ``(tenant_id, department, sequence_no)`` rejects a forked chain under
    concurrency (defense-in-depth on top of the budget-row-lock serialisation).
    """

    __tablename__ = "prana_transaction"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department: Mapped[str] = mapped_column(String(50), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)

    action_type: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ml/llm/vision/hybrid
    cost: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # spend/refund/refill/emergency
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    data_classification: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'INTERNAL'")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    # Tamper evidence -- per (tenant, department) chain (see compute_prana_hash).
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "department", "sequence_no", name="uq_prana_tx_seq"),
        CheckConstraint(
            "kind IN ('spend', 'refund', 'refill', 'emergency')", name="ck_prana_tx_kind"
        ),
        Index("idx_prana_tx_tenant_dept", "tenant_id", "department"),
        {"extend_existing": True},
    )
