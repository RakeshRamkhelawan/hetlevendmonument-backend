"""De keten van een klant is pas een keten als hij doorvalt (BE-LLM-005, fase 3).

**Wat er voor deze knip stond.** `LLMService.for_tenant` nam de EERSTE bruikbare rij en klaar.
De tabel is per ontwerp geordend (`volgorde`), dus er was een keten zonder failover: viel het
eindpunt van een klant uit, dan viel zijn agent uit. ADR-026 par. 1.2.1 belooft die keten met een
circuit breaker; die bestond alleen in de twin-stapel, platformbreed en gevoed uit
omgevingsvariabelen.

**De vier eigenschappen die deze tests vastleggen**, en waarom elk zijn tegenrichting heeft:

1. valt rij 1 om, dan levert rij 2 het antwoord -- en bij een WERKENDE rij 1 wordt rij 2 niet
   aangeroepen, anders is "altijd alles proberen" een geldige implementatie;
2. na de drempel wordt een kapotte rij OVERGESLAGEN in plaats van elke keer opnieuw geprobeerd;
3. de breaker van tenant A raakt tenant B niet. Dit is de belangrijkste en hij komt uit een
   gemeten valkuil: de twin sleutelt zijn breakers op `klassenaam#index`
   (`learning/interfaces/failover_llm_provider.py:70`), en bij een klantketen zouden twee
   tenants daarmee EEN breaker delen;
4. faalt de hele keten, dan komt er een fout en GEEN stille terugval op het platformmodel. Bij
   een lege keten is terugvallen juist (die klant heeft niets ingericht), maar als er rijen
   staan en ze falen allemaal, heeft de klant een verwerker gekozen -- zijn gegevens dan alsnog
   naar onze standaardprovider sturen is een subverwerker-wissel die hij niet goedkeurde.
"""

from __future__ import annotations

import pytest

from collections.abc import AsyncGenerator

from src.core.services.llm.base import (
    LLMConfig,
    LLMContentFilterError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMServiceError,
)
from src.core.services.llm.providers.failover import (
    FailoverProvider,
    KetenSchakel,
    _reset_alle_breakers,
)


@pytest.fixture(autouse=True)
async def _schone_breakers() -> None:
    """De registry is PROCESBREED, dus toestand lekt tussen tests.

    Dat is geen ongeluk maar de bedoeling: een breaker per exemplaar zou zijn tellers
    wissen bij elke nieuwe agenttaak en daarmee nooit iets besparen. Deze fixture is de
    prijs ervan. Hij is toegevoegd nadat de derde test hier ROOD werd op `2 == 3`: de
    eerste test had al een fout op dezelfde sleutel geteld. Dat was meteen het bewijs dat
    de toestand echt procesbreed is.
    """
    await _reset_alle_breakers()


class _NepProvider(LLMProvider):
    """Een provider die antwoordt of valt, en telt hoe vaak hij is aangeroepen."""

    def __init__(
        self,
        naam: str,
        *,
        faalt: bool = False,
        fout: type[Exception] = LLMServiceError,
        stukken: list[str] | None = None,
        faalt_na_het_eerste_stuk: bool = False,
    ) -> None:
        super().__init__(LLMConfig(model="m", base_url="https://" + naam + ".test/v1"))
        self.naam = naam
        self.faalt = faalt
        self.fout = fout
        self.stukken = ["hoi-van-" + naam] if stukken is None else stukken
        self.faalt_na_het_eerste_stuk = faalt_na_het_eerste_stuk
        self.aanroepen = 0
        self.stroom_aanroepen = 0

    def _validate_config(self) -> None:
        return None

    @property
    def provider_name(self) -> str:
        return self.naam

    @property
    def serves_mock(self) -> bool:
        return False

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.aanroepen += 1
        if self.faalt:
            raise self.fout(self.naam + ": eindpunt onbereikbaar")
        return LLMResponse(
            content="antwoord van " + self.naam,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            model="m",
            finish_reason="stop",
        )


    @property
    def supports_streaming(self) -> bool:
        return True

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        self.stroom_aanroepen += 1
        if self.faalt:
            raise self.fout(self.naam + ": stroom kon niet worden geopend")
        for i, stuk in enumerate(self.stukken):
            yield stuk
            if i == 0 and self.faalt_na_het_eerste_stuk:
                raise LLMServiceError(self.naam + ": de verbinding viel weg halverwege")


