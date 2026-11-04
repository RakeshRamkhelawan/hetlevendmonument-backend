"""De onderdelen van een limietsleutel: de echte afzender, de route en de gebruiker.

Brief 2026-10-27 (rate-limit nazorg). Een limiet beschermt alleen als zijn sleutel de juiste
dingen telt. Drie dingen waren fout, alle drie door de client te sturen:

- het adres kwam uit de EERSTE waarde van X-Forwarded-For (door de client zelf meegestuurd);
- het ingevulde pad zat in de sleutel, dus een ander id in het pad gaf een nieuwe emmer;
- de gebruiker was de ruwe `sub` uit het token, en die heeft twee vormen (e-mailadres of id).

Deze module heeft geen governance-afhankelijkheden, zodat `shared/rate_limiter.py` hem kan
gebruiken.
"""

from __future__ import annotations

import functools
import ipaddress
import logging
import os

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

#: De route is niet gevonden (een verzoek dat geen route raakt): een vaste waarde, nooit het pad.
ONBEKENDE_ROUTE = "onbekende-route"


#: Wat een proxy van onszelf is: loopback en de prive-netwerken (Docker, VNet). Bewust een lijst en
#: niet `ipaddress.is_private`: dat telt ook de documentatiebereiken (192.0.2.0/24, 198.51.100.0/24,
#: 203.0.113.0/24) als prive, en dan zou een afzender uit die bereiken als proxy tellen (gemeten
#: 2026-10-27 aan `test_xff_first_value`). 100.64.0.0/10 (CGNAT) staat er NIET in: of de
#: Container Apps-ingress daar vandaan komt is niet gemeten.
_STANDAARD_NETWERKEN = tuple(
    ipaddress.ip_network(netwerk)
    for netwerk in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)


#: De instelling voor de vertrouwde proxy's: komma-gescheiden netwerken (CIDR) die BOVEN de standaard
#: komen. Een proxy is een directe afzender in een van deze netwerken; alleen van zo'n afzender telt
#: `X-Forwarded-For`. Leeg of afwezig: alleen de standaardlijst (loopback en prive-netwerken).
INSTELLING_VERTROUWDE_PROXYS = "TRUSTED_PROXY_NETWORKS"

#: Een netwerk dat zo breed is dat vrijwel elke afzender een proxy wordt, is een instelfout: dan
#: kiest de client via `X-Forwarded-For` zijn eigen adres. Zulke netwerken worden genegeerd.
_MIN_PREFIX_IPV4 = 8
_MIN_PREFIX_IPV6 = 16


