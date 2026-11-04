import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from src.domains.projects.models import ProjectConfig

logger = logging.getLogger("project_repo")


class ProjectRepository:
    """
    Persistence layer for ProjectConfigs with tenant isolation.
    Uses JSON files in `data/projects/{tenant_id}/`.

    SECURITY: tenant_id isolation via directory structure (Fase 0.2)
    """

    def __init__(self, tenant_id: str, storage_dir: str = "data/projects") -> None:
        self._tenant_id = tenant_id
        self.storage_dir = Path(storage_dir) / tenant_id
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, project: ProjectConfig) -> str:
        """Save or update a project with tenant isolation."""
        # Ensure project belongs to this tenant
        if project.tenant_id != self._tenant_id:
            raise ValueError(
                f"Project tenant_id {project.tenant_id} does not match "
                f"repository tenant_id {self._tenant_id}"
            )

        file_path = self.storage_dir / f"{project.id}.json"
        try:
            # Pydantic v2 dump (use .dict() for v1 if needed)
            data = project.model_dump(mode="json")

            # Write async (simulated via thread)
            await asyncio.to_thread(
                file_path.write_text, json.dumps(data, indent=2), encoding="utf-8"
            )
            return project.id
        except Exception as e:
            logger.error(f"Failed to save project {project.id}: {e}")
            raise e

    async def get(self, project_id: str) -> ProjectConfig | None:
        """Load a project by ID, ensuring it belongs to the tenant."""
        file_path = self.storage_dir / f"{project_id}.json"
        if not file_path.exists():
            logger.debug(f"Project {project_id} not found in tenant {self._tenant_id}")
            return None

        try:
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
            data = json.loads(content)
            project = ProjectConfig(**data)

            # Double-check tenant isolation (defense in depth)
            if project.tenant_id != self._tenant_id:
                logger.error(
                    f"Tenant isolation breach: project {project_id} "
                    f"belongs to tenant {project.tenant_id} but accessed via tenant {self._tenant_id}"
                )
                return None

            return project
        except Exception as e:
            logger.error(f"Failed to load project {project_id}: {e}")
            return None

    async def list_active(self) -> list[ProjectConfig]:
        """List all active projects for the tenant."""
        projects: list[ProjectConfig] = []
        try:
            for file_path in self.storage_dir.glob("*.json"):
                content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
                data = json.loads(content)
                project = ProjectConfig(**data)

                # Verify tenant isolation
                if project.tenant_id != self._tenant_id:
                    logger.warning(
                        f"Skipping project {project.id} - wrong tenant {project.tenant_id}"
                    )
                    continue

                if project.status == "ACTIVE":
                    projects.append(project)
        except Exception as e:
            logger.error(f"Failed to list projects for tenant {self._tenant_id}: {e}")

        return projects


# NOTE: Singleton removed - ProjectRepository now requires tenant_id
# Use: ProjectRepository(tenant_id="tenant-123") instead
