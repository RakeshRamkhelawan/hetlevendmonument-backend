"""Debiteuren nazorg (2026-10-22): vier ogen alleen via de eigen route, besloten goedkeuringen zichtbaar, geen dubbel voorstel.

Echte app-stack, echte Postgres op netwerkpoort 5455, het echte recht per rol uit het seedscript. Alleen CSRF is vervangen
(Redis-gebonden; de controle zelf heeft eigen tests).

Gemeten, beide richtingen:

1. `PUT /api/v1/tenants/{id}` kan vier ogen en de escalatietermijn NIET meer wijzigen (de beheerder zou vier ogen UIT kunnen
   zetten langs de eigen route met zijn controles en auditregel heen); een gewone instelling wel, en de taalmodelkeuze
   (die geen eigen route heeft) blijft door dezelfde route te wijzigen.
2. `GET /api/v1/tools/hitl/decided`: een goedkeurder ziet de BESLOTEN tickets van de EIGEN tenant voor de tools die hij mag
   beslissen, met wie besloot en wanneer; niet die van een andere tenant, niet de wachtende, niet die van een proces waar hij
   geen recht op heeft, en zonder invoer van de actie. Iemand zonder goedkeurrecht krijgt 403.
3. Een tweede voorstel voor een vordering met een openstaand voorstel wordt geweigerd met een Nederlandse melding; een
   verlopen, een besloten of een voorstel van een andere tenant blokkeert niet.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import AsyncGenerator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LIJST = "/api/v1/receivables"
TENANTS = "/api/v1/tenants/1"
DECIDED = "/api/v1/tools/hitl/decided"
ACTIE = "send_payment_reminder"
_SEED_PAD = Path(__file__).resolve().parents[2] / "scripts" / "seed_tweede_gebruiker.py"
# Alleen voor wegwerpgebruikers; als variabele, zodat geen letterlijke waarde achter een geheimnaam staat.
_TESTSLEUTEL = "nazorg-testsleutel"


def _seed() -> Any:
    spec = importlib.util.spec_from_file_location("_seed_nazorg", _SEED_PAD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _zet_overrides(app: Any, session: AsyncSession, user: Any | None) -> dict[Any, Any]:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.auth.dependencies import get_current_user as echte_user
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _geen_csrf() -> None:
        return None

    overrides: dict[Any, Any] = {get_db: _db, api_get_db: _db, validate_csrf_token: _geen_csrf}
    if user is not None:
        overrides[echte_user] = lambda: user
    app.dependency_overrides.update(overrides)
    return overrides


@pytest_asyncio.fixture
async def api(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """De gezaaide beheerder (gebruiker 1, tenant 1)."""
    from tests.integration.conftest import _build_test_token

    overrides = _zet_overrides(integration_app, postgres_session, None)
    token = _build_test_token(user_id=1, email="admin@integration.test", tenant_id=1)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=integration_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client
    finally:
        for dep in overrides:
            integration_app.dependency_overrides.pop(dep, None)


async def _client_met_rol(
    app: Any, session: AsyncSession, email: str, rol_naam: str
) -> AsyncGenerator[AsyncClient, None]:
    from tests.integration.conftest import _build_test_token

    from src.core.auth.auth_service import UserResponse

    user_id = await _seed().maak_tweede_gebruiker(
        session, tenant_id=1, email=email, password=_TESTSLEUTEL, rol_naam=rol_naam
    )
    gebruiker = UserResponse(id=user_id, email=email, tenant_id=1, roles=[rol_naam])
    overrides = _zet_overrides(app, session, gebruiker)
    token = _build_test_token(user_id=user_id, email=email, tenant_id=1)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


@pytest_asyncio.fixture
async def goedkeurder(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _client_met_rol(
        integration_app, postgres_session, "nazorg-goedkeurder@integration.test", "goedkeurder"
    ):
        yield client


@pytest_asyncio.fixture
async def medewerker(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    async for client in _client_met_rol(
        integration_app, postgres_session, "nazorg-medewerker@integration.test", "debiteuren"
    ):
        yield client


async def _settings(session: AsyncSession) -> dict[str, Any]:
    rij = (
        await session.execute(text("SELECT CAST(settings AS TEXT) FROM tenants WHERE id = 1"))
    ).scalar_one()
    return dict(json.loads(rij or "{}"))


async def _zet_settings(session: AsyncSession, **sleutels: object) -> None:
    await session.execute(
        text(
            "UPDATE tenants SET settings = CAST(CAST(COALESCE(CAST(settings AS TEXT), '{}') AS JSONB) "
            "|| CAST(:s AS JSONB) AS JSON) WHERE id = 1"
        ),
        {"s": json.dumps(sleutels)},
    )


# --- 1. De beheerde instellingen alleen via hun eigen route -------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantPutLaatBeheerdeInstellingenStaan:
    async def test_a_put_with_an_empty_four_eyes_list_leaves_four_eyes_on(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _zet_settings(postgres_session, four_eyes_actions=[ACTIE])

        antwoord = await api.put(TENANTS, json={"settings": {"four_eyes_actions": []}})

        assert (antwoord.status_code, (await _settings(postgres_session))["four_eyes_actions"]) == (
            200,
            [ACTIE],
        )

    async def test_a_put_cannot_change_the_escalation_term(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _zet_settings(postgres_session, escalatie_na_dagen=21)

        await api.put(TENANTS, json={"settings": {"escalatie_na_dagen": 3}})

        assert (await _settings(postgres_session))["escalatie_na_dagen"] == 21

    async def test_a_put_cannot_switch_on_four_eyes_that_was_never_set_either(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        # De sleutel hoort bij de eigen route: ook "aanzetten" loopt daarlangs, met controle en auditregel.
        await postgres_session.execute(
            text("UPDATE tenants SET settings = CAST('{}' AS JSON) WHERE id = 1")
        )

        await api.put(TENANTS, json={"settings": {"four_eyes_actions": [ACTIE]}})

        assert "four_eyes_actions" not in await _settings(postgres_session)

    async def test_an_ordinary_setting_is_still_changed(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        # Tegenproef: zonder deze is "elke settings-wijziging weigeren" een geldige oplossing.
        antwoord = await api.put(TENANTS, json={"settings": {"thema": "donker"}})

        assert (antwoord.status_code, (await _settings(postgres_session)).get("thema")) == (
            200,
            "donker",
        )

    async def test_the_language_model_choice_can_still_be_changed_through_the_tenant_route(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        antwoord = await api.put(TENANTS, json={"settings": {"llm_provider": "ollama"}})

        assert (antwoord.status_code, (await _settings(postgres_session)).get("llm_provider")) == (
            200,
            "ollama",
        )

    async def test_four_eyes_still_changes_through_its_own_route(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        antwoord = await api.put("/api/v1/tools/hitl/four-eyes", json={"actions": [ACTIE]})

        assert (antwoord.status_code, (await _settings(postgres_session))["four_eyes_actions"]) == (
            200,
            [ACTIE],
        )


# --- 2. Besloten tickets zichtbaar voor de goedkeurder ------------------------------------------------------


async def _ticket(
    session: AsyncSession,
    ref: str,
    *,
    tenant_id: int = 1,
    status: str = "approved",
    tool: str = ACTIE,
    besluiter: int | None = 1,
    notitie: str | None = None,
    receivable_id: int | None = None,
    verloopt: str = "clock_timestamp() + interval '1 day'",
) -> None:
    payload: dict[str, object] = {"_requested_by": "1", "_decision_id": ref}
    if receivable_id is not None:
        payload["receivable_id"] = receivable_id
    await session.execute(
        text(
            "INSERT INTO hitl_tickets (ticket_ref, tenant_id, status, tool_name, payload, risk_level, "
            "expires_at, resolved_at, resolved_by, resolution_note) VALUES (:r, :t, CAST(:s AS VARCHAR), :tool, "
            f"CAST(:p AS JSONB), 'high', {verloopt}, "
            "CASE WHEN CAST(:s AS VARCHAR) = 'pending' THEN NULL ELSE clock_timestamp() END, "
            "CASE WHEN CAST(:s AS VARCHAR) = 'pending' THEN NULL ELSE CAST(:b AS INTEGER) END, :n)"
        ),
        {
            "r": ref,
            "t": tenant_id,
            "s": status,
            "tool": tool,
            "p": json.dumps(payload),
            "b": besluiter,
            "n": notitie,
        },
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestBeslotenTickets:
    @staticmethod
    async def _refs(client: AsyncClient) -> list[str]:
        antwoord = await client.get(DECIDED)
        assert antwoord.status_code == 200, antwoord.text
        return [t["ticket_ref"] for t in antwoord.json()["data"]]

    async def test_an_approver_sees_the_decided_tickets_of_the_own_tenant(
        self, goedkeurder: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _ticket(postgres_session, "TOOL-N-OK", status="approved")
        await _ticket(postgres_session, "TOOL-N-NEE", status="rejected", notitie="klant belt terug")
        await _ticket(postgres_session, "TOOL-N-UIT", status="consumed")

        assert set(await self._refs(goedkeurder)) >= {"TOOL-N-OK", "TOOL-N-NEE", "TOOL-N-UIT"}

    async def test_a_ticket_of_another_tenant_is_not_shown(
        self, goedkeurder: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _ticket(postgres_session, "TOOL-N-ANDERE", tenant_id=2, status="approved")
        await _ticket(postgres_session, "TOOL-N-EIGEN", tenant_id=1, status="approved")

        refs = await self._refs(goedkeurder)

        assert ("TOOL-N-EIGEN" in refs, "TOOL-N-ANDERE" in refs) == (True, False)

    async def test_a_pending_ticket_is_not_shown_here(
        self, goedkeurder: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _ticket(postgres_session, "TOOL-N-WACHT", status="pending")

        assert "TOOL-N-WACHT" not in await self._refs(goedkeurder)

    async def test_a_ticket_of_a_process_the_approver_may_not_decide_is_not_shown(
        self, goedkeurder: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _ticket(postgres_session, "TOOL-N-HR", status="approved", tool="schedule_training")
        await _ticket(postgres_session, "TOOL-N-DEB", status="approved")

        refs = await self._refs(goedkeurder)

        assert ("TOOL-N-DEB" in refs, "TOOL-N-HR" in refs) == (True, False)

    async def test_the_answer_says_who_decided_and_the_note_of_the_person(
        self, goedkeurder: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _ticket(postgres_session, "TOOL-N-WIE", status="rejected", notitie="klant belt terug")

        antwoord = await goedkeurder.get(DECIDED)

        ticket = [t for t in antwoord.json()["data"] if t["ticket_ref"] == "TOOL-N-WIE"][0]
        assert (ticket["rejected_by"], ticket["rejection_reason"], bool(ticket["rejected_at"])) == (
            "admin@integration.test",
            "klant belt terug",
            True,
        )

    async def test_the_answer_carries_no_input_of_the_action(
        self, goedkeurder: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _ticket(postgres_session, "TOOL-N-LEEG", status="approved", receivable_id=12345)

        antwoord = await goedkeurder.get(DECIDED)

        ticket = [t for t in antwoord.json()["data"] if t["ticket_ref"] == "TOOL-N-LEEG"][0]
        assert (ticket["tool_input"], "12345" in antwoord.text) == ({}, False)

    async def test_the_newest_decision_comes_first(
        self, goedkeurder: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _ticket(postgres_session, "TOOL-N-EERST", status="approved")
        await _ticket(postgres_session, "TOOL-N-LAATST", status="approved")

        refs = await self._refs(goedkeurder)

        assert refs.index("TOOL-N-LAATST") < refs.index("TOOL-N-EERST")

    async def test_the_total_counts_only_what_the_approver_may_see(
        self, goedkeurder: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _ticket(postgres_session, "TOOL-N-T1", status="approved")
        await _ticket(postgres_session, "TOOL-N-T2", tenant_id=2, status="approved")
        await _ticket(postgres_session, "TOOL-N-T3", status="approved", tool="schedule_training")

        antwoord = (await goedkeurder.get(DECIDED)).json()

        assert antwoord["total"] == len(antwoord["data"])

    async def test_someone_without_an_approval_right_is_refused(
        self, medewerker: AsyncClient
    ) -> None:
        antwoord = await medewerker.get(DECIDED)

        assert antwoord.status_code == 403


# --- 3. Geen dubbel voorstel --------------------------------------------------------------------------------


def _vervang_voorsteller(monkeypatch: pytest.MonkeyPatch, oproepen: list[list[int]]) -> None:
    """De agent zelf is hier niet het onderwerp; wel wat de route doet voordat en nadat hij start."""

    async def _nep(**kwargs: Any) -> list[dict[str, object]]:
        ids = list(kwargs["receivable_ids"])
        oproepen.append(ids)
        return [
            {"receivable_id": i, "status": "wacht_op_goedkeuring", "ticket_ref": f"TOOL-NEP-{i}"}
            for i in ids
        ]

    monkeypatch.setattr(
        sys.modules["src.core.api.v1.receivables.router"], "start_reminder_proposals", _nep
    )


async def _factuur(api: AsyncClient, nummer: str) -> int:
    antwoord = await api.post(
        LIJST,
        json={
            "customer_name": "Klant B.V.",
            "customer_email": "klant@acceptatie.example",
            "invoice_number": nummer,
            "amount": "10.00",
            "currency": "EUR",
            "due_date": date(2026, 9, 1).isoformat(),
        },
    )
    assert antwoord.status_code == 201, antwoord.text
    return int(antwoord.json()["data"]["id"])


async def _stel_voor(api: AsyncClient, ids: list[int]) -> list[dict[str, Any]]:
    antwoord = await api.post(f"{LIJST}/reminder-proposals", json={"receivable_ids": ids})
    assert antwoord.status_code == 200, antwoord.text
    return list(antwoord.json()["data"])


@pytest.mark.integration
@pytest.mark.asyncio
class TestGeenDubbelVoorstel:
    async def test_a_second_proposal_for_the_same_receivable_is_refused(
        self, api: AsyncClient, postgres_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        oproepen: list[list[int]] = []
        _vervang_voorsteller(monkeypatch, oproepen)
        rij = await _factuur(api, "NZ-001")
        await _ticket(postgres_session, "TOOL-NZ-1", status="pending", receivable_id=rij)

        uitkomst = await _stel_voor(api, [rij])

        assert (uitkomst[0]["status"], oproepen) == ("niet_gelukt", [])

    async def test_the_refusal_is_in_dutch_and_points_to_the_approvals(
        self, api: AsyncClient, postgres_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _vervang_voorsteller(monkeypatch, [])
        rij = await _factuur(api, "NZ-002")
        await _ticket(postgres_session, "TOOL-NZ-2", status="pending", receivable_id=rij)

        uitkomst = await _stel_voor(api, [rij])

        reden = str(uitkomst[0]["reason"])
        assert "al een voorstel" in reden and "Goedkeuringen" in reden

    async def test_only_the_receivable_without_a_proposal_is_started(
        self, api: AsyncClient, postgres_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        oproepen: list[list[int]] = []
        _vervang_voorsteller(monkeypatch, oproepen)
        met, zonder = await _factuur(api, "NZ-003"), await _factuur(api, "NZ-004")
        await _ticket(postgres_session, "TOOL-NZ-3", status="pending", receivable_id=met)

        uitkomst = await _stel_voor(api, [met, zonder])

        assert (oproepen, [(u["receivable_id"], u["status"]) for u in uitkomst]) == (
            [[zonder]],
            [(met, "niet_gelukt"), (zonder, "wacht_op_goedkeuring")],
        )

    async def test_a_decided_proposal_does_not_block_a_new_one(
        self, api: AsyncClient, postgres_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        oproepen: list[list[int]] = []
        _vervang_voorsteller(monkeypatch, oproepen)
        rij = await _factuur(api, "NZ-005")
        await _ticket(postgres_session, "TOOL-NZ-5", status="consumed", receivable_id=rij)

        await _stel_voor(api, [rij])

        assert oproepen == [[rij]]

    async def test_an_expired_proposal_does_not_block_a_new_one(
        self, api: AsyncClient, postgres_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        oproepen: list[list[int]] = []
        _vervang_voorsteller(monkeypatch, oproepen)
        rij = await _factuur(api, "NZ-006")
        await _ticket(
            postgres_session,
            "TOOL-NZ-6",
            status="pending",
            receivable_id=rij,
            verloopt="clock_timestamp() - interval '1 hour'",
        )

        await _stel_voor(api, [rij])

        assert oproepen == [[rij]]

    async def test_a_proposal_of_another_tenant_does_not_block(
        self, api: AsyncClient, postgres_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        oproepen: list[list[int]] = []
        _vervang_voorsteller(monkeypatch, oproepen)
        rij = await _factuur(api, "NZ-007")
        await _ticket(
            postgres_session, "TOOL-NZ-7", tenant_id=2, status="pending", receivable_id=rij
        )

        await _stel_voor(api, [rij])

        assert oproepen == [[rij]]

    async def test_a_pending_ticket_of_another_tool_does_not_block(
        self, api: AsyncClient, postgres_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        oproepen: list[list[int]] = []
        _vervang_voorsteller(monkeypatch, oproepen)
        rij = await _factuur(api, "NZ-008")
        await _ticket(
            postgres_session,
            "TOOL-NZ-8",
            status="pending",
            tool="schedule_training",
            receivable_id=rij,
        )

        await _stel_voor(api, [rij])

        assert oproepen == [[rij]]

    async def test_the_same_id_twice_in_one_request_is_started_once(
        self, api: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        oproepen: list[list[int]] = []
        _vervang_voorsteller(monkeypatch, oproepen)
        rij = await _factuur(api, "NZ-009")

        await _stel_voor(api, [rij, rij])

        assert oproepen == [[rij]]
