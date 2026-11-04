"""`schedule_training` -- de eerste SCHRIJFtool van de HR-registry (2026-09-21).

**Waarom hij bestaat.** De acceptatiemeting (`scripts/acceptance_thread.py`) loopt van vraag tot
besluit en staat op stap 2 van 7. Stap 6 vraagt een schrijfactie met een risicoklasse; twee
leestools leveren per definitie nooit een besluit op. Dit is de handeling waar een gap-analyse
toe leidt: de aanbevolen training aan een medewerker toewijzen.

**Waarom een EIGEN testbestand en niet onderaan `test_hr_registry.py`.** Dat bestand heeft een
autouse-fixture die `ToolPermissionManager.is_tool_allowed` patcht. Voor de leestools is dat
terecht (de permissielaag heeft eigen tests), maar deze tool is HIGH en zijn hele bestaansrecht
is dat er iets tussen zit. Een assertie over die tool in een bestand waar de permissiecontrole
is uitgezet, is precies de holle vorm die `.claude/rules/quality-gates.md` beschrijft onder "DE
TESTOPSTELLING ZET UIT WAT JE MEET".

**Hier staat geen patch OP DE PERMISSIELAAG.** Dat is een nauwkeuriger zin dan "hier staat geen
enkele patch", die er eerst stond: `tests/unit/tool_broker/conftest.py` legt wel drie
autouse-fixtures op dit bestand (`prana_guard`, `council_gate`,
`_deterministic_pseudonymisation_key`). Geen ervan raakt `_schedule_training` -- nagelopen, en
het mutatiebewijs toont het empirisch: elke mutatie in de tool wordt hier rood. Een lezer die de
oude zin natrok vond wel patches en wist dan niet meer wat de zin waard was. (Gate 2,
2026-09-21.)
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Deze import staat op MODULENIVEAU, en dat is geen slordigheid. De fixture `async_engine`
# (`tests/fixtures/database.py:124`) doet `create_all` over de metadata zoals die op DAT moment
# is, en importeert daarvoor zelf een VASTE lijst modelmodules waarin de HR-modellen niet
# voorkomen. Zonder deze regel bestaat de tabel `skills` niet en faalt `trainings` op zijn
# foreign key -- maar alleen wanneer dit bestand LOS draait, want in een volledige suite heeft
# een ander testbestand ze toevallig al geimporteerd. Gemeten 2026-09-21:
# `NoReferencedTableError: Foreign key associated with column 'trainings.skill_id' could not
# find table 'skills'`. Een test die alleen samen met de rest groen is, meet niet wat hij zegt.
#
# `import_all_models` en niet de twee modules apart: dat is de kanonieke plek in dit project
# (`src/core/database/import_all_models.py`, bewaakt door
# `tests/architecture/test_import_all_models_coverage.py`), dus deze regel rot niet dicht zodra
# er een derde modelmodule bijkomt. (Gate 2, 2026-09-21, LOW-2.)
import src.core.database.import_all_models  # noqa: F401

SCHEDULE = "schedule_training"
#: De logger van de module onder test. De logassertie hieronder filtert hierop: `caplog.records`
#: bevat ook aiosqlite-records met de proefdata erin.
_REGISTRY_LOGGER = "src.core.tool_broker.hr_registry"
READ_TOOL = "query_hr_database"
TRAINING = "Veilig werken met AI"


async def _seed(session: AsyncSession, tenant_id: int, slug: str) -> str:
    """Een tenant met EEN actieve medewerker. Geeft het e-mailadres terug."""
    from src.core.models.rbac_models import Role, Tenant, User

    session.add(Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug))
    await session.flush()
    role = Role(tenant_id=tenant_id, name="Engineer")
    session.add(role)
    await session.flush()
    email = f"{slug}-engineer@example.test"
    user = User(tenant_id=tenant_id, email=email, hashed_password="x", is_active=True)
    user.roles.append(role)
    session.add(user)
    await session.commit()
    return email


async def _seed_training(session: AsyncSession, tenant_id: int, naam: str = TRAINING) -> None:
    """Zet EEN training in de catalogus van deze tenant."""
    from src.core.models.hr_training_models import Training

    session.add(Training(tenant_id=tenant_id, name=naam))
    await session.commit()


def _registry(session_factory: Any | None = None) -> Any:
    from src.core.tool_broker.hr_registry import HRToolRegistry

    return HRToolRegistry(session_factory)


class _TellendeFabriek:
    """Een sessiefabriek die de BESTAANDE testsessie teruggeeft en commits/rollbacks telt.

    Geen mock van de database: de echte sessie doet het echte werk, alleen `commit` en
    `rollback` worden geteld voordat ze worden doorgegeven. Zonder deze telling kan geen
    assertie onderscheiden of de tool zelf commit of dat de fabriek dat voor hem doet -- zie de
    toelichting bij `test_the_tool_commits_itself_and_does_not_lean_on_its_factory`.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.commits = 0
        self.rollbacks = 0

    def __call__(self) -> _TellendeFabriek:
        return self

    async def __aenter__(self) -> Any:
        fabriek = self

        class _Gemeten:
            def __getattr__(self, naam: str) -> Any:
                return getattr(fabriek._session, naam)

            async def commit(self) -> None:
                fabriek.commits += 1
                await fabriek._session.commit()

            async def rollback(self) -> None:
                fabriek.rollbacks += 1
                await fabriek._session.rollback()

        return _Gemeten()

    async def __aexit__(self, *_: object) -> None:
        """Bewust GEEN commit. Dat is het hele punt: de tool moet het zelf doen."""
        return None


