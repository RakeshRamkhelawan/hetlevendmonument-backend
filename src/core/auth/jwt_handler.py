"""JWT Token Handler - Production Implementation
Verantwoordelijk voor JWT creatie en verificatie zoals gespecificeerd in FASE 1 STAP 1.2
"""

import asyncio
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional, cast

from src.core.auth.types import JWTPayload, VerifiedJWTPayload
from src.core.auth.token_kind import TokenKind, TokenSoortFout

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config.unified_config import config

if TYPE_CHECKING:
    from src.core.auth.token_blacklist import TokenBlacklist

logger = logging.getLogger(__name__)


class JWTHandler:
    """
    Production-grade JWT handler voor authenticatie
    Integrated with unified configuration system
    """

    # Teller per weigergrond (OP-182). Lui gevuld in _tel_soortfout, want er zijn
    # toetsen die een handler bouwen met JWTHandler.__new__ en dus __init__ overslaan.
    soortfouten: dict[TokenSoortFout, int]

    def __init__(self) -> None:
        self.config = config
        # CONFIGURATION: Explicitly controlled bcrypt rounds
        # Default to 12 (secure) if not set.
        # DO NOT rely on "TESTING" env var for this, as it leads to context mismatches.
        MIN_BCRYPT_ROUNDS = 12
        try:
            rounds = int(os.getenv("BCRYPT_ROUNDS", str(MIN_BCRYPT_ROUNDS)))
            if rounds < MIN_BCRYPT_ROUNDS:
                logger.warning(f"BCRYPT_ROUNDS {rounds} below minimum, using {MIN_BCRYPT_ROUNDS}")
                rounds = MIN_BCRYPT_ROUNDS
        except (TypeError, ValueError):
            rounds = MIN_BCRYPT_ROUNDS

        self.pwd_context = CryptContext(
            schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=rounds
        )
        logger.debug(f"Using bcrypt rounds={rounds}")
        self.algorithm = "HS256"
        self.secret_key = self._get_secret_key()
        self.access_token_expire_minutes = self.config.jwt_expire_minutes

    def _get_secret_key(self) -> str:
        """Get JWT secret key with validation"""
        secret = self.config.jwt_secret_key

        if not secret:
            if self.config.is_production():
                raise ValueError("JWT_SECRET_KEY must be set in production")
            # Generate random secret for development - NEVER log this
            secret = secrets.token_urlsafe(32)
            logger.warning("Using generated JWT secret for development (not logged for security)")
            # Store in environment for consistency across restarts
            os.environ["JWT_SECRET_KEY"] = secret

        # Validate secret strength in production
        if self.config.is_production():
            self._validate_secret_for_production(secret)

        return cast(str, secret)

    def _validate_secret_for_production(self, secret: str) -> bool:
        """
        Validate JWT secret strength for production use

        Args:
            secret: JWT secret key to validate

        Returns:
            True if secret is valid

        Raises:
            ValueError: If secret doesn't meet security requirements
        """
        # Reject non-string types
        if not isinstance(secret, str):
            raise ValueError("JWT secret must be a string")

        # Reject non-ASCII secrets (security requirement: ASCII-only)
        if not secret.isascii():
            raise ValueError("JWT secret must contain only ASCII characters")

        # Check minimum length (256 bits = 32 bytes)
        if len(secret) < 32:
            raise ValueError("JWT secret must be at least 32 characters in production")

        # Check for insecure patterns (case-insensitive)
        insecure_patterns = [
            "dev-",
            "dev_",
            "test-",
            "test_",
            "change-in-production",
            "change",
            "password",
        ]
        secret_lower = secret.lower()

        for pattern in insecure_patterns:
            if pattern in secret_lower:
                raise ValueError(f"Development secret detected: Insecure pattern '{pattern}' found")

        return True

    def create_access_token(
        self,
        data: JWTPayload,
        expires_delta: timedelta | None = None,
    ) -> str:
        """
        Create a JWT access token.

        Args:
            data: Data to encode in the token (e.g. {"sub": "user@email.com"}).
            expires_delta: Optional custom expiry time.

        Returns:
            Encoded JWT token string.
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=self.access_token_expire_minutes
            )

        to_encode.update({"exp": int(expire.timestamp())})

        # NEO Audit Sprint 7: Add jti (JWT ID) for individual token revocation.
        # Only add if caller did not pass a custom jti.
        if "jti" not in to_encode:
            to_encode["jti"] = str(uuid.uuid4())

        return self._encode(to_encode, TokenKind.ACCESS)

    def create_refresh_token(
        self,
        data: JWTPayload,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Maak een JWT REFRESH token.

        Dit is een aparte fabriek en GEEN parameter op create_access_token. Reden: een
        parameter met een default is de bypass -- vergeet een aanroeper hem, dan krijgt
        een refresh token de access-stempel en laat de controle in verify_token hem door
        op elk access-endpoint, met de volle levensduur van een refresh token. Twee
        fabrieken hebben geen veld dat je kunt vergeten.
        """
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(days=7)

        to_encode.update({"exp": int(expire.timestamp())})
        if "jti" not in to_encode:
            to_encode["jti"] = str(uuid.uuid4())

        return self._encode(to_encode, TokenKind.REFRESH)

    def _encode(self, to_encode: JWTPayload, soort: TokenKind) -> str:
        """De enige plek in deze klasse die ondertekent, met de soort-stempel erin.

        De stempel gaat in de JOSE-header `typ` (RFC 9068 par. 2.1), niet in de body.
        """
        encoded_jwt = cast(
            str,
            jwt.encode(
                cast(dict[str, object], to_encode),
                self.secret_key,
                algorithm=self.algorithm,
                headers={"typ": soort.value},
            ),
        )
        return encoded_jwt

    def _soort_klopt(self, token: str, verwacht: TokenKind) -> bool:
        """Vergelijk de JOSE-header `typ` met het verwachte soort.

        Fail-secure: een ONTBREKENDE `typ` wordt geweigerd, niet doorgelaten. Er is
        bewust GEEN terugvalvenster voor tokens van voor deze wijziging -- er is geen
        productiedata en er zijn geen klanten, alleen zelf aangemaakte testgebruikers,
        dus de kosten van de harde knip zijn een keer opnieuw inloggen. Een terugval
        die een `typ`-loos token accepteert, laat het gat van OP-182 juist open.
        """
        kop = jwt.get_unverified_header(token)
        gevonden = kop.get("typ")
        if not gevonden:
            self._tel_soortfout(TokenSoortFout.ONTBREEKT, verwacht, gevonden)
            return False
        if gevonden not in verwacht.aanvaarde_headerwaarden:
            self._tel_soortfout(TokenSoortFout.VERKEERD, verwacht, gevonden)
            return False
        return True

    def _tel_soortfout(
        self, reden: TokenSoortFout, verwacht: TokenKind, gevonden: object
    ) -> None:
        """Houd per reden bij hoe vaak deze guard vuurt.

        Zonder deze telling is een guard die nooit vuurt van buiten niet te
        onderscheiden van een guard die iemand heeft weggehaald.
        """
        # Lui aangemaakt en NIET in __init__ gezet: er zijn toetsen die een handler
        # bouwen met JWTHandler.__new__ en dus __init__ overslaan. Een guard die
        # crasht op een object dat zo is gebouwd, is een guard die je niet kunt
        # vertrouwen -- de weigering moet altijd een nette weigering zijn.
        tellers = getattr(self, "soortfouten", None)
        if tellers is None:
            tellers = {}
            self.soortfouten = tellers
        tellers[reden] = tellers.get(reden, 0) + 1
        logger.warning(
            "Token geweigerd op soort: reden=%s verwacht=%s gevonden=%s",
            reden.value,
            verwacht.value,
            gevonden,
        )

    def verify_token(
        self, token: str, *, expected_kind: TokenKind = TokenKind.ACCESS
    ) -> VerifiedJWTPayload | None:
        """
        Verifieer en decodeer een JWT token

        Args:
            token: JWT token string om te verificeren

        Returns:
            Decoded payload als token geldig is
            None if token is invalid, malformed, expired, or missing required claims

        Raises:
            TypeError: If token is not a string (e.g., None)
            ValueError: If token is empty or whitespace only

        Security Notes (OWASP A02):
        - Algorithm is explicitly specified (prevents "none" attack)
        - Only HS256 is accepted (algorithm confusion protection)
        - Expiration is verified by default
        - Returns None for clear error signaling without exceptions
        """
        # Validate token is a string (raises TypeError if not)
        if not isinstance(token, str):
            raise TypeError("Token must be a string")

        # Check for empty or whitespace-only token
        if not token or not token.strip():
            raise ValueError("Token cannot be empty or whitespace")

        try:
            # SECURITY: Explicitly specify allowed algorithms to prevent algorithm confusion
            # CRITICAL: Never use algorithms=None or include "none" in the list
            decoded: dict[str, object] = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],  # Explicit algorithm - prevents none attack
                options={
                    "require_exp": True,
                    "verify_exp": True,
                    "verify_aud": False,  # Allow tokens with arbitrary aud claims
                },  # Require and verify expiration
            )
            payload: VerifiedJWTPayload = cast(VerifiedJWTPayload, decoded)

            # OP-182: controleer het SOORT token, NA een geslaagde decode -- pas dan is
            # de header authentiek, want hij valt onder de handtekening. Gemeten: noch
            # python-jose noch PyJWT doet deze controle zelf.
            if not self._soort_klopt(token, expected_kind):
                return None

            # Validate required claims
            if "sub" not in payload:
                # Token is valid but missing required claim - return None instead of raising
                logger.warning("Token valid but missing required 'sub' claim")
                return None

            if "tenant_id" not in payload:
                # Token is valid but missing required claim - return None instead of raising
                logger.warning("Token valid but missing required 'tenant_id' claim")
                return None

            return payload
        except JWTError as e:
            # Log without exposing details (security best practice)
            logger.warning(f"JWT verification failed: {type(e).__name__}")
            # Return None instead of raising (RED phase behavior - backward compatible)
            return None

    async def verify_token_with_blacklist(
        self, token: str, blacklist: Optional["TokenBlacklist"] = None
    ) -> VerifiedJWTPayload | None:
        """
        Verify JWT token AND check if it's blacklisted (revoked).

        This method combines JWT verification with blacklist checking
        for immediate logout support.

        Args:
            token: JWT token string to verify
            blacklist: TokenBlacklist instance to check against

        Returns:
            Decoded payload if token is valid AND not revoked, else None

        Security Notes:
        - First verifies JWT token syntax and signature
        - Then checks if token is in revoked token blacklist
        - Returns None if either check fails
        """
        # First: Verify JWT token syntax and signature
        payload: VerifiedJWTPayload | None = self.verify_token(token)
        if payload is None:
            return None

        # Second: Check if token is blacklisted (if blacklist provided)
        if blacklist is not None:
            is_revoked = await blacklist.is_token_revoked(token)
            if is_revoked:
                logger.info("Token is revoked (blacklisted): [TOKEN REDACTED]")
                return None

        return payload

    def _validate_ascii_only(self, password: str) -> None:
        """
        Validate that password contains only ASCII characters

        Security requirement from Instructions.md line 213:
        "ASCII-ONLY ENCODING: Strict ASCII, geen Unicode karakters"

        Args:
            password: Plain text password to validate

        Raises:
            TypeError: If password is not a string
            ValueError: If password is None, empty, or contains non-ASCII characters
        """
        # Defensive input validation
        if password is None:
            raise ValueError("Password cannot be None")

        if not isinstance(password, str):
            raise TypeError(f"Password must be a string, got {type(password).__name__}")

        if not password:
            raise ValueError("Password cannot be empty")

        # ASCII-only validation (security requirement)
        if not password.isascii():
            raise ValueError("Password must contain only ASCII characters")

    def _truncate_password(self, password: str) -> str:
        """
        Truncate password to 72 bytes for bcrypt compatibility

        Bcrypt has a hard limit of 72 bytes. Since ASCII-only validation
        is enforced before this method is called, we can safely truncate
        at character level (ASCII is 1 byte per character).

        Args:
            password: Plain text password (ASCII-only, pre-validated)

        Returns:
            Password truncated to 72 characters

        Raises:
            TypeError: If password is not a string
            ValueError: If password is None or empty
        """
        # Defensive input validation
        if password is None:
            raise ValueError("Password cannot be None")

        if not isinstance(password, str):
            raise TypeError(f"Password must be a string, got {type(password).__name__}")

        if not password:
            raise ValueError("Password cannot be empty")

        # Since password is ASCII-only (enforced by validate_ascii_only),
        # we can safely truncate at character level (1 byte per character)
        if len(password) > 72:
            return password[:72]

        return password

    async def hash_password(self, password: str) -> str:
        """
        Hash een wachtwoord met bcrypt (async-safe)

        Uses run_in_executor to prevent blocking the async event loop.
        Bcrypt hashing with 12 rounds takes ~200-400ms, which would
        block async operations if run synchronously.

        Args:
            password: Plain text wachtwoord

        Returns:
            Gehashed wachtwoord

        Raises:
            TypeError: If password is not a string
            ValueError: If password is None, empty, or contains non-ASCII characters
            RuntimeError: If bcrypt hashing fails
        """
        # Defensive input validation and ASCII-only enforcement
        self._validate_ascii_only(password)

        # Truncate password to 72 bytes for bcrypt
        truncated_password = self._truncate_password(password)

        try:
            # Run CPU-intensive bcrypt hashing in thread pool
            loop = asyncio.get_event_loop()
            hashed = cast(
                str, await loop.run_in_executor(None, self.pwd_context.hash, truncated_password)
            )
            return hashed
        except Exception as e:
            logger.error(f"Bcrypt hashing failed: {e}", exc_info=True)
            raise RuntimeError(f"Password hashing failed: {str(e)}") from e

    async def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verifieer een wachtwoord tegen de hash (async-safe)

        Uses run_in_executor to prevent blocking the async event loop.
        Bcrypt verification with 12 rounds takes ~200-400ms, which would
        block async operations if run synchronously.

        Args:
            plain_password: Plain text wachtwoord
            hashed_password: Gehashed wachtwoord uit database

        Returns:
            True als wachtwoord correct is, anders False

        Raises:
            TypeError: If plain_password is not a string
            ValueError: If plain_password is None, empty, or contains non-ASCII characters
            RuntimeError: If bcrypt verification fails
        """
        # Defensive input validation and ASCII-only enforcement
        self._validate_ascii_only(plain_password)

        # Validate hashed_password
        if hashed_password is None:
            raise ValueError("Hashed password cannot be None")

        if not isinstance(hashed_password, str):
            raise TypeError(
                f"Hashed password must be a string, got {type(hashed_password).__name__}"
            )

        if not hashed_password:
            raise ValueError("Hashed password cannot be empty")

        # Truncate password to 72 bytes for bcrypt
        truncated_password = self._truncate_password(plain_password)

        try:
            # Run CPU-intensive bcrypt verification in thread pool
            loop = asyncio.get_event_loop()
            is_valid = cast(
                bool,
                await loop.run_in_executor(
                    None, self.pwd_context.verify, truncated_password, hashed_password
                ),
            )
            return is_valid
        except Exception as e:
            logger.error(f"Bcrypt verification failed: {e}", exc_info=True)
            raise RuntimeError(f"Password verification failed: {str(e)}") from e

    async def create_token_pair(
        self,
        user_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, str]:
        """
        Create both access and refresh tokens for a user.

        Args:
            user_data: User data to encode (must include 'id', 'email', 'tenant_id', 'roles')

        Returns:
            Dictionary with 'access_token' and 'refresh_token' keys
        """
        # Access token: short-lived (default 60 minutes)
        access_token = self.create_access_token(cast(JWTPayload, user_data))

        # Refresh token: long-lived (7 days), via de REFRESH-fabriek.
        # De body-claim `token_type` is hier weggehaald: gemeten op 2026-09-11 werd hij
        # op exact deze plek geschreven en op NUL plekken als claim gelezen. Het soort
        # zit nu in de JOSE-header, waar de controle hem ook zoekt.
        refresh_payload = {
            **user_data,
            "jti": str(uuid.uuid4()),
        }
        refresh_token = self.create_refresh_token(
            cast(JWTPayload, refresh_payload), expires_delta=timedelta(days=7)
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }


class _LazyProxy:
    """Proxy that instantiates the real object on first attribute access."""

    def __init__(self, factory: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._factory = factory
        self._instance: Any = None

    def _get_instance(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    def __getattr__(self, name: str) -> Any:  # TODO(TYPE): replace with concrete type
        return getattr(self._get_instance(), name)

    def __call__(
        self, *args: Any, **kwargs: Any
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        return self._get_instance()(*args, **kwargs)

    def __repr__(self) -> str:
        if self._instance is None:
            return f"_LazyProxy({self._factory.__qualname__}, not initialized)"
        return repr(self._instance)

    @property
    def __class__(self) -> type:
        return cast(type, self._get_instance().__class__)

    @__class__.setter
    def __class__(self, value: type) -> None:
        pass


jwt_handler = _LazyProxy(JWTHandler)


def get_jwt_handler() -> "_LazyProxy":
    """Return the lazy-initialized JWT handler proxy."""
    return jwt_handler


def get_password_hash(password: str) -> str:
    """Synchronous wrapper for password hashing (mainly for tests/scripts)"""
    jwt_handler._validate_ascii_only(password)
    truncated = jwt_handler._truncate_password(password)
    return cast(str, jwt_handler.pwd_context.hash(truncated))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Synchronous wrapper for password verification"""
    jwt_handler._validate_ascii_only(plain_password)
    truncated = jwt_handler._truncate_password(plain_password)
    return cast(bool, jwt_handler.pwd_context.verify(truncated, hashed_password))
