"""Een MEETHARNAS: de echte bonnen-route zonder database en zonder echte login (bonlezer dag 3).

Alleen voor `scripts/bonlezer/meet_upload.sh`, in een container op een intern netwerk zonder gepubliceerde
poort. De route, de opslag, de verzending naar de worker en het ophalen van het resultaat zijn de ECHTE
code (`src/core/api/v1/bonnen`, `src/core/als/bonlezer`); alleen de login en de database zijn vervangen:

- de login (`get_current_user`) en de rechtentoets (`_toets_read`, `_toets_write`) zijn vervangen; de
  gebruiker wordt gekozen met de header `X-Test-Tenant` (zodat tenant A en tenant B naast elkaar kunnen).
  De afhankelijkheid `require_receipts_*` die de gebruiker voor de snelheidsbegrenzing op het verzoek zet
  is wel ECHT;
- `get_db` geeft een nepsessie, waardoor de auditregel stil wordt overgeslagen (`best_effort`);
- `TESTING=1` (gezet door `meet_upload.sh`): `_resolve_tenant_id` valt dan terug op de tenant van de
  gebruiker in plaats van op de context die de echte `TenantMiddleware` uit de JWT zet. Die
  middleware en het controleren van een JWT zijn dus NIET gemeten; dat doen de HR-integratietests
  voor hetzelfde patroon.

Dit is GEEN voorbeeld voor productie: een header die de tenant bepaalt is precies wat de applicatie nooit
doet. Het staat daarom hier en niet onder `src/`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

from fastapi import FastAPI, Request

from src.core.api.v1.bonnen.dependencies import (
    UserResponse,
    _toets_read,
    _toets_write,
    get_current_user,
    get_db,
)
from src.core.api.v1.bonnen.router import router
from src.core.exceptions.handlers import register_exception_handlers


def _gebruiker(request: Request) -> UserResponse:
    tenant = int(request.headers["x-test-tenant"])
    return UserResponse(
        id=100 + tenant, email="meting@example.test", tenant_id=tenant, roles=["user"]
    )


async def _nepsessie() -> AsyncGenerator[AsyncMock, None]:
    yield AsyncMock()


app = FastAPI()
register_exception_handlers(app)
app.include_router(router)
app.dependency_overrides[get_db] = _nepsessie
app.dependency_overrides[get_current_user] = _gebruiker
app.dependency_overrides[_toets_read] = lambda: 1
app.dependency_overrides[_toets_write] = lambda: 1
