"""Het aantal routes zonder auth-dependency is een MEETWAARDE, geen anekdote (OP-62).

**De bevinding.** De registerrij noteert "839 routes, 155 zonder route-eigen
auth-dependency" -- gemeten met de hand, op een dag, en daarna nooit meer. Bij de hermeting
van 2026-08-29 bleek dat getal niet reproduceerbaar: de meting vereist een geassembleerde
FastAPI-app, en een statische AST-telling gaf 997 gedeclareerd / 290 zonder. Die twee meten
niet hetzelfde. Zolang niemand het kan naspelen, is het geen bevinding maar een herinnering.

**De uitkomst van die meting, 2026-08-30.** 788 unieke geserveerde paden, waarvan 153 zonder
herkenbare auth-dependency. Dat ligt dicht bij de 839/155 uit de registerrij -- het verschil in
het totaal is te verklaren doordat de rij ROUTES telde en dit PADEN (een pad met GET en POST is
een pad, twee routes).

Dat is meteen een correctie op het auditrapport van 2026-08-29, dat noteerde dat deze meting
niet reproduceerbaar was. Zij was niet reproduceerbaar in DIE omgeving (geen fastapi
geinstalleerd), niet in deze. De oorspronkelijke meting stond er dus beter voor dan de audit
suggereerde; wat ontbrak was niet de juistheid maar de herhaalbaarheid. Die staat nu vast.

**Wat deze guard doet, en wat NIET.** Hij meet, legt de meting vast, en wordt rood zodra het
aantal routes zonder auth GROEIT. Hij lost OP-62 niet op -- de triage van de bestaande
gevallen in "bewust publiek", "leunt op de middleware" en "te repareren" is eigen werk, en een
default-deny op `src/api/v1/` is een eigen wijziging. Wat hij wel doet is voorkomen dat het
getal ongemerkt oploopt terwijl de rij op een oude anekdote blijft staan.

**Waarom een bovengrens en geen exact getal.** Een exacte gelijkheid maakt elke toegevoegde
publieke route (health, metrics) tot een rode gate en nodigt uit tot gedachteloos ophogen. Een
bovengrens met een gedateerde nulmeting maakt de RICHTING zichtbaar: omlaag mag altijd, omhoog
vraagt een bewuste stap.

**Mutatietest (2026-08-30, beide richtingen):** de bovengrens op de gemeten waarde min een
gezet -> ROOD met beide getallen in de melding; teruggezet -> GROEN.
"""

from __future__ import annotations

import pytest

from tests.architecture._api_surface import paden_zonder_auth, route_paden

#: Nulmeting 2026-08-30 op de app die `create_test_app()` bouwt.
GEMETEN_OP = "2026-08-30"

#: Bovengrens voor het aantal PADEN zonder herkenbare auth-dependency. Verlagen mag zonder
#: overleg; verhogen hoort een bewuste, toegelichte stap te zijn (ADR-036 OP-62).
#: 2026-09-11 (ADR-029 Foundation Portal): 153 -> 157 (+4 unieke publieke paden voor
#: publieke erfgoed-ontsluiting: oai-pmh metadata harvesting, openbare content/media catalogus,
#: geo-kaart bbox en publieke tenant-resolutie).
#: 2026-09-12 (ADR-029 P2-5 Sitemap & P2-EDU): 157 -> 161 (+4 unieke publieke paden voor
#: publieke sitemap.xml en publiek bereikbare onderwijs toegangscodes endpoints).
#: 2026-09-24 (BE-QA architectuur-groen, iter/wk1-architectuur-groen): 161 -> 186 (+27 nieuw,
#: -2 verdwenen). Diff gemeten tegen pin-commit 7a0fe78c6 met dezelfde helper
#: (tests/architecture/_api_surface.paden_zonder_auth) op beide commits:
#:   - VERDWENEN (-2): /{tenantSlug}/foundation/edu/codes en /edu/codes/{id} -- de BE-SEC-057-
#:     versmalling; code-beheer vereist nu een curator/admin-JWT. Gewenste krimp.
#:   - DUAL-MOUNT (+17): de foundation-router serveert sinds de /api/v1-dual-registratie elk
#:     bestaand publiek pad ook onder /api/v1/{tenantSlug}/foundation/... -- dit zijn de
#:     DEZELFDE handlers die in de 161-nulmeting al als bewust publiek golden (content,
#:     content/{id}, media, map/bbox, oai-pmh, settings, sitemap.xml, auth/logout e.a.).
#:   - NIEUW, per endpoint geverifieerd in de router-code (+10):
#:     * auth/quick-login: publiek maar fail-closed -- 403 zodra ENVIRONMENT=production
#:       (auth.py:467-472), geen rol-promotie voor bestaande users (BE-SEC-054).
#:     * contact: POST met require_hcaptcha (contact.py:57) + rate limit.
#:     * donations/checkout: POST met require_hcaptcha (donations.py:62).
#:     * donations/webhook: Stripe handtekening-verificatie (donations.py:234-251).
#:     * donations/stats: publieke transparantie-telling, bewust publiek (BE-EP-046).
#:     * newsletter/confirm + newsletter/unsubscribe: token-hash-verificatie + generieke
#:       anti-enumeratie-responses + rate limit (newsletter.py).
#:     * content/{id}/media/stream: privacy/visibility/moderatie-gate in de handler
#:       (upload.py:403-458) + portal_media_read_limit.
#:     * robots.txt (3 vormen): statische SEO-directive, publiek by design (sitemap.py).
#: Geen endpoint gevonden dat per ongeluk publiek is; niets hoeft dichtgezet te worden.
MAX_PADEN_ZONDER_AUTH = 186


#: Ondergrens voor het totaal aantal geserveerde paden -- vangnet tegen een lege meting.
MIN_PADEN_TOTAAL = 750


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_the_measurement_is_not_empty() -> None:
    """Vangnet: assembleert de app niet, dan meet alles hieronder nul en slaagt het altijd."""
    totaal = len(route_paden())

    assert totaal >= MIN_PADEN_TOTAAL, (
        f"Slechts {totaal} paden gevonden op de geassembleerde app (ondergrens "
        f"{MIN_PADEN_TOTAAL}, gemeten {GEMETEN_OP}). Registreert `create_test_app()` de routers "
        "nog wel? Zonder routes bewijst de toets hieronder niets."
    )


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_the_number_of_unauthenticated_paths_does_not_grow() -> None:
    """Het aantal paden zonder auth-dependency mag dalen, niet stijgen."""
    zonder = paden_zonder_auth()

    assert len(zonder) <= MAX_PADEN_ZONDER_AUTH, (
        f"Er zijn nu {len(zonder)} paden zonder herkenbare auth-dependency; de nulmeting van "
        f"{GEMETEN_OP} stond op {MAX_PADEN_ZONDER_AUTH}.\n\n"
        "Een route zonder route-eigen dependency leunt volledig op de middleware. Dat KAN "
        "bewust zijn (health, metrics, login), maar dan hoort het een keuze te zijn en geen "
        "bijproduct. Voeg de dependency toe, of verhoog deze grens met een toelichting waarom "
        "de nieuwe route publiek is (ADR-036 OP-62).\n\n"
        "Paden zonder auth:\n  " + "\n  ".join(zonder)
    )
