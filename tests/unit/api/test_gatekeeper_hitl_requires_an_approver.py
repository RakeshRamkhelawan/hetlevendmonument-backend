"""De HITL-goedkeuringsroute vereist een beheerder en negeert de body-identiteit (OP-43).

**Waarom dit de route is die telt.** OP-31 haalde de klaartekst uit `GET /v1/tools/hitl/audit`,
maar bij het narekenen in ronde 5 bleek `src/core/tool_broker/router.py` nul importeurs te hebben
in `src/`: die endpoints worden niet geserveerd (ADR-036 OP-37). De HITL-routes die de app
DAADWERKELIJK aanbiedt zijn `POST /api/v1/gatekeeper/hitl/approve` en `/reject`, en die hadden nul
auth-dependencies -- `get_current_user` komt nul keer voor in dat bestand.

**Twee gebreken in een endpoint.** Er was geen rolcheck, en de naam van de goedkeurder kwam uit
`request_body.approved_by`. Die waarde gaat in `GovernanceContract.record_hitl_approval()` -- het
veld dat ADR-036 OP-28 registreert als de kern van het art.-14-toezicht. Elke gebruiker met een
geldig tenant-token kon dus elk openstaand ticket goedkeuren EN zelf kiezen welke naam als
goedkeurder werd vastgelegd. Dezelfde klasse als de NOOIT-regel "tenant_id nooit uit de request
body", toegepast op het veld dat moet vastleggen WELKE mens toestemming gaf.

**Het gekozen admin-vocabulaire staat hier vastgepind, met opzet.** Rakesh vond bij de review van
het fixplan ZEVEN admin-checks in DRIE onverenigbare vocabulaires (ADR-036 OP-40): `is_tenant_admin`
en `auth/require_admin` accepteren `{admin, tenantadmin}` plus superuser, vier checks in het
`admin/`-domein accepteren `{admin, system_admin}` maar GEEN superuser, en `api/require_admin_user`
alleen `{admin}` plus superuser. Deze fix consolideert er twee en lost die splitsing NIET op. Om te
voorkomen dat "er is nu een definitie" schijnzekerheid wordt, legt
`test_the_chosen_admin_vocabulary_is_pinned` expliciet vast WELK vocabulaire hier geldt -- zodat een
latere verschuiving een zichtbare testwijziging is en geen stille gedragswijziging.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from src.core.exceptions import register_exception_handlers
from fastapi.testclient import TestClient

TENANT = 5
TICKET = "hitl-ticket-abc123"

#: Wat een aanvrager in de body zet. Mag NOOIT in het governance-contract belanden.
FORGED_APPROVER = "ceo@klant.nl"

#: De geauthenticeerde gebruiker. Dit hoort vastgelegd te worden.
REAL_ADMIN_EMAIL = "beheerder@klant.nl"

#: Wat er sinds OP-55 (ronde 7) als goedkeurder wordt vastgelegd: het onveranderlijke
#: gebruikersnummer uit `_user()`, met `user:`-prefix. Bewust NIET `REAL_ADMIN_EMAIL` -- een
#: gebruiker kan zijn eigen adres wijzigen via `PUT /api/v1/users/me`, dus dat adres is geen
#: bruikbaar art.-14-bewijs.
EXPECTED_APPROVER = "user:42"


class _FakeHitl:
    def __init__(self) -> None:
        self.tenant_id = TENANT
        self.status = "pending"
        self.agent_id = _FakeGatekeeperRepo.agent_id
        self.task_id = "task-1"
        # ADR-036 OP-81: de aanvragende mens. Hier bewust een ANDERE dan `_user()` (id 42), zodat
        # dit bestand blijft toetsen wat het altijd toetste -- de ROL en de herkomst van de
        # goedkeurdersidentiteit -- en niet stilzwijgend op de zelf-goedkeuringscheck stukloopt.
        # DAT die check bestaat wordt bewezen in
        # tests/unit/api/test_gatekeeper_hitl_refuses_self_approval.py.
        self.requested_by_user_id = 999


class _FakeGatekeeperRepo:
    """Legt vast met welke `approved_by`/`rejected_by` de status is bijgewerkt."""

    calls: list[dict[str, Any]] = []
    #: De agent van het ticket; `dunning` is een gewired proces met een eigen goedkeurrecht.
    agent_id = "dunning"

    def __init__(self, db: Any, tenant_id: int) -> None:
        self.tenant_id = tenant_id

    async def get_hitl_by_ticket(self, ticket_ref: str) -> _FakeHitl:
        return _FakeHitl()

    async def update_hitl_status(self, hitl: Any, **kwargs: Any) -> None:
        type(self).calls.append(kwargs)


class _FakeContract:
    approvals: list[dict[str, Any]] = []

    def record_hitl_approval(self, approved_by: str, action: str) -> None:
        type(self).approvals.append({"approved_by": approved_by, "action": action})


class _FakeContractRepo:
    def __init__(self, db: Any, tenant_id: int) -> None:
        pass

    async def load_or_create(self, agent_id: str) -> _FakeContract:
        return _FakeContract()

    async def save(self, contract: Any) -> None:
        return None


pytestmark = pytest.mark.usefixtures("procesrecht_voor_de_beslisser")


def _user(email: str, roles: list[str], is_superuser: bool = False) -> Any:
    """Een gebruikersobject zoals `get_current_user` het teruggeeft."""
    from src.core.api.auth.schemas import UserResponse

    user = UserResponse(
        id=42,
        email=email,
        tenant_id=TENANT,
        roles=roles,
    )
    # `is_superuser` staat niet op het schema maar wordt met `getattr` gelezen; zo doet
    # `is_tenant_admin` het ook.
    object.__setattr__(user, "is_superuser", is_superuser)
    return user


def _client(user: Any, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Een app met alleen de gatekeeper-HITL-router, en `user` als geauthenticeerde gebruiker."""
    from src.core.api.dependencies import get_db
    from src.core.api.v1.gatekeeper import gatekeeper_hitl_router as module
    from src.core.auth.api_deps import get_current_user
    from src.core.middleware.tenant_context import set_tenant_id

    monkeypatch.setattr(module, "GatekeeperRepository", _FakeGatekeeperRepo)
    monkeypatch.setattr(module, "GovernanceContractRepository", _FakeContractRepo)
    set_tenant_id(TENANT)

    app = FastAPI()

    register_exception_handlers(app)
    app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user
    # De CSRF-controle (ADR-036 OP-80) leunt op Redis en op een header die deze tests niet zetten.
    # Hier overschreven zodat ze hun EIGEN eigenschap blijven toetsen; DAT de controle bestaat
    # wordt bewezen door `TestTheGatekeeperApprovalRoutesRequireACsrfToken`, die hem juist NIET
    # overschrijft.
    from src.core.api.auth.dependencies import validate_csrf_token

    app.dependency_overrides[validate_csrf_token] = lambda: None

    _FakeGatekeeperRepo.calls = []
    _FakeContract.approvals = []
    return TestClient(app)


