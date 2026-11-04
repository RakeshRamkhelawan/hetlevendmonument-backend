"""
A2A Smart Contracts - Secure Inter-Agent Communication

When agents from different departments communicate (e.g., Talent Acquisition
in HR talking to Cloud Orchestration in IT), simple SYNAPTIC messages are
not secure enough.

This module implements:
- CONTRACT_PROPOSAL: Agent A requests data from Agent B
- CONTRACT_AGREED: SLA and data schema formalized
- Schema validation for data integrity
- Internal compute cost tracking (prana)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from collections.abc import Callable


from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.als.infrastructure.signal_bus import Signal, SignalBus

logger = logging.getLogger("A2AContracts")


class SignalTierExt(str, Enum):
    """Extended signal tiers including A2A contract phases."""

    # Original tiers
    REFLEX = "reflex"
    COGNITIVE = "cognitive"
    EMOTIONAL = "emotional"
    SYNAPTIC = "synaptic"
    BROADCAST = "broadcast"
    # New A2A contract tiers
    CONTRACT_PROPOSAL = "contract_proposal"  # Agent A requests data
    CONTRACT_COUNTER = "contract_counter"  # Agent B negotiates terms
    CONTRACT_AGREED = "contract_agreed"  # SLA finalized
    CONTRACT_EXECUTE = "contract_execute"  # Execute contracted work
    CONTRACT_SETTLE = "contract_settle"  # Payment/confirmation


class ContractStatus(str, Enum):
    """Status of an A2A contract."""

    PROPOSED = "proposed"
    NEGOTIATING = "negotiating"
    AGREED = "agreed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    DISPUTED = "disputed"


@dataclass
class DataSchema:
    """Schema definition for contract data exchange.

    Uses Pydantic for runtime validation.
    """

    schema_name: str
    schema_definition: dict[str, Any]  # JSON Schema or Pydantic model dict  # TODO(TYPE): replace Any with concrete type
    required_fields: list[str] = field(default_factory=list)

    # SECURITY FIX: Safe type mapping to prevent RCE via eval()
    # Maps type name strings to actual Python types
    _TYPE_MAP: dict[str, type] = field(
        default_factory=lambda: {
            "int": int,
            "str": str,
            "bool": bool,
            "float": float,
            "dict": dict,
            "list": list,
            "tuple": tuple,
            "set": set,
        }
    )

    def validate_payload(self, payload: dict[str, Any]) -> tuple[bool, str | None]:  # TODO(TYPE): replace Any with concrete type
        """Validate payload against schema."""
        try:
            # Check required fields
            for field in self.required_fields:
                if field not in payload:
                    return False, f"Missing required field: {field}"

            # Type checking (simplified) - SECURE: uses safe type mapping, NOT eval()
            for key, value in payload.items():
                expected_type_str = self.schema_definition.get(key)
                if expected_type_str:
                    expected_type = self._TYPE_MAP.get(expected_type_str)
                    if expected_type is None:
                        return (
                            False,
                            f"Field {key} has unknown type: {expected_type_str}",
                        )
                    if not isinstance(value, expected_type):
                        return (
                            False,
                            f"Field {key} has wrong type, expected {expected_type_str}",
                        )

            return True, None
        except Exception as e:
            return False, str(e)


@dataclass
class A2AContract:
    """
    A2A Smart Contract between two agents.

    Example:
        # Talent Acquisition Agent (HR) requests data from
        # Cloud Orchestration Agent (IT)
        contract = A2AContract(
            contract_id="contract_123",
            producer_agent="cloud_orchestration",
            consumer_agent="talent_acquisition",
            required_schema={
                "candidate_count": "int",
                "skill_matrix": "dict",
                "timeline_weeks": "int"
            },
            deadline_ms=5000,
            prana_cost=100
        )
    """

    contract_id: str
    producer_agent: str  # Agent providing data/service
    consumer_agent: str  # Agent requesting data/service
    producer_department: Department
    consumer_department: Department

    # Contract terms
    required_schema: DataSchema
    deadline_ms: int = 5000  # SLA deadline in milliseconds
    prana_cost: int = 50  # Internal compute cost

    # State
    status: ContractStatus = ContractStatus.PROPOSED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    agreed_at: datetime | None = None
    completed_at: datetime | None = None

    # Execution tracking
    payload_delivered: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    payload_valid: bool = False
    settlement_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize contract to dictionary."""
        return {
            "contract_id": self.contract_id,
            "producer_agent": self.producer_agent,
            "consumer_agent": self.consumer_agent,
            "producer_department": self.producer_department.value,
            "consumer_department": self.consumer_department.value,
            "required_schema": {
                "schema_name": self.required_schema.schema_name,
                "schema_definition": self.required_schema.schema_definition,
                "required_fields": self.required_schema.required_fields,
            },
            "deadline_ms": self.deadline_ms,
            "prana_cost": self.prana_cost,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "agreed_at": self.agreed_at.isoformat() if self.agreed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ContractManager:
    """
    Manages A2A contracts for secure inter-agent communication.

    Responsibilities:
    - Create and track contracts
    - Validate schema compliance
    - Enforce SLA deadlines
    - Handle dispute resolution
    - Manage "prana" (compute cost) settlement

    Example:
        manager = ContractManager(signal_bus, tenant_id)

        # Consumer agent initiates contract
        contract = await manager.propose_contract(
            consumer_agent="talent_acquisition",
            producer_agent="cloud_orchestration",
            required_data={"candidate_count": "int", "skills": "list"}
        )

        # Producer agent reviews and accepts
        await manager.agree_to_contract(contract.contract_id)

        # Execute with validation
        result = await manager.execute_contract(
            contract.contract_id,
            payload={"candidate_count": 5, "skills": ["python", "aws"]}
        )
    """

    def __init__(self, signal_bus: SignalBus, tenant_id: int) -> None:
        self.signal_bus = signal_bus
        self.tenant_id = tenant_id

        # Contract storage
        self._contracts: dict[str, A2AContract] = {}
        self._pending_proposals: dict[str, asyncio.Event] = {}  # contract_id -> event

        # Schema registry
        self._schema_registry: dict[str, DataSchema] = {}

        # Settlement tracking
        self._prana_ledger: dict[str, int] = {}  # agent_id -> prana balance

        # Contract listener task (wired when event stream listener is implemented, ADR-006)
        self._listener_task: asyncio.Task[None] | None = None

        logger.info(f"ContractManager initialized for tenant {tenant_id}")

    async def propose_contract(
        self,
        consumer_agent: str,
        producer_agent: str,
        consumer_dept: Department,
        producer_dept: Department,
        required_data: dict[str, str],
        deadline_ms: int = 5000,
        prana_cost: int = 50,
    ) -> A2AContract:
        """
        Consumer agent proposes a contract to producer agent.

        Args:
            consumer_agent: Agent requesting data
            producer_agent: Agent providing data
            required_data: Map of field names to expected types
            deadline_ms: SLA deadline
            prana_cost: Compute cost for this contract
        """
        import uuid

        contract_id = f"contract_{uuid.uuid4().hex[:12]}"

        # Create schema
        schema = DataSchema(
            schema_name=f"schema_{contract_id}",
            schema_definition=required_data,
            required_fields=list(required_data.keys()),
        )

        contract = A2AContract(
            contract_id=contract_id,
            producer_agent=producer_agent,
            consumer_agent=consumer_agent,
            producer_department=producer_dept,
            consumer_department=consumer_dept,
            required_schema=schema,
            deadline_ms=deadline_ms,
            prana_cost=prana_cost,
            status=ContractStatus.PROPOSED,
        )

        self._contracts[contract_id] = contract
        self._pending_proposals[contract_id] = asyncio.Event()

        # Emit proposal signal
        signal = Signal(
            tenant_id=self.tenant_id,
            source_agent_id=consumer_agent,
            target_agent_ids=[producer_agent],
            tier=SignalTierExt.CONTRACT_PROPOSAL,
            payload={"contract": contract.to_dict(), "action": "review_proposal"},
        )

        await self.signal_bus.emit(signal)

        logger.info(
            "Contract proposed",
            extra={
                "contract_id": contract_id,
                "consumer": consumer_agent,
                "producer": producer_agent,
            },
        )

        return contract

    async def agree_to_contract(
        self, contract_id: str, counter_terms: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Producer agent agrees to contract (optionally with counter-terms).

        Args:
            contract_id: Contract to agree to
            counter_terms: Optional modifications (e.g., higher prana_cost)
        """
        if contract_id not in self._contracts:
            logger.error(f"Contract {contract_id} not found")
            return False

        contract = self._contracts[contract_id]

        # Apply counter-terms if provided
        if counter_terms:
            if "deadline_ms" in counter_terms:
                contract.deadline_ms = counter_terms["deadline_ms"]
            if "prana_cost" in counter_terms:
                contract.prana_cost = counter_terms["prana_cost"]
            contract.status = ContractStatus.NEGOTIATING

            # Notify consumer of counter-terms
            signal = Signal(
                tenant_id=self.tenant_id,
                source_agent_id=contract.producer_agent,
                target_agent_ids=[contract.consumer_agent],
                tier=SignalTierExt.CONTRACT_COUNTER,
                payload={"contract_id": contract_id, "counter_terms": counter_terms},
            )
            await self.signal_bus.emit(signal)
        else:
            # Direct agreement
            contract.status = ContractStatus.AGREED
            contract.agreed_at = datetime.now(timezone.utc)

            # Notify consumer
            signal = Signal(
                tenant_id=self.tenant_id,
                source_agent_id=contract.producer_agent,
                target_agent_ids=[contract.consumer_agent],
                tier=SignalTierExt.CONTRACT_AGREED,
                payload={"contract_id": contract_id, "terms": contract.to_dict()},
            )
            await self.signal_bus.emit(signal)

            # Signal waiting proposer
            if contract_id in self._pending_proposals:
                self._pending_proposals[contract_id].set()

        logger.info(
            f"Contract {'countered' if counter_terms else 'agreed'}",
            extra={"contract_id": contract_id},
        )

        return True

    async def execute_contract(self, contract_id: str, payload: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute contract with payload validation.

        Args:
            contract_id: Contract to execute
            payload: Data being delivered
        """
        if contract_id not in self._contracts:
            return {"success": False, "error": "Contract not found"}

        contract = self._contracts[contract_id]

        if contract.status != ContractStatus.AGREED:
            return {
                "success": False,
                "error": f"Contract not agreed (status: {contract.status})",
            }

        contract.status = ContractStatus.EXECUTING

        # Validate payload against schema
        is_valid, error_msg = contract.required_schema.validate_payload(payload)
        contract.payload_valid = is_valid
        contract.payload_delivered = payload

        if not is_valid:
            contract.status = ContractStatus.FAILED
            logger.error(
                "Contract execution failed: schema violation",
                extra={"contract_id": contract_id, "error": error_msg},
            )
            return {"success": False, "error": f"Schema validation failed: {error_msg}"}

        # Check deadline
        if contract.agreed_at is None:
            contract.status = ContractStatus.FAILED
            logger.error(
                "Contract execution failed: agreed_at is None",
                extra={"contract_id": contract_id},
            )
            return {
                "success": False,
                "error": "Contract not properly agreed (agreed_at is None)",
            }

        agreed_at = contract.agreed_at
        elapsed_ms = (datetime.now(timezone.utc) - agreed_at).total_seconds() * 1000
        if elapsed_ms > contract.deadline_ms:
            contract.status = ContractStatus.FAILED
            logger.error(
                "Contract execution failed: deadline exceeded",
                extra={"contract_id": contract_id, "elapsed_ms": elapsed_ms},
            )
            return {"success": False, "error": "Deadline exceeded"}

        # Mark completed
        contract.status = ContractStatus.COMPLETED
        contract.completed_at = datetime.now(timezone.utc)

        # Emit settlement signal
        signal = Signal(
            tenant_id=self.tenant_id,
            source_agent_id=contract.producer_agent,
            target_agent_ids=[contract.consumer_agent],
            tier=SignalTierExt.CONTRACT_SETTLE,
            payload={
                "contract_id": contract_id,
                "status": "completed",
                "prana_cost": contract.prana_cost,
                "execution_time_ms": elapsed_ms,
            },
        )
        await self.signal_bus.emit(signal)

        # Transfer prana
        await self._settle_prana(contract)

        logger.info(
            "Contract executed successfully",
            extra={"contract_id": contract_id, "execution_time_ms": elapsed_ms},
        )

        return {
            "success": True,
            "contract_id": contract_id,
            "execution_time_ms": elapsed_ms,
            "prana_transferred": contract.prana_cost,
        }

    async def wait_for_agreement(self, contract_id: str, timeout_ms: float = 10000) -> bool:
        """Wait for producer to agree to contract."""
        if contract_id not in self._pending_proposals:
            return False

        try:
            await asyncio.wait_for(
                self._pending_proposals[contract_id].wait(), timeout=timeout_ms / 1000
            )
            return True
        except TimeoutError:
            return False

    def get_contract(self, contract_id: str) -> A2AContract | None:
        """Get contract by ID."""
        return self._contracts.get(contract_id)

    def get_agent_contracts(
        self, agent_id: str, status: ContractStatus | None = None
    ) -> list[A2AContract]:
        """Get all contracts for an agent."""
        contracts = [
            c
            for c in self._contracts.values()
            if c.producer_agent == agent_id or c.consumer_agent == agent_id
        ]
        if status:
            contracts = [c for c in contracts if c.status == status]
        return contracts

    def get_prana_balance(self, agent_id: str) -> int:
        """Get prana balance for an agent."""
        return self._prana_ledger.get(agent_id, 0)

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except (asyncio.CancelledError, NotImplementedError):
                pass

    # Internal methods

    async def _listen_for_contracts(self) -> None:
        """Listen for contract-related signals."""
        raise NotImplementedError(
            "ContractManager background listener is not yet wired to Redis streams. See ADR-006."
        )

    async def _settle_prana(self, contract: A2AContract) -> None:
        """Transfer prana from consumer to producer."""
        # Deduct from consumer
        consumer_balance = self._prana_ledger.get(contract.consumer_agent, 0)
        self._prana_ledger[contract.consumer_agent] = consumer_balance - contract.prana_cost

        # Add to producer
        producer_balance = self._prana_ledger.get(contract.producer_agent, 0)
        self._prana_ledger[contract.producer_agent] = producer_balance + contract.prana_cost

        contract.settlement_confirmed = True


class SchemaRegistry:
    """Registry for reusable data schemas."""

    def __init__(self) -> None:
        self._schemas: dict[str, DataSchema] = {}

    def register_schema(self, schema_id: str, schema: DataSchema) -> None:
        """Register a reusable schema."""
        self._schemas[schema_id] = schema

    def get_schema(self, schema_id: str) -> DataSchema | None:
        """Get registered schema."""
        return self._schemas.get(schema_id)

    def get_standard_schema(self, schema_type: str) -> DataSchema | None:
        """Get standard enterprise schemas."""
        standard_schemas = {
            "employee_data": DataSchema(
                schema_name="employee_data",
                schema_definition={
                    "employee_id": "str",
                    "name": "str",
                    "department": "str",
                    "skills": "list",
                    "tenure_years": "float",
                },
                required_fields=["employee_id", "name"],
            ),
            "financial_metrics": DataSchema(
                schema_name="financial_metrics",
                schema_definition={
                    "revenue": "float",
                    "expenses": "float",
                    "profit_margin": "float",
                    "period": "str",
                },
                required_fields=["revenue", "expenses"],
            ),
            "security_alert": DataSchema(
                schema_name="security_alert",
                schema_definition={
                    "severity": "str",
                    "threat_type": "str",
                    "affected_systems": "list",
                    "timestamp": "str",
                },
                required_fields=["severity", "threat_type"],
            ),
        }
        return standard_schemas.get(schema_type)
