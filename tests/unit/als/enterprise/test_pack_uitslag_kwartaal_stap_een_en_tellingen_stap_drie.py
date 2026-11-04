"""De uitslag van mkb.zero_admin noemt het kwartaal bij stap 1 en zegt eerlijk wat stap 3 deed (2026-10-19).

Stap 1 (receiptscanner) krijgt het `kwartaal` erbij, naast aantal, totaal en btw. Stap 3 (dunning) geeft alleen twee
TELLINGEN vrij: `openstaand` (None als onbekend) en `voorgesteld`, plus `openstaand_afgekapt` als de lijst is afgekapt.
De tekst die het model schreef en alles wat op een persoon lijkt gaat nooit mee naar het scherm.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import pytest

from src.core.api.v1.agentic.agentic_domain_router import _naar_antwoord
from src.core.shared.interfaces import ExecutionResult

BONNEN = {"kwartaal": "2026-Q3", "aantal": 2, "totaal": "22.10", "btw": {"9": "0.50", "21": "3.34"}}
DUNNING = {"openstaand": 3, "voorgesteld": 1}


def _stap(agent_id: str, data: dict[str, object] | None, success: bool = True):  # noqa: ANN202
    resultaat = ExecutionResult(task_id="t1", success=success, agent_id=agent_id, result_data=data)
    return _naar_antwoord("pack.test", [resultaat], sla_breached=False).steps[0]


class TestStapEenNoemtHetKwartaal:
    def test_the_quarter_is_released_with_the_other_parts(self) -> None:
        assert _stap("receiptscanner", dict(BONNEN)).samenvatting == BONNEN

    def test_without_a_quarter_the_old_shape_still_works(self) -> None:
        oud = {k: v for k, v in BONNEN.items() if k != "kwartaal"}

        assert _stap("receiptscanner", dict(oud)).samenvatting == oud

    @pytest.mark.parametrize("kapot", [2026, "2026-Q5", "derde kwartaal", None, ""])
    def test_a_wrong_quarter_blocks_the_whole_summary(self, kapot: object) -> None:
        assert _stap("receiptscanner", {**BONNEN, "kwartaal": kapot}).samenvatting is None

    def test_other_keys_are_still_not_released(self) -> None:
        stap = _stap("receiptscanner", {**BONNEN, "leverancier": "Bakkerij"})

        assert stap.samenvatting is not None and "leverancier" not in stap.samenvatting


class TestStapDrieZegtWatHijDeed:
    def test_the_two_counts_are_released(self) -> None:
        assert _stap("dunning", dict(DUNNING)).samenvatting == DUNNING

    def test_an_unknown_count_is_released_as_unknown(self) -> None:
        stap = _stap("dunning", {"openstaand": None, "voorgesteld": 0})

        assert stap.samenvatting == {"openstaand": None, "voorgesteld": 0}

    def test_a_truncated_list_is_released(self) -> None:
        stap = _stap("dunning", {**DUNNING, "openstaand_afgekapt": True})

        assert stap.samenvatting == {**DUNNING, "openstaand_afgekapt": True}

    def test_the_model_text_and_other_keys_never_go_to_the_screen(self) -> None:
        stap = _stap(
            "dunning",
            {
                **DUNNING,
                "output": "Beste meneer Jansen ...",
                "errors": [{"error": "x"}],
                "results": [],
            },
        )

        assert stap.samenvatting == DUNNING

    def test_a_failed_step_releases_nothing(self) -> None:
        assert _stap("dunning", dict(DUNNING), success=False).samenvatting is None

    def test_a_result_without_the_counts_releases_nothing(self) -> None:
        assert _stap("dunning", {"output": "klaar", "tool_calls": 0}).samenvatting is None

    @pytest.mark.parametrize(
        "kapot",
        [
            {"openstaand": "drie"},
            {"openstaand": True},
            {"openstaand": -1},
            {"voorgesteld": "een"},
            {"voorgesteld": None},
            {"voorgesteld": True},
            {"voorgesteld": -1},
            {"openstaand_afgekapt": "ja"},
        ],
    )
    def test_one_wrong_part_blocks_the_summary(self, kapot: dict[str, object]) -> None:
        assert _stap("dunning", {**DUNNING, **kapot}).samenvatting is None

    def test_another_agent_does_not_release_the_counts_shape(self) -> None:
        assert _stap("vatcompliance", dict(DUNNING)).samenvatting is None
