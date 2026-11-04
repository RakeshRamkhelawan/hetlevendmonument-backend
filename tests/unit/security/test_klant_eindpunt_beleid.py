"""Wat een door een KLANT opgegeven LLM-eindpunt moet doorstaan.

Dit toetst `KlantEindpuntControle` zelf -- het beleid. De orkestratie eromheen staat in
`tests/unit/services/test_tenant_llm_provider_service.py` en gebruikt daar een dubbel.

**Waarom de naamresolutie hier gestuurd wordt en niet echt gebeurt.** Een unittest die
`getaddrinfo` aanroept, meet de DNS-resolver van de machine mee. Dat is niet alleen traag maar
ook onbetrouwbaar als bewijs: bij een resolver met een wildcard (sommige providers geven op elke
onbestaande naam een advertentie-adres terug) valt een test om die hier hoort te slagen, en
andersom. De vorige versie van deze code werd door precies die verwevenheid onderuitgehaald: een
test die "een normaal extern adres mag" moest aantonen, slaagde uitsluitend doordat de naam NIET
bestond en de controle toen nog fail-open was.

Elke test hieronder zegt daarom expliciet wat de naam oplevert. De echte `SSRFProtector` doet
verder gewoon zijn werk -- alleen de opzoekstap is vervangen.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.core.security.llm_endpoint_policy import (
    KLANT_EINDPUNT_CONFIG,
    KlantEindpuntControle,
    maak_klant_endpoint_protector,
)
from src.core.security.ssrf_protection import SSRFProtector, SSRFValidationError

#: Een gewoon publiek adres. Er gaat geen verkeer heen -- de resolutie is gestuurd en er wordt
#: niets aangeroepen -- maar het moet wel als publiek TELLEN.
#:
#: Bewust NIET een adres uit TEST-NET (RFC 5737, 203.0.113.0/24): gemeten 2026-09-20 rekent
#: `SSRFProtector` die reeksen tot `reserved` en weigert ze. Dat is terecht, en het is precies
#: waarom je zo'n aanname niet ongemeten in een testconstante zet.
PUBLIEK_ADRES = "93.184.216.34"


@pytest.fixture
def controle(monkeypatch: pytest.MonkeyPatch) -> Iterator[KlantEindpuntControle]:
    """De ECHTE controle, met een naamresolutie die altijd hetzelfde publieke adres geeft."""
    protector = SSRFProtector(KLANT_EINDPUNT_CONFIG)
    monkeypatch.setattr(protector, "_resolve_hostname", lambda _naam: [PUBLIEK_ADRES])
    yield KlantEindpuntControle(protector)


@pytest.fixture
def controle_zonder_dns(monkeypatch: pytest.MonkeyPatch) -> Iterator[KlantEindpuntControle]:
    """Dezelfde controle, maar de naam is nergens op te zoeken."""
    protector = SSRFProtector(KLANT_EINDPUNT_CONFIG)
    monkeypatch.setattr(protector, "_resolve_hostname", lambda _naam: [])
    yield KlantEindpuntControle(protector)


def test_een_gewoon_extern_https_eindpunt_mag(controle: KlantEindpuntControle) -> None:
    """Zonder deze test is 'weiger alles' een geldige oplossing."""
    adres = "https://api.voorbeeld-leverancier.example/v1"

    assert controle.validate_url(adres) == adres


def test_een_naam_die_nergens_resolveert_wordt_GEWEIGERD(
    controle_zonder_dns: KlantEindpuntControle,
) -> None:
    """De kern van de Gate 2-bevinding: `SSRFProtector` liet dit DOOR.

    `ssrf_protection.py:500-508` keert stil terug als DNS niets oplevert. Voor een callback-URL
    is dat verdedigbaar; hier betekent het dat een interne naam die op de controlerende machine
    niet bestaat maar in het uitrolnetwerk wel, er gewoon langs komt.
    """
    with pytest.raises(SSRFValidationError) as fout:
        controle_zonder_dns.validate_url("https://interne-app.corp/v1")

    assert fout.value.violation_type.value == "hostname_resolution_failed"


def test_een_letterlijk_publiek_IP_mag_ook_zonder_naamresolutie(
    controle_zonder_dns: KlantEindpuntControle,
) -> None:
    """De andere richting van de vorige test.

    Een letterlijk IP gaat in `validate_url` door `_validate_ip_address` en komt nooit bij de
    naamresolutie. Zou de fail-closed-eis ook daarop slaan, dan weigerde de controle een geldig
    adres zonder iets te winnen -- dat is de vorm waarin "weiger alles" binnensluipt.
    """
    adres = f"https://{PUBLIEK_ADRES}/v1"

    assert controle_zonder_dns.validate_url(adres) == adres


@pytest.mark.parametrize(
    "adres",
    [
        "https://gebruiker:wachtwoord@api.voorbeeld.example/v1",
        "https://:wachtwoord@api.voorbeeld.example/v1",
    ],
)
def test_inloggegevens_in_het_adres_worden_geweigerd(
    controle: KlantEindpuntControle, adres: str
) -> None:
    """De achterdeur naast de versleutelde sleutel.

    `base_url` is een gewone, ONVERSLEUTELDE kolom die het leesendpoint teruggeeft. Een geheim
    dat daarin past, omzeilt de hele belofte "de sleutel komt er nooit uit".
    """
    with pytest.raises(SSRFValidationError, match="inloggegevens"):
        controle.validate_url(adres)


@pytest.mark.parametrize(
    "adres",
    [
        "https://api.voorbeeld.example/v1?api-key=zzzzzzzzzzzz",
        "https://api.voorbeeld.example/v1#zzzzzzzzzzzz",
    ],
)
def test_een_query_of_fragment_wordt_geweigerd(controle: KlantEindpuntControle, adres: str) -> None:
    """Dezelfde achterdeur in een andere vorm; een basis-adres heeft ze niet nodig."""
    with pytest.raises(SSRFValidationError):
        controle.validate_url(adres)


def test_http_wordt_geweigerd_ook_naar_een_publieke_host(
    controle: KlantEindpuntControle,
) -> None:
    """De sleutel gaat als bearer-token mee; over klare lijn is dat weggeven."""
    with pytest.raises(SSRFValidationError) as fout:
        controle.validate_url("http://api.voorbeeld.example/v1")

    assert fout.value.violation_type.value == "invalid_scheme"


@pytest.mark.parametrize(
    "adres,verwacht",
    [
        ("https://169.254.169.254/latest", "metadata_service"),
        ("https://127.0.0.1/v1", "loopback"),
        ("https://10.0.0.5/v1", "private_ip"),
        ("https://192.168.1.10/v1", "private_ip"),
    ],
)
def test_de_bestemmingen_die_een_SSRF_aanval_iets_opleveren_blijven_dicht(
    controle: KlantEindpuntControle, adres: str, verwacht: str
) -> None:
    """Deze weigeringen kwamen al uit `SSRFProtector`; ze horen niet stil te verdwijnen."""
    with pytest.raises(SSRFValidationError) as fout:
        controle.validate_url(adres)

    assert fout.value.violation_type.value == verwacht


@pytest.mark.parametrize(
    "adres",
    [
        "https://[::]/v1",  # onbepaald adres -- verbinden komt op loopback uit
        "https://[::0]/v1",
        "https://[0:0:0:0:0:0:0:0]/v1",
        "https://[::1]/v1",  # loopback
        "https://[fc00::1]/v1",  # unique local
        "https://[fe80::1]/v1",  # link-local
        "https://[2002:a9fe:a9fe::]/v1",  # 6to4 van 169.254.169.254
        "https://[64:ff9b::a9fe:a9fe]/v1",  # NAT64 van 169.254.169.254
        "https://[64:ff9b::0a00:0005]/v1",  # NAT64 van 10.0.0.5
        "https://[::ffff:169.254.169.254]/v1",  # IPv4-mapped
    ],
)
def test_een_LETTERLIJK_ipv6_adres_dat_naar_binnen_wijst_wordt_geweigerd(
    controle_zonder_dns: KlantEindpuntControle, adres: str
) -> None:
    """De tweede Gate 2-ronde vond dit gat, en de asymmetrie maakte het aanwijsbaar.

    `https://0.0.0.0/v1` werd geweigerd (die reeks staat in de gereserveerde lijst van
    `SSRFProtector`) maar `https://[::]/v1` niet -- terwijl verbinden met het onbepaalde adres
    op loopback uitkomt. Hetzelfde gold voor 6to4 en NAT64 van het metadata-adres.

    De fixture ZONDER DNS wordt gebruikt om te bewijzen dat deze weigering van het adres zelf
    komt en niet van een naamopzoeking: er valt hier niets op te zoeken.
    """
    with pytest.raises(SSRFValidationError):
        controle_zonder_dns.validate_url(adres)


@pytest.mark.parametrize(
    "adres",
    [
        "https://93.184.216.34/v1",
        "https://[2606:4700:4700::1111]/v1",
        "https://[2001:4860:4860::8888]/v1",
    ],
)
def test_een_PUBLIEK_letterlijk_adres_mag_nog_steeds(
    controle_zonder_dns: KlantEindpuntControle, adres: str
) -> None:
    """De tegenrichting. Zonder deze helft is 'weiger elk letterlijk IP' een geldige oplossing.

    IPv6 staat er expliciet bij: de weigering hierboven mag niet neerkomen op "IPv6 is eng".
    """
    assert controle_zonder_dns.validate_url(adres) == adres


def test_een_naam_die_naar_een_INTERN_adres_resolveert_wordt_geweigerd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Een publieke naam die stiekem naar binnen wijst -- de klassieke DNS-rebinding."""
    protector = SSRFProtector(KLANT_EINDPUNT_CONFIG)
    monkeypatch.setattr(protector, "_resolve_hostname", lambda _naam: ["169.254.169.254"])

    with pytest.raises(SSRFValidationError):
        KlantEindpuntControle(protector).validate_url("https://ziet-er-normaal-uit.example/v1")


