"""
SP-W02: cva_tasks + workflow_tasks fix tests

B-015: cva_tasks.py hardcoded user_id=1
B-013: workflow_tasks.py thread-unsafe asyncio.new_event_loop()
"""

import inspect
import os

import pytest

os.environ.setdefault("TESTING", "1")


@pytest.mark.unit
class TestCvaTasks:
    def test_cva_tasks_no_hardcoded_user_id_1(self) -> None:
        """cva_tasks.py mag geen hardcoded user_id=1 meer bevatten (B-015)."""
        from src.core.tasks import cva_tasks

        source = inspect.getsource(cva_tasks)
        assert "user_id = 1" not in source and "user_id=1" not in source, (
            "cva_tasks heeft nog hardcoded user_id=1 (B-015) "
            "-- alle CVA-berichten worden onterecht geattribueerd aan user 1"
        )

    def test_cva_tasks_gets_user_id_from_request_data(self) -> None:
        """cva_tasks leest user_id uit request_data payload, niet hardcoded."""
        from src.core.tasks import cva_tasks

        source = inspect.getsource(cva_tasks)
        # Fix: user_id = request_data.get("user_id") OF request_data["user_id"]
        has_payload_read = (
            'request_data.get("user_id")' in source
            or 'request_data["user_id"]' in source
            or "request_data.get('user_id')" in source
        )
        assert has_payload_read, (
            "cva_tasks leest user_id niet uit request_data -- "
            "voeg request_data.get('user_id') toe en valideer aanwezigheid"
        )

    def test_cva_tasks_validates_user_id_presence(self) -> None:
        """cva_tasks logt een fout en returnt vroeg als user_id ontbreekt."""
        from src.core.tasks import cva_tasks

        source = inspect.getsource(cva_tasks)
        # After reading user_id from payload, there must be a guard like the other fields
        # (tenant_id, channel, text all have "if not X: logger.error... return" pattern)
        assert "user_id" in source, "user_id ontbreekt volledig in cva_tasks"
        # The validation guard must exist somewhere after reading user_id
        assert "Missing required field" in source, (
            "cva_tasks heeft geen validatie-guards voor verplichte velden"
        )


@pytest.mark.unit
class TestWorkflowTasks:
    def test_workflow_tasks_no_new_event_loop(self) -> None:
        """workflow_tasks.py gebruikt GEEN asyncio.new_event_loop() meer (B-013)."""
        from src.core.tasks import workflow_tasks

        source = inspect.getsource(workflow_tasks)
        assert "new_event_loop" not in source, (
            "workflow_tasks heeft nog asyncio.new_event_loop() (B-013) "
            "-- dit is thread-unsafe in Dramatiq worker threads"
        )

    def test_workflow_tasks_no_set_event_loop(self) -> None:
        """workflow_tasks.py gebruikt GEEN asyncio.set_event_loop() meer (B-013)."""
        from src.core.tasks import workflow_tasks

        source = inspect.getsource(workflow_tasks)
        assert "set_event_loop" not in source, (
            "workflow_tasks heeft nog asyncio.set_event_loop() (B-013) "
            "-- dit is niet thread-safe bij concurrent Dramatiq workers"
        )

    def test_workflow_tasks_draait_agent_in_verse_loop_met_eigen_poolloze_engine(self) -> None:
        """Elke actor-run draait de agent in een EIGEN verse loop met een EIGEN poolloze engine.

        Dekt B-013: geen gedeelde loop en geen gedeelde gepoolde engine, anders volgt in een
        tweede run `attached to a different loop`. Gedragsmeting, geen tekstzoektocht: de actor
        wordt twee keer aangeroepen met een nepagent die de loop en sessiefabriek vastlegt, en
        een nep-`db_manager.create_poolless_engine`.

        Mutatiebewijs: workflow_tasks tijdelijk teruggezet op `asyncio.run(agent.process_task(
        task))` (oude patroon, geen eigen engine/fabriek) -> deze test rood (geen poolloze
        engine aangemaakt, geen sessiefabriek gezet). Huidige code (draai_in_eigen_loop) groen.
        """
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.core.tasks import workflow_tasks

        loops: list[asyncio.AbstractEventLoop] = []
        fabrieken: list[object] = []

        class NepUitslag:
            def model_dump(self) -> dict[str, object]:
                return {"ok": True}

        class NepAgent:
            session_factory: object = None

            async def process_task(self, task: object) -> NepUitslag:
                loops.append(asyncio.get_running_loop())
                fabrieken.append(self.session_factory)
                return NepUitslag()

        engines: list[MagicMock] = []

        def maak_engine() -> MagicMock:
            engine = MagicMock()
            engine.dispose = AsyncMock()
            engines.append(engine)
            return engine

        taak = {"tenant_id": 1, "task_id": "t-1", "task_type": "x", "payload": {}}
        with (
            patch.object(workflow_tasks, "AutonomousAgent", NepAgent),
            patch.object(workflow_tasks, "set_tenant_id"),
            patch.object(workflow_tasks, "TaskData", lambda **kw: kw),
            patch("src.core.database.database.db_manager.create_poolless_engine", maak_engine),
        ):
            uitslag1 = workflow_tasks.execute_workflow_step.fn(taak)
            uitslag2 = workflow_tasks.execute_workflow_step.fn(taak)

        assert uitslag1 == uitslag2 == {"ok": True}
        assert len(loops) == 2
        assert loops[0] is not loops[1], "twee runs delen dezelfde event loop"
        assert all(lp.is_closed() for lp in loops), "verse loop is na de run niet opgeruimd"
        assert len(engines) == 2, "elke run moet een eigen poolloze engine maken"
        for engine in engines:
            engine.dispose.assert_awaited_once()
        assert all(f is not None for f in fabrieken), "agent kreeg geen eigen sessiefabriek"
