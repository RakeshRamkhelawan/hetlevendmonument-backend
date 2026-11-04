"""
Contract State Machine - Hard transition rules for A2A contracts.

This module defines the allowed state transitions and enforces
the rules defined in Section 1.1 of the ALS 2.0 specification.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.als.enterprise.contracts.models import A2AContract, ContractState, ContractTransitionError


class ActorRole(Enum):
    """Actor roles in contract state transitions"""

    CONSUMER = "consumer"
    PRODUCER = "producer"
    CHIEF = "chief"
    SYSTEM = "system"


class ContractStateMachine:
    """
    Deterministic state machine for A2A contract lifecycle.

    NON-NEGOTIABLE RULES:
    1. PROPOSED -> REJECTED: Always allowed (consumer)
    2. PROPOSED -> COUNTERED: Always allowed (producer)
    3. PROPOSED -> EXECUTING: NEVER allowed (must go through AGREED)
    4. Max 3 retries: FAILED -> RETRYING max 3x, then CLOSED
    5. Only SYSTEM can transition to EXECUTING
    """

    # Define allowed transitions: (from_state, to_state) -> allowed_actors
    _TRANSITIONS: dict[tuple[ContractState, ContractState], set[ActorRole]] = {
        # PROPOSED transitions
        (ContractState.PROPOSED, ContractState.REJECTED): {ActorRole.CONSUMER},
        (ContractState.PROPOSED, ContractState.COUNTERED): {ActorRole.PRODUCER},
        (ContractState.PROPOSED, ContractState.AGREED): {ActorRole.PRODUCER},
        # COUNTERED transitions
        (ContractState.COUNTERED, ContractState.AGREED): {ActorRole.CONSUMER},
        (ContractState.COUNTERED, ContractState.REJECTED): {ActorRole.CONSUMER},
        (ContractState.COUNTERED, ContractState.PROPOSED): {
            ActorRole.CONSUMER
        },  # Reject counter, back to proposed
        # AGREED transitions
        (ContractState.AGREED, ContractState.EXECUTING): {
            ActorRole.SYSTEM,
            ActorRole.CHIEF,
        },
        # EXECUTING transitions
        (ContractState.EXECUTING, ContractState.SETTLED): {ActorRole.SYSTEM},
        (ContractState.EXECUTING, ContractState.FAILED): {ActorRole.SYSTEM},
        # FAILED transitions
        (ContractState.FAILED, ContractState.RETRYING): {ActorRole.CHIEF},
        (ContractState.FAILED, ContractState.CLOSED): {
            ActorRole.CHIEF,
            ActorRole.SYSTEM,
        },
        # RETRYING transitions
        (ContractState.RETRYING, ContractState.EXECUTING): {ActorRole.SYSTEM},
        (ContractState.RETRYING, ContractState.FAILED): {ActorRole.SYSTEM},  # Retry failed again
        # SETTLED transitions
        (ContractState.SETTLED, ContractState.CLOSED): {ActorRole.SYSTEM},
        # REJECTED transitions
        (ContractState.REJECTED, ContractState.CLOSED): {ActorRole.SYSTEM},
    }

    @classmethod
    def can_transition(
        cls,
        from_state: ContractState,
        to_state: ContractState,
        actor: ActorRole | None = None,
    ) -> bool:
        """
        Check if a state transition is allowed.

        Args:
            from_state: Current state
            to_state: Desired new state
            actor: Who is requesting the transition (optional)

        Returns:
            True if transition is allowed, False otherwise
        """
        key = (from_state, to_state)
        if key not in cls._TRANSITIONS:
            return False

        allowed_actors = cls._TRANSITIONS[key]
        if actor is None:
            return True  # Just checking if transition exists

        return actor in allowed_actors

    @classmethod
    def transition(
        cls, from_state: ContractState, to_state: ContractState, actor: ActorRole
    ) -> None:
        """
        Validate and execute a state transition.

        Args:
            from_state: Current state
            to_state: Desired new state
            actor: Who is requesting the transition

        Raises:
            ContractTransitionError: If transition is not allowed
        """
        if not cls.can_transition(from_state, to_state, actor):
            allowed = cls.get_allowed_transitions(from_state, actor)
            raise ContractTransitionError(
                f"Invalid transition: {from_state.value} -> {to_state.value} "
                f"by {actor.value}. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )

    @classmethod
    def get_allowed_transitions(
        cls, state: ContractState, actor: ActorRole | None = None
    ) -> list[ContractState]:
        """
        Get list of allowed next states from current state.

        Args:
            state: Current state
            actor: Filter by actor role (optional)

        Returns: List[Any] of allowed next states  # TODO(TYPE): replace Any with concrete type
        """
        allowed: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for (from_s, to_s), actors in cls._TRANSITIONS.items():
            if from_s == state:
                if actor is None or actor in actors:
                    allowed.append(to_s)
        return allowed

    @classmethod
    def get_required_actor(
        cls, from_state: ContractState, to_state: ContractState
    ) -> ActorRole | None:
        """
        Get the required actor for a transition.

        Returns:
            ActorRole if single actor required, None if multiple allowed
        """
        key = (from_state, to_state)
        if key not in cls._TRANSITIONS:
            return None

        actors = cls._TRANSITIONS[key]
        if len(actors) == 1:
            return list(actors)[0]
        return None  # Multiple actors allowed

    @classmethod
    def is_terminal_state(cls, state: ContractState) -> bool:
        """Check if state is terminal (no outgoing transitions)"""
        return len(cls.get_allowed_transitions(state)) == 0

    @classmethod
    def validate_retry(cls, retry_count: int, max_retries: int = 3) -> bool:
        """
        Validate if retry is allowed.

        NON-NEGOTIABLE: Max 3 retries
        """
        return retry_count < max_retries


# Convenience functions for common transitions
def producer_accepts(contract: A2AContract) -> None:
    """Producer accepts proposed contract"""
    ContractStateMachine.transition(contract.state, ContractState.AGREED, ActorRole.PRODUCER)
    contract.state = ContractState.AGREED
    contract.agreed_at = datetime.now(timezone.utc)


def consumer_accepts_counter(contract: A2AContract) -> None:
    """Consumer accepts counter-proposal"""
    ContractStateMachine.transition(contract.state, ContractState.AGREED, ActorRole.CONSUMER)
    contract.state = ContractState.AGREED
    contract.agreed_at = datetime.now(timezone.utc)


def start_execution(contract: A2AContract) -> None:
    """System starts contract execution"""
    ContractStateMachine.transition(contract.state, ContractState.EXECUTING, ActorRole.SYSTEM)
    contract.state = ContractState.EXECUTING
    contract.executing_at = datetime.now(timezone.utc)


def settle_contract(contract: A2AContract) -> None:
    """Contract settled successfully"""
    ContractStateMachine.transition(contract.state, ContractState.SETTLED, ActorRole.SYSTEM)
    contract.state = ContractState.SETTLED
    contract.settled_at = datetime.now(timezone.utc)


def fail_contract(contract: A2AContract, can_retry: bool = True) -> None:
    """Contract execution failed"""
    if can_retry and ContractStateMachine.validate_retry(contract.retry_count):
        ContractStateMachine.transition(contract.state, ContractState.RETRYING, ActorRole.CHIEF)
        contract.state = ContractState.RETRYING
        contract.retry_count += 1
    else:
        ContractStateMachine.transition(contract.state, ContractState.FAILED, ActorRole.SYSTEM)
        contract.state = ContractState.FAILED
