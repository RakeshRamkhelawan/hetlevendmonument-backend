"""Verifies that subagents_manager module is importable under the new semantic name."""


def test_subagents_manager_importable_under_new_name():
    from src.core.agents.subagents_manager import PerfectSubagentsManager  # noqa: F401

    assert PerfectSubagentsManager is not None


def test_old_name_no_longer_exists():
    import importlib.util

    spec = importlib.util.find_spec("src.core.agents.perfect_subagents_manager")
    assert spec is None, "perfect_subagents_manager mag niet meer bestaan als apart module"
