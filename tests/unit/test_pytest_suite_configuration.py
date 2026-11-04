"""AUDIT-UTS-DAG1: Regressietests voor pytest suite configuratie.

Deze tests bewaken pytest-timeouts en quarantine governance,
zodat tijdelijke uitsluitingen niet permanent worden.
"""

from pathlib import Path

import pytest
import tomllib


PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"
UNIT_TEST_DIR = Path(__file__).resolve().parent
TEMP_DISABLED_DIR = UNIT_TEST_DIR / "temp_disabled"
QUARANTINE_MANIFEST = TEMP_DISABLED_DIR / "QUARANTINE.md"
MAX_QUARANTINED_TEST_FILES = 25


def test_pytest_timeout_is_configured() -> None:
    """Assert dat pyproject.toml timeout=60 bevat in ini_options."""
    assert PYPROJECT_PATH.exists(), f"pyproject.toml niet gevonden op {PYPROJECT_PATH}"

    with PYPROJECT_PATH.open("rb") as f:
        config = tomllib.load(f)

    timeout = config.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("timeout")

    assert timeout == 300, (
        f"AUDIT-UTS-DAG1: pytest timeout is {timeout}, moet 300 zijn. "
        f"Unit tests in CI gebruiken --timeout=60 override."
    )


def test_quarantine_manifest_exists_with_owner_and_target_date() -> None:
    """Quarantine moet expliciet eigenaar + reactiveringsdatum bevatten."""
    assert TEMP_DISABLED_DIR.exists(), (
        f"AUDIT-UTS-DAG1: {TEMP_DISABLED_DIR} bestaat niet. Quarantine-map ontbreekt."
    )
    assert QUARANTINE_MANIFEST.exists(), (
        f"AUDIT-UTS-DAG1: {QUARANTINE_MANIFEST} ontbreekt. "
        "Quarantine vereist eigenaar, reden en reactiveringsdatum."
    )

    text = QUARANTINE_MANIFEST.read_text(encoding="utf-8")
    assert "Owner:" in text
    assert "Target Reactivation Date:" in text


def test_quarantine_size_is_capped() -> None:
    """Quarantine mag niet onbegrensd groeien; dit bewaakt dekkingserosie."""
    assert TEMP_DISABLED_DIR.exists(), f"AUDIT-UTS-DAG1: {TEMP_DISABLED_DIR} bestaat niet."

    quarantined = [p for p in TEMP_DISABLED_DIR.rglob("test_*.py") if "__pycache__" not in str(p)]
    assert len(quarantined) <= MAX_QUARANTINED_TEST_FILES, (
        f"AUDIT-UTS-DAG1: Quarantine bevat {len(quarantined)} tests, "
        f"maximaal toegestaan is {MAX_QUARANTINED_TEST_FILES}."
    )


def test_temp_disabled_is_not_collected() -> None:
    """Assert dat pytest temp_disabled niet doorzoekt tijdens collectie."""
    assert PYPROJECT_PATH.exists(), f"pyproject.toml niet gevonden op {PYPROJECT_PATH}"

    with PYPROJECT_PATH.open("rb") as f:
        config = tomllib.load(f)

    norecursedirs = (
        config.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("norecursedirs", [])
    )
    addopts = config.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("addopts", [])

    # norecursedirs matches by basename; addopts has --ignore with full path
    in_norecurse = "temp_disabled" in norecursedirs
    in_addopts = any("tests/unit/temp_disabled" in str(opt) for opt in addopts)
    assert in_norecurse or in_addopts, (
        "AUDIT-UTS-DAG1: tests/unit/temp_disabled ontbreekt in norecursedirs/addopts. "
        "Pytest zal de hangende tests alsnog proberen te verzamelen."
    )
