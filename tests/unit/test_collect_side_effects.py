"""
Regression tests for pytest collection performance.

AUDIT-COLL-01: TESTING=1 must be set before any src.* import in conftest.py.
AUDIT-COLL-02: validate_config_at_startup() must not fire unconditionally at
               module import time in src/main.py.
AUDIT-COLL-03a: AgentModelMatcher.__init__ must skip expensive profile loading
                in test mode (lazy init via _ensure_initialized).
AUDIT-COLL-03b: focus_builder/agents.py must not load 291 ALS agents eagerly
                at module import time.
"""

import inspect

import pytest
from pathlib import Path


@pytest.mark.unit
def test_conftest_sets_testing_before_src_import():
    """TESTING=1 must appear before 'from src.main import' in conftest.py.

    RED before fix: TESTING is set on line 50, src.main import is on line 48.
    GREEN after fix: TESTING is moved to before the src.main import.
    """
    conftest_path = Path(__file__).parents[2] / "tests" / "conftest.py"
    source = conftest_path.read_text(encoding="utf-8")
    lines = source.splitlines()

    testing_set_line = None
    main_import_line = None

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if 'os.environ["TESTING"] = "1"' in stripped and not stripped.startswith("#"):
            if testing_set_line is None:
                testing_set_line = i
        if "from src.main import" in stripped and not stripped.startswith("#"):
            if main_import_line is None:
                main_import_line = i

    assert testing_set_line is not None, (
        'os.environ["TESTING"] = "1" not found in tests/conftest.py'
    )
    assert main_import_line is not None, "'from src.main import' not found in tests/conftest.py"
    assert testing_set_line < main_import_line, (
        f'AUDIT-COLL-01: os.environ["TESTING"]="1" is on line {testing_set_line} '
        f"but 'from src.main import' is on line {main_import_line}. "
        f"TESTING must be set BEFORE the src.main import to prevent module-level "
        f"side effects (validate_config_at_startup, configure_logging, singletons) "
        f"from firing during pytest --collect-only."
    )


@pytest.mark.unit
def test_validate_config_guarded_by_testing_check_in_main():
    """validate_config_at_startup() must be guarded by a TESTING check in src/main.py.

    RED before fix: main.py calls validate_config_at_startup() unconditionally at
                    module level — risks sys.exit(1) when required env vars are absent.
    GREEN after fix: the call is preceded by a guard checking TESTING or
                     PYTEST_CURRENT_TEST.
    """
    main_path = Path(__file__).parents[2] / "src" / "main.py"
    source = main_path.read_text(encoding="utf-8")
    lines = source.splitlines()

    call_line_num = None
    guard_found_before_call = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "validate_config_at_startup()" in stripped and not stripped.startswith("#"):
            call_line_num = i
            break

    assert call_line_num is not None, "validate_config_at_startup() call not found in src/main.py"

    # Scan backwards from the call to find a TESTING guard within 5 lines
    search_start = max(0, call_line_num - 6)
    for line in lines[search_start : call_line_num - 1]:
        if 'os.getenv("TESTING")' in line or "PYTEST_CURRENT_TEST" in line:
            guard_found_before_call = True
            break

    assert guard_found_before_call, (
        f"AUDIT-COLL-02: validate_config_at_startup() on line {call_line_num} of "
        f"src/main.py has no TESTING guard within the preceding 5 lines. "
        f'Add: if not (os.getenv("TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ): '
        f"to prevent sys.exit(1) during test collection when required env vars are absent."
    )


@pytest.mark.unit
def test_agent_model_matcher_init_has_testing_guard():
    """AgentModelMatcher.__init__ must not call _initialize_default_profiles() unconditionally.

    RED before fix: __init__ always calls _initialize_default_profiles() — logs
                    'Initialized 5 default agent profiles' during --collect-only.
    GREEN after fix: a TESTING guard skips the expensive call; _ensure_initialized()
                     defers it to first real use.
    """
    from src.core.llm.agent_model_matcher import AgentModelMatcher

    source = inspect.getsource(AgentModelMatcher.__init__)
    has_testing_guard = (
        'os.environ.get("TESTING")' in source
        or 'os.getenv("TESTING")' in source
        or "PYTEST_CURRENT_TEST" in source
    )
    assert has_testing_guard, (
        "AUDIT-COLL-03a: AgentModelMatcher.__init__ calls _initialize_default_profiles() "
        "unconditionally — fires expensive profile loading during pytest --collect-only. "
        "Add a TESTING guard and defer initialization to _ensure_initialized()."
    )


@pytest.mark.unit
def test_als_agents_not_eagerly_loaded_at_module_level():
    """_build_als_agents() must not be called at module level in focus_builder/agents.py.

    RED before fix: line 87 has '_ALS_AGENTS = _build_als_agents()' at module scope —
                    scans AGENT_REGISTRY (291 agents) during --collect-only.
    GREEN after fix: replaced by lazy getter _get_internal_agents().
    """
    agents_path = (
        Path(__file__).parents[2] / "src" / "core" / "api" / "v1" / "focus_builder" / "agents.py"
    )
    source = agents_path.read_text(encoding="utf-8")
    lines = source.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Module-level call: not inside a def/class (no leading whitespace) and calls _build_als_agents()
        if (
            "_build_als_agents()" in stripped
            and not line.startswith(" ")
            and not line.startswith("\t")
            and not stripped.startswith("def ")
            and not stripped.startswith("#")
        ):
            pytest.fail(
                f"AUDIT-COLL-03b: _build_als_agents() called at module level on line {i} "
                f"of focus_builder/agents.py — loads 291 ALS agents during "
                f"pytest --collect-only. Replace with lazy getter _get_internal_agents()."
            )


@pytest.mark.unit
def test_als_agents_not_eagerly_loaded_in_focus_builder_agents() -> None:
    """_build_als_agents() must not be called at module level in als/agents/focus_builder_agents.py.

    AUDIT-COLL-03c: mirror of AUDIT-COLL-03b for the new als-domain location (SP-API-009 Dag 3).
    """
    new_path = (
        Path(__file__).parents[2] / "src" / "core" / "als" / "agents" / "focus_builder_agents.py"
    )
    source = new_path.read_text(encoding="utf-8")
    lines = source.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if (
            "_build_als_agents()" in stripped
            and not line.startswith(" ")
            and not line.startswith("\t")
            and not stripped.startswith("def ")
            and not stripped.startswith("#")
        ):
            pytest.fail(
                f"AUDIT-COLL-03c: _build_als_agents() called at module level on line {i} "
                f"of als/agents/focus_builder_agents.py — loads ALS agents during "
                f"pytest --collect-only. Must remain lazy via _get_internal_agents()."
            )
