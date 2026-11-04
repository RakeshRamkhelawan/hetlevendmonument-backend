"""
CVA State Machine Implementation
Manages transitions between CVAMode states with validation and callbacks
Supports the M-MDP CEO_MODE strategic learning paradigm
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from collections.abc import Callable, Awaitable

logger = logging.getLogger(__name__)


class CVAMode(Enum):
    """CVA operational modes for M-MDP strategic learning"""

    REACTIVE = "reactive"  # Responds to direct requests
    PROACTIVE = "proactive"  # Monitors and initiates actions
    AUTONOMOUS = "autonomous"  # Full self-operation
    CEO_MODE = "ceo_mode"  # Executive decision making with strategic memory


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted"""

    pass


class StateTransitionCallback:
    """Callback handlers for state transitions"""

    def __init__(self) -> None:
        """Initialize callback registry"""
        self._on_enter: dict[CVAMode, list[Callable[..., Any]]] = {mode: [] for mode in CVAMode}  # TODO(TYPE): replace Any with concrete type
        self._on_exit: dict[CVAMode, list[Callable[..., Any]]] = {mode: [] for mode in CVAMode}  # TODO(TYPE): replace Any with concrete type
        self._on_transition: list[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type

    def register_on_enter(self, mode: CVAMode, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register a callback to execute when entering a mode"""
        if not callable(callback):
            raise TypeError(f"Callback must be callable, got {type(callback)}")
        self._on_enter[mode].append(callback)
        logger.debug(f"Registered on_enter callback for {mode.value}")

    def register_on_exit(self, mode: CVAMode, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register a callback to execute when exiting a mode"""
        if not callable(callback):
            raise TypeError(f"Callback must be callable, got {type(callback)}")
        self._on_exit[mode].append(callback)
        logger.debug(f"Registered on_exit callback for {mode.value}")

    def register_on_transition(self, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register a callback to execute on any transition"""
        if not callable(callback):
            raise TypeError(f"Callback must be callable, got {type(callback)}")
        self._on_transition.append(callback)
        logger.debug("Registered on_transition callback")

    async def execute_on_enter(self, mode: CVAMode, context: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Execute all on_enter callbacks for a mode"""
        for callback in self._on_enter[mode]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(context)
                else:
                    callback(context)
            except Exception as e:
                logger.error(f"Error executing on_enter callback for {mode.value}: {e}")

    async def execute_on_exit(self, mode: CVAMode, context: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Execute all on_exit callbacks for a mode"""
        for callback in self._on_exit[mode]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(context)
                else:
                    callback(context)
            except Exception as e:
                logger.error(f"Error executing on_exit callback for {mode.value}: {e}")

    async def execute_on_transition(
        self, from_mode: CVAMode, to_mode: CVAMode, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Execute all on_transition callbacks"""
        transition_context = {
            **context,
            "from_mode": from_mode,
            "to_mode": to_mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for callback in self._on_transition:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(transition_context)
                else:
                    callback(transition_context)
            except Exception as e:
                logger.error(f"Error executing on_transition callback: {e}")


class CVAStateMachine:
    """
    State machine for managing CVAMode transitions with validation

    Transition Graph:
    - REACTIVE <-> PROACTIVE <-> AUTONOMOUS <-> CEO_MODE
    - All transitions are bidirectional except CEO_MODE has restrictions
    - CEO_MODE is the highest level and can transition to any state
    - Any state can transition to CEO_MODE if authorized  # TODO(TYPE): replace Any with concrete type
    """

    # Valid transitions: from_mode -> set(valid_to_modes)
    VALID_TRANSITIONS: dict[CVAMode, set[CVAMode]] = {
        CVAMode.REACTIVE: {CVAMode.PROACTIVE, CVAMode.CEO_MODE},
        CVAMode.PROACTIVE: {CVAMode.REACTIVE, CVAMode.AUTONOMOUS, CVAMode.CEO_MODE},
        CVAMode.AUTONOMOUS: {CVAMode.PROACTIVE, CVAMode.CEO_MODE},
        CVAMode.CEO_MODE: {CVAMode.REACTIVE, CVAMode.PROACTIVE, CVAMode.AUTONOMOUS},
    }

    # Mode hierarchy for validation (higher number = higher level)
    MODE_HIERARCHY: dict[CVAMode, int] = {
        CVAMode.REACTIVE: 1,
        CVAMode.PROACTIVE: 2,
        CVAMode.AUTONOMOUS: 3,
        CVAMode.CEO_MODE: 4,
    }

    def __init__(self, initial_mode: CVAMode = CVAMode.REACTIVE) -> None:
        """
        Initialize state machine with initial mode

        Args:
            initial_mode: Starting mode (default: REACTIVE)
        """
        if not isinstance(initial_mode, CVAMode):
            raise TypeError(f"initial_mode must be CVAMode, got {type(initial_mode)}")

        self.current_mode = initial_mode
        self.previous_mode: CVAMode | None = None
        self.transition_count = 0
        self.last_transition_time: datetime | None = None
        self.transition_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.callbacks = StateTransitionCallback()

        logger.info(f"CVA State Machine initialized in {initial_mode.value} mode")

    def is_valid_transition(self, to_mode: CVAMode) -> bool:
        """
        Check if transition from current mode to target mode is valid

        Args:
            to_mode: Target mode

        Returns:
            bool: True if transition is valid, False otherwise
        """
        if not isinstance(to_mode, CVAMode):
            logger.warning(f"Invalid mode type: {type(to_mode)}")
            return False

        if self.current_mode == to_mode:
            return False  # No self-transitions

        return to_mode in self.VALID_TRANSITIONS.get(self.current_mode, set())

    def validate_transition(self, to_mode: CVAMode) -> bool:
        """
        Validate transition and raise error if invalid

        Args:
            to_mode: Target mode

        Raises:
            StateTransitionError: If transition is invalid

        Returns:
            bool: True if valid
        """
        if not isinstance(to_mode, CVAMode):
            raise StateTransitionError(f"Invalid mode type: {type(to_mode)}")

        if self.current_mode == to_mode:
            raise StateTransitionError(f"Cannot transition to same mode: {self.current_mode.value}")

        if not self.is_valid_transition(to_mode):
            raise StateTransitionError(
                f"Invalid transition: {self.current_mode.value} -> {to_mode.value}"
            )

        return True

    async def transition_to(
        self, to_mode: CVAMode, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """
        Perform state transition with validation and callbacks

        Args:
            to_mode: Target mode
            context: Optional context data for callbacks

        Raises:
            StateTransitionError: If transition is invalid
        """
        # Validate transition
        self.validate_transition(to_mode)

        # Prepare context
        if context is None:
            context = {}
        from_mode = self.current_mode
        transition_context: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            **context,
            "from_mode": from_mode,
            "to_mode": to_mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transition_number": self.transition_count + 1,
        }

        try:
            # Execute on_exit callbacks for current mode
            await self.callbacks.execute_on_exit(from_mode, transition_context)

            # Execute on_transition callbacks
            await self.callbacks.execute_on_transition(from_mode, to_mode, transition_context)

            # Perform transition
            self.previous_mode = from_mode
            self.current_mode = to_mode
            self.transition_count += 1
            self.last_transition_time = datetime.now(timezone.utc)

            # Record in history
            self.transition_history.append(
                {
                    "from": from_mode.value,
                    "to": to_mode.value,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "transition_number": self.transition_count,
                    "context": context,
                }
            )

            # Execute on_enter callbacks for new mode
            await self.callbacks.execute_on_enter(to_mode, transition_context)

            logger.info(
                f"State transition: {from_mode.value} -> {to_mode.value} "
                f"(transition #{self.transition_count})"
            )

        except Exception as e:
            logger.error(f"Error during state transition: {e}")
            raise StateTransitionError(f"Transition failed: {str(e)}") from e

    def get_current_mode(self) -> CVAMode:
        """Get the current operational mode"""
        return self.current_mode

    def get_previous_mode(self) -> CVAMode | None:
        """Get the previous operational mode"""
        return self.previous_mode

    def get_available_transitions(self) -> set[CVAMode]:
        """Get all valid transitions from current mode"""
        return self.VALID_TRANSITIONS.get(self.current_mode, set()).copy()

    def get_transition_count(self) -> int:
        """Get total number of transitions performed"""
        return self.transition_count

    def get_transition_history(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get complete transition history"""
        return self.transition_history.copy()

    def get_mode_hierarchy_level(self, mode: CVAMode | None = None) -> int:
        """
        Get hierarchy level of a mode (1=lowest, 4=highest)

        Args:
            mode: Mode to check (default: current mode)

        Returns:
            int: Hierarchy level
        """
        if mode is None:
            mode = self.current_mode

        return self.MODE_HIERARCHY.get(mode, 0)

    def is_mode_available(self, mode: CVAMode) -> bool:
        """Check if a mode is available for transition"""
        return mode in self.get_available_transitions()

    def can_escalate(self, target_mode: CVAMode) -> bool:
        """
        Check if transition represents an escalation (moving to higher hierarchy)

        Args:
            target_mode: Target mode to check

        Returns:
            bool: True if target_mode is higher in hierarchy
        """
        return self.get_mode_hierarchy_level(target_mode) > self.get_mode_hierarchy_level()

    def can_deescalate(self, target_mode: CVAMode) -> bool:
        """
        Check if transition represents a deescalation (moving to lower hierarchy)

        Args:
            target_mode: Target mode to check

        Returns:
            bool: True if target_mode is lower in hierarchy
        """
        return self.get_mode_hierarchy_level(target_mode) < self.get_mode_hierarchy_level()

    def reset_to(self, mode: CVAMode) -> None:
        """
        Reset state machine to initial mode (without transitions/callbacks)

        Args:
            mode: Mode to reset to
        """
        self.current_mode = mode
        self.previous_mode = None
        self.transition_count = 0
        self.last_transition_time = None
        self.transition_history = []
        logger.info(f"State machine reset to {mode.value}")

    def get_state_summary(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get complete state summary"""
        return {
            "current_mode": self.current_mode.value,
            "previous_mode": self.previous_mode.value if self.previous_mode else None,
            "transition_count": self.transition_count,
            "last_transition_time": (
                self.last_transition_time.isoformat() if self.last_transition_time else None
            ),
            "available_transitions": [mode.value for mode in self.get_available_transitions()],
            "hierarchy_level": self.get_mode_hierarchy_level(),
            "transition_history_length": len(self.transition_history),
        }
