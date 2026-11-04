import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.agents.cva_state_machine import CVAMode, CVAStateMachine, StateTransitionError

from .models import CVAState

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, initial_mode: CVAMode = CVAMode.CEO_MODE) -> None:
        self.state_machine = CVAStateMachine(initial_mode=initial_mode)
        self.cva_state = CVAState(
            mode=initial_mode,
            active_orchestrations=[],
            learning_context={},
            performance_metrics={},
            last_optimization=datetime.now(timezone.utc),
            autonomous_triggers_active=True,
        )

    async def transition_to_mode(
        self, target_mode: CVAMode, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Transition CVA agent to a new operational mode
        """
        try:
            # Perform state machine transition
            await self.state_machine.transition_to(target_mode, context)

            # Sync CVAState with state machine
            self.cva_state.mode = target_mode
            self.cva_state.learning_context.update(context or {})

            # Update CVAState timestamp
            self.cva_state.last_optimization = datetime.now(timezone.utc)

            logger.info(
                f"CVA Agent transitioned to {target_mode.value} mode "
                f"(transition #{self.state_machine.get_transition_count()})"
            )

            return True

        except StateTransitionError as e:
            logger.warning(f"Failed to transition to {target_mode.value} mode: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during mode transition: {e}")
            return False
