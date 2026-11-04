"""
GDPR Deletion Framework - Compliant data erasure with audit trail

Provides:
- GDPR deletion reasons (enum)
- Deletion audit logging
- Anonymization for PII
- Protection for audit logs
- Decision framework implementation

GDPR Compliance:
- Article 17: Right to erasure (hard_delete)
- Article 5: Data minimization (anonymize)
- Article 30: Record of processing activities (deletion_audit)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base
from src.core.utils.best_effort import best_effort

from .soft_delete import SoftDeleteMixin

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class GDPRDeletionReason(str, Enum):
    """
    Valid reasons for hard deletion under GDPR.

    Each reason maps to specific GDPR articles and legal bases.
    """

    USER_ERASURE_REQUEST = "user_erasure_request"
    """GDPR Article 17 - User exercised right to erasure."""

    CONSENT_WITHDRAWN = "consent_withdrawn"
    """GDPR Article 7 - User withdrew consent, no other legal basis."""

    DATA_RETENTION_EXPIRED = "data_retention_expired"
    """GDPR Article 5(1)(e) - Data no longer necessary for original purpose."""

    REGULATORY_REQUIREMENT = "regulatory_requirement"
    """Legal obligation to delete data (non-GDPR laws)."""

    CONTRACT_TERMINATED = "contract_terminated"
    """Contract ended and data no longer needed."""

    def description(self) -> str:
        """Get human-readable description."""
        descriptions = {
            GDPRDeletionReason.USER_ERASURE_REQUEST: "GDPR Article 17 - Right to erasure",
            GDPRDeletionReason.CONSENT_WITHDRAWN: "GDPR Article 7 - Consent withdrawn",
            GDPRDeletionReason.DATA_RETENTION_EXPIRED: "GDPR Article 5 - Retention period expired",
            GDPRDeletionReason.REGULATORY_REQUIREMENT: "Legal/regulatory requirement",
            GDPRDeletionReason.CONTRACT_TERMINATED: "Contract terminated",
        }
        return descriptions.get(self, "Unknown reason")


class AuditProtectionError(Exception):
    """Raised when attempting to hard delete protected audit records."""

    def __init__(self, entity_type: str) -> None:
        super().__init__(
            f"Cannot hard delete {entity_type}: Audit logs are protected by compliance policy. "
            "Use anonymization for PII removal while preserving audit trail."
        )
        self.entity_type = entity_type


class DeletionJustificationError(Exception):
    """Raised when deletion justification is insufficient."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Deletion justification insufficient: {reason}")


@dataclass
class DeletionAuditEntry:
    """Data class for deletion audit information."""

    entity_type: str
    entity_id: int | str
    deletion_reason: GDPRDeletionReason
    deleted_by: int | None
    tenant_id: int | None = None
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class DeletionAudit(Base):  # type: ignore[misc]
    """
    Audit table for hard deletions.

    Records all hard deletions for compliance and forensic purposes.
    This table itself should NEVER be deleted (compliance requirement).
    """

    __tablename__ = "deletion_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # What was deleted
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # GDPR context
    deletion_reason: Mapped[str] = mapped_column(String(50), nullable=False)
    legal_basis: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # GDPR article reference

    # Who deleted
    deleted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Tenant context -- ADR-005: NOT NULL, no FK (audit logs must survive tenant deletion)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Snapshot of deleted data (hashed/anonymized)
    entity_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_metadata: Mapped[Any | None] = (  # TODO(TYPE): replace Any with concrete type
        mapped_column(  # TODO(TYPE): replace Any with concrete type
            JSON, nullable=True
        )
    )  # Non-sensitive metadata

    # Justification
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DeletionAudit(entity_type={self.entity_type}, "
            f"entity_id={self.entity_id}, reason={self.deletion_reason})>"
        )


