"""
Adaptation Service - Handles adaptation rule creation and application.

This service is responsible for:
- Creating adaptation rules from patterns
- Managing adaptation rule lifecycle
- Applying adaptations based on context
- Tracking adaptation success/failure
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from src.core.shared.learning_audit import log_learning_audit_event
from src.core.learning.metrics import record_learning_adaptation_applied
from src.core.shared.config import get_feature_flag

if TYPE_CHECKING:
    from src.core.agents.learning_loop import AdaptationRule, LearningPattern, LearningRepository

logger = logging.getLogger(__name__)


class AdaptationService:
    """Service for managing adaptation rules."""

    def __init__(
        self,
        tenant_id: int,
        repository: Optional["LearningRepository"] = None,
    ) -> None:
        self.tenant_id = tenant_id
        self._repository = repository

        # In-memory storage
        self.rules: dict[str, "AdaptationRule"] = {}

        # Metrics
        self.rules_created = 0
        self.rules_applied = 0

    async def create_from_pattern(
        self,
        pattern: "LearningPattern",
    ) -> "AdaptationRule":
        """Create an adaptation rule from a learned pattern.

        P1 FIX: Uses write-ahead pattern - database write happens BEFORE
        in-memory update to ensure consistency.

        Args:
            pattern: The pattern to create a rule from

        Returns:
            The created AdaptationRule

        Raises:
            RuntimeError: If database persistence fails
        """
        from src.core.agents.learning_loop import AdaptationRule

        rule_id = str(uuid.uuid4())

        rule = AdaptationRule(
            id=rule_id,
            name=f"Adaptation for {pattern.pattern_type}",
            condition=json.dumps(pattern.trigger_conditions),
            action=json.dumps(pattern.learned_behavior),
            parameters={
                "pattern_id": pattern.id,
                "confidence_threshold": pattern.confidence_score,
                "success_rate_threshold": pattern.success_rate,
                "user_id": pattern.trigger_conditions.get("user_id"),
            },
            success_metrics=["improvement_rate", "success_rate", "efficiency_gain"],
            active=True,
            created_at=datetime.now(timezone.utc),
        )

        # P1 FIX: Write-ahead pattern - persist to database FIRST
        if self._repository:
            try:
                await self._repository.save_rule(self.tenant_id, rule)
            except Exception as exc:
                logger.error("Failed to persist rule %s: %s", rule_id, exc)
                raise RuntimeError(f"Failed to persist adaptation rule: {exc}") from exc

        # Only update in-memory state AFTER successful DB write
        self.rules[rule_id] = rule
        self.rules_created += 1

        logger.info("Adaptation rule created: %s", rule_id)
        return rule

    async def apply(
        self,
        rule_id: str,
        context: dict[str, object],
    ) -> dict[str, object]:
        """Apply an adaptation rule.

        Args:
            rule_id: ID of the rule to apply
            context: Current context for rule evaluation

        Returns:
            Result of the adaptation application
        """
        if not get_feature_flag("learning_enabled"):
            return {"success": False, "reason": "Learning disabled"}

        rule = self.rules.get(rule_id)
        if not rule or not rule.active:
            return {"success": False, "error": "Rule not found or inactive"}

        try:
            # Evaluate condition
            condition = json.loads(rule.condition)
            if not self._evaluate_condition(condition, context):
                return {"success": False, "reason": "Condition not met"}

            # Apply action
            action = json.loads(rule.action)
            result = self._apply_action(action, context)

            # Update metrics
            rule.trigger_count += 1
            if result.get("success"):
                rule.success_count += 1

            # Persist updated stats
            if self._repository:
                try:
                    await self._repository.increment_rule_stats(
                        rule_id,
                        applied_successfully=bool(result.get("success", False)),
                    )
                except Exception as exc:
                    logger.error("Failed to update rule stats: %s", exc)
                    # Don't raise - stats update failure shouldn't break the flow

            self.rules_applied += 1
            record_learning_adaptation_applied(
                self.tenant_id, success=bool(result.get("success", False))
            )
            await log_learning_audit_event(
                action="learning.adaptation_applied",
                tenant_id=self.tenant_id,
                resource=f"rule:{rule_id}",
                details={"success": bool(result.get("success", False)), "context": context},
            )

            return {
                "success": True,
                "rule_id": rule_id,
                "action_applied": action,
                "result": result,
            }

        except Exception as exc:
            logger.error("Failed to apply rule %s: %s", rule_id, exc)
            return {"success": False, "error": str(exc)}

    def _evaluate_condition(
        self,
        condition: dict[str, object],
        context: dict[str, object],
    ) -> bool:
        """Evaluate if condition is met in context."""
        # Simplified condition evaluation
        for key, value in condition.items():
            if key not in context:
                return False
            if context[key] != value:
                return False
        return True

    def _apply_action(
        self,
        action: dict[str, object],
        context: dict[str, object],
    ) -> dict[str, object]:
        """Apply the action to the context."""
        # Simplified action application
        return {
            "success": True,
            "modifications": action,
            "context_before": context.copy(),
        }

    def get_active_rules(self) -> list["AdaptationRule"]:
        """Get all active rules sorted by priority."""
        active = [r for r in self.rules.values() if r.active]
        return sorted(active, key=lambda r: getattr(r, "priority", 0), reverse=True)

    def get_relevant_rules(self, context: dict[str, object]) -> list["AdaptationRule"]:
        """Return active rules whose conditions match the supplied context."""
        relevant: list["AdaptationRule"] = []
        for rule in self.get_active_rules():
            try:
                condition = json.loads(rule.condition)
            except (json.JSONDecodeError, TypeError):
                continue
            if self._evaluate_condition(condition, context):
                relevant.append(rule)
        return relevant

    def get_rule(self, rule_id: str) -> Optional["AdaptationRule"]:
        """Get a specific rule by ID."""
        return self.rules.get(rule_id)

    async def deactivate(self, rule_id: str) -> bool:
        """Deactivate a rule."""
        rule = self.rules.get(rule_id)
        if rule:
            rule.active = False
            # Persist deactivation
            if self._repository:
                try:
                    # Note: This would need a method to update rule status
                    pass
                except Exception as exc:
                    logger.error("Failed to deactivate rule: %s", exc)
            return True
        return False

    async def load_from_db(self) -> None:
        """Load rules from database."""
        if not self._repository:
            return

        try:
            rules = await self._repository.get_active_rules(self.tenant_id)
            for rule in rules:
                self.rules[rule.id] = rule
            logger.info(
                "Loaded %d rules from database for tenant %s",
                len(rules),
                self.tenant_id,
            )
        except Exception as exc:
            logger.error("Failed to load rules from database: %s", exc)
            raise
