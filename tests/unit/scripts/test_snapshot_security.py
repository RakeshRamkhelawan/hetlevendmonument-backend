import importlib.util
import os
import sys
from pathlib import Path

import pytest

# scripts/ is not a package (no __init__.py), so load it directly by file path.
_SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
_SPEC = importlib.util.spec_from_file_location(
    "snapshot_prod_mirror",
    _SCRIPTS_DIR / "snapshot_prod_mirror.py",
)
assert _SPEC is not None, "Could not locate snapshot_prod_mirror.py"
assert _SPEC.loader is not None, "Module spec has no loader"
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["snapshot_prod_mirror"] = _MOD

# `snapshot_prod_mirror.py` eist `DATABASE_URL` in zijn MODULEBODY en gooit anders een
# RuntimeError -- dat is een bewuste fail-fast in dat script en blijft zo. Gevolg voor deze
# test: hij kan het script alleen laden als die variabele gezet is.
#
# Tot 2026-09-18 leunde hij daarvoor op de omgeving. In de hoofdmap staat een (ongetrackte)
# `.env` die hem zet, dus daar was de test groen. In ELKE git worktree ontbreekt dat bestand,
# en in CI ook -- daar gaf dit vier ERRORS bij het verzamelen en stond de volledige testpoort
# dus altijd rood, zonder dat er iets mis was met de code die getoetst wordt. Gemeten
# 2026-09-18: 16657 passed, 0 failed, 4 errors, push geweigerd.
#
# Deze test heeft alleen `_validate_db_identifier` nodig, een pure functie die BOVEN die
# controle staat. Daarom een wegwerpwaarde puur om de module te kunnen laden, meteen weer
# teruggezet zodat geen andere test in dezelfde xdist-worker hem ziet.
_VORIGE_DATABASE_URL = os.environ.get("DATABASE_URL")
os.environ["DATABASE_URL"] = "postgresql://laadwaarde-voor-deze-test/niet-verbinden"
try:
    _SPEC.loader.exec_module(_MOD)  # type: ignore[union-attr]
finally:
    if _VORIGE_DATABASE_URL is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = _VORIGE_DATABASE_URL

_validate_db_identifier = _MOD._validate_db_identifier


@pytest.mark.unit
def test_valid_identifier_passes():
    assert _validate_db_identifier("sanskriti_prodmirror") == "sanskriti_prodmirror"
    assert _validate_db_identifier("test_db_1") == "test_db_1"


@pytest.mark.unit
def test_underscore_prefix_passes():
    assert _validate_db_identifier("_internal_db") == "_internal_db"


@pytest.mark.unit
def test_sql_injection_rejected():
    with pytest.raises(ValueError):
        _validate_db_identifier("db'; DROP TABLE users; --")


@pytest.mark.unit
def test_semicolon_rejected():
    with pytest.raises(ValueError):
        _validate_db_identifier("valid_db; DROP DATABASE postgres")


@pytest.mark.unit
def test_spaces_rejected():
    with pytest.raises(ValueError):
        _validate_db_identifier("my db")


@pytest.mark.unit
def test_empty_rejected():
    with pytest.raises(ValueError):
        _validate_db_identifier("")


@pytest.mark.unit
def test_hyphen_rejected():
    with pytest.raises(ValueError):
        _validate_db_identifier("my-database")


@pytest.mark.unit
def test_digit_prefix_rejected():
    with pytest.raises(ValueError):
        _validate_db_identifier("1bad_name")


@pytest.mark.unit
def test_too_long_rejected():
    # 64 characters exceeds PostgreSQL's 63-character identifier limit
    with pytest.raises(ValueError):
        _validate_db_identifier("a" * 64)


@pytest.mark.unit
def test_exactly_63_chars_passes():
    name = "a" * 63
    assert _validate_db_identifier(name) == name


@pytest.mark.unit
def test_newline_rejected():
    with pytest.raises(ValueError):
        _validate_db_identifier("db\nDROP DATABASE postgres")


@pytest.mark.unit
def test_dollar_sign_rejected():
    # Dollar signs are valid in some PG contexts but excluded here for safety
    with pytest.raises(ValueError):
        _validate_db_identifier("db$name")