@pytest.mark.unit
class TestAUserWithoutAnApprovalRightCannotApprove:
    def test_approve_is_refused_for_a_user_without_an_approval_right(
        self, monkeypatch: pytest.MonkeyPatch, procesrecht_poort: Callable[[set[str]], None]
    ) -> None:
        """Een gewoon tenant-token is geen goedkeuringsbevoegdheid.

        Zonder deze eis is de HITL-poort een formaliteit: de tool-broker weigert een HIGH-risk
        actie zonder goedgekeurd ticket, en iedereen kan dat ticket zelf goedkeuren.
        """
        procesrecht_poort(set())
        client = _client(_user("gebruiker@klant.nl", roles=["viewer"]), monkeypatch)

        response = client.post(
            "/api/v1/gatekeeper/hitl/approve",
            json={"ticket_ref": TICKET, "approved_by": FORGED_APPROVER},
        )

        assert response.status_code == 403, (
            f"Een gebruiker zonder goedkeurrecht kreeg {response.status_code} op "
            "/hitl/approve. Dan is de HITL-gate uit ADR-015 zelf-goedkeurend."
        )
        assert not _FakeGatekeeperRepo.calls, (
            "De status is bijgewerkt ondanks de weigering -- de check staat na de mutatie."
        )

    def test_reject_is_refused_for_a_user_without_an_approval_right(
        self, monkeypatch: pytest.MonkeyPatch, procesrecht_poort: Callable[[set[str]], None]
    ) -> None:
        """Ook afwijzen is een governance-besluit, niet een gebruikersactie."""
        procesrecht_poort(set())
        client = _client(_user("gebruiker@klant.nl", roles=["viewer"]), monkeypatch)

        response = client.post(
            "/api/v1/gatekeeper/hitl/reject",
            json={
                "ticket_ref": TICKET,
                "rejected_by": FORGED_APPROVER,
                "reason": "Niet nodig volgens mij.",
            },
        )

        assert response.status_code == 403, (
            f"Een gebruiker zonder goedkeurrecht kreeg {response.status_code} op /hitl/reject."
        )
        assert not _FakeGatekeeperRepo.calls


