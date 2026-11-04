"""Knowledge Extractor - Helper for agents to extract insights from experiences.

This module provides utilities for agents to automatically extract
shareable insights from their task executions.
"""

import logging
from typing import Any, Optional

from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger("KnowledgeExtractor")


class KnowledgeExtractor:
    """Extracts insights from agent task executions.

    Analyzes successful (and failed) task executions to identify
    patterns that can be shared with other agents.

    Example:
        extractor = KnowledgeExtractor()

        # After task completion
        insight = extractor.extract_from_success(
            agent_id="code_agent_1",
            task=task_data,
            result=execution_result,
            context={"legacy_codebase": True, "language": "python"}
        )

        if insight:
            await collective_memory.store_insight(**insight)
    """

    def __init__(self) -> None:
        self.extraction_rules = self._init_extraction_rules()

    def extract_from_success(
        self,
        agent_id: str,
        task: TaskData,
        result: ExecutionResult,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Extract insight from a successful task execution.

        Args:
            agent_id: Agent that completed the task
            task: Original task data
            result: Successful execution result
            context: Additional context about the task

        Returns:
            Insight dictionary ready for storage, or None if no insight extracted
        """
        context = context or {}

        # Determine insight type from task
        insight_type = self._classify_task(task)

        # Extract key learnings
        content = self._extract_success_patterns(task, result, context)

        if not content:
            return None

        return {
            "agent_id": agent_id,
            "insight_type": insight_type,
            "context": self._determine_context(task, context),
            "content": content,
            "confidence": self._calculate_confidence(result),
            "metadata": {
                "task_id": task.id,
                "execution_time": result.execution_time,
                "extracted_from": "success",
            },
        }

    def extract_from_failure(
        self,
        agent_id: str,
        task: TaskData,
        result: ExecutionResult,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Extract lesson from a failed task execution.

        Args:
            agent_id: Agent that attempted the task
            task: Original task data
            result: Failed execution result
            context: Additional context

        Returns:
            Insight dictionary with anti-pattern/lesson, or None
        """
        context = context or {}

        if not result.error_message:
            return None

        # Extract the lesson from the failure
        content = {
            "failure_type": self._classify_failure(result.error_message),
            "error_pattern": result.error_message[:200],  # Truncate long errors
            "prevention_steps": self._suggest_prevention(task, result),
            "task_context": {"title": task.title, "tags": task.tags},
        }

        return {
            "agent_id": agent_id,
            "insight_type": "lesson",  # Will be converted to InsightType.LESSON
            "context": f"failure_{self._classify_failure(result.error_message)}",
            "content": content,
            "confidence": 0.6,  # Lower confidence for failures
            "metadata": {
                "task_id": task.id,
                "error_message": result.error_message[:500],
                "extracted_from": "failure",
            },
        }

    def extract_patterns_from_history(
        self, agent_id: str, task_history: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Extract patterns from multiple similar task executions.

        Args:
            agent_id: Agent analyzing history
            task_history: List[Any] of {task, result, context} dictionaries  # TODO(TYPE): replace Any with concrete type

        Returns: List[Any] of extracted insights  # TODO(TYPE): replace Any with concrete type
        """
        insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if len(task_history) < 3:
            return insights  # Need at least 3 for patterns

        # Group by task type
        by_type: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for entry in task_history:
            task_type = entry["task"].title if hasattr(entry["task"], "title") else "unknown"
            by_type.setdefault(task_type, []).append(entry)

        # Find common success patterns
        for task_type, entries in by_type.items():
            if len(entries) < 3:
                continue

            success_count = sum(1 for e in entries if e["result"].success)
            if success_count >= 2:
                # Extract common successful approach
                pattern = self._extract_common_pattern(entries)
                if pattern:
                    insights.append(
                        {
                            "agent_id": agent_id,
                            "insight_type": "pattern",
                            "context": task_type,
                            "content": pattern,
                            "confidence": success_count / len(entries),
                            "metadata": {
                                "based_on": len(entries),
                                "success_rate": success_count / len(entries),
                            },
                        }
                    )

        return insights

    # Private helper methods

    def _init_extraction_rules(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Initialize extraction rules for different task types."""
        return {
            "refactor": {
                "keywords": ["refactor", "rewrite", "clean", "optimize"],
                "extract_fields": ["before_state", "after_state", "technique_used"],
            },
            "security": {
                "keywords": ["security", "vulnerability", "fix", "patch"],
                "extract_fields": ["vulnerability_type", "fix_applied", "severity"],
            },
            "performance": {
                "keywords": ["performance", "speed", "slow", "optimize", "cache"],
                "extract_fields": ["bottleneck", "optimization", "improvement"],
            },
        }

    def _classify_task(self, task: TaskData) -> str:
        """Classify task type for insight categorization."""
        title_lower = task.title.lower() if hasattr(task, "title") else ""
        tags_lower = [t.lower() for t in task.tags] if hasattr(task, "tags") else []

        # Check against rules
        for category, rules in self.extraction_rules.items():
            keywords = rules["keywords"]
            if any(kw in title_lower for kw in keywords):
                return category
            if any(kw in " ".join(tags_lower) for kw in keywords):
                return category

        return "general"

    def _extract_success_patterns(
        self, task: TaskData, result: ExecutionResult, context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Extract patterns from successful execution."""
        content = {
            "task_title": task.title if hasattr(task, "title") else "Unknown",
            "approach_used": result.result_data if result.result_data else {},
            "execution_time": result.execution_time,
            "context_factors": context,
        }

        # Add specific learnings based on task type
        task_type = self._classify_task(task)
        if task_type == "refactor":
            content["technique"] = self._detect_refactoring_technique(result)
        elif task_type == "security":
            content["vulnerability_fixed"] = context.get("vulnerability_type", "unknown")

        return content

    def _determine_context(self, task: TaskData, context: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Determine the context string for storage."""
        # Build context from task and additional context
        parts: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if hasattr(task, "title"):
            # Extract key words from title
            title_words = task.title.lower().split()[:3]
            parts.append("_".join(title_words))

        # Add significant context factors
        significant_keys = ["language", "framework", "legacy", "critical"]
        for key in significant_keys:
            if key in context and context[key]:
                parts.append(str(context[key]).lower())

        return "_".join(parts) if parts else "general"

    def _calculate_confidence(self, result: ExecutionResult) -> float:
        """Calculate confidence score for extracted insight."""
        confidence = 0.5  # Base confidence

        # Higher confidence for faster executions (less variance)
        if result.execution_time < 1.0:
            confidence += 0.2
        elif result.execution_time < 5.0:
            confidence += 0.1

        # Higher confidence if result has data
        if result.result_data:
            confidence += 0.2

        return min(1.0, confidence)

    def _classify_failure(self, error_message: str | None) -> str:
        """Classify failure type from error message."""
        if not error_message:
            return "unknown"
        error_lower = error_message.lower()

        failure_types = {
            "timeout": ["timeout", "timed out", "deadline"],
            "connection": ["connection", "network", "unreachable"],
            "permission": ["permission", "access denied", "unauthorized"],
            "validation": ["validation", "invalid", "schema"],
            "resource": ["resource", "memory", "disk", "quota"],
        }

        for failure_type, keywords in failure_types.items():
            if any(kw in error_lower for kw in keywords):
                return failure_type

        return "unknown"

    def _suggest_prevention(self, task: TaskData, result: ExecutionResult) -> list[str]:
        """Suggest prevention steps based on failure."""
        suggestions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        failure_type = self._classify_failure(result.error_message)

        prevention_map = {
            "timeout": [
                "Add timeout handling",
                "Implement retry logic",
                "Break task into smaller chunks",
            ],
            "connection": [
                "Check network connectivity",
                "Verify service availability",
                "Add connection pooling",
            ],
            "permission": [
                "Verify credentials",
                "Check access rights",
                "Request necessary permissions",
            ],
            "validation": [
                "Validate inputs before processing",
                "Add schema validation",
                "Sanitize user input",
            ],
            "resource": [
                "Monitor resource usage",
                "Implement rate limiting",
                "Optimize resource allocation",
            ],
        }

        return prevention_map.get(failure_type, ["Review error logs", "Add error handling"])

    def _extract_common_pattern(self, entries: list[dict[str, Any]]) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Extract common pattern from multiple similar entries."""
        if not entries:
            return None

        # Find common success factors
        successful = [e for e in entries if e["result"].success]
        if not successful:
            return None

        # Extract common approach
        approaches: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for entry in successful:
            if entry["result"].result_data:
                approaches.append(entry["result"].result_data)

        if not approaches:
            return None

        return {
            "pattern_type": "successful_approach",
            "sample_size": len(successful),
            "common_factors": self._find_common_factors(approaches),
            "recommendation": "This approach has worked consistently",
        }

    def _find_common_factors(self, approaches: list[dict[str, Any]]) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Find common keys across multiple approach dictionaries."""
        if not approaches:
            return []

        # Get keys from first approach
        common_keys = set(approaches[0].keys())

        # Intersect with other approaches
        for approach in approaches[1:]:
            common_keys &= set(approach.keys())

        return list(common_keys)

    def _detect_refactoring_technique(self, result: ExecutionResult) -> str:
        """Detect which refactoring technique was used."""
        result_data = result.result_data or {}

        techniques = {
            "extract_method": ["extract", "method", "function"],
            "rename_variable": ["rename", "variable", "parameter"],
            "inline_method": ["inline", "remove_method"],
            "move_method": ["move", "relocate"],
        }

        result_str = str(result_data).lower()

        for technique, keywords in techniques.items():
            if any(kw in result_str for kw in keywords):
                return technique

        return "unknown"
