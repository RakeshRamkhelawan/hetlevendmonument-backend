"""SP-WE-20: ProactiveScheduler app.state wiring regression guards."""

from pathlib import Path


def test_wire_proactive_extras_called_in_lifespan() -> None:
    """SP-WE-20: _wire_proactive_extras moet aangeroepen worden in app_lifespan.py."""
    source = Path("src/core/app_lifespan.py").read_text(encoding="utf-8")
    assert "_wire_proactive_extras" in source, (
        "SP-WE-20: ProactiveScheduler app.state dependencies niet gewired -- "
        "gehele proactive monitoring pipeline is uitgeschakeld."
    )


def test_init_proactive_scheduler_in_startup_steps() -> None:
    """SP-WE-20: _init_proactive_scheduler moet in de init_steps lijst staan."""
    source = Path("src/core/app_lifespan.py").read_text(encoding="utf-8")
    assert "_init_proactive_scheduler" in source, (
        "SP-WE-20: ProactiveScheduler niet opgestart in lifespan init_steps."
    )
