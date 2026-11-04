"""
Cookie Consent Manager - GDPR Art. 7 compliance.

Implements:
- Art. 7: Explicit consent (opt-out model, default=disabled for non-essential)
- Consent withdrawal logging
- Policy version tracking
- Audit trail for consent changes

Usage:
    manager = CookieConsentManager(db)

    # Get current consent
    consent = await manager.get_consent(user_id="user_123", tenant_id=1)

    # Update consent
    await manager.update_consent(
        user_id="user_123",
        tenant_id=1,
        preferences={"analytics": True, "marketing": False},
        policy_version="1.0",
    )

    # Check specific category
    has_analytics = await manager.is_consent_given(
        user_id="user_123",
        tenant_id=1,
        category=ConsentCategory.ANALYTICS,
    )
"""

import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

logger = logging.getLogger(__name__)

from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.ketencontext import ketencontext
from src.core.governance.models import AuditLog, UserConsent


async def _maybe_await(value: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Await value if it's a coroutine (handles AsyncMock in tests)."""
    if inspect.iscoroutine(value):
        return await value
    return value


from src.core.shared.consent_categories import ConsentCategory as ConsentCategory
from src.core.governance.audit_chain_key import mark_entry


class ConsentPreferences(BaseModel):
    """
    User's cookie consent preferences.

    Default: Opt-out model (non-essential cookies disabled by default)
    """

    essential: bool = True  # Always True - cannot be disabled
    analytics: bool = False  # Default False - user must opt-in
    marketing: bool = False  # Default False - user must opt-in
    personalization: bool = False  # Default False - user must opt-in
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    policy_version: str


@dataclass
class UserConsentRecord:
    """
    In-memory representation of user's consent record.

    Used for internal operations; database model is UserConsent.
    """

    user_id: str
    tenant_id: int
    essential: bool = True
    analytics: bool = False
    marketing: bool = False
    personalization: bool = False
    policy_version: str = "1.0"
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class CookieConsentManager:
    """
    GDPR-compliant cookie consent management.

    Implements:
    - Art. 7: Explicit consent with policy version tracking
    - Consent withdrawal logging
    - Audit trail for compliance

    Default Behavior:
    - Essential cookies: Always enabled (required for service)
    - Analytics/Marketing/Personalization: Disabled by default (opt-in)

    Example:
        manager = CookieConsentManager(db)

        # Get consent
        consent = await manager.get_consent(user_id="123", tenant_id=1)

        # Update with new preferences
        new_consent = await manager.update_consent(
            user_id="123",
            tenant_id=1,
            preferences={"analytics": True, "marketing": False},
            policy_version="1.0",
        )

        # Check specific category
        if await manager.is_consent_given(user_id="123", tenant_id=1, category=ConsentCategory.ANALYTICS):
            # Enable analytics tracking
            pass
    """

    CURRENT_POLICY_VERSION = "1.0"

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize CookieConsentManager.

        Args:
            db: SQLAlchemy async session
        """
        self._db = db

    async def _get_or_create_db_record(
        self,
        user_id: str,
        tenant_id: int,
    ) -> UserConsent:
        """
        Get existing consent record from DB or create new one with defaults.

        Args:
            user_id: User ID
            tenant_id: Tenant ID

        Returns:
            UserConsent model (existing or new with defaults)
        """
        # Query existing record
        result = await self._db.execute(
            select(UserConsent).where(
                UserConsent.user_id == user_id,
                UserConsent.tenant_id == tenant_id,
            )
        )
        existing = await _maybe_await(result.scalar_one_or_none())

        if existing:
            return cast(UserConsent, existing)

        # Create new record with defaults
        new_record = UserConsent(
            user_id=user_id,
            tenant_id=tenant_id,
            essential=True,
            analytics=False,
            marketing=False,
            personalization=False,
            policy_version=self.CURRENT_POLICY_VERSION,
        )
        self._db.add(new_record)
        await self._db.commit()
        await self._db.refresh(new_record)
        return new_record

    def _db_to_preferences(self, record: UserConsent) -> ConsentPreferences:
        """Convert database record to ConsentPreferences."""
        ts: datetime | None = getattr(record, "updated_at", None) or getattr(
            record, "created_at", None
        )
        return ConsentPreferences(
            essential=record.essential,
            analytics=record.analytics,
            marketing=record.marketing,
            personalization=record.personalization,
            timestamp=ts if isinstance(ts, datetime) else datetime.now(timezone.utc),
            policy_version=str(record.policy_version),
        )

    async def get_consent(
        self,
        user_id: str,
        tenant_id: int,
    ) -> ConsentPreferences:
        """
        Get current consent preferences for a user.

        Returns existing preferences or default (essential only) for new users.

        Args:
            user_id: User ID
            tenant_id: Tenant ID

        Returns:
            ConsentPreferences object
        """
        record = await self._get_or_create_db_record(user_id, tenant_id)
        return self._db_to_preferences(record)

    async def update_consent(
        self,
        user_id: str,
        tenant_id: int,
        preferences: dict[str, bool],
        policy_version: str,
    ) -> ConsentPreferences:
        """
        Update consent preferences for a user.

        Logs the change to audit trail. If a category is being disabled,
        logs it as a withdrawal.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            preferences: Dictionary of category -> enabled
            policy_version: Current policy version

        Returns:
            Updated ConsentPreferences
        """
        # Get existing record
        existing_record = await self._get_or_create_db_record(user_id, tenant_id)

        # Track what changed for audit
        changes = []
        withdrawals = []

        # Validate and apply changes
        # Essential CANNOT be disabled
        new_essential = True  # Always True

        new_analytics = preferences.get("analytics", existing_record.analytics)
        if new_analytics != existing_record.analytics:
            changes.append(f"analytics: {existing_record.analytics} -> {new_analytics}")
            if not new_analytics and existing_record.analytics:
                withdrawals.append("analytics")

        new_marketing = preferences.get("marketing", existing_record.marketing)
        if new_marketing != existing_record.marketing:
            changes.append(f"marketing: {existing_record.marketing} -> {new_marketing}")
            if not new_marketing and existing_record.marketing:
                withdrawals.append("marketing")

        new_personalization = preferences.get("personalization", existing_record.personalization)
        if new_personalization != existing_record.personalization:
            changes.append(
                f"personalization: {existing_record.personalization} -> {new_personalization}"
            )
            if not new_personalization and existing_record.personalization:
                withdrawals.append("personalization")

        # Update the database record
        existing_record.essential = new_essential
        existing_record.analytics = new_analytics
        existing_record.marketing = new_marketing
        existing_record.personalization = new_personalization
        existing_record.policy_version = policy_version
        # updated_at is handled by onupdate

        await self._db.commit()
        await self._db.refresh(existing_record)

        result = self._db_to_preferences(existing_record)

        # Audit log is best-effort: a failure here must not roll back the consent update.
        try:
            audit_details: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "policy_version": policy_version,
                "preferences": {
                    "essential": new_essential,
                    "analytics": new_analytics,
                    "marketing": new_marketing,
                    "personalization": new_personalization,
                },
                "changes": changes,
            }

            if withdrawals:
                audit_details["withdrawals"] = withdrawals

            user_id_int = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else None

            audit_entry = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id_int,
                action="consent.updated",
                resource=f"consent:user:{user_id}",
                details=audit_details,
                event_type="gdpr_consent",
                threat_level="info",
                client_ip="unknown",
                endpoint="/api/consent",
                description=f"Consent updated for user {user_id}",
                event_metadata={
                    "policy_version": policy_version,
                    "withdrawal": len(withdrawals) > 0,
                    "withdrawn_categories": withdrawals,
                },
            )
            # De tijdstempel wordt EXPLICIET gezet zodat de hash reproduceerbaar is bij
            # herverificatie. Dat gebeurt hieronder NA het slot.
            try:
                # Advisory lock serializes chain writes per tenant -- prevents forked chain.
                await self._db.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": tenant_id}
                )
                # DE TIJDSTEMPEL NA HET SLOT (ADR-036 OP-110). De schrijvers ketenen aan de laatste rij
                # ORDER BY timestamp DESC, id DESC en de verifier loopt de keten op diezelfde volgorde. Een
                # tijdstempel die VOOR het slot wordt gekozen, kan na die van een latere schrijver worden
                # geketend: op tijd VOOR hem, in de keten ACHTER hem, en dan meldt verify_chain manipulatie
                # op een gave keten. Binnen het slot is elke tijdstempel later dan die van de vorige
                # schrijver. De tijdstempel zit in de hash en staat er hier VOOR het hashen; wat er
                # gehasht wordt is niet veranderd. Zelfde vorm als AuditService.log_event.
                audit_entry.timestamp = datetime.now(timezone.utc)
                async with self._db.begin_nested():
                    from src.core.governance.hash_chain import HashChainVerifier  # noqa: PLC0415

                    async with ketencontext(self._db, tenant_id):
                        prev_result = await self._db.execute(
                            select(AuditLog.audit_hash)
                            .where(
                                AuditLog.tenant_id == tenant_id,
                                AuditLog.audit_hash.isnot(None),
                            )
                            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                            .limit(1)
                        )
                        _previous_hash: str | None = prev_result.scalar_one_or_none()
                    _verifier = HashChainVerifier(db_session=self._db)
                    audit_entry.previous_hash = _previous_hash
                    # Markeer WELK algoritme deze rij gebruikt, VOOR het hashen (ADR-036 OP-120).
                    # `mark_entry` schakelt alleen om als er een echte sleutel is; zonder sleutel blijft
                    # de rij op legacy SHA-256 in plaats van hard te falen en stil ongehasht te landen.
                    mark_entry(audit_entry)
                    audit_entry.audit_hash = _verifier._compute_hash(audit_entry, _previous_hash)
            except Exception as _e:
                logger.error(
                    "cookie_consent: hash chain populatie mislukt tenant %s: %s: %s",
                    tenant_id,
                    type(_e).__name__,
                    _e,
                    exc_info=True,
                )
                # audit_entry wordt alsnog weggeschreven zonder hash (degraded mode)
            # Een regel ZONDER keten (de ketenlookup faalde al voor het slot) heeft hier nog geen
            # tijdstempel. Die hoort niet in een keten en hoeft dus niet na een slot.
            if audit_entry.timestamp is None:
                audit_entry.timestamp = datetime.now(timezone.utc)
            self._db.add(audit_entry)
            await self._db.commit()
        except Exception as audit_exc:
            logger.error(
                "Consent audit log failed (consent already saved): %s: %s",
                type(audit_exc).__name__,
                audit_exc,
                exc_info=True,
            )
            await self._db.rollback()

        return result

    async def is_consent_given(
        self,
        user_id: str,
        tenant_id: int,
        category: ConsentCategory,
    ) -> bool:
        """
        Check if consent is given for a specific category.

        Essential category always returns True.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            category: ConsentCategory to check

        Returns:
            True if consent given, False otherwise
        """
        # Essential is always enabled
        if category == ConsentCategory.ESSENTIAL:
            return True

        # Get user's consent
        consent = await self.get_consent(user_id, tenant_id)

        # Check specific category
        if category == ConsentCategory.ANALYTICS:
            return consent.analytics
        elif category == ConsentCategory.MARKETING:
            return consent.marketing
        elif category == ConsentCategory.PERSONALIZATION:
            return consent.personalization

        return False

    async def get_consent_audit_trail(
        self,
        user_id: str,
        tenant_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get audit trail of consent changes for a user.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            limit: Maximum number of records to return

        Returns:
            List of audit log entries
        """
        result = await self._db.execute(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action == "consent.updated",
                AuditLog.resource == f"consent:user:{user_id}",
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
        )
        scalars_result = result.scalars()
        logs = scalars_result.all()

        return [
            {
                "timestamp": log.timestamp.isoformat(),
                "action": log.action,
                "details": log.details,
            }
            for log in logs
        ]

    async def has_consent_changed(
        self,
        user_id: str,
        tenant_id: int,
        new_preferences: dict[str, bool],
    ) -> bool:
        """
        Check if new preferences differ from stored preferences.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            new_preferences: Proposed new preferences

        Returns:
            True if different, False if same
        """
        current = await self.get_consent(user_id, tenant_id)

        return (
            current.analytics != new_preferences.get("analytics", current.analytics)
            or current.marketing != new_preferences.get("marketing", current.marketing)
            or current.personalization
            != new_preferences.get("personalization", current.personalization)
        )


# Module exports
__all__ = [
    "CookieConsentManager",
    "ConsentPreferences",
    "ConsentCategory",
    "UserConsentRecord",
]
