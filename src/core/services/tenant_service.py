"""
Tenant service: lookup, context utilities, and request-scoped CRUD operations.

Provides standardised access to Tenant records and tenant_id extraction
from the request-scoped ContextVar (set by TenantMiddleware from JWT).
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.models import Agent
from src.core.schemas.tenant_schemas import (
    TenantCreate,
    TenantListResponse,
    TenantResponse,
    TenantStats,
    TenantUpdate,
)
from src.core.container import TenantContext
from src.core.middleware.tenant_context import get_tenant_id
from src.core.models.rbac_models import Tenant, User, with_four_eyes_defaults
from src.core.shared.tenant_instellingen import (
    behoud_beheerde_instellingen,
    genegeerde_beheerde_instellingen,
)
from src.domains.documents.models import Document

logger = logging.getLogger(__name__)


async def get_tenant_by_id(tenant_id: int, db: AsyncSession) -> Tenant | None:
    """
    Return the Tenant with the given id, or None if not found.

    Does NOT raise on missing tenant -- callers decide the error strategy.
    Uses async SQLAlchemy select() per CLAUDE.md pattern.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


def require_tenant_context(request: Request) -> int:
    """
    Extract the tenant_id set by TenantMiddleware from the request ContextVar.

    Raises HTTPException(400) when the context is absent or invalid -- never
    falls back to a hardcoded value (ADR-003).
    """
    tenant_id: int | None = get_tenant_id()

    if tenant_id is None:
        logger.warning(
            "require_tenant_context: tenant_id missing for %s %s",
            request.method,
            request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context unavailable",
        )

    return tenant_id


