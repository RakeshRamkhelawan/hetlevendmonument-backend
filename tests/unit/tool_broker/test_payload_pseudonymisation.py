"""Payload-pseudonimisering platformbreed (BE-AGT-045, ADR-036 OP-27).

Een tool-payload is bij agent-gedreven uitvoering de `json.loads` van een `TOOL_CALL`-directive
en dus door een taalmodel geschreven. Die dict gaat naar vier plekken:

1. de event bus (`ToolBrokerService._publish_tool_event`);
2. de leeropslag -- `learning_event_handler._record_tool_event` schrijft hem als
   `observation_data` weg;
3. de auditketen (`ToolAuditRepository.log_execution(tool_input=...)`), per ADR-019 onuitwisbaar;
4. het HITL-ticket (`hitl_store.py`).

De eerste drie bewaren machinaal. De vierde is een MENSELIJK beoordelingsoppervlak en wordt
daarom bewust NIET geredigeerd: wie een actie goedkeurt moet zien wat hij goedkeurt (AI Act
art. 14). Die uitzondering staat hieronder als test, zodat niemand hem later "voor de
consistentie" dichtzet.

**Waarom pseudonimiseren en niet blanken -- een PRODUCT-afweging, geen wetsplicht.** Een eerdere
versie van deze docstring stelde dat AI Act art. 12 automatische logging over de levensduur van
het systeem vraagt en dat de verordening de invoer die tot het resultaat leidde als verplicht
logveld zou noemen. Dat tweede is bij de bron nagemeten onjuist en in ronde 3 weerlegd:
invoer-logging is uitsluitend verplicht voor Annex III punt 1(a) (biometrische identificatie) en
dit systeem valt onder punt 4 (personeelsbeheer). Waarden leesbaar houden was nooit verplicht.
Zie ADR-036 OP-27.

De keyed digest blijft de keuze om de redenen die wel standhouden: het log blijft forensisch
bruikbaar (wie de waarde kent kan de digest narekenen), herhaling van dezelfde waarde blijft
zichtbaar zonder de waarde te kennen, en art. 12(2) vraagt logging die risico-identificatie en
toezicht mogelijk maakt. Een marker sloopt die drie eigenschappen; een digest bewaart ze zonder
het persoonsgegeven leesbaar te laten.

**Waarom keyed en niet een naakte SHA-256.** Een hash van een e-mailadres of een naam heeft
lage entropie en is brute-force-baar; dat is geen anonimisering en het blijft een
persoonsgegeven. HMAC met een eigen sleutel maakt er pseudonimisering van in de zin van AVG
art. 4(5).
"""

from __future__ import annotations

from typing import Any

import pytest

PERSONAL_VALUE = "jan.jansen@acme.nl"
SENSITIVE_VALUE = "salaris 82000, ziektedagen 14"

#: De tenant is een VERPLICHTE parameter en komt bij elke aanroeper uit de executiecontext.
#: In de eerste versie viel hij terug op `payload.get("tenant_id", "unscoped")`, waardoor het
#: model zijn eigen scope koos en alle context-loze aanroepers een scope deelden. Dat de tests
#: hem nu moeten meegeven is het punt: "geen tenant" is niet meer representeerbaar.
TENANT = 1


def _payload() -> dict[str, Any]:
    """Een payload zoals een taalmodel hem zou kunnen produceren."""
    return {
        "role": "Finance Analyst",
        "employee_id": PERSONAL_VALUE,
        "department": SENSITIVE_VALUE,
    }


