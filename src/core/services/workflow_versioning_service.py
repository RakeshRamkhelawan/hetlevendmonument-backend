"""
Workflow Versioning Service
=============================

Manages workflow snapshots, history, and rollback.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.workflow.schemas import WorkflowDefinition
from src.core.models.workflow_version_models import WorkflowVersion

logger = logging.getLogger(__name__)


class WorkflowVersioningService:
    """
    Service for managing workflow versions and history.
    """

    @staticmethod
    async def save_version(
        db: AsyncSession,
        tenant_id: int,
        workflow_id: str,
        name: str,
        workflow: WorkflowDefinition,
        created_by: int,
        change_description: str = "",
        tags: list[str] | None = None,
    ) -> WorkflowVersion:
        """
        Save a new version of a workflow.

        Args:
            db: Database session
            tenant_id: Tenant ID
            workflow_id: Workflow identifier
            name: Workflow name
            workflow: Workflow definition (nodes + edges)
            created_by: User ID who created this version
            change_description: What changed
            tags: Optional tags for this version

        Returns:
            Created WorkflowVersion
        """

        try:
            # Get next version number
            result = await db.execute(
                select(WorkflowVersion)
                .where(
                    WorkflowVersion.tenant_id == tenant_id,
                    WorkflowVersion.workflow_id == workflow_id,
                )
                .order_by(WorkflowVersion.version_number.desc())
            )
            last_version = result.scalars().first()
            next_version = (last_version.version_number + 1) if last_version else 1

            # Create version
            version = WorkflowVersion(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                version_number=next_version,
                name=name,
                created_by=created_by,
                workflow_spec={
                    "nodes": [
                        {
                            "id": n.id,
                            "name": n.name,
                            "type": n.type,
                            "x": n.x,
                            "y": n.y,
                            "data": n.data,
                        }
                        for n in workflow.nodes
                    ],
                    "edges": [
                        {
                            "id": e.id,
                            "source": e.source,
                            "target": e.target,
                            "type": e.type,
                        }
                        for e in workflow.edges
                    ],
                },
                change_description=change_description,
                tags=tags or [],
            )

            db.add(version)
            await db.flush()

            logger.info(
                f"[OK] Saved workflow version {next_version}",
                extra={
                    "tenant_id": tenant_id,
                    "workflow_id": workflow_id,
                    "version": next_version,
                },
            )

            return version

        except Exception as e:
            logger.error(f"[FAIL] Failed to save version: {str(e)}", exc_info=True)
            raise

    @staticmethod
    async def get_version_history(
        db: AsyncSession,
        tenant_id: int,
        workflow_id: str,
        limit: int = 10,
    ) -> list[WorkflowVersion]:
        """
        Get version history for a workflow.

        Args:
            db: Database session
            tenant_id: Tenant ID
            workflow_id: Workflow ID
            limit: Max versions to return

        Returns: List[Any] of WorkflowVersion objects, most recent first  # TODO(TYPE): replace Any with concrete type
        """

        result = await db.execute(
            select(WorkflowVersion)
            .where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.workflow_id == workflow_id,
            )
            .order_by(WorkflowVersion.version_number.desc())
            .limit(limit)
        )

        return list(result.scalars().all())

    @staticmethod
    async def get_version(
        db: AsyncSession,
        tenant_id: int,
        workflow_id: str,
        version_number: int,
    ) -> WorkflowVersion | None:
        """
        Get a specific workflow version.

        Args:
            db: Database session
            tenant_id: Tenant ID
            workflow_id: Workflow ID
            version_number: Version to retrieve

        Returns:
            WorkflowVersion or None if not found
        """

        result = await db.execute(
            select(WorkflowVersion).where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.workflow_id == workflow_id,
                WorkflowVersion.version_number == version_number,
            )
        )

        return result.scalars().first()

    @staticmethod
    async def rollback_to_version(
        db: AsyncSession,
        tenant_id: int,
        workflow_id: str,
        target_version: int,
        rolled_back_by: int,
    ) -> WorkflowVersion:
        """
        Rollback workflow to a previous version.

        Creates a new version with the old content.

        Args:
            db: Database session
            tenant_id: Tenant ID
            workflow_id: Workflow ID
            target_version: Version number to rollback to
            rolled_back_by: User ID performing rollback

        Returns:
            New WorkflowVersion with restored content
        """

        try:
            # Get target version
            target = await WorkflowVersioningService.get_version(
                db, tenant_id, workflow_id, target_version
            )

            if not target:
                raise ValueError(f"Version {target_version} not found")

            # Restore as new version
            restored_spec = target.workflow_spec
            workflow = WorkflowDefinition(
                nodes=[],
                edges=[],
            )

            # Reconstruct workflow from spec
            from src.core.workflow.schemas import WorkflowEdge, WorkflowNode

            for node_data in restored_spec.get("nodes", []):
                workflow.nodes.append(
                    WorkflowNode(
                        id=node_data["id"],
                        name=node_data["name"],
                        type=node_data["type"],
                        x=node_data.get("x", 0),
                        y=node_data.get("y", 0),
                        data=node_data.get("data", {}),
                    )
                )

            for edge_data in restored_spec.get("edges", []):
                workflow.edges.append(
                    WorkflowEdge(
                        id=edge_data["id"],
                        source=edge_data["source"],
                        target=edge_data["target"],
                        type=edge_data.get("type", "smoothstep"),
                    )
                )

            # Save as new version
            new_version = await WorkflowVersioningService.save_version(
                db=db,
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                name=target.name,
                workflow=workflow,
                created_by=rolled_back_by,
                change_description=f"Rolled back to version {target_version}: {target.change_description}",
                tags=(target.tags or []) + ["rollback"],
            )

            logger.info(
                f"[OK] Rolled back to version {target_version}",
                extra={
                    "tenant_id": tenant_id,
                    "workflow_id": workflow_id,
                    "target_version": target_version,
                    "new_version": new_version.version_number,
                },
            )

            await db.commit()
            return new_version

        except Exception as e:
            logger.error(f"[FAIL] Rollback failed: {str(e)}", exc_info=True)
            raise

    @staticmethod
    async def compare_versions(
        db: AsyncSession,
        tenant_id: int,
        workflow_id: str,
        version1: int,
        version2: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Compare two workflow versions.

        Args:
            db: Database session
            tenant_id: Tenant ID
            workflow_id: Workflow ID
            version1: First version number
            version2: Second version number

        Returns: Dict[str, Any] with differences  # TODO(TYPE): replace Any with concrete type
        """

        v1 = await WorkflowVersioningService.get_version(db, tenant_id, workflow_id, version1)
        v2 = await WorkflowVersioningService.get_version(db, tenant_id, workflow_id, version2)

        if not v1 or not v2:
            raise ValueError("One or both versions not found")

        spec1 = v1.workflow_spec
        spec2 = v2.workflow_spec

        # Simple diff: count nodes
        nodes_added = len(spec2["nodes"]) - len(spec1["nodes"])
        edges_added = len(spec2["edges"]) - len(spec1["edges"])

        return {
            "version1": version1,
            "version2": version2,
            "created_at_v1": v1.created_at.isoformat() if v1.created_at else None,
            "created_at_v2": v2.created_at.isoformat() if v2.created_at else None,
            "nodes_change": nodes_added,
            "edges_change": edges_added,
            "description_v1": v1.change_description,
            "description_v2": v2.change_description,
        }
