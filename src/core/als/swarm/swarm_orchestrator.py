"""Swarm Orchestrator - Dynamic agent team formation.

This module enables dynamic formation of agent swarms (teams) for complex tasks,
with automatic role assignment and lifecycle management.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger("SwarmOrchestrator")


class SwarmRole(str, Enum):
    """Predefined roles in a swarm."""

    LEADER = "leader"  # Coordinates the swarm
    STRATEGIST = "strategist"  # Plans approach
    EXECUTOR = "executor"  # Does the work
    REVIEWER = "reviewer"  # Reviews outputs
    SPECIALIST = "specialist"  # Domain expert
    SUPPORT = "support"  # Helper role


class SwarmMember:
    """A member of a swarm.

    Attributes:
        agent_id: Agent identifier
        role: Role in the swarm
        capabilities: Capabilities this agent provides
        assigned_tasks: Tasks currently assigned
        status: Current status
    """

    def __init__(
        self, agent_id: str, role: SwarmRole, capabilities: list[str] | None = None
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.capabilities = capabilities or []
        self.assigned_tasks: list[str] = []
        self.status = "idle"  # idle, working, completed, failed
        self.joined_at = datetime.now(timezone.utc)
        self.completed_tasks = 0

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "capabilities": self.capabilities,
            "status": self.status,
            "assigned_tasks": self.assigned_tasks,
            "completed_tasks": self.completed_tasks,
            "joined_at": self.joined_at.isoformat(),
        }


class Swarm:
    """A dynamic team of agents working on a mission.

    Attributes:
        swarm_id: Unique identifier
        tenant_id: Tenant scope
        mission: Mission description
        members: Swarm members
        status: Swarm status
        created_at: Creation time
        completed_at: Completion time
        results: Mission results
    """

    def __init__(
        self, tenant_id: int, mission: str, required_capabilities: list[str], max_size: int = 5
    ) -> None:
        self.swarm_id = str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.mission = mission
        self.required_capabilities = required_capabilities
        self.max_size = max_size

        self.members: dict[str, SwarmMember] = {}
        self.status = "forming"  # forming, active, completing, completed, dissolved
        self.created_at = datetime.now(timezone.utc)
        self.activated_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.results: ExecutionResult | None = None
        self.task_assignments: dict[str, str] = {}  # task_id -> agent_id

        logger.info(f"Swarm {self.swarm_id} created for mission: {mission}")

    @property
    def size(self) -> int:
        """Current swarm size."""
        return len(self.members)

    @property
    def is_full(self) -> bool:
        """Check if swarm is at max capacity."""
        return self.size >= self.max_size

    @property
    def leader(self) -> SwarmMember | None:
        """Get swarm leader."""
        for member in self.members.values():
            if member.role == SwarmRole.LEADER:
                return member
        return None

    @property
    def active_members(self) -> list[SwarmMember]:
        """Get members still working."""
        return [m for m in self.members.values() if m.status == "working"]

    def add_member(
        self, agent_id: str, role: SwarmRole, capabilities: list[str] | None = None
    ) -> bool:
        """Add a member to the swarm.

        Returns:
            True if added successfully, False if swarm is full
        """
        if self.is_full:
            logger.warning(f"Swarm {self.swarm_id} is full, cannot add {agent_id}")
            return False

        if agent_id in self.members:
            logger.warning(f"Agent {agent_id} already in swarm {self.swarm_id}")
            return False

        self.members[agent_id] = SwarmMember(agent_id, role, capabilities)
        logger.info(f"Agent {agent_id} added to swarm {self.swarm_id} as {role.value}")

        return True

    def remove_member(self, agent_id: str) -> bool:
        """Remove a member from the swarm."""
        if agent_id not in self.members:
            return False

        del self.members[agent_id]
        logger.info(f"Agent {agent_id} removed from swarm {self.swarm_id}")
        return True

    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """Assign a task to a swarm member."""
        if agent_id not in self.members:
            return False

        member = self.members[agent_id]
        member.assigned_tasks.append(task_id)
        member.status = "working"
        self.task_assignments[task_id] = agent_id

        return True

    def complete_task(self, task_id: str, success: bool = True) -> bool:
        """Mark a task as completed."""
        if task_id not in self.task_assignments:
            return False

        agent_id = self.task_assignments[task_id]
        member = self.members[agent_id]

        if success:
            member.completed_tasks += 1

        # Check if member has more tasks
        if task_id in member.assigned_tasks:
            member.assigned_tasks.remove(task_id)

        if not member.assigned_tasks:
            member.status = "completed" if success else "failed"

        return True

    def activate(self) -> None:
        """Activate the swarm to start working."""
        if self.size == 0:
            raise ValueError("Cannot activate empty swarm")

        if not self.leader:
            # Assign first member as leader if no leader
            first_member = list(self.members.values())[0]
            first_member.role = SwarmRole.LEADER
            logger.info(f"Agent {first_member.agent_id} assigned as leader")

        self.status = "active"
        self.activated_at = datetime.now(timezone.utc)
        logger.info(f"Swarm {self.swarm_id} activated with {self.size} members")

    def complete(self, results: ExecutionResult) -> None:
        """Complete the swarm mission."""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
        self.results = results
        logger.info(f"Swarm {self.swarm_id} completed mission")

    def dissolve(self) -> None:
        """Dissolve the swarm."""
        self.status = "dissolved"
        self.completed_at = datetime.now(timezone.utc)
        logger.info(f"Swarm {self.swarm_id} dissolved")

    def get_capabilities_coverage(self) -> dict[str, bool]:
        """Check which required capabilities are covered."""
        covered = set()
        for member in self.members.values():
            covered.update(member.capabilities)

        return {cap: cap in covered for cap in self.required_capabilities}

    @property
    def capability_coverage_ratio(self) -> float:
        """Ratio of required capabilities that are covered."""
        coverage = self.get_capabilities_coverage()
        if not coverage:
            return 1.0
        return sum(coverage.values()) / len(coverage)

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "swarm_id": self.swarm_id,
            "tenant_id": self.tenant_id,
            "mission": self.mission,
            "required_capabilities": self.required_capabilities,
            "max_size": self.max_size,
            "size": self.size,
            "status": self.status,
            "members": [m.to_dict() for m in self.members.values()],
            "capability_coverage": self.get_capabilities_coverage(),
            "created_at": self.created_at.isoformat(),
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class SwarmOrchestrator:
    """Orchestrates dynamic formation and management of agent swarms.

    Manages swarm lifecycle from formation through execution to dissolution.

    Example:
        orchestrator = SwarmOrchestrator(tenant_id=123)

        # Form swarm for complex task
        swarm = await orchestrator.form_swarm(
            mission="Refactor legacy authentication system",
            required_capabilities=["architecture", "security", "testing"],
            available_agents=["architect_1", "security_1", "code_1", "test_1"],
            min_size=3,
            max_size=4
        )

        # Activate and execute
        await orchestrator.activate_swarm(swarm.swarm_id)

        # Monitor progress
        status = orchestrator.get_swarm_status(swarm.swarm_id)

        # Complete
        await orchestrator.complete_swarm(swarm.swarm_id, results)
    """

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self._swarms: dict[str, Swarm] = {}
        self._agent_swarm_map: dict[str, str] = {}  # agent_id -> swarm_id
        logger.info(f"SwarmOrchestrator initialized for tenant {tenant_id}")

    async def form_swarm(
        self,
        mission: str,
        required_capabilities: list[str],
        available_agents: list[str],
        agent_capabilities: dict[str, list[str]] | None = None,
        min_size: int = 2,
        max_size: int = 5,
        priority: str = "normal",
    ) -> Swarm | None:
        """Form a new swarm for a mission.

        Args:
            mission: Mission description
            required_capabilities: Capabilities needed
            available_agents: Pool of available agents
            agent_capabilities: Map of agent -> capabilities
            min_size: Minimum swarm size
            max_size: Maximum swarm size
            priority: Mission priority

        Returns:
            Formed Swarm or None if formation failed
        """
        agent_capabilities = agent_capabilities or {}

        # Create swarm
        swarm = Swarm(
            tenant_id=self.tenant_id,
            mission=mission,
            required_capabilities=required_capabilities,
            max_size=max_size,
        )

        # Select agents based on capabilities
        selected_agents = self._select_agents_for_swarm(
            available_agents=available_agents,
            agent_capabilities=agent_capabilities,
            required_capabilities=required_capabilities,
            max_size=max_size,
        )

        if len(selected_agents) < min_size:
            logger.warning(
                f"Not enough agents for swarm. Required {min_size}, "
                f"found {len(selected_agents)}"
            )
            return None

        # Assign roles and add to swarm
        for i, (agent_id, capabilities) in enumerate(selected_agents):
            role = self._assign_role(i, capabilities)
            swarm.add_member(agent_id, role, capabilities)
            self._agent_swarm_map[agent_id] = swarm.swarm_id

        # Store swarm
        self._swarms[swarm.swarm_id] = swarm

        logger.info(
            f"Swarm {swarm.swarm_id} formed with {swarm.size} agents " f"for mission: {mission}"
        )

        return swarm

    async def activate_swarm(self, swarm_id: str) -> bool:
        """Activate a swarm to begin mission execution.

        Args:
            swarm_id: Swarm to activate

        Returns:
            True if activated successfully
        """
        swarm = self._swarms.get(swarm_id)
        if not swarm:
            logger.error(f"Swarm not found: {swarm_id}")
            return False

        try:
            swarm.activate()
            return True
        except ValueError as e:
            logger.error(f"Failed to activate swarm: {e}")
            return False

    async def assign_task_to_swarm(
        self, swarm_id: str, task: TaskData, preferred_agent: str | None = None
    ) -> str | None:
        """Assign a task to a swarm member.

        Args:
            swarm_id: Target swarm
            task: Task to assign
            preferred_agent: Preferred agent (optional)

        Returns:
            Assigned agent ID or None
        """
        swarm = self._swarms.get(swarm_id)
        if not swarm or swarm.status != "active":
            return None

        # Use preferred agent if available
        agent_id: str | None = None
        if preferred_agent and preferred_agent in swarm.members:
            agent_id = preferred_agent
        else:
            # Find best available agent
            agent_id = self._find_best_agent_for_task(swarm, task)

        if agent_id:
            swarm.assign_task(task.id, agent_id)
            logger.debug(f"Task {task.id} assigned to {agent_id} in swarm {swarm_id}")

        return agent_id

    async def complete_task(self, swarm_id: str, task_id: str, success: bool = True) -> bool:
        """Mark a task as completed in a swarm.

        Returns:
            True if task was found and marked complete
        """
        swarm = self._swarms.get(swarm_id)
        if not swarm:
            return False

        return swarm.complete_task(task_id, success)

    async def complete_swarm(self, swarm_id: str, results: ExecutionResult) -> bool:
        """Complete a swarm mission.

        Args:
            swarm_id: Swarm to complete
            results: Mission results

        Returns:
            True if completed successfully
        """
        swarm = self._swarms.get(swarm_id)
        if not swarm:
            return False

        swarm.complete(results)

        # Clean up agent mappings
        for agent_id in list(swarm.members.keys()):
            if agent_id in self._agent_swarm_map:
                del self._agent_swarm_map[agent_id]

        return True

    async def dissolve_swarm(self, swarm_id: str) -> bool:
        """Dissolve a swarm.

        Args:
            swarm_id: Swarm to dissolve

        Returns:
            True if dissolved successfully
        """
        swarm = self._swarms.get(swarm_id)
        if not swarm:
            return False

        swarm.dissolve()

        # Clean up agent mappings
        for agent_id in list(swarm.members.keys()):
            if self._agent_swarm_map.get(agent_id) == swarm_id:
                del self._agent_swarm_map[agent_id]

        # Optionally remove from active swarms
        # del self._swarms[swarm_id]  # Keep for history

        return True

    def get_swarm_status(self, swarm_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get current status of a swarm."""
        swarm = self._swarms.get(swarm_id)
        if not swarm:
            return None

        return swarm.to_dict()

    def get_swarm_for_agent(self, agent_id: str) -> str | None:
        """Get swarm ID for an agent."""
        return self._agent_swarm_map.get(agent_id)

    def get_active_swarms(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get all active swarms."""
        return [
            swarm.to_dict()
            for swarm in self._swarms.values()
            if swarm.status in ["forming", "active", "completing"]
        ]

    def get_agent_workload(self, agent_id: str) -> int:
        """Get number of tasks assigned to an agent."""
        swarm_id = self._agent_swarm_map.get(agent_id)
        if not swarm_id:
            return 0

        swarm = self._swarms.get(swarm_id)
        if not swarm or agent_id not in swarm.members:
            return 0

        return len(swarm.members[agent_id].assigned_tasks)

    def _select_agents_for_swarm(
        self,
        available_agents: list[str],
        agent_capabilities: dict[str, list[str]],
        required_capabilities: list[str],
        max_size: int,
    ) -> list[tuple[str, list[str]]]:
        """Select best agents for swarm based on capabilities."""
        selected: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        covered_capabilities: set[str] = set()

        # Sort agents by number of matching capabilities
        agent_scores: list[tuple[str, set[str], int]] = []
        for agent_id in available_agents:
            caps = set(agent_capabilities.get(agent_id, []))
            matching = caps & set(required_capabilities)
            score = len(matching)
            agent_scores.append((agent_id, caps, score))

        # Sort by score descending
        agent_scores.sort(key=lambda x: x[2], reverse=True)

        # Select agents until we cover all capabilities or reach max
        for agent_id, caps, score in agent_scores:
            if len(selected) >= max_size:
                break

            # Check if this agent adds new capabilities
            new_caps = caps - covered_capabilities
            if new_caps or len(selected) < 2:  # Always take at least 2
                selected.append((agent_id, list(caps)))
                covered_capabilities.update(caps)

        return selected

    def _assign_role(self, index: int, capabilities: list[str]) -> SwarmRole:
        """Assign role based on position and capabilities."""
        caps_lower = [c.lower() for c in capabilities]

        # First agent is leader
        if index == 0:
            return SwarmRole.LEADER

        # Check for specific capabilities
        if any("strateg" in c or "architect" in c for c in caps_lower):
            return SwarmRole.STRATEGIST
        elif any("review" in c or "qa" in c or "test" in c for c in caps_lower):
            return SwarmRole.REVIEWER
        elif any("specialist" in c or "expert" in c for c in caps_lower):
            return SwarmRole.SPECIALIST
        elif index == 1:
            return SwarmRole.STRATEGIST
        else:
            return SwarmRole.EXECUTOR

    def _find_best_agent_for_task(self, swarm: Swarm, task: TaskData) -> str | None:
        """Find best available agent for a task."""
        # Get idle members
        idle_members = [m for m in swarm.members.values() if m.status == "idle"]

        if not idle_members:
            # Get member with fewest tasks
            working = [m for m in swarm.members.values() if m.status == "working"]
            if working:
                return min(working, key=lambda m: len(m.assigned_tasks)).agent_id
            return None

        # Score by task type match
        task_title = task.title.lower() if hasattr(task, "title") else ""

        def score_member(member: SwarmMember) -> float:
            score = 0.0
            caps_lower = [c.lower() for c in member.capabilities]

            if any(kw in task_title for kw in ["refactor", "clean"]):
                if any("refactor" in c or "code" in c for c in caps_lower):
                    score += 1.0
            elif any(kw in task_title for kw in ["security", "vulnerability"]):
                if any("security" in c for c in caps_lower):
                    score += 1.0
            elif any(kw in task_title for kw in ["test", "spec"]):
                if any("test" in c or "qa" in c for c in caps_lower):
                    score += 1.0

            # Prefer members with fewer tasks
            score -= len(member.assigned_tasks) * 0.1

            return score

        idle_members.sort(key=score_member, reverse=True)
        return idle_members[0].agent_id

    def get_orchestrator_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get orchestrator statistics."""
        active_swarms = self.get_active_swarms()

        return {
            "total_swarms": len(self._swarms),
            "active_swarms": len(active_swarms),
            "agents_in_swarms": len(self._agent_swarm_map),
            "swarm_status_distribution": self._count_swarm_statuses(),
        }

    def _count_swarm_statuses(self) -> dict[str, int]:
        """Count swarms by status."""
        counts: dict[str, int] = {}
        for swarm in self._swarms.values():
            counts[swarm.status] = counts.get(swarm.status, 0) + 1
        return counts