def _schakel(provider: _NepProvider, tenant_id: int, volgorde: int) -> KetenSchakel:
    return KetenSchakel(
        breaker_id=f"tenant:{tenant_id}|{provider.naam}.test|{volgorde}",
        provider=provider,
    )


def _bericht() -> list[LLMMessage]:
    return [LLMMessage(role="user", content="hallo")]


@pytest.mark.asyncio
async def test_valt_rij_1_om_dan_antwoordt_rij_2() -> None:
    eerste = _NepProvider("eerste", faalt=True)
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    antwoord = await keten.generate(_bericht())

    assert antwoord.content == "antwoord van tweede"
    assert eerste.aanroepen == 1
    assert tweede.aanroepen == 1


@pytest.mark.asyncio
async def test_bij_een_WERKENDE_eerste_rij_blijft_de_tweede_ongemoeid() -> None:
    """De tegenrichting. Zonder deze test is 'altijd de hele keten aflopen' geldig."""
    eerste = _NepProvider("eerste")
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    antwoord = await keten.generate(_bericht())

    assert antwoord.content == "antwoord van eerste"
    assert tweede.aanroepen == 0


@pytest.mark.asyncio
async def test_een_kapotte_rij_wordt_na_de_drempel_OVERGESLAGEN() -> None:
    """Zonder dit blijft elke aanroep op een dood eindpunt wachten tot zijn tijdslimiet."""
    eerste = _NepProvider("eerste", faalt=True)
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    for _ in range(4):
        await keten.generate(_bericht())

    assert eerste.aanroepen == 3, (
        "de kapotte rij is vaker geprobeerd dan de drempel toestaat; de circuit breaker doet "
        "niets of telt per aanroep opnieuw"
    )
    assert tweede.aanroepen == 4


@pytest.mark.asyncio
async def test_de_breaker_van_tenant_A_raakt_tenant_B_NIET() -> None:
    """De belangrijkste: een breaker die per klassenaam sleutelt, lekt tussen klanten."""
    a_kapot = _NepProvider("gedeeld", faalt=True)
    a_reserve = _NepProvider("reserve-a")
    keten_a = FailoverProvider([_schakel(a_kapot, 1, 1), _schakel(a_reserve, 1, 2)])

    for _ in range(4):
        await keten_a.generate(_bericht())

    # Tenant 2 heeft een provider met dezelfde naam op dezelfde plek in zijn keten.
    b_werkend = _NepProvider("gedeeld")
    keten_b = FailoverProvider([_schakel(b_werkend, 2, 1)])

    antwoord = await keten_b.generate(_bericht())

    assert antwoord.content == "antwoord van gedeeld"
    assert b_werkend.aanroepen == 1, (
        "de provider van tenant 2 is overgeslagen omdat die van tenant 1 kapot was -- de "
        "breakersleutel is niet per tenant"
    )


@pytest.mark.asyncio
async def test_een_volledig_gefaalde_keten_geeft_een_FOUT_en_geen_ander_model() -> None:
    eerste = _NepProvider("eerste", faalt=True)
    tweede = _NepProvider("tweede", faalt=True)
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    with pytest.raises(LLMServiceError):
        await keten.generate(_bericht())


@pytest.mark.asyncio
async def test_de_naam_van_de_keten_zegt_welke_rij_hem_bediende() -> None:
    """Zonder dit staat er in het log en het API-antwoord een klassenaam.

    `provider_name` wordt op drie plekken in `src/` gelezen; een samengestelde provider die
    daar "failover" meldt, verbergt welk eindpunt het werk deed.
    """
    eerste = _NepProvider("eerste", faalt=True)
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    await keten.generate(_bericht())

    assert keten.provider_name == "tweede"


