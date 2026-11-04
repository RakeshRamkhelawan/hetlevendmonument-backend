"""Instellingen in `tenants.settings` die een algemene wijziging van `settings` niet mag wissen.

`TenantService.update_tenant` zet `settings` als GEHEEL. Een beheerder van de eigen tenant bereikt dat via
`PUT /api/v1/tenants/{id}`. Wat daarbij niet in de nieuwe waarde staat, verdwijnt: een ontbrekende vier-ogen-sleutel
betekent UIT (`four_eyes_from_settings`), dus een wijziging van een ongerelateerde instelling zette vier ogen stil uit
en wiste de escalatietermijn en de taalmodelkeuze (gerichte security-review F1, 2026-10-20).

Deze instellingen hebben een eigen route en een eigen auditregel; een algemene wijziging laat ze staan, tenzij hij ze
UITDRUKKELIJK meegeeft (dan wint de nieuwe waarde, zoals bij `behoud_llm_keuze`). De sleutels staan hier als tekst en
niet als import van hun eigenaren, zodat `shared` van niets afhangt; een test houdt ze gelijk
(`tests/unit/test_update_tenant_behoudt_beheerde_instellingen.py`).
"""

from __future__ import annotations

from collections.abc import Mapping

#: Deze instellingen wijzig je ALLEEN via hun eigen route (lijst uit de catalogus, CSRF, tempo, auditregel). Een
#: algemene wijziging van `settings` (`PUT /api/v1/tenants/{id}`) neemt ze ALTIJD uit de oude waarde; een meegegeven waarde
#: wordt genegeerd en met alleen de sleutelnaam gelogd, geen fout (besluit 2026-10-22: anders zet een beheerder vier ogen
#: UIT langs de eigen route met zijn controles en auditregel heen).
ALLEEN_EIGEN_ROUTE = frozenset(
    {
        # Vier ogen per actie (ADR-039) en de markering dat de beheerder de uitleg nog moet zien.
        "four_eyes_actions",
        "four_eyes_explanation_pending",
        # De escalatietermijn van de debiteuren (BE-DEB-004), eigen route `PUT /api/v1/receivables/settings`.
        "escalatie_na_dagen",
    }
)

#: De taalmodelkeuze (ADR-041 B14) heeft GEEN eigen route: `PUT /api/v1/tenants/{id}` met het gevalideerde schema is de
#: route ("per klant schakelbaar"). Hij blijft dus behouden als hij ontbreekt, maar een uitdrukkelijke waarde wint.
BEHOUDEN_ALS_ONTBREEKT = frozenset({"llm_provider"})

BEHEERDE_INSTELLINGEN = ALLEEN_EIGEN_ROUTE | BEHOUDEN_ALS_ONTBREEKT


def behoud_beheerde_instellingen(
    oud: Mapping[str, object] | None, nieuw: dict[str, object]
) -> dict[str, object]:
    """De nieuwe instellingen, met de beheerde sleutels zoals hierboven beschreven.

    Sleutels in `ALLEEN_EIGEN_ROUTE`: altijd de oude waarde; stond de sleutel er niet, dan verdwijnt een meegegeven
    waarde. `llm_provider`: de oude waarde als hij in de nieuwe ontbreekt. Geeft een nieuw dict; `nieuw` en `oud`
    blijven ongewijzigd.
    """
    uit = dict(nieuw)
    oud_map: Mapping[str, object] = oud if isinstance(oud, Mapping) else {}
    for sleutel in ALLEEN_EIGEN_ROUTE:
        if sleutel in oud_map:
            uit[sleutel] = oud_map[sleutel]
        else:
            uit.pop(sleutel, None)
    for sleutel in BEHOUDEN_ALS_ONTBREEKT:
        if sleutel not in uit and sleutel in oud_map:
            uit[sleutel] = oud_map[sleutel]
    return uit


def genegeerde_beheerde_instellingen(
    oud: Mapping[str, object] | None, nieuw: Mapping[str, object]
) -> list[str]:
    """De sleutels uit `ALLEEN_EIGEN_ROUTE` die `nieuw` meegaf met een andere waarde dan de oude, gesorteerd.

    Alleen de NAMEN: de waarden horen niet in een logregel.
    """
    oud_map: Mapping[str, object] = oud if isinstance(oud, Mapping) else {}
    return sorted(
        sleutel
        for sleutel in ALLEEN_EIGEN_ROUTE
        if sleutel in nieuw and (sleutel not in oud_map or nieuw[sleutel] != oud_map[sleutel])
    )
