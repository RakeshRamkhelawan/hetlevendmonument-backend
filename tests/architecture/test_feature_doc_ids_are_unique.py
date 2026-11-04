"""AUDIT-ARCH-2026-07-02 Dag 2 -- ontdekt tijdens feature-doc-registratie
(niet in scope van de audit zelf, apart genoteerd als SP-DOCS-ARCH-1).

`docs/backend/features/` en `docs/frontend/features/` gebruiken een BE-<domein>-
<nummer>/FE-<domein>-<nummer> ID-conventie, maar meerdere IDs zijn dubbel
gebruikt voor totaal ongerelateerde specs uit verschillende sprints (bijv.
BE-GOV-001 t/m BE-GOV-004 hebben elk 2 conflicterende bestanden,
BE-SEC-001/002 ook). Dit maakt ID-REGISTRY.md-lookups ambigu en is precies het
soort drift dat leidt tot verwarring over welke spec bij welke bevinding hoort.

Deze test is bewust ROOD (backlog, SP-DOCS-ARCH-1) -- het corrigeren van alle
bestaande collisions vereist het narekenen van de volledige sprint-geschiedenis
per collisie (welke spec is de "echte" eigenaar van het ID) en valt buiten de
scope van deze architectuur-audit-sprint. Nieuwe specs mogen GEEN nieuwe
collisions toevoegen (zie `_KNOWN_COLLISIONS` -- alleen pre-existing entries
staan hier, nieuwe collisions doen de test verder falen dan het huidige aantal).
"""

import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FEATURE_DIRS = (
    REPO_ROOT / "docs" / "backend" / "features",
    REPO_ROOT / "docs" / "frontend" / "features",
)

ID_PATTERN = re.compile(r"^((?:BE|FE)-[A-Z0-9]+-\d+)-")


def _ids_to_files() -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    for feature_dir in FEATURE_DIRS:
        if not feature_dir.exists():
            continue
        for md_file in feature_dir.glob("*.md"):
            if md_file.name == "ID-REGISTRY.md":
                continue
            match = ID_PATTERN.match(md_file.name)
            if match:
                mapping[match.group(1)].append(md_file.name)
    return mapping


def test_no_new_feature_doc_id_collisions_beyond_known_backlog() -> None:
    """SP-DOCS-ARCH-1: bestaande collisions blijven staan (backlog), maar het
    totale aantal dubbel-gebruikte IDs mag niet stijgen t.o.v. de bekende
    baseline van vandaag (2026-07-02)."""
    ontbrekend = [str(d) for d in FEATURE_DIRS if not d.exists()]
    assert not ontbrekend, (
        f"Deze paden in FEATURE_DIRS bestaan niet: {ontbrekend}. Verplaatst of hernoemd? "
        "Deze guard controleert dan een deel van de feature-docs helemaal niet meer."
    )

    mapping = _ids_to_files()
    totaal = sum(len(files) for files in mapping.values())
    assert totaal >= 400, (
        f"Slechts {totaal} feature-doc-bestanden met een BE-/FE-ID gevonden -- dat lijkt "
        "een (bijna) lege scan. Deze guard controleert dan vrijwel niets."
    )

    duplicates = {id_: files for id_, files in mapping.items() if len(files) > 1}

    KNOWN_BASELINE_COUNT = 0  # doel: 0 -- vandaag staat de teller hoger, zie assert-bericht
    assert len(duplicates) <= KNOWN_BASELINE_COUNT, (
        f"{len(duplicates)} feature-doc-ID(s) worden hergebruikt door meerdere, "
        f"ongerelateerde specs (SP-DOCS-ARCH-1 backlog): {duplicates}. "
        "Nieuwe specs: kies altijd een vrij nummer (grep docs/backend/features/ "
        "eerst) i.p.v. te vertrouwen op ID-REGISTRY.md alleen, want die loopt "
        "achter op de daadwerkelijke bestanden op disk."
    )
