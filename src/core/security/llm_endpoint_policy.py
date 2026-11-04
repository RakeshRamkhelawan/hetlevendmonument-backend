"""Het beveiligingsbeleid voor een LLM-eindpunt dat een KLANT opgeeft.

Dit hoort in `src/core/security/` en niet bij de service die het gebruikt: het is een
beveiligingsbeslissing, en de DSM-indeling rekent deze map tot `auth`. De servicelaag krijgt de
uitkomst ingespoten in plaats van hem te importeren -- zie
`src/core/services/tenant_llm_provider_service.py` voor waarom (de koppelingsbudgetten van
`agent_runtime` zijn vol, en injectie is hier toch al het betere ontwerp).

**Waarom deze grenzen.** Bij LiteLLM, het bekendste OpenAI-compatibele doorgeefluik, is precies
dit gat dit jaar twee keer uitgebuit: CVE-2026-59823 (een genest configuratieveld langs de
controle heen) en CVE-2026-84377, waarbij de proxy de opgeslagen sleutels van de operator
meestuurt naar een adres dat de gebruiker kiest. Zolang het adres uit de uitrol komt is er geen
pad van buiten; zodra een klant het veld vult, is dit de enige rem.

**Waarom `SSRFProtector` hier NIET rechtstreeks wordt gebruikt.** Twee Gate 2-rondes
betrapten vier gaten, en alle vier zijn nagemeten voordat er iets veranderde:

1. **`SSRFProtector` faalt OPEN als DNS niets oplevert** (`ssrf_protection.py:500-508`:
   "DNS resolution failed - log warning but allow"). Gemeten met de oude configuratie:
   `http://interne-app.corp`, `https://2130706433/` (de decimale vorm van 127.0.0.1) en
   `http://ollama/v1` werden alle drie TOEGESTAAN. Voor een callback-URL is die keuze
   verdedigbaar; voor de enige rem op een klant-eindpunt is het een gat, want een naam die op
   de controlerende machine niet bestaat, bestaat in het uitrolnetwerk vaak wel.
2. **Inloggegevens in de URL passeerden.** `https://gebruiker:geheim@api.example.com/v1` werd
   toegestaan en beland dan in `base_url` -- een gewone, ONVERSLEUTELDE kolom die het
   leesendpoint gewoon teruggeeft. Daarmee is de belofte "de sleutel komt er nooit uit" te
   omzeilen met een URL.
3. **`http` naar een publiek adres passeerde.** De opgeslagen klantsleutel gaat als
   bearer-token mee; over klare lijn is dat weggeven. Lokale eindpunten (het enige echte
   argument voor `http`) worden hier toch al geweigerd.
4. **Drie IPv6-vormen liepen er in de TWEEDE ronde nog steeds doorheen:** `[::]` (het
   onbepaalde adres, dat bij verbinden op loopback uitkomt), `[2002:a9fe:a9fe::]` (6to4)
   en `[64:ff9b::a9fe:a9fe]` (NAT64) -- allemaal wegen naar 169.254.169.254 of naar de
   eigen machine. De IPv4-tegenhanger `0.0.0.0` werd WEL geweigerd, en juist die
   asymmetrie maakt het een omissie in plaats van een keuze. Zie `_eis_publiek_adres`.

`ssrf_protection.py` zelf blijft ONGEMOEID: die heeft andere aanroepers die op het huidige
gedrag rekenen, en hun gedrag veranderen om ons probleem op te lossen is de verkeerde volgorde.
De strengere eisen staan daarom in de laag eromheen.
"""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlsplit

from src.core.security.ssrf_protection import (
    SSRFConfig,
    SSRFProtector,
    SSRFValidationError,
    SSRFViolationType,
)

logger = logging.getLogger(__name__)

#: De well-known NAT64-reeks (RFC 6052). `is_global` kijkt hier NIET doorheen -- gemeten
#: 2026-09-20: `64:ff9b::a9fe:a9fe` (dat is 169.254.169.254) telt als globaal. De enige
#: ingebedde vorm die apart uitgepakt moet worden; 6to4 en IPv4-mapped worden door
#: `is_global` zelf al correct beoordeeld.
_NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")

#: Loopback, prive-netwerken, link-local en metadata-diensten staan UIT -- dat zijn de
#: bestemmingen waarmee een SSRF-aanval iets bereikt wat de aanvrager zelf niet mag zien.
#:
#: Alleen `https` en alleen poort 443. Dat is strenger dan de eerste versie (die `http` en
#: poort 80 ook toestond) en het kost niets: een klant-eindpunt op een prive-adres wordt hier
#: sowieso geweigerd, dus er bleef geen legitiem `http`-geval over -- alleen het risico dat de
#: sleutel over klare lijn gaat.
#:
#: Ons eigen Ollama komt hier nooit langs: dat adres staat in `LLM_BASE_URL` in de uitrol en
#: nooit in een tenantrij.
KLANT_EINDPUNT_CONFIG = SSRFConfig(
    allowed_schemes=frozenset({"https"}),
    allowed_ports=frozenset({443}),
    allow_private_networks=False,
    allow_loopback=False,
    allow_link_local=False,
    allow_metadata_services=False,
)


