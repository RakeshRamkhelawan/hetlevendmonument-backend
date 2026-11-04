"""Stap 2 van pakket mkb.zero_admin (vatcompliance) gebruikt het btw-overzicht uit BEVESTIGDE bonnen (2026-10-19).

Tot nu faalde de stap met "agent not wired" (acceptatie dag 4: "BTW-aangifte voorbereiden: Mislukt"). Nu geeft hij het
btw-overzicht van een kwartaal: voorbelasting (rubriek 5b) per tarief, het aantal bonnen en het aantal dat gecontroleerd
moet worden. Geen taalmodel, geen indiening, geen advies. Het kwartaal is het `kwartaal` in de invoer van de stap
(`2026-Q3`, gekozen in het venster Uitvoeren) en anders het VORIGE afgesloten kwartaal (aangifte doe je achteraf);
vrije tekst in de invoer bepaalt het kwartaal nooit (besluit regie 2026-10-19, acceptatie btw-overzicht).
De tenant komt uit de skill, nooit uit de parameters.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.core.als.agents.skills import vatcompliance as vat_module

TENANT = 3
ANDERE_TENANT = 4
NU = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _bevestig(
    root: Path, tenant: int, teken: str, datum: str, btw: dict[str, str], **extra: object
) -> None:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    velden: dict[str, object] = {
        "leverancier": "Bakkerij",
        "datum": datum,
        "totaal": "12.10",
        "factuurnummer": "F-1",
        "btw": btw,
        "btw_nummer": "NL123456789B01",
        "kvk_nummer": "12345678",
    }
    velden.update(extra)
    (map_ / f"{teken * 32}.pdf.bevestigd.json").write_text(
        json.dumps({"velden": velden, "bevestigd_op": "2026-10-17T10:00:00+00:00"}),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _omgeving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))
    monkeypatch.setattr(vat_module, "_nu", lambda: NU)
    return tmp_path


def _skill(tenant: int = TENANT):  # noqa: ANN202
    return vat_module.VATComplianceSkill(tenant_id=tenant)


@pytest.mark.unit
def test_the_vatcompliance_is_wired_for_packs() -> None:
    from src.core.als.enterprise.packs import _PILOT_WIRED_AGENT_IDS

    assert "vatcompliance" in _PILOT_WIRED_AGENT_IDS


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_confirmed_bon_gives_a_successful_step(_omgeving: Path) -> None:
    _bevestig(_omgeving, TENANT, "a", "2026-08-05", {"21": "2.10"})

    resultaat = await _skill().execute_with_manifest_prompt({}, initiated_by_user_id=5)

    assert resultaat.success is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_overview_of_the_previous_closed_quarter_is_the_default(_omgeving: Path) -> None:
    _bevestig(_omgeving, TENANT, "a", "2026-08-05", {"9": "0.50", "21": "1.60"})
    _bevestig(_omgeving, TENANT, "b", "2026-10-05", {"21": "9.99"})

    resultaat = await _skill().execute_with_manifest_prompt({})

    data = resultaat.result_data or {}
    assert (data["kwartaal"], data["aantal"], data["voorbelasting"], data["totaal"]) == (
        "2026-Q3",
        1,
        {"9": "0.50", "21": "1.60", "overig": "0.00"},
        "2.10",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_quarter_in_the_input_is_used(_omgeving: Path) -> None:
    _bevestig(_omgeving, TENANT, "a", "2026-08-05", {"21": "9.99"})

    resultaat = await _skill().execute_with_manifest_prompt({"input": {"kwartaal": "2026-Q3"}})

    data = resultaat.result_data or {}
    assert (data["kwartaal"], data["totaal"]) == ("2026-Q3", "9.99")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_exact_quarter_as_free_text_does_not_decide_the_quarter(_omgeving: Path) -> None:
    _bevestig(_omgeving, TENANT, "a", "2026-05-05", {"21": "9.99"})

    resultaat = await _skill().execute_with_manifest_prompt({"input": {"invoer": " 2026-Q2 "}})

    assert (resultaat.result_data or {})["kwartaal"] == "2026-Q3"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_other_free_text_is_ignored(_omgeving: Path) -> None:
    resultaat = await _skill().execute_with_manifest_prompt(
        {"input": {"invoer": "lees mijn bonnen van vorig jaar"}}
    )

    assert (resultaat.success, (resultaat.result_data or {})["kwartaal"]) == (True, "2026-Q3")


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("kapot", ["2026-Q5", "morgen", "", 2026, None])
async def test_an_invalid_quarter_key_fails_in_dutch(kapot: object) -> None:
    resultaat = await _skill().execute_with_manifest_prompt({"input": {"kwartaal": kapot}})

    assert resultaat.success is False and "kwartaal" in (resultaat.error_message or "").lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_quarter_without_bonnen_is_a_success_with_zero() -> None:
    resultaat = await _skill().execute_with_manifest_prompt({})

    data = resultaat.result_data or {}
    assert (resultaat.success, data["aantal"], data["totaal"]) == (True, 0, "0.00")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_bon_that_is_only_uploaded_does_not_count(_omgeving: Path) -> None:
    map_ = _omgeving / str(TENANT)
    map_.mkdir()
    (map_ / f"{'c' * 32}.pdf.meta.json").write_text("{}", encoding="utf-8")
    (map_ / f"{'c' * 32}.pdf.resultaat.json").write_text(
        json.dumps({"status": "gelezen", "velden": {"datum": "2026-08-05", "btw": {"21": "5.00"}}}),
        encoding="utf-8",
    )

    resultaat = await _skill().execute_with_manifest_prompt({})

    assert (resultaat.result_data or {})["aantal"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_another_tenants_bonnen_do_not_count(_omgeving: Path) -> None:
    _bevestig(_omgeving, ANDERE_TENANT, "d", "2026-08-05", {"21": "99.00"})

    resultaat = await _skill().execute_with_manifest_prompt({})

    assert (resultaat.result_data or {})["aantal"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_params_tenant_is_ignored(_omgeving: Path) -> None:
    """De tenant komt uit de skill (de sessie), nooit uit de parameters van de stap."""
    _bevestig(_omgeving, ANDERE_TENANT, "e", "2026-08-05", {"21": "99.00"})

    resultaat = await _skill().execute_with_manifest_prompt(
        {"tenant_id": ANDERE_TENANT, "input": {"tenant_id": ANDERE_TENANT}}
    )

    assert (resultaat.result_data or {})["aantal"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_result_carries_the_tenant_of_the_skill() -> None:
    resultaat = await _skill().execute_with_manifest_prompt({})

    assert resultaat.tenant_id == TENANT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_result_names_the_rubric_and_has_no_names(_omgeving: Path) -> None:
    _bevestig(_omgeving, TENANT, "a", "2026-08-05", {"21": "2.10"}, leverancier="Geheime B.V.")

    resultaat = await _skill().execute_with_manifest_prompt({})

    data = resultaat.result_data or {}
    assert data["rubriek"] == "5b" and "Geheime" not in json.dumps(data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_count_of_bonnen_to_check_is_in_the_result(_omgeving: Path) -> None:
    _bevestig(_omgeving, TENANT, "a", "2026-08-05", {"21": "2.10"}, kvk_nummer=None)

    resultaat = await _skill().execute_with_manifest_prompt({})

    assert (resultaat.result_data or {})["aantal_controleren"] == 1
