"""Unit tests for BE-SEC-054: geen admin auto-promotie bij password-login.

Offline: geen database, geen Redis, geen netwerk. De endpoints
`login_with_password` en `quick_login` uit
`src/core/api/v1/foundation/auth.py` worden direct aangeroepen met een
in-memory fake sessie die de WHERE email-filters van de echte statements
evalueert tegen in-memory rijen.

Beveiligingsinvarianten (markt-review 2026-09-24, security.md HIGH-bevinding):

a. Eerste password-login van een core User zonder PortalUser provisioneert met
   de LAAGSTE rol (PortalRole.VISITOR), nooit ADMIN (OWASP Authorization
   Cheat Sheet: least privilege / deny by default).
b. Er is geen hardcoded fallback die username "admin" (of elke string zonder
   "@") mapt op admin@levendmonument.nl.
c. Een legitieme, via seed aangemaakte portal-admin blijft gewoon inloggen.
d. quick-login werkt alleen buiten productie en promoveert een bestaande
   gebruiker nooit naar admin.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt as jose_jwt

from src.core.api.v1.foundation.auth import login_with_password, quick_login
from src.core.api.v1.foundation.schemas import PasswordLoginRequest, QuickLoginRequest
from src.core.auth.jwt_handler import jwt_handler
from src.core.models.foundation_content import PortalRole, PortalUser
from src.core.models.rbac_models import User


# ============================================================================
# Fake sessie: evalueert de echte WHERE email-filters tegen in-memory rijen
# ============================================================================


class _FakeResult:
    """Minimale stand-in voor sqlalchemy Result (scalars().first())."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_FakeResult":
        return self

    def first(self) -> object | None:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> object | None:
        return self._rows[0] if self._rows else None


class _FakeAuthSession:
    """AsyncSession-stand-in die SELECTs op User/PortalUser echt filtert.

    De bind-parameters van het gecompileerde statement (o.a. de email-waarden
    uit `==` of `in_([...])` filters) worden gematcht tegen de in-memory
    tabellen. Zo testen we de WERKELIJKE lookup-semantiek -- inclusief wat er
    gebeurt als de code een hardcoded fallback-email in de WHERE zet.
    """

    def __init__(
        self,
        *,
        core_users: list[User] | None = None,
        portal_users: list[PortalUser] | None = None,
    ) -> None:
        self.core_users = {u.email: u for u in (core_users or [])}
        self.portal_users = {u.email: u for u in (portal_users or [])}
        self.added: list[object] = []
        self.statements: list[object] = []

    async def execute(self, stmt: object) -> _FakeResult:
        self.statements.append(stmt)
        entity = stmt.column_descriptions[0]["entity"]  # type: ignore[attr-defined]
        params = stmt.compile().params  # type: ignore[attr-defined]
        waarden: list[object] = []
        for value in params.values():
            if isinstance(value, (list, tuple)):
                waarden.extend(value)
            else:
                waarden.append(value)
        bron = self.core_users if entity is User else self.portal_users
        rows = [u for email, u in bron.items() if email in waarden]
        return _FakeResult(rows)

    def add(self, obj: object) -> None:
        self.added.append(obj)
        if isinstance(obj, PortalUser):
            self.portal_users.setdefault(obj.email, obj)

    async def flush(self) -> None:
        return None


def _core_user(email: str, *, is_active: bool = True) -> User:
    return User(
        tenant_id=1,
        email=email,
        hashed_password="fake-hash",
        is_active=is_active,
    )


def _portal_user(email: str, role: PortalRole) -> PortalUser:
    user = PortalUser(
        tenant_id=1,
        email=email,
        display_name=email,
        role=role,
        is_verified=True,
        email_verified=True,
    )
    user.id = 1000 + len(email)  # deterministische nep-id voor JWT-sub
    return user


def _mock_request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    return request


def _mock_tenant() -> MagicMock:
    tenant = MagicMock()
    tenant.id = 1
    tenant.slug = "default"
    return tenant


def _decode_role(access_token: str) -> str:
    payload = jose_jwt.decode(
        access_token,
        jwt_handler.secret_key,
        algorithms=[jwt_handler.algorithm],
        audience="portal",
    )
    return str(payload["role"])


