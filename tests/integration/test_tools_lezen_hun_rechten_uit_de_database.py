"""Tools lezen hun rechten uit de DATABASE (`role_permissions`), niet uit een vaste matrix (OP-143).

Tot deze wijziging bestonden er twee rolsystemen naast elkaar. De HTTP-routes lazen
`role_permissions` (via `RBACService` in `services/rbac_service.py`). De SecurityOfficer, die
beslist of een AGENT een tool mag draaien, las `ROLE_PERMISSIONS` in `auth/rbac.py`: een
woordenboek in de code waar de database niets over te zeggen had. Gevolg, gemeten: de rol
`editor` kreeg via de routes `agents:*` en `workflows:*`, en via een agent op elke tool
`MISSING_SCOPE`; een beheerder die een recht uit `role_permissions` haalde, behield het voor
agenten.

**Wat hier echt is.** Postgres (de integratiedatabase), de rollen en rechten zoals de ECHTE zaaier
`RBACService.ensure_default_roles` ze neerzet (niet door deze test verzonnen: dat zou aan beide
kanten van de vergelijking hetzelfde vocabulaire verzinnen), de gebruikers met PRECIES een rol
via `user_roles`, de echte `SecurityOfficer` en de echte `rbac_service.user_has_scope_for`
(die een eigen sessie opent). **Vervangen:** alleen de twee systeemgrenzen die niets met rechten te
doen hebben -- de toollijst van het agentprofiel (`is_allowed`: open, anders zou een VETO uit de
allowlist het antwoord vertroebelen) en de PromptGuard ("geen injectie"). Het antwoord is het
`reason_code` van het echte oordeel: `MISSING_SCOPE` is geweigerd door de rechten, alles anders
heeft de rechtencontrole gepasseerd.

**Tabel per rol (tools voor -> na), `L`=tools:read `S`=tools:write `A`=tools:admin
`P`=receivables:propose:**

    rol          voor (ROLE_PERMISSIONS)   na (role_permissions)   verschil
    admin        L S A P                   L S A P  (via *:*)      geen
    user         L                         L                       geen
    debiteuren   L P                       L P                     geen
    editor       -  (niets)                L                       + L (bewust, enige verruiming)

**Mutatiebewijs (2026-10-09), kopie als terugweg, per element:**

- `tools:read` bij `editor` uit de zaailijst -> ROOD `editor-list_tasks` (+ de architectuurtest);
  `tools:write` bij `user` erbij -> ROOD `user-local__write_file` en
  `test_granting_a_tools_write_row_opens_the_write_tool` (+ architectuurtest); `*:*` bij `admin`
  vervangen door `*:read` -> ROOD drie admin-regels; `receivables:propose` bij `debiteuren` weg
  -> ROOD `debiteuren-send_payment_reminder`.
- `query_hr_database` in `tool_risk_levels.yml` van `tools:admin` naar `tools:read` -> ROOD
  `user-`, `debiteuren-` en `editor-query_hr_database`.
- `_gebruiker_heeft_recht` zonder gebruikerscontrole -> ROOD de gedeactiveerde en de verwijderde
  gebruiker en de gebruiker van klant B met een rol van klant A (3 rood). "Admin van B, gevraagd
  voor A" blijft GROEN omdat de rolfilter van de database-RBAC (`Role.tenant_id`) die weigering
  al levert (twee lagen, een is genoeg om te weigeren).
- Een eigen rol met `*:write` krijgt `tools:write` maar niet `tools:admin`: de tweede verruiming
  naast `editor`, een gevolg van een bron (`test_a_custom_role_with_a_wildcard_row_...`).
- Een typefout (`tools:beheerder`) of een wildcard (`*:*`) in het yml -> ROOD in
  `test_every_required_permission_is_a_real_permission` (architectuurtest); in deze module
  weigert de oordeelroute ze al (`TestEenOnbekendeWaardeWeigert`).
- Legitieme richting (rij erbij of rol ongewijzigd) -> GROEN: 31 passed.

**Rood voor de bouw (gemeten 2026-10-09 op de oude code):** 4 failed, 25 passed --
`editor-list_tasks`, `test_revoking_a_tools_read_row_refuses_the_next_call`,
`test_granting_a_tools_write_row_opens_the_write_tool` en
`test_revoking_the_admin_wildcard_refuses_the_admin`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

TENANT_A = 4451
TENANT_B = 4452

#: Een tool per niveau, allemaal met een regel in `tool_risk_levels.yml`.
LEES_TOOL = "list_tasks"
SCHRIJF_TOOL = "local__write_file"
BEHEER_TOOL = "query_hr_database"
VOORSTEL_TOOL = "send_payment_reminder"

_TOEGESTAAN = {"COMPLIANT", "HIGH_RISK_TOOL"}


async def _sql(query: str, **params: Any) -> Any:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as sessie:
        resultaat = await sessie.execute(text(query), params)
        await sessie.commit()
        return resultaat


@dataclass(frozen=True)
class Omgeving:
    """Per rol een gebruiker met PRECIES die rol, in klant A; plus de randgevallen."""

    per_rol: dict[str, int]
    rol_ids: dict[str, int]
    inactieve_beheerder: int
    verwijderde_beheerder: int
    beheerder_van_b: int


async def _ruim_op() -> None:
    for tenant in (TENANT_A, TENANT_B):
        await _sql(
            "DELETE FROM user_roles WHERE user_id IN (SELECT id FROM users WHERE tenant_id = :t)",
            t=tenant,
        )
        await _sql("DELETE FROM role_permissions WHERE tenant_id = :t", t=tenant)
        await _sql("DELETE FROM roles WHERE tenant_id = :t", t=tenant)
        await _sql("DELETE FROM users WHERE tenant_id = :t", t=tenant)
        await _sql("DELETE FROM tenants WHERE id = :t", t=tenant)


async def _maak_gebruiker(tenant: int, rol_id: int, label: str) -> int:
    resultaat = await _sql(
        "INSERT INTO users (tenant_id, email, hashed_password, is_active) "
        "VALUES (:t, :e, 'x', true) RETURNING id",
        t=tenant,
        e=f"{label}-{uuid.uuid4().hex[:8]}@op143.example.com",
    )
    user_id = int(resultaat.scalar_one())
    await _sql("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)", u=user_id, r=rol_id)
    return user_id


@pytest_asyncio.fixture
async def omgeving() -> AsyncGenerator[Omgeving, None]:
    from src.core.database.database import db_manager
    from src.core.models.rbac_models import Tenant
    from src.core.services.rbac_service import RBACService

    await _ruim_op()
    async with db_manager.get_session() as sessie:
        for tenant in (TENANT_A, TENANT_B):
            sessie.add(Tenant(id=tenant, name=f"OP143 {tenant}", slug=f"op143-{tenant}"))
        await sessie.commit()
    # De ECHTE producent van rollen en rechten.
    for tenant in (TENANT_A, TENANT_B):
        async with db_manager.get_session() as sessie:
            await RBACService(sessie).ensure_default_roles(tenant)

    rij = await _sql(
        "SELECT tenant_id, name, id FROM roles WHERE tenant_id IN (:a, :b)", a=TENANT_A, b=TENANT_B
    )
    ids = {(r.tenant_id, r.name): int(r.id) for r in rij}
    rol_ids = {naam: ids[(TENANT_A, naam)] for naam in ("admin", "user", "debiteuren", "editor")}

    per_rol = {
        naam: await _maak_gebruiker(TENANT_A, rol_id, naam) for naam, rol_id in rol_ids.items()
    }
    inactief = await _maak_gebruiker(TENANT_A, rol_ids["admin"], "inactief")
    await _sql("UPDATE users SET is_active = false WHERE id = :u", u=inactief)
    verwijderd = await _maak_gebruiker(TENANT_A, rol_ids["admin"], "verwijderd")
    await _sql("UPDATE users SET deleted_at = now() WHERE id = :u", u=verwijderd)
    van_b = await _maak_gebruiker(TENANT_B, ids[(TENANT_B, "admin")], "klant-b")

    yield Omgeving(
        per_rol=per_rol,
        rol_ids=rol_ids,
        inactieve_beheerder=inactief,
        verwijderde_beheerder=verwijderd,
        beheerder_van_b=van_b,
    )
    await _ruim_op()


class _ToollijstOpen:
    """Systeemgrens: de toollijst van het agentprofiel. Open, zodat alleen de RECHTEN beslissen."""

    async def is_allowed(self, action_type: str, tenant_id: int, user_id: int) -> bool:
        return True


class _GeenInjectie:
    """Systeemgrens: de PromptGuard, op "geen injectie"."""

    def scan(self, text: str) -> dict[str, object]:
        return {"injection_detected": False, "patterns": []}


async def _oordeel(user_id: int, tenant_id: int, tool: str) -> str:
    """Het `reason_code` van de ECHTE SecurityOfficer met de ECHTE rechtencontrole."""
    from src.core.auth.rbac import rbac_service
    from src.core.copilot.council.members.security_officer import SecurityOfficer
    from src.core.copilot.council.types import (
        DataClassification,
        DeliberationContext,
        Proposal,
        ProposalTrigger,
    )

    voorstel = Proposal(
        tenant_id=tenant_id,
        user_id=user_id,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type=tool,
        action_params={},
        message="Voer de tool uit.",
        reasoning="Een agent vraagt om deze tool namens de gebruiker.",
        data_classification=DataClassification.INTERNAL,
        confidence=0.9,
        model_id="deepseek-chat",
        model_version="v3",
        context_snapshot={},
        proposal_id=uuid.uuid4(),
    )
    context = DeliberationContext(
        tenant_settings={},
        user_preferences={},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=uuid.uuid4(),
    )
    officer = SecurityOfficer(_ToollijstOpen(), _GeenInjectie(), rbac_service)
    return (await officer.deliberate(voorstel, context)).reason_code


# De tabel uit de moduledocstring, als gegevens. Een regel per (rol, niveau).
_VERWACHT: list[tuple[str, str, bool]] = [
    ("admin", LEES_TOOL, True),
    ("admin", SCHRIJF_TOOL, True),
    ("admin", BEHEER_TOOL, True),
    ("admin", VOORSTEL_TOOL, True),
    ("user", LEES_TOOL, True),
    ("user", SCHRIJF_TOOL, False),
    ("user", BEHEER_TOOL, False),
    ("user", VOORSTEL_TOOL, False),
    ("debiteuren", LEES_TOOL, True),
    ("debiteuren", SCHRIJF_TOOL, False),
    ("debiteuren", BEHEER_TOOL, False),
    ("debiteuren", VOORSTEL_TOOL, True),
    ("editor", LEES_TOOL, True),
    ("editor", SCHRIJF_TOOL, False),
    ("editor", BEHEER_TOOL, False),
    ("editor", VOORSTEL_TOOL, False),
]


@pytest.mark.integration
@pytest.mark.asyncio
class TestPerRolPerNiveau:
    @pytest.mark.parametrize(
        "rol,tool,toegestaan", _VERWACHT, ids=[f"{r}-{t}" for r, t, _ in _VERWACHT]
    )
    async def test_the_seeded_role_gets_exactly_this_answer(
        self, omgeving: Omgeving, rol: str, tool: str, toegestaan: bool
    ) -> None:
        reden = await _oordeel(omgeving.per_rol[rol], TENANT_A, tool)

        assert (reden in _TOEGESTAAN) is toegestaan, (
            f"rol {rol!r} op {tool!r}: reason_code={reden!r}, verwacht "
            f"{'toegestaan' if toegestaan else 'MISSING_SCOPE'}"
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeDatabaseBeslist:
    async def test_revoking_a_tools_read_row_refuses_the_next_call(
        self, omgeving: Omgeving
    ) -> None:
        """Het hart van OP-143: wat in `role_permissions` verdwijnt, verdwijnt ook voor agenten."""
        voor = await _oordeel(omgeving.per_rol["user"], TENANT_A, LEES_TOOL)
        await _sql(
            "DELETE FROM role_permissions WHERE role_id = :r AND resource = 'tools' "
            "AND action = 'read'",
            r=omgeving.rol_ids["user"],
        )
        na = await _oordeel(omgeving.per_rol["user"], TENANT_A, LEES_TOOL)

        assert (voor in _TOEGESTAAN, na) == (True, "MISSING_SCOPE")

    async def test_granting_a_tools_write_row_opens_the_write_tool(
        self, omgeving: Omgeving
    ) -> None:
        """De andere richting: een rij die erbij komt opent het recht ('weiger alles' is geen oplossing)."""
        voor = await _oordeel(omgeving.per_rol["user"], TENANT_A, SCHRIJF_TOOL)
        await _sql(
            "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
            "VALUES (:r, :t, 'tools', 'write')",
            r=omgeving.rol_ids["user"],
            t=TENANT_A,
        )
        na = await _oordeel(omgeving.per_rol["user"], TENANT_A, SCHRIJF_TOOL)

        assert (voor, na in _TOEGESTAAN) == ("MISSING_SCOPE", True)

    async def test_a_custom_role_with_a_wildcard_row_gets_the_matching_tool_rights(
        self, omgeving: Omgeving
    ) -> None:
        """Gevolg van EEN bron: een eigen rol met `*:write` krijgt ook `tools:write` (OP-143).

        Voorheen kreeg een zelfgemaakte rol nooit toolrechten, ook niet met een jokerrij; de
        oude matrix kende alleen vaste namen. Dit is de tweede verruiming naast `editor`, en ze
        volgt uit de keuze dat de database beslist: dezelfde jokerregel als de HTTP-routes.
        Vastgelegd zodat niemand haar later per ongeluk wegneemt of verder opent: `tools:admin`
        blijft dicht.
        """
        resultaat = await _sql(
            "INSERT INTO roles (tenant_id, name, is_active) VALUES (:t, 'eigen-schrijver', true) "
            "RETURNING id",
            t=TENANT_A,
        )
        rol_id = int(resultaat.scalar_one())
        await _sql(
            "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
            "VALUES (:r, :t, '*', 'write')",
            r=rol_id,
            t=TENANT_A,
        )
        gebruiker = await _maak_gebruiker(TENANT_A, rol_id, "eigen")

        schrijf = await _oordeel(gebruiker, TENANT_A, SCHRIJF_TOOL)
        beheer = await _oordeel(gebruiker, TENANT_A, BEHEER_TOOL)

        assert (schrijf in _TOEGESTAAN, beheer) == (True, "MISSING_SCOPE")

    async def test_revoking_the_admin_wildcard_refuses_the_admin(self, omgeving: Omgeving) -> None:
        await _sql(
            "DELETE FROM role_permissions WHERE role_id = :r AND resource = '*' AND action = '*'",
            r=omgeving.rol_ids["admin"],
        )

        assert await _oordeel(omgeving.per_rol["admin"], TENANT_A, BEHEER_TOOL) == "MISSING_SCOPE"


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeGebruikerTelt:
    """De rechtencontrole kijkt ook naar de GEBRUIKER en naar de rol, niet alleen naar rijen."""

    async def test_an_inactive_user_with_a_valid_role_is_refused(self, omgeving: Omgeving) -> None:
        reden = await _oordeel(omgeving.inactieve_beheerder, TENANT_A, LEES_TOOL)

        assert reden == "MISSING_SCOPE"

    async def test_a_deleted_user_with_a_valid_role_is_refused(self, omgeving: Omgeving) -> None:
        reden = await _oordeel(omgeving.verwijderde_beheerder, TENANT_A, LEES_TOOL)

        assert reden == "MISSING_SCOPE"

    async def test_a_user_of_another_tenant_is_refused(self, omgeving: Omgeving) -> None:
        reden = await _oordeel(omgeving.beheerder_van_b, TENANT_A, LEES_TOOL)

        assert reden == "MISSING_SCOPE"

    async def test_a_user_of_tenant_b_cannot_be_linked_to_a_role_of_tenant_a(
        self, omgeving: Omgeving
    ) -> None:
        """De gekruiste koppeling bestaat niet meer: de DATABASE weigert hem (f75e35a6, OP-190 deel 2).

        Hier stond een test die zo'n rij aanmaakte en dan vroeg of de GEBRUIKERScontrole hem weigerde. Sinds
        `fk_user_roles_role_tenant` kan de rij er niet in (ForeignKeyViolation, gemeten 2026-10-26), dus die
        route naar de gebruikerscontrole is dicht. Wat deze test nu bewijst is sterker: de gekruiste koppeling
        is onmogelijk, en er blijft niets achter. Of de gebruikerscontrole zelf nog een eigen toets heeft
        zonder deze situatie is NIET vastgesteld.
        """
        resultaat = await _sql(
            "INSERT INTO users (tenant_id, email, hashed_password, is_active) "
            "VALUES (:t, :e, 'x', true) RETURNING id",
            t=TENANT_B,
            e=f"gekruist-{uuid.uuid4().hex[:8]}@op143.example.com",
        )
        gekruist = int(resultaat.scalar_one())

        with pytest.raises(IntegrityError, match="fk_user_roles_role_tenant"):
            await _sql(
                "INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)",
                u=gekruist,
                r=omgeving.rol_ids["admin"],
            )

        aantal = await _sql("SELECT count(*) FROM user_roles WHERE user_id = :u", u=gekruist)
        assert aantal.scalar_one() == 0

    async def test_the_same_user_is_allowed_in_his_own_tenant(self, omgeving: Omgeving) -> None:
        """De helft die voorkomt dat 'weiger alles' hierboven een geldige oplossing is."""
        reden = await _oordeel(omgeving.beheerder_van_b, TENANT_B, LEES_TOOL)

        assert reden in _TOEGESTAAN

    async def test_a_deactivated_role_stops_the_access(self, omgeving: Omgeving) -> None:
        await _sql("UPDATE roles SET is_active = false WHERE id = :r", r=omgeving.rol_ids["admin"])

        assert await _oordeel(omgeving.per_rol["admin"], TENANT_A, LEES_TOOL) == "MISSING_SCOPE"


@pytest.mark.integration
@pytest.mark.asyncio
class TestEenOnbekendeWaardeWeigert:
    """Een typefout of wildcard in `tool_risk_levels.yml` mag nooit een tool openzetten."""

    @pytest.mark.parametrize("waarde", ["bestaat_niet", "tools:bestaat_niet", "*:*", "tools:*", ""])
    async def test_an_unknown_or_wildcard_value_refuses_even_the_admin(
        self, omgeving: Omgeving, waarde: str
    ) -> None:
        with patch(
            "src.core.tool_broker.risk_classifier.ToolRiskClassifier.required_permission",
            return_value=waarde,
        ):
            reden = await _oordeel(omgeving.per_rol["admin"], TENANT_A, BEHEER_TOOL)

        assert reden == "MISSING_SCOPE"