@pytest.mark.unit
class TestPseudonymisationShape:
    def test_a_reviewed_value_of_the_right_shape_stays_readable(self) -> None:
        """Een beoordeelde sleutel MET de juiste waardevorm blijft in het klare.

        Sinds ronde 3 beslist niet de sleutelnaam alleen: de waarde moet ook een opsombare vorm
        hebben. Paginering is zo'n vorm. `role` niet -- een rolnaam en een persoonsnaam zijn qua
        vorm niet te onderscheiden, dus die wordt gedigest.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "query_hr_database", {"limit": 25, "role": "Finance Analyst"}, tenant_id=TENANT
        )

        assert published["limit"] == 25

    def test_all_parameter_shaped_keys_remain_visible(self) -> None:
        """De VORM van de aanroep blijft traceerbaar (AI Act art. 12(2)).

        Sleutels weglaten zou het spoor onbruikbaar maken: je kunt dan niet meer vaststellen
        welke invoer bij welk resultaat hoorde. Sleutels die op een parameternaam lijken blijven
        daarom zichtbaar -- ook als hun waarde gedigest is.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication("query_hr_database", _payload(), tenant_id=TENANT)

        assert set(published) == {"role", "employee_id", "department"}

    def test_a_key_that_is_not_a_parameter_name_is_itself_pseudonymised(self) -> None:
        """Ook de sleutel is modeloutput (ronde 3, CRITICAL-1).

        Zonder deze eis kon de payload de persoonsgegevens in de SLEUTEL zetten. Met `None` als
        waarde zag de vastgelegde regel er dan volledig schoon uit -- geen digest te bekennen,
        terwijl de gegevens er wel stonden.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "query_hr_database",
            {f"{PERSONAL_VALUE} heeft diagnose D-2291": None},
            tenant_id=TENANT,
        )

        assert PERSONAL_VALUE not in str(published), (
            "De sleutelnaam staat verbatim in het log. Een sleutel is net zo goed vrije tekst "
            "als een waarde, en met None ernaast oogt de regel volkomen schoon."
        )

    def test_unreviewed_values_become_a_keyed_digest(self) -> None:
        """Geen marker en geen ruwe waarde, maar een verifieerbare digest."""
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication("query_hr_database", _payload(), tenant_id=TENANT)
        rendered = str(published)

        assert PERSONAL_VALUE not in rendered
        assert SENSITIVE_VALUE not in rendered

        digest = published["employee_id"]
        assert isinstance(digest, dict) and "hmac" in digest, (
            "Er hoort een digest te staan, geen marker. Een marker sloopt de toetsbaarheid die "
            "art. 12(2) van de logging vraagt: je kunt niet meer aantonen welke invoer bij welk "
            "resultaat hoorde, en herhaling van dezelfde waarde is niet meer zichtbaar."
        )
        assert len(str(digest["hmac"])) == 64

    def test_identical_values_give_identical_digests(self) -> None:
        """Herhaling moet zichtbaar zijn zonder de waarde te kennen."""
        from src.core.tool_broker.redaction import redact_for_publication

        first = redact_for_publication(
            "query_hr_database", {"role": PERSONAL_VALUE}, tenant_id=TENANT
        )
        second = redact_for_publication(
            "query_hr_database", {"role": PERSONAL_VALUE}, tenant_id=TENANT
        )

        assert first["role"] == second["role"]

    def test_digest_changes_when_the_key_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """De digest MOET van de sleutel afhangen -- anders is hij niet keyed.

        Een naakte SHA-256 van een e-mailadres is met een woordenboekaanval terug te rekenen en
        blijft dus een persoonsgegeven. Getoetst als EIGENSCHAP en niet door de naakte hash na
        te rekenen: die eerste opzet vergeleek met `sha256(waarde)` terwijl de implementatie de
        JSON-vorm hasht, dus de digests verschilden altijd en de test slaagde ook bij een
        naakte hash. Dat was een vacuum-test; deze variant is mutatie-doodbaar gemaakt.
        """
        from src.core.tool_broker import redaction

        monkeypatch.setattr(redaction, "_configured_key", lambda: "sleutel-een-" + "x" * 32)
        redaction.reset_key_cache()
        first = redaction.redact_for_publication(
            "query_hr_database", {"role": PERSONAL_VALUE}, tenant_id=TENANT
        )

        monkeypatch.setattr(redaction, "_configured_key", lambda: "sleutel-twee-" + "x" * 32)
        redaction.reset_key_cache()
        second = redaction.redact_for_publication(
            "query_hr_database", {"role": PERSONAL_VALUE}, tenant_id=TENANT
        )

        redaction.reset_key_cache()

        assert first["role"]["hmac"] != second["role"]["hmac"], (
            "Dezelfde waarde geeft onder een andere sleutel dezelfde digest. De digest hangt "
            "dus niet van de sleutel af en is geen keyed HMAC maar een naakte hash -- voor "
            "lage-entropie-waarden terug te rekenen (AVG art. 4(5))."
        )


@pytest.mark.unit
class TestTheKey:
    def test_production_without_a_key_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Buiten de ephemere-omgevingen zonder sleutel: harde fout, geen terugval."""
        from src.core.tool_broker import redaction

        monkeypatch.setattr(redaction, "_configured_key", lambda: None)
        monkeypatch.setattr(redaction, "_allows_ephemeral_key", lambda: False)
        redaction.reset_key_cache()

        with pytest.raises(RuntimeError, match="pseudonim"):
            redaction.pseudonymisation_key()

    def test_development_without_a_key_uses_an_ephemeral_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In development/test/local mag hij ephemeer zijn -- veiliger dan een constante."""
        from src.core.tool_broker import redaction

        monkeypatch.setattr(redaction, "_configured_key", lambda: None)
        monkeypatch.setattr(redaction, "_allows_ephemeral_key", lambda: True)
        redaction.reset_key_cache()

        key = redaction.pseudonymisation_key()

        assert isinstance(key, bytes)
        assert len(key) >= 32

    def test_a_production_process_refuses_to_start_without_the_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falen bij het OPSTARTEN, niet bij de eerste tool-aanroep.

        De runtime-fail-closed dekt de veiligheidseigenschap al, maar hij doet dat pas als er
        een tool wordt aangeroepen -- dus een deploy lijkt te slagen en breekt later stil. Deze
        boot-check is bewust pas toegevoegd nadat de sleutel in beide CD-workflows en de
        blue/green-compose stond; die volgorde is de kern van de bevinding.

        Eerder stond in de documentatie dat dit "het opstarten in de testomgeving brak". Dat is
        nagemeten en onjuist: `src/main.py` slaat `validate_config_at_startup()` over onder
        pytest, en deze lijst wordt alleen doorlopen als ENVIRONMENT production of staging is.
        """
        from src.core.config.config_validator import ConfigSeverity, ConfigValidator
        from src.core.tool_broker.redaction import KEY_ENV_VAR

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv(KEY_ENV_VAR, raising=False)

        result = ConfigValidator().validate()
        blocking = [
            issue
            for issue in result.issues
            if issue.key == KEY_ENV_VAR and issue.severity == ConfigSeverity.ERROR
        ]

        assert blocking, (
            f"{KEY_ENV_VAR} ontbreekt en de configuratievalidatie meldt geen fout. Dan start "
            "een productieproces zonder pseudonimiseringssleutel en faalt pas bij de eerste "
            "tool-aanroep -- een stille storing in plaats van een luide deploy-fout."
        )


