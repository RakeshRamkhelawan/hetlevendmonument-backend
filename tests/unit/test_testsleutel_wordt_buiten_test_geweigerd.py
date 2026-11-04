"""De vaste testsleutel wordt geweigerd buiten een testomgeving (brief 2026-10-24, bevinding c).

De testsleutel staat in `tests/conftest.py` en dus in de repo: iedereen kent hem. Een omgeving die hem
als `MASTER_ENCRYPTION_KEY` gebruikt versleutelt klantsleutels met een publiek bekende sleutel. Niets
verhinderde dat; de sleutel was ook niet als test herkenbaar. `TenantSecretEncryption` weigert nu PRECIES
deze waarde zodra `ENVIRONMENT` geen zachte omgeving is.

De lijst zachte omgevingen is dezelfde fail-closed lijst als bij de applicatierol-controle
(`ZACHTE_OMGEVINGEN` in `src/core/database/applicatierol_controle.py`): alleen development/dev/local/
test/testing zijn zacht; een onbekende of verkeerd gespelde naam (`prod`, `live`, een lege waarde) is streng.
Er is bewust GEEN import uit die module (security -> database zou een nieuwe laagrand zijn); een test hieronder
houdt de twee lijsten gelijk.

MUTATIEBEWIJS (2026-10-24):
    de weigering weghalen                                          -> `..._geweigerd_buiten_test` ROOD (alle omgevingen)
    de weigering ook in een zachte omgeving                         -> `..._geaccepteerd_in_een_testomgeving` ROOD
    de weigering voor elke sleutel                                  -> `..._andere_sleutel_blijft_geldig_in_productie` ROOD
    een lijst die afwijkt van ZACHTE_OMGEVINGEN                     -> `..._dezelfde_lijst_als_de_applicatierol` ROOD
    de constante in src aanpassen zonder conftest                   -> `..._constante_is_gelijk_aan_conftest` ROOD
"""

from __future__ import annotations

import ast
import base64
from pathlib import Path

import pytest

from src.core.security.tenant_secret_encryption import (
    BEKENDE_TESTSLEUTEL,
    HoofdsleutelIsTestsleutel,
    HoofdsleutelOntbreekt,
    TenantSecretEncryption,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ANDERE_GELDIGE_SLEUTEL = "Zk3Qm9Lp-Vt7Xw2Ab5Cd8Ef1Gh4Ij6Kn0Rs-UyYvNOE"


def _constanten_uit(pad: Path, naam: str) -> set[str]:
    boom = ast.parse(pad.read_text(encoding="utf-8"))
    for node in ast.walk(boom):
        waarde = None
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == naam for t in node.targets
        ):
            waarde = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == naam
        ):
            waarde = node.value
        if waarde is not None:
            return {
                e.value
                for e in ast.walk(waarde)
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
    raise AssertionError(f"{naam} niet gevonden in {pad}")


@pytest.mark.parametrize("omgeving", ["production", "staging", "prod", "live", "acceptatie", ""])
def test_de_testsleutel_wordt_geweigerd_buiten_test(
    monkeypatch: pytest.MonkeyPatch, omgeving: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", omgeving)

    with pytest.raises(HoofdsleutelIsTestsleutel):
        TenantSecretEncryption(master_key=BEKENDE_TESTSLEUTEL)


@pytest.mark.parametrize("omgeving", ["development", "dev", "local", "test", "testing", "TEST "])
def test_de_testsleutel_wordt_geaccepteerd_in_een_testomgeving(
    monkeypatch: pytest.MonkeyPatch, omgeving: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", omgeving)

    assert TenantSecretEncryption(master_key=BEKENDE_TESTSLEUTEL) is not None


def test_een_andere_sleutel_blijft_geldig_in_productie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    assert TenantSecretEncryption(master_key=ANDERE_GELDIGE_SLEUTEL) is not None


def test_de_testsleutel_uit_de_omgevingsvariabele_wordt_ook_geweigerd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", BEKENDE_TESTSLEUTEL)

    with pytest.raises(HoofdsleutelIsTestsleutel):
        TenantSecretEncryption()


def _varianten_van_de_testsleutel() -> dict[str, str]:
    """Dezelfde BYTES in andere vormen: extra opvulling, hex, en het standaard-base64-alfabet."""
    opvulling = "=" * (-len(BEKENDE_TESTSLEUTEL) % 4)
    ruw = base64.b64decode(BEKENDE_TESTSLEUTEL + opvulling, altchars=b"-_")
    return {
        "urlsafe-met-opvulling": BEKENDE_TESTSLEUTEL + (opvulling or "="),
        "hex": ruw.hex(),
        # Hex met hoofdletters wordt door `_ontcijfer_hoofdsleutel` eerst als base64 gelezen (48 bytes) en
        # zou zo langs de materiaalvergelijking glippen; de hex-lezing van dezelfde tekst is de testsleutel.
        "hex-hoofdletters": ruw.hex().upper(),
        "standaard-met-opvulling": base64.b64encode(ruw).decode("ascii"),
        "standaard-zonder-opvulling": base64.b64encode(ruw).decode("ascii").rstrip("="),
        "omringd-door-spaties": f"  {BEKENDE_TESTSLEUTEL}\n",
    }


@pytest.mark.parametrize("vorm", list(_varianten_van_de_testsleutel()))
def test_dezelfde_bytes_in_een_andere_vorm_worden_buiten_test_geweigerd(
    monkeypatch: pytest.MonkeyPatch, vorm: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(HoofdsleutelOntbreekt):
        TenantSecretEncryption(master_key=_varianten_van_de_testsleutel()[vorm])


@pytest.mark.parametrize("vorm", ["urlsafe-met-opvulling", "hex", "omringd-door-spaties"])
def test_een_andere_vorm_die_als_sleutel_werkt_is_in_een_testomgeving_toegestaan(
    monkeypatch: pytest.MonkeyPatch, vorm: str
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")

    assert TenantSecretEncryption(master_key=_varianten_van_de_testsleutel()[vorm]) is not None


def test_een_geheel_andere_sleutel_in_dezelfde_vorm_blijft_geldig_in_productie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    ander = base64.urlsafe_b64decode(ANDERE_GELDIGE_SLEUTEL + "=").hex()

    assert TenantSecretEncryption(master_key=ander) is not None


def test_de_weigering_valt_onder_hoofdsleutel_ontbreekt() -> None:
    """Elke aanroeper die `HoofdsleutelOntbreekt` al afvangt (de 503 in de router) pakt dit mee."""
    assert issubclass(HoofdsleutelIsTestsleutel, HoofdsleutelOntbreekt)


def test_de_constante_is_gelijk_aan_conftest() -> None:
    uit_conftest = _constanten_uit(REPO_ROOT / "tests/conftest.py", "_TEST_MASTER_ENCRYPTION_KEY")

    assert uit_conftest == {BEKENDE_TESTSLEUTEL}


def test_dezelfde_lijst_als_de_applicatierol() -> None:
    uit_src = _constanten_uit(
        REPO_ROOT / "src/core/security/tenant_secret_encryption.py", "_ZACHTE_OMGEVINGEN"
    )
    uit_rol = _constanten_uit(
        REPO_ROOT / "src/core/database/applicatierol_controle.py", "ZACHTE_OMGEVINGEN"
    )

    assert uit_src == uit_rol
