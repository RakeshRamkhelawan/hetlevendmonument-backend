"""
JWT Token Handling for Tool Broker Service

Provides secure token creation, validation, and management with:
- HS256 signing algorithm
- Configurable expiration times
- Token payload validation
- Secure secret management
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class TokenData(BaseModel):
    """Validated token data extracted from JWT"""

    username: str
    scopes: list[str] = Field(default_factory=list)
    user_id: str | None = None
    exp: datetime | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "admin_user",
                "scopes": ["tool:execute", "tool:read"],
                "user_id": "user_123",
                "exp": "2025-10-18T10:30:00Z",
            }
        }
    )


class TokenPayload(BaseModel):
    """Payload structure for JWT token creation"""

    username: str
    scopes: list[str] = Field(default_factory=list)
    user_id: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "admin_user",
                "scopes": ["tool:execute"],
                "user_id": "user_123",
            }
        }
    )


class JWTHandler:
    """Handles JWT token creation and validation"""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
    ) -> None:
        """
        Initialize JWT handler

        Args:
            secret_key: Secret key for signing tokens (keep private!)
            algorithm: JWT algorithm (default: HS256)
            access_token_expire_minutes: Token expiration time in minutes

        Raises:
            ValueError: If secret key is too short or algorithm unsupported
        """
        if len(secret_key) < 32:
            logger.warning("Secret key is shorter than 32 characters - security risk!")

        if algorithm not in ["HS256", "HS384", "HS512"]:
            raise ValueError(f"Unsupported algorithm: {algorithm}. Use HS256, HS384, or HS512")

        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes

    def create_access_token(
        self, payload: TokenPayload, expires_delta: timedelta | None = None
    ) -> str:
        """
        Create a new JWT access token

        Args:
            payload: Token payload data
            expires_delta: Optional custom expiration time

        Returns:
            Encoded JWT token as string

        Example:
            >>> handler = JWTHandler(secret_key="secret123", access_token_expire_minutes=30)
            >>> payload = TokenPayload(username="admin", scopes=["tool:execute"])
            >>> token = handler.create_access_token(payload)
            >>> print(token)  # eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
        """
        to_encode = payload.model_dump()

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=self.access_token_expire_minutes
            )

        to_encode.update({"exp": expire})

        try:
            jwt_token: str = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            logger.debug(f"Token created for user: {payload.username}")
            return jwt_token
        except Exception as e:
            logger.error(f"Failed to create token: {str(e)}")
            raise

    def validate_token(self, token: str) -> TokenData:
        """
        Validate and decode a JWT token

        Args:
            token: JWT token string

        Returns:
            Validated TokenData

        Raises:
            JWTError: If token is invalid, expired, or tampered
            ValueError: If required claims missing

        Example:
            >>> handler = JWTHandler(secret_key="secret123")
            >>> token_data = handler.validate_token(token)
            >>> print(token_data.username)  # "admin"
            >>> print(token_data.scopes)  # ["tool:execute"]
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            username: str = payload.get("username") or ""
            if not username:
                logger.warning("Token missing 'username' claim")
                raise ValueError("Token missing required 'username' claim")

            scopes: list[str] = payload.get("scopes", [])
            user_id: str = payload.get("user_id") or ""
            exp_timestamp: int = payload.get("exp") or 0

            exp = None
            if exp_timestamp:
                exp = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

            logger.debug(f"Token validated for user: {username}")

            return TokenData(username=username, scopes=scopes, user_id=user_id, exp=exp)

        except JWTError as e:
            logger.error(f"JWT validation failed: {str(e)}")
            raise
        except ValueError as e:
            logger.error(f"Token payload validation failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during token validation: {str(e)}")
            raise

    def is_token_expired(self, token_data: TokenData) -> bool:
        """
        Check if a token has expired

        Args:
            token_data: Validated token data

        Returns:
            True if token expired, False otherwise
        """
        if not token_data.exp:
            return False

        return datetime.now(timezone.utc) > token_data.exp

    def get_remaining_seconds(self, token_data: TokenData) -> int | None:
        """
        Get remaining time until token expiration

        Args:
            token_data: Validated token data

        Returns:
            Remaining seconds until expiration, or None if no expiration
        """
        if not token_data.exp:
            return None

        remaining = token_data.exp - datetime.now(timezone.utc)
        return max(0, int(remaining.total_seconds()))


# Factory function for easier use
def create_jwt_handler(
    secret_key: str, algorithm: str = "HS256", expire_minutes: int = 30
) -> JWTHandler:
    """Factory function to create JWT handler"""
    return JWTHandler(
        secret_key=secret_key,
        algorithm=algorithm,
        access_token_expire_minutes=expire_minutes,
    )
