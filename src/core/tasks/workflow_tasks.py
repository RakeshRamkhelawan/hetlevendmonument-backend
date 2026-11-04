import logging
import typing

from src.core.agents.autonomous_agent import AutonomousAgent
from src.core.middleware.tenant_context import set_tenant_id
from src.core.services.noodstop_toegang import KlantStilgezet, eis_klant_actief
from src.core.shared.interfaces import TaskData
from src.core.tasks.dramatiq_broker import workflow_actor
from src.core.tasks.eigen_loop import SessieFabriek, draai_in_eigen_loop

logger = logging.getLogger(__name__)


@workflow_actor
def execute_workflow_step(
    task_data_dict: dict[str, object],
) -> dict[str, object]:
    """
    Dramatiq actor to execute a workflow step.
    Wraps the async agent call in a synchronous runner.
    """
    _tid_raw = task_data_dict.get("tenant_id")
    if _tid_raw is None:
        raise ValueError(
            f"tenant_id missing in task_data for task "
            f"{task_data_dict.get('task_id', 'unknown')} -- "
            "rejecting to prevent data isolation bypass (ADR-003)"
        )
    if not isinstance(_tid_raw, (int, str)):
        raise TypeError(
            f"tenant_id has unexpected type {type(_tid_raw).__name__} in task "
            f"{task_data_dict.get('task_id', 'unknown')} -- rejecting"
        )
    set_tenant_id(_tid_raw)
    logger.info("Executing workflow step via Dramatiq: %s", task_data_dict.get("task_id"))

    try:
        # Create a fresh agent instance per task (stateless regarding Redis connection pool).
        # Must be inside the try block so that the finally cleanup still runs if
        # construction fails (AUDIT-003).
        agent = AutonomousAgent()
        task = TaskData(**typing.cast(dict[str, typing.Any], task_data_dict))
        resultaat: dict[str, object] = {}

        async def _draai(sessie_fabriek: SessieFabriek) -> None:
            # draai_in_eigen_loop doet asyncio.run() (verse loop) met een poolloze engine per run
            # (zie eigen_loop): de gepoolde db_manager-engine
            # hangt na run 1 aan een gesloten loop. De agent leest zijn contract via deze fabriek.
            agent.session_factory = sessie_fabriek
            # NOODSTOP PER KLANT (ADR-036 OP-03): deze actor is een deur -- hij start een
            # agentstap. Een stilgezette klant krijgt een weigering als uitslag en GEEN
            # Dramatiq-herhaling (de stop is een besluit, geen storing). Is de stand niet te lezen,
            # dan gooien we door: dat is een storing en een latere poging is dan juist goed.
            try:
                await eis_klant_actief(_tid_raw)
            except KlantStilgezet as stop:
                if stop.onbekend:
                    raise
                resultaat.update(
                    {"success": False, "error": stop.bericht, "geweigerd_door": "noodstop"}
                )
                return
            uitslag = await agent.process_task(task)
            resultaat.update(uitslag.model_dump())

        draai_in_eigen_loop(_draai)
        return resultaat
    except Exception as e:
        logger.error("Error executing workflow step: %s", e, exc_info=True)
        raise
    finally:
        # Clear ContextVar so pooled Dramatiq threads do not bleed tenant_id to the next task.
        set_tenant_id(None)
