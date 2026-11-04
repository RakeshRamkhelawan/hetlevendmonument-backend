import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.exceptions import AuthError
from src.core.shared.interfaces import ExecutionResult, ExecutionStatusContract, TaskData
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

# AUDIT-009 / ADR-036 D10: only the pilot skill has real execution wiring.
# Every other catalog agent fails explicitly in _execute_step -- no second
# silent placeholder. Skills get wired here when their execution path is
# built and reviewed (same pattern as the tool-permission profiles, ADR-015).
# Debiteurenagent dag 2 (2026-10-05): `dunning` erbij, met eigen manifest-pad en profiel.
# Bonlezer dag 4 (2026-10-17): `receiptscanner` erbij; samenvatting van bevestigde bonnen, geen taalmodel.
# Btw-overzicht (2026-10-19): `vatcompliance` erbij; het btw-overzicht per kwartaal uit bevestigde bonnen.
# Crediteuren dag 2 (2026-10-24): `crediteuren` erbij; de agent verwerkt een gelezen inkoopfactuur (geen taalmodel).
_PILOT_WIRED_AGENT_IDS = frozenset(
    {"skillsgaptraining", "dunning", "receiptscanner", "vatcompliance", "crediteuren"}
)


#: De agents die een WORKFLOWSTAP kan uitvoeren (agentstap dag 1, 2026-10-24): dezelfde bedrade vier als hierboven.
#: Een eigen naam zodat `workflow_stap.py` geen privenaam importeert; de lijst zelf heeft een enkele bron.
UITVOERBARE_AGENT_SLEUTELS = _PILOT_WIRED_AGENT_IDS