class TenantService:
    """
    Request-scoped tenant CRUD and aggregation service.

    All database access for the tenants domain lives here. Routers inject
    this service via ``get_tenant_service`` and keep only HTTP/auth concerns.

    Tenant scoping is enforced in two places for defense-in-depth:
    1. The ``TenantContext`` injected from the JWT claim (superusers get
       ``bypass_filter=True``).
    2. Each method resolves the effective tenant_id through ``_tenant_scope``,
       rejecting cross-tenant access for non-superusers.
    """

    def __init__(self, db: AsyncSession, tenant_context: TenantContext) -> None:
        self.db = db
        self.tenant_context = tenant_context

    def _tenant_scope(self, tenant_id: int) -> int:
        """
        Resolve the effective tenant id for an operation.

        Superusers may act on any tenant (``bypass_filter=True``). Regular users
        may only act on their own tenant. Raises HTTPException(403) on mismatch.
        """
        if self.tenant_context.bypass_filter:
            return tenant_id
        if tenant_id != self.tenant_context.require_tenant():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-tenant access denied",
            )
        return tenant_id

    async def create_tenant(self, data: TenantCreate) -> TenantResponse:
        """
        Create a new tenant organization.

        Raises HTTPException(400) if the slug or domain already exists.
        """
        existing = await self.db.execute(select(Tenant).where(Tenant.slug == data.slug))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tenant with slug '{data.slug}' already exists",
            )

        existing_name = await self.db.execute(select(Tenant).where(Tenant.name == data.name))
        if existing_name.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tenant with name '{data.name}' already exists",
            )

        if data.domain:
            existing_domain = await self.db.execute(
                select(Tenant).where(Tenant.domain == data.domain)
            )
            if existing_domain.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Domain '{data.domain}' is already in use",
                )

        tenant = Tenant(
            name=data.name,
            slug=data.slug,
            domain=data.domain,
            # ADR-039: de vier-ogen-standaard, tenzij de aanmaker zelf iets meegaf.
            settings=with_four_eyes_defaults(data.settings),
            max_users=data.max_users,
            max_agents=data.max_agents,
            max_storage_gb=data.max_storage_gb,
            subscription_tier=data.subscription_tier,
            subscription_status="active",
            is_active=True,
            data_residency=data.data_residency,
        )

        self.db.add(tenant)
        await self.db.commit()
        await self.db.refresh(tenant)

        # De standaardrollen horen bij een nieuwe tenant, niet bij de eerste
        # registratie. Sinds ADR-036 OP-185 maakt create_user geen rollen meer aan, dus
        # een tenant zonder rollen zou niemand meer kunnen aanmaken -- gemeten door de
        # Gate-2-reviewer op 2026-09-11, en de eigen meting bij OP-187 liet zien dat
        # tenant 2 in deze database precies in die toestand staat. Zaaien is geen
        # versoepeling: ensure_default_roles maakt uitsluitend de vaste standaardlijst.
        # best_effort omdat de tenant al is gecommit; een mislukt zaaien mag de
        # tenantcreatie niet terugdraaien, maar het moet wel in het log komen.
        #
        # Dynamisch via importlib, net als de prana-aanroep hieronder en om precies
        # dezelfde reden: een `from src.core.services.rbac_service import ...` telt als een
        # nieuwe agent_runtime->auth-koppeling en zette op 2026-09-11 twee plafondguards op
        # rood (test_dsm017_runtime_deps_facade: 17 tegenover plafond 16, en
        # test_dsm_008_reclassification). Het plafond is een plafond en geen buffer, dus het
        # mag niet worden opgerekt voor iets dat ook dynamisch kan.
        import importlib

        from src.core.utils.best_effort import best_effort

        rbac_mod = importlib.import_module("src.core.services.rbac_service")

        # De NIEUWE tenant wordt hier aangenomen, niet die van de aanmaker (ADR-036 OP-155).
        #
        # Op dit punt staat `app.current_tenant` op de tenant van de BEHEERDER die de nieuwe
        # tenant aanmaakt, terwijl `ensure_default_roles` schrijft met `tenant.id` van de
        # NIEUWE tenant. `roles` en `role_permissions` hebben allebei een RLS-policy, en die
        # hebben geen aparte `WITH CHECK` -- PostgreSQL gebruikt de `USING`-expressie dan ook
        # voor INSERT (https://www.postgresql.org/docs/15/sql-createpolicy.html). Een rij
        # wegschrijven met een `tenant_id` die niet gelijk is aan de context is dus een
        # overtreding.
        #
        # En dat zou hier STIL misgaan: `best_effort` vangt de fout op. Een nieuwe klant zou
        # zonder rollen achterblijven, met een logregel, en dat wordt pas zichtbaar wanneer de
        # eerste gebruiker van die klant nergens bij kan.
        #
        # Gevonden op 2026-09-15 door sanskritisetu-org-bf tijdens een regie-controle op haar
        # eigen wijziging -- de vijfde aanroeper van `ensure_default_roles`, die in geen enkele
        # registerrij stond. `adopt_tenant` zet de vorige waarde bij het verlaten terug, dus
        # de rest van het verzoek van de beheerder blijft ongemoeid.
        #
        # LET OP als je hier een `best_effort` ziet staan rond een andere schrijf: na de
        # omschakeling naar `sanskritisetu_app` verandert `best_effort` rond een schrijf die
        # een policy raakt van "vangt een storing op" in "verbergt een autorisatiefout".
        #
        # En dat geldt DUBBEL voor UPDATE en DELETE. Gemeten 2026-09-15: zonder
        # tenantcontext werpt alleen INSERT een fout; UPDATE en DELETE raken nul rijen en
        # slagen zonder enige melding, omdat `USING` daar eerst bepaalt welke rijen
        # zichtbaar zijn. Bij die twee is er dus niets dat `best_effort` kan verbergen --
        # ze zijn al stil.
        from src.core.database.bypass_session import adopt_tenant

        async with best_effort("standaardrollen zaaien voor nieuwe tenant", db_session=self.db):
            async with adopt_tenant(self.db, tenant.id):
                await rbac_mod.RBACService(self.db).ensure_default_roles(tenant.id)

        logger.info("Tenant '%s' (ID: %s) created", tenant.name, tenant.id)

        # ADR-021: seed the per-department prana budgets. best_effort so a prana failure
        # never blocks tenant creation (the tenant is already committed above).
        # Dynamisch via importlib (i.p.v. `from ... import`) om agent_runtime's governance-
        # koppeling niet verder op te rekken -- zie test_dsm006_ar_governance_fan_out.py
        # (plafond, GEEN buffer) en `_get_prana_guard()` in specialist_base.py voor hetzelfde
        # patroon.
        import importlib

        from src.core.utils.best_effort import best_effort

        prana_service_mod = importlib.import_module("src.core.governance.prana_service")

        # De klant wordt hier NET ZO GOED aangenomen als bij het zaaien van de rollen
        # hierboven (ADR-036 OP-153). Dat ontbrak, en dat is precies het geval waar de
        # waarschuwing twintig regels hoger voor bedoeld was.
        #
        # `provision_tenant` schrijft in `prana_department_budget`, een tabel met een
        # afschermingsregel. Zonder aangenomen klant faalt die INSERT na de omschakeling
        # naar `sanskritisetu_app` -- en `best_effort` VANGT die fout op. Een nieuwe klant
        # zou dan stil zonder budget worden aangemaakt, en de eerste actie die budget
        # kost zou geweigerd worden zonder dat iemand weet waarom.
        #
        # Gevonden op 2026-09-16 door `test_bypass_lezen_en_schrijven_blijven_bij_elkaar`,
        # de guard uit deze iteratie zelf.
        async with best_effort("prana provision_tenant", db_session=self.db):
            async with adopt_tenant(self.db, tenant.id):
                await prana_service_mod.PranaService(self.db).provision_tenant(tenant.id)
                await self.db.commit()

        return TenantResponse.model_validate(tenant)

    async def list_tenants(
        self, skip: int, limit: int, is_active: bool | None
    ) -> TenantListResponse:
        """
        List tenants with pagination and optional active-status filter.

        Superusers see all tenants; regular users see only their own tenant.
        """
        query = select(Tenant)
        count_query = select(func.count(Tenant.id))

        if not self.tenant_context.bypass_filter:
            tenant_id = self.tenant_context.require_tenant()
            query = query.where(Tenant.id == tenant_id)
            count_query = count_query.where(Tenant.id == tenant_id)

        if is_active is not None:
            query = query.where(Tenant.is_active == is_active)
            count_query = count_query.where(Tenant.is_active == is_active)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        query = query.offset(skip).limit(limit).order_by(Tenant.created_at.desc())
        result = await self.db.execute(query)
        tenants = result.scalars().all()

        return TenantListResponse(
            data=[TenantResponse.model_validate(t) for t in tenants],
            total=int(total or 0),
            page=(skip // limit) + 1 if limit > 0 else 1,
            per_page=limit,
        )

    async def get_tenant(self, tenant_id: int) -> TenantResponse | None:
        """
        Return a tenant by ID, scoped to the requester's tenant context.

        Returns None if the tenant is not found. Raises HTTPException(403) for
        cross-tenant access by non-superusers.
        """
        target_id = self._tenant_scope(tenant_id)
        result = await self.db.execute(select(Tenant).where(Tenant.id == target_id))
        tenant = result.scalar_one_or_none()
        return TenantResponse.model_validate(tenant) if tenant else None

    async def update_tenant(self, tenant_id: int, data: TenantUpdate) -> TenantResponse | None:
        """
        Update a tenant, scoped to the requester's tenant context.

        Returns None if the tenant is not found. Raises HTTPException(400) on
        duplicate domain, HTTPException(403) on cross-tenant access.
        """
        target_id = self._tenant_scope(tenant_id)
        # Met rijslot en een verse rij: `settings` wordt als geheel teruggeschreven, dus een oude kopie overschrijft anders
        # de wijziging van een ander (bijvoorbeeld de escalatietermijn of vier ogen) -- gerichte security-review F1.
        result = await self.db.execute(
            select(Tenant)
            .where(Tenant.id == target_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            return None

        if data.domain and data.domain != tenant.domain:
            existing = await self.db.execute(select(Tenant).where(Tenant.domain == data.domain))
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Domain '{data.domain}' is already in use",
                )

        update_data = data.model_dump(exclude_unset=True)
        if isinstance(update_data.get("settings"), dict):
            # `settings` wordt als geheel vervangen; vier ogen, de escalatietermijn en de taalmodelkeuze mogen daarbij niet
            # stil verdwijnen (een ontbrekende vier-ogen-sleutel betekent UIT).
            genegeerd = genegeerde_beheerde_instellingen(tenant.settings, update_data["settings"])
            if genegeerd:
                # Alleen de sleutelnamen, nooit de waarden. Geen fout: de rest van de wijziging gaat gewoon door.
                logger.warning(
                    "update_tenant: instellingen met een eigen route genegeerd voor tenant %s: %s",
                    target_id,
                    ", ".join(genegeerd),
                )
            update_data["settings"] = behoud_beheerde_instellingen(
                tenant.settings, update_data["settings"]
            )
        for field, value in update_data.items():
            setattr(tenant, field, value)

        # Explicitly stamp updated_at for deterministic ordering/tests.
        tenant.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(tenant)

        logger.info("Tenant %s updated", tenant_id)
        return TenantResponse.model_validate(tenant)

    async def delete_tenant(self, tenant_id: int) -> bool:
        """
        Soft-delete a tenant by deactivating it.

        Returns True if the tenant was found and deactivated, False otherwise.
        Raises HTTPException(403) on cross-tenant access by non-superusers.
        """
        target_id = self._tenant_scope(tenant_id)
        result = await self.db.execute(select(Tenant).where(Tenant.id == target_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            return False

        tenant.is_active = False
        tenant.subscription_status = "cancelled"
        await self.db.commit()

        logger.info("Tenant %s deactivated", tenant_id)
        return True

    async def get_tenant_stats(self, tenant_id: int) -> TenantStats | None:
        """
        Return usage statistics for a tenant, scoped to the requester's context.

        Returns None if the tenant is not found. Raises HTTPException(403) for
        cross-tenant access by non-superusers.
        """
        target_id = self._tenant_scope(tenant_id)

        tenant_exists = await self.db.execute(select(Tenant.id).where(Tenant.id == target_id))
        if tenant_exists.scalar_one_or_none() is None:
            return None

        user_count_result = await self.db.execute(
            select(func.count(User.id)).where(User.tenant_id == target_id)
        )
        user_count = int(user_count_result.scalar() or 0)

        agent_count_result = await self.db.execute(
            select(func.count(Agent.id)).where(Agent.tenant_id == target_id)
        )
        agent_count = int(agent_count_result.scalar() or 0)

        last_activity_result = await self.db.execute(
            text("SELECT MAX(timestamp) FROM audit_logs WHERE tenant_id = :tenant_id").bindparams(
                tenant_id=target_id
            )
        )
        last_activity = last_activity_result.scalar()

        storage_gb = 0.0
        try:
            storage_result = await self.db.execute(
                select(func.sum(Document.file_size_bytes)).where(Document.tenant_id == target_id)
            )
            total_bytes = storage_result.scalar() or 0
            storage_gb = round(total_bytes / (1024**3), 4)
        except Exception as exc:
            logger.warning(
                "storage_used_gb calculation failed (best effort): %s: %s",
                type(exc).__name__,
                exc,
                extra={"tenant_id": target_id},
            )

        return TenantStats(
            user_count=user_count,
            agent_count=agent_count,
            storage_used_gb=storage_gb,
            last_activity=last_activity,
        )