def _patched(*, environment: str = "development"):
    """Contextmanager-stack: tenant-scope, wachtwoordverificatie en settings.

    `jwt_handler.verify_password` wordt gepatcht (bcrypt blijft buiten scope);
    `create_access_token` blijft ECHT zodat de JWT-claims decodeerbaar zijn.
    """
    mock_jwt = MagicMock()
    mock_jwt.verify_password = AsyncMock(return_value=True)
    mock_jwt.create_access_token = jwt_handler.create_access_token

    scope = MagicMock()
    scope.return_value.__aenter__ = AsyncMock(return_value=_mock_tenant())
    scope.return_value.__aexit__ = AsyncMock(return_value=False)

    settings = MagicMock()
    settings.environment = environment

    return (
        patch("src.core.api.v1.foundation.auth.public_tenant_scope", scope),
        patch("src.core.api.v1.foundation.auth.jwt_handler", mock_jwt),
        patch("src.core.api.v1.foundation.auth.get_settings", return_value=settings),
    )


# ============================================================================
# (a) Eerste password-login provisioneert met de LAAGSTE rol, nooit admin
# ============================================================================


@pytest.mark.unit
class TestPasswordLoginProvisioning:
    async def test_first_login_provisions_visitor_not_admin(self) -> None:
        """Core User zonder PortalUser: aangemaakte PortalUser is VISITOR.

        Voor de fix werd hier role=PortalRole.ADMIN gezet -- elke core-user
        die op het portal inlogde werd portal-admin (privilege escalation).
        """
        session = _FakeAuthSession(core_users=[_core_user("medewerker@lm.nl")])
        p1, p2, p3 = _patched()
        with p1, p2, p3:
            response = await login_with_password(
                tenantSlug="default",
                request=_mock_request(),
                data=PasswordLoginRequest(
                    username="medewerker@lm.nl", password="SterkWachtwoord123"
                ),
                session=session,  # type: ignore[arg-type]
            )

        aangemaakt = [o for o in session.added if isinstance(o, PortalUser)]
        assert len(aangemaakt) == 1, "precies een PortalUser geprovisioneerd"
        assert aangemaakt[0].role == PortalRole.VISITOR, (
            f"nieuwe PortalUser moet de laagste rol krijgen, kreeg: {aangemaakt[0].role}"
        )
        assert aangemaakt[0].role != PortalRole.ADMIN
        assert response["user"]["role"] == "visitor"
        assert _decode_role(str(response["access_token"])) == "visitor"

    async def test_first_login_never_provisions_curator_or_admin(self) -> None:
        """Auto-provisioning kent alleen de laagste rol; hogere rollen komen
        uit de seed/curator-flow, nooit uit een login-side-effect."""
        session = _FakeAuthSession(core_users=[_core_user("directeur@lm.nl")])
        p1, p2, p3 = _patched()
        with p1, p2, p3:
            await login_with_password(
                tenantSlug="default",
                request=_mock_request(),
                data=PasswordLoginRequest(
                    username="directeur@lm.nl", password="SterkWachtwoord123"
                ),
                session=session,  # type: ignore[arg-type]
            )

        aangemaakt = [o for o in session.added if isinstance(o, PortalUser)]
        assert len(aangemaakt) == 1
        assert aangemaakt[0].role not in (PortalRole.ADMIN, PortalRole.CURATOR)


# ============================================================================
# (b) Geen hardcoded fallback naar admin@levendmonument.nl
# ============================================================================