@functools.cache
def _netwerken_voor(waarde: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """De standaardlijst plus de geldige, niet te brede netwerken uit `waarde`."""
    extra: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for deel in waarde.split(","):
        deel = deel.strip()
        if not deel:
            continue
        try:
            netwerk = ipaddress.ip_network(deel, strict=False)
        except ValueError:
            logger.warning("%s: %r is geen netwerk; genegeerd", INSTELLING_VERTROUWDE_PROXYS, deel)
            continue
        minimum = _MIN_PREFIX_IPV4 if netwerk.version == 4 else _MIN_PREFIX_IPV6
        if netwerk.prefixlen < minimum:
            logger.warning(
                "%s: %s is te breed (kleiner dan /%d); genegeerd",
                INSTELLING_VERTROUWDE_PROXYS,
                deel,
                minimum,
            )
            continue
        extra.append(netwerk)
    return _STANDAARD_NETWERKEN + tuple(extra)


def _vertrouwde_netwerken() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return _netwerken_voor(os.getenv(INSTELLING_VERTROUWDE_PROXYS, ""))


def _als_adres(waarde: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Een adres, met een IPv4-adres in IPv6-vorm (`::ffff:10.0.0.1`) uitgepakt tot IPv4.

    Zonder dit is `::ffff:172.18.0.2` geen vertrouwde proxy (geen netwerk uit de lijst bevat
    hem), en dan deelt iedere klant achter die proxy een emmer. Gemeten door de security-review
    2026-10-27. Een ongeldige waarde geeft `ValueError`.
    """
    adres = ipaddress.ip_address(waarde)
    if isinstance(adres, ipaddress.IPv6Address) and adres.ipv4_mapped is not None:
        return adres.ipv4_mapped
    return adres


def _is_vertrouwd(adres: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(adres in netwerk for netwerk in _vertrouwde_netwerken() if netwerk.version == adres.version)


def _sleutel_adres(adres: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """IPv4 als adres, IPv6 als zijn /64: een client met een /64 kiest anders per verzoek een adres.

    Niet gemeten tegen een echte IPv6-client (security-review 2026-10-27).
    """
    if isinstance(adres, ipaddress.IPv6Address):
        return f"{ipaddress.IPv6Address((int(adres) >> 64) << 64)}/64"
    return str(adres)


def is_vertrouwde_proxy(host: str) -> bool:
    """Is `host` een loopback- of prive-adres, dus een proxy waarvan de header telt?

    Achter Traefik (ADR-009) is `request.client.host` het adres van de proxy. Een client die de
    proxy omzeilt heeft een openbaar adres; zijn X-Forwarded-For wordt dan genegeerd
    (GHSA-c2r5-cfqr-c553).
    """
    try:
        return _is_vertrouwd(_als_adres(host))
    except ValueError:
        return False


def _bepaal_afzender(
    request: Request,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | str | None:
    """Het echte adres van de afzender: een adres, de ruwe verbinding bij een onleesbaar adres, of `None`.

    X-Forwarded-For is een lijst waar elke proxy RECHTS aan toevoegt: alles wat de client zelf
    meestuurt staat dus links. Wie de eerste waarde pakt, laat de client zijn adres kiezen (gemeten
    2026-10-27: per verzoek een andere eerste waarde gaf per verzoek een nieuwe emmer). Daarom
    wordt van RECHTS gelezen en worden vertrouwde proxy's overgeslagen; de eerste waarde die geen
    vertrouwde proxy is, is wat de buitenste proxy waarnam.

    X-Forwarded-For telt alleen als de directe afzender zelf een vertrouwde proxy is. Een waarde
    die geen adres is, ondermijnt de keten en valt terug op de verbinding. Alle
    X-Forwarded-For-headers tellen, in volgorde (een proxy kan een eigen header toevoegen).
    """
    verbinding = request.client.host if request.client and request.client.host else None
    if verbinding is None:
        return None
    try:
        peer = _als_adres(verbinding)
    except ValueError:
        return verbinding
    if not _is_vertrouwd(peer):
        return peer
    stappen = [
        stap.strip()
        for header in request.headers.getlist("x-forwarded-for")
        for stap in header.split(",")
        if stap.strip()
    ]
    for stap in reversed(stappen):
        try:
            adres = _als_adres(stap)
        except ValueError:
            return peer
        if not _is_vertrouwd(adres):
            return adres
    return peer


def afzender_adres(request: Request) -> str:
    """HET adres van de klant, voor limiet, beveiliging en auditlog: een regel, een functie.

    Het echte adres (IPv4 ook uit IPv6-vorm), of `unknown` als er geen verbinding is. Brief
    2026-10-28: tot dan hadden de limietsleutel, de SecurityMiddleware en de auditmiddleware elk een
    eigen regel (rechtse niet-vertrouwde waarde, N-de van rechts, EERSTE waarde = door de client
    gekozen), en zagen voor hetzelfde verzoek drie verschillende adressen.

    Welke afzenders een proxy zijn staat in `TRUSTED_PROXY_NETWORKS` (komma-gescheiden CIDR, boven
    op loopback en de prive-netwerken). Standaard vertrouwt dit niets wat de client meestuurt.

    NIET gemeten: hoeveel proxy-stappen er op staging voor de app zitten en welk adres de Container
    Apps-ingress daar als afzender heeft (ADR-038 noemt hetzelfde als nog niet gemeten). Een
    ingress buiten de vertrouwde netwerken (bijvoorbeeld 100.64.0.0/10) laat X-Forwarded-For hier
    ongelezen: dan is het adres overal dat van de ingress, en delen alle klanten daarachter EEN
    limietemmer. Dat is geen omzeiling maar wel een storing tussen klanten. Meet het adres na de
    eerste staging-uitrol en zet het netwerk in de instelling.
    """
    adres = _bepaal_afzender(request)
    return "unknown" if adres is None else str(adres)


def client_adres(request: Request) -> str | None:
    """`afzender_adres` als LIMIETSLEUTEL, of `None` als er geen verbinding is.

    IPv6 per /64 (een client met een /64 kiest anders per verzoek een adres); niet gemeten tegen een
    echte IPv6-client (security-review 2026-10-27). Voor het auditlog en de beveiliging telt het
    volledige adres uit `afzender_adres`.
    """
    adres = _bepaal_afzender(request)
    if adres is None:
        return None
    if isinstance(adres, str):
        return adres
    return _sleutel_adres(adres)


def route_sleutel(request: Request) -> str:
    """Het routesjabloon (`/x/{item_id}`), niet het ingevulde pad.

    Een route met een id in het pad gaf per id een eigen emmer: wie het id wisselt, wisselt van
    emmer. Zonder gevonden route valt de sleutel terug op een vaste waarde, nooit op het pad
    (dat is wat de client kiest).
    """
    pad = getattr(request.scope.get("route"), "path", None)
    return pad if isinstance(pad, str) and pad else ONBEKENDE_ROUTE


def tenant_en_gebruiker(request: Request) -> tuple[str, str] | None:
    """(tenant, gebruiker) van de geauthenticeerde aanvrager, of `None` zonder tenant.

    De gebruiker is het NUMERIEKE id dat `TenantMiddleware` uit de `sub` heeft vastgesteld
    (`request.state.limiet_gebruiker`), of het id van een `request.state.user`-object. Nooit de
    ruwe `sub`: die is op het wachtwoordpad een e-mailadres en op de andere paden het id, en een
    gebruiker kreeg dan twee emmers.

    Een aanvrager MET tenant maar zonder vast te stellen id is een geauthenticeerde aanvrager die
    we niet kunnen tellen: dat is een 401, geen `anon`-emmer en geen gedeelde emmer.
    """
    gebruiker = getattr(request.state, "user", None)
    if gebruiker is not None:
        gebruikers_id = getattr(gebruiker, "id", None)
        tenant = getattr(gebruiker, "tenant_id", None)
        if gebruikers_id is not None and tenant is not None:
            return str(tenant), f"u{gebruikers_id}"
    tenant = getattr(request.state, "tenant_id", None)
    if tenant is None:
        return None
    vastgesteld = getattr(request.state, "limiet_gebruiker", None)
    if not isinstance(vastgesteld, str) or not vastgesteld:
        raise HTTPException(
            status_code=401,
            detail="Gebruiker niet vast te stellen voor de limiet",
        )
    return str(tenant), vastgesteld