@pytest.mark.asyncio
async def test_serves_mock_geldt_voor_de_HELE_keten() -> None:
    """Een samengestelde provider is pas echt als geen van zijn schakels namaak bedient.

    De basisklasse leidt `serves_mock` af uit `provider_name`, en die is hier overschreven --
    precies de constructie waar `test_een_provider_die_zijn_naam_kiest_kiest_ook_serves_mock.py`
    voor bestaat. Een keten met een namaakschakel erin mag in productie niet als echt gelden.
    """

    class _Namaak(_NepProvider):
        @property
        def serves_mock(self) -> bool:
            return True

    echt = _NepProvider("echt")
    namaak = _Namaak("namaak")

    assert FailoverProvider([_schakel(echt, 1, 1)]).serves_mock is False
    assert FailoverProvider([_schakel(echt, 1, 1), _schakel(namaak, 1, 2)]).serves_mock is True


# ------------------------------------------------------------------- het STREAMpad
#
# Dit hele blok ontbrak in ronde 1, en beide Gate 2-reviewers wezen er onafhankelijk op. Het pad
# is live (`OpenAICompatibleProvider.supports_streaming` is True, en `LLMService.stream_generate`
# gaat erdoorheen), het is niet-triviaal (een async generator met failover), en de breaker stond
# er verkeerd om: hij omhulde een lege aanroep die per definitie slaagde. Zelf nagemeten wat dat
# deed: twee mislukte stromen brachten een OPEN breaker via HALF_OPEN terug naar CLOSED.


@pytest.mark.asyncio
async def test_de_stroom_valt_door_naar_de_volgende_schakel() -> None:
    eerste = _NepProvider("eerste", faalt=True)
    tweede = _NepProvider("tweede", stukken=["een", "twee"])
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    stukken = [s async for s in keten.stream(_bericht())]

    assert stukken == ["een", "twee"]
    assert eerste.stroom_aanroepen == 1


@pytest.mark.asyncio
async def test_de_breaker_werkt_OOK_op_het_streampad() -> None:
    """De kern van de reparatie: een kapotte stroomschakel wordt na de drempel overgeslagen.

    Voor de reparatie kon dit niet: de breaker zag op dit pad nooit een fout, dus elke aanroep
    probeerde het dode eindpunt opnieuw tot zijn tijdslimiet.
    """
    eerste = _NepProvider("eerste", faalt=True)
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    for _ in range(4):
        _ = [s async for s in keten.stream(_bericht())]

    assert eerste.stroom_aanroepen == 3, (
        "de kapotte stroomschakel is vaker geprobeerd dan de drempel toestaat; de breaker ziet "
        "op dit pad geen fouten"
    )
    assert tweede.stroom_aanroepen == 4


@pytest.mark.asyncio
async def test_een_mislukte_stroom_maakt_een_OPEN_breaker_niet_weer_gezond() -> None:
    """De tweede helft van dezelfde fout, en de gevaarlijkste.

    Gemeten voor de reparatie: `OPEN -> HALF_OPEN -> CLOSED` na twee mislukte stroompogingen.
    Een dood eindpunt verklaarde zichzelf gezond, ook voor het gewone pad -- beide halen dezelfde
    breaker op onder dezelfde sleutel.
    """
    kapot = _NepProvider("kapot", faalt=True)
    reserve = _NepProvider("reserve")
    keten = FailoverProvider([_schakel(kapot, 1, 1), _schakel(reserve, 1, 2)])

    for _ in range(3):
        await keten.generate(_bericht())  # breaker van 'kapot' gaat OPEN
    aanroepen_na_openen = kapot.aanroepen

    for _ in range(5):
        _ = [s async for s in keten.stream(_bericht())]

    assert await keten.generate(_bericht()) is not None
    assert kapot.aanroepen == aanroepen_na_openen, (
        "het gewone pad probeerde de kapotte schakel opnieuw; mislukte stromen hebben zijn "
        "circuit gesloten"
    )


