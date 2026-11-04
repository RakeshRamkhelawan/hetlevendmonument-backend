"""Een beoordeelde SLEUTEL is nog geen vertrouwde WAARDE (BE-AGT-045 ronde 3, ADR-036 OP-27).

Ronde 2 sloot "het model kiest welke sleutelNAAM leesbaar blijft". Ronde 3 legt de laag eronder
bloot: de allowlist beslist op de sleutelnaam, en de WAARDE onder die sleutel is nog steeds
volledig modeloutput. De redactie loopt bovendien VOORDAT de tool zijn parameters valideert, dus
ook een waarde die de tool daarna zou weigeren is dan al vastgelegd.

Aangetoond door code te draaien, niet beredeneerd:

    redact_for_publication("query_hr_database", {"role": "jan.jansen@acme.nl"}, tenant_id=1)
    -> {"role": "jan.jansen@acme.nl"}

    redact_for_publication("query_hr_database", {"limit": "salaris 82000"}, tenant_id=1)
    -> {"limit": "salaris 82000"}        # een string in een veld dat een getal hoort te zijn

    redact_for_publication("query_hr_database", {"role": {"naam": "Jan Jansen"}}, tenant_id=1)
    -> {"role": {"naam": "Jan Jansen"}}  # geneste structuren werden nooit doorlopen

Dit is dezelfde fout als HIGH-2 uit ronde 2, een niveau lager: een NAAM beslist iets wat het
model beheerst. De oplossing is dezelfde vorm als daar -- niet vertrouwen op wat iets HEET, maar
eisen wat het IS. Een waarde blijft alleen leesbaar als hij een opsombare vorm heeft (getal,
of een gedeclareerde enum-waarde); vrije tekst wordt gedigest, ook onder een beoordeelde sleutel.

**UUID's zijn GEEN leesbare vorm** (Gate 2 ronde 6, F9a). Deze regel adverteerde die tot
2026-08-05 nog wel, terwijl `_is_uuid()` in `ad3779a7` is verwijderd omdat geen enkele
`PAYLOAD_POLICY`-regel hem gebruikte. Regel 177 in dit bestand legt het tegendeel al vast. Zo'n
verschil tussen documentatie en code is de verkeerde kant op gevaarlijk: wie het ziet, concludeert
uit de documentatie dat UUID's leesbaar HOREN te zijn en zet hem terug -- en dan staat er een
stabiele correlatiesleutel in een onuitwisbaar log zonder dat een test die beslissing afdwingt.

**Waarom `role` daarmee gedigest wordt.** Een rolnaam en een persoonsnaam zijn qua vorm niet te
onderscheiden -- "Finance Analyst" en "Jan Jansen" passen op hetzelfde patroon. De
art.-12(2)-traceerbaarheid blijft intact: de digest is verifieerbaar door wie de waarde kent, en
twee aanroepen voor dezelfde rol geven dezelfde digest. Wat je verliest is leesbaarheid op een
oogopslag; wat je wint is dat het model daar geen naam meer kan achterlaten.

De bestaande test `TestEveryToolIsCovered::test_no_tool_publishes_a_raw_personal_value` kon dit
per constructie niet vinden: die probeert de sleutel `"unexpected"`, die juist NIET op een
allowlist staat.
"""

from __future__ import annotations

import pytest

PERSONAL_VALUE = "jan.jansen@acme.nl"
PERSON_NAME = "Jan Jansen"
TENANT = 1


#: Per toegelaten waardevorm een detectiewaarde die BINNEN die vorm past en toch een
#: persoonsgegeven is. Dit is de correctie op de vorige opzet: die gebruikte een e-mailadres, en
#: dat wordt door elke vorm al op zijn TEKENS afgewezen. De test bewees dus de tekenklasse en
#: niet de eigenschap -- aangetoond doordat een mutatie (`employee_id` als opsombare waarde
#: toevoegen) de suite groen liet met een BSN verbatim in de uitvoer.
PII_THAT_FITS_THE_SHAPE: list[tuple[str, str, object]] = [
    # Opsombare codes: alleen exacte enum-leden mogen passeren.
    ("create_task", "status", "Jan-Jansen"),
    ("create_task", "priority", "ontslaan_wegens_fraude_2026"),
    ("list_tasks", "status", "jan_jansen_at_acme_nl"),
    ("update_task", "priority", "salaris_82000_Jan_Jansen"),
    ("update_task", "status", "HIV-positief-ontslagdossier"),
    # Getallen: een BSN of telefoonnummer valt buiten het bereik dat de tool accepteert.
    ("query_hr_database", "limit", 123456782),
    ("query_hr_database", "offset", 612345678),
    ("list_tasks", "limit", 123456782),
    ("list_tasks", "skip", 612345678),
    # Een UUID is 128 bits aanvallerskeuze: deze decodeert naar leesbare tekst.
    ("update_task", "task_id", "4a616e5f-4a61-6e73-656e-5f4849562e2e"),
    ("delete_task", "task_id", "4a616e5f-4a61-6e73-656e-5f4849562e2e"),
]

