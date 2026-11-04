"""SP-API-010: router.py bestanden mogen geen verboden directe imports bevatten.

ADR-033 Contract 1 uitbreiding: src.core.services, src.core.ml, src.core.als,
src.core.semantic_router toegevoegd aan forbidden_modules. Alle 14 violations
moeten via dependencies.py gefaciliteerd worden.

RED: tests falen zolang de imports nog in router.py zitten.
GREEN: na verplaatsing naar dependencies.py.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).parent.parent.parent


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


class TestRouterBoundaryADR033:
    """Bewijst dat alle verboden imports uit router.py bestanden zijn."""

    # ------------------------------------------------------------------
    # auth/router.py -- database (3 violations)
    # ------------------------------------------------------------------

    def test_auth_router_no_database_database_import(self) -> None:
        """auth/router.py mag src.core.database.database niet direct importeren."""
        src = _src("src/core/api/auth/router.py")
        assert "from src.core.database.database import" not in src, (
            "Verboden: auth/router.py importeert direct src.core.database.database. "
            "Verplaats naar src/core/api/auth/dependencies.py."
        )

    def test_auth_router_no_database_redis_import(self) -> None:
        """auth/router.py mag src.core.database.redis niet direct importeren."""
        src = _src("src/core/api/auth/router.py")
        assert "from src.core.database.redis import" not in src, (
            "Verboden: auth/router.py importeert direct src.core.database.redis. "
            "Verplaats naar src/core/api/auth/dependencies.py."
        )

    def test_auth_router_no_database_tenant_filter_import(self) -> None:
        """auth/router.py mag src.core.database.tenant_query_filter niet direct importeren."""
        src = _src("src/core/api/auth/router.py")
        assert "from src.core.database.tenant_query_filter import" not in src, (
            "Verboden: auth/router.py importeert direct src.core.database.tenant_query_filter. "
            "Verplaats naar src/core/api/auth/dependencies.py."
        )

    # ------------------------------------------------------------------
    # auth/router.py -- services (3 violations)
    # ------------------------------------------------------------------

    def test_auth_router_no_audit_service_import(self) -> None:
        """auth/router.py mag de audit-service niet direct importeren.

        ADR-036 OP-197: deze assertie noemde tot 2026-09-02 `src.core.services.audit_service`,
        en die module BESTAAT NIET (gemeten: geen bestand op dat pad, en de naam staat niet in
        `src/core/services/__init__.py`). De assertie kon dus nooit falen, ook niet als
        `auth/router.py` de audit-service morgen wel direct zou importeren. De service leeft op
        TWEE plaatsen -- `src/core/audit/audit_service.py` en
        `src/core/governance/services/audit_service.py` -- en beide worden nu genoemd.
        Nagemeten dat `auth/router.py` vandaag niets audit-gerelateerds importeert (hij
        importeert alleen fastapi en zijn eigen buurmodules), dus deze test is groen.
        """
        src = _src("src/core/api/auth/router.py")
        verboden = (
            "from src.core.audit.audit_service import",
            "from src.core.governance.services.audit_service import",
        )
        aangetroffen = [pad for pad in verboden if pad in src]
        assert not aangetroffen, (
            f"Verboden: auth/router.py importeert direct de audit-service ({aangetroffen}). "
            "Verplaats naar src/core/api/auth/dependencies.py."
        )

    def test_auth_router_no_email_import(self) -> None:
        """auth/router.py mag src.core.services.email niet direct importeren."""
        src = _src("src/core/api/auth/router.py")
        assert "from src.core.services.email import" not in src, (
            "Verboden: auth/router.py importeert direct src.core.services.email. "
            "Verplaats naar src/core/api/auth/dependencies.py."
        )

    def test_auth_router_no_rbac_service_import(self) -> None:
        """auth/router.py mag src.core.services.rbac_service niet direct importeren."""
        src = _src("src/core/api/auth/router.py")
        assert "from src.core.services.rbac_service import" not in src, (
            "Verboden: auth/router.py importeert direct src.core.services.rbac_service. "
            "Verplaats naar src/core/api/auth/dependencies.py."
        )

    # ------------------------------------------------------------------
    # v1/collaboration/router.py (1 violation)
    # ------------------------------------------------------------------

    def test_collaboration_router_no_direct_services_import(self) -> None:
        """v1/collaboration/router.py mag src.core.services.* niet direct importeren."""
        src = _src("src/core/api/v1/collaboration/router.py")
        assert "from src.core.services.collaboration_service import" not in src, (
            "Verboden: collaboration/router.py importeert direct src.core.services. "
            "Verplaats naar v1/collaboration/dependencies.py."
        )

    # ------------------------------------------------------------------
    # v1/gamification/router.py (1 violation)
    # ------------------------------------------------------------------

    def test_gamification_router_no_direct_services_import(self) -> None:
        """v1/gamification/router.py mag src.core.services.* niet direct importeren."""
        src = _src("src/core/api/v1/gamification/router.py")
        assert "from src.core.services.gamification_service import" not in src, (
            "Verboden: gamification/router.py importeert direct src.core.services. "
            "Verplaats naar v1/gamification/dependencies.py."
        )

    # ------------------------------------------------------------------
    # v1/personas/router.py (1 violation)
    # ------------------------------------------------------------------

    def test_personas_router_no_direct_services_import(self) -> None:
        """v1/personas/router.py mag src.core.services.* niet direct importeren."""
        src = _src("src/core/api/v1/personas/router.py")
        assert "from src.core.services.persona_service import" not in src, (
            "Verboden: personas/router.py importeert direct src.core.services. "
            "Verplaats naar v1/personas/dependencies.py."
        )

    # ------------------------------------------------------------------
    # v1/tenant_custom_data/router.py (2 violations)
    # ------------------------------------------------------------------

    def test_tenant_custom_data_router_no_direct_services_import(self) -> None:
        """v1/tenant_custom_data/router.py mag src.core.services.* niet direct importeren."""
        src = _src("src/core/api/v1/tenant_custom_data/router.py")
        assert "from src.core.services." not in src, (
            "Verboden: tenant_custom_data/router.py importeert direct src.core.services. "
            "Verplaats naar v1/tenant_custom_data/dependencies.py."
        )

    # ------------------------------------------------------------------
    # v1/ml/router.py (1 violation)
    # ------------------------------------------------------------------

    def test_ml_router_no_direct_ml_import(self) -> None:
        """v1/ml/router.py mag src.core.ml.* niet direct importeren."""
        src = _src("src/core/api/v1/ml/router.py")
        assert "from src.core.ml.tool_predictor import" not in src, (
            "Verboden: ml/router.py importeert direct src.core.ml.tool_predictor. "
            "Verplaats naar v1/ml/dependencies.py."
        )

    # ------------------------------------------------------------------
    # v1/routing/router.py (2 violations)
    # ------------------------------------------------------------------

    def test_routing_router_no_direct_als_import(self) -> None:
        """v1/routing/router.py mag src.core.als.* niet direct importeren."""
        src = _src("src/core/api/v1/routing/router.py")
        assert "from src.core.als." not in src, (
            "Verboden: routing/router.py importeert direct src.core.als.*. "
            "Verplaats naar v1/routing/dependencies.py."
        )

    def test_routing_router_no_direct_semantic_router_import(self) -> None:
        """v1/routing/router.py mag src.core.semantic_router.* niet direct importeren."""
        src = _src("src/core/api/v1/routing/router.py")
        assert "from src.core.semantic_router." not in src, (
            "Verboden: routing/router.py importeert direct src.core.semantic_router.*. "
            "Verplaats naar v1/routing/dependencies.py."
        )

    # ==================================================================
    # Positieve facade-aanwezigheidstests (FA-004 -- SP-API-010 minor)
    # Elke router moet actief iets importeren uit zijn eigen dependencies.py.
    # ==================================================================

    def test_auth_router_uses_dependencies_facade(self) -> None:
        """auth/router.py moet importeren via .dependencies (ADR-033 Laag 1)."""
        src = _src("src/core/api/auth/router.py")
        assert "from .dependencies import" in src, (
            "auth/router.py importeert niets uit .dependencies -- facade is verbroken."
        )

    def test_collaboration_router_uses_dependencies_facade(self) -> None:
        """v1/collaboration/router.py moet importeren via .dependencies."""
        src = _src("src/core/api/v1/collaboration/router.py")
        assert "from .dependencies import" in src, (
            "collaboration/router.py importeert niets uit .dependencies -- facade is verbroken."
        )

    def test_gamification_router_uses_dependencies_facade(self) -> None:
        """v1/gamification/router.py moet importeren via .dependencies."""
        src = _src("src/core/api/v1/gamification/router.py")
        assert "from .dependencies import" in src, (
            "gamification/router.py importeert niets uit .dependencies -- facade is verbroken."
        )

    def test_personas_router_uses_dependencies_facade(self) -> None:
        """v1/personas/router.py moet importeren via .dependencies."""
        src = _src("src/core/api/v1/personas/router.py")
        assert "from .dependencies import" in src, (
            "personas/router.py importeert niets uit .dependencies -- facade is verbroken."
        )

    def test_tenant_custom_data_router_uses_dependencies_facade(self) -> None:
        """v1/tenant_custom_data/router.py moet importeren via .dependencies."""
        src = _src("src/core/api/v1/tenant_custom_data/router.py")
        assert "from .dependencies import" in src, (
            "tenant_custom_data/router.py importeert niets uit .dependencies -- facade is verbroken."
        )

    def test_ml_router_uses_dependencies_facade(self) -> None:
        """v1/ml/router.py moet importeren via .dependencies."""
        src = _src("src/core/api/v1/ml/router.py")
        assert "from .dependencies import" in src, (
            "ml/router.py importeert niets uit .dependencies -- facade is verbroken."
        )

    def test_routing_router_uses_dependencies_facade(self) -> None:
        """v1/routing/router.py moet Department importeren via .dependencies."""
        src = _src("src/core/api/v1/routing/router.py")
        assert "from .dependencies import Department" in src, (
            "routing/router.py importeert Department niet via .dependencies -- facade is verbroken."
        )
