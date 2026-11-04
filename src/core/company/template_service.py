"""TemplateService - Company templates and onboarding.

This service manages company templates including:
- Listing and retrieving templates
- Instantiating templates into companies
- Exporting companies as templates
- Contributing templates to the marketplace

Architecture: docs/ARCHITECTURE_PAPERCLIP_INTEGRATION.md S.7.5
PRD: docs/3-PRDs/PRD_PAPERCLIP_INTEGRATION_v1.0.md S.4.5
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.models import Agent
from src.core.company.agent_mappings import get_agents_for_department
from src.core.company.models import Company, CompanyTemplate, Department, Goal
from src.core.company.schemas import CompanyResponse, TemplateInstantiateRequest, TemplateResponse
from src.core.company.sector_departments import get_departments, is_generic_template
from src.core.database.database import DatabaseManager
from src.core.exceptions.exceptions import NotFoundError


class TemplateServiceError(Exception):
    """Base exception for TemplateService errors."""

    pass


class TemplateInstantiationError(TemplateServiceError):
    """Failed to instantiate template."""

    pass


class TemplateService:
    """Service for managing company templates.

    Templates provide pre-configured company setups that can be instantiated
    to quickly create companies with departments, goals, and pack configurations.
    """

    # Secret patterns to scrub during export
    SECRET_PATTERNS = [
        r"api_key[_\w]*",
        r"apikey[_\w]*",
        r"secret[_\w]*",
        r"password[_\w]*",
        r"token[_\w]*",
        r"webhook_url[_\w]*",
        r"webhook[_\w]*",
        r"auth[_\w]*",
        r"credential[_\w]*",
        r"private_key[_\w]*",
        r"client_secret[_\w]*",
    ]

    def __init__(
        self,
        db_manager: DatabaseManager,
        tenant_context: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Initialize TemplateService.

        Args:
            db_manager: Database manager for session management
            tenant_context: Tenant context for isolation
        """
        self.db_manager = db_manager
        self.tenant_context = tenant_context

    async def list_templates(
        self,
        filters: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> list[TemplateResponse]:
        """List available templates with optional filtering.

        Args:
            filters: Optional filters (company_type, sector, is_platform_template)

        Returns: List[Any] of TemplateResponse  # TODO(TYPE): replace Any with concrete type
        """
        tenant_id = self.tenant_context.tenant_id
        filters = filters or {}

        async with self.db_manager.get_session() as session:
            query = select(CompanyTemplate).where(
                (CompanyTemplate.is_platform_template.is_(True))
                | (CompanyTemplate.contributed_by_tenant_id == tenant_id)
            )

            # Apply filters
            if "company_type" in filters:
                query = query.where(CompanyTemplate.company_type == filters["company_type"])
            if "sector" in filters:
                query = query.where(CompanyTemplate.sector == filters["sector"])
            if "is_platform_template" in filters:
                query = query.where(
                    CompanyTemplate.is_platform_template == filters["is_platform_template"]
                )

            # Order by usage count (most popular first)
            query = query.order_by(CompanyTemplate.usage_count.desc())

            result = await session.execute(query)
            templates = result.scalars().all()

            return [self._to_response_model(t) for t in templates]

    async def get_template(self, template_id: uuid.UUID) -> TemplateResponse:
        """Get a specific template by ID.

        Args:
            template_id: Template UUID

        Returns:
            TemplateResponse

        Raises:
            NotFoundError: If template not found
        """
        tenant_id = self.tenant_context.tenant_id

        async with self.db_manager.get_session() as session:
            template = await self._get_template(session, template_id, tenant_id)
            if not template:
                raise NotFoundError(f"Template {template_id} not found")

            return self._to_response_model(template)

    async def instantiate(
        self,
        template_id: uuid.UUID,
        data: TemplateInstantiateRequest,
    ) -> CompanyResponse:
        """Instantiate a template into a new company.

        Creates a new company based on the template definition, including
        departments, goals, and pack configurations.

        Args:
            template_id: Template UUID
            data: Instantiation request with company name and customizations

        Returns:
            CompanyResponse for the created company

        Raises:
            NotFoundError: If template not found
            TemplateInstantiationError: If instantiation fails
        """
        tenant_id = self.tenant_context.tenant_id

        async with self.db_manager.get_session() as session:
            # Get template
            template = await self._get_template(session, template_id, tenant_id)
            if not template:
                raise NotFoundError(f"Template {template_id} not found")

            try:
                # Create company
                company = await self._create_company_from_template(
                    session, template, data, tenant_id
                )

                # MODIFIED: Create departments and get return value
                departments = await self._create_departments_from_template(
                    session, company, template, data.customizations
                )

                # NEW: Create agents for each department
                for dept in departments:
                    await self._create_agents_for_department(session, dept)

                # Create goals
                await self._create_goals_from_template(
                    session, company, template, data.customizations
                )

                # Update template usage count
                template.usage_count += 1
                await session.commit()
                await session.refresh(company)

                return self._company_to_response(company)

            except Exception as e:
                raise TemplateInstantiationError(f"Failed to instantiate template: {str(e)}") from e

    async def export_company(
        self,
        company_id: uuid.UUID,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Export a company as a template definition.

        Exports company structure (departments, goals) as a template
        definition. Secrets are scrubbed from the export.

        Args:
            company_id: Company UUID to export

            Returns:
            Template definition dictionary

        Raises:
            NotFoundError: If company not found
        """
        tenant_id = self.tenant_context.tenant_id

        async with self.db_manager.get_session() as session:
            # Get company with relationships
            company = await self._get_company(session, company_id, tenant_id)
            if not company:
                raise NotFoundError(f"Company {company_id} not found")

            # Build template definition
            template_def: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "name": f"{company.name} Template",
                "company_type": company.company_type,
                "sector": company.sector,
                "mission": company.mission,
                "departments": [],
                "goals": [],
                "board_role_config": company.board_role_config,
            }

            # Add departments
            for dept in company.departments:
                template_def["departments"].append(
                    {
                        "name": dept.name,
                        "parent_department_id": (
                            str(dept.parent_department_id) if dept.parent_department_id else None
                        ),
                        "board_role": dept.board_role,
                        "budget_monthly_tokens": dept.budget_monthly_tokens,
                        "domain_pack_ids": dept.domain_pack_ids,
                    }
                )

            # Add goals
            for goal in company.goals:
                template_def["goals"].append(
                    {
                        "goal_type": goal.goal_type,
                        "title": goal.title,
                        "description": goal.description,
                        "parent_goal_id": str(goal.parent_goal_id) if goal.parent_goal_id else None,
                        "department_name": goal.department.name if goal.department else None,
                        "kpis": goal.kpis,
                    }
                )

            # Scrub secrets
            scrubbed_def = self._scrub_secrets(template_def)

            return scrubbed_def

    async def contribute(
        self,
        name: str,
        company_type: str,
        sector: str,
        description: str,
        template_definition: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> TemplateResponse:
        """Contribute a new template to the marketplace.

        Allows tenants to contribute their company configurations
        as templates for others to use.

        Args:
            name: Template name
            company_type: Company type (mkb, zzp, enterprise)
            sector: Industry sector
            description: Template description
            template_definition: Complete template definition

        Returns:
            TemplateResponse for the created template
        """
        tenant_id = self.tenant_context.tenant_id

        async with self.db_manager.get_session() as session:
            # Scrub secrets before saving
            scrubbed_definition = self._scrub_secrets(template_definition)

            template = CompanyTemplate(
                name=name,
                company_type=company_type,
                sector=sector,
                description=description,
                template_definition=scrubbed_definition,
                is_platform_template=False,
                contributed_by_tenant_id=tenant_id,
                usage_count=0,
                rating_sum=0,
                rating_count=0,
                status="active",
            )

            session.add(template)
            await session.commit()
            await session.refresh(template)

            return self._to_response_model(template)

    def _scrub_secrets(self, data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Scrub secrets from template definition.

        Recursively scans the dictionary for secret patterns and
        replaces them with placeholder values.

        Args:
            data: Dict[str, Any]ionary to scrub  # TODO(TYPE): replace Any with concrete type

        Returns:
            Scrubbed dictionary
        """
        scrubbed: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for key, value in data.items():
            # Check if key matches secret pattern
            is_secret = any(
                re.match(pattern, key, re.IGNORECASE) for pattern in self.SECRET_PATTERNS
            )

            if is_secret:
                # Replace with placeholder
                scrubbed[key] = f"[SCRUBBED_{key.upper()}]"
            elif isinstance(value, dict):
                # Recurse into nested dict
                scrubbed[key] = self._scrub_secrets(value)
            elif isinstance(value, list):
                # Process list items
                scrubbed[key] = [
                    self._scrub_secrets(item) if isinstance(item, dict) else item for item in value
                ]
            else:
                scrubbed[key] = value

        return scrubbed

    async def _get_template(
        self,
        session: AsyncSession,
        template_id: uuid.UUID,
        tenant_id: int,
    ) -> CompanyTemplate | None:
        """Get template by ID with tenant check."""
        result = await session.execute(
            select(CompanyTemplate).where(
                CompanyTemplate.id == template_id,
                (
                    (CompanyTemplate.is_platform_template.is_(True))
                    | (CompanyTemplate.contributed_by_tenant_id == tenant_id)
                ),
            )
        )
        return result.scalar_one_or_none()

    async def _get_company(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        tenant_id: int,
    ) -> Company | None:
        """Get company by ID with tenant check."""
        result = await session.execute(
            select(Company).where(
                Company.id == company_id,
                Company.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def _create_company_from_template(
        self,
        session: AsyncSession,
        template: CompanyTemplate,
        data: TemplateInstantiateRequest,
        tenant_id: int,
    ) -> Company:
        """Create company from template."""
        company = Company(
            tenant_id=tenant_id,
            name=data.company_name,
            company_type=template.company_type,
            sector=template.sector,
            mission=template.template_definition.get("mission"),
            board_role_config=template.template_definition.get("board_role_config"),
            template_id=template.id,
            status="active",
        )
        session.add(company)
        await session.flush()
        return company

    async def _create_departments_from_template(
        self,
        session: AsyncSession,
        company: Company,
        template: CompanyTemplate,
        customizations: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[Department]:
        """Create departments from template definition.

        If template has generic departments, uses sector-specific configuration.
        Returns list of created departments for agent creation.
        """
        # Get template definition
        definition = template.template_definition or {}
        departments_data = definition.get("departments", [])

        # NEW: Check if generic and enrich with sector-specific
        if is_generic_template(departments_data):
            sector_depts = get_departments(template.sector, template.company_type)
            if sector_depts:
                departments_data = sector_depts
                # Apply any customizations
                for i, dept in enumerate(departments_data):
                    dept_name = dept["name"]
                    if f"dept_{dept_name}_name" in customizations:
                        departments_data[i] = {
                            **dept,
                            "name": customizations[f"dept_{dept_name}_name"],
                        }

        dept_map: dict[str, uuid.UUID] = {}
        created_departments: list[Department] = []

        # First pass: create all departments
        for dept_def in departments_data:
            dept_name = dept_def["name"]
            # Apply customizations (if not already applied during enrichment)
            if f"dept_{dept_name}_name" in customizations:
                dept_name = customizations[f"dept_{dept_name}_name"]

            dept = Department(
                tenant_id=company.tenant_id,
                company_id=company.id,
                name=dept_name,
                board_role=dept_def.get("board_role"),
                budget_monthly_tokens=dept_def.get("budget_monthly_tokens"),
                domain_pack_ids=dept_def.get("domain_pack_ids", []),
            )
            session.add(dept)
            await session.flush()
            dept_map[dept_def["name"]] = dept.id
            created_departments.append(dept)

        # Second pass: set parent relationships
        for dept_def in departments_data:
            if dept_def.get("parent_department_id"):
                # Find parent by name and set relationship
                parent_name = None
                for d in departments_data:
                    if d.get("id") == dept_def["parent_department_id"]:
                        parent_name = d["name"]
                        break

                if parent_name and parent_name in dept_map:
                    # Update department with parent
                    result = await session.execute(
                        select(Department).where(
                            Department.company_id == company.id,
                            Department.name == dept_def["name"],
                        )
                    )
                    dept = result.scalar_one()
                    dept.parent_department_id = dept_map[parent_name]

        return created_departments

    async def _create_agents_for_department(
        self,
        session: AsyncSession,
        department: Department,
    ) -> list[Agent]:
        """Create default agents for a department.

        Uses ONLY existing Agent model fields:
        - id (auto)
        - name (str)
        - agent_type (str)
        - tenant_id (int)
        - department_id (UUID) - NEW from migration
        - created_at (auto)

        NOTE: department_id is now available after Task 3 migration
        """
        agent_types = get_agents_for_department(department.name)
        created_agents = []

        for agent_type in agent_types:
            agent = Agent(
                tenant_id=department.tenant_id,
                department_id=department.id,
                name=f"{agent_type}",
                agent_type=agent_type,
            )
            session.add(agent)
            created_agents.append(agent)

        await session.flush()
        return created_agents

    async def _create_goals_from_template(
        self,
        session: AsyncSession,
        company: Company,
        template: CompanyTemplate,
        customizations: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Create goals from template definition."""
        goal_map: dict[str, uuid.UUID] = {}  # template goal title -> new goal ID

        goals = template.template_definition.get("goals", [])

        # First pass: create all goals
        for goal_def in goals:
            goal_title = goal_def["title"]
            # Apply customizations
            if f"goal_{goal_title}_title" in customizations:
                goal_title = customizations[f"goal_{goal_title}_title"]

            # Find department if specified
            department_id = None
            if goal_def.get("department_name"):
                result = await session.execute(
                    select(Department).where(
                        Department.company_id == company.id,
                        Department.name == goal_def["department_name"],
                    )
                )
                dept = result.scalar_one_or_none()
                if dept:
                    department_id = dept.id

            goal = Goal(
                tenant_id=company.tenant_id,
                company_id=company.id,
                department_id=department_id,
                goal_type=goal_def["goal_type"],
                title=goal_title,
                description=goal_def.get("description"),
                kpis=goal_def.get("kpis", {}),
                status="not_started",
                progress_pct=0,
            )
            session.add(goal)
            await session.flush()
            goal_map[goal_def["title"]] = goal.id

        # Second pass: set parent relationships
        for goal_def in goals:
            if goal_def.get("parent_goal_id"):
                # Find parent by title
                parent_title = None
                for g in goals:
                    if g.get("id") == goal_def["parent_goal_id"]:
                        parent_title = g["title"]
                        break

                if parent_title and parent_title in goal_map:
                    result = await session.execute(
                        select(Goal).where(
                            Goal.company_id == company.id,
                            Goal.title == goal_def["title"],
                        )
                    )
                    goal = result.scalar_one()
                    goal.parent_goal_id = goal_map[parent_title]

    def _to_response_model(self, template: CompanyTemplate) -> TemplateResponse:
        """Convert CompanyTemplate ORM to response model."""
        rating_avg = None
        if template.rating_count > 0:
            rating_avg = template.rating_sum / template.rating_count

        return TemplateResponse(
            id=template.id,
            name=template.name,
            company_type=template.company_type,
            sector=template.sector,
            description=template.description or "",
            is_platform_template=template.is_platform_template,
            usage_count=template.usage_count,
            rating_avg=rating_avg,
        )

    def _company_to_response(self, company: Company) -> CompanyResponse:
        """Convert Company ORM to response model."""
        return CompanyResponse(
            id=company.id,
            tenant_id=company.tenant_id,
            name=company.name,
            company_type=company.company_type,
            sector=company.sector,
            mission=company.mission,
            status=company.status,
            departments_count=len(company.departments),
            goals_count=len(company.goals),
            created_at=company.created_at,
        )
