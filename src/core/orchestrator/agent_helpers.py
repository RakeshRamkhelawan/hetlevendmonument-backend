"""
Agent Helpers for GitHub Copilot Orchestration

This module provides helper functions for the main orchestrating agent
to easily spawn and manage subagents.
"""

import json
from dataclasses import dataclass
from typing import Any, Optional

from .copilot_orchestrator import CopilotOrchestrator, OrchestratorTask, TaskResult


@dataclass
class QuickTask:
    """Simplified task definition for quick usage"""

    description: str
    depends_on: list[str] | None = None
    timeout: int = 600


def create_quick_tasks(task_descriptions: list[str]) -> list[OrchestratorTask]:
    """
    Create tasks from simple string descriptions

    Args:
        task_descriptions: List[Any] of task descriptions  # TODO(TYPE): replace Any with concrete type

    Returns: List[Any] of OrchestratorTask objects  # TODO(TYPE): replace Any with concrete type

    Example:
        tasks = create_quick_tasks([
            "Fix all test failures in test_auth_endpoints.py",
            "Fix all test failures in test_user_endpoints.py",
            "Fix all test failures in test_workflow_endpoints.py"
        ])
    """
    tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for i, desc in enumerate(task_descriptions, 1):
        task = OrchestratorTask(task_id=f"task_{i}", description=desc, timeout=600)
        tasks.append(task)
    return tasks


def create_dependency_chain(task_descriptions: list[str]) -> list[OrchestratorTask]:
    """
    Create tasks that must execute sequentially

    Args:
        task_descriptions: List[Any] of task descriptions in order  # TODO(TYPE): replace Any with concrete type

    Returns: List[Any] of OrchestratorTask objects with dependencies  # TODO(TYPE): replace Any with concrete type

    Example:
        tasks = create_dependency_chain([
            "Create core/types.py with all type definitions",
            "Update all imports to use core.types",
            "Run tests to verify all passing"
        ])
        # Task 2 depends on Task 1, Task 3 depends on Task 2
    """
    tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for i, desc in enumerate(task_descriptions, 1):
        dependencies = [f"task_{i-1}"] if i > 1 else []
        task = OrchestratorTask(
            task_id=f"task_{i}",
            description=desc,
            dependencies=dependencies,
            timeout=600,
        )
        tasks.append(task)
    return tasks


def create_complex_workflow(phases: dict[str, list[str]]) -> list[OrchestratorTask]:
    """
    Create complex workflow with multiple phases

    Args:
        phases: Dict[str, Any]ionary mapping phase names to task descriptions  # TODO(TYPE): replace Any with concrete type
               Tasks in same phase run in parallel
               Phases execute sequentially

    Returns: List[Any] of OrchestratorTask objects  # TODO(TYPE): replace Any with concrete type

    Example:
        workflow = create_complex_workflow({
            "schema": [
                "Design database schema",
                "Create alembic migration"
            ],
            "models": [
                "Implement User model",
                "Implement Role model",
                "Implement Permission model"
            ],
            "api": [
                "Implement auth API endpoints",
                "Implement RBAC API endpoints"
            ],
            "tests": [
                "Create comprehensive test suite"
            ]
        })
        # models phase waits for schema phase
        # api phase waits for models phase
        # tests phase waits for api phase
    """
    tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    phase_names = list(phases.keys())
    prev_phase_tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for phase_idx, phase_name in enumerate(phase_names):
        phase_task_ids: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for task_idx, desc in enumerate(phases[phase_name], 1):
            task_id = f"{phase_name}_{task_idx}"

            # Tasks in this phase depend on all tasks from previous phase
            dependencies = prev_phase_tasks if phase_idx > 0 else []

            task = OrchestratorTask(
                task_id=task_id,
                description=desc,
                dependencies=dependencies,
                timeout=900,  # 15 minutes for complex tasks
            )
            tasks.append(task)
            phase_task_ids.append(task_id)

        prev_phase_tasks = phase_task_ids

    return tasks


