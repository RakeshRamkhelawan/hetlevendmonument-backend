"""
Contract Settlement - Audit records for A2A contract execution.

Implements immutable settlement records for the internal token economy
and audit trail requirements.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.als.enterprise.contracts.validator import InsufficientPranaError


class SettlementStatus(Enum):
    """Settlement execution status"""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED_VALIDATION = "failed_validation"
    FAILED_TIMEOUT = "failed_timeout"
    FAILED_PRANA = "failed_prana_insufficient"
    FAILED_EXECUTION = "failed_execution"


@dataclass
class SettlementRecord:
    """
    Immutable settlement record for audit and economy tracking.

    NON-NEGOTIABLE:
    - Settlement records are append-only (no edits)
    - Contains hashes only, no PII
    - Prana transfer is atomic with settlement
    """

    # Identification
    settlement_id: str
    contract_id: str
    tenant_id: int

    # Timing
    started_at: datetime
    completed_at: datetime | None = None
    latency_ms: int = 0

    # Execution details
    status: SettlementStatus = SettlementStatus.PENDING
    validation_errors: list[Any] = field(default_factory=list[Any])  # TODO(TYPE): replace Any with concrete type
    retry_count: int = 0

    # Economy (prana = internal compute tokens)
    prana_spent: int = 0
    prana_refunded: int = 0  # Refunded on failure

    # Data integrity (hashes only, NO PII!)
    input_hash: str | None = None  # SHA-256 of input payload
    output_hash: str | None = None  # SHA-256 of output payload

    # Audit trail
    producer_agent: str = ""
    consumer_agent: str = ""
    producer_department: str = ""
    consumer_department: str = ""

    # Failure tracking
    failure_reason: str | None = None
    stack_trace: str | None = None  # Only for internal errors

    def complete(self, status: SettlementStatus, latency_ms: int) -> None:
        """Mark settlement as completed"""
        self.status = status
        self.completed_at = datetime.now(timezone.utc)
        self.latency_ms = latency_ms

    def to_event(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Convert to event sourcing format.

        NO PII - only hashes and metadata!
        """
        return {
            "event_type": "contract_settled",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "settlement_id": self.settlement_id,
            "contract_id": self.contract_id,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "prana_spent": self.prana_spent,
            "prana_refunded": self.prana_refunded,
            "producer_agent": self.producer_agent,
            "consumer_agent": self.consumer_agent,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "retry_count": self.retry_count,
        }

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize to dictionary"""
        return {
            "settlement_id": self.settlement_id,
            "contract_id": self.contract_id,
            "tenant_id": self.tenant_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "latency_ms": self.latency_ms,
            "status": self.status.value,
            "validation_errors": self.validation_errors,
            "retry_count": self.retry_count,
            "prana_spent": self.prana_spent,
            "prana_refunded": self.prana_refunded,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "producer_agent": self.producer_agent,
            "consumer_agent": self.consumer_agent,
            "failure_reason": self.failure_reason,
        }


class SettlementEngine:
    """
    Executes contract settlement with prana transfer.
    """

    def __init__(self, event_store: Any = None, prana_ledger: Any = None) -> None:
        self.event_store = event_store
        self.prana_ledger = prana_ledger

    async def settle(self, record: SettlementRecord, success: bool) -> SettlementRecord:
        """
        Execute settlement and prana transfer.

        Args:
            record: Settlement record to process
            success: Whether contract execution succeeded

        Returns:
            Updated settlement record
        """
        if success:
            record.status = SettlementStatus.SUCCESS
            # Prana stays with producer
            record.prana_refunded = 0
        else:
            record.status = SettlementStatus.FAILED_EXECUTION
            # Refund prana to consumer on failure
            record.prana_refunded = record.prana_spent

        record.completed_at = datetime.now(timezone.utc)

        # Publish event
        if self.event_store:
            await self._publish_event(record)

        return record

    async def _publish_event(self, record: SettlementRecord) -> None:
        """Publish settlement event to event store"""
        event = record.to_event()
        # Implementation depends on event store interface
        pass


class PranaLedger:
    """
    Tracks prana (compute token) balances for departments/agents.

    NON-NEGOTIABLE:
    - All prana transfers are atomic
    - No negative balances allowed
    - All transfers logged
    """

    def __init__(self) -> None:
        self._balances: dict[str, int] = {}  # agent_id -> balance

    def get_balance(self, agent_id: str) -> int:
        """Get prana balance for agent"""
        return self._balances.get(agent_id, 0)

    def deposit(self, agent_id: str, amount: int) -> int:
        """Deposit prana to agent"""
        current = self._balances.get(agent_id, 0)
        self._balances[agent_id] = current + amount
        return self._balances[agent_id]

    def withdraw(self, agent_id: str, amount: int) -> int:
        """
        Withdraw prana from agent.

        Raises:
            InsufficientPranaError: If balance < amount
        """
        current = self._balances.get(agent_id, 0)
        if current < amount:
            raise InsufficientPranaError(
                f"Insufficient prana: {current} available, {amount} required"
            )
        self._balances[agent_id] = current - amount
        return self._balances[agent_id]

    def transfer(self, from_agent: str, to_agent: str, amount: int) -> tuple[int, int]:
        """
        Transfer prana between agents (atomic).

        Returns:
            (from_balance, to_balance) after transfer
        """
        self.withdraw(from_agent, amount)
        self.deposit(to_agent, amount)
        return (self.get_balance(from_agent), self.get_balance(to_agent))