def test_de_fabriek_levert_de_strenge_configuratie() -> None:
    """Zonder deze test kan de fabriek een losse `SSRFProtector` gaan teruggeven.

    Dan zouden alle tests hierboven nog slagen -- die bouwen hun eigen object -- terwijl de
    productiecode de soepele variant gebruikt.

    **Deze test WAS zelf hol, op precies de manier die deze docstring belooft te voorkomen.**
    Een Gate 2-reviewer draaide de genoemde mutatie (`KlantEindpuntControle(SSRFProtector())`,
    standaardconfiguratie: schemes http+https, poorten 80/443/8080/8443) en mat dat alle vijf
    asserties GROEN bleven: `isinstance` zegt niets over de configuratie, en de vier andere
    keken naar de module-CONSTANTE in plaats van naar het gebouwde object. De constante was
    natuurlijk nog streng -- hij werd alleen niet meer gebruikt.

    Nu wordt het OBJECT bevraagd, en bovendien met gedrag: er gaat een `http`-adres doorheen
    dat onder de standaardconfiguratie zou passeren.
    """
    controle = maak_klant_endpoint_protector()

    assert isinstance(controle, KlantEindpuntControle)
    assert controle._protector.config is KLANT_EINDPUNT_CONFIG
    assert controle._protector.config.allowed_schemes == frozenset({"https"})
    assert controle._protector.config.allowed_ports == frozenset({443})

    # Gedrag, niet alleen configuratie: onder de standaardconfiguratie van `SSRFProtector` is
    # `http` op poort 80 toegestaan, dus deze aanroep sterft bij de genoemde mutatie.
    with pytest.raises(SSRFValidationError):
        controle.validate_url("http://api.voorbeeld.example/v1")