@pytest.mark.unit
class TestTheApproverIdentityComesFromTheToken:
    def test_the_body_approved_by_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """De naam in de body mag het art.-14-bewijs niet bepalen.

        `record_hitl_approval()` legt vast WELKE mens toestemming gaf. Kwam die naam uit de body,
        dan is dat bewijs door de aanvrager zelf gekozen -- en dan bewijst het niets.
        """
        client = _client(_user(REAL_ADMIN_EMAIL, roles=["admin"]), monkeypatch)

        response = client.post(
            "/api/v1/gatekeeper/hitl/approve",
            json={"ticket_ref": TICKET, "approved_by": FORGED_APPROVER},
        )

        assert response.status_code == 200, response.text
        recorded = [call.get("approved_by") for call in _FakeGatekeeperRepo.calls]
        # Sinds OP-55 (ronde 7) is dit het gebruikersNUMMER en niet meer het adres uit het token:
        # dat adres is door de gebruiker zelf te wijzigen. Deze test blijft toetsen wat hij altijd
        # toetste -- dat de BODY het bewijs niet bepaalt -- met de nieuwe, onveranderlijke waarde.
        assert recorded == [EXPECTED_APPROVER], (
            f"De vastgelegde goedkeurder is {recorded}, niet de geauthenticeerde "
            f"{EXPECTED_APPROVER!r}. Zolang de body dit veld bepaalt, kan een aanvrager elke naam "
            "als goedkeurder in de auditketen zetten."
        )
        assert FORGED_APPROVER not in str(_FakeContract.approvals), (
            f"De body-waarde staat in het governance-contract: {_FakeContract.approvals}. Dat is "
            "het veld dat OP-28 registreert als de kern van het art.-14-toezicht."
        )

    def test_the_body_rejected_by_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _client(_user(REAL_ADMIN_EMAIL, roles=["admin"]), monkeypatch)

        response = client.post(
            "/api/v1/gatekeeper/hitl/reject",
            json={
                "ticket_ref": TICKET,
                "rejected_by": FORGED_APPROVER,
                "reason": "Buiten het mandaat van deze agent.",
            },
        )

        assert response.status_code == 200, response.text
        recorded = [call.get("rejected_by") for call in _FakeGatekeeperRepo.calls]
        assert recorded == [EXPECTED_APPROVER], (
            f"De vastgelegde afwijzer is {recorded}, niet de geauthenticeerde gebruiker."
        )


