"""`PublicEndpointRegistry` anchort nu op segmentgrenzen (ADR-036 OP-202, GESLOTEN 2026-09-10).

**De oorspronkelijke bevinding (2026-09-03).** `is_public()` besliste met een kale `startswith`
over `PUBLIC_PREFIXES`, en de ADR-029-foundation-regel was een SUBSTRING-toets. Daardoor golden
zes paden ten onrechte als publiek, waaronder de kruising van twee te ruime regels: de
foundation-router heeft de vorm `/{tenantSlug}/foundation/...`, dus het eerste padsegment wordt
door de AANVRAGER gekozen, en koos die `static`, dan matchte het pad ook de `/static`-prefix uit
`PUBLIC_PREFIXES` -- ook al sloot de eigen `/admin/`-uitsluiting van de foundation-regel het
daar al terecht uit. Een echte slug werkte niet: `/acme/foundation/admin/curatie` gaf `False`.

**De fix (2026-09-10).** Twee onafhankelijke reparaties in `PublicEndpointRegistry.is_public()`:

1. `_matches_prefix()` ankert elke `PUBLIC_PREFIXES`-match op een segmentgrens (`path == anchor`
   of `path.startswith(anchor + "/")`) -- sluit `/api/v1/demoagents` en
   `/api/v1/workflow-templates-internal/secrets` uit.
2. De foundation-regel matcht nu op de WERKELIJKE routevorm (`segments[2] == "foundation"`, niet
   een substring "/foundation/" ergens in het pad) EN geeft fail-closed `False` zodra het
   aanvrager-gekozen eerste segment een van de `_RESERVED_TOP_SEGMENTS` is (elk eerste segment
   van een `PUBLIC_PREFIXES`-entry: static/assets/public/health/...). Geen enkele van die drie
   heeft vandaag een eigen bestandsserver in deze app (geverifieerd: geen `StaticFiles`-mount in
   `src/`) -- de botsing met de tenantSlug-catch-all is dus zuiver toeval, en fail-closed kost
   niets, want een echte tenant krijgt zo'n gereserveerd woord nooit als slug.

Gevolg: alle zes de oorspronkelijke over-matches geven nu `False`, inclusief
`/public/foundation/content` -- ook al is "content" normaal een publiek foundation-subpad, de
botsing met de gereserveerde `/public/`-prefix wint bewust (fail-closed op de dubbelzinnigheid,
niet een aanname over de bedoeling van een specifieke aanvrager).

**Wat deze guard nu doet.** Regressiebewaking: dezelfde zes paden MOETEN niet-publiek blijven, en
de vier tegenrichting-proeven (waaronder een echte tenant-slug) MOETEN het ook blijven.

**Mutatiebewijs (BEIDE richtingen, gemeten 2026-09-10 -- niet alleen de originele 2026-09-03-ronde
op de OUDE code).** `_matches_prefix` tijdelijk terugveranderd naar kale `path.startswith(prefix)`
(werkkopie): alle drie de segmentgrens-gevallen (`/api/v1/demoagents`,
`/api/v1/demo-admin/keys`, `/api/v1/workflow-templates-internal/secrets`) weer `True` ->
`test_no_regression_on_the_original_overmatches` ROOD.

`_RESERVED_TOP_SEGMENTS`-check tijdelijk verwijderd (werkkopie): **precies EEN** van de drie
foundation/reserved-gevallen komt terug, `/public/foundation/content` -> ROOD. De andere twee
(`/static/foundation/admin/curatie`, `/assets/foundation/admin/curatie`) blijven `False`, want
die worden AL onafhankelijk uitgesloten door de bestaande `/admin/`-check verderop in dezelfde
`if`-tak -- deze mutatie raakt alleen het pad waarvoor de reserved-check de ENIGE bescherming is.
Dat is geen zwakte van de test (hij wordt wel degelijk ROOD), maar een eerdere versie van dit
bestand beweerde hier ten onrechte "alle drie" -- een Gate 2-code-review (2026-09-10) rekende de
mutatie na en vond het verschil. Correctie verwerkt, conform de eigen regel van dit project dat
een mutatiebewijs-claim nooit ongeverifieerd mag blijven staan.

Ongemuteerd: alle drie de tests GROEN.
"""

