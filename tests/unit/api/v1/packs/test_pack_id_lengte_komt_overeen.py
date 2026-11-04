"""De lengtegrens van een `pack_id` in de API is dezelfde als in de database (pakket aanzetten, dag 1).

`src/core/api/v1/packs/schemas.py` kent de grens als vaste waarde (de API-laag importeert het model niet,
anders telt de fan-out-meting van `core_api` een paar meer); deze test koppelt hem aan de kolomlengte en
de CHECK-constraint van `tenant_pack_activations`, zodat ze niet uit elkaar kunnen lopen.
"""

from src.core.api.v1.packs.schemas import PACK_ID_MAX_LENGTE as API_GRENS
from src.core.models.tenant_pack_activation_models import (
    PACK_ID_MAX_LENGTE as DATABASE_GRENS,
    TenantPackActivation,
)


def test_de_api_grens_is_de_kolomlengte() -> None:
    assert API_GRENS == DATABASE_GRENS


def test_de_api_grens_is_de_lengte_van_de_kolom() -> None:
    assert TenantPackActivation.__table__.c.pack_id.type.length == API_GRENS  # type: ignore[attr-defined]


def test_de_check_constraint_noemt_dezelfde_grens() -> None:
    teksten = [
        str(c.sqltext) for c in TenantPackActivation.__table__.constraints if hasattr(c, "sqltext")
    ]

    assert any(f"BETWEEN 1 AND {API_GRENS}" in tekst for tekst in teksten)
