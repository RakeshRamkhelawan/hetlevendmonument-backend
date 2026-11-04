"""De catalogussleutel wordt op TWEE plekken afgeleid; die moeten het altijd eens zijn.

`EnterpriseCatalogLoader._normalize_agent_key` is de bron. `scripts/audit_agent_yaml.py`
houdt daarvan een BEWUSTE kopie -- met een geldige reden, die in zijn eigen docstring staat:
dat script moet buiten de applicatiecontext kunnen draaien en importeert daarom niets uit
`src/`.

Een kopie met een goede reden blijft een kopie. Deze codebase heeft op 2026-09-25 twee keer
meegemaakt dat een tweede vindplaats stil uiteenliep met de eerste: een bewaker die
`class_name.replace("Agent", "Skill")` nabouwde in plaats van aanriep, en een guard die de
afgeleide NAAM van een provider las in plaats van te vragen wat hij deed. Beide zouden
precies de wijziging hebben overleefd die ze moesten betrappen.

Deze toets draait dezelfde namen door beide implementaties en eist hetzelfde antwoord. Hij
kan wat de guard-met-kopie niet kan: hij faalt zodra er EEN van de twee verandert.

Mutatiebewijs (2026-09-26), in beide richtingen:
  voorwaarts -- de loader terug op `.replace("agent", "")`, het script niet: ROOD.
  voorwaarts -- het script terug op `.replace("agent", "")`, de loader niet: ROOD.
  voorwaarts -- de terugval bij een lege romp weggehaald in de loader: ROOD.
  tegen      -- BEIDE terug op de oude regel: GROEN (hij toetst OVEREENSTEMMING, niet
                welke van de twee regels de juiste is -- dat doen de tests op de loader).
"""

from __future__ import annotations

import pytest

from scripts.audit_agent_yaml import _normalize_key
from src.core.als.agents.loader import EnterpriseCatalogLoader

# Namen die de RANDEN raken, niet alleen het gewone geval. Elk met de reden waarom.
NAMEN: tuple[str, ...] = (
    "DunningAgent",             # gewoon geval
    "DunningAgentAgent",        # dubbel achtervoegsel -- de bevinding van BE-AGT-068
    "AgentRouterAgent",         # 'Agent' aan het BEGIN; de oude regel at hem op
    "AgentHealthMonitorAgent",  # idem, langer
    "PaymentAgentRouterAgent",  # 'Agent' in het MIDDEN
    "Agent",                    # romp wordt leeg
    "AgentAgent",               # romp wordt 'Agent'
    "VATComplianceAgent",       # hoofdletters in de romp
    "ReceiptScanner",           # geen achtervoegsel
    "agent",                    # al kleingeschreven, geen achtervoegsel-match
)


@pytest.mark.architecture
@pytest.mark.parametrize("class_name", NAMEN)
def test_beide_afleidingen_geven_dezelfde_sleutel(class_name: str) -> None:
    uit_de_loader = EnterpriseCatalogLoader._normalize_agent_key(class_name)
    uit_het_script = _normalize_key({"agent_id": "x", "class_name": class_name})
    assert uit_de_loader == uit_het_script, (
        f"'{class_name}' geeft '{uit_de_loader}' in de loader en '{uit_het_script}' in "
        f"scripts/audit_agent_yaml.py. Die kopie is bewust, maar hij moet meebewegen."
    )


@pytest.mark.architecture
def test_geen_enkele_naam_levert_een_LEGE_sleutel() -> None:
    """Een lege sleutel importeert `...skills.` en faalt onleesbaar."""
    leeg = [n for n in NAMEN if not EnterpriseCatalogLoader._normalize_agent_key(n)]
    assert not leeg, f"Deze namen geven een lege catalogussleutel: {leeg}"


# De toets hierboven meet OVEREENSTEMMING. Zet iemand BEIDE implementaties terug op de
# oude regel, dan blijft hij groen -- gemeten 2026-09-26 met mutatie S4. Dat is juist
# gedrag voor die toets, maar het laat een gat: er moet ook iets zijn dat de REGEL zelf
# vastlegt. Dit is dat iets.
VERWACHT: tuple[tuple[str, str], ...] = (
    # (klassenaam, sleutel) -- elk geval is met de OUDE `.replace("agent", "")` anders.
    ("AgentRouterAgent", "agentrouter"),              # oud: "router"
    ("AgentHealthMonitorAgent", "agenthealthmonitor"),  # oud: "healthmonitor"
    ("PaymentAgentRouterAgent", "paymentagentrouter"),  # oud: "paymentrouter"
    ("DunningAgentAgent", "dunningagent"),            # oud: "dunning" -- de bevinding zelf
    ("AgentAgent", "agent"),                          # oud: "" (leeg)
)


@pytest.mark.architecture
@pytest.mark.parametrize(("class_name", "sleutel"), VERWACHT)
def test_de_afleiding_strip_het_ACHTERVOEGSEL_en_niet_elk_voorkomen(
    class_name: str, sleutel: str
) -> None:
    """`str.replace` vervangt ELK voorkomen; dat is de fout die BE-AGT-068 opleverde."""
    gekregen = EnterpriseCatalogLoader._normalize_agent_key(class_name)
    assert gekregen == sleutel, (
        f"'{class_name}' hoort sleutel '{sleutel}' te geven maar gaf '{gekregen}'. "
        f"Lijkt dit op de oude regel `class_name.lower().replace('agent', '')`? Die eet "
        f"elk voorkomen van 'agent' op, ook midden in een naam."
    )