def test_de_controle_levert_OOK_het_adres_waar_de_naam_heen_wees(
    controle: KlantEindpuntControle,
) -> None:
    """Zonder dit adres kan de aanroeper niets vastpinnen (BE-LLM-004).

    **Deze test bestaat door een gemeten bijna-storing.** `keten()` is op 2026-09-23 overgezet
    van `validate_url` naar `validate_and_resolve`, en die methode zat WEL op `SSRFProtector`
    maar NIET op deze wrapper. De unittests van de keten bleven groen, want hun dubbel had hem
    wel; in productie had elke rij van elke klant een `AttributeError` gegeven, netjes gelogd
    als "het opgeslagen adres doorstaat de adrescontrole niet meer" -- een melding die naar de
    klant wijst terwijl het probleem bij ons zat. De typecontrole ving het op.

    Daarom staat hij hier op de ECHTE wrapper en niet op een dubbel.
    """
    adres = "https://api.voorbeeld-leverancier.example/v1"

    gevalideerd, adressen = controle.validate_and_resolve(adres)

    assert gevalideerd == adres
    assert adressen == [PUBLIEK_ADRES]


def test_de_vier_extra_eisen_gelden_ook_op_de_resolverende_weg(
    controle: KlantEindpuntControle,
) -> None:
    """Een tweede deur mag geen zwakkere deur zijn.

    De wrapper bestaat om vier eisen bovenop `SSRFProtector` te leggen. Zou
    `validate_and_resolve` rechtstreeks naar de protector doorschieten, dan was er een weg naar
    buiten die inloggegevens in het adres accepteert -- en precies die weg wordt sinds fase 2b
    op het verzoekpad gebruikt.
    """
    with pytest.raises(SSRFValidationError):
        controle.validate_and_resolve("https://gebruiker:geheim@api.voorbeeld.example/v1")

    with pytest.raises(SSRFValidationError):
        controle.validate_and_resolve("http://api.voorbeeld.example/v1")


