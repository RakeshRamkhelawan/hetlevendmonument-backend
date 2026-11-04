import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.als.agents.skill_manifest import SkillManifest
from src.core.als.agents.specialist_base import BaseSpecialistAgent
from src.core.als.bonlezer.btw_overzicht import BtwOverzicht, kwartaal_uit_pakketinvoer
from src.core.als.bonlezer.opruimen import upload_map
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)


class VATComplianceSkill(BaseSpecialistAgent):
    """
    VATCompliance worker agent.

    Loaded from ``manifests/vatcompliance.yml``; behavior is driven by the manifest
    and executed through the shared BaseSpecialistAgent OODA loop.
    """

    def __init__(self, tenant_id: int, **kwargs: Any) -> None:
        manifest = SkillManifest.load(Path(__file__).parent / "manifests/vatcompliance.yml")
        config = manifest.to_config()
        # Merge any runtime overrides passed by the caller
        config.update(kwargs)
        super().__init__(config=config, tenant_id=tenant_id)

    async def act(self, decision: str) -> ExecutionResult:
        """Execute using the shared OODA/tool runtime instead of a hardcoded stub."""
        logger.info(f"[{self.agent_id}] Executing via shared runtime for tenant {self.tenant_id}")
        return await super().act(decision)

    async def execute_with_manifest_prompt(
        self,
        params: dict[str, object],
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult:
        """Het pad dat `packs.py::_execute_step` aanroept: het btw-overzicht uit BEVESTIGDE bonnen.

        Geen taalmodel, geen indiening, geen advies: de voorbelasting (rubriek 5b) per tarief van een kwartaal,
        het aantal bonnen en het aantal dat gecontroleerd moet worden. Het kwartaal is het `kwartaal` in de invoer
        van de stap (`2026-Q3`) en anders het VORIGE afgesloten kwartaal; een ongeldig `kwartaal` is een mislukte
        stap. Vrije tekst in de invoer bepaalt het kwartaal nooit. Stap 1 (receiptscanner) gebruikt dezelfde regel
        (`kwartaal_uit_pakketinvoer`). De tenant komt uit de skill, nooit uit `params`.
        """
        kwartaal, fout = kwartaal_uit_pakketinvoer(params.get("input"), _nu())
        if fout is not None or kwartaal is None:
            return ExecutionResult(
                task_id=f"{self.agent_id}-btw-overzicht",
                success=False,
                error_message=fout or "Dit kwartaal is niet geldig.",
                tenant_id=self.tenant_id,
            )
        overzicht = await asyncio.to_thread(
            BtwOverzicht(upload_map()).overzicht, self.tenant_id, kwartaal
        )
        return ExecutionResult(
            task_id=f"{self.agent_id}-btw-overzicht",
            success=True,
            result_data=dict(overzicht),
            tenant_id=self.tenant_id,
        )


def _nu() -> datetime:
    return datetime.now(timezone.utc)
