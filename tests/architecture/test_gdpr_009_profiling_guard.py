"""Architecture test -- SP-DLP-003 wiring obligation (GDPR-009).

This test is RED until SP-DLP-003 adds a per-request profiling guard inside
EnhancedBaseAgent.process_task() that consults _profiling_opted_out (or a real
ConsentRepository check) before calling _execute_task().

It must remain RED to enforce CI until SP-DLP-003 is delivered.
TODO(Rakesh): SP-DLP-003 -- per-request ConsentRepository.has_profiling_consent() in process_task
"""

from pathlib import Path


def test_gdpr_009_process_task_gates_on_profiling_flag() -> None:
    """TODO(SP-DLP-003): process_task() moet _profiling_opted_out checken voor _execute_task().

    SP-DLP-002 voegde het attribuut toe als stub.
    SP-DLP-003 MOET een echte per-request guard toevoegen in process_task().
    """
    src = Path("src/core/agents/base_agent.py").read_text(encoding="utf-8")
    assert "_profiling_opted_out" in src and "if self._profiling_opted_out" in src, (
        "SP-DLP-003 niet afgerond: process_task() checkt _profiling_opted_out niet -- "
        "GDPR-009 per-request profiling guard ontbreekt"
    )