@pytest.mark.parametrize(
    "adres",
    [
        pytest.param("::", id="onbepaald-adres"),
        pytest.param("64:ff9b::a9fe:a9fe", id="NAT64-naar-169.254.169.254"),
        pytest.param("2002:a9fe:a9fe::", id="6to4-naar-169.254.169.254"),
    ],
)
def test_een_NAAM_die_naar_zo_n_ipv6_vorm_wijst_wordt_ook_geweigerd(
    monkeypatch: pytest.MonkeyPatch, adres: str
) -> None:
    """De strengere eis geldt ook voor wat de opzoeking OPLEVERT (Gate 2 op BE-LLM-004).

    Deze klasse bestaat omdat `SSRFProtector` drie IPv6-vormen doorlaat die naar binnen
    wijzen. Die eis draaide alleen op de tak waar de klant een LETTERLIJK IP intypt. Gemeten
    voor de reparatie: een naam die naar `::`, NAT64 of 6to4 wees kwam er gewoon doorheen --
    en sinds BE-LLM-004 is dat het adres waar de verbinding daadwerkelijk heen gaat, want het
    wordt vastgepind. De IPv4-tegenhanger (169.254.169.254) was wel dicht; juist die
    asymmetrie maakt het een omissie en geen keuze.

    Een parameter per vorm: zo is er een mutatie per element van de benoemde verzameling.
    """
    protector = SSRFProtector(KLANT_EINDPUNT_CONFIG)
    monkeypatch.setattr(protector, "_resolve_hostname", lambda _naam: [adres])
    controle = KlantEindpuntControle(protector)

    with pytest.raises(SSRFValidationError):
        controle.validate_url("https://llm.klant.example/v1")

    with pytest.raises(SSRFValidationError):
        controle.validate_and_resolve("https://llm.klant.example/v1")


def test_een_naam_die_naar_een_ECHT_publiek_adres_wijst_mag_nog_steeds(
    controle: KlantEindpuntControle,
) -> None:
    """De tegenrichting. Zonder deze test is 'weiger elke naam' een geldige oplossing."""
    adres = "https://api.voorbeeld-leverancier.example/v1"

    gevalideerd, adressen = controle.validate_and_resolve(adres)

    assert gevalideerd == adres
    assert adressen == [PUBLIEK_ADRES]
