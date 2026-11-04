"""
Mode Manager - CVA operational mode management.

Handles mode switching, history tracking, and mode-specific context
initialization for the Ultimate CVA Agent.

Usage:
    manager = ModeManager(db_fetcher)
    optimal_mode = manager.determine_optimal_mode(parsed_command, trigger_type)
    await manager.switch_mode(optimal_mode, reason="User request")
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from collections.abc import Callable

from loguru import logger

from .models import CVAMode, IntentType, ParsedCommand


class ModeManager:
    """Manages CVA operational modes with history and context tracking."""

    def __init__(
        self,
        dashboard_fetcher: Callable[..., Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        max_history: int = 50,
    ) -> None:
        """
        Initialize mode manager.

        Args:
            dashboard_fetcher: Async callable to fetch dashboard data for CEO mode
            max_history: Maximum mode transitions to keep in history
        """
        self.current_mode = CVAMode.CEO_MODE
        self.mode_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.mode_context: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.max_history = max_history
        self._dashboard_fetcher = dashboard_fetcher
        self._lock = asyncio.Lock()

    def determine_optimal_mode(
        self,
        parsed_command: ParsedCommand,
        trigger_type: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> CVAMode:
        """Determine optimal mode based on trigger type and command."""
        # Try TriggerType-based mapping first
        if trigger_type:
            mode = self._mode_from_trigger_type(trigger_type)
            if mode:
                logger.debug(f"Mode from TriggerType: {mode.value}")
                return mode

        # Fall back to intent-based selection
        return self._mode_from_intent(parsed_command)

    def _mode_from_trigger_type(self, trigger_type: Any) -> CVAMode | None:  # TODO(TYPE): replace Any with concrete type
        """Map TriggerType to CVAMode."""
        try:
            from src.core.agents.cva_autonomous_trigger import TriggerType

            mode_map = {
                TriggerType.EMERGENCY: CVAMode.CEO_MODE,
                TriggerType.SCHEDULED: CVAMode.PROACTIVE,
                TriggerType.EVENT_DRIVEN: CVAMode.REACTIVE,
                TriggerType.INTELLIGENT: CVAMode.AUTONOMOUS,
                TriggerType.USER_INITIATED: CVAMode.REACTIVE,
            }
            return mode_map.get(trigger_type)
        except ImportError:
            logger.warning("TriggerType not available")
            return None

    def _mode_from_intent(self, parsed_command: ParsedCommand) -> CVAMode:
        """Determine mode from parsed command intent and confidence."""
        if parsed_command.intent == IntentType.CEO_DIRECTIVE:
            return CVAMode.CEO_MODE

        if parsed_command.confidence < 0.7:
            logger.debug(f"Low confidence ({parsed_command.confidence:.2f}) -> REACTIVE")
            return CVAMode.REACTIVE

        if parsed_command.intent in [
            IntentType.TASK_MANAGEMENT,
            IntentType.SYSTEM_CONTROL,
        ]:
            return CVAMode.PROACTIVE

        return CVAMode.REACTIVE

    async def switch_mode(
        self, new_mode: CVAMode, reason: str, token: str | None = None
    ) -> bool:
        """
        Switch to new mode with context preservation and audit logging.

        Returns True if mode was changed, False if already in target mode.
        """
        async with self._lock:
            if new_mode == self.current_mode:
                return False

            old_mode = self.current_mode
            self._record_transition(old_mode, new_mode, reason)
            self.current_mode = new_mode
            logger.info(f"Mode: {old_mode.value} -> {new_mode.value} ({reason})")

            await self._initialize_mode_context(new_mode, token)
            return True

    def _record_transition(self, old_mode: CVAMode, new_mode: CVAMode, reason: str) -> None:
        """Record mode transition in history."""
        self.mode_history.append(
            {
                "from": old_mode.value,
                "to": new_mode.value,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        if len(self.mode_history) > self.max_history:
            self.mode_history = self.mode_history[-self.max_history :]

    async def _initialize_mode_context(self, mode: CVAMode, token: str | None = None) -> None:
        """Initialize context for the new mode."""
        try:
            if mode == CVAMode.CEO_MODE:
                await self._init_ceo_context(token)
            elif mode == CVAMode.AUTONOMOUS:
                self._init_autonomous_context()
        except Exception as e:
            logger.error(f"Failed to initialize {mode.value} context: {e}")

    async def _init_ceo_context(self, token: str | None = None) -> None:
        """Initialize CEO mode strategic context."""
        context = {"initialized_at": datetime.now(timezone.utc).isoformat()}

        if self._dashboard_fetcher:
            try:
                dashboard = await self._dashboard_fetcher(token)
                context["system_health"] = dashboard
            except Exception as e:
                logger.warning(f"Dashboard fetch failed: {e}")

        self.mode_context["ceo_mode"] = context
        logger.debug("CEO mode context initialized")

    def _init_autonomous_context(self) -> None:
        """Initialize autonomous mode context."""
        self.mode_context["autonomous_mode"] = {
            "initialized_at": datetime.now(timezone.utc).isoformat(),
            "learning_enabled": True,
        }
        logger.debug("Autonomous mode context initialized")

    def get_recent_history(self, limit: int = 5) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get recent mode transition history."""
        return self.mode_history[-limit:] if self.mode_history else []
