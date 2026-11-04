"""BE-EP-056: een verteller meldt zich aan via de inloglink.

Regels die deze tests bewaken:
1. Een onbekend adres met ``aanmelden=True`` krijgt een account met de laagste
   rol (VISITOR), niet geverifieerd, in de tenant van de aanvraag.
2. Zonder ``aanmelden`` wordt er voor een onbekend adres niets aangemaakt.
3. Een bestaand account houdt zijn rol; er komt geen tweede account bij.
4. Iets dat niet op een e-mailadres lijkt, krijgt geen account.
5. Het antwoord is in alle gevallen hetzelfde (geen e-mail-enumeratie).
6. Wie de link gebruikt, is daarna geverifieerd.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request

from src.core.api.v1.foundation.auth import (
    MagicLinkRequest,
    MagicLinkVerifyRequest,
    request_magic_link,
    verify_magic_link,
)
from src.core.models.foundation_content import MagicLinkToken, PortalRole, PortalUser

GENERIEK = "If the email exists, a login link has been sent."


class _Tenant:
    def __init__(self, id: int = 7) -> None:
        self.id = id
        self.slug = "hetlevendmonument"
        self.name = "Het Levend Monument"


class _Bestaand:
    def __init__(self, role: PortalRole) -> None:
        self.id = 42
        self.tenant_id = 7
        self.email = "curator@example.org"
        self.role = role
        self.is_blocked = False
        self.is_verified = True
        self.email_verified = True
        self.last_login_at: datetime | None = None


class _Savepoint:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/auth/magic-link",
        "headers": [],
        "app": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    req = Request(scope)
    req.state.parsed_email = None
    return req


def _sessie(gevonden: object | None) -> AsyncMock:
    session = AsyncMock()
    resultaat = MagicMock()
    resultaat.scalar_one_or_none.return_value = gevonden
    session.execute.return_value = resultaat
    session.add = MagicMock()
    session.begin_nested = MagicMock(return_value=_Savepoint())
    return session


async def _vraag(session: AsyncMock, email: str, aanmelden: bool) -> dict[str, object]:
    tenant = _Tenant()

    @contextlib.asynccontextmanager
    async def scope(slug: str, s: Any):  # noqa: ARG001
        yield tenant

    with patch("src.core.api.v1.foundation.auth.public_tenant_scope", side_effect=scope), patch(
        "src.core.api.v1.foundation.auth.require_portal_magic_link_email_rate_limit",
        new=AsyncMock(),
    ), patch(
        "src.core.api.v1.foundation.auth.brevo_email_service.send_magic_link", new=AsyncMock()
    ), patch(
        "src.core.api.v1.foundation.auth.notification_service.notify_user", new=AsyncMock()
    ):
        return await request_magic_link(
            tenantSlug="hetlevendmonument",
            request=_request(),
            data=MagicLinkRequest(email=email, aanmelden=aanmelden),
            session=session,
            _check_ip=None,
        )


def _toegevoegd(session: AsyncMock, soort: type) -> list[Any]:
    return [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], soort)]


@pytest.mark.asyncio
async def test_een_nieuw_adres_krijgt_een_bezoekersaccount() -> None:
    session = _sessie(None)
    res = await _vraag(session, "  Verteller@Example.org ", aanmelden=True)

    nieuwe = _toegevoegd(session, PortalUser)
    assert len(nieuwe) == 1
    gebruiker = nieuwe[0]
    assert gebruiker.role == PortalRole.VISITOR
    assert gebruiker.tenant_id == 7
    assert gebruiker.email == "verteller@example.org"
    assert gebruiker.is_verified is False
    assert gebruiker.email_verified is False
    assert len(_toegevoegd(session, MagicLinkToken)) == 1
    assert res["message"] == GENERIEK


@pytest.mark.asyncio
async def test_zonder_aanmelden_komt_er_geen_account() -> None:
    session = _sessie(None)
    res = await _vraag(session, "verteller@example.org", aanmelden=False)

    session.add.assert_not_called()
    assert res["message"] == GENERIEK


@pytest.mark.parametrize("rol", [PortalRole.CURATOR, PortalRole.ADMIN, PortalRole.TEACHER])
@pytest.mark.asyncio
async def test_een_bestaand_account_houdt_zijn_rol(rol: PortalRole) -> None:
    bestaand = _Bestaand(rol)
    session = _sessie(bestaand)
    res = await _vraag(session, "curator@example.org", aanmelden=True)

    assert _toegevoegd(session, PortalUser) == []
    assert len(_toegevoegd(session, MagicLinkToken)) == 1
    assert bestaand.role == rol
    assert res["message"] == GENERIEK


@pytest.mark.parametrize("onzin", ["abc", "geen-apenstaart.nl", "a@b", "twee@@x.nl", "met spatie@x.nl"])
@pytest.mark.asyncio
async def test_iets_dat_geen_e_mailadres_is_krijgt_geen_account(onzin: str) -> None:
    session = _sessie(None)
    res = await _vraag(session, onzin, aanmelden=True)

    session.add.assert_not_called()
    assert res["message"] == GENERIEK


@pytest.mark.asyncio
async def test_het_antwoord_verraadt_niet_of_het_adres_bestond() -> None:
    nieuw = await _vraag(_sessie(None), "nieuw@example.org", aanmelden=True)
    bestaand = await _vraag(_sessie(_Bestaand(PortalRole.CURATOR)), "curator@example.org", aanmelden=True)
    onbekend = await _vraag(_sessie(None), "onbekend@example.org", aanmelden=False)

    assert nieuw == bestaand == onbekend == {"message": GENERIEK}


@pytest.mark.asyncio
async def test_wie_de_link_gebruikt_is_geverifieerd() -> None:
    token = MagicMock()
    token.id = 10
    token.portal_user_id = 42
    token.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    gebruiker = _Bestaand(PortalRole.VISITOR)
    gebruiker.is_verified = False
    gebruiker.email_verified = False

    sel, upd, usr = MagicMock(), MagicMock(), MagicMock()
    sel.scalar_one_or_none.return_value = token
    upd.scalar_one_or_none.return_value = token.id
    usr.scalar_one_or_none.return_value = gebruiker
    session = AsyncMock()
    session.execute.side_effect = [sel, upd, usr]

    @contextlib.asynccontextmanager
    async def scope(slug: str, s: Any):  # noqa: ARG001
        yield _Tenant()

    with patch("src.core.api.v1.foundation.auth.public_tenant_scope", side_effect=scope), patch(
        "src.core.api.v1.foundation.auth.AuditService.log_event", new=AsyncMock()
    ), patch(
        "src.core.api.v1.foundation.auth.jwt_handler.create_access_token", return_value="jwt"
    ):
        await verify_magic_link(
            tenantSlug="hetlevendmonument",
            request=_request(),
            data=MagicLinkVerifyRequest(token="geldige-token"),
            session=session,
            _check_ip=None,
        )

    assert gebruiker.is_verified is True
    assert gebruiker.email_verified is True