@pytest.mark.asyncio
async def test_een_storing_NA_het_eerste_stuk_valt_niet_door() -> None:
    """Anders krijgt de aanroeper het begin van het ene antwoord en het vervolg van het andere."""
    eerste = _NepProvider("eerste", stukken=["begin", "rest"], faalt_na_het_eerste_stuk=True)
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    ontvangen: list[str] = []
    with pytest.raises(LLMServiceError):
        async for stuk in keten.stream(_bericht()):
            ontvangen.append(stuk)

    assert ontvangen == ["begin"]
    assert tweede.stroom_aanroepen == 0, (
        "er is doorgevallen nadat er al tekst was geleverd; dan plakt de aanroeper twee "
        "antwoorden aan elkaar zonder dat iets dat meldt"
    )


@pytest.mark.asyncio
async def test_een_LEGE_stroom_is_een_storing_en_geen_stil_succes() -> None:
    """Nul stukjes zonder fout was in de eerste versie een geldig antwoord.

    Dat is de succes-zonder-werk-vorm uit ADR-036: de aanroeper krijgt niets, er valt niets door
    en er staat niets in het log. Het gewone pad weigert een leeg antwoord al (`_lees_antwoord`);
    dit pad doet dat nu ook.
    """
    leeg = _NepProvider("leeg", stukken=[])
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(leeg, 1, 1), _schakel(tweede, 1, 2)])

    stukken = [s async for s in keten.stream(_bericht())]

    assert stukken == ["hoi-van-tweede"]


# ------------------------------------------------------- wat NIET door de keten hoort te lopen


@pytest.mark.asyncio
async def test_een_inhoudsweigering_gaat_omhoog_en_niet_naar_de_volgende_leverancier() -> None:
    """Anders is de keten een manier om een filter te omzeilen door het vaak genoeg te vragen."""
    eerste = _NepProvider("eerste", faalt=True, fout=LLMContentFilterError)
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    with pytest.raises(LLMContentFilterError):
        await keten.generate(_bericht())

    assert tweede.aanroepen == 0


@pytest.mark.asyncio
async def test_een_fout_van_ONSZELF_gaat_omhoog_en_niet_naar_de_volgende_leverancier() -> None:
    """Een bug van ons mag geen wissel van subverwerker veroorzaken.

    `specialist_base._get_llm_service` laat dezelfde vier fouttypen om dezelfde reden door. Een
    laag lager het tegenovergestelde doen betekent: dezelfde prompt naar leverancier 2 en 3
    wegens een `TypeError` van ons -- en die telt dan ook nog als storing op de breaker van een
    kerngezond eindpunt.
    """
    eerste = _NepProvider("eerste", faalt=True, fout=TypeError)
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    with pytest.raises(TypeError):
        await keten.generate(_bericht())

    assert tweede.aanroepen == 0


@pytest.mark.asyncio
async def test_een_verlopen_SLEUTEL_valt_wel_door() -> None:
    """De tegenrichting van de twee tests hierboven, en een bewuste keuze.

    Zonder deze test zou "laat alles omhoog gaan" een geldige implementatie zijn, en dan bestaat
    de keten nergens meer voor: een ingetrokken sleutel op schakel 1 is juist het geval waarvoor
    een klant een tweede provider inricht.
    """
    from src.core.services.llm.base import LLMAuthenticationError

    eerste = _NepProvider("eerste", faalt=True, fout=LLMAuthenticationError)
    tweede = _NepProvider("tweede")
    keten = FailoverProvider([_schakel(eerste, 1, 1), _schakel(tweede, 1, 2)])

    antwoord = await keten.generate(_bericht())

    assert antwoord.content == "antwoord van tweede"
