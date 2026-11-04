"""Een goedkeuring geldt voor EEN tool, EEN set parameters, en EEN keer (ADR-036 OP-63/OP-64/OP-65).

**Hoe dit gevonden is.** Twee onafhankelijke, blinde reviewrondes op dag 1 van BE-AGT-045 kwamen
los van elkaar op dezelfde drie bevindingen. De aanleiding is dat dag 1 de goedkeuringslus SLOOT
(OP-37): tot dat moment kon geen enkele route een ticket op `approved` zetten, dus de poort in
`tool_broker/service.py` was fail-closed maar dood. Het commit dat goedkeuren mogelijk maakt is
daarmee ook het commit dat de begrenzing moet regelen.

**Wat er mis was, gemeten en niet beredeneerd:**

1. De poort toetste uitsluitend `status == "approved"`. `git grep "ticket.tool_name"` binnen
   `src/core/tool_broker/` leverde alleen de twee digest-aanroepen in `hitl_router.py` op -- er was
   NERGENS een vergelijking tussen de tool die wordt uitgevoerd en de tool waarvoor is goedgekeurd,
   geen vergelijking van de parameters, en het ticket werd na gebruik niet verbruikt. En
   `ToolRiskClassifier` zet ONBEKENDE tools standaard op HIGH, dus elke niet-geregistreerde tool
   loopt door precies deze poort. Een goedkeuring was dus een permanente volmacht voor de hele
   tenant. (OP-63)

2. `expires_at` werd nergens afgedwongen behalve in een opruimtaak die door geen enkel gedeployed
   proces wordt gestart. `approve` toetste alleen `status != "pending"`, dus een ticket van een jaar
   oud was nog steeds goed te keuren. Een vervaltermijn die alleen door een cron-taak bestaat, is
   geen vervaltermijn. (OP-64)

3. `_BLIJFT` hield `_agent_id` en `_task_id` op grond van hun NAAM. Op het live pad zet
   `create_hitl_request` die twee helemaal niet -- de payload is `{**action_params, ...}` en
   `action_params` is rauwe modeluitvoer. Wat het model onder die namen schrijft, overleefde de
   opruiming permanent. Dat is dezelfde fout als de `ALWAYS_PUBLISHABLE`-naamlijst uit ronde 2 van
   deze sprint, die toen is gesloten door wiring in plaats van namen te gebruiken. (OP-65)

De unit-tests hieronder bewaken de VORM (welke sleutels, welke SQL-voorwaarden). Het GEDRAG --
eenmalig verbruik onder gelijktijdigheid -- hoort op echte Postgres en staat in
`tests/integration/test_hitl_integration.py`.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.tool_broker.hitl_repository import _BLIJFT, HITLTicketRepository


def _compiled_sql(statement: object) -> str:
    """Het statement als SQL-tekst met de waarden INGEVULD.

    Zonder `literal_binds=True` rendert SQLAlchemy elke `literal()` als bindparameter en staan de
    sleutelnamen niet in de tekst -- dan toetst de assertie niets.
    """
    from sqlalchemy.dialects import postgresql

    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _statement_of(db: AsyncMock) -> object:
    assert db.execute.await_args is not None, "er is geen statement uitgevoerd"
    return db.execute.await_args[0][0]


@pytest.mark.unit
class TestAnApprovalIsBoundToOneTool:
    """OP-63 -- de poort mag een goedkeuring niet als volmacht behandelen."""

    @pytest.mark.asyncio
    async def test_redeeming_requires_the_same_tool(self) -> None:
        """De tool waarvoor is goedgekeurd MOET in de WHERE staan.

        Zonder deze voorwaarde is elke goedgekeurde ticketverwijzing bruikbaar voor elke andere
        HIGH-risk tool -- en onbekende tools zijn per definitie HIGH.
        """
        db = AsyncMock()
        db.execute.return_value.rowcount = 1
        repo = HITLTicketRepository(db)

        await repo.redeem(
            "hitl_abc",
            tenant_id=1,
            tool_name="delete_task",
            payload={"task_id": "42"},
        )

        sql = _compiled_sql(_statement_of(db))
        assert "tool_name" in sql, (
            "De UPDATE die een goedkeuring verzilvert toetst de tool niet. Een ticket dat is "
            f"goedgekeurd voor tool A verzilvert dan ook voor tool B. SQL:\n{sql}"
        )

    @pytest.mark.asyncio
    async def test_redeeming_requires_the_same_parameters(self) -> None:
        """Dezelfde tool met ANDERE parameters is een andere handeling.

        Goedkeuren van `delete_task(id=1)` mag `delete_task(id=999)` niet dekken.
        """
        # DE BINDINGEN vergelijken, niet de SQL-tekst (ADR-036 OP-93).
        #
        # De eerste versie van deze test deed `assert sql_one != sql_two`. Die kon NIET falen:
        # `redeem` rendert `resolved_at > <nu met microseconden>` als literal, dus twee aanroepen
        # verschillen altijd -- ook met identieke parameters. Zelf nagemeten na de blinde review:
        # twee IDENTIEKE payloads leverden verschillende SQL. De test beloofde in zijn naam iets
        # wat hij niet toetste, en overleefde het weghalen van de bindingsvoorwaarde uit `redeem`.
        from src.core.tool_broker.redaction import approval_binding

        een = approval_binding("delete_task", {"task_id": "1"}, tenant_id=1)
        ander = approval_binding("delete_task", {"task_id": "999"}, tenant_id=1)

        assert een != ander, (
            "Twee verschillende parametersets leveren dezelfde binding op. Een goedkeuring dekt dan "
            "elke aanroep van diezelfde tool."
        )

        # En die binding MOET in de WHERE van `redeem` staan, anders wordt hij nooit vergeleken.
        db = AsyncMock()
        db.execute.return_value.rowcount = 1
        await HITLTicketRepository(db).redeem(
            "hitl_abc", tenant_id=1, tool_name="delete_task", payload={"task_id": "1"}
        )
        sql = _compiled_sql(_statement_of(db))

        assert een in sql, (
            "De berekende binding komt niet voor in de UPDATE. `redeem` vergelijkt de parameters "
            f"dan niet met wat er is goedgekeurd. SQL: {sql}"
        )

    @pytest.mark.asyncio
    async def test_redeeming_consumes_the_ticket(self) -> None:
        """Een goedkeuring is eenmalig; de status MOET van `approved` af.

        Blijft hij op `approved`, dan is dezelfde verwijzing oneindig herbruikbaar.
        """
        db = AsyncMock()
        db.execute.return_value.rowcount = 1
        repo = HITLTicketRepository(db)

        await repo.redeem("hitl_abc", tenant_id=1, tool_name="t", payload={})

        sql = _compiled_sql(_statement_of(db))
        assert "approved" in sql, f"De WHERE eist geen goedgekeurd ticket. SQL:\n{sql}"
        assert "consumed" in sql, (
            "De UPDATE zet de status niet op `consumed`. Het ticket blijft `approved` en is "
            f"daarmee oneindig opnieuw te gebruiken. SQL:\n{sql}"
        )

    @pytest.mark.asyncio
    async def test_a_second_redemption_reports_failure(self) -> None:
        """Nul geraakte rijen betekent: niet verzilverd. Fail-closed."""
        db = AsyncMock()
        db.execute.return_value.rowcount = 0
        repo = HITLTicketRepository(db)

        allowed = await repo.redeem("hitl_abc", tenant_id=1, tool_name="t", payload={})

        assert allowed is False, (
            "Een UPDATE die nul rijen raakt betekent dat er geen geldige, ongebruikte goedkeuring "
            "was. Dat MOET als geweigerd terugkomen."
        )


@pytest.mark.unit
class TestAnExpiredTicketCannotBeApproved:
    """OP-64 -- de vervaltermijn moet in de beslissing zelf zitten, niet in een cron-taak."""

    @pytest.mark.asyncio
    async def test_approve_filters_on_expiry(self) -> None:
        db = AsyncMock()
        db.execute.return_value.rowcount = 1
        repo = HITLTicketRepository(db)

        await repo.approve("hitl_abc", tenant_id=1, user_id=7)

        sql = _compiled_sql(_statement_of(db))
        assert "expires_at" in sql, (
            "`approve` toetst `expires_at` niet. De enige handhaving van de SLA van 4 uur zit dan "
            "in `cleanup_expired`, en die actor wordt door geen enkel gedeployed proces gestart "
            f"(OP-64). Een ticket van een jaar oud is dan nog steeds goed te keuren. SQL:\n{sql}"
        )

    @pytest.mark.asyncio
    async def test_reject_does_not_filter_on_expiry(self) -> None:
        """Afwijzen van een verlopen aanvraag moet WEL kunnen.

        Anders blijft een verlopen ticket eeuwig `pending` staan met zijn inhoud erin, en is er
        geen enkele weg om het op te ruimen zolang de opruimtaak niet draait.
        """
        db = AsyncMock()
        db.execute.return_value.rowcount = 1
        repo = HITLTicketRepository(db)

        await repo.reject("hitl_abc", tenant_id=1, user_id=7)

        sql = _compiled_sql(_statement_of(db))
        assert "expires_at" not in sql, (
            "`reject` filtert op vervaldatum. Een verlopen aanvraag is dan niet meer af te wijzen "
            f"en houdt zijn inhoud vast. SQL:\n{sql}"
        )


@pytest.mark.unit
class TestNoModelWrittenKeySurvivesResolution:
    """OP-65 -- een sleutel wordt niet vertrouwd om zijn naam."""

    def test_agent_id_and_task_id_are_not_kept(self) -> None:
        """Op het LIVE pad schrijft de broker deze twee niet.

        `create_hitl_request` bouwt de payload als `{**action_params, "_decision_id", "_reason",
        "_requested_by", "_requested_at"}`. `action_params` is `dict(proposal.action_params)` uit
        `copilot/service.py` -- rauwe modeluitvoer. Alles wat NA de spreiding wordt gezet is
        server-geschreven; al het andere niet. `_agent_id` en `_task_id` staan er niet bij.
        """
        assert "_agent_id" not in _BLIJFT, (
            "`_agent_id` wordt bewaard op grond van zijn naam. Op het live pad zet niets die "
            "sleutel, dus wat het model eronder schrijft blijft permanent staan -- en wordt "
            "getoond op /hitl/pending, /hitl/audit en over de websocket. Dat is dezelfde fout als "
            "de ALWAYS_PUBLISHABLE-naamlijst uit ronde 2."
        )
        assert "_task_id" not in _BLIJFT, "Zelfde als `_agent_id`: naam, geen wiring."

    def test_only_server_written_keys_are_kept(self) -> None:
        """Vangnet: de lijst mag alleen de drie sleutels bevatten die de server zelf zet."""
        assert set(_BLIJFT) == {"_decision_id", "_requested_by", "_requested_at"}, (
            f"_BLIJFT is {sorted(_BLIJFT)}. Alleen sleutels die `create_hitl_request` NA de "
            "spreiding van action_params zet, zijn aantoonbaar niet van het model."
        )


@pytest.mark.unit
class TestTheDigestBranchIsActuallyExercised:
    """De tak die in productie draait had nul dekking (reviewbevinding H1, dag 1).

    Gemeten door de reviewer: `if not redacted: return rebuilt` vervangen door `if True: ...` --
    waarmee de digest volledig verdween -- liet 72 tests groen. `redacted_payload_digest` kwam in
    geen enkele unit-test voor, en elke integratietest riep `approve`/`reject` aan ZONDER digest.
    De router geeft er altijd een mee, dus juist de productietak was ongetest.
    """

    def test_the_digest_lands_in_the_statement(self) -> None:
        digest: dict[str, object] = {"command": {"hmac": "deadbeef"}}
        repo = HITLTicketRepository(AsyncMock())

        without_sql, _ = _rendered(repo._resolution_payload(None))
        with_sql, with_values = _rendered(repo._resolution_payload(digest))

        assert without_sql != with_sql, (
            "Met en zonder digest leveren dezelfde expressie op -- de digest wordt niet "
            "weggeschreven. Dit is de tak die in productie draait."
        )
        assert "_redacted_payload" in with_values, (
            f"De digest staat niet onder zijn eigen sleutel. Waarden: {with_values}"
        )
        assert digest in with_values, (
            "De meegegeven digestwaarde komt niet in het statement terecht; er wordt iets anders "
            f"weggeschreven dan wat de router berekende. Waarden: {with_values}"
        )

    def test_without_a_digest_only_the_decision_remains(self) -> None:
        """Verlopen tickets krijgen geen digest: er is nooit een beslissing genomen."""
        repo = HITLTicketRepository(AsyncMock())

        _, values = _rendered(repo._resolution_payload(None))

        assert "_redacted_payload" not in values, (
            f"Een verlopen ticket krijgt een digest van iets dat niemand heeft beoordeeld: {values}"
        )
        for key in _BLIJFT:
            assert key in values, f"`{key}` overleeft de opruiming niet. Waarden: {values}"


def _rendered(expression: Any) -> tuple[str, list[Any]]:
    """De SQL-tekst plus de INGEVULDE waarden, apart.

    Bewust niet `literal_binds=True` zoals elders in deze suite: de digest-tak bevat een
    `cast(dict, JSONB)`, en daar heeft SQLAlchemy geen literal-renderer voor -- de compilatie
    faalt dan met een CompileError en de test meet niets meer. De waarden komen daarom uit
    `compile().params`, wat bovendien een sterkere toets is: het vergelijkt objecten in plaats
    van substrings in SQL-tekst.
    """
    from sqlalchemy.dialects import postgresql

    compiled = expression.compile(dialect=postgresql.dialect())
    return str(compiled), list(compiled.params.values())


@pytest.mark.unit
class TestTheHumanReasonIsKept:
    """Wat de MENS erbij schreef hoort bewaard te blijven (ADR-036 OP-69).

    `ToolHITLRejection.reason` is verplicht met `min_length=10` en `ToolHITLApproval.notes` is
    optioneel. Beide werden gevalideerd en daarna weggegooid, omdat `hitl_tickets` er geen kolom
    voor had -- `hitl_store` las ze met een `getattr` naar een attribuut dat niet bestond, dus het
    antwoord was altijd `None`. Op een endpoint waarvan de hele rechtvaardiging aantoonbaar
    menselijk toezicht is (AI Act art. 14), was de motivering van de mens het enige dat niet werd
    vastgelegd.

    Deze tekst valt bewust BUITEN de pseudonimisering en overleeft de opruiming: hij is door een
    mens geschreven, niet door een model.
    """

    @pytest.mark.asyncio
    async def test_approve_writes_the_note(self) -> None:
        db = AsyncMock()
        db.execute.return_value.rowcount = 1
        repo = HITLTicketRepository(db)

        await repo.approve("hitl_abc", tenant_id=1, user_id=7, note="afgestemd met de teamlead")

        sql = _compiled_sql(_statement_of(db))
        assert "resolution_note" in sql, (
            f"`approve` schrijft de notitie van de goedkeurder niet weg. SQL:\n{sql}"
        )

    @pytest.mark.asyncio
    async def test_reject_writes_the_reason(self) -> None:
        db = AsyncMock()
        db.execute.return_value.rowcount = 1
        repo = HITLTicketRepository(db)

        await repo.reject("hitl_abc", tenant_id=1, user_id=7, note="doelt op productie, niet temp")

        sql = _compiled_sql(_statement_of(db))
        assert "resolution_note" in sql, (
            "`reject` schrijft de opgegeven reden niet weg, terwijl het schema hem VERPLICHT "
            f"stelt met min_length=10. Gevalideerd en dan weggegooid. SQL:\n{sql}"
        )

    def test_the_column_exists_on_the_model(self) -> None:
        """Zonder kolom is doorgeven zinloos, en een `getattr` maakt dat stil."""
        from src.core.tool_broker.models import HITLTicket

        assert "resolution_note" in HITLTicket.__table__.columns, (
            "`hitl_tickets` heeft geen kolom `resolution_note`. Eerder las de store hem met "
            "`getattr(ticket, 'notes', None)` -- dat geeft altijd None terug zonder ooit te falen."
        )


@pytest.mark.unit
class TestTheBindingIsComputedOverTheSameProjectionOnBothSides:
    """De rondgang: goedkeuren en verzilveren moeten op DEZELFDE waarde uitkomen (ADR-036 OP-75).

    **Hoe dit is gevonden, en waarom mijn eigen tests het misten.** De blinde code-review van
    2026-08-06 bouwde een integratietest die een ticket aanmaakt via `create_hitl_request`, hem via
    de router goedkeurt, en daarna `execute_tool(context=...)` aanroept -- de volledige rondgang.
    Uitkomst: `redeem` gaf `False`. Elke menselijke goedkeuring was op het live pad onverzilverbaar.

    De oorzaak: `service.py` zet `payload["tenant_id"]` en `payload["user_id"]` UIT DE
    EXECUTIECONTEXT in de payload, VOORDAT de HITL-poort draait. `approval_binding` sloot alleen
    sleutels met een `_`-prefix uit, dus die twee telden bij uitvoering wel mee en bij goedkeuring
    niet -- want `create_hitl_request` zet ze daar niet.

    Mijn eigen tests konden dit niet zien omdat ze aan BEIDE kanten dezelfde handgemaakte payload
    gebruikten. Een test die zijn eigen invoer aan beide kanten verzint, toetst alleen dat de
    functie deterministisch is.

    Dit is dezelfde klasse fout als OP-63/OP-65: aannemen wat er in een payload staat in plaats van
    het te meten op het pad dat draait.
    """

    TOOL = "local__run_shell"

    def test_the_context_injection_does_not_change_the_binding(self) -> None:
        """De twee sleutels die de broker zelf injecteert horen NIET in de binding.

        Ze komen niet van het model en staan niet in het ticket; ze meetellen maakt de binding
        afhankelijk van iets dat pas bij uitvoering bestaat.
        """
        from src.core.tool_broker.redaction import approval_binding

        zoals_goedgekeurd = {
            "command": "cleanup --dry-run",
            "_decision_id": "d1",
            "_reason": "modeltekst",
            "_requested_by": "7",
            "_requested_at": "t",
        }
        zoals_uitgevoerd = {
            "command": "cleanup --dry-run",
            "_hitl_ticket_ref": "hitl_abc",
            "tenant_id": 1,
            "user_id": 7,
        }

        assert approval_binding(self.TOOL, zoals_goedgekeurd, tenant_id=1) == approval_binding(
            self.TOOL, zoals_uitgevoerd, tenant_id=1
        ), (
            "De binding bij goedkeuren verschilt van die bij uitvoeren. `service.py` zet "
            "`tenant_id` en `user_id` uit de context in de payload voordat de poort draait; staan "
            "die in de binding, dan matcht de UPDATE in `redeem` nul rijen en is ELKE menselijke "
            "goedkeuring onverzilverbaar. De actie blijft dan permanent geblokkeerd -- precies de "
            "toestand die OP-37 zou oplossen, maar dan een laag dieper en stil."
        )

    def test_a_different_parameter_still_breaks_the_binding(self) -> None:
        """Vangnet: alles uitsluiten zou de test hierboven ook groen maken.

        Zonder deze assertie is "sluit elke sleutel uit" een geldige oplossing, en dan dekt een
        goedkeuring weer elke aanroep van dezelfde tool.
        """
        from src.core.tool_broker.redaction import approval_binding

        een = approval_binding(self.TOOL, {"command": "cleanup --dry-run"}, tenant_id=1)
        ander = approval_binding(self.TOOL, {"command": "deploy --force"}, tenant_id=1)

        assert een != ander, (
            "Twee verschillende commando's leveren dezelfde binding op. De goedkeuring is dan niet "
            "aan de parameters gebonden."
        )

    def test_the_excluded_keys_match_what_the_broker_actually_injects(self) -> None:
        """Wiring, geen naamlijst.

        De uitgesloten sleutels moeten exact de sleutels zijn die `execute_tool` zelf uit de
        context in de payload schrijft. Loopt dat uiteen -- iemand voegt daar een derde sleutel toe
        -- dan is de binding weer aan beide kanten anders en breekt het goedkeuren opnieuw, stil.
        """
        import ast
        from pathlib import Path

        from src.core.tool_broker.redaction import BROKER_INJECTED_KEYS

        source = Path("src/core/tool_broker/service.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        injected: set[str] = set()
        for node in ast.walk(tree):
            # Patroon: payload["<naam>"] = context["<naam>"]
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            value = node.value
            if not (isinstance(target, ast.Subscript) and isinstance(value, ast.Subscript)):
                continue
            if not (isinstance(target.value, ast.Name) and target.value.id == "payload"):
                continue
            if not (isinstance(value.value, ast.Name) and value.value.id == "context"):
                continue
            if isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                injected.add(target.slice.value)

        assert injected, (
            "Geen enkele `payload[...] = context[...]`-toewijzing gevonden in service.py. Is het "
            "patroon veranderd? Zolang dit leeg is bewaakt deze test niets."
        )
        assert injected == set(BROKER_INJECTED_KEYS), (
            f"`BROKER_INJECTED_KEYS` is {sorted(BROKER_INJECTED_KEYS)} maar `execute_tool` schrijft "
            f"{sorted(injected)} uit de context in de payload. Die twee MOETEN gelijk zijn: anders "
            "verschilt de binding bij goedkeuren van die bij uitvoeren en is de goedkeuring stil "
            "onverzilverbaar."
        )


@pytest.mark.unit
class TestTheTenantFilterIsPresent:
    """De tenantgrens in de SQL zelf (backend-patterns par. 11).

    **Waarom een VORMtest naast de gedragstest.** De integratietest bewijst dat een andere tenant
    er niet in komt, maar niet WELKE laag dat doet: de tenant zit ook in de domeinscheiding van de
    HMAC, dus de binding matcht al niet. Gemeten door de blinde review van 2026-08-06: het
    `tenant_id`-filter uit de WHERE van `redeem` halen laat de gedragstest GROEN. Dat filter is dus
    verdediging-in-de-diepte, en zonder deze test kan het stil verdwijnen.
    """

    @pytest.mark.asyncio
    async def test_redeem_filters_on_tenant(self) -> None:
        db = AsyncMock()
        db.execute.return_value.rowcount = 1
        repo = HITLTicketRepository(db)

        await repo.redeem("hitl_abc", tenant_id=7, tool_name="t", payload={})

        sql = _compiled_sql(_statement_of(db))
        assert "tenant_id" in sql, (
            "`redeem` filtert niet op tenant. De binding dekt het vandaag af omdat de tenant in de "
            "sleutelafleiding zit, maar dat is EEN laag; deze hoort er ook te zijn. SQL: " + sql
        )

    @pytest.mark.asyncio
    async def test_get_filters_on_tenant(self) -> None:
        """`get()` is het filter waar approve en reject op leunen.

        Beide handlers laden het ticket met `repo.get(ref, tenant_id=...)` en concluderen uit een
        treffer dat het ticket van jouw tenant is. Valt dit filter weg, dan keurt een beheerder van
        tenant A een ticket van tenant B goed -- de ticketverwijzing staat gewoon in API-antwoorden.
        """
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        repo = HITLTicketRepository(db)

        await repo.get("hitl_abc", tenant_id=7)

        sql = _compiled_sql(_statement_of(db))
        # Op de VOORWAARDE met de waarde erin, niet op het woord: `select(HITLTicket)` zet
        # `tenant_id` sowieso in de kolomlijst. De eerste versie van deze assertie overleefde het
        # verwijderen van het filter -- dezelfde holle vorm als eerder bij `status`.
        assert "tenant_id = 7" in sql, (
            "`get` filtert niet op tenant. approve en reject leunen hierop om vast te stellen of "
            "een ticket van jouw organisatie is. SQL: " + sql
        )

    @pytest.mark.asyncio
    async def test_count_by_tenant_filters_on_tenant(self) -> None:
        # MagicMock voor het RESULTAAT, AsyncMock alleen voor `execute`: `scalar_one()` is
        # synchroon, dus een doorgeschoven AsyncMock geeft daar een coroutine terug.
        result = MagicMock()
        result.scalar_one.return_value = 0
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        repo = HITLTicketRepository(db)

        await repo.count_by_tenant(tenant_id=7)

        sql = _compiled_sql(_statement_of(db))
        assert "tenant_id" in sql, (
            "`count_by_tenant` telt over ALLE tenants. Het aantal op /hitl/pending en /hitl/audit "
            "verraadt dan hoeveel HIGH-risk acties een andere organisatie uitvoert. SQL: " + sql
        )

    @pytest.mark.asyncio
    async def test_get_by_tenant_filters_on_tenant_and_status(self) -> None:
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        repo = HITLTicketRepository(db)

        await repo.get_by_tenant(tenant_id=7, status="pending")

        sql = _compiled_sql(_statement_of(db))
        assert "tenant_id = 7" in sql, (
            "`get_by_tenant` filtert niet op tenant. SQL: " + sql
        )
        # Op de VOORWAARDE toetsen, niet op het woord: `select(HITLTicket)` zet `status` sowieso
        # in de kolomlijst, dus `"status" in sql` is altijd waar. Die eerste versie overleefde het
        # verwijderen van het filter -- een holle assertie, precies wat deze reeks moest uitbannen.
        assert "= 'pending'" in sql, (
            "`get_by_tenant` filtert niet op status. /hitl/pending toont dan ook afgehandelde "
            "tickets, inclusief hun onbewerkte tool_input. SQL: " + sql
        )


@pytest.mark.unit
class TestAnApprovalDoesNotStayValidForever:
    """Een goedkeuring veroudert (ADR-036 OP-83).

    `approve` eist sinds OP-64 dat het ticket nog niet verlopen is, maar `redeem` kende GEEN
    tijdsgrens. Een actie die maanden geleden is goedgekeurd bleef dus uitvoerbaar tot de retentie
    de rij verwijdert -- en die retentie draait pas sinds OP-76 uberhaupt ergens naartoe.

    Menselijk toezicht gaat over een beslissing op een MOMENT, met de context van dat moment. Een
    goedkeuring die een jaar later nog geldt is geen toezicht meer.
    """

    @pytest.mark.asyncio
    async def test_redeem_bounds_the_age_of_the_approval(self) -> None:
        db = AsyncMock()
        db.execute.return_value.rowcount = 1
        repo = HITLTicketRepository(db)

        await repo.redeem("hitl_abc", tenant_id=1, tool_name="t", payload={})

        sql = _compiled_sql(_statement_of(db))
        assert "resolved_at" in sql, (
            "`redeem` kent geen tijdsgrens op de goedkeuring zelf. Een maanden oude goedkeuring "
            f"blijft dan verzilverbaar. SQL: {sql}"
        )