@pytest.mark.unit
class TestWhoMayApproveIsDecidedByTheProcessRight:
    """Wie goedkeurt, volgt uit het recht bij het PROCES van het ticket (ADR-039 F1/F2/F7).

    Dit vervangt `TestTheChosenAdminVocabularyIsPinned` (OP-40/OP-43), die vastpinde dat het
    beheerders-vocabulaire `{admin, system_admin, tenantadmin}` plus superuser mocht goedkeuren.
    Besluit Rakesh 2026-10-09: "een beheerder heeft niets te maken met een proces dat geaccordeerd
    moet worden". De rolnaam in het token doet er nu niet meer toe; het recht komt uit de database
    (`role_permissions`) en hangt aan de agent van het ticket
    (`approval_rights.RECHT_PER_AGENT`, onbekende agent = weigeren). Het recht zelf met
    een echte database: `tests/integration/test_goedkeuren_is_een_procesbevoegdheid.py`.
    """

    @pytest.mark.parametrize(
        ("roles", "is_superuser", "rechten", "agent", "allowed"),
        [
            (["admin"], False, set(), "dunning", False),
            (["system_admin"], False, set(), "dunning", False),
            (["tenantadmin"], False, set(), "dunning", False),
            (["viewer"], True, set(), "dunning", False),  # platform-superuser: F7
            ([], False, set(), "dunning", False),
            (["viewer"], False, {"receivables:approve"}, "dunning", True),
            (["admin"], False, {"receivables:approve"}, "dunning", True),  # een persoon, alle rollen
            (["viewer"], False, {"hr:approve"}, "dunning", False),  # recht van een ander proces
            (["viewer"], False, {"hr:approve"}, "skillsgaptraining", True),
            (["viewer"], False, {"receivables:approve"}, "agent-1", False),  # onbekende agent
        ],
    )
    def test_who_may_approve(
        self,
        roles: list[str],
        is_superuser: bool,
        rechten: set[str],
        agent: str,
        allowed: bool,
        monkeypatch: pytest.MonkeyPatch,
        procesrecht_poort: Callable[[set[str]], None],
    ) -> None:
        procesrecht_poort(rechten)
        client = _client(
            _user("iemand@klant.nl", roles=roles, is_superuser=is_superuser), monkeypatch
        )
        _FakeGatekeeperRepo.agent_id = agent

        try:
            response = client.post(
                "/api/v1/gatekeeper/hitl/approve",
                json={"ticket_ref": TICKET, "approved_by": FORGED_APPROVER},
            )
        finally:
            _FakeGatekeeperRepo.agent_id = "dunning"

        expected = 200 if allowed else 403
        assert response.status_code == expected, (
            f"roles={roles}, is_superuser={is_superuser}, rechten={sorted(rechten)}, agent={agent} "
            f"gaf {response.status_code}, verwacht {expected}. Goedkeuren is een procesbevoegdheid: "
            "alleen een recht in role_permissions bij het proces van het ticket telt, geen rolnaam."
        )


@pytest.mark.unit
class TestTheServedAppActuallyHasTheGuardedRoute:
    """Op de GEASSEMBLEERDE app, niet op de leaf-router.

    Dit is de les uit OP-37: de OP-31-fix was correct maar de onderbouwing niet gemeten, want
    `src/core/tool_broker/router.py` wordt nergens geimporteerd en die endpoints worden dus niet
    geserveerd. Een guard die alleen naar het losse bestand kijkt kan dat niet zien -- en
    `tests/unit/api/test_gatekeeper_router_equivalence.py` kijkt ook alleen naar de sub-routers.
    Deze test bouwt de echte app en toetst wat er daadwerkelijk aan de lijn hangt.
    """

    @staticmethod
    def _routes_by_path() -> dict[str, Any]:
        from fastapi.routing import APIRoute

        from src.main import create_test_app

        app = create_test_app()
        return {route.path: route for route in app.routes if isinstance(route, APIRoute)}

    @staticmethod
    def _dependency_names(route: Any) -> set[str]:
        """Alle dependency-functienamen van een route, recursief."""
        names: set[str] = set()

        def walk(dependant: Any) -> None:
            for sub in getattr(dependant, "dependencies", []):
                call = getattr(sub, "call", None)
                if call is not None:
                    names.add(getattr(call, "__name__", ""))
                walk(sub)

        walk(route.dependant)
        return names

    @pytest.mark.parametrize(
        "path",
        ["/api/v1/gatekeeper/hitl/approve", "/api/v1/gatekeeper/hitl/reject"],
    )
    def test_the_route_is_served_and_carries_authentication(self, path: str) -> None:
        routes = self._routes_by_path()

        assert path in routes, (
            f"{path} bestaat niet in de geassembleerde app. Dan is de rolcheck erop even "
            "onbereikbaar als die op /v1/tools/hitl/audit (OP-37) -- de fix is dan preventief, "
            "niet curatief, en dat hoort te blijken uit een test en niet uit een aanname."
        )

        names = self._dependency_names(routes[path])
        assert "get_current_user" in names, (
            f"{path} heeft geen get_current_user in zijn dependencies (gevonden: {sorted(names)}). "
            "Zonder geauthenticeerde gebruiker kan _require_approver niets toetsen en komt de "
            "identiteit van de goedkeurder weer uit de request body."
        )