@pytest.mark.unit
class TestNoHardcodedAdminFallback:
    async def test_lookup_query_contains_no_hardcoded_admin_email(self) -> None:
        """De core-user lookup mag alleen de ingevoerde username bevatten.

        Voor de fix stond `admin@levendmonument.nl` hardcoded in de IN-lijst
        van de WHERE zodra de username "admin" was of geen "@" bevatte.
        """
        session = _FakeAuthSession(core_users=[])
        p1, p2, p3 = _patched()
        with p1, p2, p3:
            with pytest.raises(HTTPException):
                await login_with_password(
                    tenantSlug="default",
                    request=_mock_request(),
                    data=PasswordLoginRequest(username="admin", password="x"),
                    session=session,  # type: ignore[arg-type]
                )

        assert session.statements, "er moet een core-user lookup zijn uitgevoerd"
        params = session.statements[0].compile().params  # type: ignore[attr-defined]
        waarden: list[object] = []
        for value in params.values():
            if isinstance(value, (list, tuple)):
                waarden.extend(value)
            else:
                waarden.append(value)
        assert "admin@levendmonument.nl" not in waarden, (
            "hardcoded fallback-email zit nog in de lookup-query"
        )

    async def test_bare_admin_username_does_not_resolve_to_fallback_email(self) -> None:
        """Username 'admin' mag NIET matchen op core user admin@levendmonument.nl.

        Semantische toets via de fake sessie: alleen een core user met email
        'admin@levendmonument.nl' bestaat. Voor de fix logde 'admin' daarop in.
        """
        session = _FakeAuthSession(
            core_users=[_core_user("admin@levendmonument.nl")]
        )
        p1, p2, p3 = _patched()
        with p1, p2, p3:
            with pytest.raises(HTTPException) as exc_info:
                await login_with_password(
                    tenantSlug="default",
                    request=_mock_request(),
                    data=PasswordLoginRequest(username="admin", password="x"),
                    session=session,  # type: ignore[arg-type]
                )
        assert exc_info.value.status_code == 401

    async def test_username_without_at_sign_has_no_fallback(self) -> None:
        """Elke string zonder '@' wordt letterlijk opgezocht, niet gemapt."""
        session = _FakeAuthSession(
            core_users=[_core_user("admin@levendmonument.nl")]
        )
        p1, p2, p3 = _patched()
        with p1, p2, p3:
            with pytest.raises(HTTPException) as exc_info:
                await login_with_password(
                    tenantSlug="default",
                    request=_mock_request(),
                    data=PasswordLoginRequest(username="beheerder", password="x"),
                    session=session,  # type: ignore[arg-type]
                )
        assert exc_info.value.status_code == 401


# ============================================================================
# (c) Bestaande legitieme admin (via seed) blijft werken
# ============================================================================


@pytest.mark.unit
class TestExistingAdminKeepsWorking:
    async def test_seeded_admin_logs_in_as_admin(self) -> None:
        """PortalUser met role=ADMIN (aangemaakt via seed/curator-flow) krijgt
        bij password-login gewoon een admin-token; er wordt niets geprovisioneerd."""
        session = _FakeAuthSession(
            core_users=[_core_user("beheer@lm.nl")],
            portal_users=[_portal_user("beheer@lm.nl", PortalRole.ADMIN)],
        )
        p1, p2, p3 = _patched()
        with p1, p2, p3:
            response = await login_with_password(
                tenantSlug="default",
                request=_mock_request(),
                data=PasswordLoginRequest(username="beheer@lm.nl", password="x"),
                session=session,  # type: ignore[arg-type]
            )

        assert response["user"]["role"] == "admin"
        assert _decode_role(str(response["access_token"])) == "admin"
        assert not [o for o in session.added if isinstance(o, PortalUser)]

    async def test_unknown_user_gets_generic_401(self) -> None:
        session = _FakeAuthSession(core_users=[])
        p1, p2, p3 = _patched()
        with p1, p2, p3:
            with pytest.raises(HTTPException) as exc_info:
                await login_with_password(
                    tenantSlug="default",
                    request=_mock_request(),
                    data=PasswordLoginRequest(
                        username="onbekend@lm.nl", password="x"
                    ),
                    session=session,  # type: ignore[arg-type]
                )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Ongeldige gebruikersnaam of wachtwoord."


# ============================================================================
# (d) quick-login: alleen buiten productie, nooit promotie naar admin
# ============================================================================