async def _rijen(session: AsyncSession) -> list[Any]:
    from src.core.models.hr_training_models import EmployeeTraining

    result = await session.execute(select(EmployeeTraining))
    return list(result.scalars().all())


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleTrainingWrites:
    async def test_the_assignment_is_actually_persisted(self, db_session: AsyncSession) -> None:
        """Niet de returnwaarde toetsen maar de TABEL.

        `inserted=1` is wat de code beweert; een rij in `employee_trainings` is wat er is
        gebeurd. Een schrijftool die niets schrijft en `success` meldt is de faalvorm die
        ADR-036 paragraaf 1 beschrijft -- dan ziet elke test, elk log en elk dashboard er
        hetzelfde uit als bij werkende code.
        """
        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)

        result = await _registry().execute_hr_tool(
            SCHEDULE, {"user_email": email, "training_name": TRAINING}, tenant_id=1
        )

        assert result["success"] is True, result
        assert result["assigned"] == 1

        rijen = await _rijen(db_session)
        assert len(rijen) == 1, (
            "De tool meldde succes maar er staat geen rij in `employee_trainings`. Dat is geen "
            "verkeerd getal maar een tool die niets doet en dat als werk rapporteert."
        )
        assert rijen[0].status == "assigned"
        assert rijen[0].tenant_id == 1

    async def test_a_second_call_updates_instead_of_duplicating(
        self, db_session: AsyncSession
    ) -> None:
        """Dezelfde toewijzing tweemaal geeft een bijwerking, geen tweede rij.

        De tweede aanroep zette eerst `status="completed"` -- dat kan niet meer, zie
        `TestScheduleTrainingOnlyAssigns`. Wat blijft is wat deze test hoort te meten: de
        upsert maakt geen duplicaat.
        """
        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)
        basis = {"user_email": email, "training_name": TRAINING}

        eerste = await _registry().execute_hr_tool(SCHEDULE, dict(basis), tenant_id=1)
        tweede = await _registry().execute_hr_tool(SCHEDULE, dict(basis), tenant_id=1)

        assert eerste["success"] is True, eerste
        assert tweede["success"] is True, tweede
        assert tweede["updated"] == 1
        assert tweede["assigned"] == 0
        rijen = await _rijen(db_session)
        assert len(rijen) == 1
        assert rijen[0].status == "assigned"

    async def test_the_tool_commits_itself_and_does_not_lean_on_its_factory(
        self, db_session: AsyncSession
    ) -> None:
        """De tool commit ZELF; hij vertrouwt niet op het gedrag van zijn sessiefabriek.

        `db_manager.get_session()` commit bij het verlaten van het blok, dus zonder eigen commit
        werkt de standaardweg toch. Een ingespoten fabriek -- tests, en elke toekomstige
        aanroeper die zijn eigen sessie meegeeft -- hoeft dat niet te doen, en dan schrijft een
        schrijftool niets terwijl hij succes meldt.

        **Waarom dit op de AANROEP toetst en niet op de database.** De unit-fixture gebruikt
        SQLite met een `StaticPool`: alle sessies delen EEN verbinding, dus een niet-gecommitte
        rij is ook zichtbaar voor een "verse" sessie. Op die opstelling kan geen enkele assertie
        over de tabel onderscheid maken tussen wel en niet committen -- de bewering zou groen
        staan om de verkeerde reden. Vandaar een fabriek die meetelt wat de tool doet.
        """
        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)
        fabriek = _TellendeFabriek(db_session)

        result = await _registry(fabriek).execute_hr_tool(
            SCHEDULE, {"user_email": email, "training_name": TRAINING}, tenant_id=1
        )

        assert result["success"] is True, result
        assert fabriek.commits == 1, (
            "De tool heeft niet zelf gecommit. Met de standaardfabriek valt dat niet op, want "
            "die commit bij het verlaten van het blok -- met een ingespoten sessie schrijft de "
            "tool dan niets en meldt toch succes."
        )
        assert fabriek.rollbacks == 0

    async def test_a_refused_row_is_rolled_back_instead_of_committed(
        self, db_session: AsyncSession
    ) -> None:
        """Faalt de rij, dan wordt er teruggedraaid -- niet gecommit.

        De standaardfabriek commit bij het verlaten van het blok. Zonder expliciete rollback zou
        een rij die per ongeluk toch in de sessie staat meeliften op een aanroep die als MISLUKT
        wordt gerapporteerd: succes en mislukking in dezelfde transactie.
        """
        email = await _seed(db_session, 1, "alpha")  # geen training in de catalogus
        fabriek = _TellendeFabriek(db_session)

        result = await _registry(fabriek).execute_hr_tool(
            SCHEDULE, {"user_email": email, "training_name": "Bestaat niet"}, tenant_id=1
        )

        assert result["success"] is False
        assert fabriek.rollbacks == 1, "Een mislukte aanroep is niet teruggedraaid."
        assert fabriek.commits == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleTrainingTenantIsolation:
    async def test_a_training_of_another_tenant_cannot_be_assigned(
        self, db_session: AsyncSession
    ) -> None:
        """De training bestaat -- bij tenant 2. Tenant 1 mag hem niet toewijzen.

        De isolatietest die backend-patterns paragraaf 11 voor elke nieuwe repository-methode
        eist, hier op het TOOLpad: de catalogus van een andere tenant blijft onbereikbaar, ook
        als het model de exacte naam kent.
        """
        email = await _seed(db_session, 1, "alpha")
        await _seed(db_session, 2, "beta")
        await _seed_training(db_session, 2, "Cursus van de buren")

        result = await _registry().execute_hr_tool(
            SCHEDULE,
            {"user_email": email, "training_name": "Cursus van de buren"},
            tenant_id=1,
        )

        assert result["success"] is False
        assert not await _rijen(db_session), (
            "Er is een toewijzing vastgelegd op een training van een andere tenant."
        )

    async def test_an_employee_of_another_tenant_cannot_be_assigned(
        self, db_session: AsyncSession
    ) -> None:
        """Andersom: de training is van ons, de medewerker niet."""
        await _seed(db_session, 1, "alpha")
        vreemd_email = await _seed(db_session, 2, "beta")
        await _seed_training(db_session, 1)

        result = await _registry().execute_hr_tool(
            SCHEDULE, {"user_email": vreemd_email, "training_name": TRAINING}, tenant_id=1
        )

        assert result["success"] is False
        assert not await _rijen(db_session)


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleTrainingRefusesLoudly:
    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"user_email": "alpha-engineer@example.test"},
            {"training_name": TRAINING},
            {"user_email": "   ", "training_name": TRAINING},
            {"user_email": "alpha-engineer@example.test", "training_name": 42},
            {"user_email": "alpha-engineer@example.test", "training_name": TRAINING, "status": ""},
        ],
    )
    async def test_an_unusable_field_is_refused_and_nothing_is_written(
        self, db_session: AsyncSession, payload: dict[str, Any]
    ) -> None:
        """Een onbruikbaar veld wordt geweigerd, niet stil aangevuld.

        Dezelfde regel als bij `_read_bounded_int`: stil corrigeren laat de aanroeper denken dat
        zijn invoer is opgevolgd. Bij een schrijftool is dat erger dan bij een leestool -- dan
        staat er een rij die niemand bedoeld heeft.
        """
        await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)

        result = await _registry().execute_hr_tool(SCHEDULE, payload, tenant_id=1)

        assert result["success"] is False
        assert "moet een niet-lege tekst zijn" in result["error"]
        assert not await _rijen(db_session)

    async def test_an_unknown_status_is_refused_with_the_allowed_value(
        self, db_session: AsyncSession
    ) -> None:
        """De toegestane waarde staat in de melding -- een constante uit onze eigen code."""
        from src.core.tool_broker.hr_registry import TOEGESTANE_SCHEDULE_STATUS

        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)

        result = await _registry().execute_hr_tool(
            SCHEDULE,
            {"user_email": email, "training_name": TRAINING, "status": "afgerond"},
            tenant_id=1,
        )

        assert result["success"] is False
        assert TOEGESTANE_SCHEDULE_STATUS in result["error"]
        assert not await _rijen(db_session)

    @pytest.mark.parametrize("veld", ["user_email", "training_name", "status"])
    async def test_a_value_longer_than_its_column_is_refused(
        self, db_session: AsyncSession, veld: str
    ) -> None:
        """Langer dan de kolom kan niets matchen -- en hoort er ook niet in te gaan.

        Zonder grens gaat de volledige, door het model gekozen waarde wel als gebonden parameter
        naar de database en via de melding naar het logbestand.

        **De lengtes komen uit de MODELLEN, niet uit de tool.** De eerste versie van deze test
        gebruikte 321 tekens omdat de tool 320 als grens noemde -- en die grens was verzonnen:
        `User.email` is `String(255)`. Het venster 256-320 passeerde dus ongehinderd terwijl de
        testnaam beloofde dat het werd geweigerd. Een Gate 2-reviewer heeft dat nagemeten. Nu
        leest de test de echte kolombreedte en toetst hij op grens+1, dus hij kan niet opnieuw
        naast het venster vallen.
        """
        from src.core.models.hr_training_models import EmployeeTraining, Training
        from src.core.models.rbac_models import User

        kolommen = {
            "user_email": User.__table__.c.email.type.length,
            "training_name": Training.__table__.c.name.type.length,
            "status": EmployeeTraining.__table__.c.status.type.length,
        }
        waarde = "a" * (int(kolommen[veld]) + 1)
        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)
        payload = {"user_email": email, "training_name": TRAINING, veld: waarde}

        result = await _registry().execute_hr_tool(SCHEDULE, payload, tenant_id=1)

        assert result["success"] is False
        assert "maximaal" in result["error"]
        assert not await _rijen(db_session)


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleTrainingNeverEchoesModelText:
    async def test_a_failed_assignment_does_not_repeat_the_payload(
        self, db_session: AsyncSession
    ) -> None:
        """De foutmelding citeert niets uit de payload -- die gaat de leeropslag in.

        `upsert_employee_trainings` zet de ontvangen naam WEL in zijn melding, en dat is daar
        terecht: daar komt hij uit een bestand dat een mens heeft geupload. Op dit pad komt hij
        uit een `TOOL_CALL`-directive, dus uit het model, en het resultaat van een tool wordt
        door `learning_event_handler._record_tool_event` in `observation_data` gepersisteerd.
        Een model dat een persoonsgegeven in `training_name` zet, zou het zo in een onuitwisbare
        opslag krijgen (OP-27).
        """
        email = await _seed(db_session, 1, "alpha")

        smokkel = "Jan Jansen salaris 82000"
        result = await _registry().execute_hr_tool(
            SCHEDULE, {"user_email": email, "training_name": smokkel}, tenant_id=1
        )

        assert result["success"] is False
        assert smokkel not in str(result), (
            "De payload wordt teruggeciteerd in het antwoord. Dat antwoord gaat de event bus op "
            "en wordt in de leeropslag vastgelegd."
        )
        assert "Jansen" not in str(result)

    async def test_the_email_is_never_in_the_answer(self, db_session: AsyncSession) -> None:
        """Ook niet bij SUCCES. De aanroeper kent het adres al; de leeropslag hoeft het niet."""
        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)

        result = await _registry().execute_hr_tool(
            SCHEDULE, {"user_email": email, "training_name": TRAINING}, tenant_id=1
        )

        assert result["success"] is True, result
        assert email not in str(result)