class GDPRDeletionManager:
    """
    Manager for GDPR-compliant data deletion.

    Implements the decision framework for data deletion:

    | Situatie | Actie | Reden |
    |----------|-------|-------|
    | Gebruiker wil account weg | anonymize PII, soft-delete account | Audit trail bewaren |
    | GDPR Art. 17 verzoek | hard_delete PII + deletion_audit entry | Wettelijke plicht |
    | Tenant contract opgezegd | soft-delete tenant data, hard-delete na 90 dagen | Bewaartermijn |
    | Test/demo data opruimen | hard_delete (REGULATORY) | Geen compliance-risico |
    | Audit logs | NOOIT hard_delete | Compliance-vereiste |
    """

    # Entity types that should NEVER be hard deleted
    PROTECTED_ENTITY_TYPES: set[str] = {
        "deletion_audit",
        "audit_logs",
        "security_alerts",
        "security_events",
    }

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize GDPR deletion manager.

        Args:
            session: Database session for operations
        """
        self._session = session

    async def soft_delete(
        self,
        entity: SoftDeleteMixin,
        deleted_by: int | None = None,
        reason: str | None = None,
    ) -> None:
        """
        Soft delete an entity (default deletion method).

        This is the standard approach for operational deletions.
        Data remains in database but is hidden from normal queries.

        Args:
            entity: Entity to soft delete
            deleted_by: User ID performing deletion
            reason: Reason for deletion
        """
        entity.soft_delete(deleted_by=deleted_by, reason=reason)
        self._session.add(entity)
        logger.info(
            "Soft deleted %s (id=%s)",
            entity.__class__.__name__,
            getattr(entity, "id", "unknown"),
        )

    async def hard_delete(
        self,
        entity: Any,  # TODO(TYPE): replace Any with concrete type
        deletion_reason: GDPRDeletionReason,
        deleted_by: int | None = None,
        justification: str | None = None,
        tenant_id: int | None = None,
    ) -> None:
        """
        Hard delete an entity (permanent removal).

        REQUIRES valid GDPRDeletionReason.
        Creates deletion_audit entry AFTER deletion (inside best_effort block).

        Args:
            entity: Entity to delete
            deletion_reason: Valid GDPR reason
            deleted_by: User ID performing deletion
            justification: Additional justification
            tenant_id: Tenant context

        Raises:
            AuditProtectionError: If entity type is protected
            DeletionJustificationError: If reason is invalid
        """
        entity_type = entity.__class__.__name__.lower()
        entity_id = getattr(entity, "id", "unknown")

        # Check if entity type is protected
        if entity_type in self.PROTECTED_ENTITY_TYPES:
            raise AuditProtectionError(entity_type)

        # Validate deletion reason
        if not isinstance(deletion_reason, GDPRDeletionReason):
            raise DeletionJustificationError(
                f"Invalid deletion reason: {deletion_reason}. "
                f"Must be one of: {list(GDPRDeletionReason)}"
            )

        # Capture entity data before deletion (entity object still in memory after delete())
        snapshot_hash = self._hash_entity(entity)
        entity_meta = self._extract_metadata(entity)

        # Primary: delete the entity
        await self._session.delete(entity)

        logger.warning(
            "Hard deleted %s (id=%s) with reason: %s",
            entity_type,
            entity_id,
            deletion_reason.value,
        )

        # Secondary: audit log -- failure must not abort the deletion
        async with best_effort("GDPR deletion audit", db_session=self._session):
            audit_entry = DeletionAudit(
                entity_type=entity_type,
                entity_id=str(entity_id),
                deletion_reason=deletion_reason.value,
                legal_basis=deletion_reason.description(),
                deleted_by=deleted_by,
                tenant_id=tenant_id if tenant_id is not None else 0,
                entity_snapshot_hash=snapshot_hash,
                entity_metadata=entity_meta,
                justification=justification,
            )
            self._session.add(audit_entry)

    async def anonymize(
        self,
        entity: Any,  # TODO(TYPE): replace Any with concrete type
        pii_fields: list[str],
        retention_fields: list[str] | None = None,
        anonymization_token: str = "[REDACTED]",
    ) -> None:
        """
        Anonymize PII fields while preserving record structure.

        This is the preferred approach for:
        - User account deletion requests (keep analytics data)
        - Statistical preservation requirements
        - GDPR compliance where data structure must remain

        Args:
            entity: Entity to anonymize
            pii_fields: List[Any] of field names containing PII to anonymize  # TODO(TYPE): replace Any with concrete type
            retention_fields: Fields to keep (non-PII)
            anonymization_token: Token to replace PII with
        """
        entity_type = entity.__class__.__name__
        entity_id = getattr(entity, "id", "unknown")

        anonymized_count = 0
        for field in pii_fields:
            if hasattr(entity, field):
                old_value = getattr(entity, field)
                if old_value is not None:
                    # Create hash for potential future verification
                    hashed_value = self._hash_value(str(old_value))
                    setattr(entity, field, f"{anonymization_token}_{hashed_value[:8]}")
                    anonymized_count += 1

        # Mark as anonymized
        if hasattr(entity, "anonymized_at"):
            entity.anonymized_at = datetime.now(timezone.utc)
        if hasattr(entity, "anonymized"):
            entity.anonymized = True

        self._session.add(entity)

        logger.info(
            "Anonymized %s (id=%s): %d fields redacted",
            entity_type,
            entity_id,
            anonymized_count,
        )

    async def handle_erasure_request(
        self,
        entity: Any,  # TODO(TYPE): replace Any with concrete type
        erasure_type: str,
        deleted_by: int | None = None,
        tenant_id: int | None = None,
    ) -> str:
        """
        Handle a GDPR Article 17 erasure request.

        Implements the decision framework:
        - Audit logs: Never delete, anonymize PII
        - Operational data: Hard delete with audit
        - Analytics data: Anonymize PII, keep structure

        Args:
            entity: Entity to process
            erasure_type: Type of entity being erased
            deleted_by: User ID processing request
            tenant_id: Tenant context

        Returns:
            Action taken description
        """
        entity_type = entity.__class__.__name__.lower()

        # Decision framework
        if entity_type in self.PROTECTED_ENTITY_TYPES:
            # Audit logs - anonymize only
            if hasattr(entity, "user_email"):
                await self.anonymize(entity, ["user_email", "user_name"])
            return "anonymized"

        elif erasure_type == "user_account":
            # Anonymize PII, soft delete account
            pii_fields = ["email", "name", "phone", "address"]
            await self.anonymize(
                entity,
                [f for f in pii_fields if hasattr(entity, f)],
            )
            await self.soft_delete(
                entity,
                deleted_by=deleted_by,
                reason="GDPR Article 17 erasure request",
            )
            return "anonymized_and_soft_deleted"

        else:
            # Operational data - hard delete
            await self.hard_delete(
                entity,
                deletion_reason=GDPRDeletionReason.USER_ERASURE_REQUEST,
                deleted_by=deleted_by,
                justification="User exercised right to erasure under GDPR Article 17",
                tenant_id=tenant_id,
            )
            return "hard_deleted"

    def _hash_entity(self, entity: Any) -> str:  # TODO(TYPE): replace Any with concrete type
        """Create hash of entity for audit trail."""
        entity_dict: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for key, value in entity.__dict__.items():
            if not key.startswith("_"):
                try:
                    # Simple string representation
                    entity_dict[key] = str(value)[:100]  # Truncate long values
                except Exception:
                    pass

        json_str = json.dumps(entity_dict, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _hash_value(self, value: str) -> str:
        """Create hash of a value."""
        return hashlib.sha256(value.encode()).hexdigest()

    def _extract_metadata(
        self,
        entity: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Extract non-sensitive metadata for audit."""
        metadata = {
            "class_name": entity.__class__.__name__,
            "module": entity.__class__.__module__,
        }

        # Add safe fields if they exist
        safe_fields = ["created_at", "updated_at", "tenant_id", "is_active"]
        for field in safe_fields:
            if hasattr(entity, field):
                value = getattr(entity, field)
                if value is not None:
                    metadata[field] = str(value)

        return metadata

    @staticmethod
    def get_retention_period(deletion_reason: GDPRDeletionReason) -> int | None:
        """
        Get recommended retention period in days for soft-deleted data.

        Args:
            deletion_reason: GDPR deletion reason

        Returns:
            Retention period in days, or None for immediate deletion
        """
        retention_periods = {
            GDPRDeletionReason.USER_ERASURE_REQUEST: 90,  # 90 days then purge
            GDPRDeletionReason.CONSENT_WITHDRAWN: 30,  # 30 days then purge
            GDPRDeletionReason.DATA_RETENTION_EXPIRED: 0,  # Immediate purge
            GDPRDeletionReason.REGULATORY_REQUIREMENT: 365,  # 1 year
            GDPRDeletionReason.CONTRACT_TERMINATED: 90,  # 90 days
        }
        return retention_periods.get(deletion_reason)


