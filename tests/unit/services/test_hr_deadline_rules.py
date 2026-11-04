"""De afgeleide termijnen worden BEREKEND uit de ingevulde data (HR-pilot dag 3).

Voorbeelden uit de dagbrief; elke regel noemt in de module of de bron primair of secundair is.
Het systeem beslist niets: het rekent een datum uit en zegt waar die vandaan komt.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.core.utils.hr_deadline_rules import Termijn, afgeleide_termijnen


def _per_label(termijnen: list[Termijn]) -> dict[str, Termijn]:
    return {t.label: t for t in termijnen}


class TestContractEinde:
    def test_de_aanzegdatum_is_een_maand_voor_het_einde(self) -> None:
        termijnen = afgeleide_termijnen(
            "contract_einde", start_date=None, end_date=date(2026, 12, 31), analysis_date=None
        )

        assert _per_label(termijnen)["Aanzegdatum"].datum == date(2026, 11, 30)

    def test_een_maand_terug_valt_op_het_einde_van_een_kortere_maand(self) -> None:
        termijnen = afgeleide_termijnen(
            "contract_einde", start_date=None, end_date=date(2026, 3, 31), analysis_date=None
        )

        assert _per_label(termijnen)["Aanzegdatum"].datum == date(2026, 2, 28)

    def test_de_aanzegdatum_komt_uit_een_secundaire_bron(self) -> None:
        termijnen = afgeleide_termijnen(
            "contract_einde", start_date=None, end_date=date(2026, 12, 31), analysis_date=None
        )

        assert _per_label(termijnen)["Aanzegdatum"].bron == "secundair"

    def test_zonder_einddatum_is_er_geen_berekening(self) -> None:
        with pytest.raises(ValueError):
            afgeleide_termijnen(
                "contract_einde", start_date=None, end_date=None, analysis_date=None
            )


class TestVerzuim:
    START = date(2026, 10, 1)

    def test_de_probleemanalyse_is_uiterlijk_op_de_laatste_dag_van_week_zes(self) -> None:
        termijnen = afgeleide_termijnen(
            "verzuim", start_date=self.START, end_date=None, analysis_date=None
        )

        # Strengste lezing van "uiterlijk in de zesde week": eerste ziektedag + 41 dagen.
        assert _per_label(termijnen)["Probleemanalyse"].datum == date(2026, 11, 11)

    def test_de_probleemanalyse_komt_uit_een_primaire_bron(self) -> None:
        termijnen = afgeleide_termijnen(
            "verzuim", start_date=self.START, end_date=None, analysis_date=None
        )

        assert _per_label(termijnen)["Probleemanalyse"].bron == "primair"

    def test_het_plan_van_aanpak_komt_twee_weken_na_de_werkelijke_analyse(self) -> None:
        termijnen = afgeleide_termijnen(
            "verzuim",
            start_date=self.START,
            end_date=None,
            analysis_date=date(2026, 11, 5),
        )

        assert _per_label(termijnen)["Plan van aanpak"].datum == date(2026, 11, 19)

    def test_zonder_analysedatum_is_er_nog_geen_plan_van_aanpak(self) -> None:
        termijnen = afgeleide_termijnen(
            "verzuim", start_date=self.START, end_date=None, analysis_date=None
        )

        assert "Plan van aanpak" not in _per_label(termijnen)

    def test_het_plan_van_aanpak_staat_niet_vast_op_week_acht(self) -> None:
        termijnen = afgeleide_termijnen(
            "verzuim",
            start_date=self.START,
            end_date=None,
            analysis_date=date(2026, 11, 12),
        )

        assert _per_label(termijnen)["Plan van aanpak"].datum == date(2026, 11, 26)

    def test_de_melding_bij_het_uwv_is_in_week_42(self) -> None:
        termijnen = afgeleide_termijnen(
            "verzuim", start_date=self.START, end_date=None, analysis_date=None
        )

        assert _per_label(termijnen)["Melding UWV (week 42)"].datum == date(2027, 7, 22)

    def test_de_melding_bij_het_uwv_komt_uit_een_secundaire_bron(self) -> None:
        termijnen = afgeleide_termijnen(
            "verzuim", start_date=self.START, end_date=None, analysis_date=None
        )

        assert _per_label(termijnen)["Melding UWV (week 42)"].bron == "secundair"

    def test_de_eerstejaarsevaluatie_is_rond_week_52(self) -> None:
        termijnen = afgeleide_termijnen(
            "verzuim", start_date=self.START, end_date=None, analysis_date=None
        )

        assert _per_label(termijnen)["Eerstejaarsevaluatie"].datum == date(2027, 9, 30)

    def test_zonder_startdatum_is_er_geen_berekening(self) -> None:
        with pytest.raises(ValueError):
            afgeleide_termijnen("verzuim", start_date=None, end_date=None, analysis_date=None)


class TestCertificaat:
    def test_het_signaal_komt_dertig_dagen_voor_het_einde(self) -> None:
        termijnen = afgeleide_termijnen(
            "certificaat", start_date=None, end_date=date(2026, 12, 1), analysis_date=None
        )

        assert _per_label(termijnen)["Certificaat verlengen"].datum == date(2026, 11, 1)

    def test_dit_is_een_eigen_standaard_en_geen_wettelijke_termijn(self) -> None:
        termijnen = afgeleide_termijnen(
            "certificaat", start_date=None, end_date=date(2026, 12, 1), analysis_date=None
        )

        assert _per_label(termijnen)["Certificaat verlengen"].bron == "eigen"


def test_een_onbekende_soort_wordt_geweigerd() -> None:
    with pytest.raises(ValueError):
        afgeleide_termijnen("onzin", start_date=None, end_date=date(2026, 1, 1), analysis_date=None)


class TestRandgevallen:
    def test_een_maand_terug_vanaf_31_mei_geeft_30_april(self) -> None:
        termijnen = afgeleide_termijnen(
            "contract_einde", start_date=None, end_date=date(2026, 5, 31), analysis_date=None
        )

        assert _per_label(termijnen)["Aanzegdatum"].datum == date(2026, 4, 30)

    def test_een_maand_terug_in_een_schrikkeljaar_geeft_29_februari(self) -> None:
        termijnen = afgeleide_termijnen(
            "contract_einde", start_date=None, end_date=date(2028, 3, 31), analysis_date=None
        )

        assert _per_label(termijnen)["Aanzegdatum"].datum == date(2028, 2, 29)

    def test_een_maand_terug_vanaf_januari_gaat_naar_december_van_het_jaar_ervoor(self) -> None:
        termijnen = afgeleide_termijnen(
            "contract_einde", start_date=None, end_date=date(2027, 1, 15), analysis_date=None
        )

        assert _per_label(termijnen)["Aanzegdatum"].datum == date(2026, 12, 15)

    def test_de_eerstejaarsevaluatie_is_een_richtdatum_en_geen_wettelijke_datum(self) -> None:
        termijnen = afgeleide_termijnen(
            "verzuim", start_date=date(2026, 10, 1), end_date=None, analysis_date=None
        )

        assert _per_label(termijnen)["Eerstejaarsevaluatie"].bron == "eigen"
