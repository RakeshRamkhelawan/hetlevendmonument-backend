"""Debiteuren vanzelf afronden, op de echte stack (2026-10-20, brief debiteuren-vanzelf-afronden).

Echte app-stack, echte Postgres op netwerkpoort 5455, het echte recht `receivables:write` op het JWT. Alleen CSRF is
vervangen (Redis-gebonden; de controle zelf heeft eigen tests). Het afschrift is het verzonnen voorbeeld uit
`tests/fixtures/bankafschrift/`.

Gemeten, beide richtingen:

1. Upload: precies de facturen met gelijk bedrag en los factuurnummer gaan op betaald, met de datum uit het afschrift
   en een auditregel; een tweede keer hetzelfde bestand vinkt niets af en geeft geen tweede auditregel.
2. Tenantgrens: een factuur van tenant 2 met hetzelfde nummer en bedrag wordt NIET afgevinkt, en de eigen factuur wel.
3. Veiligheid: een bestand met een DOCTYPE, een verkeerd inhoudstype en een te groot bestand worden geweigerd en
   vinken niets af.
4. Niets bewaren: geen enkele auditregel bevat tekst uit de omschrijving van het afschrift.
5. Een klaarstaande brief van een afgevinkte factuur gaat niet meer weg.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

URL = "/api/v1/receivables/bankafschrift"
LIJST = "/api/v1/receivables"
VOORBEELD = (
    Path(__file__).resolve().parents[1] / "fixtures" / "bankafschrift" / "camt053_voorbeeld.xml"
)
XML = {"Content-Type": "application/xml"}

# 1, 2 en 6 horen afgevinkt te worden (zie het voorbeeldafschrift); 3 heeft een afwijkend bedrag op het afschrift.
_FACTUREN = [
    ("F-2026-001", "121.00"),
    ("F-2026-002", "250.00"),
    ("F-2026-003", "100.00"),
    ("F-2026-006", "60.00"),
]

_TELLING_AUDIT = (
    "SELECT COUNT(*) FROM audit_logs "
    "WHERE event_type = 'receivable_paid_via_bankstatement' AND tenant_id = 1"
)


@pytest_asyncio.fixture
async def api(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    async def _geen_csrf() -> None:
        return None

    overrides = {get_db: _db, api_get_db: _db, validate_csrf_token: _geen_csrf}
    integration_app.dependency_overrides.update(overrides)
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


async def _voer_in(api: AsyncClient, nummer: str, bedrag: str) -> int:
    antwoord = await api.post(
        LIJST,
        json={
            "customer_name": "Bakkerij De Korst",
            "customer_email": "administratie@dekorst.example",
            "invoice_number": nummer,
            "amount": bedrag,
            "currency": "EUR",
            "due_date": "2026-09-01",
        },
    )
    assert antwoord.status_code == 201, antwoord.text
    return int(antwoord.json()["data"]["id"])


async def _zaai(api: AsyncClient) -> dict[str, int]:
    return {nummer: await _voer_in(api, nummer, bedrag) for nummer, bedrag in _FACTUREN}


async def _status(api: AsyncClient) -> dict[str, dict[str, Any]]:
    rijen = (await api.get(LIJST, params={"limit": 1000})).json()["data"]
    return {r["invoice_number"]: r for r in rijen}


async def _rij_van_tenant_2(session: AsyncSession) -> int:
    from src.core.models.receivable_models import Receivable

    rij = Receivable(
        tenant_id=2,
        customer_name="Ander Bedrijf",
        customer_email="geheim@ander.example",
        invoice_number="F-2026-001",
        amount=Decimal("121.00"),
        currency="EUR",
        due_date=date(2026, 9, 1),
        status="open",
        source="handmatig",
    )
    session.add(rij)
    await session.flush()
    return rij.id


@pytest.mark.integration
@pytest.mark.asyncio
class TestAfvinken:
    async def test_the_matching_receivables_are_paid_with_the_date_of_the_statement(
        self, api: AsyncClient
    ) -> None:
        await _zaai(api)

        antwoord = await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)

        assert antwoord.status_code == 200, antwoord.text
        rijen = await _status(api)
        assert {n: (r["status"], (r["betaald_op"] or "")[:10]) for n, r in rijen.items()} == {
            "F-2026-001": ("betaald", "2026-10-05"),
            "F-2026-002": ("betaald", "2026-10-06"),
            "F-2026-003": ("open", ""),
            "F-2026-006": ("betaald", "2026-10-11"),
        }

    async def test_the_answer_counts_what_was_and_was_not_matched(self, api: AsyncClient) -> None:
        await _zaai(api)

        data = (await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)).json()["data"]

        assert (len(data["afgevinkt"]), data["al_afgevinkt"], len(data["niet_gekoppeld"])) == (
            3,
            1,
            3,
        )

    async def test_a_second_upload_of_the_same_file_ticks_nothing_off(
        self, api: AsyncClient
    ) -> None:
        await _zaai(api)
        await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)

        data = (await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)).json()["data"]

        assert (data["afgevinkt"], data["al_afgevinkt"]) == ([], 4)

    async def test_an_audit_line_is_written_per_ticked_off_receivable(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _zaai(api)
        await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)

        aantal = (await postgres_session.execute(text(_TELLING_AUDIT))).scalar_one()

        assert aantal == 3

    async def test_a_second_upload_writes_no_second_audit_line(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _zaai(api)
        await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)
        await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)

        aantal = (await postgres_session.execute(text(_TELLING_AUDIT))).scalar_one()

        assert aantal == 3

    async def test_nothing_of_the_statement_text_is_in_the_audit_log(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await _zaai(api)
        await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)

        alles = (
            "COALESCE(CAST(event_metadata AS TEXT), '') || COALESCE(CAST(details AS TEXT), '') "
            "|| description"
        )
        aantal = (
            await postgres_session.execute(
                text(
                    "SELECT COUNT(*) FROM audit_logs WHERE tenant_id = 1 AND "
                    f"({alles} LIKE '%Voorbeeld Debiteur%' OR {alles} LIKE '%met dank%' "
                    f"OR {alles} LIKE '%NL00VOOR%')"
                )
            )
        ).scalar_one()

        assert aantal == 0

    async def test_a_letter_that_was_ready_does_not_go_after_ticking_off(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        ids = await _zaai(api)
        await postgres_session.execute(
            text(
                "INSERT INTO outgoing_messages (tenant_id, receivable_id, channel, kind, status, "
                "pogingen, recipient, subject, body, created_at) "
                "VALUES (1, :rid, 'email', 'herinnering', 'klaar', 0, 'x@example.test', "
                "'onderwerp', 'tekst', now())"
            ),
            {"rid": ids["F-2026-001"]},
        )

        await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)

        status = (
            await postgres_session.execute(
                text("SELECT status FROM outgoing_messages WHERE receivable_id = :rid"),
                {"rid": ids["F-2026-001"]},
            )
        ).scalar_one()
        assert status == "mislukt"


@pytest.mark.integration
@pytest.mark.asyncio
class TestTenantgrens:
    async def test_another_tenants_receivable_with_the_same_number_is_not_ticked_off(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        andere = await _rij_van_tenant_2(postgres_session)
        await _zaai(api)

        await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)

        status = (
            await postgres_session.execute(
                text("SELECT status FROM receivables WHERE id = :i"), {"i": andere}
            )
        ).scalar_one()
        # Beide helften: de vreemde factuur blijft open EN de eigen factuur met hetzelfde nummer is afgevinkt. Zonder
        # tenantfilter bij het ophalen ziet de koppelregel twee kandidaten en vinkt niets af.
        assert (status, (await _status(api))["F-2026-001"]["status"]) == ("open", "betaald")

    async def test_the_own_receivable_with_that_number_is_ticked_off(
        self, api: AsyncClient
    ) -> None:
        # Tweede helft van de tenantgrens: zonder deze is "nooit iets afvinken" een geldige oplossing.
        await _zaai(api)

        await api.post(URL, content=VOORBEELD.read_bytes(), headers=XML)

        assert (await _status(api))["F-2026-001"]["status"] == "betaald"


@pytest.mark.integration
@pytest.mark.asyncio
class TestWeigeren:
    async def test_a_file_with_a_doctype_is_refused_and_ticks_nothing_off(
        self, api: AsyncClient
    ) -> None:
        await _zaai(api)
        kwaad = VOORBEELD.read_bytes().replace(
            b"<Document", b'<!DOCTYPE d [<!ENTITY x "y">]><Document', 1
        )

        antwoord = await api.post(URL, content=kwaad, headers=XML)

        assert (antwoord.status_code, {r["status"] for r in (await _status(api)).values()}) == (
            422,
            {"open"},
        )

    async def test_the_refusal_is_in_dutch(self, api: AsyncClient) -> None:
        antwoord = await api.post(URL, content=b"geen xml", headers=XML)

        assert "afschrift" in antwoord.json()["detail"].lower()

    async def test_another_content_type_is_refused(self, api: AsyncClient) -> None:
        antwoord = await api.post(
            URL, content=VOORBEELD.read_bytes(), headers={"Content-Type": "application/json"}
        )

        assert antwoord.status_code == 415

    async def test_a_file_that_is_too_large_is_refused(self, api: AsyncClient) -> None:
        antwoord = await api.post(URL, content=b"<a>" + b"x" * (5 * 1024 * 1024), headers=XML)

        assert antwoord.status_code == 413


# --- De escalatietermijn per klant (B3) -----------------------------------------------------------------

SETTINGS = "/api/v1/receivables/settings"
_SEED_PAD = Path(__file__).resolve().parents[2] / "scripts" / "seed_tweede_gebruiker.py"
# Alleen voor een wegwerpgebruiker; als variabele, zodat geen letterlijke waarde achter een geheimnaam staat.
_TESTSLEUTEL = "vreemde-testsleutel"


def _seed() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_seed_tweede_gebruiker_afronden", _SEED_PAD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest_asyncio.fixture
async def debiteurenmedewerker(
    integration_app: Any, postgres_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """De rol `debiteuren`: mag lezen en schrijven op debiteuren, is GEEN beheerder."""
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    email = "debiteuren-afronden@integration.test"
    user_id = await _seed().maak_tweede_gebruiker(
        postgres_session,
        tenant_id=1,
        email=email,
        password="debiteuren-wachtwoord",
        rol_naam="debiteuren",
    )

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    async def _geen_csrf() -> None:
        return None

    gebruiker = UserResponse(id=user_id, email=email, tenant_id=1, roles=["debiteuren"])
    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        validate_csrf_token: _geen_csrf,
        get_current_user: lambda: gebruiker,
    }
    integration_app.dependency_overrides.update(overrides)
    token = _build_test_token(user_id=user_id, email=email, tenant_id=1)
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


@pytest.mark.integration
@pytest.mark.asyncio
class TestEscalatietermijn:
    async def test_the_default_is_fourteen_days(self, api: AsyncClient) -> None:
        antwoord = await api.get(SETTINGS)

        assert antwoord.json()["data"] == {"escalatie_na_dagen": 14}

    async def test_the_administrator_sets_the_term_and_it_is_read_back(
        self, api: AsyncClient
    ) -> None:
        zet = await api.put(SETTINGS, json={"escalatie_na_dagen": 30})

        assert (zet.status_code, (await api.get(SETTINGS)).json()["data"]) == (
            200,
            {"escalatie_na_dagen": 30},
        )

    @pytest.mark.parametrize("waarde", [0, 121, -5])
    async def test_a_term_outside_the_range_is_refused_in_dutch(
        self, api: AsyncClient, waarde: int
    ) -> None:
        antwoord = await api.put(SETTINGS, json={"escalatie_na_dagen": waarde})

        assert (antwoord.status_code, "dagen" in antwoord.json()["detail"]) == (422, True)

    async def test_a_tenant_id_in_the_body_is_refused(self, api: AsyncClient) -> None:
        antwoord = await api.put(SETTINGS, json={"escalatie_na_dagen": 20, "tenant_id": 2})

        assert antwoord.status_code == 422

    async def test_a_change_leaves_an_audit_line_with_old_and_new(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await api.put(SETTINGS, json={"escalatie_na_dagen": 21})

        rij = (
            await postgres_session.execute(
                text(
                    "SELECT CAST(event_metadata AS TEXT) FROM audit_logs "
                    "WHERE event_type = 'receivable_escalation_term_changed' AND tenant_id = 1 "
                    "ORDER BY id DESC LIMIT 1"
                )
            )
        ).scalar_one()

        assert ("14" in rij, "21" in rij) == (True, True)

    async def test_a_non_administrator_cannot_change_the_term(
        self, debiteurenmedewerker: AsyncClient
    ) -> None:
        antwoord = await debiteurenmedewerker.put(SETTINGS, json={"escalatie_na_dagen": 5})

        assert (antwoord.status_code, antwoord.json()["detail"]) == (
            403,
            "Alleen een beheerder mag de escalatietermijn wijzigen.",
        )

    async def test_a_non_administrator_can_read_the_term(
        self, debiteurenmedewerker: AsyncClient
    ) -> None:
        antwoord = await debiteurenmedewerker.get(SETTINGS)

        assert antwoord.status_code == 200


# --- Het overzicht per factuur en de auditregel van het voorstel (B4) --------------------------------------


def _vervang_voorsteller(monkeypatch: pytest.MonkeyPatch, uitkomsten: list[dict[str, object]]) -> None:
    """De agent zelf is hier niet het onderwerp (die heeft eigen tests); wel wat de route met zijn uitkomst doet."""

    async def _nep(**_kwargs: object) -> list[dict[str, object]]:
        return uitkomsten

    # `sys.modules`, niet het puntpad: het pakket `receivables` heeft zelf een attribuut `router` (de APIRouter) dat de
    # submodule met dezelfde naam verbergt.
    import sys

    monkeypatch.setattr(
        sys.modules["src.core.api.v1.receivables.router"], "start_reminder_proposals", _nep
    )


async def _tijdlijn(api: AsyncClient, rij_id: int) -> list[dict[str, Any]]:
    antwoord = await api.get(f"{LIJST}/{rij_id}/tijdlijn")
    assert antwoord.status_code == 200, antwoord.text
    return list(antwoord.json()["data"])


@pytest.mark.integration
@pytest.mark.asyncio
class TestVoorstelAudit:
    async def test_a_proposal_leaves_an_audit_line_per_invoice_that_waits(
        self,
        api: AsyncClient,
        postgres_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ids = await _zaai(api)
        eerste, tweede = ids["F-2026-001"], ids["F-2026-002"]
        _vervang_voorsteller(
            monkeypatch,
            [
                {"receivable_id": eerste, "status": "wacht_op_goedkeuring", "ticket_ref": "TOOL-A1"},
                {"receivable_id": tweede, "status": "niet_gelukt", "reason": "geen e-mailadres"},
            ],
        )

        antwoord = await api.post(
            f"{LIJST}/reminder-proposals", json={"receivable_ids": [eerste, tweede]}
        )

        rijen = (
            await postgres_session.execute(
                text(
                    "SELECT user_id, CAST(event_metadata AS TEXT) FROM audit_logs "
                    "WHERE event_type = 'receivable_reminder_proposed' AND tenant_id = 1"
                )
            )
        ).all()
        assert (antwoord.status_code, len(rijen), rijen[0][0], "TOOL-A1" in rijen[0][1]) == (
            200,
            1,
            1,
            True,
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestTijdlijnRoute:
    async def test_the_timeline_lists_the_steps_in_dutch_with_the_names(
        self,
        api: AsyncClient,
        postgres_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        rij_id = (await _zaai(api))["F-2026-001"]
        _vervang_voorsteller(
            monkeypatch,
            [{"receivable_id": rij_id, "status": "wacht_op_goedkeuring", "ticket_ref": "TOOL-T1"}],
        )
        await api.post(f"{LIJST}/reminder-proposals", json={"receivable_ids": [rij_id]})
        await postgres_session.execute(
            text(
                "INSERT INTO hitl_tickets (ticket_ref, tenant_id, status, tool_name, payload, "
                "risk_level, expires_at, resolved_at, resolved_by) VALUES ('TOOL-T1', 1, "
                "'consumed', 'send_payment_reminder', CAST('{}' AS JSONB), 'high', "
                "clock_timestamp() + interval '1 day', clock_timestamp(), 1)"
            )
        )
        await postgres_session.execute(
            text(
                "INSERT INTO outgoing_messages (tenant_id, receivable_id, channel, kind, status, "
                "pogingen, recipient, subject, body, hitl_ticket_ref, verzonden_op, created_at) "
                "VALUES (1, :rid, 'email', 'herinnering', 'verzonden', 1, 'x@example.test', "
                "'onderwerp', 'tekst', 'TOOL-T1', clock_timestamp(), clock_timestamp())"
            ),
            {"rid": rij_id},
        )

        teksten = [g["tekst"] for g in await _tijdlijn(api, rij_id)]

        assert teksten == [
            "Factuur aangemaakt door admin@integration.test",
            "Herinnering voorgesteld door admin@integration.test",
            "Goedgekeurd door admin@integration.test",
            "Herinnering klaargezet voor verzending",
            "Herinnering verzonden",
        ]

    async def test_a_receivable_of_another_tenant_has_no_timeline(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        andere = await _rij_van_tenant_2(postgres_session)

        antwoord = await api.get(f"{LIJST}/{andere}/tijdlijn")

        assert antwoord.status_code == 404

    async def test_the_timeline_shows_nothing_of_the_recipient_or_the_letter(
        self,
        api: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        rij_id = (await _zaai(api))["F-2026-001"]
        await postgres_session.execute(
            text(
                "INSERT INTO outgoing_messages (tenant_id, receivable_id, channel, kind, status, "
                "pogingen, recipient, subject, body, verzonden_op, created_at) "
                "VALUES (1, :rid, 'email', 'herinnering', 'verzonden', 1, 'schuldenaar@example.test', "
                "'GEHEIM ONDERWERP', 'GEHEIME BRIEFTEKST', now(), now())"
            ),
            {"rid": rij_id},
        )

        tekst = (await api.get(f"{LIJST}/{rij_id}/tijdlijn")).text

        assert [w for w in ("schuldenaar@example", "GEHEIM") if w in tekst] == []

    async def test_a_tenant_id_in_the_query_is_ignored(self, api: AsyncClient, postgres_session: AsyncSession) -> None:
        andere = await _rij_van_tenant_2(postgres_session)

        antwoord = await api.get(f"{LIJST}/{andere}/tijdlijn", params={"tenant_id": 2})

        assert antwoord.status_code == 404

    async def test_a_user_without_read_right_is_refused(
        self, integration_app: Any, postgres_session: AsyncSession
    ) -> None:
        # De gewone gebruiker (rol `user`, alleen `*:read`) heeft wel read; een rol zonder receivables:read bestaat
        # in deze opzet niet. Gemeten wordt dus dat de route het recht vraagt: zonder token geen toegang.
        async with AsyncClient(
            transport=ASGITransport(app=integration_app), base_url="http://test"
        ) as anoniem:
            antwoord = await anoniem.get(f"{LIJST}/1/tijdlijn")

        assert antwoord.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.asyncio
class TestAanvragerMetNaam:
    async def test_the_audit_list_shows_the_requester_by_email(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        await postgres_session.execute(
            text(
                "INSERT INTO hitl_tickets (ticket_ref, tenant_id, status, tool_name, payload, "
                "risk_level, expires_at) VALUES ('TOOL-N1', 1, 'pending', 'send_payment_reminder', "
                "CAST('{\"_requested_by\": \"1\"}' AS JSONB), 'high', "
                "clock_timestamp() + interval '1 day')"
            )
        )

        antwoord = await api.get("/api/v1/tools/hitl/audit")

        tickets = {t["ticket_ref"]: t for t in antwoord.json()["data"]}
        assert tickets["TOOL-N1"]["requested_by_email"] == "admin@integration.test"


# --- Gate 2 ronde 1: rijslot en tenantfilter -------------------------------------------------------------


def _leg_sql_vast(session: AsyncSession) -> list[str]:
    from sqlalchemy import event

    uitgevoerd: list[str] = []

    def _noteer(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        uitgevoerd.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", _noteer)
    return uitgevoerd


@pytest.mark.integration
@pytest.mark.asyncio
class TestRijslot:
    async def test_ticking_off_locks_the_receivable_row(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        from src.core.repositories.receivable_repository import ReceivableRepository

        rij_id = (await _zaai(api))["F-2026-001"]
        sql = _leg_sql_vast(postgres_session)

        await ReceivableRepository(postgres_session).mark_paid_via_statement(1, rij_id, None)

        assert any("FROM receivables" in s and "FOR UPDATE" in s for s in sql)

    async def test_changing_the_escalation_term_locks_the_tenant_row(
        self, postgres_session: AsyncSession
    ) -> None:
        from src.core.governance.debiteuren_instellingen import schrijf_escalatie_na_dagen

        sql = _leg_sql_vast(postgres_session)

        await schrijf_escalatie_na_dagen(postgres_session, tenant_id=1, dagen=15)

        assert any("FROM tenants" in s and "FOR UPDATE" in s for s in sql)


@pytest.mark.integration
@pytest.mark.asyncio
class TestAanvragerUitEenAndereTenant:
    async def test_a_requester_of_another_tenant_gets_no_email(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        vreemd = await _seed().maak_tweede_gebruiker(
            postgres_session,
            tenant_id=2,
            email="vreemd@andere-tenant.example",
            password=_TESTSLEUTEL,
        )
        await postgres_session.execute(
            text(
                "INSERT INTO hitl_tickets (ticket_ref, tenant_id, status, tool_name, payload, "
                "risk_level, expires_at) VALUES ('TOOL-V1', 1, 'pending', 'send_payment_reminder', "
                "CAST(:p AS JSONB), 'high', clock_timestamp() + interval '1 day')"
            ),
            {"p": f'{{"_requested_by": "{vreemd}"}}'},
        )

        antwoord = await api.get("/api/v1/tools/hitl/audit")

        tickets = {t["ticket_ref"]: t for t in antwoord.json()["data"]}
        assert tickets["TOOL-V1"]["requested_by_email"] is None


# --- Gate 2 ronde 2: het slot werkt ook als de rij al in de sessie zit -----------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
class TestSlotOpVerseRij:
    """Een rijslot helpt niet als de sessie de rij al kent: zonder `populate_existing` blijft de OUDE status staan."""

    async def test_a_receivable_paid_elsewhere_after_loading_is_not_ticked_off_again(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        from src.core.repositories.receivable_repository import ReceivableRepository

        rij_id = (await _zaai(api))["F-2026-001"]
        repo = ReceivableRepository(postgres_session)
        geladen = await repo.list_all_for_matching(1, limit=100)  # de route houdt deze rijen ook vast
        assert geladen
        await postgres_session.execute(
            text("UPDATE receivables SET status = 'betaald' WHERE id = :i"), {"i": rij_id}
        )

        assert await repo.mark_paid_via_statement(1, rij_id, None) is None

    async def test_a_receivable_still_open_after_loading_is_ticked_off(
        self, api: AsyncClient, postgres_session: AsyncSession
    ) -> None:
        # Tweede helft: zonder deze is "nooit afvinken" een geldige oplossing.
        from src.core.repositories.receivable_repository import ReceivableRepository

        rij_id = (await _zaai(api))["F-2026-001"]
        repo = ReceivableRepository(postgres_session)
        geladen = await repo.list_all_for_matching(1, limit=100)  # de route houdt deze rijen ook vast
        assert geladen

        bijgewerkt = await repo.mark_paid_via_statement(1, rij_id, None)

        assert bijgewerkt is not None and bijgewerkt.status == "betaald"

    async def test_the_escalation_term_keeps_a_key_written_elsewhere(
        self, postgres_session: AsyncSession
    ) -> None:
        from sqlalchemy import select

        from src.core.governance.debiteuren_instellingen import schrijf_escalatie_na_dagen
        from src.core.models.rbac_models import Tenant

        bekend = (await postgres_session.execute(select(Tenant).where(Tenant.id == 1))).scalar_one()
        assert bekend.id == 1  # de sessie houdt de tenant vast, zoals een verzoek dat doet
        await postgres_session.execute(
            text(
                "UPDATE tenants SET settings = CAST(CAST(COALESCE(CAST(settings AS TEXT), '{}') AS JSONB) "
                "|| CAST('{\"elders_geschreven\": true}' AS JSONB) AS JSON) WHERE id = 1"
            )
        )

        await schrijf_escalatie_na_dagen(postgres_session, tenant_id=1, dagen=16)

        settings = (
            await postgres_session.execute(text("SELECT CAST(settings AS TEXT) FROM tenants WHERE id = 1"))
        ).scalar_one()
        assert "elders_geschreven" in settings

    async def test_four_eyes_keeps_a_key_written_elsewhere(
        self, postgres_session: AsyncSession
    ) -> None:
        from sqlalchemy import select

        from src.core.governance.four_eyes import write_four_eyes_actions
        from src.core.models.rbac_models import Tenant

        bekend = (await postgres_session.execute(select(Tenant).where(Tenant.id == 1))).scalar_one()
        assert bekend.id == 1
        await postgres_session.execute(
            text(
                "UPDATE tenants SET settings = CAST(CAST(COALESCE(CAST(settings AS TEXT), '{}') AS JSONB) "
                "|| CAST('{\"elders_geschreven\": true}' AS JSONB) AS JSON) WHERE id = 1"
            )
        )

        await write_four_eyes_actions(postgres_session, tenant_id=1, actions=[])

        settings = (
            await postgres_session.execute(text("SELECT CAST(settings AS TEXT) FROM tenants WHERE id = 1"))
        ).scalar_one()
        assert "elders_geschreven" in settings

    async def test_the_four_eyes_explanation_keeps_a_key_written_elsewhere(
        self, postgres_session: AsyncSession
    ) -> None:
        from sqlalchemy import select

        from src.core.governance.four_eyes import confirm_four_eyes_explanation
        from src.core.models.rbac_models import Tenant

        bekend = (await postgres_session.execute(select(Tenant).where(Tenant.id == 1))).scalar_one()
        assert bekend.id == 1
        await postgres_session.execute(
            text(
                "UPDATE tenants SET settings = CAST(CAST(COALESCE(CAST(settings AS TEXT), '{}') AS JSONB) "
                "|| CAST('{\"elders_geschreven\": true}' AS JSONB) AS JSON) WHERE id = 1"
            )
        )

        await confirm_four_eyes_explanation(postgres_session, tenant_id=1)

        settings = (
            await postgres_session.execute(text("SELECT CAST(settings AS TEXT) FROM tenants WHERE id = 1"))
        ).scalar_one()
        assert "elders_geschreven" in settings


# --- Gerichte review (laag): bestaat `pgcode` echt bij asyncpg? ------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
class TestEchteDeadlock:
    """Twee ECHTE verbindingen zetten elkaar vast; de 409-tak van de upload leunt op `exc.orig.pgcode`."""

    async def test_a_real_deadlock_carries_the_pgcode_the_upload_looks_for(self) -> None:
        import asyncio
        import os

        from sqlalchemy.exc import DBAPIError
        from sqlalchemy.ext.asyncio import create_async_engine

        from src.core.api.v1.receivables.dependencies import _SLOT_FOUTEN

        engine = create_async_engine(os.environ["SANSKRITISETU_TEST_DATABASE_URL"])

        async def _pak(verbinding: Any, sleutel: int) -> DBAPIError | None:
            try:
                await verbinding.execute(text(f"SELECT pg_advisory_xact_lock({sleutel})"))
                return None
            except DBAPIError as fout:
                await verbinding.rollback()
                return fout

        try:
            async with engine.connect() as a, engine.connect() as b:
                await a.execute(text("SELECT pg_advisory_xact_lock(90011)"))
                await b.execute(text("SELECT pg_advisory_xact_lock(90012)"))
                taak_a = asyncio.create_task(_pak(a, 90012))
                await asyncio.sleep(0.5)
                taak_b = asyncio.create_task(_pak(b, 90011))
                uitkomsten = await asyncio.wait_for(asyncio.gather(taak_a, taak_b), timeout=30)
                await a.rollback()
                await b.rollback()
        finally:
            await engine.dispose()

        fouten = [u for u in uitkomsten if u is not None]
        assert [getattr(f.orig, "pgcode", None) for f in fouten] == ["40P01"]
        assert "40P01" in _SLOT_FOUTEN