def format_results_summary(results: list[TaskResult]) -> str:
    """
    Format results into human-readable summary

    Args:
        results: List[Any] of task results  # TODO(TYPE): replace Any with concrete type

    Returns:
        Formatted summary string (ASCII-safe)
    """
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    lines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    lines.append("=" * 80)
    lines.append("ORCHESTRATOR RESULTS")
    lines.append("=" * 80)
    lines.append("")

    # Summary stats
    total_time = sum(r.execution_time for r in results)
    lines.append(f"Total Tasks: {len(results)}")
    lines.append(f"Successful: {len(successful)}")
    lines.append(f"Failed: {len(failed)}")
    lines.append(f"Total Time: {total_time:.2f}s")
    lines.append("")

    # Successful tasks
    if successful:
        lines.append("[OK] SUCCESSFUL TASKS:")
        for result in successful:
            lines.append(f"  - {result.task_id} ({result.execution_time:.2f}s)")
            if result.output:
                output_preview = (
                    result.output[:100] + "..." if len(result.output) > 100 else result.output
                )
                lines.append(f"    Output: {output_preview}")
        lines.append("")

    # Failed tasks
    if failed:
        lines.append("[FAIL] FAILED TASKS:")
        for result in failed:
            lines.append(f"  - {result.task_id} ({result.status.value})")
            if result.error:
                lines.append(f"    Error: {result.error}")
        lines.append("")

    lines.append("=" * 80)

    return "\n".join(lines)


def format_progress_update(orchestrator: CopilotOrchestrator) -> str:
    """
    Format current progress for display

    Args:
        orchestrator: Orchestrator instance

    Returns:
        Formatted progress string (ASCII-safe)
    """
    status = orchestrator.get_status()

    lines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    lines.append("[ORCHESTRATOR STATUS]")
    lines.append(f"  Total Tasks: {status['total_tasks']}")
    lines.append(f"  Completed: {status['completed']}")
    lines.append(f"  Failed: {status['failed']}")
    lines.append(f"  Active: {status['active']}")
    lines.append(f"  Pending: {status['pending']}")

    return "\n".join(lines)


def load_tasks_from_json(json_file: str) -> list[OrchestratorTask]:
    """
    Load tasks from JSON file

    Args:
        json_file: Path to JSON file

    Returns: List[Any] of OrchestratorTask objects  # TODO(TYPE): replace Any with concrete type

    JSON Format:
        {
            "tasks": [
                {
                    "task_id": "task1",
                    "description": "Task description",
                    "dependencies": [],
                    "timeout": 600,
                    "priority": 0
                }
            ]
        }
    """
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for task_data in data.get("tasks", []):
        task = OrchestratorTask(**task_data)
        tasks.append(task)

    return tasks


def save_results_to_json(results: list[TaskResult], output_file: str) -> None:
    """
    Save results to JSON file

    Args:
        results: List[Any] of task results  # TODO(TYPE): replace Any with concrete type
        output_file: Path to output JSON file
    """
    output_data = {
        "summary": {
            "total": len(results),
            "successful": len([r for r in results if r.success]),
            "failed": len([r for r in results if not r.success]),
            "total_time": sum(r.execution_time for r in results),
        },
        "results": [r.to_dict() for r in results],
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)


# Quick usage examples for documentation

USAGE_EXAMPLES = """
# Example 1: Parallel Test Fixing
from src.core.orchestrator.agent_helpers import create_quick_tasks, format_results_summary
from src.core.orchestrator.copilot_orchestrator import execute_tasks

tasks = create_quick_tasks([
    "Fix all test failures in test_auth_endpoints.py",
    "Fix all test failures in test_user_endpoints.py",
    "Fix all test failures in test_workflow_endpoints.py"
])

results = await execute_tasks(tasks, max_concurrent=3)
print(format_results_summary(results))


# Example 2: Sequential Workflow
from src.core.orchestrator.agent_helpers import create_dependency_chain

tasks = create_dependency_chain([
    "Create core/types.py with all type definitions",
    "Update all imports to use core.types",
    "Run full test suite and verify all passing"
])

results = await execute_tasks(tasks, max_concurrent=1)


# Example 3: Complex Multi-Phase Workflow
from src.core.orchestrator.agent_helpers import create_complex_workflow

workflow = create_complex_workflow({
    "setup": [
        "Create project structure",
        "Initialize configuration files"
    ],
    "implementation": [
        "Implement feature A",
        "Implement feature B",
        "Implement feature C"
    ],
    "validation": [
        "Run all tests",
        "Check code quality"
    ]
})

results = await execute_tasks(workflow, max_concurrent=4)


# Example 4: Load from JSON
from src.core.orchestrator.agent_helpers import load_tasks_from_json, save_results_to_json

tasks = load_tasks_from_json("tasks.json")
results = await execute_tasks(tasks)
save_results_to_json(results, "results.json")
"""
