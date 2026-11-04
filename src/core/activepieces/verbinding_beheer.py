"""Het vastleggen van de ActivePieces-verbinding van een tenant (ADR-040 B3), door de platformbeheerder.

Dit is de SCHRIJFkant van `verbinding.py`: de beheerroute roept `ApVerbindingBeheer.leg_vast` aan.
Het wachtwoord gaat er in, wordt hier versleuteld met de sleutel van DEZE tenant en komt er nooit
meer uit: `toon` geeft alleen terug OF er een wachtwoord staat.

**Waarom alles wordt INGESPOTEN en niets geimporteerd.** Zelfde reden als
`TenantLLMProviderService`: de koppelingsbudgetten van de DSM-indeling zijn vol, en opslag
(`repositories`, infra) mag niet van beveiliging (`security`, auth) afhangen. De wiring gebeurt in
de API-laag (`api/v1/admin/dependencies.py`).

**Het adres.** Alleen `https`, of `http` naar `localhost` voor ontwikkeling en de lokale
scheidingsproef met twee AP-containers. Geen inloggegevens in de URL: een wachtwoord in
`https://gebruiker:geheim@...` zou in de ONVERSLEUTELDE kolom `base_url` belanden, en dat is
precies de omweg waarmee de belofte "het wachtwoord komt er nooit uit" te omzeilen is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit

from src.core.exceptions import ValidatieFout

if TYPE_CHECKING:  # pragma: no cover - alleen voor de typecontrole
    from src.core.repositories.tenant_ap_verbinding_repository import OpgeslagenAPVerbinding

logger = logging.getLogger(__name__)

_LOKALE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class OngeldigeApGegevens(ValidatieFout):
    """Wat de beheerder opgaf is niet bruikbaar; de tekst mag naar de beheerder."""


class OngeldigApAdres(OngeldigeApGegevens):
    """Het opgegeven adres van de ActivePieces is niet toegestaan."""


@dataclass(frozen=True)
class ApVerbindingInfo:
    """De verbinding zoals de beheerder hem terugziet -- ZONDER wachtwoord."""

    tenant_id: int
    base_url: str
    email: str
    project_id: str
    heeft_wachtwoord: bool


class _Opslag(Protocol):
    async def get(self, tenant_id: int) -> OpgeslagenAPVerbinding | None: ...

    async def upsert(
        self,
        tenant_id: int,
        base_url: str,
        email: str,
        wachtwoord_encrypted: str,
        project_id: str,
    ) -> OpgeslagenAPVerbinding: ...


class _Encryptie(Protocol):
    def encrypt(self, tenant_id: int, plaintext: str) -> str: ...


def controleer_adres(adres: str) -> str:
    """Geef het opgeschoonde adres terug, of gooi `OngeldigApAdres`."""
    schoon = adres.strip().rstrip("/")
    if any(ord(teken) < 33 or ord(teken) == 127 for teken in schoon):
        # `urlsplit` haalt tab en regeleinde STIL weg: wat we valideren is dan niet wat we opslaan.
        raise OngeldigApAdres("Het adres mag geen spaties of besturingstekens bevatten.")
    delen = urlsplit(schoon)
    if delen.scheme not in {"http", "https"} or not delen.hostname:
        raise OngeldigApAdres("Het adres moet beginnen met https:// en een hostnaam bevatten.")
    if delen.username or delen.password:
        raise OngeldigApAdres("Zet geen inloggegevens in het adres; gebruik de aparte velden.")
    if delen.query or delen.fragment:
        raise OngeldigApAdres("Het adres mag geen query of fragment bevatten.")
    host = delen.hostname.lower().rstrip(".")
    if delen.scheme == "http" and host not in _LOKALE_HOSTS:
        raise OngeldigApAdres("Een adres zonder versleuteling (http) mag alleen naar localhost.")
    # Normaliseren, zodat `HTTPS://AP.x`, `ap.x.` en `ap.x:443` NIET als een ander adres tellen:
    # de uniekheid van (adres, project) en de breaker-sleutel zijn tekstvergelijkingen.
    try:
        poort = delen.port
    except ValueError as e:
        # `:99999`, `:abc`, `:-1`: `urlsplit` gooit pas bij het OPVRAGEN van de poort.
        raise OngeldigApAdres("De poort in het adres is geen geldig poortnummer.") from e
    if (delen.scheme, poort) in {("https", 443), ("http", 80)}:
        poort = None
    netloc = f"[{host}]" if ":" in host else host
    if poort is not None:
        netloc = f"{netloc}:{poort}"
    return f"{delen.scheme}://{netloc}{delen.path.rstrip('/')}"


class ApVerbindingBeheer:
    """Legt de verbinding van EEN tenant vast en toont hem zonder geheim."""

    def __init__(self, opslag: _Opslag, encryptie: _Encryptie) -> None:
        self._opslag = opslag
        self._encryptie = encryptie

    async def toon(self, tenant_id: int) -> ApVerbindingInfo | None:
        rij = await self._opslag.get(tenant_id)
        return None if rij is None else self._info(rij)

    async def leg_vast(
        self,
        tenant_id: int,
        *,
        base_url: str,
        email: str,
        wachtwoord: str,
        project_id: str,
    ) -> ApVerbindingInfo:
        """Versleutel het wachtwoord met de sleutel van deze tenant en sla alles op.

        Gooit `OngeldigeApGegevens` (of `OngeldigApAdres`) VOOR er iets wordt versleuteld of opgeslagen.
        """
        adres = controleer_adres(base_url)
        if not email.strip() or not wachtwoord or not project_id.strip():
            # Een leeg wachtwoord versleutelt prima en geeft dan een verbinding die nooit inlogt.
            raise OngeldigeApGegevens("E-mailadres, wachtwoord en project zijn alle drie verplicht.")
        versleuteld = self._encryptie.encrypt(tenant_id, wachtwoord)
        rij = await self._opslag.upsert(
            tenant_id,
            base_url=adres,
            email=email.strip(),
            wachtwoord_encrypted=versleuteld,
            project_id=project_id.strip(),
        )
        return self._info(rij)

    @staticmethod
    def _info(rij: OpgeslagenAPVerbinding) -> ApVerbindingInfo:
        return ApVerbindingInfo(
            tenant_id=rij.tenant_id,
            base_url=rij.base_url,
            email=rij.email,
            project_id=rij.project_id,
            heeft_wachtwoord=bool(rij.wachtwoord_encrypted),
        )
