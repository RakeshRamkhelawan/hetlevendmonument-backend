"""Het beleid rond klant-eindpunten: mag het, deugt het adres, en versleutel de sleutel.

**Waarom dit een servicelaag is en niet de repository.** De eerste versie zette deze controles
in `src/core/repositories/`, en `test_dsm_009_no_medium_backward.py` viel daarop om: de
DSM-indeling rekent repositories tot `infra` en `src/core/security` tot `auth`, en infra mag
niet van auth afhangen. Die regel wees iets echts aan -- opslag hoort niet te weten wat een
geldig adres is.

**Waarom alles hier wordt INGESPOTEN en niets geimporteerd.** De tweede versie importeerde de
beveiligingsmodules hier wel, en toen vielen `test_dsm017_runtime_deps_facade.py` en
`test_dsm_008_reclassification.py` om: `agent_runtime` heeft een budget van 16 auth-imports
(werd 17) en een koppelingsplafond van 234 (werd 237). Die budgetten bestaan om koppelingsgroei
te stoppen, en het antwoord daarop is niet ze ophogen maar minder koppelen. Alle
afhankelijkheden komen daarom van de aanroeper; de imports hieronder staan onder
`TYPE_CHECKING` en bestaan alleen voor de typecontrole. Dat is bovendien het patroon dat
ADR-034 voorschrijft, en het maakt deze klasse testbaar zonder iets te patchen.

De wiring gebeurt in de API-laag (`src/core/api/`), die beide lagen wel mag kennen.

**Waarom de grens op EEN plek staat.** Een controle bij de aanroeper werkt tot er een tweede
aanroeper komt. Dit is een doorgang waar niemand omheen kan, en daardoor ook toetsbaar:
`tests/architecture/test_elk_schrijfpad_naar_een_klanteindpunt_wordt_gevalideerd.py` wordt rood
zodra er een schrijfweg bijkomt die dit overslaat.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from src.core.exceptions import ValidatieFout

if TYPE_CHECKING:  # pragma: no cover - alleen voor de typecontrole
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.core.repositories.tenant_llm_provider_repository import (
        OpgeslagenProvider,
        TenantLLMProviderRepository,
    )
    from src.core.security.ssrf_protection import SSRFProtector
    from src.core.security.tenant_secret_encryption import TenantSecretEncryption


logger = logging.getLogger(__name__)


class ExterneProviderNietToegestaan(PermissionError):
    """Deze tenant staat op lokaal-alleen en er wordt een extern eindpunt aangeboden.

    Fail-secure bij het SCHRIJVEN en niet pas bij het gebruiken: een sleutel die je niet mag
    gebruiken hoor je ook niet te bewaren.
    """


class _AdresControle(Protocol):
    """Wat de service van een SSRF-controle verwacht.

    Een Protocol en geen import: zie de moduledocstring. De echte implementatie is
    `SSRFProtector` uit `src/core/security/ssrf_protection.py`, gemaakt door
    `maak_klant_endpoint_protector()`.
    """

    def validate_url(self, url: str) -> str: ...

    def validate_and_resolve(self, url: str) -> tuple[str, list[str]]: ...


@dataclass(frozen=True)
class ProviderRij:
    """Een providerrij met ONTSLEUTELDE sleutel, voor de LLM-laag."""

    volgorde: int
    naam: str
    base_url: str
    model: str
    #: Het IP waarnaar de aanroeper MOET verbinden, uit dezelfde controle die het adres
    #: goedkeurde. Leeg als de naam niets opleverde; dan is er niets vast te pinnen en valt de
    #: aanroeper terug op gewone naamsopzoeking -- die rij is dan al door de adrescontrole
    #: gekomen, maar draagt het rebinding-risico dat BE-LLM-004 beschrijft.
    gevalideerd_ip: str | None
    # `repr=False` is hier geen netheid maar de enige rem. Gemeten in Gate 2 (2026-09-20):
    # zonder die vlag drukt de standaard-repr de sleutel in klare tekst af, en een enkele
    # `logger.debug("%s", rij)` of een traceback die locals rendert zet hem daarmee in het
    # logbestand. Deze hele module bestaat om dat te voorkomen.
    api_key: str | None = field(repr=False)


@dataclass(frozen=True)
class ProviderOverzicht:
    """Hetzelfde zonder sleutel. Dit is wat een mens te zien krijgt."""

    id: int
    volgorde: int
    naam: str
    base_url: str
    model: str
    heeft_sleutel: bool
    actief: bool


class TenantLLMProviderService:
    """Configureert en levert de providerketen van een tenant."""

    def __init__(
        self,
        repository: TenantLLMProviderRepository,
        encryptie: TenantSecretEncryption,
        protector: _AdresControle | SSRFProtector,
    ) -> None:
        self._repo = repository
        self._encryptie = encryptie
        self._protector = protector

    async def toon(self, tenant_id: int) -> list[ProviderOverzicht]:
        """De keten zoals een mens hem mag zien -- zonder sleutels."""
        return [
            ProviderOverzicht(
                id=rij.id,
                volgorde=rij.volgorde,
                naam=rij.naam,
                base_url=rij.base_url,
                model=rij.model,
                heeft_sleutel=bool(rij.api_key_encrypted),
                actief=rij.actief,
            )
            for rij in await self._repo.alle(tenant_id)
        ]

    async def keten(self, tenant_id: int) -> list[ProviderRij]:
        """De ACTIEVE keten met ontsleutelde sleutels, in EEN aanroep.

        Dit is `opgeslagen_rijen()` gevolgd door `beproef()`. Handig voor een aanroeper die
        toch al een sessie openhoudt (de beheerdersroute), en de vorm waarin de tests van
        fase 2a en 2b het gedrag vastleggen.

        **Wie op het verzoekpad zit, gebruikt de twee helften apart** -- zie
        `LLMService.for_tenant`. De reden staat in `beproef()`: de tweede helft doet
        naamsopzoekingen van maximaal vijf seconden per rij, en die horen niet binnen een
        openstaande databasesessie.
        """
        return await self.beproef(tenant_id, await self.opgeslagen_rijen(tenant_id))

    async def instellingen_van_de_klant(self, tenant_id: int) -> dict[str, object] | None:
        """De tenantinstellingen (waaronder de taalmodelkeuze `llm_provider`). Alleen databasewerk."""
        return await self._repo.instellingen(tenant_id)

    async def opgeslagen_rijen(self, tenant_id: int) -> list[OpgeslagenProvider]:
        """De actieve rijen uit de opslag. Alleen databasewerk, zo kort mogelijk.

        **Het eerste slot zit hier** (BE-LLM-005 haalde het uit `keten()` hierheen): staat de
        tenant op lokaal-alleen, dan komt er niets terug en is er ook geen adrescontrole nodig.
        """
        if not await self._repo.mag_extern(tenant_id):
            # HET EERSTE SLOT. Tot 2026-09-21 stond dit alleen op het schrijfpad, en een
            # toetsing door een andere sessie mat het gevolg: met de schakelaar op FALSE gaf
            # `keten()` een IDENTIEK antwoord als met TRUE -- zelfde rij, zelfde ontsleutelde
            # sleutel. `mag_extern` had in heel `src/` precies EEN aanroeper.
            #
            # Waarom dat meer is dan een gemiste controle: deze vlag is tegelijk de
            # feature-schakelaar en de terugdraaiknop. Wie hem op FALSE zet om een probleem te
            # stoppen, hoort iets te stoppen.
            if await self._repo.actieve(tenant_id):
                # Luid, want dit is een tegenstrijdige toestand: er STAAN providers ingericht
                # terwijl de tenant ze niet mag gebruiken. Stil een lege lijst teruggeven zou
                # "succes zonder werk" zijn.
                logger.error(
                    "tenant %s heeft ingerichte providers maar 'externe_providers_toegestaan' "
                    "staat UIT -- de keten blijft leeg en de aanroeper valt terug op het "
                    "platformmodel",
                    tenant_id,
                )
            return []
        rijen: list[OpgeslagenProvider] = await self._repo.actieve(tenant_id)
        return rijen

    async def beproef(
        self, tenant_id: int, rijen: list[OpgeslagenProvider]
    ) -> list[ProviderRij]:
        """Adrescontrole en ontsleuteling. Raakt de database NIET.

        **Waarom dit los staat van het ophalen (BE-LLM-005).** Hieronder zit per rij een
        naamsopzoeking van maximaal vijf seconden. Zolang die binnen de sessie van de aanroeper
        stond, hield elke agenttaak een verbinding bezet voor de duur van al die opzoekingen --
        met een keten van vier rijen twintig seconden, op een database die op 40 van de 50
        verbindingen zit. `.claude/rules/database.md`: geen transactie open tijdens externe I/O.

        Wat NIET verschuift is de volgorde: de controle gebeurt nog steeds VOOR het gebruik.
        Dat is de hele reden dat hij bestaat.

        **Beide sloten gelden hier, net als op het schrijfpad.** Eerst of deze tenant extern
        MAG, dan pas of het adres deugt. Het eerste ontbrak tot 2026-09-21.

        **Het adres wordt hier OPNIEUW gecontroleerd, en dat is geen dubbel werk.** Beide Gate
        2-reviewers wezen hetzelfde aan: een controle bij het opslaan bevriest een oordeel over
        iets dat kan bewegen. Een klant die zijn eigen DNS beheert, laat de naam bij het
        inrichten naar een publiek adres wijzen en daarna naar `169.254.169.254`. Dat is
        letterlijk de vorm van CVE-2026-84377, en de bewaker op het schrijfpad kan hem per
        constructie niet zien. Vandaag heeft deze methode nul aanroepers, en dat maakt dit het
        goedkoopste moment om de eis vast te leggen in plaats van het duurste.

        **Een rij die niet deugt wordt OVERGESLAGEN, niet stilgehouden.** Een enkele onleesbare
        of niet meer geldige rij mag de hele keten niet omleggen -- dan zou een tenant met twee
        providers door een fout in de tweede ook zijn eerste kwijtraken. Maar overslaan zonder
        iets te zeggen is "succes zonder werk", precies wat dit project nergens wil: daarom een
        `logger.error` per overgeslagen rij, met de reden en ZONDER de sleutel. Blijft er niets
        over, dan is het antwoord een lege lijst en valt de aanroeper terug op het
        platformmodel -- dat is de veilige kant.
        """
        bruikbaar: list[ProviderRij] = []
        for rij in rijen:
            try:
                # `validate_and_resolve` in plaats van `validate_url`, en in een THREAD.
                #
                # Het IP moet mee (BE-LLM-004): een adres valideren en daarna de NAAM aan de
                # HTTP-client geven laat die de naam nog een keer opzoeken, en dan kan het
                # antwoord een ander adres zijn. Die TOCTOU-vorm is in 2026 tweemaal als
                # kwetsbaarheid uitgebracht in precies deze constructie. De aanroeper pint het
                # IP vast; zie `OpenAICompatibleProvider`.
                #
                # De thread is er omdat hieronder `socket.getaddrinfo` zit -- synchroon, tot
                # `dns_resolution_timeout` seconden. Bij het inrichten viel dat niet op; op het
                # verzoekpad staat het per rij op de event loop en houdt het elke andere taak
                # in dat proces tegen.
                adres, ips = await asyncio.to_thread(
                    self._protector.validate_and_resolve, rij.base_url
                )
            except Exception as exc:
                logger.error(
                    "provider '%s' (volgorde %s) van tenant %s overgeslagen: het opgeslagen "
                    "adres doorstaat de adrescontrole niet meer (%s: %s)",
                    rij.naam,
                    rij.volgorde,
                    tenant_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                continue

            try:
                sleutel = (
                    self._encryptie.decrypt(tenant_id, rij.api_key_encrypted)
                    if rij.api_key_encrypted
                    else None
                )
            except Exception as exc:
                # GEEN `exc` in de melding en geen `exc_info`: bij een ontsleutelfout kan de
                # uitzondering brokstukken van de tekst dragen, en dat is precies het geheim.
                logger.error(
                    "provider '%s' (volgorde %s) van tenant %s overgeslagen: de opgeslagen "
                    "sleutel is niet te ontsleutelen (%s). Waarschijnlijk is de hoofdsleutel "
                    "gewijzigd; de rij moet opnieuw worden ingericht.",
                    rij.naam,
                    rij.volgorde,
                    tenant_id,
                    type(exc).__name__,
                )
                continue

            bruikbaar.append(
                ProviderRij(
                    volgorde=rij.volgorde,
                    naam=rij.naam,
                    base_url=adres,
                    model=rij.model,
                    # De EERSTE van de gevalideerde adressen. Elk adres in die lijst is door
                    # dezelfde controle gekomen, dus de keuze is willekeurig maar nooit
                    # onveilig. Stond er al een IP in `base_url`, dan bevat de lijst dat ene
                    # adres en is vastpinnen een no-op. Leeg betekent: de naam leverde niets op.
                    gevalideerd_ip=ips[0] if ips else None,
                    api_key=sleutel,
                )
            )
        return bruikbaar

    async def configureer(
        self,
        tenant_id: int,
        *,
        volgorde: int,
        naam: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        actief: bool = True,
    ) -> int:
        """Voeg een provider toe. De twee sloten zitten hier.

        De volgorde van de controles is bewust: eerst of deze tenant extern MAG, dan pas of het
        adres deugt. Andersom zou een tenant op lokaal-alleen uit de foutmelding kunnen aflezen
        welke interne adressen bestaan.
        """
        if not await self._repo.mag_extern(tenant_id):
            raise ExterneProviderNietToegestaan(
                "Deze tenant staat op lokaal-alleen. Een extern eindpunt wordt niet opgeslagen "
                "zolang 'externe_providers_toegestaan' uit staat -- bewaar geen sleutel die je "
                "niet mag gebruiken."
            )

        try:
            gevalideerd = self._protector.validate_url(base_url)
        except Exception as exc:
            # De reden komt mee (de aanroeper is een beheerder die zijn eigen typefout moet
            # kunnen zien), maar niets uit een netwerkantwoord -- er is nog geen aanroep gedaan.
            # Breed vangen omdat het fouttype van de controle hier niet geimporteerd wordt;
            # het TYPE staat in de melding zodat het onderscheid niet verdwijnt.
            # De SSRF-reden (kan een opgelost intern adres noemen) gaat naar het log, niet naar
            # de aanvrager: die krijgt een vaste Nederlandse tekst.
            logger.warning(
                "base_url geweigerd door de SSRF-controle: %s: %s", type(exc).__name__, exc
            )
            raise ValidatieFout("Dit adres is niet toegestaan voor een taalmodel-provider.") from exc

        return await self._repo.voeg_toe(
            tenant_id,
            volgorde=volgorde,
            naam=naam,
            base_url=gevalideerd,
            model=model,
            api_key_encrypted=(self._encryptie.encrypt(tenant_id, api_key) if api_key else None),
            actief=actief,
        )


def bouw_tenant_llm_service(db: AsyncSession) -> TenantLLMProviderService:
    """De ENIGE montage van deze dienst, voor elke aanroeper.

    Tot BE-LLM-004 stond deze montage alleen in `api/v1/admin/dependencies.py`. Fase 2b
    voegt een tweede aanroeper toe (de agentdeur via `LLMService.for_tenant`), en twee
    kopieen van dezelfde drie regels lopen stil uit elkaar -- de ene krijgt dan wel een
    strengere protector of een andere sleutelbron dan de andere, en niets wordt daar rood van.

    De imports staan bewust IN de functie, net als bij de admin-laag: ze houden de
    afhankelijkheden van de servicelaag bij het opstarten laag en voorkomen een importcyclus
    met `src.core.security`.

    Gooit `HoofdsleutelOntbreekt` als `MASTER_ENCRYPTION_KEY` niet gezet is. Dat is opzet en
    geen ongeluk: zonder hoofdsleutel is elke opgeslagen klantsleutel onleesbaar, en dat hoort
    luid te falen in plaats van stil terug te vallen op het platformmodel -- anders lijkt een
    kapotte inrichting op een tenant die gewoon niets heeft ingericht.
    """
    from src.core.repositories.tenant_llm_provider_repository import TenantLLMProviderRepository
    from src.core.security.llm_endpoint_policy import maak_klant_endpoint_protector
    from src.core.security.tenant_secret_encryption import TenantSecretEncryption

    return TenantLLMProviderService(
        repository=TenantLLMProviderRepository(db),
        encryptie=TenantSecretEncryption(),
        protector=maak_klant_endpoint_protector(),
    )
