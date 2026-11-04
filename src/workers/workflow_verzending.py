"""Een workflowtaak naar de werker sturen -- en een zichtbare fout als dat niet lukt (ADR-036 OP-13).

Brief 2026-10-20 (ActivePieces per klant, dag 1), besluit 5.

**Waarom dit een eigen functie is.** `src/workers/workflow_worker.py` zet bij het importeren een
`StubBroker`; de echte `RedisBroker` komt pas na `get_redis_broker()`, en dat roept alleen het
werkerproces aan. De API stuurde dus met `execute_workflow_task.send(...)` naar een geheugenwachtrij
die niemand uitleest, en gaf `202 pending` voor een uitvoering die nooit zou starten. Faalde het
versturen wel, dan werd dat alleen gelogd en kreeg de klant alsnog `202`.

Hier: eerst de echte broker binden, dan versturen. Lukt dat niet, dan:

1. staat er een regel in de dead letter queue (zichtbaar, en later opnieuw te proberen),
2. staat de uitvoering op FAILED met een reden, en
3. krijgt de aanroeper een Nederlandse fout (503) in plaats van een 202.

De broker zelf blijft bij het importeren gezet; dat losmaken raakt elf bestanden die hun actors
impliciet aan die broker hangen en is een eigen traject (zie het register, OP-13).
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions.exceptions import SanskritiError
from src.core.utils.best_effort import best_effort
from src.core.workflow.dead_letter_queue import DeadLetterQueue
from src.core.workflow.models import WorkflowStatus

if TYPE_CHECKING:
    from src.core.workflow.models import C7WorkflowExecution

logger = logging.getLogger(__name__)


class _Verstuurbaar(Protocol):
    """Een dramatiq-actor; de decorator geeft hem een `send` die mypy niet ziet."""

    def send(self, execution_id: str, tenant_id: int | None = None) -> object: ...


class WorkflowTaakNietVerstuurdError(SanskritiError):
    """503 -- de workflowtaak kon niet naar de werker en is dus niet gestart."""

    def __init__(self, execution_id: str) -> None:
        super().__init__(
            message=(
                "De workflow is niet gestart: de opdracht kon niet naar de werker. "
                "Probeer het over enkele minuten opnieuw."
            ),
            error_code="WORKFLOW_TAAK_NIET_VERSTUURD",
            status_code=503,
            details={"execution_id": execution_id},
        )


async def verstuur_workflow_taak(db: AsyncSession, uitvoering: C7WorkflowExecution) -> None:
    """Stuur de uitvoering naar de werker, of laat zichtbaar mislukken.

    De klant gaat MEE met de opdracht (ADR-036 OP-153): de werker draait buiten elk verzoek en kan
    de klant daarna niet meer uit het uitvoeringsrecord lezen. Dit is geen tenant uit invoer:
    `uitvoering.tenant_id` komt uit het token via de middleware, en de werker controleert de
    waarde tegen de database voordat hij iets doet.
    """
    from src.workers import workflow_worker

    try:
        workflow_worker.get_redis_broker()
        cast(_Verstuurbaar, workflow_worker.execute_workflow_task).send(
            uitvoering.execution_id, uitvoering.tenant_id
        )
    except Exception as e:  # noqa: BLE001 -- elke oorzaak wordt hieronder een zichtbare fout
        logger.error(
            "workflow_taak_niet_verstuurd: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"execution_id": uitvoering.execution_id, "tenant_id": uitvoering.tenant_id},
        )
        reden = f"De opdracht kon niet naar de werker: {type(e).__name__}."
        async with best_effort("workflow-taak naar de dead letter queue", db_session=db):
            await DeadLetterQueue(db).enqueue(
                original_task_id=uitvoering.execution_id,
                execution_id=uitvoering.execution_id,
                tenant_id=uitvoering.tenant_id,
                workflow_id=uitvoering.workflow_id,
                error_message=reden,
                stack_trace=traceback.format_exc(),
                error_type=type(e).__name__,
                max_retries=0,
            )
        # Na de dead-letter-poging: een rollback daarin zou deze wijziging anders weer ongedaan
        # maken.
        uitvoering.status = WorkflowStatus.FAILED
        uitvoering.error_message = reden
        uitvoering.finished_at = datetime.now(timezone.utc)
        await db.commit()
        raise WorkflowTaakNietVerstuurdError(uitvoering.execution_id) from e

    logger.info(
        "Workflow execution enqueued",
        extra={"execution_id": uitvoering.execution_id, "tenant_id": uitvoering.tenant_id},
    )
