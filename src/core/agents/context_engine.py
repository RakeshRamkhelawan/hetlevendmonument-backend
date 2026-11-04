import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memory.services.context_packer_service import ContextPackerService

logger = logging.getLogger(__name__)

# Keys excluded from EnrichedContext.context:
# - profile: SQLAlchemy ORM object (not JSON-serializable)
# - tenant_id: must not leak outside ContextVar boundary (ADR-003)
# - built_at: datetime object (not JSON-serializable without custom encoder)
# - recent_episodes/top_facts/top_preferences: list[MemoryItem] ORM objects
_EXCLUDED_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "profile",
        "tenant_id",
        "built_at",
        "recent_episodes",
        "top_facts",
        "top_preferences",
    }
)


@dataclass
class EnrichedContext:
    # TODO(TYPE): replace Any with concrete type
    context: dict[str, Any] = field(
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    twin_profile: dict[str, Any] = field(
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    surface: str = ""
    query: str = ""


class AIContextEngine:
    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id

    async def enrich(
        self,
        agent_id: str,
        query: str,
        surface: str,
    ) -> EnrichedContext:
        try:
            packer = ContextPackerService(db=self._db, tenant_id=self._tenant_id)
            raw_context = await packer.build(agent_id=agent_id)
        except Exception as exc:
            logger.error(
                "AIContextEngine.enrich failed for tenant %d: %s",
                self._tenant_id,
                type(exc).__name__,
                exc_info=True,
            )
            return EnrichedContext(context={}, twin_profile={}, surface=surface, query=query)

        profile = raw_context.get("profile")
        twin_profile: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        if profile is not None:
            twin_profile = {
                "persona_name": getattr(profile, "persona_name", None),
                "persona_description": getattr(profile, "persona_description", None),
                "active_goals": getattr(profile, "active_goals", []),
                "operating_rules": getattr(profile, "operating_rules", []),
                "domain_expertise": getattr(profile, "domain_expertise", []),
                "agent_type": getattr(profile, "agent_type", None),
            }

        serializable_context = {
            k: v for k, v in raw_context.items() if k not in _EXCLUDED_CONTEXT_KEYS
        }
        return EnrichedContext(
            context=serializable_context,
            twin_profile=twin_profile,
            surface=surface,
            query=query,
        )
