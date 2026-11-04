"""De inhoud-opt-in: aan te zetten, maar nooit per ongeluk aan (ADR-036 OP-27).

Zonder deze schakelaar is er geen manier om bij het debuggen van een agent te zien wat er
werkelijk in de payload zat. Met een naieve schakelaar is er geen manier om te garanderen dat hij
niet in productie aan staat. De OpenTelemetry GenAI-conventie kiest de eerste helft -- vastleggen
van prompt- en tool-inhoud staat standaard uit en moet expliciet aan
(`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`) -- en laat de tweede helft aan de
implementatie. Deze tests dekken die tweede helft.

Vijf eigenschappen, elk met een eigen test:

1. Standaard uit.
2. Fail-closed bij parsen: alleen een expliciete allowlist van tokens zet hem aan, zodat de
   string `"false"` niet als waarheid geldt.
3. Genegeerd waar echte persoonsgegevens kunnen staan -- en dan LUID, met een `logger.error`.
4. Elke onbewerkt vastgelegde regel zegt dat van zichzelf, en een model kan die marker niet
   vervalsen.
5. Luid zolang hij aan staat: een waarschuwing per proces, niet per aanroep.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

PERSONAL_VALUE = "jan.jansen@acme.nl"
TENANT = 1


@pytest.fixture(autouse=True)
def _clean_capture_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """De opt-in en de eenmalige waarschuwing opruimen voor EN na.

    De waarschuwing wordt in een module-globale bijgehouden; zonder opruimen lekt die naar elke
    latere test in dezelfde xdist-worker -- het patroon dat OP-20 blootlegde.
    """
    from src.core.tool_broker import redaction

    monkeypatch.delenv(redaction.CAPTURE_ENV_VAR, raising=False)
    redaction.reset_capture_warning()
    yield
    redaction.reset_capture_warning()


def _published(**env: str) -> dict[str, object]:
    from src.core.tool_broker.redaction import redact_for_publication

    return redact_for_publication(
        "query_hr_database", {"role": PERSONAL_VALUE, "limit": 10}, tenant_id=TENANT
    )


@pytest.mark.unit
class TestTheDefaultIsOff:
    def test_without_the_variable_the_payload_is_pseudonymised(self) -> None:
        """Niets gezet betekent het bestaande gedrag -- geen enkele bestaande test verandert."""
        published = _published()

        assert PERSONAL_VALUE not in str(published)


@pytest.mark.unit
class TestParsingFailsClosed:
    @pytest.mark.parametrize("token", ["false", "0", "no", "off", "", "  ", "onzin", "False"])
    def test_anything_other_than_an_explicit_yes_means_off(
        self, token: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`bool(os.environ.get(...))` zou van de string "false" een `True` maken.

        Dan staat het aan terwijl de configuratie zegt dat het uit is -- en dat is precies het
        soort stille afwijking waar deze hele reeks over gaat.
        """
        from src.core.tool_broker import redaction

        monkeypatch.setenv(redaction.CAPTURE_ENV_VAR, token)

        assert PERSONAL_VALUE not in str(_published()), (
            f"Het token {token!r} zet de opt-in aan. Alleen een expliciete ja hoort dat te doen."
        )

    @pytest.mark.parametrize("token", ["1", "true", "TRUE", "yes", "on", " true "])
    def test_an_explicit_yes_turns_it_on(self, token: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """De andere richting: zonder dit is "alles is uit" een geldige implementatie."""
        from src.core.tool_broker import redaction

        monkeypatch.setenv(redaction.CAPTURE_ENV_VAR, token)

        assert _published()["role"] == PERSONAL_VALUE, (
            f"Het token {token!r} zet de opt-in niet aan; dan is de schakelaar onbruikbaar."
        )


@pytest.mark.unit
class TestItIsIgnoredWhereRealDataCanBe:
    @pytest.mark.parametrize("environment", ["production", "staging", "blue", "green", ""])
    def test_the_optin_is_refused_outside_the_allowed_environments(
        self, environment: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Aan in productie betekent NIET aan. Dit is de kern van de afspraak.

        Wie de inhoud wil vastleggen in een omgeving met echte gegevens moet
        `CONTENT_CAPTURE_ENVIRONMENTS` wijzigen -- zichtbaar in de diff en onder deze test. Een
        omgevingsvariabele is de verkeerde drempel voor die beslissing.

        De lege omgeving hoort er ook bij: een proces waar `ENVIRONMENT` vergeten is mag niet
        stil in de ontwikkelmodus vallen.
        """
        from src.core.tool_broker import redaction

        monkeypatch.setenv(redaction.CAPTURE_ENV_VAR, "1")
        monkeypatch.setenv("ENVIRONMENT", environment)

        assert PERSONAL_VALUE not in str(_published()), (
            f"De opt-in wordt gehonoreerd in omgeving {environment!r}. Daar kunnen echte "
            "persoonsgegevens staan, en die belanden dan onbewerkt in de onuitwisbare auditketen."
        )

    def test_being_refused_is_loud(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Uit en LUID, niet uit en stil.

        Wie de vlag in productie zet denkt dat hij aan staat. Zonder foutmelding zoekt die persoon
        zich vervolgens blind op een schakelaar die stil is genegeerd.
        """
        import logging

        from src.core.tool_broker import redaction

        monkeypatch.setenv(redaction.CAPTURE_ENV_VAR, "1")
        monkeypatch.setenv("ENVIRONMENT", "production")

        with caplog.at_level(logging.ERROR, logger=redaction.__name__):
            _published()

        assert any(redaction.CAPTURE_ENV_VAR in record.message for record in caplog.records), (
            "Er is geen foutmelding wanneer de opt-in wordt genegeerd."
        )


@pytest.mark.unit
class TestEveryVerbatimRecordSaysSo:
    def test_a_verbatim_record_carries_the_mode_marker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zonder marker is een leesbare waarde dubbelzinnig.

        Beoordeeld-en-toegestaan, of onder de opt-in vastgelegd? Die dubbelzinnigheid in een
        auditketen is zelf een defect. De afwezigheid van de marker betekent gepseudonimiseerd, en
        dat is buiten de toegestane omgevingen de enige mogelijke modus.
        """
        from src.core.tool_broker import redaction

        monkeypatch.setenv(redaction.CAPTURE_ENV_VAR, "1")

        published = _published()

        assert published[redaction.REDACTION_MODE_KEY] == redaction.VERBATIM_MODE

    def test_a_pseudonymised_record_has_no_marker(self) -> None:
        """De andere richting: de standaardmodus voegt niets toe.

        Zo verandert geen enkele bestaande test, en blijft de payload in het normale geval exact
        de vorm van de aanroep.
        """
        from src.core.tool_broker import redaction

        assert redaction.REDACTION_MODE_KEY not in _published()

    def test_the_model_cannot_forge_the_marker(self) -> None:
        """Een payload met `_redaction: verbatim` mag geen onbewerkte regel nabootsen.

        In de standaardmodus hoort `_redaction` bij geen enkel tool-vocabulaire, dus de
        SLEUTELNAAM wordt zelf een pseudonym -- de marker kan daar niet leesbaar verschijnen.
        """
        from src.core.tool_broker import redaction
        from src.core.tool_broker.redaction import redact_for_publication

        published = redact_for_publication(
            "query_hr_database",
            {redaction.REDACTION_MODE_KEY: redaction.VERBATIM_MODE, "role": PERSONAL_VALUE},
            tenant_id=TENANT,
        )

        assert published.get(redaction.REDACTION_MODE_KEY) != redaction.VERBATIM_MODE, (
            "Een door het model geschreven marker overleeft. Dan kan modeloutput een regel laten "
            "doorgaan voor een bewust onbewerkt vastgelegde regel."
        )


@pytest.mark.unit
class TestTheWarningIsOncePerProcess:
    def test_it_warns_once_and_not_per_call(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Per aanroep waarschuwen verdrinkt het signaal in ruis.

        Bij BE-AGT-044 is een per-aanroep-waarschuwing teruggedraaid om precies die reden: een
        detectiesignaal dat bij elke routineuze actie afgaat, is geen detectiesignaal meer.
        """
        import logging

        from src.core.tool_broker import redaction

        monkeypatch.setenv(redaction.CAPTURE_ENV_VAR, "1")

        with caplog.at_level(logging.WARNING, logger=redaction.__name__):
            for _ in range(5):
                _published()

        relevant = [r for r in caplog.records if redaction.CAPTURE_ENV_VAR in r.message]
        assert len(relevant) == 1, (
            f"{len(relevant)} waarschuwingen voor vijf aanroepen; verwacht er precies een."
        )
