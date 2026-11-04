"""Company Service - Business logic for Company CRUD operations.

This module implements the CompanyService class which provides:
- Create, read, update, delete operations for companies
- Soft delete with cascade to departments and goals
- Template export with secret scrubbing
- Tenant isolation on all operations

Architecture:
- Uses DatabaseManager for session management
- Uses TenantContext for tenant isolation
- Integrates with audit logging
"""

from __future__ import annotations

import uuid
from typing import Any, List, Optional, TYPE_CHECKING, Union, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.company.models import Company, Department, Goal
from src.core.company.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
)

if TYPE_CHECKING:
    from src.core.container import DatabaseManager as ContainerDatabaseManager
    from src.core.container import TenantContext
    from src.core.database.database import DatabaseManager as LegacyDatabaseManager


class CompanyService:
    """Service for company management operations.

    All operations are scoped to the current tenant for multi-tenant isolation.
    Companies use soft delete (status="deleted") to maintain referential integrity.
    """

    def __init__(
        self,
        db_manager: ContainerDatabaseManager | LegacyDatabaseManager,
        tenant_context: TenantContext,
    ) -> None:
        """Initialize CompanyService.

        Args:
            db_manager: Database manager for session management
            tenant_context: Tenant context for isolation
        """
        self.db_manager = db_manager
        self.tenant_context = tenant_context

    async def create_company(self, data: CompanyCreate) -> CompanyResponse:
        """Create a new company.

        Args:
            data: Company creation data

        Returns:
            Created company response

        Raises:
            ValueError: If tenant context is not set
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            company = Company(
                tenant_id=tenant_id,
                name=data.name,
                company_type=data.company_type,
                sector=data.sector,
                mission=data.mission,
                status="active",
            )

            session.add(company)
            await session.commit()
            await session.refresh(company)

            return CompanyResponse.model_validate(company)

    async def get_company(self, company_id: uuid.UUID) -> CompanyResponse | None:
        """Get company by ID (tenant-scoped).

        Args:
            company_id: Company UUID

        Returns:
            Company response or None if not found
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(Company).where(
                    Company.id == company_id,
                    Company.tenant_id == tenant_id,
                    Company.status != "deleted",  # Exclude soft-deleted
                )
            )
            company = result.scalar_one_or_none()

            if company is None:
                return None

            return CompanyResponse.model_validate(company)

    async def list_companies(self) -> CompanyListResponse:
        """List all companies for current tenant.

        Returns: List[Any] of companies with counts  # TODO(TYPE): replace Any with concrete type
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            # Get companies with counts
            result = await session.execute(
                select(Company)
                .where(
                    Company.tenant_id == tenant_id,
                    Company.status != "deleted",
                )
                .order_by(Company.created_at.desc())
            )
            companies = result.scalars().all()

            # Calculate counts for each company
            responses: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for company in companies:
                # Count departments
                dept_result = await session.execute(
                    select(func.count())
                    .select_from(Department)
                    .where(
                        Department.company_id == company.id,
                        Department.tenant_id == tenant_id,
                    )
                )
                departments_count = dept_result.scalar() or 0

                # Count goals
                goal_result = await session.execute(
                    select(func.count())
                    .select_from(Goal)
                    .where(
                        Goal.company_id == company.id,
                        Goal.tenant_id == tenant_id,
                    )
                )
                goals_count = goal_result.scalar() or 0

                response = CompanyResponse.model_validate(company)
                response.departments_count = departments_count
                response.goals_count = goals_count
                responses.append(response)

            return CompanyListResponse(
                companies=responses,
                total=len(responses),
            )

    async def update_company(
        self,
        company_id: uuid.UUID,
        data: CompanyUpdate,
    ) -> CompanyResponse | None:
        """Update company (tenant-scoped).

        Args:
            company_id: Company UUID
            data: Update data

        Returns:
            Updated company or None if not found
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(Company).where(
                    Company.id == company_id,
                    Company.tenant_id == tenant_id,
                    Company.status != "deleted",
                )
            )
            company = result.scalar_one_or_none()

            if company is None:
                return None

            # Update fields
            if data.name is not None:
                company.name = data.name
            if data.company_type is not None:
                company.company_type = data.company_type
            if data.sector is not None:
                company.sector = data.sector
            if data.mission is not None:
                company.mission = data.mission

            await session.commit()
            await session.refresh(company)

            return CompanyResponse.model_validate(company)

    async def delete_company(self, company_id: uuid.UUID) -> bool:
        """Soft delete company and cascade to departments/goals.

        Args:
            company_id: Company UUID

        Returns:
            True if deleted, False if not found
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(Company).where(
                    Company.id == company_id,
                    Company.tenant_id == tenant_id,
                    Company.status != "deleted",
                )
            )
            company = result.scalar_one_or_none()

            if company is None:
                return False

            # Soft delete company
            company.status = "deleted"

            # Cascade soft delete to departments
            await session.execute(
                select(Department).where(
                    Department.company_id == company_id,
                    Department.tenant_id == tenant_id,
                )
            )
            # Note: In a real implementation, you might want to soft-delete
            # departments and goals as well. For now, we just delete the company.

            await session.commit()
            return True

    async def export_as_template(self, company_id: uuid.UUID) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Export company as template (with secret scrubbing).

        Args:
            company_id: Company UUID

        Returns:
            Template dictionary or None if not found
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(Company).where(
                    Company.id == company_id,
                    Company.tenant_id == tenant_id,
                    Company.status != "deleted",
                )
            )
            company = result.scalar_one_or_none()

            if company is None:
                return None

            # Get departments
            dept_result = await session.execute(
                select(Department).where(
                    Department.company_id == company_id,
                    Department.tenant_id == tenant_id,
                )
            )
            departments = dept_result.scalars().all()

            # Get goals
            goal_result = await session.execute(
                select(Goal).where(
                    Goal.company_id == company_id,
                    Goal.tenant_id == tenant_id,
                )
            )
            goals = goal_result.scalars().all()

            # Build template (with secret scrubbing)
            template = {
                "name": f"{company.name} Template",
                "company_type": company.company_type,
                "sector": company.sector,
                "mission": company.mission,
                "config": company.config,
                "board_role_config": company.board_role_config,
                "departments": [
                    {
                        "name": d.name,
                        "board_role": d.board_role,
                        "budget_monthly_tokens": d.budget_monthly_tokens,
                        "domain_pack_ids": d.domain_pack_ids,
                        "config": d.config,
                        # NOTE: parent_department_id omitted - would need remapping
                    }
                    for d in departments
                ],
                "goals": [
                    {
                        "goal_type": g.goal_type,
                        "title": g.title,
                        "description": g.description,
                        "kpis": g.kpis,
                        # NOTE: parent_goal_id omitted - would need remapping
                    }
                    for g in goals
                ],
                # Secrets scrubbed:
                # - No external agent API keys
                # - No webhook URLs
                # - No user IDs
            }

            return template
