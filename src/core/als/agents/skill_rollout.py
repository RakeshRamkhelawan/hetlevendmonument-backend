"""Gefaseerde uitrol van een manifestwijziging over tenants (ADR-036 OP-02).

**De bevinding.** Een wijziging in het manifest of de instructietekst van de HR-pilootagent
ging in EEN keer naar alle tenants. Er was geen versienummer op het manifest, dus achteraf
was niet vast te stellen welke tekst een tenant had gedraaid, en terugdraaien kon alleen
met een nieuwe deploy. Het bestaande blue-green-raamwerk
(`deployment/blue_green/deploy.py`) helpt hier niet: dat schakelt hele containeromgevingen
om via nginx, van 0 naar 100 procent tegelijk, en kent geen tenants -- gemeten is dat geen
enkel bestand in `src/` het importeert.

**Wat een manifest nu kan declareren.** Naast `manifest_version` (verplicht bij een canary,
en het nummer dat de tenant daadwerkelijk draait) een optioneel `canary`-blok:

    manifest_version: 1
    system_prompt: 'De stabiele tekst.'
    canary:
      manifest_version: 2
      percentage: 5
      system_prompt: 'De nieuwe tekst.'
      enabled_tenant_ids: [1]
      excluded_tenant_ids: []
      enabled: true

Elke sleutel in het canary-blok behalve de zes besturingsvelden overschrijft het
gelijknamige veld voor tenants BINNEN de uitrol. Tenants erbuiten zien het manifest
ongewijzigd.

**Vijf procent.** Dat is de startwaarde die `config/rollout/phase3_canary.yaml` in dit
project al hanteert voor zijn canary-fase, en het is ook wat de leveranciers adviseren
(LaunchDarkly noemt 5 tot 10 procent als gebruikelijk startpunt voor
configuratiewijzigingen aan AI-systemen). Het getal staat niet in code vast: het komt uit
het manifest.

**Terugvallen kan op drie niveaus, oplopend in bereik.** Alle drie zonder codewijziging:

  1. een tenant in `excluded_tenant_ids` -- die ene klant terug naar de stabiele tekst;
  2. `percentage: 0` of `enabled: false` -- de uitrol stopt voor iedereen;
  3. de omgevingsvariabele `SKILL_CANARY_KILL_SWITCH=true` -- ALLE manifest-canary's van
     het hele platform uit, zonder een manifest aan te raken.

Nummer 3 is de noodrem. Hij wordt bij ELKE aanroep gelezen en niet bij import, zodat een
herstart van het proces met een gewijzigde variabele genoeg is; er hoeft geen image
opnieuw gebouwd te worden.

**Fail-safe.** Een canary-blok dat niet te lezen is (verkeerd type, tekst waar een getal
hoort, een percentage buiten 0-100) wordt genegeerd met een WARNING in het log, en de
tenant krijgt de stabiele versie. Een tikfout in een uitrolblok mag nooit tot gevolg
hebben dat een agent zonder of met een halve prompt draait. Dit is dezelfde keuze die
`company.feature_flags._read_remote_config()` maakt wanneer Redis niet leesbaar is: bij
twijfel de bekende, stabiele configuratie.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from src.core.shared.rollout import is_in_rollout

logger = logging.getLogger(__name__)

# Noodrem voor alle manifest-canary's tegelijk. Bewust een omgevingsvariabele en geen
# databaseveld: hij moet werken ook als de database het probleem is.
KILL_SWITCH_ENV = "SKILL_CANARY_KILL_SWITCH"

# De besturingsvelden van het canary-blok. Alles wat hier NIET in staat, is een override op
# een manifestveld. Expliciet benoemd en niet afgeleid, zodat een nieuw besturingsveld niet
# per ongeluk als promptoverride in de agentconfiguratie belandt.
_BESTURINGSVELDEN = frozenset(
    {
        "manifest_version",
        "percentage",
        "enabled",
        "enabled_tenant_ids",
        "excluded_tenant_ids",
    }
)


class OngeldigCanaryBlok(ValueError):
    """Het canary-blok is niet te lezen; de aanroeper valt terug op de stabiele versie."""


@dataclass(frozen=True)
class ManifestCanary:
    """Een gevalideerd canary-blok uit een skill-manifest."""

    manifest_version: int
    percentage: int
    overrides: dict[str, object] = field(default_factory=dict)
    enabled: bool = True
    enabled_tenant_ids: frozenset[int] = frozenset()
    excluded_tenant_ids: frozenset[int] = frozenset()

    @classmethod
    def from_raw(cls, raw: object) -> "ManifestCanary":
        """Lees en valideer een canary-blok. Gooit `OngeldigCanaryBlok` bij twijfel.

        Streng valideren en niet stil repareren: een `percentage: "vijf"` betekent dat
        iemand een uitrol bedoelde en dat die niet doet wat hij denkt. Doorgaan met een
        gegokte waarde zou een onbedoeld aantal tenants op een nieuwe prompt zetten -- de
        fout die deze hele module moet voorkomen.
        """
        if not isinstance(raw, dict):
            raise OngeldigCanaryBlok(f"canary moet een mapping zijn, kreeg {type(raw).__name__}")

        versie = raw.get("manifest_version")
        if not isinstance(versie, int) or isinstance(versie, bool):
            raise OngeldigCanaryBlok(
                f"canary.manifest_version moet een geheel getal zijn, kreeg {versie!r}"
            )

        percentage = raw.get("percentage")
        if not isinstance(percentage, int) or isinstance(percentage, bool):
            raise OngeldigCanaryBlok(
                f"canary.percentage moet een geheel getal zijn, kreeg {percentage!r}"
            )
        if not 0 <= percentage <= 100:
            raise OngeldigCanaryBlok(
                f"canary.percentage moet tussen 0 en 100 liggen, is {percentage}"
            )

        ingeschakeld = raw.get("enabled", True)
        if not isinstance(ingeschakeld, bool):
            raise OngeldigCanaryBlok(
                f"canary.enabled moet true of false zijn, kreeg {ingeschakeld!r}"
            )

        overrides = {k: v for k, v in raw.items() if k not in _BESTURINGSVELDEN}
        if not overrides:
            raise OngeldigCanaryBlok(
                "canary bevat geen enkel veld om te overschrijven; een uitrol die niets "
                "verandert verdeelt tenants zonder reden over twee versies"
            )

        return cls(
            manifest_version=versie,
            percentage=percentage,
            overrides=overrides,
            enabled=ingeschakeld,
            enabled_tenant_ids=_tenant_verzameling(raw.get("enabled_tenant_ids"), "enabled"),
            excluded_tenant_ids=_tenant_verzameling(raw.get("excluded_tenant_ids"), "excluded"),
        )


def _tenant_verzameling(raw: object, naam: str) -> frozenset[int]:
    """Lees een lijst tenant-ids. Leeg bij afwezigheid, fout bij onzin."""
    if raw is None:
        return frozenset()
    if not isinstance(raw, (list, tuple, set, frozenset)):
        raise OngeldigCanaryBlok(f"canary.{naam}_tenant_ids moet een lijst zijn, kreeg {raw!r}")
    ids: set[int] = set()
    for waarde in raw:
        if not isinstance(waarde, int) or isinstance(waarde, bool):
            raise OngeldigCanaryBlok(
                f"canary.{naam}_tenant_ids bevat {waarde!r}; alleen gehele getallen zijn geldig"
            )
        ids.add(waarde)
    return frozenset(ids)


def kill_switch_actief() -> bool:
    """Staat de platformbrede noodrem aan?

    Bij ELKE aanroep gelezen, niet bij import: zo is een procesherstart met een gewijzigde
    omgevingsvariabele genoeg om alle canary's te stoppen, en kan een test de rem zetten
    zonder de module opnieuw te laden.
    """
    return os.getenv(KILL_SWITCH_ENV, "false").strip().lower() == "true"


def resolve_config_for_tenant(config: dict[str, object], tenant_id: int) -> dict[str, object]:
    """Geef de agentconfiguratie zoals DEZE tenant hem moet zien.

    Buiten de uitrol (of zonder canary-blok) wordt `config` ongewijzigd teruggegeven --
    hetzelfde object, zodat er geen kopieerkosten zijn op het pad dat verreweg het vaakst
    wordt gelopen. Binnen de uitrol komt er een NIEUWE dict terug met de overrides erover;
    het origineel blijft ongemoeid, want dat wordt door de skill-klasse gedeeld tussen
    tenants.

    De salt is de agent-id, zodat elke skill zijn eigen groep tenants uitrolt. Zonder die
    salt zouden alle 135 skills exact dezelfde tenants als proefkonijn nemen en zou een
    ongelukkige tenant elke canary van het platform tegelijk krijgen.
    """
    raw = config.get("canary")
    if raw is None:
        return config

    if kill_switch_actief():
        logger.warning(
            "Manifest-canary overgeslagen voor agent %s: %s staat aan; alle tenants "
            "draaien de stabiele versie",
            config.get("agent_id"),
            KILL_SWITCH_ENV,
        )
        return config

    try:
        canary = ManifestCanary.from_raw(raw)
    except OngeldigCanaryBlok as exc:
        logger.warning(
            "Canary-blok van agent %s is genegeerd (%s: %s); tenant %s krijgt de stabiele versie",
            config.get("agent_id"),
            type(exc).__name__,
            exc,
            tenant_id,
            exc_info=True,
        )
        return config

    if not canary.enabled:
        return config

    binnen = is_in_rollout(
        tenant_id,
        percentage=canary.percentage,
        salt=f"skill-manifest:{config.get('agent_id', '')}",
        included=canary.enabled_tenant_ids,
        excluded=canary.excluded_tenant_ids,
    )
    if not binnen:
        return config

    opgelost = dict(config)
    opgelost.update(canary.overrides)
    opgelost["manifest_version"] = canary.manifest_version
    return opgelost
