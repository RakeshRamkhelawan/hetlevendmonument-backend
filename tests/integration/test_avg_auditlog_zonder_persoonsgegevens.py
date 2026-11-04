"""AVG C: het auditlog blijft bewaard bij het opheffen van een tenant, maar zonder persoonsgegevens.

Besluit Rakesh 2026-10-12: bij een harde `POST /api/gdpr/delete-all` verdwijnen de auditregels van die
tenant NIET (bewaarplicht, "bewaartermijn volgens de werkgever"), maar de persoonsgegevens erin wel.

Stap 0 (gemeten, zie de verslagen en `src/core/governance/avg_auditlog.py`):
- De hash (`HashChainVerifier._compute_hash`) dekt `tenant_id`, `action`, `resource`, `timestamp` en
  `previous_hash` (bij AI-context ook de AI-velden). `user_id`, `client_ip`, `description`, `details`
  en `event_metadata` staan BUITEN de hash en zijn dus te anonimiseren zonder de keten te breken.
- `resource` zit WEL in de hash en wordt dus niet aangeraakt.
- HITL-regels binden `user_id` via een digest in `resource` (ADR-036 H-2); een geanonimiseerde regel
  draagt een markering en wordt dan als "niet meer na te rekenen" gemeld, niet als manipulatie.
- Wat de tenantverwijdering blokkeert: `audit_logs_tenant_id_fkey` (NO ACTION) en 15 andere
  vreemde sleutels naar `tenants`.

Gemeten tegen echte Postgres, met een verse tenant en een controletenant (tenant 2).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio

from tests.integration.test_avg_wissen_werkt_echt import Persoon, _maak_gebruiker, _ruim_op
from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import _sql
from tests.integration.test_laatste_beheerder import _aanroep

EMAIL_BEHEERDER = "avgc-beheerder@avgc.invalid"
EMAIL_MEDEWERKER = "avgc-medewerker@avgc.invalid"
EMAIL_VREEMD = "avgc-vreemd@avgc.invalid"
IP_MEDEWERKER = "203.0.113.77"
IP_VREEMD = "203.0.113.88"
ANDERE_TENANT = 2
AANTAL_REGELS = 3


async def _schrijf_regel(
    tenant_id: int, user_id: int, email: str, ip: str, resource: str = "auth"
) -> None:
    from src.core.database.database import db_manager
    from src.core.governance.audit import AuditService

    async with db_manager.get_session() as session:
        await AuditService.log_action(
            tenant_id=tenant_id,
            action="avgc_test_actie",
            resource=resource,
            user_id=user_id,
            details={"email": email, "reden": "test"},
            session=session,
            threat_level="info",
            client_ip=ip,
            endpoint="/api/auth/login",
            description=f"Actie van {email}",
            event_type="avgc_test",
        )
        await session.commit()


@pytest_asyncio.fixture
async def omgeving() -> AsyncGenerator[tuple[int, Persoon, Persoon, Persoon], None]:
    """Verse tenant met beheerder en medewerker, met auditregels vol persoonsgegevens."""
    await _sql("DELETE FROM tenants WHERE slug = 'avgc-tenant'")
    tenant_id = int(
        (
            await _sql(
                "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
                "VALUES ('AVG C', 'avgc-tenant', true, 10, 10, 1) RETURNING id"
            )
        ).scalar_one()
    )
    await _sql(
        "INSERT INTO roles (tenant_id, name, is_active) VALUES (:t, 'admin', true)", t=tenant_id
    )
    beheerder = await _maak_gebruiker(EMAIL_BEHEERDER, tenant_id)
    medewerker = await _maak_gebruiker(EMAIL_MEDEWERKER, tenant_id)
    vreemd = await _maak_gebruiker(EMAIL_VREEMD, ANDERE_TENANT)
    for _ in range(AANTAL_REGELS):
        await _schrijf_regel(tenant_id, medewerker.id, EMAIL_MEDEWERKER, IP_MEDEWERKER)
    await _schrijf_regel(ANDERE_TENANT, vreemd.id, EMAIL_VREEMD, IP_VREEMD)
    yield tenant_id, beheerder, medewerker, vreemd
    await _sql("DELETE FROM audit_logs WHERE tenant_id = :t", t=tenant_id)
    await _sql(
        "DELETE FROM audit_logs WHERE tenant_id = :t AND action = 'avgc_test_actie'",
        t=ANDERE_TENANT,
    )
    for p in (beheerder, medewerker, vreemd):
        await _ruim_op(p.id)
    await _sql("DELETE FROM flows WHERE tenant_id = :t", t=tenant_id)
    await _sql("DELETE FROM roles WHERE tenant_id = :t", t=tenant_id)
    await _sql("DELETE FROM tenants WHERE id = :t", t=tenant_id)


async def _bied_export_aan(app: Any, tenant_id: int, beheerder: Persoon) -> None:
    """Een harde wissing vraagt eerst een aangeboden export (besluit Rakesh 2026-10-12)."""
    from tests.integration.conftest import _build_test_token

    token = _build_test_token(user_id=beheerder.id, email=EMAIL_BEHEERDER, tenant_id=tenant_id)
    antwoord = await _aanroep(
        app, token, "POST", "/api/gdpr/delete-all/export", {"recipient": "klant"}
    )
    assert antwoord.status_code == 200, antwoord.text


async def _hard_delete_all(app: Any, tenant_id: int, beheerder: Persoon) -> Any:
    from tests.integration.conftest import _build_test_token

    await _bied_export_aan(app, tenant_id, beheerder)
    token = _build_test_token(user_id=beheerder.id, email=EMAIL_BEHEERDER, tenant_id=tenant_id)
    return await _aanroep(
        app,
        token,
        "POST",
        "/api/gdpr/delete-all",
        {"delete_type": "hard", "confirmation_code": str(tenant_id)},
    )


async def _regels(tenant_id: int) -> list[Any]:
    return list(
        (
            await _sql(
                "SELECT id, user_id, client_ip, description, details::text, event_metadata::text "
                "FROM audit_logs WHERE tenant_id = :t AND action = 'avgc_test_actie' ORDER BY id",
                t=tenant_id,
            )
        ).all()
    )


GEHEIME_REDEN = "geheime-vrije-tekst-van-de-beheerder"


async def _maak_hitl_regel(tenant_id: int, medewerker: Persoon) -> int:
    from src.core.governance.hitl_evidence import build_resource

    resource = build_resource(
        ticket_ref=f"avgc-{medewerker.id}",
        tool_name="send_payment_reminder",
        user_id=medewerker.id,
        binding="b1",
    )
    await _schrijf_regel(tenant_id, medewerker.id, EMAIL_MEDEWERKER, IP_MEDEWERKER, resource)
    await _sql(
        "UPDATE audit_logs SET event_metadata = CAST(:m AS json) WHERE resource = :r",
        m='{"tool_name": "send_payment_reminder", "approval_binding": "b1"}',
        r=resource,
    )
    return int(
        (await _sql("SELECT id FROM audit_logs WHERE resource = :r", r=resource)).scalar_one()
    )


async def _verifieer_regel(regel_id: int, tenant_id: int) -> Any:
    from src.core.database.database import db_manager
    from src.core.governance.hash_chain import HashChainVerifier

    async with db_manager.get_session() as session:
        return await HashChainVerifier(session).verify_entry(regel_id, tenant_id)


@pytest.mark.asyncio
@pytest.mark.integration
class TestAuditlogZonderPersoonsgegevens:
    async def test_a_hard_delete_all_of_a_tenant_with_audit_rows_succeeds(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _ = omgeving

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text

    async def test_the_tenant_is_gone_afterwards(self, omgeving: Any, integration_app: Any) -> None:
        tenant_id, beheerder, _, _ = omgeving

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        aantal = (
            await _sql("SELECT count(*) FROM tenants WHERE id = :t", t=tenant_id)
        ).scalar_one()
        assert aantal == 0

    async def test_the_audit_rows_still_exist_afterwards(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _ = omgeving

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert len(await _regels(tenant_id)) == AANTAL_REGELS

    async def test_no_email_remains_in_the_audit_rows(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _ = omgeving

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        tekst = " ".join(" ".join(str(k) for k in r[3:]) for r in await _regels(tenant_id))
        assert EMAIL_MEDEWERKER not in tekst

    async def test_no_ip_address_remains_in_the_audit_rows(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _ = omgeving

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert IP_MEDEWERKER not in [r[2] for r in await _regels(tenant_id)]

    async def test_no_user_id_remains_in_the_audit_rows(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _ = omgeving

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert [r[1] for r in await _regels(tenant_id)] == [None] * AANTAL_REGELS

    async def test_the_hash_chain_is_still_valid_afterwards(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        from src.core.database.database import db_manager
        from src.core.governance.hash_chain import HashChainVerifier

        tenant_id, beheerder, _, _ = omgeving
        await _hard_delete_all(integration_app, tenant_id, beheerder)

        async with db_manager.get_session() as session:
            resultaat = await HashChainVerifier(session).verify_chain(tenant_id)

        assert (resultaat.is_valid, resultaat.tampering_detected) == (True, False)

    async def test_the_audit_rows_of_another_tenant_are_untouched(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, vreemd = omgeving

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        rij = (await _regels(ANDERE_TENANT))[0]
        assert (rij[1], rij[2], EMAIL_VREEMD in rij[3]) == (vreemd.id, IP_VREEMD, True)

    async def test_the_users_of_the_tenant_are_gone(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _ = omgeving

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        aantal = (
            await _sql("SELECT count(*) FROM users WHERE id = :u", u=medewerker.id)
        ).scalar_one()
        assert aantal == 0

    async def test_rows_in_the_other_blocking_tables_are_removed_too(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _ = omgeving
        await _sql(
            "INSERT INTO flows (tenant_id, name, react_flow_graph) VALUES (:t, 'avgc', '{}'::jsonb)",
            t=tenant_id,
        )

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text
        aantal = (
            await _sql("SELECT count(*) FROM flows WHERE tenant_id = :t", t=tenant_id)
        ).scalar_one()
        assert aantal == 0

    async def test_a_hitl_bound_row_is_not_reported_as_tampering_after_anonymising(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """De HITL-bewijsbinding noemt user_id; na het opheffen van de tenant is hij niet na te rekenen."""
        tenant_id, beheerder, medewerker, _ = omgeving
        regel_id = await _maak_hitl_regel(tenant_id, medewerker)
        await _hard_delete_all(integration_app, tenant_id, beheerder)

        resultaat = await _verifieer_regel(regel_id, tenant_id)

        assert resultaat.is_valid is True

    async def test_a_hitl_row_with_a_blanked_user_id_on_an_existing_tenant_is_still_tampering(
        self, omgeving: Any
    ) -> None:
        """De markering is geen vrijbrief: op een bestaande tenant blijft een gewijzigde binding fout."""
        tenant_id, _, medewerker, _ = omgeving
        regel_id = await _maak_hitl_regel(tenant_id, medewerker)
        await _sql(
            "UPDATE audit_logs SET user_id = NULL, "
            "event_metadata = CAST(:m AS json) WHERE id = :i",
            m='{"tool_name": "send_payment_reminder", "approval_binding": "b1", "geanonimiseerd": true}',
            i=regel_id,
        )

        resultaat = await _verifieer_regel(regel_id, tenant_id)

        assert resultaat.is_valid is False

    async def test_the_free_text_ai_summary_is_wiped_where_the_column_exists(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _ = omgeving
        await _sql("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ai_explanation_summary text")
        await _sql(
            "UPDATE audit_logs SET ai_explanation_summary = :s WHERE tenant_id = :t",
            s=f"Besluit over {EMAIL_MEDEWERKER}",
            t=tenant_id,
        )

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        resterend = (
            await _sql(
                "SELECT count(*) FROM audit_logs WHERE tenant_id = :t "
                "AND ai_explanation_summary IS NOT NULL",
                t=tenant_id,
            )
        ).scalar_one()
        assert resterend == 0

    async def test_a_row_of_another_tenant_that_names_a_deleted_person_is_anonymised(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """Anders blokkeert audit_logs_user_id_fkey het verwijderen van die persoon."""
        tenant_id, beheerder, medewerker, _ = omgeving
        await _schrijf_regel(ANDERE_TENANT, medewerker.id, EMAIL_MEDEWERKER, IP_MEDEWERKER)

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text
        rij = (
            await _sql(
                "SELECT count(*) FROM audit_logs WHERE tenant_id = :t AND client_ip = :ip",
                t=ANDERE_TENANT,
                ip=IP_MEDEWERKER,
            )
        ).scalar_one()
        assert rij == 0

    async def test_event_metadata_that_is_not_an_object_does_not_break_the_wipe(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _ = omgeving
        await _sql(
            "UPDATE audit_logs SET event_metadata = CAST('[1,2]' AS json) WHERE tenant_id = :t",
            t=tenant_id,
        )

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text

    async def test_the_free_text_reason_of_the_administrator_is_not_kept_for_a_hard_delete(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        from tests.integration.conftest import _build_test_token

        tenant_id, beheerder, _, _ = omgeving
        await _bied_export_aan(integration_app, tenant_id, beheerder)
        token = _build_test_token(user_id=beheerder.id, email=EMAIL_BEHEERDER, tenant_id=tenant_id)
        await _aanroep(
            integration_app,
            token,
            "POST",
            "/api/gdpr/delete-all",
            {
                "delete_type": "hard",
                "confirmation_code": str(tenant_id),
                "reason": GEHEIME_REDEN,
            },
        )

        tekst = (
            await _sql(
                "SELECT coalesce(string_agg(details::text, ' '), '') FROM audit_logs "
                "WHERE tenant_id = :t AND action = 'gdpr_delete_all'",
                t=tenant_id,
            )
        ).scalar_one()
        assert GEHEIME_REDEN not in tekst

    async def test_rows_in_more_of_the_blocking_tables_are_removed(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _ = omgeving
        await _sql(
            "INSERT INTO registered_agents (agent_id, address, tenant_id) VALUES ('avgc', 'x', :t)",
            t=tenant_id,
        )
        await _sql(
            "INSERT INTO governance_alerts (id, tenant_id, agent_name, severity, violation_type, "
            "dedup_key) VALUES (gen_random_uuid(), :t, 'a', 'low', 'v', 'avgc-dedup')",
            t=tenant_id,
        )

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text

    async def test_a_failure_halfway_rolls_everything_back(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        from unittest.mock import AsyncMock, patch

        tenant_id, beheerder, _, _ = omgeving
        await _sql(
            "INSERT INTO flows (tenant_id, name, react_flow_graph) VALUES (:t, 'avgc', '{}'::jsonb)",
            t=tenant_id,
        )

        with patch(
            "src.core.api.v1.gdpr_compliance.erasure_router.anonimiseer_auditlog_van_tenant",
            new=AsyncMock(side_effect=RuntimeError("stuk")),
        ):
            antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        resterend = (
            await _sql("SELECT count(*) FROM flows WHERE tenant_id = :t", t=tenant_id)
        ).scalar_one()
        assert (antwoord.status_code, resterend) == (500, 1)


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeLijstenBlijvenKloppen:
    async def test_every_blocking_foreign_key_to_tenants_is_handled(self) -> None:
        """Een nieuwe vreemde sleutel naar `tenants` zonder ON DELETE moet hier worden opgevangen."""
        from src.core.governance.avg_auditlog import TENANT_TABELLEN_DIE_DE_VERWIJDERING_BLOKKEREN

        rijen = (
            await _sql(
                "SELECT conrelid::regclass::text FROM pg_constraint WHERE contype = 'f' "
                "AND confrelid = 'tenants'::regclass AND confdeltype IN ('a', 'r')"
            )
        ).all()

        blokkerend = {str(r[0]) for r in rijen}
        assert blokkerend <= set(TENANT_TABELLEN_DIE_DE_VERWIJDERING_BLOKKEREN), (
            f"Niet opgevangen in avg_auditlog.TENANT_TABELLEN_DIE_DE_VERWIJDERING_BLOKKEREN: "
            f"{sorted(blokkerend - set(TENANT_TABELLEN_DIE_DE_VERWIJDERING_BLOKKEREN))}"
        )

    async def test_the_audit_log_has_no_foreign_key_to_tenants(self) -> None:
        rijen = (
            await _sql(
                "SELECT count(*) FROM pg_constraint WHERE contype = 'f' "
                "AND conrelid = 'audit_logs'::regclass AND confrelid = 'tenants'::regclass"
            )
        ).scalar_one()

        assert rijen == 0

    def test_the_metadata_keys_in_the_sql_match_the_constant(self) -> None:
        from src.core.governance.avg_auditlog import _ANONIMISEER, BEWIJS_SLEUTELS

        assert all(f"'{sleutel}'" in str(_ANONIMISEER) for sleutel in BEWIJS_SLEUTELS)

    async def test_every_blocking_foreign_key_to_users_is_handled(self) -> None:
        from src.core.governance.avg_auditlog import (
            TENANT_TABELLEN_BEWAARD_EN_GEANONIMISEERD,
            TENANT_TABELLEN_DIE_DE_VERWIJDERING_BLOKKEREN,
            TENANT_TABELLEN_MET_PERSOONSVERWIJZING,
        )

        rijen = (
            await _sql(
                "SELECT conrelid::regclass::text FROM pg_constraint WHERE contype = 'f' "
                "AND confrelid = 'users'::regclass AND confdeltype IN ('a', 'r')"
            )
        ).all()

        bekend = (
            {*TENANT_TABELLEN_DIE_DE_VERWIJDERING_BLOKKEREN}
            | {*TENANT_TABELLEN_MET_PERSOONSVERWIJZING}
            | {*TENANT_TABELLEN_BEWAARD_EN_GEANONIMISEERD}
            | {"audit_logs", "user_roles", "two_factor_auth", "token_blacklist"}
        )
        assert {str(r[0]) for r in rijen} <= bekend


async def _vul_rapporten(tenant_id: int, user_id: int) -> None:
    await _sql(
        "INSERT INTO ai_act_incident_reports (tenant_id, incident_type, severity, description, "
        "eu_reporting_required, resolution_status, incident_data) VALUES "
        "(:t, 'bias', 'high', :d, true, 'open', CAST(:j AS jsonb))",
        t=tenant_id,
        d=f"Gemeld door {EMAIL_MEDEWERKER} vanaf {IP_MEDEWERKER}",
        j='{"melder": "' + EMAIL_MEDEWERKER + '", "samenvatting": "model gaf afwijkend advies"}',
    )
    await _sql(
        "INSERT INTO governance_authority_reports (id, tenant_id, report_type, authority_name, "
        "content, created_by_user_id) VALUES (gen_random_uuid(), :t, 'art72', 'Autoriteit', "
        "CAST(:j AS jsonb), :u)",
        t=tenant_id,
        u=user_id,
        j='{"contact": "' + EMAIL_MEDEWERKER + '", "bevinding": "geen afwijkingen"}',
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestBewaardeRapporten:
    """AI-incidentmeldingen en toezichthouder-rapporten: bewaren zonder persoonsgegevens."""

    async def test_the_reports_still_exist_after_the_tenant_is_gone(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _ = omgeving
        await _vul_rapporten(tenant_id, medewerker.id)

        antwoord = await _hard_delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text
        meldingen = (
            await _sql(
                "SELECT count(*) FROM ai_act_incident_reports WHERE tenant_id = :t", t=tenant_id
            )
        ).scalar_one()
        rapporten = (
            await _sql(
                "SELECT count(*) FROM governance_authority_reports WHERE tenant_id = :t",
                t=tenant_id,
            )
        ).scalar_one()
        assert (meldingen, rapporten) == (1, 1)

    async def test_no_email_or_ip_remains_in_the_reports(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _ = omgeving
        await _vul_rapporten(tenant_id, medewerker.id)

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        melding = (
            await _sql(
                "SELECT description || ' ' || coalesce(incident_data::text, '') "
                "FROM ai_act_incident_reports WHERE tenant_id = :t",
                t=tenant_id,
            )
        ).scalar_one()
        rapport = (
            await _sql(
                "SELECT content::text FROM governance_authority_reports WHERE tenant_id = :t",
                t=tenant_id,
            )
        ).scalar_one()
        tekst = melding + " " + rapport
        assert EMAIL_MEDEWERKER not in tekst and IP_MEDEWERKER not in tekst

    async def test_the_evidence_itself_is_kept(self, omgeving: Any, integration_app: Any) -> None:
        tenant_id, beheerder, medewerker, _ = omgeving
        await _vul_rapporten(tenant_id, medewerker.id)

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        inhoud = (
            await _sql(
                "SELECT content::text FROM governance_authority_reports WHERE tenant_id = :t",
                t=tenant_id,
            )
        ).scalar_one()
        assert "geen afwijkingen" in inhoud

    async def test_the_person_reference_of_the_report_is_blanked(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _ = omgeving
        await _vul_rapporten(tenant_id, medewerker.id)

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        waarde = (
            await _sql(
                "SELECT created_by_user_id FROM governance_authority_reports WHERE tenant_id = :t",
                t=tenant_id,
            )
        ).scalar_one()
        assert waarde is None

    async def test_the_scrub_removes_emails_and_ips_recursively(self) -> None:
        from src.core.governance.avg_auditlog import scrub_json

        resultaat = scrub_json(
            {"a": ["mail x@y.nl", {"ip": "10.1.2.3"}], "b": 5, "x@y.nl": "sleutel"}
        )

        assert "x@y.nl" not in str(resultaat) and "10.1.2.3" not in str(resultaat)


NIET_BESTAANDE_TENANT_A = 987654
NIET_BESTAANDE_TENANT_B = 987655


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeHitlUitzonderingIsSmal:
    """De uitzondering voor een geanonimiseerde HITL-regel heeft DRIE voorwaarden: de tenantrij is weg,
    `user_id` is leeg en de markering staat er. Elke voorwaarde heeft een eigen test (mutatiebewijs):
    verwijder je een voorwaarde uit `_verify_bound_evidence`, dan wordt de bijbehorende test rood.
    """

    async def _regel_met_gewijzigde_binding(
        self, tenant_id: int, medewerker: Persoon, *, user_id_leeg: bool, markering: bool
    ) -> int:
        regel_id = await _maak_hitl_regel(tenant_id, medewerker)
        metadata = '{"tool_name": "ANDERE_TOOL", "approval_binding": "b1"'
        metadata += ', "geanonimiseerd": true}' if markering else "}"
        await _sql(
            "UPDATE audit_logs SET event_metadata = CAST(:m AS json) WHERE id = :i",
            m=metadata,
            i=regel_id,
        )
        if user_id_leeg:
            await _sql("UPDATE audit_logs SET user_id = NULL WHERE id = :i", i=regel_id)
        return regel_id

    async def test_a_gone_tenant_with_marker_and_blank_user_id_is_accepted(
        self, omgeving: Any
    ) -> None:
        """De bedoelde uitzondering: alle drie de voorwaarden gelden, dus niet als manipulatie gemeld."""
        _, _, medewerker, _ = omgeving
        try:
            regel_id = await self._regel_met_gewijzigde_binding(
                NIET_BESTAANDE_TENANT_A, medewerker, user_id_leeg=True, markering=True
            )

            resultaat = await _verifieer_regel(regel_id, NIET_BESTAANDE_TENANT_A)

            assert resultaat.is_valid is True
        finally:
            await _sql("DELETE FROM audit_logs WHERE tenant_id = :t", t=NIET_BESTAANDE_TENANT_A)

    async def test_a_kept_user_id_on_a_gone_tenant_is_still_reported(self, omgeving: Any) -> None:
        """Voorwaarde 'user_id leeg': markering + weg tenant + gewijzigde binding, user_id staat er nog."""
        _, _, medewerker, _ = omgeving
        try:
            regel_id = await self._regel_met_gewijzigde_binding(
                NIET_BESTAANDE_TENANT_A, medewerker, user_id_leeg=False, markering=True
            )

            resultaat = await _verifieer_regel(regel_id, NIET_BESTAANDE_TENANT_A)

            assert resultaat.is_valid is False
        finally:
            await _sql("DELETE FROM audit_logs WHERE tenant_id = :t", t=NIET_BESTAANDE_TENANT_A)

    async def test_a_missing_marker_on_a_gone_tenant_is_still_reported(self, omgeving: Any) -> None:
        """Voorwaarde 'markering': weg tenant + lege user_id + gewijzigde binding, maar geen markering."""
        _, _, medewerker, _ = omgeving
        try:
            regel_id = await self._regel_met_gewijzigde_binding(
                NIET_BESTAANDE_TENANT_B, medewerker, user_id_leeg=True, markering=False
            )

            resultaat = await _verifieer_regel(regel_id, NIET_BESTAANDE_TENANT_B)

            assert resultaat.is_valid is False
        finally:
            await _sql("DELETE FROM audit_logs WHERE tenant_id = :t", t=NIET_BESTAANDE_TENANT_B)


ALLES_WAT_MAG_BLIJVEN = {
    "audit_logs",
    "ai_act_incident_reports",
    "governance_authority_reports",
    "request_audit_logs",
}
HERKENBAAR = "@"


async def _tabellen_met_rijen(tenant_id: int) -> set[str]:
    """Elke tabel met een kolom `tenant_id` (elk type) waarin nog rijen van deze tenant staan."""
    namen = [
        r[0]
        for r in (
            await _sql(
                "SELECT c.table_name FROM information_schema.columns c "
                "JOIN information_schema.tables t ON t.table_name = c.table_name "
                "AND t.table_schema = c.table_schema AND t.table_type = 'BASE TABLE' "
                "WHERE c.column_name = 'tenant_id' AND c.table_schema = current_schema()"
            )
        ).all()
    ]
    gevuld: set[str] = set()
    for naam in namen:
        aantal = (
            await _sql(
                f"SELECT count(*) FROM {naam} WHERE CAST(tenant_id AS text) = :t",  # noqa: S608
                t=str(tenant_id),
            )
        ).scalar_one()
        if aantal:
            gevuld.add(naam)
    return gevuld


@pytest.mark.asyncio
@pytest.mark.integration
class TestEchtAnoniem:
    """Wat er na het opheffen van een tenant overblijft, gemeten over ALLE tabellen en echte schrijvers.

    Gemeten 2026-10-12: de verzoeklog (`request_audit_logs`) droeg e-mail, IP en user agent per tenant en
    werd niet geraakt. Wat in de hash staat (`resource`, `action`, `timestamp`, `tenant_id`) is NIET te
    anonimiseren zonder de keten te breken: `resource` draagt bij echte schrijvers een numerieke id
    (`user:<id>`, `portal_user:<id>`, `patient:<id>`, `donor:<id>`), nooit een e-mailadres (gemeten met
    een zoekopdracht over alle `resource=`-aanroepen in `src/`).
    """

    async def _zaai_verzoeklog(self, tenant_id: int, user_id: int) -> None:
        await _sql(
            "INSERT INTO request_audit_logs (request_id, user_id, user_email, tenant_id, method, path, "
            "query_params, ip_address, user_agent, changes) VALUES "
            "('avgc-req', :u, :e, :t, 'GET', :p, 'email=x@y.nl', :ip, 'Mozilla/5.0', CAST(:c AS json))",
            u=user_id,
            e=EMAIL_MEDEWERKER,
            t=str(tenant_id),
            p=f"/api/users/by-email/{EMAIL_MEDEWERKER}",
            ip=IP_MEDEWERKER,
            c='{"naam": "Jan Jansen"}',
        )

    async def test_the_request_log_loses_every_personal_field(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _ = omgeving
        await self._zaai_verzoeklog(tenant_id, medewerker.id)
        try:
            await _hard_delete_all(integration_app, tenant_id, beheerder)

            rij = (
                await _sql(
                    "SELECT user_id, user_email, ip_address, user_agent, query_params, "
                    "changes::text, path FROM request_audit_logs WHERE tenant_id = :t",
                    t=str(tenant_id),
                )
            ).one()
            assert (rij[0], rij[1], rij[2], rij[3], rij[4], rij[5]) == (None,) * 6
            assert EMAIL_MEDEWERKER not in rij[6]
        finally:
            await _sql("DELETE FROM request_audit_logs WHERE tenant_id = :t", t=str(tenant_id))

    async def test_the_request_log_of_another_tenant_is_untouched(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, vreemd = omgeving
        await self._zaai_verzoeklog(ANDERE_TENANT, vreemd.id)
        try:
            await _hard_delete_all(integration_app, tenant_id, beheerder)

            email = (
                await _sql(
                    "SELECT user_email FROM request_audit_logs WHERE tenant_id = :t",
                    t=str(ANDERE_TENANT),
                )
            ).scalar_one()
            assert email == EMAIL_MEDEWERKER
        finally:
            await _sql("DELETE FROM request_audit_logs WHERE tenant_id = :t", t=str(ANDERE_TENANT))

    async def test_only_the_known_tables_keep_rows_of_the_tenant(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _ = omgeving
        await self._zaai_verzoeklog(tenant_id, medewerker.id)
        try:
            voor = await _tabellen_met_rijen(tenant_id)
            assert "users" in voor  # controlegroep: de meting ziet wel degelijk gevulde tabellen

            await _hard_delete_all(integration_app, tenant_id, beheerder)

            assert (await _tabellen_met_rijen(tenant_id)) - ALLES_WAT_MAG_BLIJVEN == set()
        finally:
            await _sql("DELETE FROM request_audit_logs WHERE tenant_id = :t", t=str(tenant_id))

    async def test_real_writers_leave_no_email_in_any_audit_column(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """De exportroute en de wisroute schrijven echte auditregels (geen verzonnen invoer)."""
        tenant_id, beheerder, _, _ = omgeving

        await _hard_delete_all(integration_app, tenant_id, beheerder)  # biedt eerst een export aan

        tekst = (
            await _sql(
                "SELECT coalesce(string_agg(coalesce(resource,'') || ' ' || coalesce(endpoint,'') "
                "|| ' ' || coalesce(description,'') || ' ' || coalesce(details::text,'') "
                "|| ' ' || coalesce(event_metadata::text,'') || ' ' || coalesce(client_ip,''), ' '), '') "
                "FROM audit_logs WHERE tenant_id = :t",
                t=tenant_id,
            )
        ).scalar_one()
        assert HERKENBAAR not in tekst and IP_MEDEWERKER not in tekst

    async def test_a_numeric_user_id_in_resource_stays_because_it_is_in_the_hash(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """Vastgelegd besluit-in-code: `resource` is hash-bepalend en blijft dus staan, ook met een id."""
        tenant_id, beheerder, medewerker, _ = omgeving
        await _schrijf_regel(tenant_id, medewerker.id, EMAIL_MEDEWERKER, IP_MEDEWERKER, f"user:{medewerker.id}")

        await _hard_delete_all(integration_app, tenant_id, beheerder)

        aantal = (
            await _sql(
                "SELECT count(*) FROM audit_logs WHERE tenant_id = :t AND resource = :r",
                t=tenant_id,
                r=f"user:{medewerker.id}",
            )
        ).scalar_one()
        assert aantal == 1
