"""Acceptatie dag 4: in de pakketuitslag heette een gelukte stap "Stap 1" en toonde hij niets over de bonnen.

Oorzaak (gemeten op de uitslag van de draaiende opstelling): een gelukte stap kreeg het `agent_id` niet mee
(de skill zet het niet op zijn resultaat; een overgeslagen of mislukte stap kreeg het wel van het pakket), dus
het scherm kende de naam "Bonnetjes lezen" niet. Nu zet het pakket het `agent_id` van de stap op elk resultaat
dat er geen heeft, en de receiptscanner geeft aantal, totaal en btw per tarief mee in `samenvatting`.

Alleen de receiptscanner geeft een samenvatting vrij: dat zijn bedragen van bevestigde bonnen, geen
persoonsgegevens. Van een andere agent gaat nooit `result_data` mee naar het scherm.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.als.enterprise.packs import DomainPack, DomainPackOrchestrator, WorkflowStep
from src.core.api.v1.agentic.agentic_domain_router import _naar_antwoord
from src.core.shared.interfaces import ExecutionResult

INITIATOR = 42
SAMENVATTING = {"aantal": 2, "totaal": "22.10", "btw": {"9": "0.50", "21": "3.34"}}


async def _draai(resultaat: ExecutionResult) -> ExecutionResult:
    pack = DomainPack(
        pack_id="pack.test",
        name="Test",
        steps=[WorkflowStep(agent_id="receiptscanner", sla_seconds=5)],
    )

    async def _stap(*args: object, **kwargs: object) -> ExecutionResult:
        return resultaat

    with (
        patch.object(DomainPackOrchestrator, "_execute_step", side_effect=_stap),
        patch("src.core.database.database.db_manager"),
    ):
        resultaten = await DomainPackOrchestrator().run_pack(
            pack, tenant_id=1, initiated_by_user_id=INITIATOR
        )
    return resultaten[0]


class TestHetPakketZetHetAgentIdVanDeStap:
    @pytest.mark.asyncio
    async def test_a_successful_step_without_an_agent_id_gets_the_one_of_the_step(self) -> None:
        resultaat = await _draai(ExecutionResult(task_id="t1", success=True))

        assert resultaat.agent_id == "receiptscanner"

    @pytest.mark.asyncio
    async def test_an_agent_id_the_skill_set_itself_is_kept(self) -> None:
        resultaat = await _draai(ExecutionResult(task_id="t1", success=True, agent_id="eigen"))

        assert resultaat.agent_id == "eigen"

    @pytest.mark.asyncio
    async def test_the_result_data_of_the_step_is_not_changed(self) -> None:
        resultaat = await _draai(
            ExecutionResult(task_id="t1", success=True, result_data=dict(SAMENVATTING))
        )

        assert resultaat.result_data == SAMENVATTING


class TestDeSamenvattingInDeUitslag:
    def _stap(self, resultaat: ExecutionResult):  # noqa: ANN202
        return _naar_antwoord("pack.test", [resultaat], sla_breached=False).steps[0]

    def test_the_receiptscanner_gives_count_total_and_vat_per_rate(self) -> None:
        stap = self._stap(
            ExecutionResult(
                task_id="t1",
                success=True,
                agent_id="receiptscanner",
                result_data=dict(SAMENVATTING),
            )
        )

        assert stap.samenvatting == SAMENVATTING

    def test_only_the_three_known_keys_are_released(self) -> None:
        stap = self._stap(
            ExecutionResult(
                task_id="t1",
                success=True,
                agent_id="receiptscanner",
                result_data={**SAMENVATTING, "geheim": "x", "leverancier": "Bakkerij"},
            )
        )

        assert stap.samenvatting is not None and set(stap.samenvatting) == {
            "aantal",
            "totaal",
            "btw",
        }

    def test_another_agent_never_releases_its_result_data(self) -> None:
        """De data heeft de VOLLEDIG geldige vorm: alleen het agent-id mag de reden zijn dat er niets uitgaat."""
        stap = self._stap(
            ExecutionResult(
                task_id="t1",
                success=True,
                agent_id="dunning",
                result_data=dict(SAMENVATTING),
            )
        )

        assert stap.samenvatting is None

    def test_a_failed_receiptscanner_step_releases_nothing(self) -> None:
        stap = self._stap(
            ExecutionResult(
                task_id="error",
                success=False,
                agent_id="receiptscanner",
                result_data=dict(SAMENVATTING),
                error_message="stuk",
            )
        )

        assert stap.samenvatting is None

    def test_a_receiptscanner_without_result_data_has_no_summary(self) -> None:
        stap = self._stap(ExecutionResult(task_id="t1", success=True, agent_id="receiptscanner"))

        assert stap.samenvatting is None

    @pytest.mark.parametrize(
        "kapot",
        [
            {"aantal": "twee"},
            {"aantal": True},
            {"aantal": None},
            {"totaal": 5},
            {"totaal": None},
            {"btw": "veel"},
            {"btw": None},
            {"btw": {"9": 0.5}},
            {"btw": {9: "0.50"}},
        ],
    )
    def test_a_summary_with_one_wrong_part_is_not_released(self, kapot: dict[str, object]) -> None:
        """Elke voorwaarde apart: alleen DIT ene deel is fout, de rest van de vorm klopt."""
        stap = self._stap(
            ExecutionResult(
                task_id="t1",
                success=True,
                agent_id="receiptscanner",
                result_data={**SAMENVATTING, **kapot},
            )
        )

        assert stap.samenvatting is None

    def test_the_step_keeps_its_agent_id_in_the_answer(self) -> None:
        stap = self._stap(
            ExecutionResult(
                task_id="t1",
                success=True,
                agent_id="receiptscanner",
                result_data=dict(SAMENVATTING),
            )
        )

        assert stap.agent_id == "receiptscanner"


BTW = {
    "kwartaal": "2026-Q4",
    "rubriek": "5b",
    "aantal": 3,
    "aantal_controleren": 1,
    "aantal_dubbel": 2,
    "voorbelasting": {"9": "0.50", "21": "3.34", "overig": "0.00"},
    "totaal": "3.84",
}


class TestHetBtwOverzichtInDeUitslag:
    """Stap 2 (vatcompliance) toont kwartaal, voorbelasting per tarief en het aantal bonnen."""

    def _stap(self, resultaat: ExecutionResult):  # noqa: ANN202
        return _naar_antwoord("pack.test", [resultaat], sla_breached=False).steps[0]

    def _vat(self, **uit: object) -> ExecutionResult:
        return ExecutionResult(
            task_id="t1",
            success=True,
            agent_id="vatcompliance",
            result_data={**BTW, **uit},
        )

    def test_the_overview_is_released_for_vatcompliance(self) -> None:
        assert self._stap(self._vat()).samenvatting == BTW

    def test_only_the_known_keys_are_released(self) -> None:
        stap = self._stap(self._vat(geheim="x", leverancier="Bakkerij"))

        assert stap.samenvatting is not None and set(stap.samenvatting) == set(BTW)

    def test_a_failed_vat_step_releases_nothing(self) -> None:
        resultaat = ExecutionResult(
            task_id="t1",
            success=False,
            agent_id="vatcompliance",
            result_data=dict(BTW),
            error_message="stuk",
        )

        assert self._stap(resultaat).samenvatting is None

    def test_another_agent_never_releases_the_overview(self) -> None:
        resultaat = ExecutionResult(
            task_id="t1", success=True, agent_id="dunning", result_data=dict(BTW)
        )

        assert self._stap(resultaat).samenvatting is None

    def test_the_receiptscanner_does_not_release_the_overview_shape(self) -> None:
        resultaat = ExecutionResult(
            task_id="t1", success=True, agent_id="receiptscanner", result_data=dict(BTW)
        )

        assert self._stap(resultaat).samenvatting is None

    def test_vatcompliance_does_not_release_the_receipt_shape(self) -> None:
        resultaat = ExecutionResult(
            task_id="t1", success=True, agent_id="vatcompliance", result_data=dict(SAMENVATTING)
        )

        assert self._stap(resultaat).samenvatting is None

    @pytest.mark.parametrize(
        "kapot",
        [
            {"kwartaal": 2026},
            {"kwartaal": "2026-Q5"},
            {"kwartaal": None},
            {"rubriek": 5},
            {"aantal": "drie"},
            {"aantal": True},
            {"aantal_controleren": "een"},
            {"aantal_controleren": None},
            {"aantal_dubbel": "twee"},
            {"aantal_dubbel": True},
            {"aantal_dubbel": None},
            {"totaal": 3.84},
            {"totaal": None},
            {"voorbelasting": "veel"},
            {"voorbelasting": None},
            {"voorbelasting": {"9": "0.50", "21": "3.34"}},
            {"voorbelasting": {"9": 0.5, "21": "3.34", "overig": "0.00"}},
            {"voorbelasting": {"9": "0.50", "21": "3.34", "overig": "0.00", "extra": "1.00"}},
        ],
    )
    def test_an_overview_with_one_wrong_part_is_not_released(
        self, kapot: dict[str, object]
    ) -> None:
        """Elke voorwaarde apart: alleen DIT ene deel is fout, de rest van de vorm klopt."""
        assert self._stap(self._vat(**kapot)).samenvatting is None
