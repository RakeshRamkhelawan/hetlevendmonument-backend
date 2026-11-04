"""Een aanmaning op een geescaleerd dossier zet de status niet terug -- Keten B dag 3.

Dag-1-bevinding (`receivables_registry.py::_send`): de tool zet `herinnerd` buiten de
overgangsregel om, dus een goedgekeurde aanmaning op een `geescaleerd` dossier zou de factuur
terug naar `herinnerd` zetten -- en de opvolging zou hem na 14 dagen opnieuw escaleren. De
brief: "Die loopt weer door de goedkeuring (soort `aanmaning` bestaat al)" -- de aanmaning MOET
dus kunnen, en de status MOET `geescaleerd` blijven.

Beslistabel (status van de factuur x soort brief), alleen de combinaties die iets beslissen:

| status        | soort       | verwacht                                                   |
|---------------|-------------|------------------------------------------------------------|
| geescaleerd   | aanmaning   | brief klaar, status blijft `geescaleerd`                    |
| geescaleerd   | herinnering | status blijft `geescaleerd` (of de tool weigert: ook goed)  |
| open          | herinnering | status wordt `herinnerd`, `herinnerd_op` gezet (bestaand)   |
| herinnerd     | aanmaning   | (niet vastgelegd in de brief; hier niet getoetst)           |

De tests gebruiken de helpers van `test_receivables_registry.py` (echte SQLite-sessie, echte
registry; niets vervangen). `kind="aanmaning"` bestaat al in `REMINDER_KINDS`.

**Wat de opstelling uitzet, nagelopen.** Autouse in `tests/conftest.py`: TESTING=1, tenantfilter
(het EIGEN filter van de registry wordt gemeten), event loop, seed-snapshot. Geen conftest in
`tests/unit/tool_broker/` die de registry of het model raakt.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.database.import_all_models  # noqa: F401
from tests.unit.tool_broker.test_receivables_registry import (
    VERSTUREN,
    _berichten,
    _registry,
    _seed,
)


async def _brief(
    session: AsyncSession, tenant_id: int, receivable_id: int, kind: str
) -> dict[str, object]:
    voorbeeld = await _registry(session).preview_payment_reminder(tenant_id, receivable_id, kind)
    assert voorbeeld["success"] is True, voorbeeld
    params = voorbeeld["params"]
    assert isinstance(params, dict)
    return dict(params)


async def _zet_status(session: AsyncSession, receivable_id: int, status: str) -> None:
    from src.core.models.receivable_models import Receivable

    rij = await session.get(Receivable, receivable_id)
    assert rij is not None
    rij.status = status
    await session.commit()


async def _status(session: AsyncSession, receivable_id: int) -> str:
    from src.core.models.receivable_models import Receivable

    session.expire_all()
    rij = await session.get(Receivable, receivable_id)
    assert rij is not None
    return rij.status


@pytest.mark.unit
@pytest.mark.asyncio
class TestAanmaningOpEenGeescaleerdDossier:
    async def test_een_aanmaning_zet_een_geescaleerd_dossier_niet_terug_naar_herinnerd(
        self, db_session: AsyncSession
    ) -> None:
        rid = await _seed(db_session, 1, "a", "A-1")
        await _zet_status(db_session, rid, "geescaleerd")
        params = await _brief(db_session, 1, rid, "aanmaning")

        await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_dag3a"}, tenant_id=1
        )

        assert await _status(db_session, rid) == "geescaleerd"

    async def test_een_aanmaning_op_een_geescaleerd_dossier_wordt_wel_klaargezet(
        self, db_session: AsyncSession
    ) -> None:
        """Niet "weiger alles": de goedgekeurde aanmaning moet de deur uit kunnen."""
        rid = await _seed(db_session, 1, "a", "A-1")
        await _zet_status(db_session, rid, "geescaleerd")
        params = await _brief(db_session, 1, rid, "aanmaning")

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_dag3b"}, tenant_id=1
        )

        berichten = await _berichten(db_session)
        assert uit["success"] is True, uit
        assert [(b.kind, b.status, b.receivable_id) for b in berichten] == [
            ("aanmaning", "klaar", rid)
        ]

    async def test_een_herinnering_zet_een_geescaleerd_dossier_ook_niet_terug(
        self, db_session: AsyncSession
    ) -> None:
        """Dezelfde fout langs de andere soort brief; weigeren of klaarzetten zijn allebei goed."""
        rid = await _seed(db_session, 1, "a", "A-1")
        await _zet_status(db_session, rid, "geescaleerd")
        params = await _brief(db_session, 1, rid, "herinnering")

        await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_dag3c"}, tenant_id=1
        )

        assert await _status(db_session, rid) == "geescaleerd"

    async def test_een_herinnering_klaarzetten_op_een_open_dossier_laat_het_open(
        self, db_session: AsyncSession
    ) -> None:
        """Andere kant op: het klaarzetten slaagt. `herinnerd` volgt pas als de verzendlus de
        brief heeft verstuurd (wfb-dag1 stap 2, test_herinnerd_is_een_feit.py)."""
        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid, "herinnering")

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_dag3d"}, tenant_id=1
        )

        assert (uit["success"], await _status(db_session, rid)) == (True, "open")

    async def test_een_aanmaning_op_een_geescaleerd_dossier_van_een_andere_tenant_bestaat_niet(
        self, db_session: AsyncSession
    ) -> None:
        """Isolatie: tenant 2 kan de aanmaning van tenant 1 niet laten uitgaan of terugzetten."""
        rid = await _seed(db_session, 1, "a", "A-1")
        await _seed(db_session, 2, "b", "B-1")
        await _zet_status(db_session, rid, "geescaleerd")
        params = await _brief(db_session, 1, rid, "aanmaning")

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_dag3e"}, tenant_id=2
        )

        assert (uit["success"], await _status(db_session, rid), await _berichten(db_session)) == (
            False,
            "geescaleerd",
            [],
        )