class _ManifestPromptSkill(Protocol):
    """Wat een gewired pilot-skill moet kunnen.

    `get_agent_instance()` levert een BaseSpecialistAgent; die kent
    `execute_with_manifest_prompt` niet -- alleen de pilot-skill implementeert dat
    (K1 optie A, zie _execute_step). De `_PILOT_WIRED_AGENT_IDS`-guard hierboven is wat
    garandeert dat we deze methode alleen aanroepen op een skill die hem heeft; deze
    Protocol maakt dat contract expliciet in plaats van het op `Any` te laten rusten.
    """

    async def execute_with_manifest_prompt(
        self,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type -- spiegelt de concrete signatuur
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult: ...


class PackExecutionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"
    RUNNING = "in_progress"
    COMPLETED = "succeeded"
    TIMEOUT = "failed"


class PackTask(BaseModel):
    """Legacy task model used by older domain pack tests."""

    agent_id: str
    tenant_id: str | None = None
    params: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class WorkflowStep(BaseModel):
    """A single step in a Domain Pack workflow."""

    agent_id: str
    mode: Literal["sequential", "parallel"] = "sequential"
    sla_seconds: float = 30.0
    params: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class DomainPack(BaseModel):
    """Definition of a bundled agent solution."""

    model_config = ConfigDict(populate_by_name=True)

    pack_id: str
    name: str
    steps: list[WorkflowStep] = Field(default_factory=list)
    description: str | None = None
    supervisor_ids: list[str] = Field(default_factory=list)
    agent_sequence: list[dict[str, Any]] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=list
    )  # TODO(TYPE): replace Any with concrete type
    sla_minutes: int = Field(default=60, ge=0)
    estimated_value_eur: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_payload(
        cls, data: Any  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "pack_id" not in normalized and "id" in normalized:
            normalized["pack_id"] = normalized["id"]

        if "steps" not in normalized and "agent_sequence" in normalized:
            steps: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
            for item in normalized.get("agent_sequence", []):
                agents = item.get("agents", [])
                mode = item.get("type", "sequential")
                for agent_id in agents:
                    steps.append(
                        {
                            "agent_id": agent_id,
                            "mode": "parallel" if mode == "parallel" else "sequential",
                            "sla_seconds": normalized.get("sla_minutes", 60) * 60,
                            "params": {},
                        }
                    )
            normalized["steps"] = steps

        return normalized

    @property
    def id(self) -> str:
        return self.pack_id


@dataclass
class Voortgang:
    """Wat een lopende `run_pack` al gedaan heeft, per stap-index in `pack.steps`.

    `gestart`: de stap is begonnen. `klaar`: de stap heeft een resultaat (gelukt of mislukt).
    Een stap in `gestart` maar niet in `klaar` is onderbroken als de run van buiten wordt
    afgebroken (de SLA van de hele run) en kan al effect hebben gehad. Wordt gevuld TERWIJL de
    run loopt, per stap en niet per blok, en voordat het ROI-logboek van die stap loopt.
    """

    klaar: dict[int, ExecutionResult] = field(default_factory=dict)
    gestart: set[int] = field(default_factory=set)


class DomainPackOrchestrator:
    """
    Orchestrates execution of Domain Packs across multiple agents.
    Uses the central EnterpriseCatalogLoader for pack discovery.
    """

    def __init__(self) -> None:
        from src.core.als.agents.loader import EnterpriseCatalogLoader

        self.catalog = EnterpriseCatalogLoader().load_all()

    async def execute_pack(
        self,
        pack: DomainPack,
        tenant_id: str | None,
        *,
        initiated_by_user_id: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Backward-compatible pack execution API used by enterprise tests."""
        if not tenant_id:
            raise AuthError("Tenant ID is required")

        started = time.perf_counter()
        try:
            results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
            for phase in pack.agent_sequence:
                agents = phase.get("agents", [])
                if phase.get("type") == "parallel":
                    phase_results = await self._execute_parallel(
                        agents, tenant_id, initiated_by_user_id=initiated_by_user_id
                    )
                else:
                    phase_results = await self._execute_sequential(
                        agents, tenant_id, initiated_by_user_id=initiated_by_user_id
                    )
                results.extend(phase_results)

            success_count = sum(1 for result in results if result.get("status") == "success")
            failure_count = len(results) - success_count

            status = PackExecutionStatus.SUCCEEDED
            escalated_to_human = False
            if failure_count and success_count:
                status = PackExecutionStatus.PARTIAL
            elif failure_count and not success_count:
                status = PackExecutionStatus.FAILED
                escalated_to_human = True

            return {
                "status": status,
                "pack_id": pack.id,
                "tenant_id": tenant_id,
                "execution_time_ms": int((time.perf_counter() - started) * 1000),
                "success_count": success_count,
                "failure_count": failure_count,
                "sla_breached": False,
                "escalated_to_human": escalated_to_human,
                "results": results,
            }
        except TimeoutError:
            return {
                "status": PackExecutionStatus.FAILED,
                "pack_id": pack.id,
                "tenant_id": tenant_id,
                "execution_time_ms": int((time.perf_counter() - started) * 1000),
                "success_count": 0,
                "failure_count": 0,
                "sla_breached": True,
                "escalated_to_human": False,
                "results": [],
            }

    async def _execute_parallel(
        self, agents: list[str], tenant_id: str, *, initiated_by_user_id: int | None = None
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        tasks = [
            self._execute_with_retry(agent_id, tenant_id, initiated_by_user_id=initiated_by_user_id)
            for agent_id in agents
        ]
        return list(await asyncio.gather(*tasks))

    async def _execute_sequential(
        self, agents: list[str], tenant_id: str, *, initiated_by_user_id: int | None = None
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id in agents:
            results.append(
                await self._execute_with_retry(
                    agent_id, tenant_id, initiated_by_user_id=initiated_by_user_id
                )
            )
        return results

    async def _execute_with_retry(
        self,
        agent_id: str,
        tenant_id: str,
        retries: int = 1,
        *,
        initiated_by_user_id: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        last_result: dict[str, Any] = {
            "status": "error",
            "error": "Execution failed",
        }  # TODO(TYPE): replace Any with concrete type
        for _ in range(retries + 1):
            result = await self._execute_single_agent(
                agent_id, tenant_id, initiated_by_user_id=initiated_by_user_id
            )
            if result.get("status") == "success":
                return result
            last_result = result
        return last_result

    async def _execute_single_agent(
        self, agent_id: str, tenant_id: str, *, initiated_by_user_id: int | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        # ADR-005 pre-existing fix (AUDIT-009): no silent tenant_id=0 fallback.
        # A non-numeric tenant string is an explicit error, never tenant 0.
        if not tenant_id.isdigit():
            return {
                "status": "error",
                "agent_id": agent_id,
                "error": (
                    f"Invalid tenant_id '{tenant_id}': must be numeric "
                    "(no silent tenant 0 fallback, ADR-005)"
                ),
            }
        result = await self._execute_step(
            agent_id, int(tenant_id), {}, initiated_by_user_id=initiated_by_user_id
        )
        if result.success:
            return {"status": "success", "agent_id": agent_id, "task_id": result.task_id}
        return {"status": "error", "agent_id": agent_id, "error": result.error_message}

    def get_pack(self, pack_id: str) -> DomainPack | None:
        """Het pack uit de catalogus, of `None`. De route toetst hiermee op 404 (OP-09)."""
        return cast("DomainPack | None", self.catalog.packs.get(pack_id))

    async def run_pack_by_id(
        self,
        pack_id: str,
        tenant_id: int,
        *,
        initiated_by_user_id: int | None = None,
        input_data: dict[str, object] | None = None,
        voortgang: Voortgang | None = None,
    ) -> list[ExecutionResult]:
        """Runs a pack based on its catalog ID."""
        pack: Any | None = self.catalog.packs.get(  # TODO(TYPE): replace Any with concrete type
            pack_id
        )  # TODO(TYPE): replace Any with concrete type
        if pack is None:
            logger.error(f"Pack ID {pack_id} not found in catalog.")
            return [
                ExecutionResult(
                    task_id="error",
                    success=False,
                    error_message=f"Pack {pack_id} not found",
                    tenant_id=tenant_id,
                    status=ExecutionStatusContract.MISLUKT,
                )
            ]

        return await self.run_pack(
            cast(DomainPack, pack),
            tenant_id,
            initiated_by_user_id=initiated_by_user_id,
            input_data=input_data,
            voortgang=voortgang,
        )

    @staticmethod
    def skipped_result(step: WorkflowStep, tenant_id: int, reason: str) -> ExecutionResult:
        """Resultaat voor een stap die NIET (volledig) is uitgevoerd: `task_id` is `skipped`."""
        return ExecutionResult(
            task_id="skipped",
            success=False,
            error_message=reason,
            tenant_id=tenant_id,
            agent_id=step.agent_id,
        )

    @staticmethod
    def interrupted_result(step: WorkflowStep, tenant_id: int, reason: str) -> ExecutionResult:
        """Resultaat voor een stap die BEGONNEN was maar niet klaar: `task_id` is `interrupted`."""
        return ExecutionResult(
            task_id="interrupted",
            success=False,
            error_message=reason,
            tenant_id=tenant_id,
            agent_id=step.agent_id,
        )

    async def run_pack(
        self,
        pack: DomainPack,
        tenant_id: int,
        *,
        initiated_by_user_id: int | None = None,
        input_data: dict[str, object] | None = None,
        voortgang: Voortgang | None = None,
    ) -> list[ExecutionResult]:
        """
        Runs the specified domain pack for a tenant.

        `input_data` is de invoer van de gebruiker (OP-09). Elke stap krijgt als params
        `{**step.params, "input": input_data}`; zonder invoer blijft het precies `step.params`.

        Faalt een SEQUENTIELE stap, dan draaien de volgende stappen niet: die staan als
        `skipped` in het resultaat, met de reden (besluit regie 2026-10-10: een vervolgstap op
        basis van een mislukte stap is fout werk dat een klant moet terugdraaien). Een falende
        PARALLELLE stap breekt niet af; die stappen zijn los van elkaar.

        `voortgang` wordt gevuld TERWIJL de run loopt (zie `Voortgang`). Wordt de run van buiten
        afgebroken (de SLA van de hele run), dan weet de aanroeper zo per stap wat er klaar was,
        wat liep en wat nooit begon.
        """
        logger.info(f"Starting Domain Pack: {pack.name} (tenant {tenant_id})")

        voortgang = voortgang if voortgang is not None else Voortgang()
        all_results: list[ExecutionResult] = []

        async def uitvoeren(index: int, step: WorkflowStep) -> ExecutionResult:
            voortgang.gestart.add(index)

            def melden(resultaat: ExecutionResult) -> None:
                voortgang.klaar[index] = resultaat

            return await self._run_single_step(
                step,
                tenant_id,
                pack.pack_id,
                initiated_by_user_id=initiated_by_user_id,
                input_data=input_data,
                melden=melden,
            )

        async def parallel_blok(blok: list[tuple[int, WorkflowStep]]) -> list[ExecutionResult]:
            return list(await asyncio.gather(*(uitvoeren(i, st) for i, st in blok)))

        current_parallel_batch: list[tuple[int, WorkflowStep]] = []

        for index, step in enumerate(pack.steps):
            if step.mode == "sequential":
                # Execute any pending parallel batch first
                if current_parallel_batch:
                    all_results.extend(await parallel_blok(current_parallel_batch))
                    current_parallel_batch = []
                # Execute sequential step
                res = await uitvoeren(index, step)
                all_results.append(res)
                if not res.success:
                    # Het volgnummer, niet `step.agent_id`: een klant herkent `dunning` niet als stap
                    # van zijn pakket. De agent staat in het logboek hieronder.
                    reden = f"Overgeslagen: stap {index + 1} is mislukt"
                    all_results.extend(
                        self.skipped_result(rest, tenant_id, reden)
                        for rest in pack.steps[index + 1 :]
                    )
                    logger.warning(
                        "Domain Pack %s afgebroken na mislukte stap %s",
                        pack.pack_id,
                        step.agent_id,
                    )
                    return all_results
            else:
                # Add to parallel batch
                current_parallel_batch.append((index, step))

        # Run final parallel batch if exists
        if current_parallel_batch:
            all_results.extend(await parallel_blok(current_parallel_batch))

        logger.info(f"Domain Pack {pack.pack_id} completed with {len(all_results)} results.")
        return all_results

    async def _run_single_step(
        self,
        step: WorkflowStep,
        tenant_id: int,
        pack_id: str,
        *,
        initiated_by_user_id: int | None = None,
        input_data: dict[str, object] | None = None,
        melden: Callable[[ExecutionResult], None] | None = None,
    ) -> ExecutionResult:
        """Runs a single agent step with SLA monitoring and ROI logging.

        `melden` krijgt het resultaat zodra de stap klaar is, VOOR het ROI-logboek: een trage
        meting mag een gelukte stap niet 'onderbroken' laten lijken (zie `Voortgang`).
        """
        start_time = asyncio.get_event_loop().time()
        gestart_op = datetime.now(timezone.utc)
        # Een NIEUW dict: `step.params` is de YAML-definitie en blijft ongewijzigd (OP-09).
        params = step.params if input_data is None else {**step.params, "input": input_data}
        try:
            # Wrap execution in a timeout
            res = await asyncio.wait_for(
                self._execute_step(
                    step.agent_id,
                    tenant_id,
                    params,
                    initiated_by_user_id=initiated_by_user_id,
                ),
                timeout=step.sla_seconds,
            )
            if not res.agent_id:
                # Een skill zet het agent-id niet op zijn resultaat; zonder dat kent het scherm de stap alleen
                # als "Stap 1" (acceptatie bonlezer dag 4). Een overgeslagen of mislukte stap kreeg het al.
                res = res.model_copy(update={"agent_id": step.agent_id})

            if melden is not None:
                melden(res)
            # Een meting, geen onderdeel van het werk: faalt het logboek, dan blijft de stap gelukt
            # (de schrijver staat in `best_effort`). Ook een mislukte of afgebroken stap wordt
            # vastgelegd, met zijn status: alleen een geslaagde run telt later als besparing, maar
            # het aantal pogingen en mislukkingen hoort bij een eerlijk beeld (ADR-036 OP-09-nazorg).
            await self._leg_run_vast(
                tenant_id=tenant_id,
                pack_id=pack_id,
                agent_id=step.agent_id,
                task_id=res.task_id,
                status=(res.status or (
                    ExecutionStatusContract.KLAAR if res.success else ExecutionStatusContract.MISLUKT
                )).value,
                gestart_op=gestart_op,
            )
            return res
        except TimeoutError:
            logger.error(f"SLA Timeout exceeded for agent {step.agent_id}")
            timeout_resultaat = ExecutionResult(
                task_id="timeout",
                success=False,
                error_message=f"SLA Timeout: {step.agent_id} took longer than {step.sla_seconds}s",
                tenant_id=tenant_id,
                agent_id=step.agent_id,
                status=ExecutionStatusContract.MISLUKT,
            )
            if melden is not None:
                melden(timeout_resultaat)
            await self._leg_run_vast(
                tenant_id=tenant_id,
                pack_id=pack_id,
                agent_id=step.agent_id,
                task_id=timeout_resultaat.task_id,
                status=ExecutionStatusContract.MISLUKT.value,
                gestart_op=gestart_op,
            )
            return timeout_resultaat
        except Exception as e:
            logger.error(f"Error executing pack step {step.agent_id}: {e}")
            fout_resultaat = ExecutionResult(
                task_id="error",
                success=False,
                error_message=str(e),
                tenant_id=tenant_id,
                agent_id=step.agent_id,
                status=ExecutionStatusContract.MISLUKT,
            )
            if melden is not None:
                melden(fout_resultaat)
            await self._leg_run_vast(
                tenant_id=tenant_id,
                pack_id=pack_id,
                agent_id=step.agent_id,
                task_id=fout_resultaat.task_id,
                status=ExecutionStatusContract.MISLUKT.value,
                gestart_op=gestart_op,
            )
            return fout_resultaat

    async def _leg_run_vast(
        self,
        *,
        tenant_id: int,
        pack_id: str,
        agent_id: str,
        task_id: str,
        status: str,
        gestart_op: datetime,
    ) -> None:
        """Leg een run vast in `agent_run_metrics` (ROI, gemeten laag). Faalt dit: de stap blijft.

        Geen medewerker, geen eigen `commit()` op de sessie van de stap: dit opent een EIGEN
        sessie, en een trage of kapotte meting mag een gelukte stap niet onderbreken (`best_effort`).
        `items_processed` en de LLM-kosten worden hier niet gemeten (NULL); een telling die niemand
        heeft gedaan is geen nul.
        """
        from src.core.analytics.roi_service import ROIService
        from src.core.database.database import db_manager

        async with best_effort(f"pack run metrics {pack_id}/{agent_id}"):
            async with db_manager.get_session() as db:
                # `record_run` neemt zelf de tenant aan rond de INSERT (zie daar waarom).
                await ROIService(db).record_run(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    pack_id=pack_id,
                    task_id=task_id,
                    status=status,
                    started_at=gestart_op,
                    finished_at=datetime.now(timezone.utc),
                )
                await db.commit()

    async def _execute_step(
        self,
        agent_id: str,
        tenant_id: int,
        params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult:
        """Resolve and really execute an agent step (AUDIT-009).

        Replaces the old ``asyncio.sleep(0.01)`` + always-success placeholder.
        Scope (ADR-036 D10 pilot harness): the mechanism is generic, but only
        the pilot skill is wired for real execution. Unknown agents and
        catalog agents without wiring fail EXPLICITLY -- never a silent
        success, because silent success here was exactly the AUDIT-009 sin.

        K1 option A (day-5 brief): the pilot executes via its own
        manifest-prompt path (``execute_with_manifest_prompt``) so the LLM
        sees the manifest system_prompt with the TOOL_CALL contract, WITHOUT
        touching BaseSpecialistAgent.orient() for all 135 skills (that global
        change is an architecture decision, escalated to Rakesh).
        """
        if agent_id not in self.catalog.agents:
            return ExecutionResult(
                task_id="unknown-agent",
                success=False,
                error_message=f"Agent '{agent_id}' not found in the enterprise catalog",
                tenant_id=tenant_id,
                agent_id=agent_id,
                status=ExecutionStatusContract.MISLUKT,
            )
        if agent_id not in _PILOT_WIRED_AGENT_IDS:
            return ExecutionResult(
                task_id="unwired-agent",
                success=False,
                error_message=(
                    f"Agent '{agent_id}' exists in the catalog but has no real execution "
                    f"wiring yet -- only the ADR-036 D10 pilot "
                    f"({sorted(_PILOT_WIRED_AGENT_IDS)}) is connected"
                ),
                tenant_id=tenant_id,
                agent_id=agent_id,
                status=ExecutionStatusContract.MISLUKT,
            )
        try:
            # cast is veilig door de _PILOT_WIRED_AGENT_IDS-guard hierboven: we zijn hier
            # alleen voor skills waarvan is vastgesteld dat ze het manifest-prompt-pad
            # implementeren. Zonder cast valt dit terug op Any en verdwijnt elke controle
            # op de aanroep en op het retourtype.
            skill = cast(_ManifestPromptSkill, self.catalog.get_agent_instance(agent_id, tenant_id))
            return await skill.execute_with_manifest_prompt(
                params, initiated_by_user_id=initiated_by_user_id
            )
        except Exception as exc:  # explicit failure, never silent success
            logger.error(
                "Execution of agent %s failed for tenant %s: %s: %s",
                agent_id,
                tenant_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return ExecutionResult(
                task_id="error",
                success=False,
                error_message=str(exc),
                tenant_id=tenant_id,
                agent_id=agent_id,
                status=ExecutionStatusContract.MISLUKT,
            )
