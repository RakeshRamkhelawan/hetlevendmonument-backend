"""
ContextPackerService
====================

Builds a structured boot context injected at agent session start.

This is what makes the digital twin feel like it "knows" things across sessions.
The packer assembles:
  1. Agent identity profile (persona, goals, rules)
  2. Recent episodic memories (last 7 days)
  3. Top semantic facts (by importance + confidence)
  4. Top preferences (user/tenant preferences)

Token budget is respected: items are included in priority order until
the estimated token count reaches the configured budget.

Sprint A: simple priority-based packing.
Sprint B: add semantic relevance scoring against session topic.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memory.models import AgentMemoryProfile, AgentProfileSnapshot, MemoryItem
from src.domains.memory.services.memory_retrieval_service import MemoryRetrievalService

logger = logging.getLogger(__name__)

# Rough token estimate: 1 token ~= 4 chars
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


class ContextPackerService:
    """
    Builds boot context for a given agent in a given tenant.

    Usage:
        packer = ContextPackerService(db=session, tenant_id=tenant_id)
        ctx = await packer.build(agent_id="cva", token_budget=2000)
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._retrieval = MemoryRetrievalService(db=db, tenant_id=tenant_id)

    async def build(
        self,
        agent_id: str,
        session_id: int | None = None,
        token_budget: int = 2000,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Build and return a structured boot context dict.

        Priority order (most important first):
          1. Identity profile (goals + rules)
          2. Active goals (top 5)
          3. Recent episodes (last 7 days, top 10)
          4. Top semantic facts (top 15)
          5. Top preferences (top 10)

        Stops adding items when token_budget is exceeded.
        """
        tokens_used = 0
        remaining = token_budget

        # 1. Load identity profile
        profile = await self._load_profile(agent_id)
        profile_tokens = 0
        if profile:
            profile_tokens = _estimate_tokens(profile.persona_description or "") + 100
            tokens_used += profile_tokens
            remaining -= profile_tokens

        # 2. Active goals from profile (already in profile, no extra fetch)
        active_goals: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if profile and profile.active_goals:
            active_goals = profile.active_goals[:5]
            goal_tokens = sum(_estimate_tokens(str(g)) for g in active_goals)
            tokens_used += goal_tokens
            remaining -= goal_tokens

        # 3. Recent episodic memories
        recent_episodes: list[MemoryItem] = []
        if remaining > 200:
            episodes_raw = await self._retrieval.get_recent_episodes(
                agent_id=agent_id, days=7, limit=10
            )
            for ep in episodes_raw:
                ep_tokens = _estimate_tokens(ep.content)
                if ep_tokens > remaining:
                    break
                recent_episodes.append(ep)
                remaining -= ep_tokens
                tokens_used += ep_tokens

        # 4. Top semantic facts
        top_facts: list[MemoryItem] = []
        if remaining > 100:
            facts_raw = await self._retrieval.get_by_type(
                agent_id=agent_id,
                memory_types=["semantic"],
                limit=15,
            )
            for fact in facts_raw:
                fact_tokens = _estimate_tokens(fact.content)
                if fact_tokens > remaining:
                    break
                top_facts.append(fact)
                remaining -= fact_tokens
                tokens_used += fact_tokens

        # 5. Preferences
        top_preferences: list[MemoryItem] = []
        if remaining > 50:
            prefs_raw = await self._retrieval.get_by_type(
                agent_id=agent_id,
                memory_types=["preference"],
                limit=10,
            )
            for pref in prefs_raw:
                pref_tokens = _estimate_tokens(pref.content)
                if pref_tokens > remaining:
                    break
                top_preferences.append(pref)
                remaining -= pref_tokens
                tokens_used += pref_tokens

        logger.info(
            "ContextPackerService: boot context built",
            extra={
                "tenant_id": self._tenant_id,
                "agent_id": agent_id,
                "token_budget": token_budget,
                "tokens_used": tokens_used,
                "episodes": len(recent_episodes),
                "facts": len(top_facts),
                "prefs": len(top_preferences),
            },
        )

        return {
            "agent_id": agent_id,
            "tenant_id": self._tenant_id,
            "profile": profile,
            "active_goals": active_goals,
            "recent_episodes": recent_episodes,
            "top_facts": top_facts,
            "top_preferences": top_preferences,
            "estimated_tokens": tokens_used,
            "built_at": datetime.now(timezone.utc),
        }

    async def upsert_profile(
        self,
        agent_id: str,
        agent_type: str | None = None,
        persona_name: str | None = None,
        persona_description: str | None = None,
        active_goals: list[Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        operating_rules: list[Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        domain_expertise: list[Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        owner_user_id: int | None = None,
    ) -> AgentMemoryProfile:
        """
        Create or update an AgentMemoryProfile.
        Increments profile_version on every update.
        """
        existing = await self._load_profile(agent_id)

        if existing:
            # Update only provided fields
            if agent_type is not None:
                existing.agent_type = agent_type
            if persona_name is not None:
                existing.persona_name = persona_name
            if persona_description is not None:
                existing.persona_description = persona_description
            if active_goals is not None:
                existing.active_goals = active_goals
            if operating_rules is not None:
                existing.operating_rules = operating_rules
            if domain_expertise is not None:
                existing.domain_expertise = domain_expertise
            if owner_user_id is not None:
                existing.owner_user_id = owner_user_id
            existing.profile_version = (existing.profile_version or 1) + 1
            await self._db.flush()
            await self._write_snapshot(existing)
            return existing

        # Create new profile
        profile = AgentMemoryProfile(
            tenant_id=self._tenant_id,
            agent_id=agent_id,
            agent_type=agent_type,
            persona_name=persona_name,
            persona_description=persona_description,
            active_goals=active_goals or [],
            operating_rules=operating_rules or [],
            domain_expertise=domain_expertise or [],
            owner_user_id=owner_user_id,
            is_active=True,
            profile_version=1,
        )
        self._db.add(profile)
        await self._db.flush()
        await self._write_snapshot(profile)
        return profile

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _write_snapshot(self, profile: AgentMemoryProfile) -> None:
        """Write an immutable snapshot of the current profile state."""
        snapshot = AgentProfileSnapshot(
            tenant_id=self._tenant_id,
            profile_id=profile.id,
            agent_id=profile.agent_id,
            profile_version=profile.profile_version,
            snapshot={
                "active_goals": profile.active_goals,
                "operating_rules": profile.operating_rules,
                "domain_expertise": profile.domain_expertise,
                "persona_name": profile.persona_name,
                "persona_description": profile.persona_description,
            },
            change_reason="upsert",
        )
        self._db.add(snapshot)
        await self._db.flush()

    async def _load_profile(self, agent_id: str) -> AgentMemoryProfile | None:
        """Load the active profile for this agent/tenant."""
        result = await self._db.execute(
            select(AgentMemoryProfile).where(
                AgentMemoryProfile.tenant_id == self._tenant_id,
                AgentMemoryProfile.agent_id == agent_id,
                AgentMemoryProfile.is_active.is_(True),
                AgentMemoryProfile.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
