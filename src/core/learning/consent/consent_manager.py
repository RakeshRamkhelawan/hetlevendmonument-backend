"""
TwinConsentManager -- GDPR-compliant consent management voor de digital twin.

GDPR artikelen:
- Artikel 7:  Expliciete toestemming (opt-in model, default=disabled)
- Artikel 17: Right to Erasure (hard_delete_requested vlag + cascade delete)
- Artikel 20: Data Portability (export als JSON)

De manager werkt met de UserTwinConsent model in de database.
Cache in Redis (TTL=300s) om DB-round-trips te minimaliseren.

Gebruik:
    mgr = TwinConsentManager(db=session)
    enabled = await mgr.is_tracking_enabled(user_id="u1", tenant_id=1)
    await mgr.set_consent_status(user_id="u1", tenant_id=1, status=TwinConsentStatus.DISABLED)
    await mgr.hard_delete(user_id="u1", tenant_id=1)
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.shared.events.governance_bus import governance_bus
from src.core.shared.events.governance_events import ConsentAuditEvent
from src.core.learning.twin_models import (
    UserBehaviorObservation,
    UserCognitiveProfile,
    UserTwinConsent,
)
from src.core.utils.best_effort import best_effort


@dataclass
class ConsentCategories:
    """Granular consent categories for digital twin tracking."""

    behavior_tracking: bool = False
    profile_aggregation: bool = False
    ai_interventions: bool = False
    cross_session_memory: bool = False


class TwinConsentStatus(str, Enum):
    ENABLED = "enabled"  # User explicitly opted in -- tracking active
    DISABLED = "disabled"  # Default state: opt-in required (GDPR Art. 7)
    PAUSED = "paused"  # Tijdelijke pauze


class TwinConsentManager:
    """
    Beheer user consent voor de digital twin.

    Args:
        db: SQLAlchemy AsyncSession (vereist voor DB operaties)
        cache: Optionele Redis client voor consent caching
    """

    _CACHE_TTL = 300  # 5 minuten

    def __init__(
        self,
        db: AsyncSession,
        cache: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ):
        self._db = db
        self._cache = cache

    # --- Consent lezen --------------------------------------------------------

    async def get_consent_status(
        self,
        user_id: str,
        tenant_id: int,
    ) -> TwinConsentStatus:
        """
        Geef de huidige consent status voor een user.

        Default: DISABLED (opt-in model).
        """
        # Check cache eerst
        if self._cache is not None:
            try:
                cached = await self._cache.get(self._cache_key(user_id, tenant_id))
                if cached:
                    return TwinConsentStatus(
                        cached.decode() if isinstance(cached, bytes) else cached
                    )
            except Exception as exc:
                logger.debug("consent_cache_miss", error=str(exc))

        # DB lookup
        record = await self._get_or_create_consent(user_id, tenant_id)

        if record.hard_delete_requested:
            return TwinConsentStatus.DISABLED

        raw_status = getattr(record, "status", None)
        if raw_status is not None:
            try:
                status = TwinConsentStatus(raw_status)
            except ValueError:
                status = TwinConsentStatus.DISABLED
        else:
            status = (
                TwinConsentStatus.ENABLED if record.consent_given else TwinConsentStatus.DISABLED
            )

        # Update cache
        if self._cache is not None:
            try:
                await self._cache.setex(
                    self._cache_key(user_id, tenant_id),
                    self._CACHE_TTL,
                    status.value,
                )
            except Exception as exc:
                logger.debug("consent_cache_set_failed", error=str(exc))

        return status

    async def is_tracking_enabled(self, user_id: str, tenant_id: int) -> bool:
        """Snelle check: is behavior tracking aan voor deze user?"""
        categories = await self.get_consent_categories(user_id, tenant_id)
        return categories.behavior_tracking

    # --- Consent wijzigen -----------------------------------------------------

    async def get_consent_categories(
        self,
        user_id: str,
        tenant_id: int,
    ) -> ConsentCategories:
        """Geef de huidige granular consent categories voor een user."""
        record = await self._get_or_create_consent(user_id, tenant_id)
        return ConsentCategories(
            behavior_tracking=record.behavior_tracking,
            profile_aggregation=record.profile_aggregation,
            ai_interventions=record.ai_interventions,
            cross_session_memory=record.cross_session_memory,
        )

    async def set_consent_categories(
        self,
        user_id: str,
        tenant_id: int,
        categories: ConsentCategories,
    ) -> None:
        """Update granular consent categories voor een user."""
        record = await self._get_or_create_consent(user_id, tenant_id)
        record.behavior_tracking = categories.behavior_tracking
        record.profile_aggregation = categories.profile_aggregation
        record.ai_interventions = categories.ai_interventions
        record.cross_session_memory = categories.cross_session_memory
        # Backward compat: consent_given mirrors all four
        record.consent_given = (
            categories.behavior_tracking
            and categories.profile_aggregation
            and categories.ai_interventions
            and categories.cross_session_memory
        )
        # Sync legacy status field
        if record.consent_given:
            record.status = "enabled"
        elif (
            categories.profile_aggregation
            or categories.ai_interventions
            or categories.cross_session_memory
        ):
            record.status = "paused"
        else:
            record.status = "disabled"
        await self._db.flush()

        # Invalideer cache
        if self._cache is not None:
            try:
                await self._cache.delete(self._cache_key(user_id, tenant_id))
            except Exception:
                pass

        logger.info(
            "consent_categories_updated",
            user_id=user_id,
            tenant_id=tenant_id,
            behavior_tracking=categories.behavior_tracking,
            profile_aggregation=categories.profile_aggregation,
            ai_interventions=categories.ai_interventions,
            cross_session_memory=categories.cross_session_memory,
        )

        # Audit trail -- no db_session passed because primary data is not yet
        # committed (outer caller commits). best_effort uses a fresh session so
        # an audit failure cannot roll back the consent change (C-2 fix).
        async with best_effort("TWIN_CONSENT_CHANGED audit"):
            await governance_bus.emit(
                ConsentAuditEvent(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="TWIN_CONSENT_CHANGED",
                    consent_type=f"twin:consent:{tenant_id}:{user_id}",
                    details={
                        "behavior_tracking": categories.behavior_tracking,
                        "profile_aggregation": categories.profile_aggregation,
                        "ai_interventions": categories.ai_interventions,
                        "cross_session_memory": categories.cross_session_memory,
                    },
                )
            )

    async def set_consent_status(
        self,
        user_id: str,
        tenant_id: int,
        status: TwinConsentStatus,
    ) -> None:
        """
        Update de consent status voor een user (legacy convenience layer).

        Maps to granular categories:
        - ENABLED: all four True
        - DISABLED: all four False
        - PAUSED: behavior_tracking False, rest True
        """
        record = await self._get_or_create_consent(user_id, tenant_id)
        record.status = status.value
        if status == TwinConsentStatus.ENABLED:
            record.behavior_tracking = True
            record.profile_aggregation = True
            record.ai_interventions = True
            record.cross_session_memory = True
            record.consent_given = True
        elif status == TwinConsentStatus.DISABLED:
            record.behavior_tracking = False
            record.profile_aggregation = False
            record.ai_interventions = False
            record.cross_session_memory = False
            record.consent_given = False
        elif status == TwinConsentStatus.PAUSED:
            record.behavior_tracking = False
            record.profile_aggregation = True
            record.ai_interventions = True
            record.cross_session_memory = True
            record.consent_given = False
        await self._db.flush()

        # Invalideer cache
        if self._cache is not None:
            try:
                await self._cache.delete(self._cache_key(user_id, tenant_id))
            except Exception:
                pass

        logger.info(
            "consent_status_updated",
            user_id=user_id,
            tenant_id=tenant_id,
            new_status=status.value,
        )

    # --- GDPR Artikel 17: Right to Erasure ------------------------------------

    async def request_hard_delete(
        self,
        user_id: str,
        tenant_id: int,
    ) -> None:
        """
        Markeer voor Right to Erasure (GDPR Artikel 17).

        Stap 1: zet vlag -- de daadwerkelijke verwijdering gebeurt via
        de cleanup-job (emergency_twin_purge of scheduled cleanup).
        """
        record = await self._get_or_create_consent(user_id, tenant_id)
        record.hard_delete_requested = True
        record.hard_delete_requested_at = datetime.now(timezone.utc)
        record.consent_given = False
        await self._db.flush()

        logger.info(
            "hard_delete_requested",
            user_id=user_id,
            tenant_id=tenant_id,
        )

    async def hard_delete(
        self,
        user_id: str,
        tenant_id: int,
    ) -> dict[str, int]:
        """
        Verwijder ALLE twin data voor een user (GDPR Artikel 17).

        Verwijdert:
        - UserBehaviorObservation records
        - UserCognitiveProfile record
        - UserTwinConsent record

        Returns:
            Dict met aantal verwijderde records per tabel.
        """
        result: dict[str, int] = {}

        # Verwijder observaties (human_user_id is hashed in the DB)
        from src.core.learning.privacy.privacy_filter import PrivacyFilter

        hashed_user_id = PrivacyFilter.hash_user_id(user_id, tenant_id)
        await self._db.execute(
            delete(UserBehaviorObservation).where(
                UserBehaviorObservation.human_user_id == hashed_user_id,
                UserBehaviorObservation.tenant_id == tenant_id,
            )
        )
        result["observations"] = -1  # rowcount niet betrouwbaar via async

        # Verwijder cognitief profiel (human_user_id is NOT hashed here)
        await self._db.execute(
            delete(UserCognitiveProfile).where(
                UserCognitiveProfile.human_user_id == user_id,
                UserCognitiveProfile.tenant_id == tenant_id,
            )
        )
        result["profiles"] = -1

        # Verwijder consent record
        await self._db.execute(
            delete(UserTwinConsent).where(
                UserTwinConsent.human_user_id == user_id,
                UserTwinConsent.tenant_id == tenant_id,
            )
        )
        result["consent"] = -1

        # Verwijder suggestion logs (user_id is NOT hashed here)
        from src.core.learning.twin_models import TwinSuggestionLog

        await self._db.execute(
            delete(TwinSuggestionLog).where(
                TwinSuggestionLog.user_id == user_id,
                TwinSuggestionLog.tenant_id == tenant_id,
            )
        )
        result["suggestion_logs"] = -1

        await self._db.flush()
        # CRITICAL: commit deletes before any best_effort block that carries
        # db_session -- a rollback AFTER this point only affects audit entries,
        # not the GDPR erasure that already landed (ADR-026 S.2, AVG Art. 17).
        await self._db.commit()

        # Invalideer cache
        if self._cache is not None:
            try:
                await self._cache.delete(self._cache_key(user_id, tenant_id))
            except Exception:
                pass

        logger.info(
            "hard_delete_executed",
            user_id=user_id,
            tenant_id=tenant_id,
            deleted=result,
        )

        # Audit: erasure INITIATED -- handler creates its own session (C-1 fix preserved).
        async with best_effort("TWIN_HARD_DELETE_INITIATED audit"):
            await governance_bus.emit(
                ConsentAuditEvent(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="TWIN_HARD_DELETE_INITIATED",
                    consent_type=f"twin:user:{tenant_id}:{user_id}",
                    details={"user_id": user_id},
                )
            )

        # Audit: erasure completed -- handler creates its own session.
        async with best_effort("TWIN_HARD_DELETE_COMPLETED audit"):
            await governance_bus.emit(
                ConsentAuditEvent(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="TWIN_HARD_DELETE_COMPLETED",
                    consent_type=f"twin:user:{tenant_id}:{user_id}",
                    details={"deleted": result},
                )
            )

        return result

    # --- GDPR Artikel 20: Data Portability ------------------------------------

    async def export_user_data(
        self,
        user_id: str,
        tenant_id: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Exporteer alle twin data voor een user (GDPR Artikel 20).

        Returns:
            JSON-serialiseerbaar dict met alle twin data.
        """
        # Observaties (human_user_id is hashed in the DB)
        from src.core.learning.privacy.privacy_filter import PrivacyFilter

        hashed_user_id = PrivacyFilter.hash_user_id(user_id, tenant_id)
        obs_result = await self._db.execute(
            select(UserBehaviorObservation).where(
                UserBehaviorObservation.human_user_id == hashed_user_id,
                UserBehaviorObservation.tenant_id == tenant_id,
            )
        )
        observations = obs_result.scalars().all()

        # Profiel (human_user_id is NOT hashed in the profile table)
        profile_result = await self._db.execute(
            select(UserCognitiveProfile).where(
                UserCognitiveProfile.human_user_id == user_id,
                UserCognitiveProfile.tenant_id == tenant_id,
            )
        )
        profile = profile_result.scalar_one_or_none()

        logger.info(
            "twin_data_exported",
            user_id=user_id,
            tenant_id=tenant_id,
            observation_count=len(observations),
        )

        async with best_effort("TWIN_DATA_EXPORTED audit"):
            await governance_bus.emit(
                ConsentAuditEvent(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action="TWIN_DATA_EXPORTED",
                    consent_type=f"twin:user:{tenant_id}:{user_id}",
                    details={"observation_count": len(observations)},
                )
            )

        return {
            "user_id": user_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "observations": [
                {
                    "behavior_type": o.behavior_type,
                    "session_id": o.session_id,
                    "context": o.context,
                    "outcome_metrics": o.outcome_metrics,
                    "confidence_score": o.confidence_score,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in observations
            ],
            "cognitive_profile": {
                "coding_style": profile.coding_style if profile else None,
                "work_patterns": profile.work_patterns if profile else None,
                "blind_spots": profile.blind_spots if profile else None,
                "strengths": profile.strengths if profile else None,
                "confidence_level": profile.confidence_level if profile else 0.0,
                "observation_count": profile.observation_count if profile else 0,
            },
        }

    # --- Helpers --------------------------------------------------------------

    async def _get_or_create_consent(self, user_id: str, tenant_id: int) -> UserTwinConsent:
        """Haal consent record op, maak aan als het niet bestaat."""
        result = await self._db.execute(
            select(UserTwinConsent).where(
                UserTwinConsent.human_user_id == user_id,
                UserTwinConsent.tenant_id == tenant_id,
            )
        )
        record = result.scalar_one_or_none()

        if record is None:
            record = UserTwinConsent(
                human_user_id=user_id,
                tenant_id=tenant_id,
                consent_given=False,
                status="disabled",
                consent_version="1.0",
                behavior_tracking=False,
                profile_aggregation=False,
                ai_interventions=False,
                cross_session_memory=False,
            )
            self._db.add(record)
            await self._db.flush()

        return record

    @staticmethod
    def _cache_key(user_id: str, tenant_id: int) -> str:
        return f"twin:consent:{tenant_id}:{user_id}"
