"""Department Service - Business logic for Department CRUD operations.

This module implements the DepartmentService class which provides:
- Create, read, update, delete operations for departments
- Organization chart generation (tree structure)
- Optimistic locking for concurrent edits
- Circular reference detection
- Max depth validation (5 levels)

Architecture:
- Uses DatabaseManager for session management
- Uses TenantContext for tenant isolation
- Integrates with CompanyService for company validation
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Optional, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.company.models import Company, Department, PackActivationAuditLog
from src.core.company.pack_activation import (
    ActivationSignals,
    PackActivationResult,
    PackActivationScorer,
)
from src.core.company.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    OrgChartResponse,
)
from src.core.container import DatabaseManager
from src.core.exceptions.exceptions import ConflictError, NotFoundError
from src.core.monitoring.pack_metrics import record_pack_activation

if TYPE_CHECKING:
    from src.core.container import TenantContext


class DepartmentService:
    """Service for department management operations.

    All operations are scoped to the current tenant for multi-tenant isolation.
    Departments form a hierarchical tree structure within a company.
    """

    # Maximum depth of department hierarchy
    MAX_DEPTH = 5

    def __init__(
        self,
        db_manager: DatabaseManager,
        tenant_context: TenantContext,
        pack_registry: Any | None = None,  # DomainPackRegistry, optional for compat  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Initialize DepartmentService.

        Args:
            db_manager: Database manager for session management
            tenant_context: Tenant context for isolation
            pack_registry: Optional DomainPackRegistry for pack scoring
        """
        self.db_manager = db_manager
        self.tenant_context = tenant_context
        self._pack_registry = pack_registry

    async def _create_department_record(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        data: DepartmentCreate,
    ) -> Department:
        """Create and persist a department record.

        Args:
            session: Database session
            company_id: Parent company ID
            data: Department creation data

        Returns:
            Created department
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        # Validate parent department if provided
        if data.parent_department_id:
            parent_result = await session.execute(
                select(Department).where(
                    Department.id == data.parent_department_id,
                    Department.company_id == company_id,
                    Department.tenant_id == tenant_id,
                )
            )
            parent = parent_result.scalar_one_or_none()
            if parent is None:
                raise NotFoundError(f"Parent department {data.parent_department_id} not found")

            # Check max depth
            parent_depth = await self._get_department_depth(session, data.parent_department_id)
            if parent_depth >= self.MAX_DEPTH:
                raise ConflictError(f"Maximum department depth ({self.MAX_DEPTH}) exceeded")

        # Create department
        department = Department(
            tenant_id=tenant_id,
            company_id=company_id,
            name=data.name,
            parent_department_id=data.parent_department_id,
            head_user_id=data.head_user_id,
            board_role=data.board_role,
            budget_monthly_tokens=data.budget_monthly_tokens,
            version=1,
        )

        session.add(department)
        await session.commit()
        await session.refresh(department)

        return department

    async def create_department(
        self,
        company_id: uuid.UUID,
        data: DepartmentCreate,
    ) -> DepartmentResponse:
        """Create a new department.

        Args:
            company_id: Parent company ID
            data: Department creation data

        Returns:
            Created department response

        Raises:
            NotFoundError: If company not found
            ConflictError: If parent department invalid
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            # Verify company exists and belongs to tenant
            company_result = await session.execute(
                select(Company).where(
                    Company.id == company_id,
                    Company.tenant_id == tenant_id,
                    Company.status != "deleted",
                )
            )
            company = company_result.scalar_one_or_none()
            if company is None:
                raise NotFoundError(f"Company {company_id} not found")

            # Create department record
            department = await self._create_department_record(session, company_id, data)

            # Trigger pack activation scoring (R2)
            await self._trigger_pack_activation(department, company)

            return DepartmentResponse.model_validate(department)

    async def get_department(
        self,
        dept_id: uuid.UUID,
    ) -> DepartmentResponse | None:
        """Get department by ID.

        Args:
            dept_id: Department UUID

        Returns:
            Department response or None
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(Department).where(
                    Department.id == dept_id,
                    Department.tenant_id == tenant_id,
                )
            )
            department = result.scalar_one_or_none()

            if department is None:
                return None

            return DepartmentResponse.model_validate(department)

    async def get_org_chart(
        self,
        company_id: uuid.UUID,
    ) -> OrgChartResponse:
        """Get organization chart for a company.

        Args:
            company_id: Company UUID

        Returns:
            Organization chart with tree structure
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            # Get all departments for company
            result = await session.execute(
                select(Department)
                .where(
                    Department.company_id == company_id,
                    Department.tenant_id == tenant_id,
                )
                .order_by(Department.created_at)
            )
            departments = result.scalars().all()

            # Build tree structure
            dept_dict = {d.id: DepartmentResponse.model_validate(d) for d in departments}

            # Calculate children counts
            for dept in departments:
                children_count = sum(1 for d in departments if d.parent_department_id == dept.id)
                dept_dict[dept.id].children_count = children_count

            # Build tree
            tree = self._build_tree(dept_dict)

            return OrgChartResponse(
                departments=list(dept_dict.values()),
                tree_structure=tree,
            )

    async def update_department(
        self,
        dept_id: uuid.UUID,
        data: DepartmentUpdate,
    ) -> DepartmentResponse:
        """Update department with optimistic locking.

        Args:
            dept_id: Department UUID
            data: Update data (includes expected_version)

        Returns:
            Updated department

        Raises:
            NotFoundError: If department not found
            ConflictError: If version conflict or circular reference
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            # Get department with optimistic lock check
            result = await session.execute(
                select(Department).where(
                    Department.id == dept_id,
                    Department.tenant_id == tenant_id,
                )
            )
            department = result.scalar_one_or_none()

            if department is None:
                raise NotFoundError(f"Department {dept_id} not found")

            # Fetch company for pack activation
            company_result = await session.execute(
                select(Company).where(
                    Company.id == department.company_id,
                    Company.tenant_id == tenant_id,
                )
            )
            company = company_result.scalar_one_or_none()
            if company is None:
                raise NotFoundError(f"Company for department {dept_id} not found")

            # Optimistic locking check
            if data.expected_version is not None:
                if department.version != data.expected_version:
                    raise ConflictError(
                        "Department has been modified by another user",
                        current_version=department.version,
                    )

            # Check circular reference if moving parent
            if data.parent_department_id is not None:
                if data.parent_department_id == dept_id:
                    raise ConflictError("Department cannot be its own parent")

                # Check if new parent is a descendant (would create cycle)
                is_descendant = await self._is_descendant(
                    session, dept_id, data.parent_department_id
                )
                if is_descendant:
                    raise ConflictError(
                        "Cannot move department to its own descendant (circular reference)"
                    )

                # Check max depth
                new_parent_depth = await self._get_department_depth(
                    session, data.parent_department_id
                )
                if new_parent_depth >= self.MAX_DEPTH:
                    raise ConflictError(f"Maximum department depth ({self.MAX_DEPTH}) exceeded")

            # Update fields
            if data.name is not None:
                department.name = data.name
            if data.parent_department_id is not None:
                department.parent_department_id = data.parent_department_id
            if data.head_user_id is not None:
                department.head_user_id = data.head_user_id  # type: ignore[assignment]
            if data.board_role is not None:
                department.board_role = data.board_role
            if data.budget_monthly_tokens is not None:
                department.budget_monthly_tokens = data.budget_monthly_tokens

            # Increment version
            department.version += 1

            await session.commit()
            await session.refresh(department)

            # Trigger pack activation scoring on update (R2)
            await self._trigger_pack_activation(department, company)

            return DepartmentResponse.model_validate(department)

    async def delete_department(self, dept_id: uuid.UUID) -> bool:
        """Delete department (with children check).

        Args:
            dept_id: Department UUID

        Returns:
            True if deleted

        Raises:
            NotFoundError: If department not found
            ConflictError: If department has children
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(Department).where(
                    Department.id == dept_id,
                    Department.tenant_id == tenant_id,
                )
            )
            department = result.scalar_one_or_none()

            if department is None:
                raise NotFoundError(f"Department {dept_id} not found")

            # Check for children
            children_result = await session.execute(
                select(func.count())
                .select_from(Department)
                .where(
                    Department.parent_department_id == dept_id,
                    Department.tenant_id == tenant_id,
                )
            )
            children_count = children_result.scalar() or 0

            if children_count > 0:
                raise ConflictError(
                    f"Cannot delete department with {children_count} children. "
                    "Move or delete children first."
                )

            await session.delete(department)
            await session.commit()

            return True

    async def move_department(
        self,
        dept_id: uuid.UUID,
        new_parent_id: uuid.UUID | None,
    ) -> DepartmentResponse:
        """Move department to new parent.

        Args:
            dept_id: Department to move
            new_parent_id: New parent department (None for root)

        Returns:
            Updated department
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        async with self.db_manager.get_session() as session:
            # Get department
            result = await session.execute(
                select(Department).where(
                    Department.id == dept_id,
                    Department.tenant_id == tenant_id,
                )
            )
            department = result.scalar_one_or_none()

            if department is None:
                raise NotFoundError(f"Department {dept_id} not found")

            # Check circular reference
            if new_parent_id is not None:
                if new_parent_id == dept_id:
                    raise ConflictError("Department cannot be its own parent")

                is_descendant = await self._is_descendant(session, dept_id, new_parent_id)
                if is_descendant:
                    raise ConflictError("Cannot move to descendant (circular reference)")

                # Check max depth
                new_parent_depth = await self._get_department_depth(session, new_parent_id)
                if new_parent_depth >= self.MAX_DEPTH:
                    raise ConflictError(f"Maximum department depth ({self.MAX_DEPTH}) exceeded")

            department.parent_department_id = new_parent_id
            department.version += 1

            await session.commit()
            await session.refresh(department)

            return DepartmentResponse.model_validate(department)

    async def _get_department_depth(
        self,
        session: AsyncSession,
        dept_id: uuid.UUID,
    ) -> int:
        """Calculate depth of department in hierarchy.

        Args:
            session: Database session
            dept_id: Department UUID

        Returns:
            Depth (0 = root, 1 = child of root, etc.)
        """
        depth = 0
        current_id = dept_id
        max_iterations = 10  # Safety limit to prevent infinite loops

        while current_id and depth < max_iterations:
            result = await session.execute(
                select(Department.parent_department_id).where(
                    Department.id == current_id,
                )
            )
            parent_id = result.scalar_one_or_none()

            if parent_id:
                depth += 1
                current_id = parent_id
            else:
                break

        return depth

    async def _is_descendant(
        self,
        session: AsyncSession,
        ancestor_id: uuid.UUID,
        potential_descendant_id: uuid.UUID,
    ) -> bool:
        """Check if potential_descendant is a descendant of ancestor.

        Args:
            session: Database session
            ancestor_id: Potential ancestor
            potential_descendant_id: Potential descendant

        Returns:
            True if potential_descendant is a descendant
        """
        current_id = potential_descendant_id
        visited = set()
        max_iterations = 10  # Safety limit
        iterations = 0

        while current_id and iterations < max_iterations:
            if current_id in visited:
                # Cycle detected
                return False
            visited.add(current_id)

            if current_id == ancestor_id:
                return True

            result = await session.execute(
                select(Department.parent_department_id).where(
                    Department.id == current_id,
                )
            )
            parent_id = result.scalar_one_or_none()
            if parent_id is None:
                break
            current_id = parent_id
            iterations += 1

        return False

    async def _save_pack_activation_audit(
        self,
        result: PackActivationResult,
    ) -> None:
        """Persist a PackActivationAuditLog row for R2 compliance.

        Args:
            result: Pack activation result to audit
        """
        async with self.db_manager.get_session() as session:
            log = PackActivationAuditLog(
                tenant_id=self.tenant_context.tenant_id,
                pack_id=result.pack_id,
                pack_name=result.pack_name,
                confidence=result.confidence,
                match_reason=result.match_reason,
                input_signals=result.input_signals,
                score_breakdown=result.score_breakdown,
                activated_automatically=result.activated_automatically,
            )
            session.add(log)
            await session.commit()

    async def _trigger_pack_activation(
        self,
        department: Department,
        company: Company,
    ) -> None:
        """Score all packs for the department and persist audit logs (R2).

        Args:
            department: Department to score packs for
            company: Parent company with sector/type info
        """
        # Build activation signals from department and company
        signals = ActivationSignals(
            department_name=department.name,
            company_type=getattr(company, "company_type", None) or "",
            sector=getattr(company, "sector", None) or "",
            board_role=getattr(department, "board_role", None),
            domain_pack_ids=getattr(department, "domain_pack_ids", []) or [],
        )

        # Use real packs from registry if available
        available_packs: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if self._pack_registry is not None:
            # Try async method first, fall back to sync
            if hasattr(self._pack_registry, "get_active_packs"):
                available_packs = await self._pack_registry.get_active_packs(
                    tenant_id=self.tenant_context.tenant_id
                )
            elif hasattr(self._pack_registry, "get_active_packs_sync"):
                available_packs = self._pack_registry.get_active_packs_sync(
                    tenant_id=self.tenant_context.tenant_id
                )

        # Score all packs
        scorer = PackActivationScorer()
        results = scorer.score_all_packs(
            available_packs,
            signals,
            company_id=str(company.id),
            department_id=str(department.id),
        )

        # Persist audit logs for each result
        for pack_score in results:
            # Convert PackScore to PackActivationResult for audit
            result = PackActivationResult(
                pack_id=pack_score.pack_id,
                pack_name=pack_score.pack_name,
                confidence=pack_score.score,
                match_reason="; ".join(pack_score.reasons),
                input_signals=pack_score.input_signals,
                score_breakdown={
                    "total_score": pack_score.score,
                },
                audit_log_id=uuid.uuid4(),
                activated_automatically=pack_score.activated_automatically,
            )
            await self._save_pack_activation_audit(result)

    async def _activate_packs_for_department(
        self,
        session: AsyncSession,
        department: Department,
        company: Company,
    ) -> None:
        """Activate packs for a department based on scoring (R2).

        Golden Rule R2: Every activation has explainable match with audit trail.

        Args:
            session: Database session
            department: Department to activate packs for
            company: Parent company with type/sector info
        """
        try:
            # Build activation signals
            signals = ActivationSignals(
                department_name=department.name,
                company_type=company.company_type,
                sector=company.sector,
                board_role=getattr(department, "board_role", None),
                domain_pack_ids=getattr(department, "domain_pack_ids", []),
            )

            # Use real packs from registry if available, else signal-only scoring
            available_packs: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            if self._pack_registry is not None:
                available_packs = await self._pack_registry.get_active_packs(
                    tenant_id=self.tenant_context.tenant_id
                )

            if not available_packs:
                return  # No packs to activate

            # Score all packs
            scorer = PackActivationScorer()
            pack_scores = scorer.score_all_packs(
                available_packs,
                signals,
                company_id=str(company.id),
                department_id=str(department.id),
            )

            # Auto-activate packs with HIGH+ confidence (score >= 0.70)
            activated_packs: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for pack_score in pack_scores:
                # Create audit log entry (Golden Rule R2)
                audit_log = PackActivationAuditLog(
                    tenant_id=department.tenant_id,
                    company_id=company.id,
                    department_id=department.id,
                    pack_id=pack_score.pack_id,
                    pack_name=pack_score.pack_name,
                    score=pack_score.score,
                    confidence=pack_score.confidence,
                    match_reason="; ".join(pack_score.reasons),
                    input_signals={
                        "department_name": signals.department_name,
                        "company_type": signals.company_type,
                        "sector": signals.sector,
                    },
                    score_breakdown={
                        "total_score": pack_score.score,
                        "matched_signals": pack_score.input_signals,
                    },
                    activated_automatically=pack_score.activated_automatically,
                )
                session.add(audit_log)

                # Auto-activate if score >= 0.70
                if pack_score.activated_automatically:
                    activated_packs.append(pack_score.pack_id)
                    # Record pack activation metric
                    try:
                        record_pack_activation(
                            department_id=str(department.id),
                            pack_id=pack_score.pack_id,
                            trigger="auto",
                        )
                    except Exception:
                        pass  # Metrics should not break business logic

            # Update department with activated packs
            if activated_packs:
                # Get current packs and add new ones
                current_packs = set(department.domain_pack_ids or [])
                current_packs.update(activated_packs)
                department.domain_pack_ids = list(current_packs)

                await session.commit()

        except Exception:
            # Log error but don't fail department creation
            # Pack activation is best-effort
            await session.rollback()

    async def _get_available_packs(
        self,
        session: AsyncSession,
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Get all available domain packs for scoring.

        Args:
            session: Database session

        Returns: List[Any] of DomainPack-like objects  # TODO(TYPE): replace Any with concrete type
        """
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant context required")

        if self._pack_registry is not None:
            active_packs = await self._pack_registry.get_active_packs(tenant_id=tenant_id)
            return list(active_packs)
        from src.core.procedures.domain_pack_repository import DomainPackRepository

        repo = DomainPackRepository(session)
        domain_packs = await repo.list_by_tenant(tenant_id)
        return list(domain_packs)

    def _build_tree(
        self,
        dept_dict: dict[uuid.UUID, DepartmentResponse],
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Build tree structure from flat department list.

        Args:
            dept_dict: Dict[str, Any]ionary of departments by ID  # TODO(TYPE): replace Any with concrete type

        Returns:
            Tree structure with children nested
        """
        # Create lookup by parent
        children_by_parent: dict[uuid.UUID | None, list[uuid.UUID]] = {}
        for dept_id, dept in dept_dict.items():
            parent_id = dept.parent_department_id
            if parent_id not in children_by_parent:
                children_by_parent[parent_id] = []
            children_by_parent[parent_id].append(dept_id)

        # Build tree recursively
        def build_subtree(parent_id: uuid.UUID | None) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
            children = children_by_parent.get(parent_id, [])
            result: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for child_id in children:
                dept = dept_dict[child_id]
                node = {
                    "id": str(dept.id),
                    "name": dept.name,
                    "board_role": dept.board_role,
                    "children": build_subtree(child_id),
                }
                result.append(node)
            return result

        # Get root departments (no parent or parent not in this company)
        root_depts = [
            dept_id
            for dept_id, dept in dept_dict.items()
            if dept.parent_department_id is None or dept.parent_department_id not in dept_dict
        ]

        return {
            "roots": [str(did) for did in root_depts],
            "tree": build_subtree(None),
        }