class GDPRComplianceReport:
    """
    Generate compliance reports for GDPR deletions.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def generate_deletion_report(
        self,
        tenant_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate report of deletions for compliance audit.

        Args:
            tenant_id: Filter by tenant
            start_date: Report start date
            end_date: Report end date
            limit: Max rows to return (default 1000, max 10000)
            offset: Pagination offset

        Returns:
            Report dictionary with deletion statistics
        """
        from sqlalchemy import select

        query = select(DeletionAudit)

        if tenant_id:
            query = query.where(DeletionAudit.tenant_id == tenant_id)
        if start_date:
            query = query.where(DeletionAudit.deleted_at >= start_date)
        if end_date:
            query = query.where(DeletionAudit.deleted_at <= end_date)

        query = query.limit(min(limit, 10000)).offset(offset)

        result = await self._session.execute(query)
        entries = result.scalars().all()

        # Aggregate statistics
        by_reason: dict[str, int] = {}
        by_type: dict[str, int] = {}

        for entry in entries:
            by_reason[entry.deletion_reason] = by_reason.get(entry.deletion_reason, 0) + 1
            by_type[entry.entity_type] = by_type.get(entry.entity_type, 0) + 1

        return {
            "rows_returned": len(entries),
            "by_reason": by_reason,
            "by_entity_type": by_type,
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            "tenant_id": tenant_id,
            "limit": limit,
            "offset": offset,
        }
