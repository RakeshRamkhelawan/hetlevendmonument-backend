"""Een gewone toolactie van een agent MOET door de ECHTE raad komen (ADR-036 D2/D10).

Waarom dit bestand buiten `tests/unit/als`, `tests/unit/agents` en `tests/unit/tool_broker`
staat: in die drie bomen is `council_gate` een autouse-fixture die standaard APPROVED
teruggeeft. Dat staat met zoveel woorden in `tests/fixtures/agent_governance.py` als bewust
risico uit de Gate 2-review van BE-AGT-043 -- "het verwijderen van de Council-poort uit
`act()` maakt in die bomen geen enkele test rood". Precies daardoor bleef onzichtbaar dat de
poort in werkelijkheid ALLES weigert.

**Stand voor de fix, gemeten 2026-08-15 tegen echte Postgres.** Vier officieren blokkeerden:
ComplianceOfficer `APPROVE_WITH_MODIFICATION` (MISSING_AI_DISCLOSURE), SecurityOfficer VETO
(MISSING_SCOPE), ResourceOfficer DEFER (PRANA_BUDGET_EMPTY) en SanityOfficer VETO
(HALLUCINATION_DETECTED, empty_suggestion). De coordinator maakt van elke MODIFY een MODIFIED
(`coordinator.py:311`) en de agent-poort laat uitsluitend `APPROVED` door -- terecht, want hij
kan de gevraagde parameterwijziging niet toepassen. Netto voerde geen enkele skill ooit een
tool uit.

**Stand na SP-COUNCIL-GATE-001 (2026-08-16).** Alle zeven officieren keuren goed voor een
gebruiker MET het vereiste recht, en de SecurityOfficer weigert nog steeds met MISSING_SCOPE
voor een gebruiker ZONDER dat recht. Beide richtingen staan hieronder; de eerste zonder de
tweede zou betekenen dat een agent een omweg is om de rechten van de aanvrager heen.

Deze test roept de PRODUCTIE-ingang aan (`request_council_decision_for_agent`), niet een
nagebouwde raad. Een nagebouwde raad bewijst alleen dat de kopie werkt.

**Waarom een integratietest en geen unittest.** De auditschrijver van de raad gebruikt
`pg_advisory_xact_lock` om de hashketen te serialiseren. SQLite kent die functie niet, dus in
de unit-boom eindigt elke beraadslaging in "een interne fout" en zou deze test om de
VERKEERDE reden rood staan -- een test die faalt om iets anders dan wat hij bewaakt, leert je
hem te negeren.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

PILOT_AGENT = "skillsgaptraining"
PILOT_TENANT = 1
PILOT_USER = 1  # admin@integration.test, rol `admin` (conftest-seed)
PILOT_USER_ZONDER_RECHT = 2  # user@integration.test, GEEN rol (conftest-seed)


async def _seed_tenant(session: AsyncSession, tenant_id: int) -> None:
    """Zorg dat de tenant bestaat -- idempotent, want de integratiedatabase wordt gedeeld."""
    from sqlalchemy import select

    from src.core.models.rbac_models import Tenant

    bestaat = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if bestaat is None:
        session.add(
            Tenant(
                id=tenant_id,
                name="Pilot",
                slug=f"pilot-{tenant_id}",
                prana_budget=1_000_000,
                prana_spent=0,
            )
        )
        await session.commit()


async def _require_user_with_role(
    session: AsyncSession, *, user_id: int, tenant_id: int, rol: str | None
) -> None:
    """Controleer de VOORWAARDE in plaats van hem te zaaien.

    Zaaien werkt hier niet: de `db_session`-fixture van de integratiesuite draait binnen een
    transactie die aan het eind terugrolt, terwijl de raad zijn eigen verbinding opent via
    `db_manager.get_session()`. Een gebruiker die hier wordt toegevoegd bestaat voor de raad
    dus niet -- gemeten 2026-08-15: de test faalde op MISSING_SCOPE terwijl de gebruiker in
    de test wel leek te bestaan.

    `tests/integration/conftest.py` zaait al precies de twee gebruikers die deze test nodig
    heeft: een met de rol `admin` en een zonder rol. Deze functie legt vast DAT hij daarop
    leunt, zodat een wijziging in die seed hier een leesbare melding geeft in plaats van een
    onverklaarbare weigering.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from src.core.models.rbac_models import User

    gebruiker = (
        await session.execute(
            select(User).options(selectinload(User.roles)).where(User.id == user_id)
        )
    ).scalar_one_or_none()

    assert gebruiker is not None, (
        f"Gebruiker {user_id} ontbreekt in de integratiedatabase. Deze test leunt op de "
        "seed in tests/integration/conftest.py; is die veranderd?"
    )
    assert gebruiker.tenant_id == tenant_id, (
        f"Gebruiker {user_id} hoort bij tenant {gebruiker.tenant_id}, verwacht {tenant_id}."
    )
    rollen = {r.name for r in gebruiker.roles}
    if rol is None:
        assert not rollen, (
            f"Gebruiker {user_id} heeft rollen {sorted(rollen)} terwijl deze test juist een "
            "gebruiker ZONDER rechten nodig heeft."
        )
    else:
        assert rol in rollen, (
            f"Gebruiker {user_id} heeft rollen {sorted(rollen)}, verwacht {rol!r}."
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestAgentToolActionsPassTheCouncil:
    async def test_a_normal_tool_action_is_approved(self, db_session: AsyncSession) -> None:
        """De piloot vraagt een leesactie aan; de raad hoort die goed te keuren.

        Dit is de test die ontbrak. Faalt hij, dan kan GEEN ENKELE skill een tool uitvoeren --
        de governancelaag doet dan niet te weinig maar te veel, en dat is even kapot.
        """
        from src.core.copilot.council.background_gate import request_council_decision_for_agent
        from src.core.copilot.council.types import DecisionVerdict, ProposalTrigger
        from src.core.als.agents.specialist_base import _AI_DISCLOSURE

        await _seed_tenant(db_session, PILOT_TENANT)
        await _require_user_with_role(
            db_session, user_id=PILOT_USER, tenant_id=PILOT_TENANT, rol="admin"
        )

        outcome = await request_council_decision_for_agent(
            tenant_id=PILOT_TENANT,
            agent_id=PILOT_AGENT,
            user_id=PILOT_USER,
            action_type="query_hr_database",
            # Exact wat `specialist_base._council_rejection` meestuurt: toolnaam,
            # SLEUTELNAMEN (nooit de waarden -- BE-AGT-043), en de door het SYSTEEM gezette
            # bekendmaking en afdeling.
            action_params={
                "tool": "query_hr_database",
                "arg_keys": ["role"],
                "ai_disclosure": _AI_DISCLOSURE,
                "department": "hr_culture",
                "specialisation": "Skills Gap Training Specialist",
            },
            reasoning=f"Agent {PILOT_AGENT} wil query_hr_database uitvoeren.",
            message=(
                f"Agent {PILOT_AGENT} vraagt toestemming om de tool query_hr_database uit "
                "te voeren."
            ),
            trigger=ProposalTrigger.USER_REQUEST,
        )
        decision = outcome.decision

        oordelen = [
            f"  {v.officer_name}: {v.verdict.value} ({v.reason_code}) -- {v.reason_text}"
            for v in decision.officer_verdicts
        ]
        assert decision.verdict is DecisionVerdict.APPROVED, (
            f"De raad gaf {decision.verdict.value} in plaats van APPROVED. De agent-poort "
            "laat alleen APPROVED door, dus hiermee voert geen enkele skill ooit een tool "
            "uit. Oordeel per officier: " + " | ".join(oordelen)
        )

    async def test_the_same_action_is_refused_without_the_permission(
        self, db_session: AsyncSession
    ) -> None:
        """De tegenrichting, en de belangrijkste helft.

        Zonder deze test is "keur alles goed" een geldige oplossing voor de test hierboven, en
        dan is de agent een omweg om de rechten van de aanvrager heen. Zelfde tenant, zelfde
        agent, zelfde tool -- alleen een andere MENS. Die tweede gebruiker heeft in de
        conftest-seed GEEN rol, dus deze test toont 'zonder rechten wordt geweigerd'. Dat
        leesrecht alleen te weinig is voor een admin-tool bewijst
        `tests/unit/auth/test_user_scope_covers_broker_tools.py` met een `user`-rol.
        """
        from src.core.copilot.council.background_gate import request_council_decision_for_agent
        from src.core.copilot.council.types import DecisionVerdict, ProposalTrigger
        from src.core.als.agents.specialist_base import _AI_DISCLOSURE

        await _seed_tenant(db_session, PILOT_TENANT)
        await _require_user_with_role(
            db_session, user_id=PILOT_USER_ZONDER_RECHT, tenant_id=PILOT_TENANT, rol=None
        )

        outcome = await request_council_decision_for_agent(
            tenant_id=PILOT_TENANT,
            agent_id=PILOT_AGENT,
            user_id=PILOT_USER_ZONDER_RECHT,
            action_type="query_hr_database",
            action_params={
                "tool": "query_hr_database",
                "arg_keys": ["role"],
                "ai_disclosure": _AI_DISCLOSURE,
                "department": "hr_culture",
                "specialisation": "Skills Gap Training Specialist",
            },
            reasoning=f"Agent {PILOT_AGENT} wil query_hr_database uitvoeren.",
            message=(
                f"Agent {PILOT_AGENT} vraagt toestemming om de tool query_hr_database uit "
                "te voeren."
            ),
            trigger=ProposalTrigger.USER_REQUEST,
        )
        decision = outcome.decision

        assert decision.verdict is not DecisionVerdict.APPROVED, (
            "Een gebruiker zonder rechten kreeg goedkeuring voor een leesactie op "
            "personeelsgegevens. Dan is de agent een rechtenverhoging."
        )
        redenen = {v.reason_code for v in decision.officer_verdicts}
        assert "MISSING_SCOPE" in redenen, (
            "De weigering komt niet van de rechtencontrole maar ergens anders vandaan "
            f"({sorted(redenen)}). Dan bewijst deze test niet wat hij beweert."
        )

    async def test_the_council_is_not_stubbed_in_this_module(self) -> None:
        """Vangnet: zodra iemand hier een council-stub toevoegt, is de test hierboven hol.

        Zelfde patroon als `test_the_permission_check_is_not_patched_here` (ADR-036 OP-103):
        een autouse-fixture die de gecontroleerde functie patcht maakt de assertie `assert
        True`, en dat is in dit project al twee keer gebeurd.
        """
        from unittest.mock import Mock

        from src.core.copilot.council import background_gate

        echt = background_gate.request_council_decision_for_agent
        assert not isinstance(echt, Mock), (
            "`request_council_decision_for_agent` is in deze module gepatcht. Dan toetst de "
            "test hierboven een stub en niet de raad."
        )
        assert echt.__module__.startswith("src.core.copilot.council"), (
            f"De ingang komt uit {echt.__module__} in plaats van uit de productiemodule."
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestTheGateTranslatesTheVerdict:
    async def test_only_approved_passes_the_agent_gate(self, db_session: AsyncSession) -> None:
        """De poort laat uitsluitend APPROVED door -- MODIFIED wordt nooit stilzwijgend uitgevoerd.

        Legt de bestaande keuze vast in plaats van hem te veranderen: de poort kan geen
        parameters teruggeven, dus MODIFIED doorlaten zou de ONGEWIJZIGDE actie uitvoeren en
        precies de inperking negeren waar de officier om vroeg. Deze test bewaakt dat die
        redenering niet stilletjes wordt omgedraaid als iemand de poort wil "deblokkeren".

        `SkillsGapTrainingSkill` is de Annex III/HITL-piloot (`human_in_the_loop: hitl` in het
        manifest, de enige van 12 zulke skills die deze testmodule gebruikt). Sinds ADR-036
        OP-168-vervolg (2026-08-25, Rakesh's GO, zie `specialist_base.py`'s D4-002-floor)
        wordt een MODIFIED-verdict voor DEZE piloot niet meer kaal geweigerd maar opgetild naar
        HITL_REQUIRED met een echt goedkeuringsticket -- daarom vereist deze test nu een echte
        databasesessie (het ticket wordt echt aangemaakt, niet gemockt). Voor elke andere skill
        (`human_in_the_loop: hotl`, 123 van de 135) blijft MODIFIED een kale weigering; dat pad
        raakt deze test niet, want hij test specifiek de piloot.
        """
        from unittest.mock import AsyncMock, patch

        from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill
        from src.core.copilot.council.background_gate import AgentCouncilOutcome
        from src.core.copilot.council.types import DecisionVerdict

        await _seed_tenant(db_session, PILOT_TENANT)
        await _require_user_with_role(
            db_session, user_id=PILOT_USER, tenant_id=PILOT_TENANT, rol="admin"
        )

        agent = SkillsGapTrainingSkill(tenant_id=PILOT_TENANT)
        agent._initiated_by_user_id = PILOT_USER

        besluit: Any = AsyncMock()
        besluit.verdict = DecisionVerdict.MODIFIED
        besluit.explanation_for_user = "officier wil een aanpassing"
        # MODIFIED is geen HITL_REQUIRED, dus de gate zou hier zelf geen ticket hebben
        # aangemaakt (ADR-036 OP-167) -- het ticket hieronder komt van de D4-002-floor zelf.
        uitkomst = AgentCouncilOutcome(decision=besluit, hitl_ticket_ref=None)

        with patch(
            "src.core.als.agents.specialist_base.request_council_decision_for_agent",
            AsyncMock(return_value=uitkomst),
        ):
            reden = await agent._council_rejection("query_hr_database", {"role": "Analyst"})

        assert reden is not None, (
            "De poort liet MODIFIED door. Dan wordt de ONGEWIJZIGDE actie uitgevoerd terwijl "
            "een officier juist om een aanpassing vroeg."
        )
        assert "hitl_required" in reden.lower(), (
            f"Verwacht dat de D4-002-floor MODIFIED optilt naar HITL_REQUIRED voor deze "
            f"Annex III/HITL-piloot (OP-168-vervolg). Kreeg: {reden!r}"
        )
        assert "goedkeuringsticket aangemaakt" in reden.lower(), (
            f"De floor moet een ECHT ticket aanmaken, geen kale afwijzing (AI Act art. 14 -- "
            f"een mens moet de aanpassing kunnen zien en accorderen). Kreeg: {reden!r}"
        )
