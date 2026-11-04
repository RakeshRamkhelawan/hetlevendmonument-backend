"""De eerste tool die echt resolvet: `query_hr_database` (BE-AGT-044, ADR-036 D10 stap 3).

Tot vandaag was geen van de 27 in de manifesten gedeclareerde tools uitvoerbaar (BE-AGT-039
F1). Deze tool haalt de eerste regel uit `KNOWN_UNRESOLVED_BROKER_TOOLS` en bewijst de keten
end-to-end.

**Waarom deze tool tellingen teruggeeft en geen personen.** Alles wat een tool retourneert
gaat de event bus op (`tool_broker/service.py::_publish_tool_event`) en wordt door het
leersubsysteem gepersisteerd (`events/handlers/learning_event_handler._record_tool_event`
schrijft `observation_data` inclusief het volledige `result`). Rij-data zou dus
persoonsgegevens in een leeropslag zetten -- dezelfde klasse als de audit-keten-bevinding uit
de Gate 2-review van BE-AGT-042, via een kanaal waar niemand naar had gekeken. Zie OP-27.

**Waarom de expliciete tenantfilter niet stil kan verdwijnen.** De ADR-004-hook
`do_orm_execute` filtert elke ORM-query mee, dus een runtime-test alleen zou groen blijven
nadat de eigen `WHERE tenant_id` uit de registry is gehaald. Een eerdere opzet zette die hook
daarom uit met `TenantFilterBypass`; dat is teruggedraaid na de Gate 2-review (MEDIUM-4),
omdat het de hook uitschakelde in een venster waarin ook sessies worden opgezet en bij elke
routineuze leesactie een WARNING "tenant filter DISABLED" produceerde -- een detectiesignaal
tot ruis gedegradeerd. In plaats daarvan toetst `TestTheQueryItself` de GECOMPILEERDE SQL op
beide tenant-predicaten, en blijft de hook als tweede laag gewoon aan staan.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

TOOL = "query_hr_database"


@pytest.fixture(autouse=True)
def _allow_all_tools() -> Iterator[None]:
    """De permissielaag is hier niet het onderwerp; die heeft eigen tests."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


async def _seed(session: AsyncSession, tenant_id: int, slug: str, roles: dict[str, int]) -> None:
    """Zet een tenant neer met per rolnaam het gevraagde aantal actieve gebruikers."""
    from src.core.models.rbac_models import Role, Tenant, User

    session.add(Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug))
    await session.flush()

    for role_name, count in roles.items():
        role = Role(tenant_id=tenant_id, name=role_name)
        session.add(role)
        await session.flush()
        for index in range(count):
            user = User(
                tenant_id=tenant_id,
                email=f"{slug}-{role_name}-{index}@example.test",
                hashed_password="x",
                is_active=True,
            )
            user.roles.append(role)
            session.add(user)
    await session.commit()


def _registry() -> Any:
    from src.core.tool_broker.hr_registry import HRToolRegistry

    return HRToolRegistry()