from __future__ import annotations

import pytest

from src.core.shared.public_registry import PublicEndpointRegistry

#: De zes paden die voor de OP-202-fix ten onrechte publiek waren. Reden per regel: de eerste
#: drie waren een ontbrekende segmentgrens op een `PUBLIC_PREFIXES`-entry, de laatste drie een
#: botsing tussen een aanvrager-gekozen tenantSlug en een gereserveerd top-segment.
FIXED_OVERMATCHES: dict[str, str] = {
    "/api/v1/demoagents": "prefix /api/v1/demo zonder segmentgrens -- OP-202",
    "/api/v1/demo-admin/keys": "prefix /api/v1/demo zonder segmentgrens -- OP-202",
    "/api/v1/workflow-templates-internal/secrets": (
        "prefix /api/v1/workflow-templates zonder segmentgrens -- OP-202"
    ),
    "/static/foundation/admin/curatie": (
        "aanvrager-gekozen eerste segment botst met gereserveerd /static -- OP-202"
    ),
    "/assets/foundation/admin/curatie": (
        "aanvrager-gekozen eerste segment botst met gereserveerd /assets -- OP-202"
    ),
    "/public/foundation/content": (
        "aanvrager-gekozen eerste segment botst met gereserveerd /public -- OP-202"
    ),
}

#: Moeten publiek BLIJVEN -- zonder deze zou "alles is publiek" de guard niet raken.
_STILL_PUBLIC_PROBES: tuple[str, ...] = ("/health", "/docs")

#: Moeten niet-publiek BLIJVEN (negatieve controle, inclusief een echte tenant-slug).
_NEGATIVE_PROBES: tuple[str, ...] = (
    "/acme/foundation/admin/curatie",
    "/api/v1/agents",
    "/API/V1/AUTH/LOGIN",
    "/api/v1/auth/login/",
)


@pytest.mark.architecture
def test_the_probe_set_still_reaches_the_registry() -> None:
    """Vangnet: zonder een publieke treffer bewaakt deze guard niets.

    Rood te maken door `PUBLIC_PATHS` leeg te maken; dan matcht geen enkele proef meer en zou de
    guard zwijgen terwijl hij niets meer meet.
    """
    treffers = [pad for pad in _STILL_PUBLIC_PROBES if PublicEndpointRegistry.is_public(pad)]
    assert treffers == list(_STILL_PUBLIC_PROBES), (
        f"Niet elke legitiem-publieke proef wordt nog als publiek geclassificeerd: "
        f"{treffers} != {list(_STILL_PUBLIC_PROBES)}. Is de registry herschreven, dan moet deze "
        "guard mee -- nu meet hij niets."
    )


@pytest.mark.architecture
def test_no_regression_on_the_original_overmatches() -> None:
    """De zes oorspronkelijke OP-202-over-matches mogen NOOIT weer publiek worden.

    Rood te maken door de segmentgrens-anchoring of de reserved-top-segment-check in
    `is_public()` terug te draaien -- zie de mutatiebewijs-sectie in de moduledocstring.
    """
    teruggekeerd = [pad for pad in FIXED_OVERMATCHES if PublicEndpointRegistry.is_public(pad)]
    assert not teruggekeerd, (
        "Deze paden waren gefixed (ADR-036 OP-202) maar gelden weer als publiek:\n"
        + "\n".join(f"  {pad}: {FIXED_OVERMATCHES[pad]}" for pad in sorted(teruggekeerd))
    )


