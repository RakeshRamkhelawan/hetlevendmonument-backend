"""
OAuth2 Service - JWT Token Generation & Token Blacklist Management
Implements token generation, refresh, revocation, and blacklist management
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

from src.core.auth.token_kind import TokenKind
from src.core.auth.types import JWTPayload, VerifiedJWTPayload

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.core.auth.jwt_handler import jwt_handler
from src.core.config.unified_config import config
from src.core.database.database import Base

logger = logging.getLogger(__name__)


class TokenBlacklist(Base):  # type: ignore[misc]
    """
    Token Blacklist Model - Stores revoked tokens
    Used for logout/token revocation verification
    """

    __tablename__ = "token_blacklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    jti = mapped_column(
        String(255), unique=True, nullable=False
    )  # JWT ID claim (unique creates index automatically)
    user_id = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # SHA256 of token
    revoked_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )  # Token expiration
    revoked_by = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # Which user revoked it
    reason = mapped_column(
        String(255), nullable=True
    )  # Revocation reason (logout, password_change, etc)

    __table_args__ = (
        Index("idx_token_blacklist_expires", "expires_at"),
        Index("idx_token_blacklist_user", "user_id"),
        # NOTE: idx_token_blacklist_jti removed - jti column already has unique=True, index=True
        {"extend_existing": True},  # Allow table redefinition during test module reloading
    )

    def __repr__(self) -> str:
        return f"<TokenBlacklist(jti={self.jti[:8]}..., user_id={self.user_id}, expires_at={self.expires_at})>"


class OAuth2Service:
    """OAuth2 & JWT Token Service"""

    def __init__(self) -> None:
        self.jwt_handler = jwt_handler
        self.access_token_expire_minutes = config.jwt_expire_minutes or 60
        self.refresh_token_expire_days = config.refresh_token_expire_days or 7

    async def create_tokens(
        self,
        user_id: int,
        email: str,
        role_ids: list[int] | None = None,
        scopes: list[str] | None = None,
        tenant_id: int = 1,
    ) -> dict[str, str]:
        """
        Create both access and refresh tokens for a user

        Args:
            user_id: User ID
            email: User email
            role_ids: List[int] of role IDs
            scopes: List[str] of OAuth2 scopes (users.read, workflows.write, etc)
            tenant_id: Tenant ID for multi-tenant support

        Returns:
            dict[str, str] with access_token, refresh_token, expires_in, token_type
        """
        # Create access token (short-lived)
        access_token = await self._create_access_token(
            user_id=user_id,
            email=email,
            role_ids=role_ids or [],
            scopes=scopes or [],
            tenant_id=tenant_id,
        )

        # Create refresh token (long-lived)
        # OP-182, tweede helft: de tenant wordt hier MEEGEGEVEN. Hij werd niet
        # doorgegeven, waardoor de default hieronder elk refresh-token in tenant 1
        # zette -- ongeacht bij welke organisatie de gebruiker hoorde.
        refresh_token = await self._create_refresh_token(user_id, tenant_id)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": str(self.access_token_expire_minutes * 60),
        }

    async def _create_access_token(
        self, user_id: int, email: str, role_ids: list[int], scopes: list[str], tenant_id: int
    ) -> str:
        """
        Create JWT access token with user claims

        Payload structure matches frontend JWTPayload interface:
        {
            "sub": "user_id",           # User ID
            "email": "user@example.com",
            "role_ids": [1, 2],
            "scopes": ["users:read", "workflows:write"],  # Uses OAuth2Scope enum values
            "tenant_id": 1,
            "iat": 1702548000,
            "exp": 1702551600,
            "jti": "unique-id"
        }
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=self.access_token_expire_minutes)

        payload: JWTPayload = {
            "sub": str(user_id),
            "email": email,
            "role_ids": role_ids,
            "scopes": scopes,
            "tenant_id": tenant_id,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": str(uuid4()),  # JWT ID for revocation tracking
        }

        token = cast(str, self.jwt_handler.create_access_token(payload))
        logger.info(
            f"Access token created for user {user_id} (expires in {self.access_token_expire_minutes}m)"
        )
        return token

    async def _create_refresh_token(self, user_id: int, tenant_id: int) -> str:
        """
        Create long-lived refresh token for token refresh flow
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self.refresh_token_expire_days)

        payload = {
            "sub": str(user_id),
            "tenant_id": tenant_id,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": str(uuid4()),
        }

        # OP-182: het soort zit nu in de JOSE-header (`typ: refresh+jwt`) en niet meer
        # in de body-claim `type`. Een body-claim is niet gestandaardiseerd, botst in
        # dit project met het OAuth2-responseveld `token_type` ("Bearer"), en zou een
        # TWEEDE soortmechanisme naast de header zijn -- precies wat RFC 8725 par. 3.12
        # met "mutually exclusive" validatieregels wil voorkomen.
        token = cast(str, self.jwt_handler.create_refresh_token(payload))
        logger.info(
            f"Refresh token created for user {user_id} (expires in {self.refresh_token_expire_days}d)"
        )
        return token

    async def refresh_access_token(
        self, refresh_token: str, db: AsyncSession
    ) -> dict[str, str] | None:
        """
        Refresh an expired access token using a refresh token

        Args:
            refresh_token: Valid refresh token
            db: Database session

        Returns:
            New access token dict or None if invalid
        """
        # Verify refresh token -- expliciet als REFRESH, zodat een access token hier
        # niet als refresh token kan worden aangeboden en omgekeerd (OP-182).
        try:
            payload = self.jwt_handler.verify_token(
                refresh_token, expected_kind=TokenKind.REFRESH
            )
        except (TypeError, ValueError) as e:
            logger.warning("Invalid refresh token")
            return None

        # Check if payload is None (invalid token or missing required claims)
        if payload is None:
            logger.warning("Refresh token is invalid")
            return None

        # Check if refresh token is blacklisted
        jti = payload.get("jti")
        if not jti or await self._is_token_blacklisted(jti, db):
            logger.warning("Refresh token is blacklisted or has no jti")
            return None

        sub = payload.get("sub")
        if sub is None:
            logger.warning("Refresh token missing sub claim")
            return None
        user_id = int(sub)

        # Een verversingstoken van voor een "alle sessies"-intrekking (nieuw wachtwoord) levert niets meer op.
        if await self.is_uitgegeven_voor_intrekking(user_id, payload.get("iat"), db):
            logger.warning("Refresh token geweigerd: alle sessies van gebruiker %s zijn ingetrokken", user_id)
            return None

        # Opzoeken via de aparte verbinding, daarna de klant AANNEMEN (OP-154 stap 2b).
        #
        # De oude toelichting zei dat auth-endpoints "excluded from TenantMiddleware" zijn.
        # Nagemeten klopt dat niet: er zijn twee uitzonderingslijsten in de codebase en in
        # geen van beide staat een auth-pad. De uitkomst klopte wel -- een publiek verzoek
        # zonder geldig token komt zonder klantcontext binnen (`tenant_middleware.py:152-155`)
        # -- maar het mechanisme was een ander.
        #
        # De omzeiling zelf hielp bovendien alleen zolang de applicatie als tabeleigenaar
        # verbindt. Onder `sanskritisetu_app` geeft deze SELECT nul rijen, en dan is elk
        # geldig refresh-token ineens "User not found": niemand kan zijn sessie meer
        # verlengen, en de logregel hieronder suggereert dat de gebruiker weg is.
        from src.core.database.bypass_session import adopt_tenant, pre_auth_lookup
        from src.core.models.rbac_models import User

        async with pre_auth_lookup(db) as opzoeker:
            gevonden = (
                await opzoeker.execute(select(User.id, User.tenant_id).where(User.id == user_id))
            ).one_or_none()

        if not gevonden:
            logger.warning(f"User {user_id} not found for token refresh")
            return None

        async with adopt_tenant(db, gevonden.tenant_id):
            user = (
                await db.execute(select(User).where(User.id == gevonden.id))
            ).scalar_one_or_none()

        if not user:
            logger.warning(f"User {user_id} not found for token refresh")
            return None

        # Uitgeschakeld is uitgeschakeld: een refresh-token mag geen nieuw access-token meer
        # opleveren, anders blijft een uitgezette gebruiker oneindig doorlopen.
        if not user.is_active:
            logger.warning("Token refresh geweigerd: account %s is uitgeschakeld", user_id)
            return None

        # Create new access token
        access_token = await self._create_access_token(
            user_id=user.id,
            email=user.email,
            role_ids=payload.get("role_ids", []),
            scopes=payload.get("scopes", []),
            tenant_id=user.tenant_id,
        )

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": str(self.access_token_expire_minutes * 60),
        }

    async def revoke_token(
        self,
        token: str,
        user_id: int,
        db: AsyncSession,
        reason: str = "logout",
        *,
        revoked_by: int | None = None,
        expected_kind: TokenKind = TokenKind.ACCESS,
    ) -> bool:
        """
        Revoke a token by adding it to the blacklist

        Args:
            token: Token to revoke
            user_id: De HOUDER van het token (eigenaar van de blacklistrij)
            db: Database session
            reason: Revocation reason (logout, password_change, etc)
            revoked_by: Wie het intrekt; standaard de houder zelf. Een beheerder die het token van
                een medewerker intrekt, staat hier met zijn eigen id (beveiligingsnazorg 2026-10-14:
                eerder kreeg de rij het id van de aanvrager als eigenaar).
            expected_kind: ACCESS of REFRESH; een token van het verkeerde soort wordt geweigerd.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Verify token
            try:
                payload = self.jwt_handler.verify_token(token, expected_kind=expected_kind)
            except (TypeError, ValueError) as e:
                logger.warning("Invalid token for revocation")
                return False

            # Check if payload is None (invalid token or missing required claims)
            if payload is None:
                logger.warning("Invalid token for revocation")
                return False

            jti = payload.get("jti")
            exp_timestamp = payload.get("exp")

            if not jti or not exp_timestamp:
                logger.warning("Token missing JTI or expiration")
                return False

            # Een tweede poging (bijvoorbeeld een herhaalde uitlogactie na een halve mislukking) is
            # geen fout: het token is al ingetrokken.
            if await self._is_token_blacklisted(jti, db):
                return True

            # Convert timestamp to datetime
            expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

            # Add to blacklist
            blacklist_entry = TokenBlacklist(
                jti=jti,
                user_id=user_id,
                token_hash=self._hash_token(token),
                expires_at=expires_at,
                revoked_by=revoked_by if revoked_by is not None else user_id,
                reason=reason,
            )

            db.add(blacklist_entry)
            await db.commit()

            logger.info(f"Token {jti[:8]}... revoked for user {user_id} (reason: {reason})")
            return True

        except Exception as e:
            logger.error(f"Error revoking token: {e}")
            await db.rollback()
            return False

    async def is_token_valid(self, token: str, db: AsyncSession) -> bool:
        """
        Check if token is valid and not blacklisted

        Args:
            token: Token to validate
            db: Database session

        Returns:
            True if valid and not revoked, False otherwise
        """
        # Verify signature and expiration
        try:
            payload = self.jwt_handler.verify_token(token)
        except (TypeError, ValueError):
            return False

        # Check if payload is None (invalid token or missing required claims)
        if payload is None:
            return False

        jti = payload.get("jti")
        if not jti:
            return False

        # Check if blacklisted
        is_blacklisted = await self._is_token_blacklisted(jti, db)
        return not is_blacklisted

    async def is_jti_revoked(self, jti: str, db: AsyncSession) -> bool:
        """Publieke variant van de blacklistcontrole, op JTI (ADR-036 OP-188).

        Bestaat omdat het verzoekpad (`auth/dependencies._weiger_als_ingetrokken`, sinds
        2026-09-19 aangeroepen vanuit BEIDE HTTP-ingangen) de
        blacklist moet kunnen raadplegen zonder het token opnieuw te verifieren -- dat is
        daar al gebeurd. `is_token_valid()` verifieert wel opnieuw en is bedoeld voor de
        introspectie-endpoints, waar het token nog niet gecontroleerd is.
        """
        return await self._is_token_blacklisted(jti, db)

    #: Een rij met deze jti-voorloop is geen los token maar een grens voor ALLE tokens van een gebruiker.
    ALLE_SESSIES_PREFIX = "user-all:"

    async def trek_alle_tokens_in(
        self, user_id: int, db: AsyncSession, *, reason: str, revoked_by: int | None = None
    ) -> None:
        """Maak alle tot nu toe uitgegeven toegangs- en verversingstokens van deze gebruiker ongeldig.

        Gebruikt het bestaande mechanisme (de tabel `token_blacklist`, bestaande kolommen) en zet daar EEN
        rij neer die een GRENS is in plaats van een los token: tokens met een `iat` op of voor dat moment
        gelden niet meer. Een blacklist op `jti` kan dit niet: uitgegeven tokens worden nergens bijgehouden,
        dus er is geen lijst om af te lopen. (`TokenBlacklist.revoke_all_user_tokens` zocht Redis-sleutels met
        een patroon dat nooit bestond en trok niets in; gemeten 2026-10-17.)

        De rij verloopt na de langste levensduur van een token (het verversingstoken); daarna kan er geen
        token meer bestaan dat hij moest tegenhouden. De aanroeper doet de commit, in dezelfde transactie
        als de wachtwoordwijziging: beide gelden of geen van beide.
        """
        nu = datetime.now(timezone.utc)
        db.add(
            TokenBlacklist(
                jti=f"{self.ALLE_SESSIES_PREFIX}{user_id}:{uuid4()}",
                user_id=user_id,
                token_hash="user-all",  # geen los token: er is niets om te hashen
                revoked_at=nu,
                # `create_refresh_token` zet `exp` altijd op 7 dagen, ongeacht `refresh_token_expire_days`
                # (gemeten 2026-10-18): de grens moet minstens zo lang leven als het langstlevende token.
                expires_at=nu + timedelta(days=max(self.refresh_token_expire_days, 7)),
                revoked_by=revoked_by if revoked_by is not None else user_id,
                reason=reason,
            )
        )

    async def is_uitgegeven_voor_intrekking(
        self, user_id: int, iat: object, db: AsyncSession
    ) -> bool:
        """Is dit token uitgegeven op of voor de laatste "alle sessies"-intrekking van deze gebruiker?

        Een token zonder `iat` telt als oud zodra er een grens is (gesloten kant). Tokens dragen `iat` in hele
        seconden: een token uit DEZELFDE seconde als de grens telt ook als oud. Een mens logt niet binnen een
        seconde na het kiezen van een wachtwoord opnieuw in.
        """
        nu = datetime.now(timezone.utc)
        grens = (
            await db.execute(
                select(func.max(TokenBlacklist.revoked_at)).where(
                    TokenBlacklist.user_id == user_id,
                    TokenBlacklist.jti.like(f"{self.ALLE_SESSIES_PREFIX}%"),
                    TokenBlacklist.expires_at > nu,
                )
            )
        ).scalar_one_or_none()
        if grens is None:
            return False
        if not isinstance(iat, (int, float)):
            return True
        return bool(grens >= datetime.fromtimestamp(int(iat), tz=timezone.utc))

    async def _is_token_blacklisted(self, jti: str, db: AsyncSession) -> bool:
        """Check if a token (by JTI) is blacklisted"""
        result = await db.execute(select(TokenBlacklist).where(TokenBlacklist.jti == jti))
        return result.scalar_one_or_none() is not None

    async def cleanup_expired_tokens(self, db: AsyncSession) -> int:
        """
        Remove expired tokens from blacklist (runs as cron job)

        Returns:
            Number of tokens deleted
        """
        try:
            from sqlalchemy import delete

            now = datetime.now(timezone.utc)

            result = await db.execute(delete(TokenBlacklist).where(TokenBlacklist.expires_at < now))
            await db.commit()

            deleted_count = getattr(result, "rowcount", 0)
            logger.info(f"Cleaned up {deleted_count} expired tokens from blacklist")
            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up expired tokens: {e}")
            await db.rollback()
            return 0

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash token for storage (not cryptographically critical)"""
        import hashlib

        return hashlib.sha256(token.encode()).hexdigest()

    def extract_token_claims(self, token: str) -> VerifiedJWTPayload | None:
        """
        Extract claims from token without verification
        Used for display/debugging purposes only

        Returns None if token is invalid or cannot be parsed
        """
        try:
            return cast(VerifiedJWTPayload | None, self.jwt_handler.verify_token(token))
        except Exception as e:
            logger.debug(f"Could not extract token claims: {e}")
            return None


# Create singleton instance
oauth2_service = OAuth2Service()