def _broker() -> Any:
    from src.core.tool_broker.service import ToolBrokerService

    return ToolBrokerService(
        serena_client=None,  # type: ignore[arg-type]
        seq_thinking_client=None,  # type: ignore[arg-type]
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestToolResolves:
    async def test_broker_executes_the_tool_instead_of_rejecting_the_category(
        self, db_session: AsyncSession
    ) -> None:
        """De broker voert de tool uit; tot nu toe wees hij de categorie af.

        Dit is de kern van D10 stap 3: van 27 gedeclareerde tools resolvet er nul. Getoetst op
        `execute_tool` en niet op de registry zelf -- de laag eronder testen bewijst niets over
        het pad dat een skill werkelijk aflegt. Die les kostte bij BE-AGT-042 een hele
        hersteldag.
        """
        from src.core.tool_broker.exceptions import ToolExecutionException

        await _seed(db_session, 1, "alpha", {"Engineer": 2})

        try:
            result = await _broker().execute_tool(
                tool_name=TOOL,
                payload={},
                agent_id="skillsgaptraining",
                timeout_seconds=30,
                context={"tenant_id": 1},
            )
        except ToolExecutionException as exc:
            pytest.fail(
                f"execute_tool weigerde de tool: {exc}. Zolang dit 'Unknown tool category' "
                "geeft, is query_hr_database alleen een naam in een manifest."
            )

        assert result["success"] is True
        assert result["roles"][0]["user_count"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
class TestTenantIsolation:
    async def test_counts_never_include_another_tenant(self, db_session: AsyncSession) -> None:
        """Tenant A telt geen gebruiker van tenant B (backend-patterns par. 11)."""
        await _seed(db_session, 1, "alpha", {"Finance Analyst": 3})
        await _seed(db_session, 2, "beta", {"Finance Analyst": 7})

        result = await _registry().execute_hr_tool(TOOL, {}, tenant_id=1)

        assert result["success"] is True
        by_role = {row["role"]: row for row in result["roles"]}
        assert by_role["Finance Analyst"]["user_count"] == 3, (
            "De telling bevat gebruikers van een andere tenant. Dat is een datalek over "
            "tenantgrenzen heen, niet alleen een verkeerd getal."
        )

    async def test_model_cannot_choose_the_tenant_via_the_payload(
        self, db_session: AsyncSession
    ) -> None:
        """De payload is modeloutput en mag de tenant nooit bepalen.

        `execute_tool` overschreef `payload["tenant_id"]` met de context, maar `context` is een
        OPTIONELE parameter: bleef hij weg, dan overleefde de door het model gekozen tenant tot
        in de WHERE-clause. Geen enkele live aanroeper deed dat, maar een invariant die op
        gewoonte rust is geen invariant (Gate 2-review HIGH-4). De tenant komt nu als expliciet
        argument uit de context en de payload-sleutel wordt eruit gefilterd.
        """
        from src.core.tool_broker.exceptions import ToolExecutionException

        await _seed(db_session, 1, "alpha", {"Engineer": 2})
        await _seed(db_session, 2, "beta", {"Engineer": 9})

        with pytest.raises(ToolExecutionException):
            await _broker().execute_tool(
                tool_name=TOOL,
                payload={"tenant_id": 2},
                agent_id="skillsgaptraining",
                timeout_seconds=30,
                context=None,
            )

    async def test_payload_tenant_id_is_stripped_before_the_registry(
        self, db_session: AsyncSession
    ) -> None:
        """Ook mét context mag een payload-tenant de scope niet verbreden."""
        await _seed(db_session, 1, "alpha", {"Engineer": 2})
        await _seed(db_session, 2, "beta", {"Engineer": 9})

        result = await _broker().execute_tool(
            tool_name=TOOL,
            payload={"tenant_id": 2},
            agent_id="skillsgaptraining",
            timeout_seconds=30,
            context={"tenant_id": 1},
        )

        by_role = {row["role"]: row for row in result["roles"]}
        assert by_role["Engineer"]["user_count"] == 2


@pytest.mark.unit
class TestTheQueryItself:
    def test_both_tenant_predicates_are_in_the_compiled_sql(self) -> None:
        """De expliciete tenantgrens staat op BEIDE tabellen en kan niet stil verdwijnen.

        Op de gecompileerde SQL getoetst en niet op het runtime-resultaat: de ADR-004-hook
        filtert namelijk mee, dus een runtime-test zou groen blijven nadat deze filter is
        weggehaald. `user_roles` heeft zelf geen tenantkolom, dus zonder de filter op BEIDE
        kanten zou een vervuilde associatierij gebruikers van een andere tenant meetellen.
        """
        statement = _registry()._build_statement(7, 50, 0, None)
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))

        assert "roles.tenant_id = 7" in sql
        assert "users.tenant_id = 7" in sql
        assert (
            "users.deleted_at IS NULL" in sql
        ), "Wie op grond van AVG art. 17 is gewist, mag niet meer meetellen."


