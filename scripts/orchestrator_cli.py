#!/usr/bin/env python3
"""
CLI tool for Multi-Agent Orchestrator
Quick access to parallel agent execution
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

# Add src to path for imports
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

from core.orchestrator import OrchestratorTask, TaskResult, create_orchestrator
from core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


async def run_tasks_from_file(
    tasks_file: Path,
    max_concurrent: int = 4,
    fail_fast: bool = False,
    sequential: bool = False,
) -> List[TaskResult]:
    """
    Run tasks from JSON file

    Expected format:
    {
        "tasks": [
            {
                "task_id": "task1",
                "agent_name": "serena",
                "task_description": "Analyze test failures in test_auth.py",
                "priority": 10,
                "timeout": 120,
                "dependencies": [],
                "context": {}
            }
        ]
    }
    """
    # Load tasks
    with open(tasks_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    tasks = [OrchestratorTask(**task_data) for task_data in data.get("tasks", [])]

    if not tasks:
        print("[ERROR] No tasks found in file")
        return []

    print(f"[OK] Loaded {len(tasks)} tasks from {tasks_file}")

    # Create orchestrator (no MCP pool needed - uses runSubagent)
    orchestrator = create_orchestrator()
    orchestrator.add_tasks(tasks)

    # Execute
    if sequential:
        print("[RUN] Executing tasks sequentially...")
        results = await orchestrator.execute_sequential()
    else:
        print(f"[RUN] Executing tasks in parallel (max {max_concurrent} concurrent)...")
        results = await orchestrator.execute_parallel(
            max_concurrent=max_concurrent, fail_fast=fail_fast
        )

    return results


async def run_quick_tasks(
    tasks: List[str], agent_name: str = "serena", max_concurrent: int = 4
) -> List[TaskResult]:
    """
    Quick execution of simple task descriptions

    Args:
        tasks: List of task descriptions (strings)
        agent_name: Agent to use for all tasks
        max_concurrent: Max concurrent tasks
    """
    # Convert strings to OrchestratorTask objects
    agent_tasks = [
        OrchestratorTask(task_id=f"task_{i+1}", description=desc, timeout=180)
        for i, desc in enumerate(tasks)
    ]

    print(f"[OK] Created {len(agent_tasks)} tasks for agent '{agent_name}'")

    # Create orchestrator (no MCP pool needed - uses runSubagent)
    orchestrator = create_orchestrator()
    orchestrator.add_tasks(agent_tasks)

    # Execute in parallel
    print(f"[RUN] Executing {len(agent_tasks)} tasks in parallel...")
    results = await orchestrator.execute_parallel(max_concurrent=max_concurrent)

    return results


def print_results(results: List[TaskResult]) -> None:
    """Pretty print task results (ASCII-only for Windows PowerShell compatibility)"""
    print("\n" + "=" * 80)
    print("EXECUTION RESULTS")
    print("=" * 80 + "\n")

    for result in results:
        status_marker = "[OK]" if result.success else "[FAIL]"
        print(f"{status_marker} Task: {result.task_id}")
        print(f"   Status: {result.status.value}")
        print(f"   Time: {result.execution_time:.2f}s")

        if result.error:
            print(f"   Error: {result.error}")

        if result.output:
            output_str = str(result.output)
            if len(output_str) > 200:
                output_str = output_str[:200] + "..."
            print(f"   Output: {output_str}")

        print()

    # Summary
    successful = len([r for r in results if r.success])
    failed = len([r for r in results if not r.success])
    total_time = sum(r.execution_time for r in results)

    print("=" * 80)
    print(f"SUMMARY: {successful}/{len(results)} successful, {failed} failed")
    print(f"Total execution time: {total_time:.2f}s")
    print("=" * 80)


async def main():
    """Main CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Multi-Agent Orchestrator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run tasks from file
  python orchestrator_cli.py --file tasks.json

  # Run tasks in parallel
  python orchestrator_cli.py --file tasks.json --parallel --max-concurrent 8

  # Quick execution of simple tasks
  python orchestrator_cli.py --quick "Fix test_auth.py" "Fix test_user.py"

  # Sequential execution (for debugging)
  python orchestrator_cli.py --file tasks.json --sequential
        """,
    )

    parser.add_argument("--file", "-f", type=Path, help="JSON file with task definitions")

    parser.add_argument("--quick", "-q", nargs="+", help="Quick task descriptions (strings)")

    parser.add_argument(
        "--agent",
        "-a",
        default="serena",
        help="Agent name for quick tasks (default: serena)",
    )

    parser.add_argument(
        "--max-concurrent",
        "-c",
        type=int,
        default=4,
        help="Maximum concurrent tasks (default: 4)",
    )

    parser.add_argument(
        "--sequential",
        "-s",
        action="store_true",
        help="Execute tasks sequentially (for debugging)",
    )

    parser.add_argument("--fail-fast", action="store_true", help="Stop execution on first failure")

    parser.add_argument("--output", "-o", type=Path, help="Save results to JSON file")

    args = parser.parse_args()

    # Validate args
    if not args.file and not args.quick:
        parser.error("Either --file or --quick must be specified")

    try:
        # Execute tasks
        if args.file:
            results = await run_tasks_from_file(
                args.file,
                max_concurrent=args.max_concurrent,
                fail_fast=args.fail_fast,
                sequential=args.sequential,
            )
        else:
            results = await run_quick_tasks(
                args.quick, agent_name=args.agent, max_concurrent=args.max_concurrent
            )

        # Print results
        print_results(results)

        # Save to file if requested
        if args.output:
            output_data = {
                "results": [r.to_dict() for r in results],
                "summary": {
                    "total": len(results),
                    "successful": len([r for r in results if r.success]),
                    "failed": len([r for r in results if not r.success]),
                    "total_time": sum(r.execution_time for r in results),
                },
            }

            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2)

            print(f"\n[OK] Results saved to {args.output}")

        # Exit code based on results
        if any(not r.success for r in results):
            sys.exit(1)

    except Exception as e:
        print(f"\n[ERROR] Execution failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
