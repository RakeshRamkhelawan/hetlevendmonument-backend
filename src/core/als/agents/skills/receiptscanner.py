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


def _nu() -> datetime:
    return datetime.now(timezone.utc)


class ReceiptScannerSkill(BaseSpecialistAgent):
    """
    Receipt Scanner worker agent.

    Loaded from ``manifests/receiptscanner.yml``; behavior is driven by the manifest
    and executed through the shared BaseSpecialistAgent OODA loop.
    """

    def __init__(self, tenant_id: int, **kwargs: Any) -> None:
        manifest = SkillManifest.load(Path(__file__).parent / "manifests/receiptscanner.yml")
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
        """Het pad dat `packs.py::_execute_step` aanroept: een samenvatting van BEVESTIGDE bonnen van een kwartaal.

        Geen taalmodel: wat een bon zegt is door een medewerker bevestigd (bonlezer dag 4), en alleen
        dat gaat verder. Het kwartaal is hetzelfde als dat van stap 2 (`kwartaal_uit_pakketinvoer`: het `kwartaal`
        in de invoer, anders het vorige afgesloten kwartaal) en staat in de uitslag. De tenant komt uit de skill,
        nooit uit `params`. Geen bevestigde bonnen is geen fout maar aantal 0.
        """
        kwartaal, fout = kwartaal_uit_pakketinvoer(params.get("input"), _nu())
        if fout is not None or kwartaal is None:
            return ExecutionResult(
                task_id=f"{self.agent_id}-bevestigde-bonnen",
                success=False,
                error_message=fout or "Dit kwartaal is niet geldig.",
                tenant_id=self.tenant_id,
            )
        samenvatting = await asyncio.to_thread(
            BtwOverzicht(upload_map()).bonnen_samenvatting, self.tenant_id, kwartaal
        )
        return ExecutionResult(
            task_id=f"{self.agent_id}-bevestigde-bonnen",
            success=True,
            result_data=dict(samenvatting),
            tenant_id=self.tenant_id,
        )
