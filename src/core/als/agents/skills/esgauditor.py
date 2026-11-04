import logging
from pathlib import Path
from typing import Any

from src.core.als.agents.skill_manifest import SkillManifest
from src.core.als.agents.specialist_base import BaseSpecialistAgent
from src.core.shared.interfaces import ExecutionResult

logger = logging.getLogger(__name__)


class ESGAuditorSkill(BaseSpecialistAgent):
    """
    ESGAuditor worker agent.

    Loaded from ``manifests/esgauditor.yml``; behavior is driven by the manifest
    and executed through the shared BaseSpecialistAgent OODA loop.
    """

    def __init__(self, tenant_id: int, **kwargs: Any) -> None:
        manifest = SkillManifest.load(Path(__file__).parent / "manifests/esgauditor.yml")
        config = manifest.to_config()
        # Merge any runtime overrides passed by the caller
        config.update(kwargs)
        super().__init__(config=config, tenant_id=tenant_id)

    async def act(self, decision: str) -> ExecutionResult:
        """Execute using the shared OODA/tool runtime instead of a hardcoded stub."""
        logger.info(f"[{self.agent_id}] Executing via shared runtime for tenant {self.tenant_id}")
        return await super().act(decision)
