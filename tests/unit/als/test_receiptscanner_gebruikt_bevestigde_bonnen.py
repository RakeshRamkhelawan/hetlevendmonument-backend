"""De receiptscanner in pakket mkb.zero_admin werkt met BEVESTIGDE bonnen (bonlezer dag 4).

Tot dag 4 faalde de stap met "agent not wired". Nu geeft hij een samenvatting van wat de medewerker
heeft bevestigd (aantal, totaalbedrag, btw per tarief), zonder taalmodel: bonnen die niet zijn bevestigd
tellen nooit mee, en een andere tenant ook niet. Geen bevestigde bonnen is geen fout maar aantal 0.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

TENANT = 3
ANDERE_TENANT = 4


def _bevestig(root: Path, tenant: int, naam: str, velden: dict[str, object]) -> None:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    record = {"velden": velden, "door": 1, "bevestigd_op": "2026-10-17T10:00:00+00:00"}
    (map_ / f"{naam * 32}.pdf.bevestigd.json").write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture(autouse=True)
def _upload_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))
    return tmp_path


def _skill(tenant: int = TENANT):  # noqa: ANN202
    from src.core.als.agents.skills.receiptscanner import ReceiptScannerSkill

    return ReceiptScannerSkill(tenant_id=tenant)


@pytest.mark.unit
def test_the_receiptscanner_is_wired_for_packs() -> None:
    from src.core.als.enterprise.packs import _PILOT_WIRED_AGENT_IDS

    assert "receiptscanner" in _PILOT_WIRED_AGENT_IDS


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_confirmed_bon_gives_a_successful_step(_upload_root: Path) -> None:
    _bevestig(_upload_root, TENANT, "a", {"totaal": "12.10", "btw": {"9": "0.50", "21": "1.60"}})

    resultaat = await _skill().execute_with_manifest_prompt({}, initiated_by_user_id=5)

    assert resultaat.success is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_summary_counts_the_confirmed_bonnen(_upload_root: Path) -> None:
    # Stap 1 telt sinds 2026-10-19 een KWARTAAL (zelfde als stap 2), dus de bonnen krijgen een datum erbij.
    _bevestig(
        _upload_root,
        TENANT,
        "a",
        {"datum": "2026-08-05", "totaal": "12.10", "btw": {"9": "0.50", "21": "1.60"}},
    )
    _bevestig(
        _upload_root, TENANT, "b", {"datum": "2026-09-01", "totaal": "10.00", "btw": {"21": "1.74"}}
    )

    resultaat = await _skill().execute_with_manifest_prompt({"input": {"kwartaal": "2026-Q3"}})

    assert resultaat.result_data == {
        "kwartaal": "2026-Q3",
        "aantal": 2,
        "totaal": "22.10",
        "btw": {"9": "0.50", "21": "3.34"},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_confirmed_bonnen_is_a_success_with_count_zero() -> None:
    resultaat = await _skill().execute_with_manifest_prompt({})

    assert (resultaat.success, (resultaat.result_data or {}).get("aantal")) == (True, 0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_bon_that_is_only_uploaded_does_not_count(_upload_root: Path) -> None:
    map_ = _upload_root / str(TENANT)
    map_.mkdir(parents=True)
    (map_ / f"{'c' * 32}.pdf.meta.json").write_text("{}", encoding="utf-8")

    resultaat = await _skill().execute_with_manifest_prompt({})

    assert (resultaat.result_data or {}).get("aantal") == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_another_tenants_bonnen_do_not_count(_upload_root: Path) -> None:
    _bevestig(_upload_root, ANDERE_TENANT, "d", {"totaal": "99.00"})

    resultaat = await _skill().execute_with_manifest_prompt({})

    assert (resultaat.result_data or {}).get("aantal") == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_result_carries_the_tenant_of_the_skill() -> None:
    resultaat = await _skill().execute_with_manifest_prompt({})

    assert resultaat.tenant_id == TENANT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_params_tenant_is_ignored(_upload_root: Path) -> None:
    """De tenant komt uit de skill (de sessie), nooit uit de parameters van de stap."""
    _bevestig(_upload_root, ANDERE_TENANT, "e", {"totaal": "99.00"})

    resultaat = await _skill().execute_with_manifest_prompt({"tenant_id": ANDERE_TENANT})

    assert (resultaat.result_data or {}).get("aantal") == 0
