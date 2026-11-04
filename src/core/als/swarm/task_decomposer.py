"""Task Decomposer - Breaks complex tasks into subtasks for swarm execution."""

import logging
from typing import Any, Dict, List, Optional, Set

from src.core.shared.interfaces import TaskData

logger = logging.getLogger("TaskDecomposer")


class TaskDecomposer:
    """Decomposes complex tasks into manageable subtasks for swarm execution.

    Example:
        decomposer = TaskDecomposer()

        subtasks = decomposer.decompose(
            task=complex_task,
            swarm_capabilities=["architecture", "coding", "testing"]
        )
    """

    def __init__(self) -> None:
        self.decomposition_patterns = self._init_patterns()

    def decompose(
        self, task: TaskData, swarm_capabilities: list[str], max_subtasks: int = 10
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Decompose a task into subtasks.

        Args:
            task: Complex task to decompose
            swarm_capabilities: Capabilities available in swarm
            max_subtasks: Maximum number of subtasks

        Returns: List[Any] of subtask definitions  # TODO(TYPE): replace Any with concrete type
        """
        task_type = self._classify_task(task)

        # Get decomposition pattern
        if task_type in self.decomposition_patterns:
            pattern = self.decomposition_patterns[task_type]
            subtasks = pattern(task, swarm_capabilities)
        else:
            subtasks = self._default_pattern(task, swarm_capabilities)

        # Limit number of subtasks
        if len(subtasks) > max_subtasks:
            logger.warning(
                f"Task decomposed into {len(subtasks)} subtasks, limiting to {max_subtasks}"
            )
            subtasks = subtasks[:max_subtasks]

        # Assign dependencies
        subtasks = self._assign_dependencies(subtasks)

        return subtasks

    def estimate_complexity(self, task: TaskData) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Estimate task complexity for swarm sizing.

        Returns:
            Complexity estimate with recommended swarm size
        """
        # Base complexity
        complexity = 5  # Medium

        # Adjust based on description length
        if hasattr(task, "description"):
            desc_len = len(task.description)
            if desc_len > 500:
                complexity += 3
            elif desc_len > 200:
                complexity += 1

        # Adjust based on tags
        if hasattr(task, "tags"):
            tags_lower = [t.lower() for t in task.tags]
            if any(t in tags_lower for t in ["complex", "large", "migration"]):
                complexity += 2
            if any(t in tags_lower for t in ["critical", "urgent"]):
                complexity += 1

        # Determine swarm size
        if complexity <= 3:
            recommended_size = 2
        elif complexity <= 6:
            recommended_size = 3
        elif complexity <= 9:
            recommended_size = 4
        else:
            recommended_size = 5

        return {
            "complexity_score": min(10, complexity),
            "recommended_swarm_size": recommended_size,
            "estimated_duration_hours": complexity * 2,
            "parallelizable": complexity > 5,
        }

    def _init_patterns(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Initialize decomposition patterns for different task types."""
        return {
            "refactoring": self._refactoring_pattern,
            "feature_development": self._feature_dev_pattern,
            "security_audit": self._security_audit_pattern,
            "performance_optimization": self._performance_pattern,
            "general": self._default_pattern,
        }

    def _classify_task(self, task: TaskData) -> str:
        """Classify task type."""
        if hasattr(task, "title"):
            title_lower = task.title.lower()

            if any(kw in title_lower for kw in ["refactor", "rewrite", "clean"]):
                return "refactoring"
            elif any(kw in title_lower for kw in ["security", "vulnerability", "audit"]):
                return "security_audit"
            elif any(kw in title_lower for kw in ["performance", "optimize", "speed"]):
                return "performance_optimization"
            elif any(kw in title_lower for kw in ["feature", "implement", "add"]):
                return "feature_development"

        if hasattr(task, "tags"):
            tags_lower = [t.lower() for t in task.tags]
            if any(t in tags_lower for t in ["refactoring"]):
                return "refactoring"
            elif any(t in tags_lower for t in ["security"]):
                return "security_audit"
            elif any(t in tags_lower for t in ["performance"]):
                return "performance_optimization"

        return "general"

    def _refactoring_pattern(self, task: TaskData, capabilities: list[str]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Decomposition pattern for refactoring tasks."""
        return [
            {
                "title": "Analyze current codebase",
                "description": "Identify refactoring targets and risks",
                "required_capabilities": ["analysis", "architecture"],
                "estimated_effort": "2h",
                "priority": 1,
            },
            {
                "title": "Design new structure",
                "description": "Plan the refactored architecture",
                "required_capabilities": ["architecture", "design"],
                "estimated_effort": "3h",
                "priority": 2,
                "depends_on": [0],
            },
            {
                "title": "Implement core changes",
                "description": "Execute the refactoring",
                "required_capabilities": ["coding", "refactoring"],
                "estimated_effort": "6h",
                "priority": 3,
                "depends_on": [1],
            },
            {
                "title": "Update tests",
                "description": "Adapt tests to new structure",
                "required_capabilities": ["testing"],
                "estimated_effort": "3h",
                "priority": 4,
                "depends_on": [2],
            },
            {
                "title": "Review and validate",
                "description": "Final review and verification",
                "required_capabilities": ["review", "testing"],
                "estimated_effort": "2h",
                "priority": 5,
                "depends_on": [2, 3],
            },
        ]

    def _feature_dev_pattern(self, task: TaskData, capabilities: list[str]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Decomposition pattern for feature development."""
        return [
            {
                "title": "Requirements analysis",
                "description": "Clarify feature requirements",
                "required_capabilities": ["analysis"],
                "estimated_effort": "2h",
                "priority": 1,
            },
            {
                "title": "Design solution",
                "description": "Design the feature architecture",
                "required_capabilities": ["design", "architecture"],
                "estimated_effort": "3h",
                "priority": 2,
                "depends_on": [0],
            },
            {
                "title": "Implement backend",
                "description": "Build backend functionality",
                "required_capabilities": ["backend", "coding"],
                "estimated_effort": "6h",
                "priority": 3,
                "depends_on": [1],
            },
            {
                "title": "Implement frontend",
                "description": "Build frontend interface",
                "required_capabilities": ["frontend", "coding"],
                "estimated_effort": "5h",
                "priority": 3,
                "depends_on": [1],
            },
            {
                "title": "Integration testing",
                "description": "Test complete feature",
                "required_capabilities": ["testing"],
                "estimated_effort": "3h",
                "priority": 4,
                "depends_on": [2, 3],
            },
        ]

    def _security_audit_pattern(
        self, task: TaskData, capabilities: list[str]
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Decomposition pattern for security audits."""
        return [
            {
                "title": "Scope definition",
                "description": "Define audit scope and objectives",
                "required_capabilities": ["security", "analysis"],
                "estimated_effort": "1h",
                "priority": 1,
            },
            {
                "title": "Automated scanning",
                "description": "Run automated security tools",
                "required_capabilities": ["security", "automation"],
                "estimated_effort": "2h",
                "priority": 2,
                "depends_on": [0],
            },
            {
                "title": "Manual code review",
                "description": "Manual security review",
                "required_capabilities": ["security", "review"],
                "estimated_effort": "4h",
                "priority": 3,
                "depends_on": [1],
            },
            {
                "title": "Vulnerability assessment",
                "description": "Assess found vulnerabilities",
                "required_capabilities": ["security"],
                "estimated_effort": "2h",
                "priority": 4,
                "depends_on": [2],
            },
            {
                "title": "Report generation",
                "description": "Create security audit report",
                "required_capabilities": ["security", "documentation"],
                "estimated_effort": "2h",
                "priority": 5,
                "depends_on": [3],
            },
        ]

    def _performance_pattern(self, task: TaskData, capabilities: list[str]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Decomposition pattern for performance optimization."""
        return [
            {
                "title": "Performance profiling",
                "description": "Identify performance bottlenecks",
                "required_capabilities": ["performance", "profiling"],
                "estimated_effort": "2h",
                "priority": 1,
            },
            {
                "title": "Analysis and diagnosis",
                "description": "Analyze profiling results",
                "required_capabilities": ["performance", "analysis"],
                "estimated_effort": "2h",
                "priority": 2,
                "depends_on": [0],
            },
            {
                "title": "Optimization implementation",
                "description": "Implement optimizations",
                "required_capabilities": ["performance", "coding"],
                "estimated_effort": "4h",
                "priority": 3,
                "depends_on": [1],
            },
            {
                "title": "Benchmark validation",
                "description": "Verify performance improvements",
                "required_capabilities": ["performance", "testing"],
                "estimated_effort": "2h",
                "priority": 4,
                "depends_on": [2],
            },
        ]

    def _default_pattern(self, task: TaskData, capabilities: list[str]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Default decomposition pattern."""
        return [
            {
                "title": "Task analysis",
                "description": "Analyze and understand requirements",
                "required_capabilities": ["analysis"],
                "estimated_effort": "2h",
                "priority": 1,
            },
            {
                "title": "Implementation",
                "description": "Execute the task",
                "required_capabilities": ["coding"],
                "estimated_effort": "4h",
                "priority": 2,
                "depends_on": [0],
            },
            {
                "title": "Review and testing",
                "description": "Validate implementation",
                "required_capabilities": ["testing", "review"],
                "estimated_effort": "2h",
                "priority": 3,
                "depends_on": [1],
            },
        ]

    def _assign_dependencies(self, subtasks: list[dict[str, Any]]) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Ensure dependency references are valid."""
        for i, subtask in enumerate(subtasks):
            # Set default priority if not present
            if "priority" not in subtask:
                subtask["priority"] = i + 1

            # Ensure dependencies reference valid indices
            if "depends_on" in subtask:
                subtask["depends_on"] = [
                    d for d in subtask["depends_on"] if 0 <= d < len(subtasks) and d != i
                ]
            else:
                subtask["depends_on"] = []

            # Set subtask ID
            subtask["subtask_id"] = f"subtask_{i}"

        return subtasks