class KlantEindpuntControle:
    """`SSRFProtector` plus de vier eisen die deze toepassing extra stelt.

    De naam `validate_url` is met opzet gelijk aan die van `SSRFProtector`: de servicelaag
    kent alleen het Protocol `_AdresControle`, en de architectuurbewaker
    `test_elk_schrijfpad_naar_een_klanteindpunt_wordt_gevalideerd.py` zoekt naar precies die
    aanroep. Een andere naam zou de bewaker stil blind maken.
    """

    def __init__(self, protector: SSRFProtector) -> None:
        self._protector = protector

    def validate_url(self, url: str) -> str:
        """Geef de URL terug als hij door ALLE controles komt.

        Volgorde: eerst de structuurcontroles (geen netwerkverkeer), dan de bestaande
        SSRF-controle, dan de bestemmingseis. Zo kost een onzinnige URL geen DNS-lookup.

        Gooit `SSRFValidationError` bij een geweigerde bestemming. Let op: dat is niet het
        ENIGE fouttype dat hieruit kan komen, en die nuance stond hier eerst ten onrechte
        als absolute belofte. Gemeten 2026-09-20: een hostnaam die de IDNA-codering niet
        overleeft geeft `UnicodeEncodeError`, en een poortnummer boven 65535 geeft
        `ValueError` uit `urlsplit`. Beide aanroepers (`configureer` en `keten`) vangen
        breed en degraderen veilig -- een 400 respectievelijk een overgeslagen rij -- dus
        dit is een onnauwkeurig contract en geen gat. Het staat er omdat een lezer die op
        de belofte bouwt en alleen `SSRFValidationError` vangt, er wel een van maakt.
        """
        self._weiger_inloggegevens(url)
        gevalideerd: str = self._protector.validate_url(url)
        self._eis_een_publieke_bestemming(url)
        return gevalideerd

    def validate_and_resolve(self, url: str) -> tuple[str, list[str]]:
        """Hetzelfde oordeel, plus de adressen waar de naam naartoe wees.

        **Waarom deze methode hier MOET staan (BE-LLM-004, 2026-09-23).** Sinds fase 2b geeft
        `keten()` het gecontroleerde IP door zodat de HTTP-client daarheen verbindt in plaats
        van de naam opnieuw op te zoeken -- zonder dat is de hele adrescontrole een advies dat
        DNS-rebinding niet tegenhoudt. Die keten roept dus `validate_and_resolve` aan.

        Deze klasse had alleen `validate_url`. Was hij hier niet bijgekomen, dan had ELKE rij
        van ELKE klant in productie een `AttributeError` gegeven, netjes gelogd als "het
        opgeslagen adres doorstaat de adrescontrole niet meer" -- een foutmelding die naar de
        klant wijst terwijl het probleem bij ons zit. De unittests zagen dat niet, want hun
        dubbel had de methode wel. De typecontrole zag het wel; dat is waarvoor `_AdresControle`
        een Protocol is.

        De VIER extra eisen van deze klasse gelden onverkort: de opzoeking hangt aan
        `validate_url` hieronder, dus wie deze weg neemt krijgt dezelfde weigeringen.
        """
        gevalideerd = self.validate_url(url)
        _, adressen = self._protector.validate_and_resolve(gevalideerd)
        return gevalideerd, adressen

    @staticmethod
    def _weiger_inloggegevens(url: str) -> None:
        """Een geheim hoort in het sleutelveld, niet in het adres.

        Ook een query en een fragment gaan eruit: een `?api-key=...` is dezelfde achterdeur,
        en een OpenAI-compatibel basis-adres heeft er geen van beide nodig. Deze eis staat
        LOS van de SSRF-controle -- het gaat hier niet om de bestemming maar om wat er
        onversleuteld in de kolom zou belanden.
        """
        ontleed = urlsplit(url)
        if ontleed.username or ontleed.password:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.INVALID_URL,
                message=(
                    "het adres bevat inloggegevens; zet een sleutel in het veld api_key, "
                    "niet in de URL (die kolom is niet versleuteld en is leesbaar terug)"
                ),
            )
        if ontleed.query or ontleed.fragment:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.INVALID_URL,
                message=(
                    "het adres bevat een query of fragment; geef alleen het basis-adres op "
                    "(bijvoorbeeld https://api.voorbeeld.com/v1)"
                ),
            )

    def _eis_een_publieke_bestemming(self, url: str) -> None:
        """Twee gevallen, twee eisen -- en het tweede was een gat.

        **Een letterlijk IP-adres moet PUBLIEK zijn.** De eerste versie liet dit pad helemaal
        met rust, met als redenering dat `SSRFProtector` een letterlijk IP toch al toetst. Dat
        klopt voor IPv4 en niet voor IPv6, en een Gate 2-reviewer mat het verschil:
        `https://0.0.0.0/v1` werd geweigerd (die reeks staat in de gereserveerde lijst) maar
        `https://[::]/v1` niet -- terwijl verbinden met het onbepaalde adres op loopback
        uitkomt. Ook `https://[2002:a9fe:a9fe::]/v1` (6to4 van 169.254.169.254) en
        `https://[64:ff9b::a9fe:a9fe]/v1` (NAT64 van hetzelfde metadata-adres) kwamen erdoor.
        Die asymmetrie maakt het een omissie en geen keuze.

        `is_global` vervangt daarom een handonderhouden lijst: hij vangt het onbepaalde adres,
        loopback, prive-reeksen, link-local en 6to4 in een uitdrukking. Gemeten wel, gemeten
        niet: NAT64 (`64:ff9b::/96`) telt bij `is_global` als globaal, ongeacht welk IPv4-adres
        erin verstopt zit. Dat ene geval wordt daarom apart uitgepakt.

        **Een NAAM moet opzoekbaar zijn.** Daar is `SSRFProtector` fail-OPEN
        (`ssrf_protection.py:500-508`); hier is hij fail-closed. Zie de moduledocstring.
        """
        naam = urlsplit(url).hostname
        if not naam:
            return
        try:
            adres = ipaddress.ip_address(naam)
        except ValueError:
            pass  # geen letterlijk IP -- dan moet de naam resolveren
        else:
            self._eis_publiek_adres(adres, url)
            return

        # **De OPGEZOCHTE adressen gaan door dezelfde eis (2026-09-23, Gate 2 op BE-LLM-004).**
        # Hier stond alleen de opzoekbaarheidscontrole hieronder, en `_eis_publiek_adres` draaide
        # uitsluitend op de tak met een letterlijk IP. Gemeten wat daar doorheen kwam zodra de
        # klant een NAAM opgaf die hij zelf in DNS beheert:
        #
        #     ::                    -> TOEGESTAAN        2002:a9fe:a9fe:: (6to4)  -> TOEGESTAAN
        #     64:ff9b::a9fe:a9fe    -> TOEGESTAAN        ::1, fc00::1             -> geweigerd
        #
        # Dat zijn exact de drie vormen waarvoor deze klasse bestaat (zie de moduledocstring):
        # `SSRFProtector` kent ze niet in `IPV6_BLOCKED_NETWORKS`, en de IPv4-tegenhanger
        # (169.254.169.254) is wel dicht. Zolang `keten()` nul aanroepers had was dat een
        # validatiekwestie; sinds BE-LLM-004 is het opgezochte adres het adres waar de
        # verbinding daadwerkelijk heen gaat. Een eis die alleen geldt voor wat de klant
        # INTYPT, is dan geen eis meer.
        opgezochte_adressen = self._protector._resolve_hostname(naam)
        for opgezocht in opgezochte_adressen:
            self._eis_publiek_adres(ipaddress.ip_address(opgezocht), url)

        if not opgezochte_adressen:
            # Bewust de private methode van de protector en niet een eigen getaddrinfo:
            # dan geldt dezelfde time-out en dezelfde foutafhandeling als in de controle
            # die er direct naast draait. Twee verschillende resolvers zouden twee
            # verschillende antwoorden kunnen geven, en dat is precies het gat.
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.HOSTNAME_RESOLUTION_FAILED,
                message=(
                    f"de naam '{naam}' is hier niet op te zoeken. Een eindpunt dat wij niet "
                    "kunnen vinden is onbruikbaar, en een naam die hier niet bestaat maar in "
                    "het uitrolnetwerk wel is precies het SSRF-gat"
                ),
            )

    @staticmethod
    def _eis_publiek_adres(adres: ipaddress.IPv4Address | ipaddress.IPv6Address, url: str) -> None:
        """Weiger elk letterlijk IP dat niet publiek routeerbaar is."""
        echt = adres
        if isinstance(adres, ipaddress.IPv6Address) and adres in _NAT64_PREFIX:
            # NAT64 (RFC 6052) zet een IPv4-adres in de onderste 32 bits van een IPv6-adres.
            # `is_global` kijkt daar niet doorheen: `64:ff9b::a9fe:a9fe` telt als globaal
            # terwijl het 169.254.169.254 is. 6to4 en IPv4-mapped hoeven dit niet -- gemeten:
            # daar geeft `is_global` al het antwoord van het INGEBEDDE adres.
            echt = ipaddress.IPv4Address(int(adres) & 0xFFFFFFFF)

        if not echt.is_global:
            raise SSRFValidationError(
                url=url,
                violation_type=SSRFViolationType.RESERVED,
                message=(
                    f"het adres '{echt}' is niet publiek routeerbaar; een klant-eindpunt hoort "
                    "op het open internet te staan, niet op een adres dat vanaf onze server "
                    "iets anders bereikt dan vanaf het zijne"
                ),
            )


def maak_klant_endpoint_protector() -> KlantEindpuntControle:
    """De controle die een door een klant opgegeven eindpunt moet doorstaan."""
    return KlantEindpuntControle(SSRFProtector(KLANT_EINDPUNT_CONFIG))