@pytest.mark.unit
class TestQuickLogin:
    @pytest.mark.parametrize("environment", ["blue", "green", "staging", ""])
    async def test_quick_login_forbidden_outside_allowlist(
        self, environment: str
    ) -> None:
        """BE-SEC-055: quick-login is fail-closed buiten de dev/test-allowlist.

        Deploys zetten ENVIRONMENT=blue/green (blue-green productie) of
        staging; de oude guard matchte exact op "production" en liet
        quick-login daar actief. Rood voor de fix: blue/green/staging gaven
        een geldig admin-token terug.
        """
        session = _FakeAuthSession()
        p1, p2, p3 = _patched(environment=environment)
        with p1, p2, p3:
            with pytest.raises(HTTPException) as exc_info:
                await quick_login(
                    tenantSlug="default",
                    request=_mock_request(),
                    data=QuickLoginRequest(role="admin"),
                    session=session,  # type: ignore[arg-type]
                )
        assert exc_info.value.status_code == 403
        assert not [
            o for o in session.added if isinstance(o, PortalUser)
        ], "quick-login mag buiten de allowlist geen PortalUser aanmaken"

    async def test_quick_login_forbidden_in_production(self) -> None:
        session = _FakeAuthSession()
        p1, p2, p3 = _patched(environment="production")
        with p1, p2, p3:
            with pytest.raises(HTTPException) as exc_info:
                await quick_login(
                    tenantSlug="default",
                    request=_mock_request(),
                    data=QuickLoginRequest(role="admin"),
                    session=session,  # type: ignore[arg-type]
                )
        assert exc_info.value.status_code == 403

    async def test_quick_login_does_not_promote_existing_user_to_admin(self) -> None:
        """Een bestaande PortalUser mag door quick-login nooit van rol
        veranderen -- zeker niet naar ADMIN.

        Voor de fix overschreef quick-login de rol van een bestaande gebruiker
        met de gevraagde rol (default: admin).
        """
        bestaand = _portal_user("admin@levendmonument.nl", PortalRole.VISITOR)
        session = _FakeAuthSession(portal_users=[bestaand])
        p1, p2, p3 = _patched(environment="development")
        with p1, p2, p3:
            response = await quick_login(
                tenantSlug="default",
                request=_mock_request(),
                data=QuickLoginRequest(role="admin"),
                session=session,  # type: ignore[arg-type]
            )

        assert bestaand.role == PortalRole.VISITOR, (
            f"quick-login heeft de rol overschreven naar: {bestaand.role}"
        )
        assert response["user"]["role"] == "visitor"
        assert _decode_role(str(response["access_token"])) == "visitor"

    async def test_quick_login_creates_visitor_in_development(self) -> None:
        """De bewuste dev-flow (commit e395118f5) blijft werken: quick-login
        buiten productie levert een geldig token voor een nieuwe bezoeker."""
        session = _FakeAuthSession()
        p1, p2, p3 = _patched(environment="development")
        with p1, p2, p3:
            response = await quick_login(
                tenantSlug="default",
                request=_mock_request(),
                data=QuickLoginRequest(role="bezoeker"),
                session=session,  # type: ignore[arg-type]
            )

        assert response["token_type"] == "bearer"
        assert response["user"]["role"] == "visitor"
        aangemaakt = [o for o in session.added if isinstance(o, PortalUser)]
        assert len(aangemaakt) == 1
        assert aangemaakt[0].role == PortalRole.VISITOR

    async def test_quick_login_without_role_defaults_to_visitor(self) -> None:
        """BE-SEC-056: een quick-login ZONDER rol mint een visitor, geen admin.

        Rood voor de fix: QuickLoginRequest.role had schema-default "admin",
        waardoor de auth.py-default onbereikbaar was en een rol-loze POST
        een admin-account mintte (alleen binnen de dev/test-allowlist).
        """
        assert QuickLoginRequest().role == "bezoeker", (
            "schema-default moet least-privilege zijn"
        )

        session = _FakeAuthSession()
        p1, p2, p3 = _patched(environment="development")
        with p1, p2, p3:
            response = await quick_login(
                tenantSlug="default",
                request=_mock_request(),
                data=QuickLoginRequest(),
                session=session,  # type: ignore[arg-type]
            )

        assert response["user"]["role"] == "visitor"
        assert _decode_role(str(response["access_token"])) == "visitor"
        aangemaakt = [o for o in session.added if isinstance(o, PortalUser)]
        assert len(aangemaakt) == 1
        assert aangemaakt[0].role == PortalRole.VISITOR