@pytest.mark.unit
class TestTenantSeparation:
    def test_same_value_in_two_tenants_gives_different_digests(self) -> None:
        """Dezelfde persoon in twee tenants mag niet dezelfde digest krijgen.

        Anders kan iemand met leesrechten op twee tenants personen over die grens correleren --
        in strijd met de isolatie die ADR-003/004/005 juist afdwingen. De tenant gaat daarom mee
        in de domeinscheiding van de HMAC.

        De tenant komt uit de PARAMETER en niet uit de payload. De eerste versie van deze test
        gaf hem in de payload mee, en slaagde daardoor terwijl twee aanroepers zonder context in
        productie allebei op dezelfde constante `"unscoped"` uitkwamen -- de eigenschap was hier
        groen en in het echt afwezig. Het gedragsbewijs staat in
        `test_pseudonymisation_leaks.py`, waar de tenant via de ContextVar wordt gezet.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        first = redact_for_publication("query_hr_database", {"role": PERSONAL_VALUE}, tenant_id=1)
        second = redact_for_publication("query_hr_database", {"role": PERSONAL_VALUE}, tenant_id=2)

        assert first["role"]["hmac"] != second["role"]["hmac"]

    def test_an_unusable_tenant_is_refused(self) -> None:
        """Geen geldige tenant, geen digest -- en geen terugval op een gedeelde scope."""
        from src.core.tool_broker.redaction import redact_for_publication

        with pytest.raises(ValueError, match="tenant_id"):
            redact_for_publication("query_hr_database", {"role": PERSONAL_VALUE}, tenant_id=0)


@pytest.mark.unit
class TestOnlyWiredKeysStayReadable:
    def test_keys_the_caller_injected_from_context_stay_readable(self) -> None:
        """Wat leesbaar blijft volgt uit de WIRING, niet uit een naam.

        `service.py` geeft in `broker_keys` op welke sleutels het zelf uit de executiecontext
        heeft geinjecteerd. Die zijn per definitie geen modeloutput. Digesten zou hier niets
        beschermen en de tenant-routing van `pubsub_manager` breken.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "local__read_file",
            {"tenant_id": 7, "user_id": 42, "path": "/etc/x"},
            tenant_id=7,
            broker_keys=frozenset({"tenant_id", "user_id"}),
        )

        assert published["tenant_id"] == 7
        assert published["user_id"] == 42
        assert "hmac" in published["path"], "het pad is wel modeloutput en hoort gedigest"

    def test_the_same_key_is_digested_when_the_caller_did_not_inject_it(self) -> None:
        """Dezelfde sleutelnaam, andere herkomst, andere behandeling.

        Dit is precies het onderscheid dat een naamlijst niet kan maken en dat lek HIGH-2
        veroorzaakte: zonder `broker_keys` bleef staan wat het model had geschreven, met de
        leesbaarheid van een contextveld.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "local__read_file",
            {"tenant_id": 9, "path": "/etc/x"},
            tenant_id=7,
        )

        assert "tenant_id" not in published
        assert 9 not in published.values()


@pytest.mark.unit
class TestNotIdempotentOnPurpose:
    def test_a_value_shaped_like_a_digest_is_still_digested(self) -> None:
        """De vormcheck die idempotentie moest geven, was het lek.

        `_is_already_pseudonymised()` keek of een waarde de vorm `{"hmac": ...}` had en niet naar
        de inhoud, dus `{"hmac": "<e-mailadres>"}` passeerde verbatim. De functie wordt per
        uitvoering precies eenmaal op de RAUWE payload toegepast, dus idempotentie was nooit
        nodig -- alleen de controle die het lek veroorzaakte. Dat er precies eenmaal geredigeerd
        wordt, dwingt `tests/architecture/test_tool_payloads_are_pseudonymised.py` af.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "query_hr_database", {"role": {"hmac": PERSONAL_VALUE}}, tenant_id=TENANT
        )

        assert PERSONAL_VALUE not in str(published["role"])


@pytest.mark.unit
class TestEveryToolIsCovered:
    @pytest.mark.parametrize(
        "tool_name",
        ["query_hr_database", "create_task", "list_tasks", "local__read_file", "serena__search"],
    )
    def test_no_tool_publishes_a_raw_personal_value(self, tool_name: str) -> None:
        """Ook een tool zonder eigen allowlist mag geen ruwe waarde publiceren.

        Dit was het gat: alleen `query_hr_database` had een allowlist, dus de lokale,
        business- en externe paden publiceerden verbatim. De default is nu pseudonimiseren,
        niet doorlaten.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            tool_name, {"unexpected": PERSONAL_VALUE}, tenant_id=TENANT
        )

        assert PERSONAL_VALUE not in str(published)