@pytest.mark.unit
class TestScheduleTrainingIsGoverned:
    def test_the_write_tool_lands_in_the_hitl_gate(self) -> None:
        """HIGH, en expliciet -- niet via de zero-trust default.

        Twee dingen apart: `classify()` moet HIGH zeggen (anders opent de HITL-poort niet), en
        de naam moet een EIGEN regel hebben. Zonder die tweede assertie hangt het antwoord aan
        `default_risk_level`, en die kan iemand later verlagen zonder deze tool te bekijken --
        de vorm die `test_every_executable_tool_has_a_risk_level.py` beschrijft.
        """
        from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel

        classifier = ToolRiskClassifier()

        assert classifier.classify(SCHEDULE) is ToolRiskLevel.HIGH
        assert SCHEDULE in classifier._risk_levels

    def test_writing_is_never_looser_than_reading_the_same_data(self) -> None:
        """Het vereiste recht is minstens zo streng als dat van de leestools.

        Hier stond `write` -- meegeschreven toen `schedule_training` nog alleen een naam in een
        manifest was -- terwijl `query_hr_database` `admin` (nu `tools:admin`, OP-143) eist. Wie de bezetting niet mag
        opvragen, hoort niet via een agent een training te kunnen toewijzen.
        """
        from pathlib import Path

        import yaml

        config = yaml.safe_load(
            Path("src/core/config/tool_risk_levels.yml").read_text(encoding="utf-8")
        )["tool_required_permission"]

        # Sinds de HR-pilot (2026-10-10) leest `hr_medewerker` met `hr:read`; toewijzen blijft
        # `tools:admin` en dus strenger dan lezen. Losser dan lezen mag het nooit worden.
        assert (config[SCHEDULE], config[READ_TOOL]) == ("tools:admin", "hr:read"), (
            f"schedule_training eist '{config.get(SCHEDULE)}' en query_hr_database "
            f"'{config.get(READ_TOOL)}'. Een schrijfactie op personeelsdata mag nooit losser "
            "zijn dan het lezen ervan."
        )

    def test_the_payload_policy_keeps_the_email_out_of_the_log(self) -> None:
        """De redactielaag mag `user_email` nooit leesbaar vastleggen.

        Het antwoord van de tool bevat het adres niet (zie de tests hierboven), maar de PAYLOAD
        wordt apart vastgelegd. Zonder een expliciete regel valt een tool op een LEGE policy --
        dan wordt alles gedigest, wat veilig is maar niet toetsbaar vastgelegd. Deze assertie
        legt vast welke drie velden het vocabulaire zijn en dat alleen `status` leesbaar blijft.
        """
        from src.core.tool_broker.redaction import PAYLOAD_POLICY

        policy = PAYLOAD_POLICY[SCHEDULE]

        assert policy.params == frozenset({"user_email", "training_name", "status"})
        assert set(policy.readable) == {"status"}, (
            "Alleen `status` mag leesbaar blijven: dat is een opgesomde verzameling met een "
            "bron van waarheid. Een e-mailadres en een cursusnaam zijn dat niet."
        )

    def test_the_vocabulary_has_one_source(self) -> None:
        """De registry en de redactielaag noemen dezelfde drie velden.

        Twee lijsten met hetzelfde doel lopen uit elkaar. `_SCHEDULE_FIELDS` bepaalt wat de
        tool ACCEPTEERT, `PAYLOAD_POLICY[...].params` wat er leesbaar mag worden vastgelegd;
        raken die twee uit de pas, dan wordt een echt veld gedigest of een fantoomveld
        leesbaar.
        """
        from src.core.tool_broker.hr_registry import _SCHEDULE_FIELDS
        from src.core.tool_broker.redaction import PAYLOAD_POLICY

        assert _SCHEDULE_FIELDS == PAYLOAD_POLICY[SCHEDULE].params


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleTrainingOnlyAssigns:
    """De tool plant IN; hij legt geen voortgang of afronding vast.

    `EMPLOYEE_TRAINING_STATUSES` kent er drie en het model kiest de waarde vrij. Vastleggen dat
    iemand een training heeft AFGEROND is een bewering over de werkelijkheid waarvoor deze tool
    geen bewijs heeft, hij is via een tweede aanroep weer uit te wissen (`EmployeeTraining` houdt
    geen historie), en het is Annex III punt 4-data. De HITL-poort is daar geen verdediging
    tegen: de goedkeurder leest de toolnaam "schedule_training", niet de statuswaarde.
    (Gate 2-review 2026-09-21, MEDIUM-3.)
    """

    @pytest.mark.parametrize("status", ["completed", "in_progress"])
    async def test_a_status_other_than_assigned_is_refused(
        self, db_session: AsyncSession, status: str
    ) -> None:
        from src.core.models.hr_training_models import EMPLOYEE_TRAINING_STATUSES

        assert status in EMPLOYEE_TRAINING_STATUSES, (
            "Deze test is alleen zinvol voor een status die de TABEL toestaat: het punt is dat "
            "de tool nauwer is dan de tabel, niet dat hij onzin weigert."
        )
        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)

        result = await _registry().execute_hr_tool(
            SCHEDULE,
            {"user_email": email, "training_name": TRAINING, "status": status},
            tenant_id=1,
        )

        assert result["success"] is False
        assert not await _rijen(db_session), (
            f"Er is een rij met status {status!r} vastgelegd. Deze tool heet 'inplannen' en "
            "mag geen afronding of voortgang beweren."
        )

    async def test_the_written_row_is_always_assigned(self, db_session: AsyncSession) -> None:
        """De tegenrichting: het legitieme geval schrijft wel, en met de juiste status."""
        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)

        result = await _registry().execute_hr_tool(
            SCHEDULE, {"user_email": email, "training_name": TRAINING}, tenant_id=1
        )

        assert result["success"] is True, result
        rijen = await _rijen(db_session)
        assert len(rijen) == 1
        assert rijen[0].status == "assigned"


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleTrainingRefusesUnknownFields:
    """Een sleutel buiten het vocabulaire wordt geweigerd, niet genegeerd.

    Het leespad weigert `role`/`department`/`employee_id` luid, met als argument dat stil
    negeren de aanroeper laat denken dat zijn invoer is opgevolgd. Op een SCHRIJFpad weegt dat
    zwaarder: de oude evaluatieset stuurde letterlijk `{"training": ..., "participants": 3}`.
    Stil negeren levert EEN rij op terwijl het model rapporteert dat er drie mensen zijn
    ingeschreven. (Gate 2-review 2026-09-21, MEDIUM-3 / LOW-5.)
    """

    async def test_an_unknown_field_is_refused_and_nothing_is_written(
        self, db_session: AsyncSession
    ) -> None:
        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)

        result = await _registry().execute_hr_tool(
            SCHEDULE,
            {"user_email": email, "training_name": TRAINING, "participants": 3},
            tenant_id=1,
        )

        assert result["success"] is False
        assert "participants" in result["error"], (
            "De naam van het onbekende veld hoort in de melding: dat is een SLEUTEL, en het "
            "model moet kunnen zien welk veld de tool niet kent."
        )
        assert not await _rijen(db_session)

    async def test_the_fields_the_broker_injects_are_not_unknown(
        self, db_session: AsyncSession
    ) -> None:
        """De tegenrichting, en de belangrijkste: de weigering mag de ECHTE weg niet breken.

        De broker injecteert ELKE sleutel uit `BROKER_INJECTED_KEYS` in de payload
        (`service.py:190-195`) en filtert er daarna alleen `tenant_id` weer uit. De eerste versie
        van deze test somde twee namen op -- dezelfde twee die de productiecode opsomde -- en
        miste daarmee `user_id`. Gemeten in Gate 2: op het goedkeuringspad kwam de tool aan met
        `user_id` erbij en weigerde hij, NADAT `redeem_approval` het ticket op `consumed` had
        gezet. De menselijke goedkeuring was verbruikt en niet herhaalbaar; er was geen enkel pad
        waarop deze tool kon slagen.

        Deze versie leest de verzameling uit de BRON, dus hij kan niet opnieuw uit de pas lopen
        met wat de broker werkelijk injecteert.
        """
        from src.core.tool_broker.redaction import BROKER_INJECTED_KEYS

        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)
        payload: dict[str, object] = {
            "user_email": email,
            "training_name": TRAINING,
            # Servermetadata met een `_`-prefix, zelfde conventie als `approval_binding`.
            "_hitl_ticket_ref": "ticket-1",
            "_decision_id": "d-1",
        }
        # Exact wat de broker uit de executiecontext toevoegt -- afgeleid, niet opgesomd.
        for sleutel in sorted(BROKER_INJECTED_KEYS):
            payload[sleutel] = 1
        assert "user_id" in payload, (
            "BROKER_INJECTED_KEYS bevat `user_id` niet meer. Dan meet deze test de fout niet "
            "meer die hem heeft opgeleverd -- kijk of `service.py` nog steeds injecteert."
        )

        result = await _registry().execute_hr_tool(SCHEDULE, payload, tenant_id=1)

        assert result["success"] is True, result
        assert len(await _rijen(db_session)) == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleTrainingFailsSafely:
    async def test_a_database_failure_leaks_neither_the_email_nor_the_sql(
        self, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
    ) -> None:
        """De faalroute was ONGETEST (Gate 2, MEDIUM-5), en de invariant is niet klein.

        `StatementError.__str__` plakt de SQL EN de gebonden parameters aan zijn tekst -- hier
        dus het e-mailadres. Zou `error_detail` die tekst doorgeven, dan haalt elke andere test
        in dit bestand het nog, en staat het adres in de leeropslag.
        """
        import logging

        from sqlalchemy.exc import OperationalError

        from src.core.tool_broker.exceptions import ToolExecutionException

        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)


        class _KapotteFabriek(_TellendeFabriek):
            async def __aenter__(self) -> Any:
                sessie = await super().__aenter__()

                class _Kapot:
                    def __getattr__(self, naam: str) -> Any:
                        return getattr(sessie, naam)

                    async def execute(self, *a: object, **k: object) -> Any:
                        raise OperationalError(
                            f"SELECT users.email FROM users WHERE email = '{email}'",
                            {"email_1": email},
                            Exception("verbinding weg"),
                        )

                return _Kapot()

        with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
            with pytest.raises(ToolExecutionException) as gevangen:
                await _registry(_KapotteFabriek(db_session)).execute_hr_tool(
                    SCHEDULE, {"user_email": email, "training_name": TRAINING}, tenant_id=1
                )

        boodschap = str(gevangen.value)
        assert email not in boodschap, (
            "Het e-mailadres staat in de foutmelding. Die melding gaat de event bus op en "
            "wordt in de leeropslag vastgelegd."
        )
        assert "SELECT" not in boodschap.upper()

        # De VIERDE sink, en die was ongedekt. Gemeten in Gate 2 ronde 2: `logger.error(..., exc)`
        # zette `str(exc)` in de boodschap, en dat is bij SQLAlchemy de SQL PLUS de gebonden
        # parameters -- dus het e-mailadres leesbaar in het logbestand, terwijl de redactielaag
        # en het antwoord het er juist uit houden. De testnaam beloofde meer dan hij meette.
        # ALLEEN de records van deze module. `caplog.records` bevat ook die van aiosqlite, en
        # die dragen de INSERT van de proefdata met het adres erin -- dat is de testopstelling,
        # niet de tool. Zonder deze filter meet de assertie zijn eigen seeding.
        eigen = [r for r in caplog.records if r.name == _REGISTRY_LOGGER]
        assert eigen, "De module heeft niets gelogd; dan meet deze assertie niets."
        gelogd = " ".join(r.getMessage() for r in eigen)
        assert email not in gelogd, (
            "Het e-mailadres staat in het LOGBESTAND. `str(exc)` van een SQLAlchemy-fout draagt "
            "de gebonden parameters mee; log het type en laat de traceback aan `exc_info`."
        )
        assert "SELECT" not in gelogd.upper()

    async def test_the_log_line_cannot_be_split_by_the_model(
        self, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Modeltekst in het log staat op EEN regel.

        Gemeten in Gate 2 op 2026-09-21: een trainingsnaam met een regeleinde leverde EEN
        logrecord op dat er als twee regels uitzag, waarvan de tweede een succes claimde dat
        niet had plaatsgevonden (log forging, CWE-117). Het model kiest die tekst volledig.
        """
        import logging

        await _seed(db_session, 1, "alpha")
        smokkel = "Onbekend\n2026-09-21 INFO schedule_training: OK voor tenant 1"

        with caplog.at_level(logging.WARNING, logger="src.core.tool_broker.hr_registry"):
            await _registry().execute_hr_tool(
                SCHEDULE,
                {"user_email": "alpha-engineer@example.test", "training_name": smokkel},
                tenant_id=1,
            )

        records = [r for r in caplog.records if "schedule_training" in r.getMessage()]
        assert records, "Er is niets gelogd; dan meet deze test niets."
        for record in records:
            boodschap = record.getMessage()
            assert "\n" not in boodschap and "\r" not in boodschap, (
                f"De logregel bevat een regeleinde uit de payload: {boodschap!r}. Een model "
                "kan dan een tweede, verzonnen logregel injecteren."
            )


@pytest.mark.unit
@pytest.mark.asyncio
class TestScheduleTrainingGoesThroughTheHitlGate:
    async def test_the_broker_refuses_the_write_tool_without_an_approved_ticket(
        self, db_session: AsyncSession
    ) -> None:
        """De poort zelf, via `execute_tool` -- niet de configuratie die hem zou moeten openen.

        Alle andere tests in dit bestand roepen `execute_hr_tool` direct aan; dan komen de
        permissielaag en de HITL-poort er niet aan te pas, en toetsen de `IsGoverned`-tests
        alleen YAML. Deze test loopt over de ECHTE weg en legt vast dat een HIGH-schrijftool
        zonder goedgekeurd ticket niet draait. (Gate 2, 2026-09-21, LOW-3.)

        **Twee gevallen, en het tweede is de reparatie van ronde 2.** Zonder store weigert de
        broker op "HITLStore is not configured" en wordt `redeem_approval` nooit bereikt -- die
        variant vangt een verlaging van de risicoklasse, maar niets in de verzilvering. Het
        tweede geval heeft een store die `False` teruggeeft, zoals bij een ticket dat niet
        bestaat, al verbruikt is, of bij een andere tool hoort.
        """
        from src.core.tool_broker.exceptions import ToolExecutionException
        from src.core.tool_broker.service import ToolBrokerService

        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)
        broker = ToolBrokerService(
            serena_client=None,  # type: ignore[arg-type]
            seq_thinking_client=None,  # type: ignore[arg-type]
        )

        with pytest.raises(ToolExecutionException):
            await broker.execute_tool(
                tool_name=SCHEDULE,
                payload={"user_email": email, "training_name": TRAINING},
                agent_id="skillsgaptraining",
                timeout_seconds=30,
                context={"tenant_id": 1},
            )

        assert not await _rijen(db_session), (
            "Er is geschreven zonder goedgekeurd ticket. Dan is HIGH een label en geen poort."
        )

    async def test_a_ticket_that_cannot_be_redeemed_does_not_write(
        self, db_session: AsyncSession
    ) -> None:
        """Een ticketverwijzing die niet verzilverbaar is, mag niets schrijven.

        Dit is het geval dat de vorige test NIET dekt: hier is er wel een store, dus de broker
        komt tot `redeem_approval`. Die geeft `False` bij een ticket dat niet bestaat, al is
        verbruikt, bij een andere tenant hoort of bij een andere payload is goedgekeurd.
        """
        from src.core.tool_broker.exceptions import ToolExecutionException
        from src.core.tool_broker.service import ToolBrokerService

        email = await _seed(db_session, 1, "alpha")
        await _seed_training(db_session, 1)

        class _WeigerendeStore:
            async def redeem_approval(self, *a: object, **k: object) -> bool:
                return False

        broker = ToolBrokerService(
            serena_client=None,  # type: ignore[arg-type]
            seq_thinking_client=None,  # type: ignore[arg-type]
            hitl_store=_WeigerendeStore(),  # type: ignore[arg-type]
        )

        with pytest.raises(ToolExecutionException):
            await broker.execute_tool(
                tool_name=SCHEDULE,
                payload={
                    "user_email": email,
                    "training_name": TRAINING,
                    "_hitl_ticket_ref": "bestaat-niet",
                },
                agent_id="skillsgaptraining",
                timeout_seconds=30,
                context={"tenant_id": 1},
            )

        assert not await _rijen(db_session), (
            "Er is geschreven op een ticket dat niet verzilverbaar is. Dan bewijst de poort "
            "alleen dat er EEN ticketverwijzing was, niet dat die geldig was."
        )
