"""
Auth Dependencies Coverage Tests - Week 3, Subagent 4
Target: dependencies.py (16.54% -> 60%+)

Tests for authentication dependencies:
- get_current_user dependency
- get_current_user_id dependency
- require_permission dependency
- Token extraction and verification
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

# Import the REAL dependencies module directly
import src.core.auth.dependencies as deps
from src.core.auth.jwt_handler import jwt_handler

from tests.fixtures.auth import mock_sessie_zonder_intrekking


def _blacklist_mist(mock_db) -> None:
    """Laat de intrekkingscontrole van OP-188 doorlopen met "niet ingetrokken".

    `_get_user_from_token` houdt de jti tegen de blacklist met een ECHTE query;
    `scalar_one_or_none() is None` betekent "niet ingetrokken". Zo blijft die controle in
    deze tests draaien in plaats van weggemockt te worden.

    Het resultaat MOET een MagicMock zijn en geen AsyncMock-kind. Gemeten:
    `AsyncMock(spec=AsyncSession).execute.return_value` is ZELF een AsyncMock, dus
    `scalar_one_or_none()` geeft daar een COROUTINE terug. Die is nooit None, `is not None`
    wordt True, de code concludeert "ingetrokken", en er valt een 401 die niets met het
    testgeval te maken heeft.
    """
    blacklist_miss = MagicMock()
    blacklist_miss.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = blacklist_miss


def _uitgevoerde_where(mock_session) -> str:
    """De WHERE-clausule van de laatst uitgevoerde query, met de waarden erin.

    Zonder deze controle is een test op `get_current_user_id` hol: `mock_session.execute`
    geeft ONGEACHT de query dezelfde gebruiker terug, dus het filter zelf wordt nergens
    getoetst. Gemeten door de Gate 2-code-reviewer: met alleen `assert result == 42`
    overleeft `select(User).where(User.id == x)` -> `select(User)` de test, en dat is in
    productie een authenticatie-bypass (de eerste willekeurige gebruiker uit de tabel).
    """
    stmt = mock_session.execute.await_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE" in sql, (
        "De query heeft GEEN WHERE-clausule. In productie levert dat de eerste "
        "willekeurige gebruiker uit de tabel op -- een authenticatie-bypass. SQL: %s" % sql
    )
    return sql.split("WHERE")[1].strip()


class MockRequest:
    def __init__(self, headers=None, cookies=None, query_params=None):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.query_params = query_params or {}
        self.url = MagicMock()
        self.url.path = "/test"


class TestGetCurrentUser:
    """Test get_current_user dependency"""

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self):
        """Should return user for valid token with sub claim"""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock user from database
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.is_active = True
        mock_user.role_id = 5
        mock_user.tenant_id = 1

        with patch("src.core.auth.jwt_handler.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": "test@example.com", "jti": "jti-valid-token"}

            _blacklist_mist(mock_db)

            with patch.object(deps, "auth_service") as mock_auth:
                mock_auth.get_user_by_email = AsyncMock(return_value=mock_user)

                with patch(
                    "src.core.auth.dependencies.get_token_from_request",
                    return_value="valid_token",
                ):
                    result = await deps.get_current_user(MockRequest(), mock_db, None)

                assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token_raises(self):
        """Should raise 401 for invalid token"""
        mock_db = AsyncMock(spec=AsyncSession)

        with patch("src.core.auth.jwt_handler.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = None  # Token verification failed

            with patch(
                "src.core.auth.dependencies.get_token_from_request",
                return_value="invalid_token",
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await deps.get_current_user(MockRequest(), mock_db, None)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self):
        """Should raise 401 when user from token doesn't exist"""
        mock_db = AsyncMock(spec=AsyncSession)

        with patch("src.core.auth.jwt_handler.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": "deleted@example.com", "jti": "jti-deleted-user"}

            _blacklist_mist(mock_db)

            with patch.object(deps, "auth_service") as mock_auth:
                mock_auth.get_user_by_email = AsyncMock(return_value=None)

                with patch(
                    "src.core.auth.dependencies.get_token_from_request",
                    return_value="token_for_deleted_user",
                ):
                    with pytest.raises(HTTPException) as exc_info:
                        await deps.get_current_user(MockRequest(), mock_db, None)

                assert exc_info.value.status_code == 401
                # Deze test was tot 2026-09-18 GROEN OM DE VERKEERDE REDEN: zijn payload had
                # geen jti, dus de 401 kwam uit de fail-secure jti-tak (dependencies.py:122)
                # en de gebruikerslookup werd nooit bereikt. Zonder deze assertie legt de
                # test niet vast wat zijn naam belooft. Mutatiebewijs staat in de
                # commitboodschap: haal de jti weg en deze regel faalt.
                mock_auth.get_user_by_email.assert_awaited_once_with(
                    mock_db, email="deleted@example.com"
                )


