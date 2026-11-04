"""Afgeleide termijnen voor de HR-pilot (dag 3): BEREKEND, niet opgeslagen.

Het systeem beslist niets. Het rekent uit welke datum bij welke ingevulde datum hoort en zegt erbij
waar die regel vandaan komt:

- `primair`: de wettekst zelf is gelezen (wetten.overheid.nl);
- `secundair`: alleen uit een zoekfragment of een samenvatting; de klant controleert het zelf;
- `eigen`: geen wettelijke termijn maar een standaard van deze applicatie.

Bronnen en hun status staan hieronder bij elke regel (onderzoek:
`docs/onderzoek-hr-afdeling-taken-en-scenarios.md`, "Tweede ronde: primaire bronnen").

Er wordt GEEN diagnose of ziekteoorzaak vastgelegd of gebruikt: een verzuimregel heeft alleen een
eerste ziektedag en de datum van de probleemanalyse nodig.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

BRON_PRIMAIR = "primair"
BRON_SECUNDAIR = "secundair"
BRON_EIGEN = "eigen"

SOORT_CONTRACT_EINDE = "contract_einde"
SOORT_VERZUIM = "verzuim"
SOORT_CERTIFICAAT = "certificaat"
SOORTEN = (SOORT_CONTRACT_EINDE, SOORT_VERZUIM, SOORT_CERTIFICAAT)


@dataclass(frozen=True)
class Termijn:
    """Een berekende datum met de naam ervan en de herkomst van de regel."""

    label: str
    datum: date
    bron: str
    toelichting: str


def _een_maand_eerder(dag: date) -> date:
    """Dezelfde dag een kalendermaand terug; een kortere maand geeft zijn laatste dag."""
    maand = dag.month - 1 or 12
    jaar = dag.year - 1 if dag.month == 1 else dag.year
    laatste = calendar.monthrange(jaar, maand)[1]
    return date(jaar, maand, min(dag.day, laatste))


def afgeleide_termijnen(
    soort: str,
    *,
    start_date: date | None,
    end_date: date | None,
    analysis_date: date | None,
) -> list[Termijn]:
    """De berekende termijnen voor een ingevulde regel. `ValueError` bij een onbekende soort of
    een ontbrekende datum die voor die soort nodig is."""
    if soort == SOORT_CONTRACT_EINDE:
        if end_date is None:
            raise ValueError("contract_einde vraagt een einddatum")
        return [
            # SECUNDAIR: BW 7:668 (aanzegverplichting bij een contract voor bepaalde tijd,
            # minimaal een maand voor het einde). De primaire wettekst kon niet worden opgehaald
            # (afgekapt); de klant controleert dit zelf.
            Termijn(
                "Aanzegdatum",
                _een_maand_eerder(end_date),
                BRON_SECUNDAIR,
                "Uiterlijk een maand voor het einde van het contract aanzeggen of verlengen.",
            )
        ]

    if soort == SOORT_VERZUIM:
        if start_date is None:
            raise ValueError("verzuim vraagt een startdatum (eerste ziektedag)")
        termijnen = [
            # PRIMAIR: Regeling procesgang eerste en tweede ziektejaar (BWBR0013540), art. 2:
            # de probleemanalyse uiterlijk in de zesde week. BEWUST DE STRENGSTE LEZING: de
            # laatste dag van week zes, dus eerste ziektedag + 41 dagen (dag 1 = eerste ziektedag).
            # Een lezing van zes weken erna (+42 dagen) zou een dag te laat kunnen zijn, en dat
            # is voor een werkgever erger dan een dag te vroeg.
            Termijn(
                "Probleemanalyse",
                start_date + timedelta(days=41),
                BRON_PRIMAIR,
                "Uiterlijk op de laatste dag van de zesde week na de eerste ziektedag.",
            ),
        ]
        if analysis_date is not None:
            termijnen.append(
                # PRIMAIR: dezelfde regeling, art. 4 lid 1: het plan van aanpak binnen twee weken
                # NA de probleemanalyse. Dus gerekend vanaf de WERKELIJKE datum van de analyse,
                # niet vast op week 8.
                Termijn(
                    "Plan van aanpak",
                    analysis_date + timedelta(weeks=2),
                    BRON_PRIMAIR,
                    "Uiterlijk twee weken na de datum van de probleemanalyse.",
                )
            )
        termijnen.extend(
            [
                # SECUNDAIR: de melding bij het UWV rond week 42 komt alleen uit zoekfragmenten
                # van UWV.nl; de primaire tekst is niet gelezen. De klant controleert het zelf.
                Termijn(
                    "Melding UWV (week 42)",
                    start_date + timedelta(weeks=42),
                    BRON_SECUNDAIR,
                    "Rond week 42 van de ziekte; controleer de actuele regels bij het UWV.",
                ),
                # EIGEN (de datum): de VERPLICHTING van een eerstejaarsevaluatie staat in dezelfde
                # regeling, art. 4 lid 2 sub b (primair), maar het moment rond week 52 is een
                # richtdatum van deze applicatie (een jaar na de eerste ziektedag), geen
                # letterlijke wettelijke datum. Het label zegt dus niet meer dan we weten.
                Termijn(
                    "Eerstejaarsevaluatie",
                    start_date + timedelta(weeks=52),
                    BRON_EIGEN,
                    "Richtdatum rond week 52; de evaluatie zelf is verplicht (Regeling procesgang "
                    "art. 4 lid 2 sub b), de exacte datum bepaalt u zelf.",
                ),
            ]
        )
        return termijnen

    if soort == SOORT_CERTIFICAAT:
        if end_date is None:
            raise ValueError("certificaat vraagt een einddatum")
        return [
            # EIGEN: geen wettelijke termijn. Een standaard van deze applicatie: dertig dagen
            # voor de einddatum, zodat er tijd is om te verlengen.
            Termijn(
                "Certificaat verlengen",
                end_date - timedelta(days=30),
                BRON_EIGEN,
                "Dertig dagen voor het einde van de geldigheid; een standaard van deze applicatie.",
            )
        ]

    raise ValueError(f"onbekende soort termijn: {soort!r}")
