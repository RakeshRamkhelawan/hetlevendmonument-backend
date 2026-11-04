"""Zero-Admin Bookkeeping afwerken: een kwartaal voor stap 1 en 2, en een eerlijke stap 3 (2026-10-19).

Het ECHTE pakket `mkb.zero_admin` uit de catalogus loopt door de echte skills (receiptscanner, vatcompliance, dunning);
vervangen zijn alleen de uploadmap (een tijdelijke map met bevestigde bonnen), de klok van stap 1 en 2, het taalmodel
van stap 3 (een scriptdubbel zonder TOOL_CALL) en het vastleggen van de run-meting van het pakket. De vorderingen komen uit de echte
Postgres op netwerkpoort 5455.

Wat dit vaststelt:

1. Met `kwartaal` 2026-Q3 in de invoer tellen stap 1 en stap 2 alleen de Q3-bonnen en noemen beide 2026-Q3.
2. Zonder kwartaal is het het VORIGE afgesloten kwartaal, voor beide stappen hetzelfde.
3. Stap 3 zonder openstaande vorderingen meldt dat (0 openstaand, 0 voorgesteld) en geen kale "Gelukt".
4. Stap 3 telt een openstaande vordering van deze tenant, en niet die van een betaalde.
5. Het antwoord voor het scherm draagt het kwartaal bij stap 1 en 2 en de tellingen bij stap 3.

Wat NIET gemeten is: het scherm (dat staat in de vitest-tests en de acceptatie), de pakketroute zelf (zie
`test_packs_execute_route.py`) en een echt taalmodel.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.core.als.agents.skills import receiptscanner as scanner_module
from src.core.als.agents.skills import vatcompliance as vat_module
from src.core.als.agents.skills.dunning import DunningSkill
from src.core.als.enterprise.packs import DomainPackOrchestrator
from src.core.api.v1.agentic.agentic_domain_router import _naar_antwoord
from tests.fixtures.llm_dubbel import als_async

TENANT = 1
ANDERE_TENANT = 2
NU = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def _bevestig(root: Path, tenant: int, teken: str, datum: str, btw: dict[str, str]) -> None:
    map_ = root / str(tenant)
    map_.mkdir(parents=True, exist_ok=True)
    velden = {
        "leverancier": "Bakkerij De Korenaar B.V.",
        "datum": datum,
        "totaal": "12.10",
        "factuurnummer": "F-1",
        "btw": btw,
        "btw_nummer": "NL123456789B01",
        "kvk_nummer": "12345678",
    }
    (map_ / f"{teken * 32}.pdf.bevestigd.json").write_text(
        json.dumps({"velden": velden, "door": 1, "bevestigd_op": "2026-10-17T10:00:00+00:00"}),
        encoding="utf-8",
    )


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("BONLEZER_UPLOAD_ROOT", str(tmp_path))
    monkeypatch.setattr(scanner_module, "_nu", lambda: NU)
    monkeypatch.setattr(vat_module, "_nu", lambda: NU)
    return tmp_path


async def _sql(statement: str, **params: Any) -> None:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        await session.execute(text(statement), params)
        await session.commit()


@pytest_asyncio.fixture
async def zonder_vorderingen() -> AsyncGenerator[None, None]:
    await _sql("DELETE FROM receivables WHERE tenant_id = :t", t=TENANT)
    yield


@pytest_asyncio.fixture
async def met_vorderingen() -> AsyncGenerator[list[int], None]:
    from src.core.database.database import db_manager
    from src.core.repositories.receivable_repository import NewReceivable, ReceivableRepository

    await _sql("DELETE FROM receivables WHERE tenant_id = :t", t=TENANT)
    ids: list[int] = []
    async with db_manager.get_session() as session:
        repo = ReceivableRepository(session)
        for nummer, status in (("F-2026-901", "open"), ("F-2026-902", "betaald")):
            rij = await repo.add(
                TENANT,
                NewReceivable(
                    customer_name="Bakkerij De Korst",
                    customer_email="administratie@dekorst.example",
                    invoice_number=nummer,
                    amount=Decimal("100.00"),
                    currency="EUR",
                    due_date=date(2026, 9, 1),
                ),
            )
            ids.append(rij.id)
            if status == "betaald":
                await session.execute(
                    text("UPDATE receivables SET status = 'betaald' WHERE id = :r"), {"r": rij.id}
                )
        await session.commit()
    yield ids
    for rid in ids:
        await _sql("DELETE FROM receivables WHERE id = :r", r=rid)


async def _draai(input_data: dict[str, object] | None) -> list[Any]:
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="Er is niets te doen.")
    with (
        patch.object(DunningSkill, "_get_llm_service", lambda self: als_async(llm)()),
        patch.object(DomainPackOrchestrator, "_leg_run_vast", AsyncMock()),
    ):
        return await DomainPackOrchestrator().run_pack_by_id(
            "mkb.zero_admin", TENANT, initiated_by_user_id=42, input_data=input_data
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeKwartaalkeuzeVoorStapEenEnTwee:
    async def test_with_q3_chosen_both_steps_count_only_q3_and_name_it(self, root: Path) -> None:
        _bevestig(root, TENANT, "a", "2026-08-05", {"9": "0.50", "21": "1.60"})
        _bevestig(root, TENANT, "b", "2026-09-30", {"21": "2.10"})
        _bevestig(root, TENANT, "c", "2026-10-05", {"21": "9.99"})

        resultaten = await _draai({"kwartaal": "2026-Q3"})

        een, twee = resultaten[0].result_data or {}, resultaten[1].result_data or {}
        assert (een["kwartaal"], een["aantal"], twee["kwartaal"], twee["aantal"]) == (
            "2026-Q3",
            2,
            "2026-Q3",
            2,
        )

    async def test_step_two_has_the_vat_of_the_chosen_quarter(self, root: Path) -> None:
        _bevestig(root, TENANT, "a", "2026-08-05", {"9": "0.50", "21": "1.60"})
        _bevestig(root, TENANT, "c", "2026-10-05", {"21": "9.99"})

        resultaten = await _draai({"kwartaal": "2026-Q3"})

        assert (resultaten[1].result_data or {})["voorbelasting"] == {
            "9": "0.50",
            "21": "1.60",
            "overig": "0.00",
        }

    async def test_without_a_quarter_both_steps_use_the_previous_closed_quarter(
        self, root: Path
    ) -> None:
        _bevestig(root, TENANT, "a", "2026-08-05", {"21": "1.60"})
        _bevestig(root, TENANT, "c", "2026-10-05", {"21": "9.99"})

        resultaten = await _draai(None)

        een, twee = resultaten[0].result_data or {}, resultaten[1].result_data or {}
        assert (een["kwartaal"], twee["kwartaal"], een["aantal"], twee["aantal"]) == (
            "2026-Q3",
            "2026-Q3",
            1,
            1,
        )

    async def test_free_text_does_not_change_the_quarter(self, root: Path) -> None:
        _bevestig(root, TENANT, "a", "2026-08-05", {"21": "1.60"})

        resultaten = await _draai({"invoer": "het eerste kwartaal van 2026"})

        assert (resultaten[1].result_data or {})["kwartaal"] == "2026-Q3"

    async def test_another_tenants_bonnen_do_not_count(self, root: Path) -> None:
        _bevestig(root, ANDERE_TENANT, "a", "2026-08-05", {"21": "50.00"})

        resultaten = await _draai({"kwartaal": "2026-Q3"})

        assert [(r.result_data or {})["aantal"] for r in resultaten[:2]] == [0, 0]


@pytest.mark.integration
@pytest.mark.asyncio
class TestStapDrieZegtWatHijDeed:
    async def test_without_open_receivables_the_step_says_zero_and_nothing_proposed(
        self, root: Path, zonder_vorderingen: None
    ) -> None:
        resultaten = await _draai({"kwartaal": "2026-Q3"})

        data = resultaten[2].result_data or {}
        assert (data["openstaand"], data["voorgesteld"]) == (0, 0)

    async def test_an_open_receivable_is_counted_and_a_paid_one_is_not(
        self, root: Path, met_vorderingen: list[int]
    ) -> None:
        resultaten = await _draai({"kwartaal": "2026-Q3"})

        assert (resultaten[2].result_data or {})["openstaand"] == 1

    async def test_the_answer_for_the_screen_has_the_quarter_and_the_counts(
        self, root: Path, zonder_vorderingen: None
    ) -> None:
        _bevestig(root, TENANT, "a", "2026-08-05", {"21": "1.60"})

        antwoord = _naar_antwoord(
            "mkb.zero_admin", await _draai({"kwartaal": "2026-Q3"}), sla_breached=False
        )

        samenvattingen = [stap.samenvatting for stap in antwoord.steps]
        assert [
            (samenvattingen[0] or {}).get("kwartaal"),
            (samenvattingen[1] or {}).get("kwartaal"),
            samenvattingen[2],
        ] == ["2026-Q3", "2026-Q3", {"openstaand": 0, "voorgesteld": 0}]
