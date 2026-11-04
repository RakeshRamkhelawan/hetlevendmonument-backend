"""ADR-036 fix-sprint dag 3-nazorg (tweede blinde review, 2026-08-19).

BE-FLW-057 werd TWEE keer uitgegeven binnen dezelfde sprint: eerst voor de dag-3-
HITL-ticketflow (die zelf al een eerdere botsing met BE-FLW-050 corrigeerde), terwijl
BE-SEC-045 (dag 1) het al vijftien keer gebruikte zonder ooit een eigen rij in
ID-REGISTRY.md te krijgen. De "volgend vrij ID"-check doorzocht alleen deze registry, niet
de daadwerkelijke specs op disk -- exact de faalvorm die `test_feature_doc_ids_are_unique.py`
al beschrijft voor Feature-IDs ("ID-REGISTRY.md alleen vertrouwen... loopt achter op de
daadwerkelijke bestanden"), nu voor Flow-IDs.

Deze guard dekt alleen de HARDE, altijd-aantoonbare helft: een Flow-ID mag nooit meer dan
EEN rij in ID-REGISTRY.md hebben. De bredere helft (elke referentie in een spec moet ook
geregistreerd zijn) heeft vandaag 15 pre-existing, ongerelateerde gaten uit oudere sprints
(router-splits, service-lagen) -- dat oplossen vereist per geval uitzoeken welke spec de
"echte" eigenaar is, en valt buiten de scope van deze dag-3-nazorg.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = REPO_ROOT / "docs" / "backend" / "features" / "ID-REGISTRY.md"

REGISTRY_ROW_PATTERN = re.compile(r"^\| (BE-FLW-\d+) \|", re.MULTILINE)


def _registered_flow_ids() -> list[str]:
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    return REGISTRY_ROW_PATTERN.findall(text)


def test_no_flow_id_is_registered_more_than_once() -> None:
    """Elke BE-FLW-ID heeft precies EEN rij in ID-REGISTRY.md.

    Mutatiebewijs: een tweede `| BE-FLW-001 | ... |`-regel toevoegen maakt deze test rood
    (bevestigd 2026-08-19); de huidige, unieke registratie van elke ID blijft groen.
    """
    registered = _registered_flow_ids()
    duplicates = sorted({i for i in registered if registered.count(i) > 1})
    assert not duplicates, (
        f"BE-FLW-ID(s) meermaals geregistreerd in ID-REGISTRY.md: {duplicates}. Dit is "
        "precies hoe BE-FLW-057 op ADR-036 fix-sprint dag 3 een tweede keer werd uitgegeven "
        "(zie ID-REGISTRY.md's BE-FLW-057/BE-FLW-058-rijen). Kies een nieuw, elders "
        "ongebruikt nummer i.p.v. een bestaande rij te laten staan naast een nieuwe."
    )
