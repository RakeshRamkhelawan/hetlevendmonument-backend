"""De inhoudswachter: wat hij tegenhoudt, wat hij doorlaat, en wat hij NOOIT prijsgeeft.

**Waarom deze wachter bestaat.** De Council beoordeelt de VORM van een actie -- hij krijgt de
toolnaam en de argumentNAMEN, nooit de waarden (BE-AGT-043, ADR-036 OP-25), omdat alles wat hij
ziet de onuitwisbare ADR-019-keten in gaat. Gemeten 2026-09-21: `detect_pii` op een vrije prompt
vindt `['email', 'phone', 'bsn']`, en op wat de Council werkelijk krijgt `[]`. Op het chatpad
stond helemaal geen inhoudscontrole.

**Waarom hier geen enkele patch staat.** Deze module doet geen I/O en heeft geen database, dus er
is niets te mocken. Dat is geen toeval maar het ontwerp: juist omdat er niets te patchen valt, kan
een assertie hier niet hol worden door een fixture die uitzet wat hij meet.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.core.governance.input_guard import Oordeel

pytestmark = pytest.mark.unit

TENANT = 1

#: Een geldig BSN volgens de elfproef -- de detector gebruikt een controlegetal, dus een
#: willekeurig getal van negen cijfers wordt NIET gevonden en zou deze tests hol maken.
BSN = "123456782"
IBAN = "NL91ABNA0417164300"

#: De logger van de module onder test. De logasserties filteren hierop, want
#: `caplog.records` bevat ook records van andere modules.
_REGISTRY_LOGGER = "src.core.governance.input_guard"


def _beoordeel(tekst: str, tenant_id: int = TENANT) -> "Oordeel":
    from src.core.governance.input_guard import beoordeel

    return beoordeel(tekst, tenant_id=tenant_id, herkomst="test")


class TestWatErDoorGaat:
    """De tegenrichting, en die staat vooraan met opzet.

    Zonder deze klasse is "weiger alles" een geldige oplossing die elke andere test in dit
    bestand haalt. Een wachter die in de weg loopt wordt bovendien uitgezet, en dan heb je
    niets -- dus dit is niet alleen een testvorm maar de reden dat het regelbestand onderscheid
    maakt tussen blokkeren en melden.
    """

    def test_gewone_zakelijke_tekst_gaat_door(self) -> None:
        oordeel = _beoordeel("Vat de vaardighedenkloof samen voor het team Finance")

        assert oordeel.toegestaan is True
        assert oordeel.categorieen == ()
        assert oordeel.verwijzing is None

    def test_een_emailadres_gaat_door_want_dat_is_normaal_zakelijk_gebruik(self) -> None:
        """E-mail en telefoon worden GEMELD, niet geweigerd.

        "Stuur de uitnodiging naar jan@klant.test" is gewoon werk. Die weigeren maakt het
        product onbruikbaar; dat staat als afweging in `input_guard_rules.yml` (IG-002) en niet
        als constante in code, zodat een klant hem kan aanscherpen.
        """
        oordeel = _beoordeel("Stuur de uitnodiging naar jan.jansen@klant.test, tel 0612345678")

        assert oordeel.toegestaan is True

    def test_lege_invoer_is_geen_weigering(self) -> None:
        for leeg in ("", "   ", "\n"):
            assert _beoordeel(leeg).toegestaan is True


class TestWatErWordtTegengehouden:
    @pytest.mark.parametrize(
        "tekst,categorie",
        [
            (f"Plan een training voor BSN {BSN}", "bsn"),
            (f"Boek dit op {IBAN}", "iban"),
        ],
    )
    def test_een_identificator_wordt_geweigerd(self, tekst: str, categorie: str) -> None:
        """Een BSN of IBAN hoort nooit in een opdracht aan een agent."""
        oordeel = _beoordeel(tekst)

        assert oordeel.toegestaan is False
        assert categorie in oordeel.categorieen
        assert oordeel.verwijzing, "Zonder verwijzing kan een gebruiker niets melden."

    def test_de_vloer_geldt_ook_zonder_regelbestand(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Een ontbrekend of kapot regelbestand mag de VLOER niet wegnemen.

        Dat is de vorm waarin een bewaker stil verdwijnt: iemand hernoemt een bestand, alles
        blijft groen, en de wachter laat vanaf dat moment alles door. De vloer staat daarom ook
        in de code, en het bestand bepaalt alleen wat een organisatie er BOVENOP wil.
        """
        from src.core.governance import input_guard

        input_guard._regels.cache_clear()
        monkeypatch.setattr(input_guard, "REGELBESTAND", Path("bestaat-niet-xyz.yml"))
        try:
            oordeel = input_guard.beoordeel(
                f"Boek op {IBAN}", tenant_id=TENANT, herkomst="test-zonder-bestand"
            )
            assert oordeel.toegestaan is False
            assert "iban" in oordeel.categorieen
        finally:
            input_guard._regels.cache_clear()

    def test_een_onbruikbaar_regelbestand_legt_de_dienst_niet_plat(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Een bestand dat WEL parseert maar verkeerd getypt is, mag niet alles weigeren.

        Gemeten in Gate 2 (2026-09-22): `int(t)` voor de tenantlijst stond BUITEN de
        afscherming, die alleen `OSError`/`YAMLError` ving. Het commentaar in de YAML nodigde
        zelf uit tot `- 42   # reden`; een operator die `- "42 (Acme)"` schrijft kreeg ELKE
        aanvraag op BEIDE deuren geweigerd, voor ALLE tenants, plus een traceback en een
        schijfleesactie per verzoek -- `lru_cache` bewaart een uitzondering niet (zes
        ValueErrors bij zes aanroepen).
        """
        from src.core.governance import input_guard

        kapot = tmp_path / "kapot.yml"
        kapot.write_text(
            'version: 1\nenabled: true\nuit_voor_tenants:\n  - "42 (Acme)"\npolicies: []\n',
            encoding="utf-8",
        )
        input_guard._regels.cache_clear()
        monkeypatch.setattr(input_guard, "REGELBESTAND", kapot)
        try:
            onschuldig = input_guard.beoordeel(
                "Vat het rapport samen voor team Finance", tenant_id=TENANT, herkomst="test"
            )
            assert onschuldig.toegestaan is True, (
                "Een typfout in het regelbestand weigert nu elke aanvraag. Dat is geen "
                "fail-closed maar een storing met een nette naam."
            )
            # En de vloer staat er nog: de terugval mag niet alles doorlaten.
            echt = input_guard.beoordeel(
                f"Boek op {IBAN}", tenant_id=TENANT, herkomst="test"
            )
            assert echt.toegestaan is False

            # De terugval is GECACHET: geen schijfwerk per verzoek.
            voor = input_guard._regels.cache_info()
            for _ in range(5):
                input_guard.beoordeel("nog een vraag", tenant_id=TENANT, herkomst="test")
            na = input_guard._regels.cache_info()
            assert na.misses == voor.misses, (
                "Het regelbestand wordt per aanroep opnieuw gelezen. Dat is precies het "
                "schijfwerk-per-verzoek dat in Gate 2 is gemeten."
            )
        finally:
            input_guard._regels.cache_clear()


class TestDeTekstVerlaatDeWachterNooit:
    """De kern van het ontwerp: de wachter mag niet lekken wat hij tegenhield.

    Op 2026-09-21 moest exact die fout in `hr_registry._schedule_training` worden gerepareerd,
    waar een repository-melding de ontvangen naam meecitieerde. Het antwoord van een tool gaat de
    event bus op en wordt in de leeropslag vastgelegd; een chatweigering gaat naar de gebruiker
    en het logbestand.
    """

    def test_de_reden_bevat_de_gevonden_tekst_niet(self) -> None:
        oordeel = _beoordeel(f"Plan een training voor BSN {BSN}")

        for taal in ("nl", "en"):
            assert BSN not in oordeel.reden(taal)
            assert "bsn" in oordeel.reden(taal), (
                "De CATEGORIE hoort er wel in -- anders weet niemand wat eruit moet."
            )
        assert BSN not in str(oordeel)

    def test_de_reden_is_tweetalig(self) -> None:
        """Een Engelstalige gebruiker moet weten wat eruit moet, anders is er geen deur.

        `CopilotTurnRequest.language` is `Literal["nl", "en"]` (gemeten), dus die twee. De
        eerste versie gaf altijd Nederlands -- en juist dan faalt het argument waarmee deze
        melding bestaat (AI Act art. 14).
        """
        oordeel = _beoordeel(f"Plan een training voor BSN {BSN}")

        assert "geweigerd" in oordeel.reden("nl")
        assert "refused" in oordeel.reden("en")
        assert oordeel.reden("de") == oordeel.reden("en"), "Onbekende taal valt terug op Engels."

    def test_het_log_bevat_de_gevonden_tekst_niet(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="src.core.governance.input_guard"):
            _beoordeel(f"Plan een training voor BSN {BSN} en mail jan@klant.test")

        eigen = [r for r in caplog.records if r.name == "src.core.governance.input_guard"]
        assert eigen, "Er is niets gelogd; dan meet deze assertie niets."
        gelogd = " ".join(r.getMessage() for r in eigen)
        assert BSN not in gelogd, (
            "Het BSN staat in het logbestand. Dan is de wachter zelf een opslag geworden van "
            "precies wat hij tegenhield."
        )
        assert "jan@klant.test" not in gelogd
        assert "bsn" in gelogd, (
            "De categorie hoort er wel in (AI Act art. 12: er moet een log zijn)."
        )

    def test_de_verwijzing_is_niet_uit_de_inhoud_afgeleid(self) -> None:
        """Twee keer dezelfde tekst geeft twee VERSCHILLENDE verwijzingen.

        Een hash van de inhoud zou een stabiele aanwijzing naar die persoon zijn en daarmee zelf
        een persoonsgegeven -- dan lekt de verwijzing alsnog, alleen trager.
        """
        eerste = _beoordeel(f"BSN {BSN}")
        tweede = _beoordeel(f"BSN {BSN}")

        assert eerste.verwijzing != tweede.verwijzing


class TestFailClosed:
    def test_een_onverwachte_fout_weigert_in_plaats_van_door_te_laten(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Een wachter die bij een fout doorlaat, is afwezig op het moment dat het ertoe doet."""
        from src.core.governance import input_guard

        def _kapot() -> object:
            raise RuntimeError("detector stuk")

        monkeypatch.setattr(input_guard, "_regels", _kapot)
        oordeel = input_guard.beoordeel("wat dan ook", tenant_id=TENANT, herkomst="test")

        assert oordeel.toegestaan is False
        assert oordeel.categorieen == ("onbeoordeelbaar",)
        assert oordeel.verwijzing


class TestPerTenantUitTeZetten:
    """De klant is verwerkingsverantwoordelijke en moet zijn eigen afweging kunnen maken.

    AVG art. 88 plus, in Nederland, de ondernemingsraad bij monitoringtechnologie. Een wachter
    die niet uit kan, maakt onze klant niet-compliant. Standaard AAN, want de veilige stand is
    de standaard.
    """

    def test_standaard_staat_hij_aan(self) -> None:
        from src.core.governance.input_guard import _regels

        _regels.cache_clear()
        try:
            regels = _regels()
            assert regels.aan is True
            assert regels.uit_voor_tenants == frozenset(), (
                "Er staat een tenant op de uitzonderingslijst. Dat mag, maar dan hoort er een "
                "datum en een reden bij in het regelbestand."
            )
        finally:
            _regels.cache_clear()

    def test_een_uitgezette_tenant_wordt_niet_beoordeeld(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.governance import input_guard

        echt = input_guard._regels()
        monkeypatch.setattr(
            input_guard,
            "_regels",
            lambda: input_guard._Regels(
                aan=True,
                uit_voor_tenants=frozenset({99}),
                blokkeert=echt.blokkeert,
                meldt=echt.meldt,
            ),
        )

        assert input_guard.beoordeel(f"BSN {BSN}", tenant_id=99, herkomst="t").toegestaan is True
        assert input_guard.beoordeel(f"BSN {BSN}", tenant_id=1, herkomst="t").toegestaan is False


class TestGeenTaalmodelInHetBeslispad:
    def test_de_wachter_raakt_geen_llm_en_geen_database(self) -> None:
        """Deterministisch, en dat is een eis en geen voorkeur.

        Een wachter die met een taalmodel redeneert is zelf een AI-systeem en sleept als
        veiligheidscomponent van een hoog-risicosysteem die verplichtingen mee. Bovendien kan
        een prompt-injectie zo'n rechter toespreken. Een redenerende laag mag er later bovenop,
        maar met EEN richting: alleen escaleren.

        Getoetst op de AST van de module, niet op een tekstzoekactie: een naam in een comment of
        een docstring mag deze test niet rood maken, en een echte import wel.
        """
        import ast
        from pathlib import Path

        from src.core.governance import input_guard

        boom = ast.parse(Path(input_guard.__file__).read_text(encoding="utf-8"))
        ingevoerd: set[str] = set()
        for knoop in ast.walk(boom):
            if isinstance(knoop, ast.ImportFrom) and knoop.module:
                ingevoerd.add(knoop.module)
            elif isinstance(knoop, ast.Import):
                ingevoerd.update(alias.name for alias in knoop.names)

        verboden = [
            naam
            for naam in ingevoerd
            if any(
                deel in naam
                for deel in ("llm", "openai", "anthropic", "sqlalchemy", "database", "httpx")
            )
        ]
        assert not verboden, (
            f"De wachter importeert {verboden}. Het beslispad moet deterministisch blijven en "
            "zonder I/O -- dat is wat fail-closed betaalbaar maakt en wat hem buiten de "
            "AI-systeemdefinitie houdt."
        )


class TestGeenValsePositievenOpGewoneTekst:
    """De bevinding die Gate 2 het scherpst maakte: de wachter blokkeerde gewone techniek.

    Gemeten 2026-09-22, VOOR de reparatie: zes van de zes onderstaande teksten werden
    geweigerd. Oorzaken, allebei echt:

    1. `credit_card` had geen controlegetal in `_CHECKSUM_VALIDATORS` -- het patroon is elke
       reeks van 13-20 cijfers, dus een tijdstempel, een buildnummer en een ISBN golden als
       kaartnummer. Dat was een defect volgens het contract dat `gdpr_enforcer` zelf
       opschrijft; er staat nu een Luhn-validator.
    2. `bsn` leunde op de elfproef alleen, en die laat 9,12% van willekeurige negencijferige
       nummers door (1823 van 20.000 trekkingen). In een systeem vol ticketnummers is dat
       onbruikbaar als blokkeergrond; er hoort nu een contextwoord bij.

    Deze klasse is de reden dat een groene suite van 3054 tests dit NIET zag: er zat geen
    enkele ID-vormige string in.
    """

    @pytest.mark.parametrize(
        "tekst,wat",
        [
            ("ts=1726937461123 duurde te lang", "tijdstempel in milliseconden"),
            ("Version 1.2.3 build 20260922145501", "buildnummer"),
            ("order 9780306406157 ontbreekt", "ISBN"),
            ("Open ticket 123456782 graag", "ticketnummer dat de elfproef haalt"),
            ("run_id 1726937461123 is vastgelopen", "run-id"),
            ("Het factuurnummer is 2026-0000-1234-5678", "factuurnummer"),
        ],
    )
    def test_gewone_technische_tekst_wordt_niet_geweigerd(self, tekst: str, wat: str) -> None:
        oordeel = _beoordeel(tekst)

        assert oordeel.toegestaan is True, (
            f"Een {wat} wordt geweigerd. Een wachter die in de weg loopt wordt uitgezet, en "
            f"dan heb je niets. Categorieen: {oordeel.categorieen}"
        )

    def test_een_bsn_zonder_contextwoord_gaat_door_maar_wordt_gemeld(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Doorlaten is hier niet hetzelfde als negeren.

        Een beheerder moet kunnen zien dat er een geldig negencijferig getal langskwam, zonder
        dat een gebruiker erop vastloopt. Daarom `bsn_zonder_context` als MELDING.
        """
        with caplog.at_level(logging.INFO, logger=_REGISTRY_LOGGER):
            oordeel = _beoordeel(f"Open ticket {BSN} graag")

        assert oordeel.toegestaan is True
        gelogd = " ".join(
            r.getMessage() for r in caplog.records if r.name == _REGISTRY_LOGGER
        )
        assert "bsn_zonder_context" in gelogd
        assert BSN not in gelogd

    @pytest.mark.parametrize(
        "tekst",
        [
            "Plan een training voor BSN 123456782",
            "Het burgerservicenummer is 123456782",
            "sofinummer 123456782 graag verwerken",
        ],
    )
    def test_een_bsn_MET_contextwoord_wordt_wel_geweigerd(self, tekst: str) -> None:
        """De tegenrichting: het echte geval moet nog steeds worden gepakt."""
        oordeel = _beoordeel(tekst)

        assert oordeel.toegestaan is False
        assert "bsn" in oordeel.categorieen


class TestGenesteEnMeervoudigeInvoer:
    """Een waarde een JSON-veld verderop zetten mag niet genoeg zijn om erlangs te komen.

    Twee gaten uit Gate 2, beide gemeten:

    - Het AGENTpad liep met `isinstance(waarde, str)` over de bovenste laag, dus
      `{"employees": [{"bsn": "..."}]}` ging erlangs. En `params` is de `json.loads()` van
      modeloutput zonder schema, dus die nesting kiest het model zelf. Die payload gaat naar
      `hitl_tickets.payload`, dat in `tool_broker/redaction.py` als "LIVE en RAUW" staat.
    - Het CHATpad beoordeelde alleen `message` en niet `context` -- hetzelfde verzoek, een
      veld verderop, en `context` heeft geen lengtegrens in het schema.

    `detect_pii` doorzoekt geneste structuren zelf al, dus de eerste versie gooide capaciteit
    weg die er al was.
    """

    def test_een_waarde_in_een_geneste_lijst_wordt_gevonden(self) -> None:
        oordeel = _beoordeel({"employees": [{"bsn": BSN}]})

        assert oordeel.toegestaan is False
        assert "bsn" in oordeel.categorieen

    def test_een_waarde_in_een_geneste_dict_wordt_gevonden(self) -> None:
        oordeel = _beoordeel({"title": "x", "payload": {"rekening": IBAN}})

        assert oordeel.toegestaan is False
        assert "iban" in oordeel.categorieen

    def test_ook_de_sleutelnamen_worden_doorzocht(self) -> None:
        """Op het agentpad kiest het model de sleutels zelf, dus die gaan ook door de wachter.

        **Een gemeten beperking, en die staat hier omdat hij echt is.** Een identificator die
        met een liggend streepje aan een woord vastzit, matcht het patroon NIET:

            "NL91ABNA0417164300"       -> ['iban']
            "iban NL91ABNA0417164300"  -> ['iban']
            "iban:NL91ABNA0417164300"  -> ['iban']
            "iban_NL91ABNA0417164300"  -> []        <-- geen woordgrens voor NL

        Dat komt van `` in het patroon in `gdpr_enforcer`: een `_` is een woordteken. Dit is
        een bestaande eigenschap van de detector en geen regressie van de wachter, en hij is
        hier NIET gerepareerd -- het patroon aanpassen raakt ook de PrivacyOfficer en
        `redact_pii`, en dat is een eigen wijziging met eigen mutatiebewijs. De eerste versie
        van deze test gebruikte precies die vorm en faalde daardoor; dat is hoe ik het vond.
        """
        oordeel = _beoordeel({IBAN: "waarde"})

        assert oordeel.toegestaan is False
        assert "iban" in oordeel.categorieen

    def test_een_gewone_leestool_payload_gaat_door(self) -> None:
        """De tegenrichting -- anders blokkeert elke tool-aanroep."""
        assert _beoordeel({"role": "Engineer", "limit": 50, "offset": 0}).toegestaan is True

    def test_de_doorzochte_tekst_is_begrensd(self) -> None:
        """Onbegrensd rekenwerk in elk verzoek is geen optie.

        `message` staat op 2000 tekens, maar `context` heeft GEEN `max_length` in
        `CopilotTurnRequest` (gemeten 2026-09-22). De patronen lopen over de hele tekst, dus
        zonder grens is het werk per verzoek onbegrensd.
        """
        from src.core.governance.input_guard import _MAX_TEKENS, _te_doorzoeken

        veel = {"a": "x" * (_MAX_TEKENS * 2), "b": "y" * 1000}
        assert len(_te_doorzoeken(veel)) <= _MAX_TEKENS + 1  # +1 voor de scheidingsregel
