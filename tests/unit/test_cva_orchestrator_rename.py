"""Verifies that cva_orchestrator module is importable under the new semantic name."""


def test_cva_orchestrator_importable_under_new_name():
    from src.core.agents.cva_orchestrator import UltimateCVAAgent, create_ultimate_cva_agent  # noqa: F401

    assert UltimateCVAAgent is not None
    assert create_ultimate_cva_agent is not None


def test_old_module_name_no_longer_exists():
    import importlib.util

    spec = importlib.util.find_spec("src.core.agents.ultimate_cva_agent")
    assert spec is None, "ultimate_cva_agent mag niet meer bestaan als apart module"
