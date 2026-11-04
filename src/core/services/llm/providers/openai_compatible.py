"""Een provider voor ELK OpenAI-compatibel eindpunt -- de anti-lock-in-laag.

**Waarom deze bestaat.** Tot 2026-09-20 had elke leverancier een eigen klasse, en de keuze
zat in de omgevingsvariabelen van de MACHINE: `LLMService()` wordt op ongeveer twintig plekken
aangeroepen zonder tenant. Het hele platform praat dan met wie er bij het uitrollen is
ingevuld. Dat is de lock-in -- niet welke leverancier het is, maar dat de keuze in de uitrol
zit in plaats van bij de klant.

Vrijwel de hele markt spreekt inmiddels hetzelfde protocol: een POST naar `/chat/completions`
onder de meegegeven basis, met een bearer-token en het OpenAI-berichtformaat. Dat geldt voor
DeepSeek, Moonshot/Kimi, OpenAI, Groq, Mistral, vLLM, LM Studio, Ollama (op zijn v1-ingang) en
ook voor Gemini via de compatibiliteitslaag van Google. Met deze klasse is een nieuwe
leverancier daarom een regel CONFIGURATIE en nooit meer een klasse.

**Er staat met opzet GEEN adres van een leverancier in dit bestand.** Zodra hier een adres
verschijnt, kruipt de lock-in terug: dan heeft er weer een voorkeurspositie in onze code, en de
volgende sessie bouwt erop voort. `base_url` is verplicht en komt van de aanroeper. Bewaakt
door `tests/architecture/test_de_generieke_provider_kent_geen_leverancier.py`.

**Wat de gerapporteerde naam raakt -- gemeten, niet aangenomen.** `provider_name` wordt op drie
plekken in `src/` gelezen: `services/llm/service.py:108` (de mock-controle voor productie),
`services/llm/service.py:124` (een logregel) en `services/cva_service.py:394` (een veld in een
API-antwoord). Een eerdere versie van deze toelichting beweerde dat de waarde ook in de
ADR-019-auditketen en in metrics belandt; dat is NAGEMETEN en niet zo -- ADR-019 noemt het
woord provider niet en er is geen metric met dit label. De reden om `provider_name` te
overschrijven blijft staan: de basisklasse leidt hem af van de klassenaam, dus zonder override
zou een aanroep naar DeepSeek in die logregel en dat API-veld als "openaicompatible"
verschijnen.

**Waarom `api_key` mag ontbreken.** Een lokaal eindpunt (Ollama, vLLM, LM Studio) heeft geen
sleutel nodig. Dan gaat er geen Authorization-kop mee. Een cloud-eindpunt antwoordt in dat
geval met 401, en dat is een duidelijke fout -- beter dan een verzonnen placeholder die als
geldige sleutel wordt aangeboden.

**Waar de SSRF-grens hoort, en waarom NIET hier.** Deze klasse eist `http` of `https` en
weigert al het andere (`file:`, `javascript:`, een adres zonder schema). Verder gaat hij niet,
en dat is opzet: een blokkade op private adressen zou `127.0.0.1` uitsluiten, en precies daar
draait het lokale model dat de bodem van de keten is. De host-/netwerkbegrenzing hoort op de
plek waar de URL wordt AANGENOMEN -- de tenantconfiguratie uit fase 2 van het lokaal-eerst-plan
-- met `src/core/security/ssrf_protection.py` (`SSRFProtector.validate_url`), zoals
`src/core/activepieces/client.py::_check_egress` het voor klant-URL's al doet.

**Bijgewerkt 2026-09-23 (BE-LLM-004), en de vorige alinea eindigde niet voor niets met "zet
dat veld in een tenantkolom, dan hoort die controle er EERST bij".** Dat moment is er: sinds
fase 2a komt `base_url` uit `tenant_llm_providers`. De host- en netwerkbegrenzing blijft waar
hij hoorde -- op de plek waar het adres wordt AANGENOMEN en opnieuw waar de keten wordt
opgehaald -- maar EEN deel van de verdediging kan alleen hier staan: het verzoek moet naar het
adres gaan dat gevalideerd IS. Zonder dat zoekt deze client de naam zelf nog een keer op en kan
het antwoord een ander adres zijn (DNS-rebinding, in 2026 tweemaal uitgebracht in precies deze
constructie: Langflow's URL-component en `mcp-atlassian` CVE-2026-27826). Daarvoor zijn
`config.pinned_ip` en `config.sni_hostname`; zie `_chat_url`, `_oorspronkelijke_host` en
`_extensies`. Ze zijn leeg voor de platformstandaard, want daar is geen pad van buiten naar dit
veld -- gemeten 2026-09-20 kent `src/` geen enkele andere bron dan `LLM_BASE_URL` -- en een
lokale bodem op 127.0.0.1 moet onveranderd blijven werken.

(Hier stond eerst datzelfde adres MET schema en poort erbij. De bewaker hierboven werd daar
terecht rood van: hij zoekt naar een adres in dit bestand en kan niet zien of het van een
leverancier is of van de lokale bodem. Een uitzondering toevoegen zou de bewaker verzwakken
voor een toelichting; de toelichting aanpassen kost niets.)
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse

import httpx

from src.core.services.llm.base import (
    LLMAuthenticationError,
    LLMContentFilterError,
    LLMMessage,
    LLMProvider,
    LLMRateLimitError,
    LLMResponse,
    LLMServiceError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

#: Sleutel in `extra_params` waaronder de aanroeper de leveranciersnaam meegeeft.
PROVIDER_LABEL = "provider_label"

#: Schema's die wij naar buiten toe aanroepen. Al het andere wordt geweigerd.
TOEGESTANE_SCHEMAS = ("http", "https")

#: Tekens die in een leveranciersnaam mogen staan. Alles daarbuiten verdwijnt.
#: Reden: de naam komt in een logregel terecht (`service.py:124`), en een regeleinde in een
#: label maakt een tweede, verzonnen logregel. Gemeten 2026-09-20: een label met een `\n`
#: leverde `provider_name = 'deepseek\nwaarschuwing vervalst auditregel'` op.
_LABEL_TOEGESTAAN = re.compile(r"[^a-z0-9._-]+")
_LABEL_MAXLENGTE = 32


def adres_met_vastgepind_ip(base_url: str, ip: str) -> str:
    """Vervang de HOSTNAAM in een adres door een IP, met poort en pad ongemoeid.

    Los van de klasse zodat het mutatiebewijs op de omzetting zelf kan staan en niet op een
    HTTP-aanroep. Drie dingen die hier expres gebeuren:

    - een IPv6-adres komt tussen rechte haken, anders is het adres ongeldig;
    - gebruikersnaam en wachtwoord uit de netlocatie verdwijnen. Ze horen er niet te zijn
      (fase 2a weigert ze bij het opslaan) en een tweede plek waar ze zouden overleven is er
      een te veel;
    - de poort blijft staan. De reden die hier eerst stond ("een klanteindpunt op `:8443` moet
      bereikbaar blijven") is door een Gate 2-reviewer weerlegd en klopte niet:
      `KLANT_EINDPUNT_CONFIG` staat alleen poort 443 toe, dus zo'n rij bestaat niet. De echte
      reden is bescheidener en houdbaarder: deze functie zet een host om en hoort niets anders
      te verliezen, ongeacht welk beleid er vandaag boven hangt. Wordt dat beleid ooit ruimer,
      dan werkt dit nog steeds.
    """
    ontleed = urlparse(base_url)
    gastheer = "[" + ip + "]" if ":" in ip else ip
    poort = ":" + str(ontleed.port) if ontleed.port else ""
    return urlunparse(ontleed._replace(netloc=gastheer + poort))


class OpenAICompatibleProvider(LLMProvider):
    """Praat met elk eindpunt dat het OpenAI-chatprotocol aanbiedt.

    Configuratie:
    - base_url: VERPLICHT, http of https, de basis waaronder `/chat/completions` staat
    - model: VERPLICHT, de modelnaam zoals die leverancier hem noemt
    - api_key: optioneel; weggelaten betekent geen Authorization-kop (lokale eindpunten)
    - extra_params[provider_label]: de naam die in de logregel en het API-veld terechtkomt
    """

    def _validate_config(self) -> None:
        if not self.config.base_url:
            raise ValueError(
                "een OpenAI-compatibele provider heeft 'base_url' nodig; er staat met opzet "
                "geen standaardadres in de code, want dan zou een leverancier een "
                "voorkeurspositie krijgen"
            )
        if not self.config.model:
            raise ValueError(
                "een OpenAI-compatibele provider heeft 'model' nodig; welke modelnaam geldig "
                "is bepaalt de leverancier, dus wij kunnen er geen kiezen"
            )

        ontleed = urlparse(self.config.base_url)
        if ontleed.query or ontleed.fragment:
            # Twee gemeten gevolgen (Gate 2, ronde 3), en ze versterken elkaar:
            # 1. `?key=<sleutel>` is bij meerdere gateways de normale schrijfwijze. Die sleutel
            #    komt dan via `_chat_url` in de foutmelding van httpx en daarmee in het log,
            #    want `_translate` logt met `exc_info=True`.
            # 2. Het adres wordt STIL verkeerd: `/chat/completions` wordt achter de query
            #    geplakt, dus het pad blijft `/v1` en het eindpunt krijgt onzin binnen.
            #    Gemeten: "https://host/v1?key=x" wordt "https://host/v1?key=x/chat/completions".
            #
            # Dit sluit eindpunten uit die hun versie in de query dragen (Azure OpenAI is het
            # bekendste geval). Dat is geen verlies dat hier wordt gemaakt: die vorm zet het
            # pad NA de query en past sowieso niet op `base_url + "/chat/completions"`. Zo'n
            # eindpunt vraagt een eigen provider, en dan is dat een bewuste keuze in plaats van
            # een adres dat stil half werkt.
            raise ValueError(
                "'base_url' mag geen query of fragment bevatten; geef de sleutel mee via "
                "'api_key'. Een query in het adres belandt via de foutafhandeling in het log "
                "en zet het pad naar de chat-ingang op de verkeerde plek."
            )
        if ontleed.username or ontleed.password:
            # Gemeten 2026-09-20 (Gate 2, ronde 2): met
            # `https://gebruiker:geheimpje@host/v1` draagt de foutmelding van httpx de
            # VOLLEDIGE url, en sinds `_translate` met `exc_info=True` logt, belandt die
            # inclusief wachtwoord in het logbestand. `_chat_url` bevat hem ook. De docstring
            # van deze klasse belooft dat de sleutel niet lekt; zonder deze weigering was dat
            # een onware veiligheidsclaim, en die is erger dan geen claim.
            raise ValueError(
                "'base_url' mag geen inloggegevens bevatten; geef de sleutel mee via "
                "'api_key'. Gebruikersnaam of wachtwoord in het adres belandt via de "
                "foutafhandeling in het log."
            )
        if ontleed.scheme not in TOEGESTANE_SCHEMAS or not ontleed.netloc:
            raise ValueError(
                "'base_url' moet een volledig adres zijn met schema http of https, gekregen: "
                f"{ontleed.scheme or '(geen schema)'}. Zonder deze eis wordt 'file:///etc/passwd' "
                "of een kale hostnaam geaccepteerd, en gaat de sleutel van de aanroeper als "
                "bearer-token naar een bestemming die niemand heeft getoetst."
            )

        # Een afsluitende schuine streep verdubbelt straks in het pad. Sommige servers
        # accepteren dat, andere antwoorden met 404; stil afkappen is hier goedkoper dan de
        # aanroeper laten zoeken naar een typefout die niets kapotmaakt.
        self.config.base_url = self.config.base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        """Het opgeschoonde label van de aanroeper, anders de host. Nooit de klassenaam."""
        extra = self.config.extra_params or {}
        rauw = extra.get(PROVIDER_LABEL)
        if isinstance(rauw, str):
            schoon = _LABEL_TOEGESTAAN.sub("", rauw.strip().lower())[:_LABEL_MAXLENGTE]
            if schoon:
                return schoon
        host = urlparse(self.config.base_url or "").hostname
        return host or "openai-compatible"

    @property
    def serves_mock(self) -> bool:
        """NOOIT. Deze klasse praat altijd met een echt eindpunt over HTTP.

        **Waarom dit expliciet moet en niet aan de standaard mag worden overgelaten.** De
        standaard in `LLMProvider.serves_mock` leidt het antwoord af uit `provider_name`, en
        die is hierboven overschreven met een LABEL dat van de aanroeper komt -- sinds
        BE-LLM-003 uit een vrij tekstveld van 64 tekens dat een klant zelf vult. Gemeten
        2026-09-21, met een echt klant-eindpunt. Het adres staat hier bewust NIET: deze laag
        mag geen leveranciersadres noemen, en `test_de_generieke_provider_kent_geen_leverancier.py`
        betrapte een eerdere versie van deze docstring daar meteen op.

            label='mock'      -> provider_name='mock'      serves_mock=True   <-- fout
            label='MOCK'      -> provider_name='mock'      serves_mock=True   <-- fout
            label='mock-prod' -> provider_name='mock-prod' serves_mock=False

        Een klant die zijn provider "mock" noemt, legde daarmee zijn eigen productie-LLM stil
        met een `RuntimeError`. Fail-closed, dus geen lek -- maar wel een storing die de klant
        zelf kan veroorzaken met een naam, en een antwoord dat niet klopt: er komt geen
        namaakmodel aan te pas.

        **De bredere regel die hieruit volgt** (bewaakt door
        `tests/architecture/test_een_provider_die_zijn_naam_kiest_kiest_ook_serves_mock.py`):
        wie `provider_name` overschrijft, moet ook `serves_mock` overschrijven. Precies twee
        klassen doen dat vandaag -- deze en `MockProvider` -- en dat is geen toeval: het zijn
        de enige twee waar de naam niet uit de klasse komt.
        """
        return False

    @property
    def _chat_url(self) -> str:
        """Het volledige adres van de chat-ingang.

        Apart, zodat de typecontrole ziet dat `base_url` gezet IS: `_validate_config` dwingt
        dat af, maar dat is voor pyright niet zichtbaar en `str | None` plus een string is
        geen geldige bewerking.
        """
        base = self.config.base_url
        if not base:
            raise LLMServiceError(self.provider_name + ": base_url ontbreekt")
        ip = self.config.pinned_ip
        if ip:
            base = adres_met_vastgepind_ip(base, ip)
        return base + "/chat/completions"

    def _oorspronkelijke_host(self) -> str:
        """De hostnaam-met-poort zoals de klant hem opgaf, voor de `Host`-kop.

        Nodig zodra het adres naar een IP is omgezet: httpx leidt de `Host`-kop af uit de URL,
        en een server achter naamgebaseerde virtuele hosts krijgt dan een IP te zien en
        antwoordt met de verkeerde site of met een weigering. De httpx-documentatie zet deze
        kop in hetzelfde voorbeeld als `sni_hostname`, en niet voor niets: zonder de kop werkt
        het vastpinnen niet, met de kop alleen is de TLS-controle nog steeds fout.
        """
        ontleed = urlparse(self.config.base_url or "")
        gastheer = ontleed.hostname or ""
        if ":" in gastheer:
            gastheer = "[" + gastheer + "]"
        return gastheer + (":" + str(ontleed.port) if ontleed.port else "")

    def _extensies(self) -> dict[str, str]:
        """De naam waarvoor het certificaat moet gelden, als er is vastgepind.

        Alleen bij `https`: bij `http` bestaat er geen TLS-handdruk en zou de sleutel alleen
        ruis zijn. Zonder deze extensie valideert httpx het certificaat tegen het IP-adres, en
        dat mislukt bij elk normaal certificaat -- het vastpinnen zou dan elk HTTPS-eindpunt
        van een klant onbruikbaar maken in plaats van het te beveiligen.
        """
        naam = self.config.sni_hostname
        if not naam or not self.config.pinned_ip:
            return {}
        if urlparse(self.config.base_url or "").scheme != "https":
            return {}
        return {"sni_hostname": naam}

    def _client(self) -> httpx.AsyncClient:
        """De HTTP-client. Apart, zodat een test hem PER EXEMPLAAR kan vervangen.

        Een test die `httpx.AsyncClient` in deze module patcht, raakt het httpx-PAKKET en
        daarmee elke andere gebruiker in het proces -- `openai_compatible.httpx` is geen
        module-lokale alias maar het pakket zelf. Gemeten 2026-09-20: die patch zette de
        dubbel voor het hele proces. Dat is dezelfde vorm als de gedocumenteerde valkuil
        "de testopstelling zet uit wat je meet". Via deze methode blijft het bij dit exemplaar.

        **`follow_redirects=False` staat er EXPLICIET, en dat is geen dubbelop (Gate 2,
        2026-09-23).** Het is vandaag ook de standaard van httpx (gemeten op 0.28.1), maar het
        vastpinnen uit BE-LLM-004 leunt er volledig op: volgt de client een 3xx, dan zoekt hij
        de nieuwe bestemming ZELF op -- ongevalideerd, ongepind -- en reist `sni_hostname`
        vrolijk mee naar een andere host. Dan is elke regel van die verdediging in een klap
        waardeloos. Een standaardwaarde van een derde partij is geen afspraak van ons; deze
        regel maakt er wel een, en `test_een_omleiding_wordt_niet_gevolgd` bewaakt hem.
        """
        return httpx.AsyncClient(timeout=self.config.timeout, follow_redirects=False)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + str(self.config.api_key)
        if self.config.pinned_ip:
            host = self._oorspronkelijke_host()
            if host:
                headers["Host"] = host
        return headers

    def _payload(
        self,
        messages: list[LLMMessage],
        temperature: float | None,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
        }
        if stream:
            payload["stream"] = True

        # Velden van de aanroeper gaan MEE, en mogen de onze overschrijven. Zonder deze lus
        # is "werkt met elk OpenAI-compatibel eindpunt" meetbaar onwaar, en wel stil.
        #
        # Gemeten 2026-09-20: `max_completion_tokens=100` meegeven leverde een verzoek op met
        # alleen `max_tokens: 1000` -- het veld van de aanroeper werd weggegooid zonder melding.
        # OpenAI heeft `max_tokens` afgeschaft ten gunste van `max_completion_tokens`, en de
        # redeneermodellen (o-serie, GPT-5) WEIGEREN `max_tokens`. Een klant met zo'n model kon
        # deze laag dus niet gebruiken, en zou dat merken aan een fout van de leverancier in
        # plaats van aan een fout van ons.
        #
        # `None` als waarde VERWIJDERT een veld. Dat is nodig en niet sierlijk: wie
        # `max_completion_tokens` stuurt, moet `max_tokens` kwijt kunnen, want samen geven ze
        # bij OpenAI een weigering. `messages` en `stream` liggen vast -- dat zijn geen
        # instellingen maar de vorm van het verzoek zelf.
        vast = {"messages", "stream"}
        for sleutel, waarde in (self.config.extra_params or {}).items():
            if sleutel == PROVIDER_LABEL or sleutel in vast:
                continue
            if waarde is None:
                payload.pop(sleutel, None)
            else:
                payload[sleutel] = waarde
        return payload

    def _translate(self, exc: Exception, *, bij: str) -> LLMServiceError:
        """Zet een fout om in onze eigen fouttypes, ZONDER de sleutel te lekken.

        De sleutel zit in de Authorization-kop; `httpx.HTTPStatusError` draagt de URL en de
        statuscode, niet de koppen. De responsBODY gaat bewust niet mee in de melding: die kan
        van een tussenliggende proxy komen. Wel wordt hij hier gelogd met `exc_info=True`,
        conform `.claude/rules/backend-patterns.md` regel 10 -- anders is het enige
        bewijsmateriaal bij een klanteindpunt dat niet werkt een fouttype zonder context.
        """
        naam = self.provider_name
        host = urlparse(self.config.base_url or "").hostname or "(onbekende host)"
        logger.warning(
            "LLM-aanroep mislukt: provider=%s host=%s stap=%s fout=%s",
            naam,
            host,
            bij,
            type(exc).__name__,
            exc_info=True,
        )
        if isinstance(exc, httpx.TimeoutException):
            return LLMTimeoutError(
                naam + ": " + bij + " afgebroken na " + str(self.config.timeout) + "s"
            )
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            # 403 hoort bij 401: meerdere leveranciers geven 403 bij een ongeldige of
            # ontoereikende sleutel, en de aanroeper moet in beide gevallen naar zijn sleutel
            # kijken en niet naar zijn netwerk.
            if code in (401, 403):
                return LLMAuthenticationError(naam + ": sleutel geweigerd (" + str(code) + ")")
            if code == 429:
                return LLMRateLimitError(naam + ": te veel verzoeken (429)")
            return LLMServiceError(naam + ": " + bij + " gaf HTTP " + str(code))
        return LLMServiceError(naam + ": " + bij + " mislukte (" + type(exc).__name__ + ")")

    def _lees_antwoord(self, data: object) -> LLMResponse:
        """Zet het JSON-antwoord om, en weiger alles dat niet aan het protocol voldoet.

        **Deze methode is de reden dat de klasse bestaat, en hij is twee keer stil geweest.**
        Gemeten 2026-09-20, beide gevallen tegen een dubbel:

        - `{"choices":[{"message":{"content": null}}]}` gaf `content = None` terug in een veld
          dat als `str` is geannoteerd. Dat is geen randgeval: elk OpenAI-compatibel eindpunt
          zet `content` op null bij een tool_calls-antwoord of een weigering.
        - `usage` als string gaf een ONGEVANGEN `AttributeError`, omdat het uitlezen van de
          tokenvelden buiten het try-blok stond. De basisklasse belooft dat alles als
          `LLMServiceError`-familie naar buiten komt; een aanroeper met
          `except LLMServiceError` laat zo'n AttributeError door naar boven.

        Een leeg of ontbrekend antwoord mag NOOIT als geslaagd doorgaan: dan bouwt de agent
        verder op niets, en dat is de faalvorm uit ADR-036 paragraaf 1.
        """
        naam = self.provider_name
        if not isinstance(data, dict):
            raise LLMServiceError(naam + ": antwoord is geen JSON-object")

        keuzes = data.get("choices")
        if not isinstance(keuzes, list) or not keuzes or not isinstance(keuzes[0], dict):
            raise LLMServiceError(naam + ": antwoord heeft geen bruikbare 'choices'")
        keuze = keuzes[0]

        # **De REDEN wordt gelezen voordat we over de lege inhoud vallen (Gate 2, 2026-09-24).**
        # Een OpenAI-compatibel eindpunt dat de inhoud WEIGERT zet `content` op null met
        # `finish_reason: "content_filter"`. Tot deze wijziging viel dat in de generieke fout
        # hieronder, en daarmee ging een weigering van leverancier 1 als gewone storing de
        # failoverketen in: dezelfde tekst naar leverancier 2, en 3, tot er een ja zei. Dat is
        # letterlijk "een filter omzeilen door het vaak genoeg te vragen" -- precies wat de
        # docstring van `FailoverProvider` verbiedt terwijl er niets was dat het waarmaakte.
        # Tweede gevolg: die weigering telde als storing op de breaker van een GEZOND eindpunt.
        #
        # De controle in `LLMService.generate` (regel ~354) zag dit geval per constructie niet:
        # die kijkt naar `response.finish_reason` en er komt bij een weigering geen response.
        reden_ruw = keuze.get("finish_reason")
        if isinstance(reden_ruw, str) and reden_ruw == "content_filter":
            raise LLMContentFilterError(
                naam + ": de leverancier heeft de inhoud geweigerd (finish_reason="
                "content_filter). Dit is geen storing van het eindpunt en hoort dus niet naar "
                "een volgende leverancier te gaan."
            )

        bericht = keuze.get("message")
        inhoud = bericht.get("content") if isinstance(bericht, dict) else None
        if not isinstance(inhoud, str) or not inhoud.strip():
            # Expliciet ook de lege string: een antwoord zonder tekst is voor deze laag geen
            # geldig resultaat, en de aanroeper kan er niets mee.
            raise LLMServiceError(
                naam + ": antwoord volgt het OpenAI-formaat niet "
                "(choices[0].message.content is geen niet-lege tekst)"
            )

        gebruik = data.get("usage")
        if not isinstance(gebruik, dict):
            gebruik = {}

        def getal(veld: str) -> int:
            waarde = gebruik.get(veld)
            return waarde if isinstance(waarde, int) and not isinstance(waarde, bool) else 0

        model = data.get("model")
        reden = keuze.get("finish_reason")
        return LLMResponse(
            content=inhoud,
            prompt_tokens=getal("prompt_tokens"),
            completion_tokens=getal("completion_tokens"),
            total_tokens=getal("total_tokens"),
            model=model if isinstance(model, str) and model else str(self.config.model),
            finish_reason=reden if isinstance(reden, str) else "stop",
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload = self._payload(messages, temperature, max_tokens, stream=False)
        try:
            async with self._client() as client:
                response = await client.post(
                    self._chat_url,
                    json=payload,
                    headers=self._headers(),
                    extensions=self._extensies(),
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise self._translate(exc, bij="aanroep") from exc

        # BUITEN het try-blok hierboven, en dat is opzet: `_lees_antwoord` gooit zelf al
        # `LLMServiceError` en die mag niet door `_translate` worden omgezet in "aanroep
        # mislukte (LLMServiceError)" -- dan verdwijnt de reden.
        return self._lees_antwoord(data)

    @property
    def supports_streaming(self) -> bool:
        return True

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stuur het antwoord stukje bij stukje door.

        **Over de tijdsgrens.** `self.config.timeout` is bij httpx een grens PER brok, niet
        over de hele stroom. Een eindpunt dat elke 29 seconden een teken stuurt, houdt de
        verbinding dus open. Er staat hier bewust geen tweede timer: het piloot-pad begrenst de
        hele aanroep al op `budget.timeout_seconds` via `_run_within_budget`
        (`als/agents/specialist_base.py`), en twee timers die elkaar niet kennen leveren een
        onverklaarbare afbreking op. Voor een aanroeper ZONDER zo'n budget is er vandaag geen
        wandklokgrens -- dat is een bekende grens van deze laag, niet een vergeten regel.
        """
        payload = self._payload(messages, temperature, max_tokens, stream=True)
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST",
                    self._chat_url,
                    headers=self._headers(),
                    json=payload,
                    extensions=self._extensies(),
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        # Op het scheidingsteken splitsen en daarna de witruimte weghalen, NIET
                        # op de prefix "data: " met spatie toetsen. De SSE-specificatie staat
                        # `data:{...}` zonder spatie toe en meerdere servers sturen het zo.
                        # Gemeten 2026-09-20: met de oude toets leverde zo'n stroom een LEGE
                        # lijst op, zonder fout en zonder log -- in een laag die per definitie
                        # met onbekende servers praat is dat het hoofdgeval, geen randgeval.
                        if not line.startswith("data:"):
                            continue
                        brok = line.split(":", 1)[1].strip()
                        if brok == "[DONE]":
                            return
                        try:
                            deel = json.loads(brok)["choices"][0]["delta"].get("content", "")
                        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                            continue
                        if deel:
                            yield deel
        except Exception as exc:
            raise self._translate(exc, bij="stroom") from exc
