import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import jwt


class TokenService:
    def __init__(
        self, metrics: Any, key_path: str = "keys"
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        self.metrics = metrics
        self.key_path = key_path
        self.current_key_id: str | None = None
        self.keys: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self._ensure_key_path()
        self._load_or_generate_keys()

    def _ensure_key_path(self) -> None:
        if not os.path.exists(self.key_path):
            os.makedirs(self.key_path)

    def _load_or_generate_keys(self) -> None:
        if not os.path.exists(f"{self.key_path}/private.pem"):
            self._generate_new_keypair()
        else:
            self._load_existing_keys()

    def _generate_new_keypair(self) -> None:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        # Generate new RSA key pair
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )

        # Serialize private key
        pem_private = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,  # pyright: ignore[reportArgumentType]
            format=serialization.PrivateFormat.PKCS8,  # pyright: ignore[reportArgumentType]
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Serialize public key
        pem_public = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,  # pyright: ignore[reportArgumentType]
            format=serialization.PublicFormat.SubjectPublicKeyInfo,  # pyright: ignore[reportArgumentType]
        )

        # Save keys
        with open(f"{self.key_path}/private.pem", "wb") as f:
            f.write(pem_private)
        with open(f"{self.key_path}/public.pem", "wb") as f:
            f.write(pem_public)

        self._load_existing_keys()

    def _load_existing_keys(self) -> None:
        with open(f"{self.key_path}/private.pem", "rb") as f:
            self.private_key = f.read()
        with open(f"{self.key_path}/public.pem", "rb") as f:
            self.public_key = f.read()

        self.current_key_id = str(uuid4())
        self.keys[self.current_key_id] = {
            "private": self.private_key,
            "public": self.public_key,
        }

    def create_token(
        self, user_id: str, claims: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        start_time = datetime.now(timezone.utc)
        try:
            payload = {
                "sub": user_id,
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                "jti": str(uuid4()),
            }
            if claims:
                payload.update(claims)

            token = jwt.encode(
                payload,
                self.private_key,
                algorithm="RS256",
                headers={"kid": self.current_key_id},
            )

            self.metrics.track_validation(start_time.timestamp(), success=True)

            return token if isinstance(token, str) else token.decode("utf-8")

        except Exception as e:
            self.metrics.track_validation(start_time.timestamp(), success=False, reason=str(e))
            raise

    def validate_token(
        self, token: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        start_time = datetime.now(timezone.utc)
        try:
            unverified_headers = jwt.get_unverified_header(token)
            key_id = unverified_headers.get("kid")

            if not key_id or key_id not in self.keys:
                raise jwt.InvalidTokenError("Invalid key ID")

            payload: dict[str, Any] = jwt.decode(  # TODO(TYPE): replace Any with concrete type
                token, self.keys[key_id]["public"], algorithms=["RS256"]
            )

            self.metrics.track_validation(start_time.timestamp(), success=True)

            return payload

        except Exception as e:
            self.metrics.track_validation(start_time.timestamp(), success=False, reason=str(e))
            raise
