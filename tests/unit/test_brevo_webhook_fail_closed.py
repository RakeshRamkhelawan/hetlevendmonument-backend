"""BE-SEC-055: Brevo-webhook is fail-closed zonder geconfigureerd secret.

Rood-bewijs: voor de fix gaf `_verify_webhook_secret` bij een ontbrekend of
leeg `brevo_webhook_secret` stilletjes toestemming (`return` zonder check) --
het endpoint was dan publiek vervalsbaar (bounce/unsubscribe van willekeurige
e-mailadressen). Deze tests leggen vast dat ontbrekend/leeg secret 503 geeft
en dat een geconfigureerd secret het oude 401/200-gedrag behoudt.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException, status

from src.core.api.v1.foundation.webhooks import _verify_webhook_secret
from src.core.shared.config import get_settings


@pytest.mark.unit
class TestBrevoWebhookSecretFailClosed:
    """Geen geconfigureerd secret = endpoint niet beschikbaar (503)."""

    def test_missing_secret_returns_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """brevo_webhook_secret=None -> 503, nooit stilletjes permit."""
        settings = get_settings()
        monkeypatch.setattr(settings, "brevo_webhook_secret", None)

        with pytest.raises(HTTPException) as exc_info:
            _verify_webhook_secret(secret_header=None, brevo_header=None, token_query=None)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_empty_secret_returns_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """brevo_webhook_secret='' -> 503; een lege string telt niet als secret."""
        settings = get_settings()
        monkeypatch.setattr(settings, "brevo_webhook_secret", "")

        with pytest.raises(HTTPException) as exc_info:
            _verify_webhook_secret(secret_header=None, brevo_header=None, token_query=None)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_wrong_secret_returns_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Geconfigureerd secret + foute header -> 401 (ongewijzigd gedrag)."""
        settings = get_settings()
        monkeypatch.setattr(settings, "brevo_webhook_secret", "super-secret-key")

        with pytest.raises(HTTPException) as exc_info:
            _verify_webhook_secret(
                secret_header="wrong", brevo_header=None, token_query=None
            )

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_correct_secret_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Geconfigureerd secret + juiste header -> geen exception.

        Legitieme-flow-mutatie: de fix mag werkende webhooks niet breken.
        """
        settings = get_settings()
        monkeypatch.setattr(settings, "brevo_webhook_secret", "super-secret-key")

        _verify_webhook_secret(
            secret_header="super-secret-key", brevo_header=None, token_query=None
        )

    def test_whitespace_secret_returns_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """brevo_webhook_secret='   ' -> 503; whitespace telt niet als secret
        (BE-SEC-056: 'not configured' op een truthy whitespace-string zou de
        fail-closed guard passeren terwijl er feitelijk geen secret is)."""
        settings = get_settings()
        monkeypatch.setattr(settings, "brevo_webhook_secret", "   ")

        with pytest.raises(HTTPException) as exc_info:
            _verify_webhook_secret(secret_header=None, brevo_header=None, token_query=None)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
