import logging
from typing import Any

from src.core.als.agents import departments as departments_module
from src.core.als.agents.departments import AGENT_REGISTRY
from src.core.als.agents.symbiotic_agent import SymbioticAgent
from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger(__name__)
_ORIGINAL_AGENT_REGISTRY = AGENT_REGISTRY


class BaseSupervisor(SymbioticAgent):
    """
    Abstract Base Class for all Domain Supervisors.
    Implements domain-agnostic logic for orchestration.
    """

    supervisor_id: str = ""
    domain: str = ""
    managed_agents: list[str] = []

    def __init__(self, agent_id: str, tenant_id: int, department: str, **kwargs: Any) -> None:
        if tenant_id is None:
            raise ValueError("tenant_id is required for multi-tenant isolation")

        super().__init__(agent_id=agent_id, tenant_id=tenant_id, agent_type="supervisor", **kwargs)
        self.department = department
        self.active_agents: list[str] = []
        self.supervisor_id = agent_id
        if not self.domain:
            self.domain = department
        self.managed_agents = list(self.managed_agents)

    async def decompose_task(self, task: TaskData) -> list[TaskData]:
        """Breekt een complexe taak op in kleinere, agent-specifieke taken."""
        raise NotImplementedError

    async def delegate(
        self,
        sub_tasks: list[Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: Any = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Delegate subtasks to managed agents and aggregate the results."""
        resolved_tenant_id = tenant_id if tenant_id is not None else self.tenant_id
        return {
            "status": "completed",
            "results": [
                {
                    "agent_id": getattr(subtask, "agent_id", None),
                    "task": getattr(subtask, "task", None),
                    "tenant_id": resolved_tenant_id,
                }
                for subtask in sub_tasks
            ],
        }

    async def handle_timeout(
        self, agent_id: str, task: Any, tenant_id: Any = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Handle agent timeout situations and escalate when required."""
        resolved_tenant_id = tenant_id if tenant_id is not None else self.tenant_id
        return {
            "status": "escalated",
            "agent_id": agent_id,
            "task": task,
            "tenant_id": resolved_tenant_id,
            "escalated_to": "cva.meta.supervisor",
        }

    async def select_agents(self, sub_tasks: list[TaskData]) -> list[str]:
        """
        Selecteert de meest geschikte agents op basis van de sub-taken.
        """
        registry = AGENT_REGISTRY
        if (
            AGENT_REGISTRY is _ORIGINAL_AGENT_REGISTRY
            and departments_module.AGENT_REGISTRY is not _ORIGINAL_AGENT_REGISTRY
        ):
            registry = departments_module.AGENT_REGISTRY

        selected: list[str] = []
        for task in sub_tasks:
            # Eenvoudige matching logica: zoek agents in de registry die bij dit departement horen
            # Dit kan later worden uitgebreid met semantische matching (Layer 3)
            for agent_key, (dept, class_name, tech) in registry.items():
                if dept == self.department:
                    selected.append(agent_key)

        return list(set(selected))  # Unieke agents

    async def arbitrate(self, results: list[ExecutionResult]) -> ExecutionResult:
        """
        Arbitreert tussen conflicterende resultaten van agents.
        Kiest het resultaat met de hoogste confidence_score.
        Bij een gelijke score (tie) wordt geescaleerd naar de CVASupervisor.
        """
        if not results:
            return ExecutionResult(
                task_id="arb",
                success=False,
                error_message="No results to arbitrate",
                tenant_id=self.tenant_id,
            )

        if len(results) == 1:
            return results[0]

        # Sorteer op confidence score (hoog naar laag)
        sorted_results = sorted(results, key=lambda x: x.confidence_score, reverse=True)

        best = sorted_results[0]
        second_best = sorted_results[1]

        # Check voor een 'tie' (gelijkspel) bij verschillende resultaten
        if (
            best.confidence_score == second_best.confidence_score
            and best.result_data != second_best.result_data
        ):
            logger.warning(f"Arbitration tie detected for task {best.task_id} between agents.")
            return ExecutionResult(
                task_id=best.task_id,
                success=False,
                error_message="Arbitration tie: high conflict detected",
                tenant_id=self.tenant_id,
            )

        # Voeg arbitratiestap toe aan het redeneringspad
        best.reasoning_path.append(
            f"Arbiter decided based on highest confidence score ({best.confidence_score})."
        )
        return best

    async def aggregate_results(self, results: list[ExecutionResult]) -> ExecutionResult:
        """Consolideert resultaten van verschillende agents naar een antwoord."""
        combined_output: dict[str, object] = {}
        for res in results:
            key = res.agent_id if res.agent_id is not None else "unknown"
            combined_output[key] = res.result_data

        return ExecutionResult(
            task_id="aggregated",
            success=True,
            result_data=combined_output,
            tenant_id=self.tenant_id,
        )

    async def escalate(self, task: TaskData, reason: str) -> None:
        """Stuurt de taak door naar de CVASupervisor bij problemen."""
        logger.warning(f"Supervisor {self.agent_id} escalating task {task.task_id}: {reason}")
        # Logica om te communiceren met CVASupervisor via de SignalBus
        pass

    async def execute(self, task: TaskData) -> ExecutionResult:
        """
        De standaard OODA-loop voor supervisors met telemetrie.
        """
        from src.core.monitoring.ooda_metrics import OODAMonitor

        monitor = OODAMonitor()

        # Stap 1 & 2: Orient (Decomposition)
        with monitor.track_phase(self.agent_id, self.tenant_id, "orient"):
            sub_tasks = await self.decompose_task(task)

        # Stap 3: Decide (Agent Selection)
        with monitor.track_phase(self.agent_id, self.tenant_id, "decide"):
            agents = await self.select_agents(sub_tasks)
            monitor.log_decision(self.agent_id, self.tenant_id, 1.0)

        if not agents:
            await self.escalate(task, "No suitable agents found in department")
            return ExecutionResult(task_id=task.task_id, success=False, tenant_id=self.tenant_id)

        # Stap 4: Act (Execution)
        with monitor.track_phase(self.agent_id, self.tenant_id, "act"):
            return await self.aggregate_results([])

    async def observe(
        self, signal: Any  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Observe phase: extract structured telemetry and context from incoming signal."""
        payload = getattr(signal, "payload", {}) or {}
        sig_type = getattr(signal, "signal_type", payload.get("signal_type", "unknown"))
        sender = getattr(signal, "source_agent_id", getattr(signal, "sender", "unknown"))
        tier_val = getattr(signal, "tier", "cognitive")
        tier_str = str(getattr(tier_val, "value", tier_val))

        target_dept = payload.get("target_department") or payload.get("department")
        target_agents = getattr(signal, "target_agent_ids", []) or []

        return {
            "signal_id": getattr(signal, "signal_id", getattr(signal, "id", None)),
            "signal_type": sig_type,
            "sender": sender,
            "tier": tier_str,
            "target_department": target_dept,
            "target_agent_ids": target_agents,
            "department": self.department,
            "payload": payload,
            "timestamp": (
                signal.timestamp.isoformat()
                if hasattr(signal, "timestamp") and signal.timestamp
                else ""
            ),
        }

    async def orient(
        self, observation: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Orient phase: evaluate domain relevance, urgency, and actionable next steps."""
        payload = observation.get("payload", {})
        sig_type = str(observation.get("signal_type", ""))
        payload_str = str(payload).lower()

        is_urgent = any(
            kw in payload_str
            for kw in ["critical", "emergency", "urgent", "error", "failure", "breach"]
        )
        target_dept = observation.get("target_department")
        target_agents = observation.get("target_agent_ids", [])

        if self.department in ("meta", "general"):
            is_relevant = True
        elif target_agents and self.agent_id not in target_agents:
            is_relevant = False
        elif target_dept and target_dept not in (self.department, "all", "broadcast"):
            is_relevant = False
        else:
            is_relevant = True

        return {
            "department": self.department,
            "signal_type": sig_type,
            "urgency": "critical" if is_urgent else "normal",
            "is_relevant": is_relevant,
            "actionable": bool(payload) and is_relevant,
            "target_agents": self.managed_agents,
            "context": payload,
        }

    async def decide(
        self, orientation: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Decide phase: choose routing, execution, or escalation strategy."""
        if not orientation.get("is_relevant"):
            return "ignore_irrelevant"
        if not orientation.get("actionable"):
            return "acknowledge_only"
        if orientation.get("urgency") == "critical":
            return "escalate_or_immediate_dispatch"
        return f"dispatch_to_{self.department}"

    async def act(self, decision: str) -> ExecutionResult:
        """Act phase: execute the decided dispatch or response action.

        Raises:
            NotImplementedError: Real dispatch to SignalBus is not yet implemented;
                no consumer wired. See ADR-036.
        """
        if decision == "ignore_irrelevant":
            return ExecutionResult(
                task_id=f"{self.department}_ignored",
                success=True,
                tenant_id=self.tenant_id,
                result_data={"status": "ignored", "reason": "not_relevant_for_department"},
            )
        raise NotImplementedError(
            "ALS BaseSupervisor dispatch to SignalBus is not yet implemented; "
            "no consumer wired. See ADR-036."
        )