#: Sleutelnamen die er als parameternaam uitzien en toch een dossier zijn. Een tekenklasse kan
#: deze niet weren; alleen het vocabulaire van de tool kan dat.
PII_THAT_LOOKS_LIKE_A_PARAMETER: list[str] = [
    "Jan_Jansen",
    "jan_jansen_1978_bsn_123456789",
    "patient_Jansen_HIV_positief",
    "salaris_Jan_Jansen_is_82000",
    "Jan_Jansen_ontslagen_wegens_fraude",
]


@pytest.mark.unit
class TestAnAllowlistedKeyIsNotATrustedValue:
    @pytest.mark.parametrize("tool_name,key,value", PII_THAT_FITS_THE_SHAPE)
    def test_a_personal_value_that_fits_the_shape_is_still_pseudonymised(
        self, tool_name: str, key: str, value: object
    ) -> None:
        """Een waarde die in de toegelaten VORM past mag nog geen dossier zijn.

        Een patroon voor "een korte code" kan `pending` niet onderscheiden van `Jansen`. De eis
        is daarom lidmaatschap van de OPGESOMDE waarden, en die staan al gedeclareerd:
        `TaskStatusLiteral` in `domains/tasks/schemas.py`, `MAX_LIMIT` in `hr_registry.py`.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(tool_name, {key: value}, tenant_id=TENANT)

        assert published.get(key) != value, (
            f"`{key}` van `{tool_name}` laat {value!r} leesbaar door. De waarde past binnen de "
            "toegelaten vorm, maar een vorm begrenst de tekenset en niet de informatie."
        )

    @pytest.mark.parametrize("key", PII_THAT_LOOKS_LIKE_A_PARAMETER)
    def test_a_key_that_looks_like_a_parameter_is_still_pseudonymised(self, key: str) -> None:
        """Ook een sleutelnaam die op een parameternaam lijkt is modeloutput.

        `Jan_Jansen_salaris_82000` haalde de vorige tekenklasse-toets zonder problemen, en met
        `None` als waarde stond er geen enkele digest in de regel. Alleen het vocabulaire van de
        tool kan dit onderscheiden.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication("local__send_email", {key: None}, tenant_id=TENANT)

        assert key not in published, (
            f"De sleutel {key!r} staat verbatim in het log. Met None als waarde bevat de "
            "vastgelegde regel geen enkele digest en oogt hij volkomen schoon."
        )

    def test_a_nested_structure_under_a_reviewed_key_is_pseudonymised(self) -> None:
        """Een dict onder een beoordeelde sleutel werd nooit doorlopen."""
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "list_tasks", {"status": {"naam": PERSON_NAME}}, tenant_id=TENANT
        )

        assert PERSON_NAME not in str(published["status"])

    def test_a_numeric_parameter_refuses_a_text_value(self) -> None:
        """Een veld dat een getal hoort te zijn mag geen vrije tekst leesbaar doorlaten."""
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "query_hr_database", {"limit": "salaris 82000"}, tenant_id=TENANT
        )

        assert "82000" not in str(published["limit"])


@pytest.mark.unit
class TestEnumerableValuesStayReadable:
    """De andere richting: de fix mag niet alles digesten.

    Zonder deze tests is "digest alles" een geldige oplossing, en dan is de auditregel
    onbruikbaar zonder dat een test klaagt -- precies waarvoor
    `test_every_executable_tool_has_a_reviewed_allowlist` bestaat.
    """

    def test_a_pagination_number_stays_readable(self) -> None:
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "query_hr_database", {"limit": 25, "offset": 0}, tenant_id=TENANT
        )

        assert published["limit"] == 25
        assert published["offset"] == 0

    def test_the_real_paging_parameter_of_list_tasks_stays_readable(self) -> None:
        """`business_registry` leest `skip`, niet `offset`.

        De eerste versie van de tabel had `offset`: de echte parameter werd gedigest en een
        niet-bestaande bleef leesbaar. Een aanname in plaats van een meting, in precies de tabel
        die dat moet voorkomen.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication("list_tasks", {"skip": 25}, tenant_id=TENANT)

        assert published["skip"] == 25

    def test_an_enumerable_status_stays_readable(self) -> None:
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "list_tasks", {"status": "pending", "limit": 10}, tenant_id=TENANT
        )

        assert published["status"] == "pending"

    def test_a_task_identifier_keeps_its_key_but_not_its_value(self) -> None:
        """Een UUID is 128 bits aanvallerskeuze, dus de WAARDE gaat er niet leesbaar in.

        `4a616e5f-4a61-6e73-656e-5f4849562e2e` is een geldig UUID-patroon dat naar leesbare tekst
        decodeert, en de redactie loopt voordat de tool de identificator valideert. De SLEUTEL
        blijft zichtbaar -- die hoort bij het vocabulaire van de tool -- en dezelfde taak geeft
        dezelfde digest, dus de koppeling blijft narekenbaar.
        """
        from src.core.tool_broker.redaction import redact_for_publication

        task_id = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
        published = redact_for_publication("delete_task", {"task_id": task_id}, tenant_id=TENANT)

        assert "task_id" in published
        assert published["task_id"] != task_id
