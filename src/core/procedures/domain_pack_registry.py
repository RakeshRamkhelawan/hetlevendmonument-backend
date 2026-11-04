"""Domain Pack Registry - Service layer for pack and procedure discovery."""

from __future__ import annotations

import logging
from typing import Any

from cachetools import TTLCache

logger = logging.getLogger(__name__)


class _RepositoryFacade:
    """
    Facade exposing methods tests expect to mock on _repository.
    This bridges the gap between test mocks and actual repositories.
    """

    def __init__(
        self,
        domain_pack_repo: Any,  # TODO(TYPE): replace Any with concrete type
        procedure_repo: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        # domain_pack_repo: DomainPackRepository or MagicMock (for tests)
        # procedure_repo: ProcedureMetadataRepository or MagicMock (for tests)
        self._domain_pack_repo = domain_pack_repo
        self._procedure_repo = procedure_repo

    async def get_domain_packs_by_tenant(
        self, tenant_id: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get all domain packs for tenant as dicts."""
        packs = await self._domain_pack_repo.list_by_tenant(tenant_id)
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "status": p.status,
                "tenant_id": str(p.tenant_id),
                "department": p.department,
                "version": p.version,
            }
            for p in packs
        ]

    async def get_procedures_by_tenant(
        self, tenant_id: int
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get all procedures for tenant as dicts."""
        procedures = await self._procedure_repo.list_by_tenant(tenant_id)
        return [
            {
                "id": str(p.id),
                "name": p.category,
                "intent_tags": p.intent_tags,
                "category": p.category,
                "domain_pack_id": str(p.domain_pack_id),
            }
            for p in procedures
        ]


class DomainPackRegistry:
    """Registry for domain packs and procedures available to a tenant."""

    def __init__(
        self,
        db_manager: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        *,
        domain_pack_repo: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        procedure_repo: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        cache_ttl_minutes: float = 5.0,
    ) -> None:
        """
        Initialize DomainPackRegistry.

        Args:
            db_manager: Database manager (backward compatibility)
            domain_pack_repo: DomainPackRepository instance (DI)
            procedure_repo: ProcedureMetadataRepository instance (DI)
            cache_ttl_minutes: Cache TTL in minutes
        """
        # Initialize repositories (DI pattern)
        if domain_pack_repo is not None and procedure_repo is not None:
            self._domain_pack_repo = domain_pack_repo
            self._procedure_repo = procedure_repo
        elif db_manager is not None:
            # Backward compatibility: tests use this path with MagicMock
            self._db_manager = db_manager
            self._domain_pack_repo = db_manager  # Will be mocked
            self._procedure_repo = db_manager  # Will be mocked
        else:
            # For tests that only mock _repository after instantiation
            self._db_manager = None
            self._domain_pack_repo = None
            self._procedure_repo = None

        # Cache with TTL and size limit. Sleutel is _get_cache_key() -> str, waarde is
        # dezelfde vorm die get_active_packs() teruggeeft.
        # TODO(TYPE): replace Any with concrete type
        self._cache: TTLCache[str, list[dict[str, Any]]] = TTLCache[str, list[dict[str, Any]]](
            maxsize=1000, ttl=cache_ttl_minutes * 60
        )

        # Repository facade for test mocking (lazy init if repos are None)
        self._repository: _RepositoryFacade | None
        if self._domain_pack_repo is not None and self._procedure_repo is not None:
            self._repository = _RepositoryFacade(
                self._domain_pack_repo,
                self._procedure_repo,
            )
        else:
            # Will be mocked by tests
            self._repository = None

        logger.info(f"DomainPackRegistry initialized (cache_ttl={cache_ttl_minutes}min)")

    def _get_cache_key(self, tenant_id: int, method: str) -> str:
        """Generate cache key for tenant + method combination."""
        return f"{method}:{str(tenant_id)}"

    def _normalize_tenant_id(self, tenant_id: int | str) -> int:
        """Normalize tenant_id to int -- de canonieke vorm in deze codebase.

        Bewijs dat int de juiste vorm is (2026-08-01, uitputtend nagetrokken):
        - ALLE 21 `tenant_id: Mapped[...]`-kolommen in de modellen zijn `Mapped[int]`;
          geen enkele is een UUID. `DomainPack.tenant_id` incluis.
        - `DomainPackRepository.list_by_tenant` neemt een `int`.
        - Beide productie-aanroepers geven een int: de health-check
          (`health_endpoints.py`, `tenant_id=1`) en `department_service`
          (`tenant_context.tenant_id`).
        - Platformconventie ADR-005.

        Historie, zodat niemand dit nog eens omdraait:
        tot 2026-07-31 accepteerde deze functie UITSLUITEND UUID/str en gooide een
        TypeError op een int -- de health-check van de registry faalde daardoor altijd.
        Bij het repareren daarvan koos ik voor int-only, wat 11 tests brak in
        tests/unit/procedures/test_domain_pack_registry.py (480 regels, `uuid4()`-tenants).
        Tijdelijk accepteerde de functie daarna beide vormen. Die testsuite is op
        2026-08-01 gemigreerd naar int-tenants -- de UUID's daar waren een fictie: ze
        draaiden tegen een GEMOCKTE repository en zouden tegen een echte repository stil
        nul rijen opleveren, want de kolom is `Integer`.

        Een UUID levert nu dus een expliciete TypeError op in plaats van een stil lege
        lijst. Afgedwongen door tests/architecture/test_tenant_id_type_matches_model.py,
        die het geaccepteerde type koppelt aan het kolomtype in het model.
        """
        if isinstance(tenant_id, bool):
            # bool is een subclass van int; expliciet weigeren voorkomt True -> 1.
            raise TypeError(f"tenant_id must be int or numeric str, got {type(tenant_id)}")
        if isinstance(tenant_id, int):
            return tenant_id
        if isinstance(tenant_id, str) and tenant_id.isdigit():
            return int(tenant_id)
        raise TypeError(f"tenant_id must be int or numeric str, got {type(tenant_id)!r}")

    async def get_active_packs(
        self, tenant_id: int | str
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Fetch all active domain packs for a tenant."""
        tenant_key = self._normalize_tenant_id(tenant_id)

        # Check cache
        cache_key = self._get_cache_key(tenant_key, "active_packs")
        cached = self._cache.get(cache_key)
        if isinstance(cached, list):
            logger.debug(f"Cache hit: {cache_key}")
            return cached

        logger.debug(f"Cache miss: {cache_key}")

        # Fetch from repository via facade
        if self._repository is None:
            raise RuntimeError("Repository not initialized")
        all_packs = await self._repository.get_domain_packs_by_tenant(tenant_key)

        # Defense in depth: filter by status AND tenant_id
        active_packs = [
            p
            for p in all_packs
            if p.get("status") == "active" and str(p.get("tenant_id")) == str(tenant_key)
        ]

        logger.info(f"Found {len(active_packs)} active packs for tenant {tenant_key}")

        # Cache result
        self._cache[cache_key] = active_packs

        return active_packs

    async def find_candidates_by_tag(
        self,
        intent: str,
        tenant_id: int | str,
        domain_filter: str | None = None,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Find procedures matching intent tags."""
        tenant_key = self._normalize_tenant_id(tenant_id)

        logger.info(f"Finding candidates for intent '{intent}' (tenant={tenant_key})")

        # Fetch procedures via facade
        if self._repository is None:
            raise RuntimeError("Repository not initialized")
        procedures = await self._repository.get_procedures_by_tenant(tenant_key)

        # Parse intent for keywords
        keywords = set(intent.lower().split())

        # Filter and match
        candidates = []
        for proc in procedures:
            # Domain filter
            if domain_filter:
                proc_category = proc.get("category", "").lower()
                if proc_category != domain_filter.lower():
                    continue

            # Tag matching
            intent_tags = [t.lower() for t in proc.get("intent_tags", [])]
            if any(keyword in tag for keyword in keywords for tag in intent_tags):
                candidates.append(proc)
                continue

            # Name matching
            proc_name = proc.get("name", "").lower()
            if any(keyword in proc_name for keyword in keywords):
                candidates.append(proc)

        logger.info(f"Found {len(candidates)} candidates")
        return candidates
