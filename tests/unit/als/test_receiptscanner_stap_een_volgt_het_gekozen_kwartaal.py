"""Stap 1 van mkb.zero_admin (receiptscanner) telt hetzelfde kwartaal als stap 2 (zero-admin afwerken, 2026-10-19).

Tot nu telde stap 1 ALLE bevestigde bonnen over alle kwartalen terwijl stap 2 een kwartaal toonde: naast elkaar zonder
uitleg (acceptatie btw-overzicht). Nu gebruiken beide stappen de kwartaalregel van `btw_overzicht` (het `kwartaal` in de
invoer, anders het vorige afgesloten kwartaal) en noemt de uitslag het kwartaal.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.core.als.agents.skills import receiptscanner as scanner_module
from src.core.als.agents.skills import vatcompliance as vat_module

TENANT = 3
NU = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _bevestig(root: Path, tenant: int, teken: str, datum: str, btw: dict[str, str]) -> None:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    velden = {
        "leverancier": "Bakkerij",
        "datum": datum,
        "totaal": "12.10",
        "factuurnummer": "F-1",
        "btw": btw,
        "btw_nummer": "NL123456789B01",
        "kvk_nummer": "12345678",
    }
    (map_ / f"{teken * 32}.pdf.bevestigd.json").write_text(
        json.dumps({"velden": velden, "bevestigd_op": "2026-10-17T10:00:00+00:00"}),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _omgeving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))
    monkeypatch.setattr(scanner_module, "_nu", lambda: NU, raising=False)
    monkeypatch.setattr(vat_module, "_nu", lambda: NU)
    return tmp_path


async def _stap_een(params: dict[str, object]) -> dict[str, object]:
    skill = scanner_module.ReceiptScannerSkill(tenant_id=TENANT)
    resultaat = await skill.execute_with_manifest_prompt(params)
    assert resultaat.success is True
    return resultaat.result_data or {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_step_one_counts_only_the_chosen_quarter(_omgeving: Path) -> None:
    _bevestig(_omgeving, TENANT, "a", "2026-08-05", {"21": "1.60"})
    _bevestig(_omgeving, TENANT, "b", "2026-10-05", {"21": "9.99"})

    data = await _stap_een({"input": {"kwartaal": "2026-Q3"}})

    assert (data["aantal"], data["btw"]) == (1, {"21": "1.60"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_step_one_names_the_quarter(_omgeving: Path) -> None:
    data = await _stap_een({"input": {"kwartaal": "2026-Q3"}})

    assert data["kwartaal"] == "2026-Q3"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_step_one_defaults_to_the_previous_closed_quarter(_omgeving: Path) -> None:
    _bevestig(_omgeving, TENANT, "a", "2026-08-05", {"21": "1.60"})
    _bevestig(_omgeving, TENANT, "b", "2026-10-05", {"21": "9.99"})

    data = await _stap_een({})

    assert (data["kwartaal"], data["aantal"]) == ("2026-Q3", 1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_step_one_and_step_two_name_the_same_quarter_and_count_the_same(
    _omgeving: Path,
) -> None:
    _bevestig(_omgeving, TENANT, "a", "2026-08-05", {"21": "1.60"})
    _bevestig(_omgeving, TENANT, "b", "2026-10-05", {"21": "9.99"})
    params: dict[str, object] = {"input": {"kwartaal": "2026-Q3"}}

    een = await _stap_een(params)
    twee = (
        await vat_module.VATComplianceSkill(tenant_id=TENANT).execute_with_manifest_prompt(params)
    ).result_data or {}

    assert (een["kwartaal"], een["aantal"]) == (twee["kwartaal"], twee["aantal"]) == ("2026-Q3", 1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_free_text_does_not_decide_the_quarter_of_step_one(_omgeving: Path) -> None:
    data = await _stap_een({"input": {"invoer": "2026-Q1"}})

    assert data["kwartaal"] == "2026-Q3"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_invalid_quarter_fails_step_one_in_dutch() -> None:
    skill = scanner_module.ReceiptScannerSkill(tenant_id=TENANT)

    resultaat = await skill.execute_with_manifest_prompt({"input": {"kwartaal": "2026-Q9"}})

    assert resultaat.success is False and "kwartaal" in (resultaat.error_message or "").lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_another_tenants_bonnen_do_not_count_in_step_one(_omgeving: Path) -> None:
    _bevestig(_omgeving, 4, "a", "2026-08-05", {"21": "50.00"})

    data = await _stap_een({"input": {"kwartaal": "2026-Q3"}})

    assert data["aantal"] == 0
