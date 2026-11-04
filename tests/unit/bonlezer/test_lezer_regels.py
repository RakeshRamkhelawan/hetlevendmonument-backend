"""De lezer bouwt regels op uit de posities van Docling's tekstcellen (bonlezer dag 1).

Aanleiding, gemeten in de eerste meting (docs/evidence/bonlezer-meting-*.md): Docling's platte tekst
voegt aangrenzende regels samen tot een alinea. De veldenlaag werkt per regel en vond daardoor het
totaal maar in 1 van de 24 documenten. De cellen die Docling zelf bewaart hebben wel een positie
(woorden bij OCR, regels bij een PDF met tekstlaag); daaruit zijn de regels weer op te bouwen.

De resultaatobjecten hier zijn nagemaakt, met alleen de velden die de lezer gebruikt. De echte
vorm is in de meetcontainer vastgesteld (`pages[i].assembled.elements[j].cluster.cells[k]` met
`.text` en `.rect.r_x0/r_y0/r_x2/r_y2/coord_origin`).

Mutatiebewijs (2026-10-15): zie de commitboodschap.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.als.bonlezer import lezer as lezer_module
from src.core.als.bonlezer.lezer import OngeldigBestand, regels_uit_resultaat


def _cel(
    tekst: str, x0: float, y0: float, x2: float, y2: float, oorsprong: str = "TOPLEFT"
) -> object:
    rect = SimpleNamespace(r_x0=x0, r_y0=y0, r_x2=x2, r_y2=y2, coord_origin=oorsprong)
    return SimpleNamespace(text=tekst, rect=rect)


def _resultaat(*elementen: list[object], export: str = "export") -> object:
    pagina = SimpleNamespace(
        assembled=SimpleNamespace(
            elements=[
                SimpleNamespace(cluster=SimpleNamespace(cells=cellen)) for cellen in elementen
            ]
        )
    )
    document = SimpleNamespace(export_to_text=lambda: export)
    return SimpleNamespace(pages=[pagina], document=document)


class TestRegelsOpbouwen:
    def test_words_at_the_same_height_become_one_line_from_left_to_right(self) -> None:
        resultaat = _resultaat([_cel("21%", 100, 40, 140, 20), _cel("BTW", 10, 41, 60, 21)])

        assert regels_uit_resultaat(resultaat) == "BTW 21%"

    def test_two_lines_come_out_top_to_bottom_with_a_top_left_origin(self) -> None:
        resultaat = _resultaat([_cel("onder", 10, 100, 60, 80), _cel("boven", 10, 40, 60, 20)])

        assert regels_uit_resultaat(resultaat) == "boven\nonder"

    def test_two_lines_come_out_top_to_bottom_with_a_bottom_left_origin(self) -> None:
        resultaat = _resultaat(
            [
                _cel("onder", 10, 20, 60, 40, "BOTTOMLEFT"),
                _cel("boven", 10, 80, 60, 100, "BOTTOMLEFT"),
            ]
        )

        assert regels_uit_resultaat(resultaat) == "boven\nonder"

    def test_a_little_vertical_jitter_stays_on_the_same_line(self) -> None:
        resultaat = _resultaat([_cel("TOTAAL", 10, 40, 70, 20), _cel("29,30", 90, 46, 150, 26)])

        assert regels_uit_resultaat(resultaat) == "TOTAAL 29,30"

    def test_lines_that_are_one_line_height_apart_stay_separate(self) -> None:
        resultaat = _resultaat([_cel("a", 10, 40, 30, 20), _cel("b", 10, 70, 30, 50)])

        assert regels_uit_resultaat(resultaat) == "a\nb"

    def test_a_slanted_line_stays_one_line_next_to_a_parallel_line(self) -> None:
        """Een scheve foto: de woorden zakken naar rechts, tot meer dan een halve celhoogte.

        Gemeten in de eerste meting: de regel werd gesplitst, waardoor het label (KvK) en het nummer
        op verschillende regels kwamen. Elk woord hoort bij de regel van het woord ervoor.
        """
        resultaat = _resultaat(
            [
                _cel("a1", 10, 50, 40, 30),
                _cel("a2", 60, 58, 90, 38),
                _cel("a3", 110, 66, 140, 46),
                _cel("b1", 10, 80, 40, 60),
                _cel("b2", 60, 88, 90, 68),
                _cel("b3", 110, 96, 140, 76),
            ]
        )

        assert regels_uit_resultaat(resultaat) == "a1 a2 a3\nb1 b2 b3"

    def test_a_cell_that_appears_in_two_elements_is_counted_once(self) -> None:
        gedeeld = _cel("dubbel", 10, 40, 70, 20)

        assert regels_uit_resultaat(_resultaat([gedeeld], [gedeeld])) == "dubbel"

    def test_a_whole_line_cell_from_a_pdf_is_kept_as_it_is(self) -> None:
        resultaat = _resultaat([_cel("Totaal incl. btw: EUR 854,09", 10, 40, 300, 20)])

        assert regels_uit_resultaat(resultaat) == "Totaal incl. btw: EUR 854,09"

    def test_without_any_cell_it_falls_back_to_the_plain_export(self) -> None:
        assert regels_uit_resultaat(_resultaat(export="platte tekst")) == "platte tekst"

    def test_a_blank_cell_adds_no_extra_space(self) -> None:
        resultaat = _resultaat(
            [_cel("a", 10, 40, 30, 20), _cel(" ", 40, 40, 50, 20), _cel("b", 60, 40, 80, 20)]
        )

        assert regels_uit_resultaat(resultaat) == "a b"


def _pagina(*cellen: object) -> object:
    return SimpleNamespace(
        assembled=SimpleNamespace(
            elements=[SimpleNamespace(cluster=SimpleNamespace(cells=list(cellen)))]
        )
    )


class TestMeerPaginasLegeCellenEnGrenzen:
    def test_two_pages_are_not_mixed_even_at_the_same_height(self) -> None:
        resultaat = SimpleNamespace(
            pages=[_pagina(_cel("een", 10, 40, 40, 20)), _pagina(_cel("twee", 60, 40, 90, 20))],
            document=SimpleNamespace(export_to_text=lambda: "export"),
        )

        assert regels_uit_resultaat(resultaat) == "een\ntwee"

    def test_a_line_of_only_blank_cells_gives_no_empty_line(self) -> None:
        resultaat = _resultaat([_cel("a", 10, 40, 30, 20), _cel(" ", 10, 100, 30, 80)])

        assert regels_uit_resultaat(resultaat) == "a"

    def test_a_page_with_too_many_cells_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(lezer_module, "MAX_CELLEN", 5)
        cellen = [_cel(f"w{i}", 10 * i, 40, 10 * i + 8, 20) for i in range(6)]

        with pytest.raises(OngeldigBestand):
            regels_uit_resultaat(_resultaat(cellen))

    def test_a_page_with_exactly_the_maximum_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(lezer_module, "MAX_CELLEN", 5)
        cellen = [_cel(f"w{i}", 10 * i, 40, 10 * i + 8, 20) for i in range(5)]

        assert regels_uit_resultaat(_resultaat(cellen)) == "w0 w1 w2 w3 w4"

    def test_cells_each_on_their_own_line_are_handled_in_reasonable_time(self) -> None:
        import time

        cellen = [_cel("x", 1.0, 1000.0 - 25.0 * i, 3.0, 1000.0 - 25.0 * i - 20.0) for i in range(1500)]
        start = time.perf_counter()

        regels_uit_resultaat(_resultaat(cellen))

        assert time.perf_counter() - start < 2.0