class TestTokenEmailExtraction:
    """Test email extraction from different token formats"""

    @pytest.mark.asyncio
    async def test_extract_email_from_sub_claim(self):
        """Should extract email from standard 'sub' claim"""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_user = MagicMock()
        mock_user.email = "sub@example.com"
        mock_user.id = 1
        mock_user.role_id = 5
        mock_user.tenant_id = 1

        with patch("src.core.auth.jwt_handler.jwt_handler.verify_token") as mock_verify:
            mock_verify.return_value = {"sub": "sub@example.com", "jti": "jti-sub-claim"}

            _blacklist_mist(mock_db)

            with patch.object(deps, "auth_service") as mock_auth:
                mock_auth.get_user_by_email = AsyncMock(return_value=mock_user)

                with patch(
                    "src.core.auth.dependencies.get_token_from_request",
                    return_value="token",
                ):
                    with patch(
                        "src.core.security.security_manager.get_security_manager"
                    ) as mock_sm:
                        mock_sm.return_value.verify_token.return_value = None
                        result = await deps.get_current_user(
                            request=MockRequest(), db=mock_db, token=None
                        )

                mock_auth.get_user_by_email.assert_called_with(mock_db, email="sub@example.com")

    @pytest.mark.asyncio
    async def test_extract_email_from_email_claim(self):
        """Should fall back to 'email' claim if 'sub' not present"""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_user = MagicMock()
        mock_user.email = "email@example.com"
        mock_user.id = 1
        mock_user.role_id = 5
        mock_user.tenant_id = 1

        with patch("src.core.auth.jwt_handler.jwt_handler.verify_token") as mock_verify:
            # No 'sub', but has 'email'
            mock_verify.return_value = {"email": "email@example.com", "jti": "jti-email-claim"}

            _blacklist_mist(mock_db)

            with patch.object(deps, "auth_service") as mock_auth:
                mock_auth.get_user_by_email = AsyncMock(return_value=mock_user)

                with patch(
                    "src.core.auth.dependencies.get_token_from_request",
                    return_value="token",
                ):
                    with patch(
                        "src.core.security.security_manager.get_security_manager"
                    ) as mock_sm:
                        mock_sm.return_value.verify_token.return_value = None
                        result = await deps.get_current_user(
                            request=MockRequest(), db=mock_db, token=None
                        )

                mock_auth.get_user_by_email.assert_called_with(mock_db, email="email@example.com")

    @pytest.mark.asyncio
    async def test_extract_email_from_user_id_format(self):
        """Should extract email from 'user_<email>' format in user_id"""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_user = MagicMock()
        mock_user.email = "extracted@example.com"
        mock_user.id = 1
        mock_user.role_id = 5
        mock_user.tenant_id = 1

        with patch("src.core.auth.jwt_handler.jwt_handler.verify_token") as mock_verify:
            # SecurityManager format: user_id = "user_<email>"
            mock_verify.return_value = {
                "user_id": "user_extracted@example.com",
                "jti": "jti-user-id-format",
            }

            _blacklist_mist(mock_db)

            with patch.object(deps, "auth_service") as mock_auth:
                mock_auth.get_user_by_email = AsyncMock(return_value=mock_user)

                with patch(
                    "src.core.auth.dependencies.get_token_from_request",
                    return_value="token",
                ):
                    with patch(
                        "src.core.security.security_manager.get_security_manager"
                    ) as mock_sm:
                        mock_sm.return_value.verify_token.return_value = None
                        result = await deps.get_current_user(
                            request=MockRequest(), db=mock_db, token=None
                        )

                mock_auth.get_user_by_email.assert_called_with(
                    mock_db, email="extracted@example.com"
                )

    @pytest.mark.asyncio
    async def test_no_email_in_token_raises(self):
        """Should raise 401 if no email can be extracted from token"""
        mock_db = AsyncMock(spec=AsyncSession)

        with patch("src.core.auth.jwt_handler.jwt_handler.verify_token") as mock_verify:
            # Token has no email-related claims
            mock_verify.return_value = {"some_other": "claim", "jti": "jti-no-email"}

            _blacklist_mist(mock_db)

            with patch(
                "src.core.auth.dependencies.get_token_from_request",
                return_value="token_without_email",
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await deps.get_current_user(MockRequest(), mock_db, None)

            assert exc_info.value.status_code == 401
            # Zelfde verkeerde-reden-val als hierboven: zonder jti stopt de code bij de
            # fail-secure tak en bereikt hij de e-mailextractie nooit. De blacklistquery
            # loopt alleen NA die tak, dus dit legt vast dat we er voorbij zijn gekomen.
            mock_db.execute.assert_awaited_once()
            # testing.md: nooit asserteren DAT een mock is aangeroepen zonder de argumenten
            # te controleren. Dit legt vast dat er op de jti UIT DIT TOKEN is gezocht.
            assert _uitgevoerde_where(mock_db) == "token_blacklist.jti = 'jti-no-email'"


class TestGetCurrentUserId:
    """Test get_current_user_id dependency.

    Deze vier tests patchten tot 2026-09-18 `deps.config` en `deps.jwt.decode`. Geen van
    beide bestaat nog in `src/core/auth/dependencies.py`: `get_current_user_id` gaat sinds
    een refactor via `jwt_handler.verify_token()`. Ze stonden uit met de reden "Flaky:
    passes in isolation, fails in full suite due to shared state", maar faalden juist WEL
    in isolatie, deterministisch, met `AttributeError: module ... does not have the
    attribute 'config'`. Zie ADR-036 OP-196.

    Ze gebruiken nu ECHTE tokens uit `jwt_handler.create_access_token()` in plaats van een
    gemockte `verify_token`. Dat is bewust: precies een gemockt aangrijpingspunt is hier
    stilletjes verouderd, en een echt token kan dat niet. `verify_token` eist `sub` EN
    `tenant_id` (jwt_handler.py:291-301), vandaar dat beide in elke payload staan.
    """

    @pytest.mark.asyncio
    async def test_get_current_user_id_with_int_user_id(self):
        """get_current_user_id should return user ID when payload has int user_id"""
        mock_session = AsyncMock(spec=AsyncSession)

        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.email = "test@example.com"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        # OP-260: `get_current_user_id` raadpleegt sinds 2026-09-19 EERST de blacklist.
        # Zonder deze routering zou die query ook `mock_user` opleveren en concludeert de
        # code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
        mock_sessie_zonder_intrekking(mock_session, mock_result)

        token = jwt_handler.create_access_token(
            {"sub": "test@example.com", "tenant_id": 1, "user_id": 42}
        )

        result = await deps.get_current_user_id(token, mock_session)

        assert result == 42
        assert _uitgevoerde_where(mock_session) == "users.id = 42"

    @pytest.mark.asyncio
    async def test_get_current_user_id_with_string_user_id(self):
        """get_current_user_id should lookup by email when user_id is string"""
        mock_session = AsyncMock(spec=AsyncSession)

        mock_user = MagicMock()
        mock_user.id = 99
        mock_user.email = "test@example.com"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        # OP-260: `get_current_user_id` raadpleegt sinds 2026-09-19 EERST de blacklist.
        # Zonder deze routering zou die query ook `mock_user` opleveren en concludeert de
        # code "ingetrokken" -- een 401 die niets met dit testgeval te maken heeft.
        mock_sessie_zonder_intrekking(mock_session, mock_result)

        token = jwt_handler.create_access_token(
            {"sub": "test@example.com", "tenant_id": 1, "user_id": "user_test@example.com"}
        )

        result = await deps.get_current_user_id(token, mock_session)

        assert result == 99
        # De "user_"-prefix MOET gestript zijn; zonder deze regel overleeft
        # `user_email[5:]` -> `user_email[0:]` de test.
        assert _uitgevoerde_where(mock_session) == "users.email = 'test@example.com'"

    @pytest.mark.asyncio
    async def test_get_current_user_id_expired_token(self):
        """Should raise 401 for expired token"""
        mock_session = AsyncMock(spec=AsyncSession)

        # Een ECHT verlopen token: negatieve expires_delta. `verify_token` geeft dan None
        # (`except JWTError:` op jwt_handler.py:303, `return None` op 307) en
        # `get_current_user_id` maakt daar een 401 van.
        token = jwt_handler.create_access_token(
            {"sub": "test@example.com", "tenant_id": 1},
            expires_delta=timedelta(minutes=-5),
        )

        # Leg VAST dat dit token echt verlopen is. De detailtekst doet dat niet:
        # `dependencies.py:280` geeft "Invalid or expired token" voor ELKE mislukte
        # verificatie, dus `"expired" in detail` slaagt ook op een volstrekt geldig maar
        # onleesbaar token -- dan zou deze test niets anders toetsen dan zijn buurman.
        verlooptijd = jose_jwt.get_unverified_claims(token)["exp"]
        assert verlooptijd < datetime.now(timezone.utc).timestamp(), (
            "Dit token is niet verlopen; de test meet dan de verkeerde 401."
        )

        with pytest.raises(HTTPException) as exc_info:
            await deps.get_current_user_id(token, mock_session)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_user_id_invalid_token(self):
        """Should raise 401 for invalid token format"""
        mock_session = AsyncMock(spec=AsyncSession)

        with pytest.raises(HTTPException) as exc_info:
            await deps.get_current_user_id("not.a.valid.jwt", mock_session)

        assert exc_info.value.status_code == 401


class TestRequirePermission:
    """Test require_permission dependency"""

    @pytest.mark.asyncio
    async def test_require_permission_granted(self):
        """Should return user_id when permission is granted"""
        from src.core.auth.rbac import Permission

        with patch.object(deps, "require_tenant_id", return_value=1):
            mock_session = AsyncMock(spec=AsyncSession)

            # User exists in tenant
            mock_user = MagicMock()
            mock_user.id = 1
            mock_user.tenant_id = 1

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_session.execute.return_value = mock_result

            # RBAC grants permission
            with patch.object(deps, "RBACService") as MockRBAC:
                mock_rbac = MagicMock()
                mock_rbac.has_permission = AsyncMock(return_value=True)
                MockRBAC.return_value = mock_rbac

                checker = deps.require_permission(Permission.READ)
                result = await checker(user_id=1, session=mock_session)

                assert result == 1

    @pytest.mark.asyncio
    async def test_require_permission_denied(self):
        """Should raise 403 when permission is denied"""
        from src.core.auth.rbac import Permission

        with patch.object(deps, "require_tenant_id", return_value=1):
            mock_session = AsyncMock(spec=AsyncSession)

            # User exists in tenant
            mock_user = MagicMock()
            mock_user.id = 1
            mock_user.tenant_id = 1

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_session.execute.return_value = mock_result

            # RBAC denies permission
            with patch.object(deps, "RBACService") as MockRBAC:
                mock_rbac = MagicMock()
                mock_rbac.has_permission = AsyncMock(return_value=False)
                MockRBAC.return_value = mock_rbac

                checker = deps.require_permission(Permission.ADMIN)

                with pytest.raises(HTTPException) as exc_info:
                    await checker(user_id=1, session=mock_session)

                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_permission_user_not_in_tenant(self):
        """Should raise 403 when user not found in tenant"""
        from src.core.auth.rbac import Permission

        with patch.object(deps, "require_tenant_id", return_value=2):  # Different tenant
            mock_session = AsyncMock(spec=AsyncSession)

            # User NOT found in tenant
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result

            checker = deps.require_permission(Permission.READ)

            with pytest.raises(HTTPException) as exc_info:
                await checker(user_id=1, session=mock_session)

            assert exc_info.value.status_code == 403


# `TestRequirePermissionWithTenantBypass::test_super_admin_bypass` is op 2026-09-18
# VERWIJDERD en vervangen door
# `tests/unit/auth/test_de_superuser_bypass_wordt_gelogd.py` (ADR-036 OP-199).
#
# Hij stond op `pytest.mark.skip(reason="Flaky: passes in isolation, fails in full suite
# due to shared state")`. Die reden is een claim over het verleden en hij klopt niet meer:
# de test patchte `src.core.services.audit_service`, een module die niet meer bestaat, dus
# hij zou deterministisch falen en niet wisselend. Hij toetste bovendien alleen
# `result == 1` -- nooit dat de bypass een auditregel achterlaat, wat het enige is dat die
# deur verantwoord maakt. Zijn vervanger loopt over dezelfde echte producent, toetst de
# auditregel wel, en is in beide richtingen mutatie-getest.


class TestGetCurrentUserDependency:
    """Test get_current_user_dependency FastAPI wrapper"""

    @pytest.mark.asyncio
    async def test_get_current_user_dependency_wraps_get_current_user(self):
        """get_current_user_dependency should wrap get_current_user"""
        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.id = 1
        mock_user.role_id = 5
        mock_user.tenant_id = 1

        mock_db = AsyncMock(spec=AsyncSession)

        with patch.object(deps, "get_current_user", new=AsyncMock(return_value=mock_user)):
            result = await deps.get_current_user_dependency(
                request=MockRequest(), db=mock_db, credentials=None
            )

            assert result.email == "test@example.com"


class TestSecurityBearer:
    """Test security HTTPBearer configuration"""

    def test_security_bearer_exists(self):
        """HTTPBearer security should be configured"""
        assert hasattr(deps, "security")
        from fastapi.security import HTTPBearer

        assert isinstance(deps.security, HTTPBearer)

    def test_oauth2_scheme_exists(self):
        """OAuth2PasswordBearer should be configured"""
        assert hasattr(deps, "oauth2_scheme")


class TestModuleExports:
    """Test module exports correct functions"""

    def test_get_current_user_exists(self):
        """get_current_user should be exported"""
        assert hasattr(deps, "get_current_user")

    def test_get_current_user_id_exists(self):
        """get_current_user_id should be exported"""
        assert hasattr(deps, "get_current_user_id")

    def test_require_permission_exists(self):
        """require_permission should be exported"""
        assert hasattr(deps, "require_permission")

    def test_get_current_user_dependency_exists(self):
        """get_current_user_dependency should be exported"""
        assert hasattr(deps, "get_current_user_dependency")