@pytest.mark.unit
@pytest.mark.asyncio
class TestErasedUsersAreNotCounted:
    async def test_soft_deleted_user_is_excluded(self, db_session: AsyncSession) -> None:
        """Een op AVG art. 17 gewiste gebruiker telt niet meer mee.

        `dsar_service` voert die wissing uit als soft delete met een respijtperiode
        (`is_active=False`, `deleted_at` gezet). Zonder filter zou een ex-medewerker die om
        verwijdering vroeg de telling blijven ophogen -- en dat getal belandt in de leeropslag.
        """
        from src.core.models.rbac_models import Role, Tenant, User

        db_session.add(Tenant(id=1, name="Alpha", slug="alpha"))
        await db_session.flush()
        role = Role(tenant_id=1, name="Engineer")
        db_session.add(role)
        await db_session.flush()

        active = User(tenant_id=1, email="a@x.test", hashed_password="x", is_active=True)
        erased = User(
            tenant_id=1,
            email="b@x.test",
            hashed_password="x",
            is_active=False,
            deleted_at=datetime.now(timezone.utc),
        )
        for member in (active, erased):
            member.roles.append(role)
            db_session.add(member)
        await db_session.commit()

        result = await _registry().execute_hr_tool(TOOL, {}, tenant_id=1)

        assert result["roles"][0]["user_count"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestUnsupportedFiltersFailLoudly:
    async def test_department_filter_is_refused(self, db_session: AsyncSession) -> None:
        """`department` bestaat niet in het datamodel en mag NOOIT stil genegeerd worden.

        Een genegeerd filter levert meer terug dan gevraagd terwijl de aanroeper denkt dat er
        gefilterd is. Voor een adviserende skill die op die uitvoer een advies baseert, is dat
        een stille onwaarheid -- exact de klasse fouten die deze ADR blootlegt.
        """
        await _seed(db_session, 1, "alpha", {"Engineer": 2})

        result = await _registry().execute_hr_tool(TOOL, {"department": "Finance"}, tenant_id=1)

        assert result["success"] is False
        assert "department" in result["error"].lower()
        assert "roles" not in result, "bij een geweigerd filter hoort geen data terug te komen"

    async def test_employee_id_filter_is_refused(self, db_session: AsyncSession) -> None:
        """`employee_id` slaat op rij-data, en die geeft deze tool bewust niet terug."""
        await _seed(db_session, 1, "alpha", {"Engineer": 2})

        result = await _registry().execute_hr_tool(TOOL, {"employee_id": "42"}, tenant_id=1)

        assert result["success"] is False
        assert "employee_id" in result["error"].lower()

    @pytest.mark.parametrize("bad_role", [{"$ne": None}, ["a", "b"], 42, "x" * 51])
    async def test_non_string_role_filter_is_refused(
        self, db_session: AsyncSession, bad_role: Any
    ) -> None:
        """Een `role` die geen korte string is, mag niet stil nul resultaten opleveren.

        `str()` op een dict of lijst geeft een repr die nergens op matcht. De tool zou dan een
        lege lijst teruggeven en de skill zou concluderen dat die rol niet bestaat -- dezelfde
        stille onwaarheid die hierboven voor `department` juist wordt geweigerd
        (Gate 2-review MEDIUM-3).
        """
        await _seed(db_session, 1, "alpha", {"Engineer": 2})

        result = await _registry().execute_hr_tool(TOOL, {"role": bad_role}, tenant_id=1)

        assert result["success"] is False
        assert "role" in result["error"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
class TestNoPersonalDataLeavesTheTool:
    async def test_response_contains_no_personal_data(self, db_session: AsyncSession) -> None:
        """Geen e-mailadres, geen gebruikers-id, geen wachtwoordhash, geen betaal-id.

        Niet alleen hygiene: de respons wordt op de event bus gepubliceerd en door het
        leersubsysteem gepersisteerd. Wat hier uit komt, staat straks in een leeropslag.
        """
        await _seed(db_session, 1, "alpha", {"Engineer": 2})

        result = await _registry().execute_hr_tool(TOOL, {}, tenant_id=1)
        rendered = str(result)

        for forbidden in ("@example.test", "hashed_password", "stripe", "email"):
            assert forbidden not in rendered, (
                f"'{forbidden}' staat in de toolrespons. Die respons gaat de event bus op en "
                "wordt gepersisteerd door het leersubsysteem; persoonsgegevens horen daar niet."
            )

    def test_unsupported_payload_keys_are_redacted_before_publication(self) -> None:
        """De payload gaat geredigeerd de event bus op, niet verbatim.

        De payload is de `json.loads` van een TOOL_CALL-directive en dus modeloutput. Ook een
        sleutel die deze tool WEIGERT -- `employee_id` bijvoorbeeld -- draagt zijn waarde nog
        steeds, en die zou verbatim in de event bus, de leeropslag en de auditketen belanden.
        Geredigeerd en niet weggelaten, zodat de auditregel laat zien DAT er iets is meegestuurd
        (Gate 2-review HIGH-1).
        """
        from src.core.tool_broker.redaction import redact_for_publication

        redacted = redact_for_publication(
            TOOL,
            {
                "role": "Engineer",
                "limit": 10,
                "tenant_id": 1,
                "employee_id": "jan.jansen@acme.nl",
                "department": "salaris 82000",
            },
            # Verplichte parameter sinds ronde 2: de scope komt uit de executiecontext en
            # nooit uit de payload -- die is modeloutput (ADR-036 OP-27, HIGH-1).
            tenant_id=1,
            broker_keys=frozenset({"tenant_id"}),
        )

        # `role` is sinds ronde 3 GEDIGEST: een rolnaam en een persoonsnaam zijn qua vorm
        # niet te onderscheiden, dus vrije tekst blijft niet leesbaar. Alleen opsombare
        # vormen (hier: de paginering) passeren ongehinderd.
        assert "hmac" in redacted["role"]
        assert redacted["limit"] == 10
        # Sinds OP-27 een keyed digest en geen marker: een marker sloopt de
        # AI-Act-art.-12(2)-traceerbaarheid, een digest bewaart de koppeling.
        assert "hmac" in redacted["employee_id"]
        assert "hmac" in redacted["department"]
        assert "jan.jansen@acme.nl" not in str(redacted)
        assert "82000" not in str(redacted)


@pytest.mark.unit
@pytest.mark.asyncio
class TestFailuresAreReportedAsFailures:
    async def test_broker_does_not_publish_a_refusal_as_success(
        self, db_session: AsyncSession
    ) -> None:
        """Een tool die `success: false` teruggeeft, mag niet als geslaagd worden gepubliceerd.

        Anders leert het leersubsysteem dat een geweigerde aanroep een goed patroon is, en legt
        de ADR-019 hash-keten een onwaar record vast dat wel geldig geketend is
        (Gate 2-review HIGH-2).
        """
        from unittest.mock import MagicMock

        await _seed(db_session, 1, "alpha", {"Engineer": 2})

        broker = _broker()
        publisher = MagicMock()
        captured: list[dict[str, Any]] = []
        broker._publish_tool_event = lambda **kwargs: captured.append(kwargs)  # type: ignore[method-assign]
        broker.event_publisher = publisher

        result = await broker.execute_tool(
            tool_name=TOOL,
            payload={"department": "Finance"},
            agent_id="skillsgaptraining",
            timeout_seconds=30,
            context={"tenant_id": 1},
        )

        assert result["success"] is False
        assert captured, "er is geen event gepubliceerd"
        event = captured[0]
        assert event["success"] is False
        assert event["event_type"] == "tool.failed"
        assert event["publish_result"] is None, (
            "een mislukt resultaat hoort niet als output vastgelegd"
        )
        # OP-29: het gepubliceerde veld is sinds deze bevinding een digest, geen leesbare tekst
        # -- "department" mag er dus NIET meer letterlijk in staan, terwijl er wel iets vast
        # moet liggen (een verdwenen foutmelding zou net zo goed een stille bug kunnen zijn).
        assert event["publish_error"] is not None, "de weigeringsreden ontbreekt in het event"
        assert "department" not in str(event["publish_error"]), (
            "de weigeringsreden staat nog leesbaar in het event; hij hoort een digest te zijn"
        )

    async def test_error_path_also_publishes_a_redacted_payload(
        self, db_session: AsyncSession
    ) -> None:
        """Ook als de aanroep afbreekt, gaat de payload geredigeerd de sinks in.

        De redactie zat eerst alleen op het succespad, zodat de modeloutput juist bij een fout
        alsnog verbatim naar de event bus, de leeropslag en de auditketen ging (Gate 2-review
        BE-AGT-044, HIGH-A). Deze test loopt dat pad en controleert wat er gepubliceerd wordt.

        **De foutoorzaak is gewijzigd, het onderwerp niet.** Eerder brak deze test af op een
        ontbrekende tenant-context. Sinds BE-AGT-045 ronde 2 wordt de tenant centraal en VOOR de
        `try` bepaald: zonder tenant is er geen pseudonimiseringsscope en dus ook geen
        tenant-gescopeerd event of auditregel, en dan is niets publiceren het juiste gedrag --
        net als bij een geweigerde permissie. Die weigering raakt de except-takken dus niet
        meer. De fout wordt nu binnen de `try` geforceerd, zodat exact de tak wordt gelopen waar
        deze test over gaat.
        """
        from src.core.tool_broker.exceptions import ToolExecutionException

        await _seed(db_session, 1, "alpha", {"Engineer": 1})

        broker = _broker()
        captured: list[dict[str, Any]] = []
        broker._publish_tool_event = lambda **kwargs: captured.append(kwargs)  # type: ignore[method-assign]

        async def _boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("registry onderuit")

        broker.hr_registry.execute_hr_tool = _boom  # type: ignore[method-assign]

        with pytest.raises(ToolExecutionException):
            await broker.execute_tool(
                tool_name=TOOL,
                payload={"employee_id": "jan.jansen@acme.nl", "note": "salaris 82000"},
                agent_id="skillsgaptraining",
                timeout_seconds=30,
                context={"tenant_id": 1},
            )

        assert captured, "de fouttak publiceert geen event"
        published = str(captured[0]["publish_payload"])
        assert "jan.jansen@acme.nl" not in published
        assert "82000" not in published
        assert "hmac" in published, "de niet-beoordeelde waarden horen een digest te zijn"

    async def test_database_error_is_logged_and_not_handed_to_the_model(
        self, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
    ) -> None:
        """De exceptietekst van SQLAlchemy mag de LLM-context niet in.

        `StatementError.__str__` plakt de SQL EN de gebonden parameters aan de melding. Die
        string zou anders in de LLM-context, op de event bus, in de leeropslag en in de
        auditketen belanden (Gate 2-review HIGH-3). En de fout hoort zichtbaar te zijn voor een
        beheerder, wat hij eerder niet was: er werd niets gelogd.
        """
        from contextlib import asynccontextmanager

        from sqlalchemy.exc import OperationalError

        from src.core.tool_broker.hr_registry import HRToolRegistry

        boom = OperationalError(
            "SELECT secret_column FROM roles", {"param_1": "geheim"}, Exception()
        )

        class _ExplodingSession:
            async def execute(self, *args: Any, **kwargs: Any) -> Any:
                raise boom

        @asynccontextmanager
        async def _factory() -> AsyncIterator[Any]:
            yield _ExplodingSession()

        # Bewust op de databaseaanroep en niet op `_build_statement`: dat laatste draait
        # expres BUITEN de try, zodat een programmeerfout doorslaat naar de broker in plaats
        # van als "queryfout" te worden weggemoffeld.
        registry = HRToolRegistry(session_factory=_factory)

        with caplog.at_level(logging.ERROR):
            result = await registry.execute_hr_tool(TOOL, {}, tenant_id=1)

        assert result["success"] is False
        assert "secret_column" not in result["error"]
        assert "geheim" not in result["error"]
        assert "query_hr_database failed" in caplog.text, (
            "Een databasefout moet zichtbaar zijn voor een beheerder; eerder werd er niets "
            "gelogd (backend-patterns par. 10)."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestPagination:
    async def test_limit_is_honoured_and_truncated_is_reported(
        self, db_session: AsyncSession
    ) -> None:
        """`limit` begrenst het aantal rollen en `truncated` meldt eerlijk dat er meer is."""
        await _seed(db_session, 1, "alpha", {f"Role {index}": 1 for index in range(5)})

        result = await _registry().execute_hr_tool(TOOL, {"limit": 2}, tenant_id=1)

        assert result["role_count"] == 2
        assert len(result["roles"]) == 2
        assert result["truncated"] is True, (
            "Er zijn meer rollen dan teruggegeven, maar de tool meldt dat niet. Dan denkt de "
            "aanroeper dat hij alles heeft gezien."
        )

    async def test_limit_above_the_maximum_is_capped(self, db_session: AsyncSession) -> None:
        """Boven 1000 wordt afgekapt (backend-patterns par. 5)."""
        await _seed(db_session, 1, "alpha", {"Engineer": 1})

        result = await _registry().execute_hr_tool(TOOL, {"limit": 99999}, tenant_id=1)

        assert result["success"] is True
        assert result["applied_limit"] == 1000

    async def test_absurd_offset_is_capped(self, db_session: AsyncSession) -> None:
        """Een offset die de kolombreedte overschrijdt, mag geen driverfout veroorzaken."""
        await _seed(db_session, 1, "alpha", {"Engineer": 1})

        result = await _registry().execute_hr_tool(TOOL, {"offset": 10**20}, tenant_id=1)

        assert result["success"] is True
        assert result["applied_offset"] == 100_000

    @pytest.mark.parametrize(
        ("field", "value"), [("limit", "abc"), ("limit", None), ("offset", -1), ("offset", 1.5)]
    )
    async def test_unreadable_pagination_is_refused_not_silently_corrected(
        self, db_session: AsyncSession, field: str, value: Any
    ) -> None:
        """Een onleesbare `limit`/`offset` wordt geweigerd, niet stil vervangen.

        Deze module weigert `department` en een niet-string `role` juist expliciet omdat stil
        corrigeren de aanroeper laat denken dat zijn invoer is opgevolgd. Dat argument geldt
        net zo goed voor paginering (Gate 2-review BE-AGT-044, LOW-A). Afkappen boven het
        maximum blijft wel toegestaan: die correctie is zichtbaar via `applied_limit`.
        """
        await _seed(db_session, 1, "alpha", {"Engineer": 1})

        result = await _registry().execute_hr_tool(TOOL, {field: value}, tenant_id=1)

        assert result["success"] is False
        assert field in result["error"]


@pytest.mark.unit
class TestRiskClassification:
    def test_read_tool_does_not_land_in_the_hitl_gate(self) -> None:
        """Een leesactie hoort niet op een mens te wachten.

        De classifier valt voor onbekende tools terug op HIGH (zero-trust), en alleen HIGH
        opent de HITL-poort (`service.py`). MEDIUM is de classificatie uit de ADR-036
        onderzoekssynthese ("alias of query_database with PII pre-check") en betekent loggen
        plus een melding achteraf -- passend voor een leesactie op personeelsdata.
        """
        from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel

        assert ToolRiskClassifier().classify(TOOL) is ToolRiskLevel.MEDIUM
