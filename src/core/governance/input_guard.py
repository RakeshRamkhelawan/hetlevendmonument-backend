"""De inhoudswachter: beoordeelt VRIJE TEKST voordat er iets mee gebeurt.

**Waarom hij bestaat, en waarom NIET in de Council.** De Council beoordeelt vandaag de VORM van
een actie: hij krijgt de toolnaam en de NAMEN van de argumenten, nooit de waarden (BE-AGT-043,
ADR-036 OP-25). Dat is met opzet zo, en de reden is niet weg te nemen door er een officier bij te
zetten: alles wat de Council ziet belandt in `council_decisions` en wordt meegehasht in de
ADR-019-keten, die per ontwerp niet corrigeerbaar of wisbaar is. Vrije tekst daarin botst met AVG
art. 16 en 17. Daar komt bij dat de officieren hun bestuursvlaggen uit diezelfde dict lezen, dus
modeltekst daarin laat een prompt-injectie zijn eigen oordeel meesturen.

Een wachter die ERVOOR staat en NIETS bewaart, heeft geen van beide problemen. En hij staat op de
betere plek: inhoud die er niet hoort te zijn bereikt de tool en het beslissingsregister dan
helemaal niet, in plaats van dat hij achteraf wordt geredigeerd.

**Gemeten 2026-09-21, en dit is de aanleiding.** `GDPREnforcer.detect_pii` werkt:

    "Schrijf een plan voor jan.jansen@klant.test, BSN 123456782, tel 0612345678"
        -> ['email', 'phone', 'bsn']

Diezelfde functie op wat de Council op het agentpad werkelijk binnenkrijgt:

    {"tool": "local__llm_generate", "arg_keys": ["prompt"], "ai_disclosure": True}
        -> []

De capaciteit was er dus al; alleen het kanaal ontbrak.

**Drie ontwerpregels, elk met een reden die geen stijlvoorkeur is.**

1. **Geen I/O, geen database, geen taalmodel in het beslispad.** Dat maakt fail-closed
   betaalbaar: er is bijna geen faaloppervlak, dus "bij twijfel weigeren" legt niet de hele chat
   plat bij de eerste hapering. Het is bovendien een eis uit de AI-verordening: een wachter die
   met een taalmodel redeneert is zelf een AI-systeem, en als veiligheidscomponent van een
   hoog-risicosysteem sleept hij die verplichtingen mee. Regels zijn dat niet. Een redenerende
   laag mag er later bovenop, met EEN richting: alleen escaleren, nooit versoepelen.
2. **De gevonden tekst verlaat deze module NOOIT** -- niet in het antwoord en niet in het log.
   Anders lekt de wachter zelf precies wat hij tegenhield. Dat is geen theoretisch bezwaar: op
   2026-09-21 moest exact die fout in `hr_registry._schedule_training` gerepareerd worden, waar
   een repository-melding de ontvangen trainingsnaam meecitieerde.
3. **De kennis staat in een BESTAND met een versie**, niet in code en niet in een prompt. Een
   regelbestand is te diffen, te reviewen en aan een auditor te laten zien; "het model weet het"
   is bij een AI-verordening-audit geen antwoord.

**WAT DEZE WACHTER IS, EN WAT HIJ NIET IS.** Hij is een vloer onder IDENTIFICATOREN, geen
filter op persoonsgegevens. Dat onderscheid is gemeten en het is groot:

    Jan Jansen functioneert onder de maat en krijgt een verbetertraject   -> DOOR
    Medewerker zit met een burn-out en is zes weken thuis                 -> DOOR
    Salaris wordt verhoogd naar 82000 euro per jaar                       -> DOOR
    Adres: Dorpsstraat 12, 1234 AB Amsterdam                              -> DOOR
    Zij is zwanger en meldt zich in maart af                              -> DOOR

Dat zijn vijf van de vijf, en het zijn precies de gegevens waar de AVG het strengst is
(art. 9). Een patroon vindt VORMEN, geen betekenis, en in een HR-product is de payload die
telt proza over mensen. Wie deze wachter voor een AVG-filter houdt, bouwt op een verkeerde
aanname. Dat is geen tekortkoming die met een extra patroon te repareren is -- daarvoor is de
redenerende laag nodig die alleen mag escaleren, en dat is de volgende knip.

Wat hij WEL doet: een rauwe identificator tegenhouden die per ongeluk in een opdracht belandt.
Dat is een echt en veelvoorkomend geval, en het is het enige dat een patroon met een
controlegetal hard kan aantonen.

**Blokkeren mag alleen wat BEWIJSBAAR is.** Dat is de tweede les uit Gate 2, en hij was duur.
De eerste versie blokkeerde op vier categorieen; gemeten bleken zes van de zes gewone
technische teksten daardoor geweigerd te worden -- een tijdstempel, een buildnummer, een ISBN,
een ticketnummer, een factuurnummer. Daarom nu:

    iban           BLOKKEERT   mod-97-controlegetal, vrijwel geen valse positieven
    credit_card    BLOKKEERT   sinds 2026-09-22 met Luhn (die validator ONTBRAK)
    bsn            BLOKKEERT   alleen MET een contextwoord ernaast -- de elfproef alleen
                               laat 9,12% van willekeurige negencijferige nummers door
                               (gemeten over 20.000 trekkingen), en dit systeem staat vol
                               ticket- en ordernummers
    ssn            meldt       Amerikaans formaat zonder controlegetal; in een Nederlands
                               HR-product is dat vrijwel altijd ruis
    email, phone    meldt      "stuur de uitnodiging naar jan@klant.test" is gewoon werk

Een wachter die in de weg loopt wordt uitgezet, en dan heb je niets -- dat staat in mijn eigen
docstring en was binnen een dag bijna waar geworden.

**De wachter is zelf een verwerking.** Elk bericht lezen om het te beoordelen is het verwerken
van gegevens van een medewerker. De EDPB stelt dat toestemming in een arbeidsverhouding in
principe geen geldige grondslag is, dus dit draait op gerechtvaardigd belang, en in Nederland is
de ondernemingsraad in beeld bij monitoringtechnologie (AVG art. 88). Wij zijn bewerker en de
klant is verantwoordelijke -- daarom kan de wachter per tenant UIT, standaard AAN, en staat die
uitzondering als expliciete regel in het regelbestand in plaats van als stille vlag in een
database. Een klant die hem uitzet, doet dat aantoonbaar en met een datum.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final
from uuid import uuid4

import yaml

logger = logging.getLogger(__name__)

#: Het regelbestand. Naast `shadow_ceo_rules.yml`, in dezelfde vorm, zodat er EEN vorm is voor
#: beleid in dit project en niet twee.
REGELBESTAND: Final[Path] = Path(__file__).resolve().parents[1] / "config" / "input_guard_rules.yml"

#: De VLOER: categorieen die altijd blokkeren, ook als het regelbestand onleesbaar is. Ze staan
#: hier en niet alleen in het bestand, omdat een deploytypfout de vloer niet mag wegnemen -- dat
#: is precies de vorm waarin een bewaker stil verdwijnt.
#:
#: **De vloer kan door het regelbestand alleen worden VERBREED, niet versmald.** Dat hoort hier
#: te staan en niet alleen in de YAML, want de docstring van dat bestand suggereerde eerst dat
#: het blokkeer/meld-onderscheid daar te veranderen was -- en dat is voor deze twee onwaar
#: (Gate 2, 2026-09-22). Een tenant die `iban` wel wil toestaan, kan vandaag alleen de HELE
#: wachter uitzetten; dat is een echte beperking en geen ontwerpkeuze om trots op te zijn.
_VLOER: Final[frozenset[str]] = frozenset({"iban", "credit_card"})

#: `bsn` blokkeert alleen MET een van deze woorden in de buurt. De elfproef alleen is te zwak:
#: gemeten 2026-09-22 passeert 9,12% van willekeurige negencijferige nummers hem (1823 van
#: 20.000), en dit systeem staat vol ticketnummers. Met een contextwoord erbij is de kans op een
#: valse positieve verwaarloosbaar, en het echte geval ("het BSN is 123456782") wordt nog wel
#: gepakt.
_BSN_CONTEXTWOORDEN: Final[tuple[str, ...]] = (
    "bsn",
    "burgerservicenummer",
    "sofinummer",
    "sofi-nummer",
)

#: Hoeveel tekens er maximaal worden doorzocht. De patronen lopen over de hele tekst, en een
#: chatbericht is begrensd (2000 tekens) maar `context` is dat NIET -- dat veld heeft geen
#: `max_length` in `CopilotTurnRequest` (gemeten 2026-09-22). Zonder grens is het rekenwerk dus
#: onbegrensd op een pad dat in elk verzoek zit. Afkappen is hier veilig: de eerste 20.000
#: tekens van een opdracht bevatten de opdracht.
_MAX_TEKENS: Final[int] = 20_000

#: Wat er gebeurt als de wachter zichzelf niet kan uitvoeren.
_ONBEOORDEELBAAR: Final[str] = "onbeoordeelbaar"


@dataclass(frozen=True)
class Oordeel:
    """De uitkomst. Draagt een CATEGORIE en een verwijzing, nooit de gevonden tekst.

    `verwijzing` is willekeurig en NIET afgeleid van de inhoud. Een hash van de tekst zou een
    stabiele aanwijzing naar die persoon zijn en daarmee zelf een persoonsgegeven; een
    willekeurig getal koppelt alleen de melding aan de gebruiker aan de logregel, en verder
    niets.
    """

    toegestaan: bool
    categorieen: tuple[str, ...] = ()
    verwijzing: str | None = None

    def reden(self, taal: str = "nl") -> str:
        """Een leesbare reden ZONDER de gevonden tekst, voor de gebruiker of de agent.

        **Met een taal, sinds Gate 2 (2026-09-22).** De eerste versie gaf altijd Nederlands
        terug, ook aan een Engelstalige gebruiker -- en juist dan faalt het argument waarmee
        deze melding bestaat: hij moet WETEN wat eruit moet, anders is de wachter een muur
        zonder deur (AI Act art. 14).

        Alleen `nl` en `en`, want dat is wat het schema toelaat: `CopilotTurnRequest.language`
        is `Literal["nl", "en"]` (gemeten). `copilot/_refusals.py` heeft er vier, maar de twee
        extra zijn op dat pad niet te bereiken; ze hier overnemen zou dode tekst zijn. Deze
        tabel staat met opzet in dit bestand: `governance` mag niet naar `copilot` importeren,
        dat is de laaggrens de verkeerde kant op.
        """
        if self.toegestaan:
            return ""
        categorieen = ", ".join(self.categorieen)
        if _ONBEOORDEELBAAR in self.categorieen:
            boodschappen = {
                "nl": (
                    "de invoer kon niet worden beoordeeld en is daarom niet uitgevoerd "
                    f"(verwijzing {self.verwijzing})"
                ),
                "en": (
                    "the input could not be screened and was therefore not executed "
                    f"(reference {self.verwijzing})"
                ),
            }
        else:
            boodschappen = {
                "nl": (
                    "de invoer is geweigerd omdat hij gegevens bevat die hier niet thuishoren: "
                    f"{categorieen}. Stel het opnieuw zonder die gegevens "
                    f"(verwijzing {self.verwijzing})"
                ),
                "en": (
                    "the input was refused because it contains data that does not belong here: "
                    f"{categorieen}. Please rephrase it without that data "
                    f"(reference {self.verwijzing})"
                ),
            }
        return boodschappen.get(taal, boodschappen["en"])


@dataclass(frozen=True)
class _Regels:
    aan: bool
    uit_voor_tenants: frozenset[int]
    blokkeert: frozenset[str]
    meldt: frozenset[str]


def _standaardregels() -> _Regels:
    """De terugval als het regelbestand ontbreekt of onleesbaar is.

    Bewust de VLOER en niet "alles blokkeren": het bestand bepaalt wat een organisatie BOVENOP de
    wet wil, de vloer is wat de wet zelf vraagt. Een ontbrekend bestand mag de dienst niet
    platleggen, maar mag de vloer ook niet wegnemen.
    """
    return _Regels(aan=True, uit_voor_tenants=frozenset(), blokkeert=_VLOER, meldt=frozenset())


@lru_cache(maxsize=1)
def _regels() -> _Regels:
    """Lees het regelbestand EEN keer. Buiten het hete pad, want hier zit de enige I/O.

    **ALLES staat in de `try`, en dat is een reparatie uit Gate 2.** In de eerste versie stond
    `int(t)` voor de tenantlijst BUITEN de afscherming, die alleen `OSError` en `YAMLError`
    ving. Een bestand dat geldig parseert maar verkeerd getypt is -- en het commentaar in de
    YAML nodigde daar zelf toe uit met `- 42   # reden` -- gooide dan een `ValueError` omhoog
    tot in de brede `except` van `beoordeel`. Gemeten gevolg: ELKE aanvraag op BEIDE deuren
    geweigerd als `onbeoordeelbaar`, voor ALLE tenants, plus een traceback en een schijfleesactie
    per verzoek -- `lru_cache` bewaart een uitzondering namelijk niet (gemeten: zes ValueErrors
    bij zes aanroepen). Mijn verdediging van fail-closed was "geen I/O, dus bijna geen
    faaloppervlak"; dat gold alleen voor het gelukkige pad, en het gelukkige pad is niet
    waarvoor fail-closed bestaat.
    """
    try:
        rauw = yaml.safe_load(REGELBESTAND.read_text(encoding="utf-8")) or {}

        blokkeert: set[str] = set(_VLOER)
        meldt: set[str] = set()
        for regel in rauw.get("policies") or []:
            if not isinstance(regel, dict) or not regel.get("enabled", True):
                continue
            blokkeert.update(str(c) for c in regel.get("blokkeert") or [])
            meldt.update(str(c) for c in regel.get("meldt") or [])

        return _Regels(
            aan=bool(rauw.get("enabled", True)),
            uit_voor_tenants=frozenset(int(t) for t in rauw.get("uit_voor_tenants") or []),
            blokkeert=frozenset(blokkeert),
            # Een categorie die blokkeert, meldt per definitie ook -- en hij mag niet in beide
            # verzamelingen staan, anders hangt de uitkomst aan de volgorde van twee `if`s.
            meldt=frozenset(meldt - blokkeert),
        )
    except Exception as exc:  # noqa: BLE001 -- zie de docstring: dit MOET alles vangen
        logger.error(
            "input_guard: regelbestand onbruikbaar (%s: %s) -- terugval op de vloer %s. "
            "Dit wordt EEN keer gemeld, niet per verzoek.",
            type(exc).__name__,
            REGELBESTAND,
            sorted(_VLOER),
        )
        # Teruggeven in plaats van laten gooien: dan cachet `lru_cache` de terugval en is er
        # geen schijfwerk en geen traceback per verzoek.
        return _standaardregels()


def _te_doorzoeken(waarden: object) -> str:
    """Plat alle stringwaarden uit een geneste structuur tot EEN doorzoekbare tekst.

    **Waarom geneste waarden meetellen.** Op het agentpad is `params` de `json.loads()` van
    modeloutput zonder schema, dus nesting is volledig door het model te kiezen. De eerste versie
    beoordeelde alleen platte strings (`isinstance(waarde, str)`), waardoor
    `{"employees": [{"bsn": "..."}]}` er ongehinderd langs ging -- en die payload belandt in
    `hitl_tickets.payload`, dat in `tool_broker/redaction.py` als "LIVE en RAUW" staat
    gedocumenteerd. Op het chatpad gold hetzelfde voor `context`, een `dict[str, Any]` die
    rechtstreeks van de client komt en (anders dan `message`) GEEN lengtegrens heeft. Beide
    gevonden in Gate 2 op 2026-09-22.

    Afkappen op `_MAX_TEKENS`: de patronen lopen over de hele tekst en `context` is onbegrensd,
    dus zonder grens is het rekenwerk in elk verzoek onbegrensd.
    """
    stukken: list[str] = []
    totaal = 0

    def _verzamel(waarde: object) -> None:
        nonlocal totaal
        if totaal >= _MAX_TEKENS:
            return
        if isinstance(waarde, str):
            rest = _MAX_TEKENS - totaal
            stukken.append(waarde[:rest])
            totaal += min(len(waarde), rest)
        elif isinstance(waarde, dict):
            for sleutel, binnenwaarde in waarde.items():
                # Ook de SLEUTELS: op het agentpad kiest het model die zelf, dus
                # `{"123456782": "x"}` zou anders een gat zijn.
                _verzamel(str(sleutel))
                _verzamel(binnenwaarde)
        elif isinstance(waarde, (list, tuple, set)):
            for element in waarde:
                _verzamel(element)

    _verzamel(waarden)
    return "\n".join(stukken)


def _bsn_heeft_context(tekst: str) -> bool:
    """Staat er een woord bij dat een negencijferig getal tot een BSN maakt?

    De elfproef alleen is te zwak om op te BLOKKEREN: gemeten 2026-09-22 passeert 9,12% van
    willekeurige negencijferige nummers hem (1823 van 20.000 trekkingen), en dit systeem staat
    vol ticket-, order- en runnummers. Zonder deze eis werd "Open ticket 123456782 graag" een
    geweigerd chatbericht -- gemeten in Gate 2.

    Bewust over de HELE tekst en niet binnen N tekens van de treffer: dat laatste is een tweede
    knop om verkeerd te zetten, en een bericht dat het woord BSN bevat EN een geldig
    negencijferig getal, is in een HR-product hoe dan ook iets om naar te kijken.
    """
    laag = tekst.lower()
    return any(woord in laag for woord in _BSN_CONTEXTWOORDEN)


def beoordeel(waarden: object, *, tenant_id: int, herkomst: str) -> Oordeel:
    """Beoordeel vrije invoer. Geeft een oordeel terug; bewaart niets.

    `waarden` mag een string zijn of een geneste structuur (dict/lijst) -- op het agentpad is dat
    de hele `params`, op het chatpad het bericht EN de meegegeven context. Alle stringwaarden
    EN sleutelnamen worden platgeslagen; zie `_te_doorzoeken`.

    `herkomst` zegt door WELKE deur de invoer binnenkwam (`"chat"` of `"agent:<toolnaam>"`) en
    gaat alleen naar het log, zodat een beheerder kan zien waar iets wordt tegengehouden zonder
    te kunnen zien wat.

    **Fail-closed.** Faalt de beoordeling zelf, dan is het antwoord WEIGEREN. Dat is hier
    betaalbaar omdat deze functie geen I/O doet: het regelbestand is gecachet -- ook zijn
    TERUGVAL, sinds Gate 2 -- en de detectie is puur rekenwerk. Een wachter die bij een fout
    doorlaat, is precies afwezig op het moment dat er iets ongewoons gebeurt.
    """
    try:
        regels = _regels()
        if not regels.aan or tenant_id in regels.uit_voor_tenants:
            return Oordeel(toegestaan=True)

        tekst = _te_doorzoeken(waarden)
        if not tekst.strip():
            return Oordeel(toegestaan=True)

        from src.core.governance.gdpr_enforcer import GDPREnforcer

        # Dezelfde detector als de PrivacyOfficer. Geen tweede patronenlijst: twee kopieen van
        # dezelfde lijst lopen uit elkaar, en dat kostte op 2026-09-21 al een blokkerende
        # bevinding (`BROKER_INJECTED_KEYS`).
        gevonden = set(GDPREnforcer().detect_pii({"tekst": tekst}))

        # `bsn` blokkeert alleen MET een contextwoord; zonder dat blijft hij een MELDING.
        # Zie `_bsn_heeft_context` voor de meting die dit nodig maakte.
        if "bsn" in gevonden and not _bsn_heeft_context(tekst):
            gevonden.discard("bsn")
            gevonden.add("bsn_zonder_context")
    except Exception as exc:  # noqa: BLE001 -- fail-closed, zie de docstring
        verwijzing = uuid4().hex[:12]
        logger.error(
            "input_guard: beoordeling mislukt (%s) -- geweigerd, herkomst=%s tenant=%s ref=%s",
            type(exc).__name__,
            herkomst,
            tenant_id,
            verwijzing,
            exc_info=True,
        )
        return Oordeel(toegestaan=False, categorieen=(_ONBEOORDEELBAAR,), verwijzing=verwijzing)

    geblokkeerd = tuple(sorted(gevonden & regels.blokkeert))
    gemeld = tuple(sorted(gevonden - regels.blokkeert))

    if gemeld:
        # Melden en doorlaten: zakelijk normaal gebruik, maar wel zichtbaar voor een beheerder.
        # `bsn_zonder_context` zit hier ook in -- dan weet een beheerder dat er een geldig
        # negencijferig getal langskwam zonder dat een gebruiker erop is vastgelopen.
        logger.info(
            "input_guard: toegestaan met melding categorieen=%s herkomst=%s tenant=%s",
            list(gemeld),
            herkomst,
            tenant_id,
        )

    if not geblokkeerd:
        return Oordeel(toegestaan=True)

    verwijzing = uuid4().hex[:12]
    # ALLEEN de categorie, de herkomst, de tenant en de verwijzing. Nooit de tekst, nooit een
    # fragment ervan, nooit een hash ervan. Dit is het snijpunt van AI Act art. 12 (er moet een
    # log zijn) en AVG art. 5 (minimaliseer): het log bewijst dat de wachter werkte, zonder zelf
    # een opslag te worden van precies wat hij tegenhield.
    logger.warning(
        "input_guard: geweigerd categorieen=%s herkomst=%s tenant=%s ref=%s",
        list(geblokkeerd),
        herkomst,
        tenant_id,
        verwijzing,
    )
    return Oordeel(toegestaan=False, categorieen=geblokkeerd, verwijzing=verwijzing)
