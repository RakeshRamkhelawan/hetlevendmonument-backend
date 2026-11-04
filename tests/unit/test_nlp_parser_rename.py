"""Verifies that nlp_parser module is importable under the new semantic name."""


def test_nlp_parser_importable_under_new_name():
    from src.core.agents.nlp_parser import EnhancedNLPParser, IntentType  # noqa: F401

    assert EnhancedNLPParser is not None
    assert IntentType is not None


def test_old_name_no_longer_exists():
    import importlib.util

    spec = importlib.util.find_spec("src.core.agents.enhanced_nlp_parser")
    assert spec is None, "enhanced_nlp_parser mag niet meer bestaan als apart module"
