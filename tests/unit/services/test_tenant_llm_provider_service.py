"""Het schrijfpad naar een klant-eindpunt heeft twee sloten, en beide moeten dicht kunnen.

Besluit Rakesh 2026-09-20: een klant geeft zijn eigen provider op, en een tenant kan op
lokaal-alleen staan. Dat betekent twee controles op het moment van SCHRIJVEN:

1. mag deze tenant uberhaupt extern (`externe_providers_toegestaan`)
2. deugt het adres (SSRF)

Beide zitten in de SERVICE en niet in de repository. Dat is geen smaak: de DSM-regel
(`test_dsm_009_no_medium_backward.py`) verbiedt dat `src/core/repositories` (infra) van
`src/core/security` (auth) afhangt, en die regel wijst iets echts aan -- opslag hoort niet te
weten wat een geldig adres is.

**Waarom de adrescontrole hier een DUBBEL is en niet het echte beleid.** De eerste versie van
dit bestand gebruikte `maak_klant_endpoint_protector()` rechtstreeks. Dat deed een echte
DNS-lookup in een unittest, en daar ging het mis op een manier die een Gate 2-reviewer betrapte:
het "normale externe adres" was `https://api.voorbeeld-leverancier.test`, een naam die NIET
bestaat. Die test slaagde dus niet omdat het slot goed werkte, maar omdat het slot destijds
openstond voor alles wat niet resolveerde. De helft van het bewijs die moet aantonen dat
"weiger alles" geen geldige oplossing is, bewees daarmee de bug in plaats van de eigenschap.

Een dubbel met een expliciet antwoord haalt die verborgen afhankelijkheid weg. Het beleid zelf
-- wat wel en niet mag -- wordt getoetst in `tests/unit/security/test_klant_eindpunt_beleid.py`,
tegen de echte `KlantEindpuntControle`.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from src.core.security.tenant_secret_encryption import TenantSecretEncryption
from src.core.services.tenant_llm_provider_service import (
    ExterneProviderNietToegestaan,
    TenantLLMProviderService,
)

#: Opgebouwd in plaats van opgeschreven: 32 bytes in urlsafe-base64, zoals de echte eis.
HOOFDSLEUTEL = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
GEHEIM = "sk-" + "y" * 20
EXTERN = "https://api.voorbeeld-leverancier.example/v1"
GEWEIGERD_ADRES = "https://dit-adres-wordt-geweigerd.example/v1"


class _NepRepository:
    """Zo min mogelijk: beantwoordt de schakelaarvraag en onthoudt wat er is geschreven."""

    def __init__(self, mag_extern: bool, rijen: list[Any] | None = None) -> None:
        self._mag_extern = mag_extern
        self._rijen = rijen or []
        self.geschreven: list[dict[str, Any]] = []

    async def mag_extern(self, _tenant_id: int) -> bool:
        return self._mag_extern

    async def voeg_toe(self, tenant_id: int, **velden: Any) -> int:
        self.geschreven.append({"tenant_id": tenant_id, **velden})
        return 1

    async def actieve(self, _tenant_id: int) -> list[Any]:
        return self._rijen


class _NepAdresControle:
    """Weigert precies de adressen die de test noemt, en telt de aanroepen.

    Expliciet in plaats van "wat de echte controle er toevallig van vindt": zo staat in elke
    test zwart op wit welk antwoord de controle gaf, en kan geen enkele test per ongeluk
    slagen doordat een naam niet bestaat.
    """

    def __init__(self, weiger: set[str] | None = None, ip: str | None = "203.0.113.7") -> None:
        self.weiger = weiger or set()
        self.aanroepen: list[str] = []
        self.ip = ip

    def validate_url(self, url: str) -> str:
        self.aanroepen.append(url)
        if url in self.weiger:
            raise ValueError(f"SSRF blocked: {url}")
        return url

    def validate_and_resolve(self, url: str) -> tuple[str, list[str]]:
        """Zelfde oordeel, plus de adressen -- net als de echte controle (BE-LLM-004).

        Het dubbel MOET deze methode hebben en niet alleen `validate_url`: sinds het
        vastpinnen is dit de methode die `keten()` gebruikt, en een dubbel dat hem mist laat
        elke rij overslaan met een `AttributeError` die als "adres deugt niet meer" wordt
        gelogd. Dat is precies de vorm waarin een testopstelling verbergt wat hij zou meten.
        """
        gevalideerd = self.validate_url(url)
        return gevalideerd, [self.ip] if self.ip else []


def _service(
    mag_extern: bool,
    *,
    weiger: set[str] | None = None,
    rijen: list[Any] | None = None,
) -> tuple[TenantLLMProviderService, _NepRepository, _NepAdresControle]:
    repo = _NepRepository(mag_extern, rijen)
    controle = _NepAdresControle(weiger)
    service = TenantLLMProviderService(
        repository=repo,  # type: ignore[arg-type]  # het dubbel levert precies de aanroepen die deze weg doet
        encryptie=TenantSecretEncryption(master_key=HOOFDSLEUTEL),
        protector=controle,
    )
    return service, repo, controle


# --------------------------------------------------------------- slot 1: de schakelaar


@pytest.mark.asyncio
async def test_een_tenant_op_lokaal_alleen_krijgt_geen_extern_eindpunt() -> None:
    """Fail-secure bij het schrijven: bewaar geen sleutel die je niet mag gebruiken."""
    service, repo, _ = _service(mag_extern=False)

    with pytest.raises(ExterneProviderNietToegestaan):
        await service.configureer(
            1, volgorde=1, naam="extern", base_url=EXTERN, model="m", api_key=GEHEIM
        )

    assert repo.geschreven == [], "er mag niets zijn opgeslagen"


@pytest.mark.asyncio
async def test_de_schakelaar_gaat_VOOR_de_adrescontrole() -> None:
    """Andersom lekt de foutmelding welke interne adressen bestaan.

    Getoetst op het MECHANISME en niet op de foutmelding: staat de schakelaar uit, dan is de
    adrescontrole nooit aangeroepen. Een test op de tekst van de melding zou ook slagen als de
    volgorde omdraait en de melding toevallig hetzelfde blijft.
    """
    service, _, controle = _service(mag_extern=False, weiger={GEWEIGERD_ADRES})

    with pytest.raises(ExterneProviderNietToegestaan):
        await service.configureer(1, volgorde=1, naam="x", base_url=GEWEIGERD_ADRES, model="m")

    assert controle.aanroepen == [], "het adres is bekeken terwijl de schakelaar al dicht was"


# --------------------------------------------------------------- slot 2: het adres


@pytest.mark.asyncio
async def test_een_adres_dat_de_controle_weigert_wordt_niet_opgeslagen() -> None:
    """Dit is het gat waarop LiteLLM dit jaar twee keer is uitgebuit."""
    service, repo, _ = _service(mag_extern=True, weiger={GEWEIGERD_ADRES})

    with pytest.raises(ValueError, match="niet toegestaan"):
        await service.configureer(
            1, volgorde=1, naam="x", base_url=GEWEIGERD_ADRES, model="m", api_key=GEHEIM
        )

    assert repo.geschreven == []


@pytest.mark.asyncio
async def test_een_gewoon_extern_eindpunt_mag_wel() -> None:
    """Zonder deze helft zou 'weiger alles' een geldige oplossing zijn.

    Het dubbel laat dit adres aantoonbaar DOOR (het staat niet in `weiger`), dus deze test
    slaagt om de bedoelde reden en niet doordat een naam niet op te zoeken is.
    """
    service, repo, controle = _service(mag_extern=True, weiger={GEWEIGERD_ADRES})

    nieuw_id = await service.configureer(
        1, volgorde=1, naam="leverancier", base_url=EXTERN, model="m", api_key=GEHEIM
    )

    assert nieuw_id == 1
    assert controle.aanroepen == [EXTERN]
    assert len(repo.geschreven) == 1


# --------------------------------------------------------------- de sleutel


@pytest.mark.asyncio
async def test_de_sleutel_gaat_VERSLEUTELD_naar_de_opslag() -> None:
    """De repository krijgt nooit een leesbare sleutel te zien."""
    service, repo, _ = _service(mag_extern=True)

    await service.configureer(1, volgorde=1, naam="x", base_url=EXTERN, model="m", api_key=GEHEIM)
    opgeslagen = repo.geschreven[0]["api_key_encrypted"]

    assert opgeslagen is not None
    assert GEHEIM not in opgeslagen


@pytest.mark.asyncio
async def test_zonder_sleutel_blijft_het_veld_leeg() -> None:
    """Een lokaal eindpunt heeft er geen; een verzonnen placeholder zou als geldig meegaan."""
    service, repo, _ = _service(mag_extern=True)

    await service.configureer(1, volgorde=1, naam="x", base_url=EXTERN, model="m", api_key=None)

    assert repo.geschreven[0]["api_key_encrypted"] is None


@pytest.mark.asyncio
async def test_het_opgeslagen_adres_is_het_GEVALIDEERDE_adres() -> None:
    """De service geeft door wat de controle teruggaf, niet wat de aanroeper typte."""
    service, repo, _ = _service(mag_extern=True)

    await service.configureer(1, volgorde=1, naam="x", base_url=EXTERN, model="m")

    assert repo.geschreven[0]["base_url"] == EXTERN


def test_de_ontsleutelde_sleutel_staat_NIET_in_de_repr() -> None:
    """Een enkele `logger.debug("%s", rij)` zou hem anders in het logbestand zetten."""
    from src.core.services.tenant_llm_provider_service import ProviderRij

    rij = ProviderRij(
        volgorde=1,
        naam="x",
        base_url=EXTERN,
        model="m",
        gevalideerd_ip="203.0.113.7",
        api_key=GEHEIM,
    )

    assert GEHEIM not in repr(rij)


# --------------------------------------------------------------- de keten bij GEBRUIK


class _OpgeslagenRij:
    """Wat de repository teruggeeft; alleen de velden die `keten()` leest."""

    def __init__(self, naam: str, base_url: str, api_key_encrypted: str | None) -> None:
        self.id = 1
        self.volgorde = 1
        self.naam = naam
        self.base_url = base_url
        self.model = "m"
        self.api_key_encrypted = api_key_encrypted
        self.actief = True


@pytest.mark.asyncio
async def test_de_keten_is_LEEG_als_de_tenant_niet_extern_mag() -> None:
    """Het eerste slot geldt ook op het LEESpad. Tot 2026-09-21 deed het dat niet.

    Een toetsing door een andere sessie mat dat `keten()` met de schakelaar op FALSE een
    IDENTIEK antwoord gaf als met TRUE -- zelfde rij, zelfde ontsleutelde sleutel. De vlag is
    tegelijk de feature-schakelaar en de terugdraaiknop voor fase 2b; wie hem uitzet om een
    probleem te stoppen, hoorde niets te stoppen.
    """
    service, _, _ = _service(
        mag_extern=False,
        rijen=[_OpgeslagenRij("van de klant", EXTERN, None)],
    )

    assert await service.keten(1) == []


@pytest.mark.asyncio
async def test_een_tegenstrijdige_stand_wordt_LUID_gemeld(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Providers ingericht terwijl de schakelaar uit staat: stil leeg teruggeven is
    "succes zonder werk"."""
    service, _, _ = _service(
        mag_extern=False,
        rijen=[_OpgeslagenRij("van de klant", EXTERN, None)],
    )

    with caplog.at_level("ERROR"):
        await service.keten(1)

    assert any("externe_providers_toegestaan" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_zonder_ingerichte_providers_blijft_het_stil() -> None:
    """De tegenrichting van de vorige test: een tenant die gewoon niets heeft, is geen fout.

    Zonder deze helft zou "meld altijd een fout als de vlag uit staat" een geldige oplossing
    zijn, en dan staat het logbestand vol voor elke tenant die nooit iets instelde.
    """
    service, _, _ = _service(mag_extern=False, rijen=[])

    assert await service.keten(1) == []


@pytest.mark.asyncio
async def test_de_keten_controleert_het_adres_OPNIEUW_bij_gebruik() -> None:
    """Een adres is geen eigenschap van een rij maar van een moment: DNS beweegt.

    Dit is de vorm van CVE-2026-84377 -- bij het inrichten wijst de naam naar een publiek
    adres, bij het gebruiken naar een intern. De bewaker op het schrijfpad kan dat per
    constructie niet zien.
    """
    service, _, controle = _service(
        mag_extern=True,
        weiger={GEWEIGERD_ADRES},
        rijen=[_OpgeslagenRij("verhuisd", GEWEIGERD_ADRES, None)],
    )

    keten = await service.keten(1)

    assert keten == [], "een adres dat nu geweigerd wordt, hoort niet meer in de keten"
    assert controle.aanroepen == [GEWEIGERD_ADRES], "de hercontrole is niet gedaan"


@pytest.mark.asyncio
async def test_de_keten_draagt_het_GEVALIDEERDE_adres_mee() -> None:
    """Zonder dat IP is de hercontrole hierboven een advies (BE-LLM-004).

    De controle zoekt de naam op en toetst de antwoorden; geeft de keten daarna alleen de NAAM
    door, dan zoekt de HTTP-client hem opnieuw op en kan het antwoord een ander adres zijn. Dat
    is DNS-rebinding, in 2026 tweemaal uitgebracht in precies deze constructie. Het IP moet dus
    meereizen, anders bewaakt de vorige test een moment in plaats van een verbinding.
    """
    service, _, _ = _service(mag_extern=True, rijen=[_OpgeslagenRij("klant", EXTERN, None)])

    keten = await service.keten(1)

    assert len(keten) == 1
    assert keten[0].gevalideerd_ip == "203.0.113.7", (
        "de keten geeft het gecontroleerde adres niet door; de aanroeper kan dan niets "
        "vastpinnen en valt terug op een tweede naamsopzoeking"
    )


@pytest.mark.asyncio
async def test_een_naam_zonder_adres_levert_geen_vastpinning_op() -> None:
    """De tegenrichting: levert de opzoeking niets op, dan is er ook niets vast te pinnen.

    Zonder deze helft zou "altijd een IP invullen" een geldige implementatie zijn, en dan zou
    er een verzonnen adres in de configuratie van een klant belanden.
    """
    repo = _NepRepository(True, [_OpgeslagenRij("klant", EXTERN, None)])
    controle = _NepAdresControle(ip=None)
    service = TenantLLMProviderService(
        repository=repo,  # type: ignore[arg-type]  # het dubbel levert precies de aanroepen die deze weg doet
        encryptie=TenantSecretEncryption(master_key=HOOFDSLEUTEL),
        protector=controle,
    )

    keten = await service.keten(1)

    assert len(keten) == 1
    assert keten[0].gevalideerd_ip is None


@pytest.mark.asyncio
async def test_een_onleesbare_sleutel_legt_de_HELE_keten_niet_om() -> None:
    """Een fout in de tweede provider mag de eerste niet meeslepen."""
    encryptie = TenantSecretEncryption(master_key=HOOFDSLEUTEL)
    service, _, _ = _service(
        mag_extern=True,
        rijen=[
            _OpgeslagenRij("werkt", EXTERN, encryptie.encrypt(1, GEHEIM)),
            _OpgeslagenRij("stuk", EXTERN, "v1:dit-is-geen-geldige-versleutelde-tekst"),
        ],
    )

    keten = await service.keten(1)

    assert [rij.naam for rij in keten] == ["werkt"]


@pytest.mark.asyncio
async def test_een_onleesbare_sleutel_wordt_LUID_overgeslagen(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Stil overslaan is 'succes zonder werk' -- precies wat dit project nergens wil."""
    service, _, _ = _service(
        mag_extern=True,
        rijen=[_OpgeslagenRij("stuk", EXTERN, "v1:dit-is-geen-geldige-versleutelde-tekst")],
    )

    with caplog.at_level("ERROR"):
        await service.keten(1)

    # `getMessage()` en niet `record.message`: dat attribuut bestaat pas nadat een formatter
    # het record heeft aangeraakt, en zelf `% args` doen klapt op een record zonder argumenten.
    assert any("overgeslagen" in regel.getMessage() for regel in caplog.records)


@pytest.mark.asyncio
async def test_de_melding_over_een_onleesbare_sleutel_bevat_het_geheim_NIET(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Bij een ontsleutelfout kan de uitzondering brokstukken van de tekst dragen."""
    encryptie = TenantSecretEncryption(master_key=HOOFDSLEUTEL)
    andere_tenant = encryptie.encrypt(2, GEHEIM)
    service, _, _ = _service(
        mag_extern=True,
        rijen=[_OpgeslagenRij("stuk", EXTERN, andere_tenant)],
    )

    with caplog.at_level("ERROR"):
        await service.keten(1)

    assert andere_tenant not in caplog.text
    assert GEHEIM not in caplog.text
