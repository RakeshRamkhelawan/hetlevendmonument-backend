"""
Contract Models - Core A2A Contract data structures.

Implements the contract state machine and data models for
agent-to-agent smart contracts.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.als.enterprise.contracts.schema_registry import SchemaRef
from src.core.als.enterprise.departments.department_orchestrator import Department


class ContractState(Enum):
    """
    Contract lifecycle states.

    State transitions (hard rules):
    PROPOSED -> REJECTED (consumer)
    PROPOSED -> COUNTERED (producer)
    PROPOSED -> AGREED (producer)
    COUNTERED -> AGREED (consumer)
    COUNTERED -> REJECTED (consumer)
    AGREED -> EXECUTING (system)
    EXECUTING -> SETTLED (success)
    EXECUTING -> FAILED (validation/deadline)
    FAILED -> RETRYING (chief, max 3)
    FAILED -> CLOSED (max retries)
    """

    PROPOSED = "proposed"
    COUNTERED = "countered"
    AGREED = "agreed"
    EXECUTING = "executing"
    SETTLED = "settled"
    FAILED = "failed"
    REJECTED = "rejected"
    RETRYING = "retrying"
    CLOSED = "closed"


class ContractTransitionError(Exception):
    """Raised when an invalid state transition is attempted"""

    pass


@dataclass
class A2AContract:
    """
    A2A Smart Contract between two agents.

    This is the core data structure for inter-agent communication
    with schema validation and SLA enforcement.
    """

    # Identification
    contract_id: str
    tenant_id: int

    # Parties
    producer_agent: str
    consumer_agent: str
    producer_department: Department
    consumer_department: Department

    # Schema (HARD REQUIREMENT)
    schema_ref: SchemaRef
    schema_hash: str  # SHA-256 of canonical schema

    # SLA Terms
    deadline_ms: int = 5000  # Maximum execution time
    prana_cost: int = 50  # Compute cost in prana

    # State
    state: ContractState = ContractState.PROPOSED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    agreed_at: datetime | None = None
    executing_at: datetime | None = None
    settled_at: datetime | None = None

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3

    # Execution data (only populated after execution)
    payload_hash: str | None = None  # SHA-256 of input payload (no PII)
    output_hash: str | None = None  # SHA-256 of output (no PII)
    execution_time_ms: int | None = None

    # Settlement
    settlement_id: str | None = None
    prana_transferred: bool = False

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize contract to dictionary"""
        return {
            "contract_id": self.contract_id,
            "tenant_id": self.tenant_id,
            "producer_agent": self.producer_agent,
            "consumer_agent": self.consumer_agent,
            "producer_department": self.producer_department.value,
            "consumer_department": self.consumer_department.value,
            "schema_ref": self.schema_ref.ref,
            "schema_hash": self.schema_hash,
            "deadline_ms": self.deadline_ms,
            "prana_cost": self.prana_cost,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "agreed_at": self.agreed_at.isoformat() if self.agreed_at else None,
            "settled_at": self.settled_at.isoformat() if self.settled_at else None,
            "retry_count": self.retry_count,
        }

    def can_transition_to(self, new_state: ContractState) -> bool:
        """Check if transition from current state to new state is allowed"""
        from src.core.als.enterprise.contracts.state_machine import ContractStateMachine

        return ContractStateMachine.can_transition(self.state, new_state)


@dataclass
class ContractProposal:
    """Initial contract proposal from consumer to producer"""

    consumer_agent: str
    consumer_department: Department
    schema_ref: SchemaRef
    required_fields: list[str]
    deadline_ms: int
    prana_offer: int
    proposal_id: str | None = None

    def to_contract(
        self,
        contract_id: str,
        tenant_id: int,
        producer_agent: str,
        producer_department: Department,
        schema_hash: str,
    ) -> A2AContract:
        """Convert proposal to full contract"""
        return A2AContract(
            contract_id=contract_id,
            tenant_id=tenant_id,
            producer_agent=producer_agent,
            consumer_agent=self.consumer_agent,
            producer_department=producer_department,
            consumer_department=self.consumer_department,
            schema_ref=self.schema_ref,
            schema_hash=schema_hash,
            deadline_ms=self.deadline_ms,
            prana_cost=self.prana_offer,
        )


@dataclass
class CounterProposal:
    """Counter-proposal from producer to consumer"""

    original_contract_id: str
    new_deadline_ms: int | None = None
    new_prana_cost: int | None = None
    reason: str | None = None
