"""
ProfileDriftEngine
==================

Detects when an agent's observed behaviour (captured in MemoryItems) has
diverged from its declared identity (AgentMemoryProfile.active_goals +
operating_rules).

Sprint D implementation -- heuristic drift detection without a separate model:

  Drift signal = weighted sum of three sub-signals:

  1. Goal coverage score  (0-1):
     Fraction of active_goals that appear in recent semantic/episodic memories.
     If the agent hasn't produced any memory aligned with a goal in N days,
     that goal is "drifted".

  2. Rule-violation score (0-1):
     Fraction of operating_rules whose keywords appear in recent contradicted /
     archived MemoryItems.  A rule violation signal = rule was broken recently.

  3. Activity gap score (0-1):
     How many days since the last MemoryItem was written for this agent.
     0.0 if < threshold, scales linearly to 1.0 at max_gap days.

  Combined: drift_score = 0.5 * goal_coverage_gap
                        + 0.3 * rule_violation
                        + 0.2 * activity_gap

Thresholds:
  score >= 0.7 -> severity=critical  -> triggers re-anchor
  score >= 0.4 -> severity=warning   -> logs + Prometheus
  score < 0.4  -> severity=none      -> no action

Re-anchor action:
  Creates a DriftEvent dict and optionally calls ContextPackerService to
  rebuild the profile snapshot.  This signals to the caller that a human
  or automated review is needed.

All queries are ALWAYS tenant-scoped.  This is non-negotiable.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memory.models import AgentMemoryProfile, MemoryItem
from src.domains.memory.observability import DRIFT_EVENTS, DRIFT_SCORE

logger = logging.getLogger(__name__)

# Configurable thresholds
_CRITICAL_THRESHOLD = 0.70
_WARNING_THRESHOLD = 0.40
_GOAL_LOOKBACK_DAYS = 30
_ACTIVITY_GAP_MAX_DAYS = 14  # 14 days of silence -> activity_gap = 1.0


class DriftEvent:
    """Value object describing a detected drift event."""

    __slots__ = (
        "tenant_id",
        "agent_id",
        "drift_score",
        "severity",
        "goal_coverage_gap",
        "rule_violation_score",
        "activity_gap_score",
        "missing_goals",
        "violated_rules",
        "last_activity",
        "detected_at",
    )

    tenant_id: int
    agent_id: str
    drift_score: float
    severity: str
    goal_coverage_gap: float
    rule_violation_score: float
    activity_gap_score: float
    missing_goals: list[str]
    violated_rules: list[str]
    last_activity: datetime | None
    detected_at: datetime

    def __init__(
        self,
        tenant_id: int,
        agent_id: str,
        drift_score: float,
        severity: str,
        goal_coverage_gap: float,
        rule_violation_score: float,
        activity_gap_score: float,
        missing_goals: list[str],
        violated_rules: list[str],
        last_activity: datetime | None,
        detected_at: datetime,
    ) -> None:
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.drift_score = drift_score
        self.severity = severity
        self.goal_coverage_gap = goal_coverage_gap
        self.rule_violation_score = rule_violation_score
        self.activity_gap_score = activity_gap_score
        self.missing_goals = missing_goals
        self.violated_rules = violated_rules
        self.last_activity = last_activity
        self.detected_at = detected_at

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        result: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for slot in self.__slots__:
            val = getattr(self, slot)
            if isinstance(val, datetime):
                val = val.isoformat()
            result[slot] = val
        return result


class ProfileDriftEngine:
    """
    Drift detection and re-anchor for a single agent/tenant pair.

    Usage:
        engine = ProfileDriftEngine(db=session, tenant_id=tenant_id)
        event = await engine.detect(agent_id="cva")
        if event and event.severity in ("warning", "critical"):
            await engine.re_anchor(event)
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def detect(self, agent_id: str) -> DriftEvent | None:
        """
        Compute the current drift score for agent_id.

        Returns a DriftEvent (always), or None if no profile exists.
        """
        profile = await self._load_profile(agent_id)
        if not profile:
            logger.debug(f"DriftEngine: no profile for {agent_id}, skipping")
            return None

        recent_items = await self._load_recent_items(agent_id, days=_GOAL_LOOKBACK_DAYS)
        recent_content = " ".join(item.content.lower() for item in recent_items)

        # Sub-signal 1: goal coverage gap
        active_goals: list[Any] = profile.active_goals or []  # TODO(TYPE): replace Any with concrete type
        missing_goals: list[str] = []
        if active_goals:
            for goal in active_goals:
                goal_text = str(goal).lower()
                # Check if any keyword from the goal appears in recent memory
                keywords = _extract_keywords(goal_text)
                if not any(kw in recent_content for kw in keywords):
                    missing_goals.append(str(goal))
            goal_coverage_gap = len(missing_goals) / len(active_goals)
        else:
            goal_coverage_gap = 0.0

        # Sub-signal 2: rule-violation score
        rules: list[Any] = profile.operating_rules or []  # TODO(TYPE): replace Any with concrete type
        violated_rules: list[str] = []
        if rules:
            violated_items = await self._load_violated_items(agent_id)
            violated_content = " ".join(i.content.lower() for i in violated_items)
            for rule in rules:
                rule_text = str(rule).lower()
                keywords = _extract_keywords(rule_text)
                if any(kw in violated_content for kw in keywords):
                    violated_rules.append(str(rule))
            rule_violation_score = len(violated_rules) / len(rules)
        else:
            rule_violation_score = 0.0

        # Sub-signal 3: activity gap
        last_activity = await self._last_activity(agent_id)
        if last_activity is None:
            activity_gap_score = 1.0
        else:
            now = datetime.now(timezone.utc)
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            gap_days = (now - last_activity).days
            activity_gap_score = min(1.0, gap_days / _ACTIVITY_GAP_MAX_DAYS)

        # Combined score
        drift_score = (
            0.5 * goal_coverage_gap + 0.3 * rule_violation_score + 0.2 * activity_gap_score
        )

        if drift_score >= _CRITICAL_THRESHOLD:
            severity = "critical"
        elif drift_score >= _WARNING_THRESHOLD:
            severity = "warning"
        else:
            severity = "none"

        event = DriftEvent(
            tenant_id=self._tenant_id,
            agent_id=agent_id,
            drift_score=round(drift_score, 4),
            severity=severity,
            goal_coverage_gap=round(goal_coverage_gap, 4),
            rule_violation_score=round(rule_violation_score, 4),
            activity_gap_score=round(activity_gap_score, 4),
            missing_goals=missing_goals,
            violated_rules=violated_rules,
            last_activity=last_activity,
            detected_at=datetime.now(timezone.utc),
        )

        # Prometheus
        try:
            DRIFT_SCORE.labels(tenant_id=str(self._tenant_id), agent_id=agent_id).set(drift_score)
            if severity != "none":
                DRIFT_EVENTS.labels(
                    tenant_id=str(self._tenant_id),
                    agent_id=agent_id,
                    severity=severity,
                ).inc()
        except Exception:
            pass

        logger.info(
            "DriftEngine: drift detection complete",
            extra={
                "tenant_id": self._tenant_id,
                "agent_id": agent_id,
                "drift_score": drift_score,
                "severity": severity,
                "missing_goals": len(missing_goals),
                "violated_rules": len(violated_rules),
            },
        )
        return event

    async def re_anchor(
        self,
        event: DriftEvent,
        changed_by_user_id: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Re-anchor the agent's profile by writing a snapshot that documents
        the drift and marks the profile as reviewed.

        Actions:
          1. Load current profile
          2. Write a snapshot with change_reason='drift_re_anchor'
             and the drift event data embedded in the snapshot
          3. Bump profile_version

        Returns a summary dict for the API response.
        """
        from src.domains.memory.models import AgentProfileSnapshot

        profile = await self._load_profile(event.agent_id)
        if not profile:
            return {"status": "no_profile", "agent_id": event.agent_id}

        profile.profile_version = (profile.profile_version or 1) + 1
        await self._db.flush()

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
                "drift_event": event.to_dict(),
            },
            changed_by_user_id=changed_by_user_id,
            change_reason="drift_re_anchor",
        )
        self._db.add(snapshot)
        await self._db.flush()

        logger.warning(
            "DriftEngine: re-anchor completed",
            extra={
                "tenant_id": self._tenant_id,
                "agent_id": event.agent_id,
                "drift_score": event.drift_score,
                "new_version": profile.profile_version,
            },
        )

        return {
            "status": "re_anchored",
            "agent_id": event.agent_id,
            "drift_score": event.drift_score,
            "severity": event.severity,
            "new_profile_version": profile.profile_version,
            "snapshot_id": snapshot.id,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_profile(self, agent_id: str) -> AgentMemoryProfile | None:
        result = await self._db.execute(
            select(AgentMemoryProfile).where(
                AgentMemoryProfile.tenant_id == self._tenant_id,
                AgentMemoryProfile.agent_id == agent_id,
                AgentMemoryProfile.is_active.is_(True),
                AgentMemoryProfile.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _load_recent_items(self, agent_id: str, days: int) -> list[MemoryItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._db.execute(
            select(MemoryItem)
            .where(
                MemoryItem.tenant_id == self._tenant_id,
                MemoryItem.agent_id == agent_id,
                MemoryItem.status == "accepted",
                MemoryItem.deleted_at.is_(None),
                MemoryItem.created_at >= cutoff,
            )
            .order_by(desc(MemoryItem.created_at))
            .limit(100)
        )
        return list(result.scalars().all())

    async def _load_violated_items(self, agent_id: str) -> list[MemoryItem]:
        """Items that were contradicted or archived -- possible rule violations."""
        result = await self._db.execute(
            select(MemoryItem)
            .where(
                MemoryItem.tenant_id == self._tenant_id,
                MemoryItem.agent_id == agent_id,
                MemoryItem.status.in_(["contradicted", "archived"]),
                MemoryItem.deleted_at.is_(None),
            )
            .order_by(desc(MemoryItem.updated_at))
            .limit(50)
        )
        return list(result.scalars().all())

    async def _last_activity(self, agent_id: str) -> datetime | None:
        result = await self._db.execute(
            select(func.max(MemoryItem.created_at)).where(
                MemoryItem.tenant_id == self._tenant_id,
                MemoryItem.agent_id == agent_id,
                MemoryItem.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


def _extract_keywords(text: str, min_len: int = 4) -> list[str]:
    """
    Extract meaningful keywords from a goal/rule string.

    Strips stop words and returns lowercased tokens of at least min_len chars.
    """
    _STOP = {
        "that",
        "this",
        "with",
        "from",
        "have",
        "will",
        "been",
        "should",
        "must",
        "only",
        "when",
        "then",
        "also",
        "always",
        "never",
        "every",
        "each",
    }
    tokens = re.findall(r"\b[a-z]+\b", text.lower())
    return [t for t in tokens if len(t) >= min_len and t not in _STOP]