@pytest.mark.architecture
def test_the_negative_probes_stay_non_public() -> None:
    """Een legitiem geval (waaronder een echte tenant-slug) mag niet per ongeluk dicht vallen.

    Zonder deze helft is "weiger alles" een geldige oplossing en sloopt de fix de foundation-
    router voor elke echte tenant. Rood te maken door de foundation-anchoring te verbreden tot
    een kale substring-toets.
    """
    onterecht_publiek = [pad for pad in _NEGATIVE_PROBES if PublicEndpointRegistry.is_public(pad)]
    assert not onterecht_publiek, (
        "Deze paden horen NIET publiek te zijn maar `is_public()` zegt van wel:\n"
        + "\n".join(f"  {pad}" for pad in sorted(onterecht_publiek))
    )


# ---------------------------------------------------------------------------
# BE-QA (2026-09-24): substring-residu in het foundation-blok zelf
# ---------------------------------------------------------------------------
# OP-202 ankerte de ROUTE-vorm (segments[2] == "foundation") en PUBLIC_PREFIXES, maar de
# sub-padchecks binnen het foundation-blok bleven substring-toetsen
# (`"/foundation/edu/session" in path`). Daardoor matcht het MEERVOUD `/edu/sessions` mee op
# de publieke prefix `/edu/session`, en een verzonnen naam als `/edu/contentevil` op
# `/edu/content`. BE-SEC-057 versmalde dit register juist bewust (edu/codes valt erbuiten);
# een niet-geankerde substring zet die versmalling stilletjes weer open voor elke toekomstige
# route die toevallig met dezelfde letters begint.
#
# Mutatiebewijs: deze test is eerst tegen de ONGEWIJZIGDE registry gedraaid (substring-versie,
# commit 45f3f45fe) en was ROOD voor alle vier de paden hieronder; na de segment-ankering in
# `is_public()` is hij GROEN. Tegenrichting: de proeven in _FOUNDATION_STILL_PUBLIC hieronder
# bleven in beide runs publiek, dus "weiger alles" is geen geldige oplossing.
FOUNDATION_SUBSTRING_OVERMATCHES: dict[str, str] = {
    "/acme/foundation/edu/sessions": (
        "meervoud van /edu/session -- substring matchte op de publieke prefix"
    ),
    "/acme/foundation/edu/contentevil": (
        "verzonnen naam -- substring matchte op /edu/content"
    ),
    "/api/v1/acme/foundation/edu/sessions": "idem, via de /api/v1-routevorm",
    "/api/v1/acme/foundation/edu/contentevil": "idem, via de /api/v1-routevorm",
}

#: Moeten publiek BLIJVEN -- de echte edu/content- en edu/session-routes (edu.py).
_FOUNDATION_STILL_PUBLIC: tuple[str, ...] = (
    "/acme/foundation/edu/session",
    "/acme/foundation/edu/content",
    "/acme/foundation/edu/content/12",
    "/api/v1/acme/foundation/edu/session",
    "/api/v1/acme/foundation/settings",
)


@pytest.mark.architecture
def test_foundation_subpaths_are_segment_anchored() -> None:
    """Foundation-subpaden matchen op segmentgrens, niet op substring.

    Rood te maken door in `is_public()` de geankerde sub-padcheck terug te vervangen door
    `"/foundation/edu/session" in path` -- zie de mutatiebewijs-notitie hierboven.
    """
    teruggekeerd = [
        pad for pad in FOUNDATION_SUBSTRING_OVERMATCHES if PublicEndpointRegistry.is_public(pad)
    ]
    assert not teruggekeerd, (
        "Deze paden matchen via een substring op een publiek foundation-subpad:\n"
        + "\n".join(
            f"  {pad}: {FOUNDATION_SUBSTRING_OVERMATCHES[pad]}" for pad in sorted(teruggekeerd)
        )
    )


@pytest.mark.architecture
def test_foundation_public_subpaths_stay_public() -> None:
    """De echte publieke edu/settings-routes mogen door de anchoring niet dicht vallen."""
    dichtgevallen = [
        pad for pad in _FOUNDATION_STILL_PUBLIC if not PublicEndpointRegistry.is_public(pad)
    ]
    assert not dichtgevallen, (
        "Deze legitiem publieke foundation-paden zijn niet meer publiek:\n"
        + "\n".join(f"  {pad}" for pad in sorted(dichtgevallen))
    )
