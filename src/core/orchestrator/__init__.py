"""
GitHub Copilot Multi-Agent Orchestrator
True multi-agent orchestration using runSubagent capability
"""

from .agent_helpers import (
    create_complex_workflow,
    format_progress_update,
    load_tasks_from_json,
    save_results_to_json,
)
from .copilot_orchestrator import (
    CopilotOrchestrator,
    OrchestratorTask,
    TaskResult,
    TaskStatus,
    create_dependency_chain,
    create_orchestrator,
    create_quick_tasks,
    execute_tasks,
    format_results_summary,
)
# `shell_orchestrator` is VERWIJDERD op 2026-09-07 (ADR-036 OP-127, GO van Rakesh).
#
# Wat er weg is: `src/core/orchestrator/shell_orchestrator.py` en zijn enige aanroeper
# `scripts/shell_orchestrator_cli.py`. Die module deed `create_subprocess_shell(task.command)`
# terwijl `ShellTask.__post_init__` alleen op leegheid toetste: geen allowlist, geen shlex, en
# het kindproces kreeg de volledige omgeving mee. De CLI bouwde die taken rechtstreeks uit een
# JSON-bestand.
#
# Waarom verwijderen en niet hardenen: gemeten oppervlak was nul. Niets in `src/` importeerde
# de module (deze regel importeerde hem tot 2026-09-04 wel, en zette twee namen in `__all__`,
# maar dat was al teruggedraaid), er was geen HTTP-route, geen agent-pad en geen enkele test.
# Geen CI-workflow, Makefile-doel of package.json-script riep de CLI aan; alleen
# `scripts/README.md` noemde hem in een opsomming. Rakesh heeft bevestigd hem niet te
# gebruiken. Hardenen zou code toevoegen aan iets dat niemand aanroept.

__all__ = [
    # Core orchestrator (NEW - correct implementation)
    "CopilotOrchestrator",
    "OrchestratorTask",
    "TaskResult",
    "TaskStatus",
    "create_orchestrator",
    "execute_tasks",
    # Helper functions (core ones in copilot_orchestrator.py)
    "create_quick_tasks",  # From copilot_orchestrator
    "create_dependency_chain",  # From copilot_orchestrator
    "format_results_summary",  # From copilot_orchestrator
    "create_complex_workflow",  # From agent_helpers
    "format_progress_update",  # From agent_helpers
    "load_tasks_from_json",  # From agent_helpers
    "save_results_to_json",  # From agent_helpers
]
