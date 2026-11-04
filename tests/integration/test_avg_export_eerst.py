"""EERST EXPORT: een tenant wordt pas gewist nadat er een export is aangeboden (AVG art. 28 lid 3 sub g).

Besluit Rakesh 2026-10-12 na het bewaarplichtonderzoek (docs/onderzoek-bewaarplicht-en-opgeheven-klanten.md):
de bewaarplicht van facturen, loonadministratie en HR-gegevens ligt bij de KLANT of, na ontbinding, bij de
bewaarder (BW 2:24) of de curator (Fw 105b). Een verwerker mag niet wissen voordat die de gegevens heeft
kunnen ophalen. Dus:

- `POST /api/gdpr/delete-all/export` (beheerder) bouwt een leesbare export van ALLE tenantgegevens en legt
  vast aan wie hij is aangeboden (klant, bewaarder of curator) met een SHA-256 van de inhoud;
- een HARDE delete-all zonder aangeboden export geeft 409 en wist niets;
- een tenantbrede (zachte) delete-all wist na de 30 dagen alleen als er een export is aangeboden; tot dan
  wacht de planner. Een losse medewerker-wissing valt er niet onder.

Gemeten (2026-10-12): de bestaande `POST /api/gdpr/export` is een persoonlijke inzage (alleen de eigen
gebruikersrij, eigen workflows, 90 dagen eigen auditregels) en bevat geen debiteuren, personeelsgegevens of
andere gebruikers; daarom is een eigen tenantbrede export gebouwd.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from tests.integration.test_avg_30_dagen_en_een_medewerker import (  # noqa: F401
    EMAIL_BEHEERDER,
    EMAIL_MEDEWERKER,
    _auditacties,
    _delete_all,
    _draai_planner_en_purges,
    _erase,
    _gebruiker,
    _laat_de_termijn_verstrijken,
    _token,
    omgeving,
)
from tests.integration.test_avg_wissen_werkt_echt import _tel
from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import _sql
from tests.integration.test_laatste_beheerder import _aanroep


async def _hard_delete_all(app: Any, tenant_id: int, beheerder: Any) -> Any:
    return await _aanroep(
        app,
        _token(beheerder.id, EMAIL_BEHEERDER, tenant_id),
        "POST",
        "/api/gdpr/delete-all",
        {"delete_type": "hard", "confirmation_code": str(tenant_id)},
    )


async def _laat_de_delete_all_termijn_verstrijken(tenant_id: int) -> None:
    """Zet de termijn van de gebruikers EN de datum in de delete-all-auditregel op dezelfde dag.

    Alleen de gebruikers verschuiven (zoals `_laat_de_termijn_verstrijken`) herkent de groep van
    de delete-all niet meer: die wordt aan de datum in de auditregel herkend.
    """
    verstreken = datetime.now(timezone.utc) - timedelta(days=1)
    await _sql(
        "UPDATE users SET deletion_scheduled_for = :d "
        "WHERE tenant_id = :t AND deletion_scheduled_for IS NOT NULL",
        t=tenant_id,
        d=verstreken,
    )
    await _sql(
        "UPDATE audit_logs SET details = (details::jsonb || jsonb_build_object("
        "'scheduled_purge', CAST(:s AS text)))::json "
        "WHERE tenant_id = :t AND action = 'gdpr_delete_all'",
        t=tenant_id,
        s=verstreken.isoformat(),
    )


async def _export(
    app: Any,
    tenant_id: int,
    wie: Any,
    email: str,
    ontvanger: str = "klant",
    naam: str | None = None,
) -> Any:
    body: dict[str, Any] = {"recipient": ontvanger}
    if naam is not None:
        body["recipient_name"] = naam
    return await _aanroep(
        app, _token(wie.id, email, tenant_id), "POST", "/api/gdpr/delete-all/export", body
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestHardeWissingVraagEerstEenExport:
    async def test_a_hard_delete_all_without_an_export_is_refused(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 409, antwoord.text

    async def test_the_refusal_names_the_export_route(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert "delete-all/export" in antwoord.text

    async def test_nothing_is_wiped_when_the_hard_delete_is_refused(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        aantal = (
            await _sql("SELECT count(*) FROM users WHERE tenant_id = :t", t=tenant_id)
        ).scalar_one()
        assert aantal == 3

    async def test_after_an_export_the_hard_delete_goes_through(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeTenantExport:
    async def test_the_administrator_gets_an_export(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)

        assert antwoord.status_code == 200, antwoord.text

    async def test_the_export_contains_every_user_of_the_tenant(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)

        assert len(antwoord.json()["data"]["users"]["rijen"]) == 3

    async def test_the_export_contains_business_rows_of_other_tables(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        await _sql(
            "INSERT INTO flows (tenant_id, name, react_flow_graph) "
            "VALUES (:t, 'avg-export', '{}'::jsonb)",
            t=tenant_id,
        )
        try:
            antwoord = await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)

            namen = [r["name"] for r in antwoord.json()["data"]["flows"]["rijen"]]
            assert namen == ["avg-export"]
        finally:
            await _sql("DELETE FROM flows WHERE tenant_id = :t", t=tenant_id)

    async def test_the_export_never_contains_password_hashes_or_secrets(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)

        sleutels = {
            sleutel.lower()
            for tabel in antwoord.json()["data"].values()
            for rij in tabel["rijen"]
            for sleutel in rij
        }
        assert not [s for s in sleutels if "password" in s or "secret" in s or "token" in s]

    async def test_the_export_does_not_contain_another_tenants_rows(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, vreemd = omgeving

        antwoord = await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)

        ids = [r["id"] for r in antwoord.json()["data"]["users"]["rijen"]]
        assert vreemd.id not in ids

    async def test_the_answer_carries_a_checksum_and_the_recipient(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _export(
            integration_app, tenant_id, beheerder, EMAIL_BEHEERDER, "bewaarder", "Mevr. De Vries"
        )

        j = antwoord.json()
        assert (j["recipient"], len(j["sha256"])) == ("bewaarder", 64)

    async def test_the_answer_says_in_plain_language_what_happens_next(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)

        assert "export" in antwoord.json()["message"].lower()

    async def test_the_offer_is_recorded_in_the_audit_log(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)

        assert "gdpr_tenant_export_offered" in await _auditacties(tenant_id)

    async def test_an_unknown_recipient_is_rejected(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER, "buurman")

        assert antwoord.status_code == 422

    async def test_an_ordinary_user_may_not_request_it(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, _, medewerker, _, _ = omgeving

        antwoord = await _export(integration_app, tenant_id, medewerker, EMAIL_MEDEWERKER)

        assert antwoord.status_code == 403

    async def test_a_failed_offer_does_not_count_as_offered(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER, "buurman")

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 409


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeZachteTenantWissingWachtOpDeExport:
    async def test_after_the_term_the_purge_waits_when_no_export_was_offered(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _laat_de_delete_all_termijn_verstrijken(tenant_id)

        await _draai_planner_en_purges()

        assert (await _gebruiker(medewerker.id))["gepland"] is not None

    async def test_nothing_is_wiped_while_it_waits(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _laat_de_delete_all_termijn_verstrijken(tenant_id)

        await _draai_planner_en_purges()

        assert await _tel(medewerker, "cva_conversations") == 1

    async def test_after_the_term_the_planner_proceeds_once_an_export_was_offered(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, collega, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)
        await _laat_de_delete_all_termijn_verstrijken(tenant_id)

        await _draai_planner_en_purges()

        mails = [(await _gebruiker(p.id))["email"] for p in (beheerder, medewerker, collega)]
        assert all(m.endswith("@purged.invalid") for m in mails)

    async def test_a_single_employee_erasure_does_not_need_an_export(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)
        await _laat_de_termijn_verstrijken(tenant_id)

        assert await _draai_planner_en_purges() == [(medewerker.id, tenant_id)]

    async def test_the_delete_all_answer_tells_that_an_export_must_be_offered(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _delete_all(integration_app, tenant_id, beheerder)

        assert "export" in antwoord.json()["message"].lower()

    async def test_the_users_stay_unchanged_when_waiting(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _laat_de_delete_all_termijn_verstrijken(tenant_id)
        await _draai_planner_en_purges()

        gebruiker = await _gebruiker(medewerker.id)

        assert gebruiker["email"] == EMAIL_MEDEWERKER


@pytest.mark.asyncio
@pytest.mark.integration
class TestUitDeGate2Review:
    """Gate 2 (2026-10-13, code-reviewer + quality-reviewer) vond drie gaten; elk heeft hier een test."""

    async def test_every_credential_like_column_of_a_tenant_table_is_filtered(self) -> None:
        """MAJOR 1: `activepieces_connections.encrypted_credentials` ging mee in de export."""
        from src.core.governance.avg_tenant_export import _is_gevoelig

        kolommen = [
            r[0]
            for r in (
                await _sql(
                    "SELECT DISTINCT c.column_name FROM information_schema.columns c "
                    "JOIN information_schema.columns t ON t.table_name = c.table_name "
                    "AND t.table_schema = c.table_schema AND t.column_name = 'tenant_id' "
                    "WHERE c.table_schema = current_schema() AND c.column_name ~* "
                    "'(credential|encrypt|secret|token|passw|api_?key|private)'"
                )
            ).all()
        ]

        assert [k for k in kolommen if not _is_gevoelig(k)] == []

    async def test_a_second_soft_delete_all_after_the_term_still_waits_for_an_export(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """MAJOR 2: een nieuwe aanvraag na het verlopen van de eerste liet de oude groep zonder export door."""
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _laat_de_delete_all_termijn_verstrijken(tenant_id)
        await _delete_all(integration_app, tenant_id, beheerder)

        await _draai_planner_en_purges()

        assert (await _gebruiker(medewerker.id))["email"] == EMAIL_MEDEWERKER

    async def test_the_export_is_throttled_per_tenant(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """De export bouwt een dossier van de hele tenant: niet onbeperkt herhaalbaar."""
        tenant_id, beheerder, _, _, _ = omgeving
        codes = [
            (await _export(integration_app, tenant_id, beheerder, EMAIL_BEHEERDER)).status_code
            for _ in range(7)
        ]

        assert codes[-1] == 429

    def test_an_integer_tenant_column_is_compared_as_a_number_so_its_index_is_used(self) -> None:
        from src.core.governance.avg_tenant_export import waarde_voor_kolom

        assert (waarde_voor_kolom("integer", 7), waarde_voor_kolom("character varying", 7)) == (7, "7")