@pytest.mark.unit
class TestTheApproverIdentityIsImmutable:
    """Het art.-14-bewijs mag niet uit een veld komen dat de gebruiker zelf kan wijzigen.

    **Gevonden door de blinde security-review in ronde 7 (H4).** OP-43 haalde `approved_by` uit
    `request_body` en verving het door `current_user.email`. Dat is een verbetering -- de AANVRAGER
    kan het niet meer kiezen -- maar het is maar half waar dat de identiteit nu uit authenticatie
    komt: `PUT /api/v1/users/me` (`src/core/api/v1/users/me_router.py:70-79`) laat elke
    geauthenticeerde gebruiker zijn EIGEN e-mailadres op elk nog vrij adres zetten, zonder
    verificatielus en zonder `can_manage_users`-check.

    Exploit die dat oplevert: een tenantbeheerder zet zijn adres op `ceo@klant.nl`, keurt een
    HIGH-risk actie goed, en zet het terug. `hitl_requests.approved_by`, de logregel EN
    `GovernanceContract.record_hitl_approval()` leggen dan de gekozen tekst vast. Dat veld is
    precies wat OP-28 registreert als de kern van het art.-14-toezicht -- en het valt buiten
    `compute_audit_hash`, dus het is zelfgekozen EN niet manipulatiebestendig.

    Daarom nu het onveranderlijke `current_user.id`, met een `user:`-prefix zodat niemand de
    waarde later voor een weergavenaam aanziet. Het patroon bestond al in dezelfde codebase:
    `tool_broker/hitl_repository.py:88-98` slaat `resolved_by=user_id` op.
    """

    def test_the_recorded_approver_is_the_user_id_and_not_the_email(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(_user("admin@tenant.example", ["admin"]), monkeypatch)

        response = client.post(
            "/api/v1/gatekeeper/hitl/approve",
            json={"ticket_ref": TICKET, "approved_by": FORGED_APPROVER},
        )

        assert response.status_code == 200, response.text
        recorded = [call.get("approved_by") for call in _FakeGatekeeperRepo.calls]
        assert recorded == ["user:42"], (
            f"De goedkeurder is vastgelegd als {recorded!r}. Dat moet het onveranderlijke "
            "gebruikersnummer zijn: een e-mailadres kan de gebruiker zelf wijzigen via "
            "PUT /api/v1/users/me, en dan is het art.-14-bewijs zelfgekozen."
        )

    def test_the_governance_contract_also_records_the_user_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(_user("admin@tenant.example", ["admin"]), monkeypatch)

        client.post(
            "/api/v1/gatekeeper/hitl/approve",
            json={"ticket_ref": TICKET, "approved_by": FORGED_APPROVER},
        )

        recorded = [call["approved_by"] for call in _FakeContract.approvals]
        assert recorded == ["user:42"], (
            f"Het governance-contract legt {recorded!r} vast als art.-14-bewijs. Dat moet "
            "hetzelfde onveranderlijke gebruikersnummer zijn als in de HITL-rij, anders wijzen "
            "de twee bewijssporen naar verschillende dingen."
        )

    def test_the_mutable_email_appears_nowhere_in_the_recorded_evidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vangnet: het adres mag ook niet als extra veld meeliften.

        Zonder deze assertie zou "sla ook het e-mailadres op" de twee tests hierboven groen
        houden terwijl de zelfgekozen waarde alsnog in het bewijs staat.
        """
        email = "ceo@klant.example"
        client = _client(_user(email, ["admin"]), monkeypatch)

        client.post(
            "/api/v1/gatekeeper/hitl/approve",
            json={"ticket_ref": TICKET, "approved_by": FORGED_APPROVER},
        )

        rendered = repr(_FakeGatekeeperRepo.calls) + repr(_FakeContract.approvals)
        assert email not in rendered, (
            "Het door de gebruiker zelf instelbare e-mailadres staat in het vastgelegde bewijs. "
            "Leg het gebruikersnummer vast en los de weergavenaam pas bij het LEZEN op."
        )


@pytest.mark.unit
class TestTheGatekeeperApprovalRoutesRequireACsrfToken:
    """Het ZUSTEROPPERVLAK had de CSRF-laag niet (ADR-036 OP-80).

    `POST /api/v1/tools/hitl/{approve,reject}` kreeg die dependency in OP-72 met als reden dat
    `get_current_user` het `access_token`-cookie accepteert: zonder CSRF-controle is een
    cross-site POST alleen afgedekt door `SameSite`, een eigenschap van de browser en geen controle
    van ons. Diezelfde redenering geldt hier woordelijk -- deze twee routes zijn GESERVEERD,
    cookie-geauthenticeerd en veranderen staat. Ze waren de uitzondering gebleven.

    Gemeten met een route-enumeratie op de geassembleerde app: beide routes hadden
    `get_current_user` en `get_db`, geen `validate_csrf_token`.

    **Wat hier NIET bij hoort, en waarom (bijgewerkt 2026-09-09, ADR-036 OP-81 GESLOTEN).** De
    blinde review stelde destijds dat de zelf-goedkeuringscheck uit OP-70 hier verbatim van
    toepassing is. Dat klopte toen niet: `HITLRequestModel` (`governance/models.py`, class rond
    regel 353) had geen veld voor een menselijke aanvrager -- alleen `agent_id` en `task_id` --
    dus een check bouwen op een veld dat er niet was, was schijnzekerheid geweest. Dat is sinds
    OP-81 opgelost: het model draagt nu `requested_by_user_id`, en `approve_hitl`/`reject_hitl`
    passen de check inmiddels toe (getest in
    `tests/unit/api/test_gatekeeper_hitl_refuses_self_approval.py`, een apart bestand). Deze
    CSRF-test blijft ongewijzigd relevant; alleen de aanname over het ONTBREKEN van
    functiescheiding is achterhaald en hier gecorrigeerd.
    """

    def _app_without_csrf_override(self, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        from src.core.api.dependencies import get_db
        from src.core.api.v1.gatekeeper import gatekeeper_hitl_router as module
        from src.core.auth.api_deps import get_current_user
        from src.core.middleware.tenant_context import set_tenant_id

        monkeypatch.setattr(module, "GatekeeperRepository", _FakeGatekeeperRepo)
        monkeypatch.setattr(module, "GovernanceContractRepository", _FakeContractRepo)
        set_tenant_id(TENANT)

        app = FastAPI()

        register_exception_handlers(app)
        app.include_router(module.router)
        app.dependency_overrides[get_db] = lambda: None
        app.dependency_overrides[get_current_user] = lambda: _user(
            "beheerder@klant.nl", roles=["admin"]
        )
        return TestClient(app)

    def test_approve_refuses_a_request_without_a_csrf_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = self._app_without_csrf_override(monkeypatch)

        resp = client.post("/api/v1/gatekeeper/hitl/approve", json={"ticket_ref": "TICKET-CSRF"})

        assert resp.status_code == 403, (
            f"Goedkeuren lukt zonder CSRF-token (status {resp.status_code}). De sessie loopt via "
            "een cookie, dus een andere site kan dit verzoek namens een ingelogde beheerder doen."
        )

    def test_reject_refuses_a_request_without_a_csrf_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = self._app_without_csrf_override(monkeypatch)

        resp = client.post(
            "/api/v1/gatekeeper/hitl/reject",
            json={"ticket_ref": "TICKET-CSRF", "reason": "buiten mandaat van deze agent"},
        )

        assert resp.status_code == 403
