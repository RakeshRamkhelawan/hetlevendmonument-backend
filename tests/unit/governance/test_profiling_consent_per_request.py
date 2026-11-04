"""TDD: per-request profiling consent in process_task() -- SP-DLP-003 Dag 2 (GDPR-009)."""

import re
from pathlib import Path

_GUARD_PATTERN = re.compile(
    r"async def process_task.*?if self\._profiling_opted_out",
    re.DOTALL,
)


def test_process_task_gates_on_profiling_opted_out():
    """process_task() moet if self._profiling_opted_out checken -- GDPR-009."""
    src = Path("src/core/agents/base_agent.py").read_text(encoding="utf-8")
    assert len(_GUARD_PATTERN.findall(src)) >= 1, (
        "process_task() checkt _profiling_opted_out niet -- GDPR-009 per-request guard ontbreekt"
    )


def test_process_task_has_profiling_opt_out_db_check():
    """process_task() moet een DB-check doen voor profiling opt-out -- GDPR Art. 21."""
    src = Path("src/core/agents/base_agent.py").read_text(encoding="utf-8")
    assert "check_profiling_opt_out" in src or "UserProfilingOptOut" in src, (
        "process_task() heeft geen DB-check voor profiling opt-out"
    )
