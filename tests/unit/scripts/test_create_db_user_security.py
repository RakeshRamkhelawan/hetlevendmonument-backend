import importlib.util
import os
import sys
from pathlib import Path

import pytest

# scripts/ is not a package (no __init__.py), so load it directly by file path.
_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location(
    "create_db_user",
    _SCRIPTS_DIR / "create_db_user.py",
)
assert _SPEC is not None, "Could not locate create_db_user.py"
assert _SPEC.loader is not None, "Module spec has no loader"
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["create_db_user"] = _MOD
_SPEC.loader.exec_module(_MOD)  # type: ignore[union-attr]

_validate_identifier = _MOD._validate_identifier


@pytest.mark.unit
def test_valid_username_passes():
    assert _validate_identifier("sanskriti_user", "username") == "sanskriti_user"
    assert _validate_identifier("app_user_1", "username") == "app_user_1"


@pytest.mark.unit
def test_valid_database_name_passes():
    assert _validate_identifier("sanskriti_setu", "database name") == "sanskriti_setu"
    assert _validate_identifier("test_db", "database name") == "test_db"


@pytest.mark.unit
def test_underscore_prefix_passes():
    assert _validate_identifier("_internal_user", "username") == "_internal_user"


@pytest.mark.unit
def test_sql_injection_rejected():
    with pytest.raises(ValueError):
        _validate_identifier("user'; DROP TABLE users; --", "username")


@pytest.mark.unit
def test_semicolon_rejected():
    with pytest.raises(ValueError):
        _validate_identifier("valid_user; DROP DATABASE postgres", "username")


@pytest.mark.unit
def test_spaces_rejected():
    with pytest.raises(ValueError):
        _validate_identifier("my user", "username")


@pytest.mark.unit
def test_empty_rejected():
    with pytest.raises(ValueError):
        _validate_identifier("", "username")


@pytest.mark.unit
def test_hyphen_rejected():
    with pytest.raises(ValueError):
        _validate_identifier("my-user", "username")


@pytest.mark.unit
def test_digit_prefix_rejected():
    with pytest.raises(ValueError):
        _validate_identifier("1user", "username")


@pytest.mark.unit
def test_too_long_rejected():
    # 64 characters exceeds PostgreSQL's 63-character identifier limit
    with pytest.raises(ValueError):
        _validate_identifier("a" * 64, "username")


@pytest.mark.unit
def test_exactly_63_chars_passes():
    name = "a" * 63
    assert _validate_identifier(name, "username") == name


@pytest.mark.unit
def test_newline_rejected():
    with pytest.raises(ValueError):
        _validate_identifier("user\nDROP DATABASE postgres", "username")


@pytest.mark.unit
def test_dollar_sign_rejected():
    # Dollar signs are valid in some PG contexts but excluded here for safety
    with pytest.raises(ValueError):
        _validate_identifier("user$name", "username")


@pytest.mark.unit
def test_error_message_includes_label():
    """Verify error messages are clear about which field is invalid."""
    try:
        _validate_identifier("bad-username", "username")
        pytest.fail("Expected ValueError")
    except ValueError as e:
        assert "username" in str(e)
        assert "bad-username" in str(e)

    try:
        _validate_identifier("bad-database", "database name")
        pytest.fail("Expected ValueError")
    except ValueError as e:
        assert "database name" in str(e)
        assert "bad-database" in str(e)


@pytest.mark.unit
def test_importing_the_script_does_not_change_the_environment(tmp_path, monkeypatch):
    """Importing the script must not pull a .env file into os.environ.

    The script is copied next to a throw-away .env so the result does not depend
    on where the working directory lives or on a real .env above the repo.
    Mutation: removing the load_dotenv() call at module level makes this green.
    """
    probe_key = "CREATE_DB_USER_IMPORT_PROBE"
    # setenv then delenv so monkeypatch removes the key again if the import leaks it.
    monkeypatch.setenv(probe_key, "placeholder")
    monkeypatch.delenv(probe_key, raising=False)

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    copy = scripts_dir / "create_db_user.py"
    copy.write_text((_SCRIPTS_DIR / "create_db_user.py").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text(f"{probe_key}=gelekt\n", encoding="utf-8")

    before = dict(os.environ)
    spec = importlib.util.spec_from_file_location("create_db_user_env_probe", copy)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert dict(os.environ) == before
