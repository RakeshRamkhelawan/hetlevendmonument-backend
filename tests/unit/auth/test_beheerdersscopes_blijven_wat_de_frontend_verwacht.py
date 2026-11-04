"""De scopes van een beheerder zijn precies wat de frontend aanneemt (ADR-036 OP-193).

**Waarom deze test bestaat.** De Vitest-test
`frontend/src/components/auth/__tests__/AdminRoute.echte.scopes.test.tsx` bewijst dat een
beheerder op `/forbidden` landt, en gebruikt daarvoor een fixture `BEHEERDER_SCOPES` met de
vier scopes die `_get_user_scopes` uitgeeft. Die fixture is overgeschreven uit de backend en
is dus mijn woord tegen de code, niet een meting. Zonder klem veroudert hij stil: verandert
`_get_user_scopes`, dan blijft de frontendtest groen op een verzameling die niet meer bestaat
en meet hij iets anders dan de werkelijkheid.

Deze test is die klem, en hij heeft twee helften die verschillende dingen bewaken:

1. `test_een_beheerder_krijgt_exact_deze_scopes` -- EXACTE gelijkheid, geen deelverzameling.
   Een toets die alleen controleert dat de vier erin zitten, laat een vijfde scope stil toe;
   dan klopt de fixture niet meer terwijl de test groen blijft.
2. `test_geen_enkele_scope_drukt_beheerderschap_uit` -- de EIGENSCHAP waar het besluit uit
   ADR-036 OP-186 op rust: een beheerder krijgt niets in zijn token dat zegt DAT hij
   beheerder is, want de loper op rolnaam is er bewust uitgehaald en het oordeel valt
   server-side. Precies daarom kan de frontend het niet uit scopes afleiden en beantwoordt
   `/me` de vraag expliciet met `is_admin`. Zonder deze helft bewaakt de klem vier NAMEN in
   plaats van de eigenschap die het hele ontwerp draagt.

**Mutatiebewijs (2026-09-18), beide richtingen, terugweg via een kopie:**

    `OAuth2Scope.ADMIN_ALL.value` toegevoegd aan de admin-tak van `_get_user_scopes`
        -> 2 failed: ..._krijgt_exact_deze_scopes EN ..._drukt_beheerderschap_uit
    `"tenant:admin"` toegevoegd aan diezelfde tak
        -> 2 failed: dezelfde twee
    `OAuth2Scope.WORKFLOWS_WRITE.value` weggehaald uit de beheerderstak
        -> 2 failed: ..._krijgt_exact_deze_scopes EN ..._krijgt_minder_dan_een_beheerder
    ongemuteerd
        -> 3 passed

**Correctie op mijn eigen voorspelling, want die was fout.** Bij de derde mutatie had ik
"1 failed, alleen de klem" opgeschreven. Gemeten zijn het er TWEE: haal je
`workflows:write` bij de beheerder weg, dan houdt een gewone gebruiker
(`users:read, workflows:read, workflows:write`) een scope die de beheerder niet meer heeft,
en is hij geen echte deelverzameling meer. Dat is geen ruis maar precies wat die derde test
hoort te zien. De les is de reden dat dit blok gemeten en niet bedacht wordt opgeschreven:
een voorspeld mutatieresultaat leest net zo overtuigend als een gemeten resultaat.

Wat de drie mutaties samen aantonen: een toegevoegde beheerdersmarkering raakt de klem EN
de eigenschap (1 en 2), een verschoven scope raakt de klem EN het onderscheid (3). De
eigenschapstest is dus de enige die uitsluitend op beheerdersmarkeringen reageert.
"""

from __future__ import annotations

import pytest

from src.core.api.auth.router_login import _get_user_scopes

#: Wat de frontendfixture `BEHEERDER_SCOPES` aanneemt. Verandert deze verzameling, dan MOET
#: `AdminRoute.echte.scopes.test.tsx` mee veranderen -- dat is het hele punt van deze test.
VERWACHTE_BEHEERDERSSCOPES = {
    "users:read",
    "users:write",
    "workflows:read",
    "workflows:write",
}

#: Woorden waarmee een scope beheerderschap zou uitdrukken. `admin:*` is de scope die
#: `scopes.py:24` kent; `tenant:admin` is wat `AdminRoute` tot 2026-09-18 eiste en wat
#: nergens werd uitgegeven.
BEHEERDERSMARKERINGEN = ("admin", "superuser", "root", "*")


class _Rol:
    def __init__(self, naam: str) -> None:
        self.name = naam


class _Gebruiker:
    def __init__(self, *rolnamen: str) -> None:
        self.roles = [_Rol(n) for n in rolnamen]


@pytest.mark.asyncio
async def test_een_beheerder_krijgt_exact_deze_scopes() -> None:
    """EXACTE gelijkheid: een vijfde scope erbij moet deze test rood maken."""
    gevonden = set(await _get_user_scopes(_Gebruiker("admin")))

    assert gevonden == VERWACHTE_BEHEERDERSSCOPES, (
        "De scopes van een beheerder zijn veranderd.\n"
        f"  nu:      {sorted(gevonden)}\n"
        f"  verwacht:{sorted(VERWACHTE_BEHEERDERSSCOPES)}\n"
        "Werk `BEHEERDER_SCOPES` in "
        "frontend/src/components/auth/__tests__/AdminRoute.echte.scopes.test.tsx bij, anders "
        "meet die test een verzameling die niet meer bestaat en blijft hij groen om de "
        "verkeerde reden (ADR-036 OP-193)."
    )


@pytest.mark.asyncio
async def test_geen_enkele_scope_drukt_beheerderschap_uit() -> None:
    """De eigenschap uit ADR-036 OP-186, en de reden dat `/me` `is_admin` teruggeeft."""
    gevonden = sorted(await _get_user_scopes(_Gebruiker("admin")))

    verdacht = [
        scope
        for scope in gevonden
        if any(markering in scope.lower() for markering in BEHEERDERSMARKERINGEN)
    ]

    assert not verdacht, (
        f"Deze scopes drukken beheerderschap uit: {verdacht}. Dat is een loper op rolnaam, en "
        "die is in ADR-036 OP-186 bewust uit het token gehaald omdat elke rol die toevallig "
        "`admin` heet daarmee volledige macht kreeg zonder dat de database werd geraadpleegd.\n"
        "Beantwoord de beheerdersvraag via `is_admin` op `/me` (OP-193), niet via een scope."
    )


@pytest.mark.asyncio
async def test_een_gewone_gebruiker_krijgt_minder_dan_een_beheerder() -> None:
    """Zonder deze toets is 'geef iedereen dezelfde scopes' een geldige oplossing.

    Dat zou beide tests hierboven groen houden terwijl het onderscheid dat ze bewaken
    verdwenen is.
    """
    beheerder = set(await _get_user_scopes(_Gebruiker("admin")))
    gebruiker = set(await _get_user_scopes(_Gebruiker("user")))

    assert gebruiker < beheerder, (
        f"Een gewone gebruiker ({sorted(gebruiker)}) heeft niet minder rechten dan een "
        f"beheerder ({sorted(beheerder)}). Het onderscheid dat deze testset bewaakt bestaat "
        "dan niet meer."
    )
