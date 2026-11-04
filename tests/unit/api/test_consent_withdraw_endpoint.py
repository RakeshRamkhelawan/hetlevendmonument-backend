"""POST /api/v1/privacy/consent/withdraw daadwerkelijk aanroepen (ADR-036 OP-73).

**Waarom een echte TestClient-test en geen dict-op-zichzelf-assertie.**
`tests/unit/test_privacy_endpoints.py::TestConsentManagement` toetst voor de bestaande
consent-endpoints alleen losse dict-literalen tegen zichzelf -- de router wordt daar
NERGENS aangeroepen (zelfde "vacuum groen"-patroon als BE-AGT-045). Deze test bouwt in
plaats daarvan een minimale app met de echte `consent_router`, naar het patroon van
`tests/unit/test_p0_d1_d2_stub_endpoints.py::_make_rag_client` (FastAPI() + include_router +
dependency_overrides + TestClient).

`get_lawful_basis_registry` wordt NIET overriden: de echte, module-level singleton uit
`src.core.governance.dependencies` is gebruikt, en die registreert
`/api/v1/privacy/consent/withdraw` inmiddels echt (zie die module) -- dit test dus ook dat
de registratie klopt, niet alleen dat de route bestaat.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.privacy.consent_router import consent_router
from src.core.api.v1.privacy.dependencies import get_current_user, get_db
from src.core.governance.cookie_consent import ConsentPreferences


def _make_client() -> tuple[TestClient, MagicMock]:
    """Bouw een minimale app met de echte consent_router en een gemockte CookieConsentManager."""
    app = FastAPI()
    app.include_router(consent_router, prefix="/api/v1/privacy")

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.tenant_id = 42

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: MagicMock()

    return TestClient(app, raise_server_exceptions=False), mock_user


@pytest.mark.unit
def test_consent_withdraw_calls_update_consent_with_everything_disabled() -> None:
    """De route roept update_consent aan met analytics/marketing/personalization=False.

    Controleert de AANROEP-ARGUMENTEN, niet alleen dat de mock werd aangeroepen (testing.md:
    "Never assert a mock was called without checking its arguments").
    """
    client, mock_user = _make_client()

    fake_result = ConsentPreferences(
        essential=True,
        analytics=False,
        marketing=False,
        personalization=False,
        timestamp=datetime.now(timezone.utc),
        policy_version="1.0",
    )
    mock_manager = MagicMock()
    mock_manager.update_consent = AsyncMock(return_value=fake_result)

    with patch(
        "src.core.api.v1.privacy.consent_router.CookieConsentManager",
        return_value=mock_manager,
    ):
        response = client.post("/api/v1/privacy/consent/withdraw")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["essential"] is True
    assert body["analytics"] is False
    assert body["marketing"] is False
    assert body["personalization"] is False

    mock_manager.update_consent.assert_called_once_with(
        user_id=str(mock_user.id),
        tenant_id=mock_user.tenant_id,
        preferences={"analytics": False, "marketing": False, "personalization": False},
        policy_version="1.0",
    )


@pytest.mark.unit
def test_consent_withdraw_returns_500_on_manager_failure() -> None:
    """Onverwachte fout in update_consent -> 500, niet een onbehandelde exceptie."""
    client, _mock_user = _make_client()

    mock_manager = MagicMock()
    mock_manager.update_consent = AsyncMock(side_effect=RuntimeError("db weg"))

    with patch(
        "src.core.api.v1.privacy.consent_router.CookieConsentManager",
        return_value=mock_manager,
    ):
        response = client.post("/api/v1/privacy/consent/withdraw")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to withdraw consent"
