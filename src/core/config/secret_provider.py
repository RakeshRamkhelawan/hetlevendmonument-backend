"""
Unified Secret Provider - Production-ready secret management
Supports: Environment variables, .env files, file-based secrets, with audit trail
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import NamedTuple
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CacheRegel(NamedTuple):
    """Een gecachete secret MET zijn herkomst (ADR-036 OP-243).

    De herkomst hoort erbij: zonder haar logde de cache-hit in `get_secret()` een vaste
    `ENV_VAR` voor waarden die uit een bestand, een Kubernetes-secret of een generator
    kwamen.
    """

    waarde: str
    vervalt: "datetime"
    bron: "SecretSource"
    detail: str | None = None


class SecretSource(str, Enum):
    """Source where secret was retrieved from"""

    VAULT = "vault"
    KUBERNETES = "kubernetes"
    DOCKER_SECRETS = "docker_secrets"
    ENV_VAR = "env_var"
    #: Waarde uit een .env-bestand. Bestond tot 2026-09-15 niet, waardoor een
    #: bestandswaarde als ENV_VAR werd geboekt (ADR-036 OP-243).
    DOTENV_FILE = "dotenv_file"
    CONFIG_DB = "config_db"
    GENERATED = "generated"
    NOT_FOUND = "not_found"


class SecretAuditEntry(BaseModel):
    """Audit log entry for secret access"""

    timestamp: str
    action: str  # RETRIEVED, ROTATED, ACCESSED, CREATED
    secret_key: str
    source: SecretSource
    #: Welk bestand of pad de waarde leverde, als dat bekend is. `SecretSource` zegt
    #: "uit een dotenv-bestand" maar niet WELK -- en juist dat onderscheid deed ertoe
    #: (ADR-036 OP-243): `.env` is getrackt, `.env.local` is gitignored en bestaat
    #: alleen op die ene machine. Bewust GEEN enum-waarde per bestand: het aantal
    #: bestanden ligt niet vast en een enum die met de mapinhoud meegroeit is geen enum.
    source_detail: str | None = None
    status: str  # success, failure, generated
    user_id: str | None = None
    environment: str | None = None


class SecretProvider:
    """
    Unified secret provider with multi-source support and audit trail.

    Supports retrieval from:
    - Environment variables
    - .env files (.env, .env.local, .env.{environment})
    - File-based secrets (Kubernetes, Docker Swarm)
    - Generated secrets (development only, non-sensitive)

    Features:
    - Per-environment configuration
    - Result caching with TTL
    - Audit trail for compliance
    - Graceful fallback mechanisms
    - Secret validation
    """

    # Sensitive keys that should NEVER be generated
    SENSITIVE_PATTERNS = {
        "JWT",
        "SECRET",
        "PASSWORD",
        "KEY",
        "TOKEN",
        "API_KEY",
        "CREDENTIAL",
        "AUTH",
        "PRIVATE",
        "DATABASE_URL",
        "REDIS_URL",
    }

    # .env file search paths
    ENV_PATHS = [
        Path.cwd() / ".env.local",  # Highest priority (developer-specific)
        Path.cwd() / ".env.{environment}",
        Path.cwd() / ".env.development",
        Path.cwd() / ".env",
    ]

    def __init__(
        self,
        environment: str = "development",
        cache_ttl: int = 3600,
        audit_enabled: bool = True,
        strict_mode: bool = False,  # Fail on missing secrets
    ) -> None:
        """
        Initialize SecretProvider

        Args:
            environment: One of 'development', 'staging', 'production'
            cache_ttl: Cache time-to-live in seconds
            audit_enabled: Enable audit logging for all secret access
            strict_mode: If True, raise error on missing secrets instead of falling back
        """
        self.environment = environment
        self.cache_ttl = cache_ttl
        self.audit_enabled = audit_enabled
        self.strict_mode = strict_mode

        # Cache: {key: CacheRegel(waarde, vervalt, bron, detail)}
        #
        # De HERKOMST hoort hierbij (ADR-036 OP-243). Tot 2026-09-15 stond hier alleen
        # (waarde, vervaltijd) en logde de cache-hit hieronder een vaste `ENV_VAR`. Omdat
        # de cache na ELKE geslaagde lookup wordt gevuld, meldde het auditspoor vanaf de
        # tweede aanroep `env_var` voor waarden uit een .env-bestand, een Kubernetes- of
        # Docker-secret, een GEGENEREERDE willekeurige waarde en zelfs een default. Die
        # laatste twee zijn de ernstigste: een efemeer secret dat als omgevingsvariabele
        # geboekt staat, leest als iets wat iemand bewust heeft gezet. ADR-019 leunt op
        # deze keten en een lezer meet niet opnieuw.
        self.cache: dict[str, CacheRegel] = {}

        # Audit trail
        self.audit_log: list[SecretAuditEntry] = []

        # Load environment files on initialization
        self._loaded_env_files: dict[str, bool] = {}
        self._load_env_files()

    def _load_env_files(self) -> None:
        """Load .env files in order of priority"""
        # Laden van LAAGSTE naar HOOGSTE prioriteit -- elke volgende overschrijft de vorige
        # in de cache.
        #
        # Deze volgorde is op 2026-09-15 omgedraaid (ADR-036 OP-243). Hij was:
        # .env.{omgeving}, dan .env.local, dan de generieke .env als LAATSTE -- waardoor het
        # generieke bestand won van het lokale, terwijl de comment erboven .env.local
        # "developer overrides" noemde. Gemeten met een test die .env en .env.local allebei
        # een waarde gaf: `get_secret()` gaf de waarde uit .env.
        #
        # Erger dan de fout zelf: `src/core/env_loader.py` doet het precies ANDERSOM
        # (.env.local wint). Twee laders in dezelfde codebase die het oneens zijn over welk
        # bestand wint, is niet af te leiden uit de code die ze gebruikt. Nu volgen beide
        # dezelfde regel: generiek -> omgevingsspecifiek -> lokaal.
        env_generic = Path.cwd() / ".env"
        if env_generic.exists():
            self._load_from_file(env_generic)
            self._loaded_env_files[".env"] = True

        env_specific = Path.cwd() / f".env.{self.environment}"
        if env_specific.exists():
            self._load_from_file(env_specific)
            self._loaded_env_files[f".env.{self.environment}"] = True

        env_local = Path.cwd() / ".env.local"
        if env_local.exists():
            self._load_from_file(env_local)
            self._loaded_env_files[".env.local"] = True

        logger.info(f"Loaded .env files: {list(self._loaded_env_files.keys())}")

    def _load_from_file(self, file_path: Path) -> None:
        """Load secrets from .env file"""
        try:
            with open(file_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        # Store in cache for immediate access
                        # Use a special marker to indicate it came from file
                        expiry = datetime.now(timezone.utc) + timedelta(seconds=self.cache_ttl)
                        self.cache[key.strip()] = CacheRegel(
                            waarde=value.strip(),
                            vervalt=expiry,
                            bron=SecretSource.DOTENV_FILE,
                            detail=file_path.name,
                        )
        except Exception as e:
            logger.warning(f"Failed to load {file_path}: {e}")

    def get_secret(
        self, key: str, default: str | None = None, allow_generation: bool = False
    ) -> str | None:
        """
        Retrieve a secret with fallback chain.

        Retrieval order varies by environment:
        - Production: Env -> File -> Error (no defaults)
        - Staging: Env -> File -> Default
        - Development: Env -> File -> Generated (if allowed) -> Default

        Args:
            key: Secret key to retrieve
            default: Default value if secret not found
            allow_generation: Allow generating random secret (dev only)

        Returns:
            Secret value or None

        Raises:
            ValueError: If secret required in production and not found
        """
        # Check cache first
        if key in self.cache:
            regel = self.cache[key]
            if datetime.now(timezone.utc) < regel.vervalt:
                self._audit_log(
                    action="RETRIEVED",
                    key=key,
                    source=regel.bron,
                    status="success",
                    source_detail=regel.detail,
                )
                return regel.waarde

        secret = None
        source = SecretSource.NOT_FOUND

        # 1. Try environment variable
        secret = os.getenv(key)
        if secret:
            source = SecretSource.ENV_VAR

        # 2. Try .env files (already in cache from _load_env_files)
        bron_detail: str | None = None
        if not secret and key in self.cache:
            regel = self.cache[key]
            secret, source, bron_detail = regel.waarde, regel.bron, regel.detail

        # 3. Try file-based secrets (Kubernetes/Docker Secrets)
        if not secret:
            secret, source_found = self._get_from_file_secrets(key)
            if secret:
                source = source_found

        # 4. Generate random secret (development only, non-sensitive)
        if not secret and allow_generation and self.environment == "development":
            if not self._is_sensitive(key):
                secret = secrets.token_urlsafe(32)
                source = SecretSource.GENERATED
                logger.warning(f"Generated random secret for {key}")

        # 5. Use default
        if not secret and default is not None:
            secret = default

        # Cache the result
        if secret:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=self.cache_ttl)
            self.cache[key] = CacheRegel(
                waarde=secret, vervalt=expiry, bron=source, detail=bron_detail
            )
            self._audit_log(
                action="RETRIEVED",
                key=key,
                source=source,
                status="success",
                source_detail=bron_detail,
            )
            return secret

        # Handle missing secret
        self._audit_log(
            action="RETRIEVED", key=key, source=SecretSource.NOT_FOUND, status="failure"
        )

        if self.strict_mode or self._is_sensitive(key):
            if self.environment == "production":
                raise ValueError(
                    f"CRITICAL: Required secret '{key}' not found in production. "
                    f"Please set {key} environment variable or in .env file."
                )
            elif self.environment == "staging":
                raise ValueError(
                    f"Required secret '{key}' not found in staging. "
                    f"Please set {key} environment variable or in .env.staging file."
                )

        return None

    def _get_from_file_secrets(self, key: str) -> tuple[str | None, SecretSource]:
        """
        Try to load from file-based secrets (Kubernetes or Docker Secrets)

        Kubernetes: /var/run/secrets/kubernetes.io/serviceaccount/
        Docker Swarm: /run/secrets/
        """
        # Try Kubernetes secrets
        k8s_paths = [
            f"/var/run/secrets/kubernetes.io/{key.lower()}",
            f"/var/run/secrets/{key.lower()}",
        ]

        for path in k8s_paths:
            if Path(path).exists():
                try:
                    with open(path) as f:
                        return f.read().strip(), SecretSource.KUBERNETES
                except Exception as e:
                    logger.warning(f"Failed to read Kubernetes secret {key}: {e}")

        # Try Docker Swarm secrets
        docker_secret_path = f"/run/secrets/{key.lower()}"
        if Path(docker_secret_path).exists():
            try:
                with open(docker_secret_path) as f:
                    return f.read().strip(), SecretSource.DOCKER_SECRETS
            except Exception as e:
                logger.warning(f"Failed to read Docker secret {key}: {e}")

        return None, SecretSource.NOT_FOUND

    def _is_sensitive(self, key: str) -> bool:
        """Check if key appears to be a sensitive secret"""
        upper_key = key.upper()
        return any(pattern in upper_key for pattern in self.SENSITIVE_PATTERNS)

    def _audit_log(
        self,
        action: str,
        key: str,
        source: SecretSource,
        status: str,
        user_id: str | None = None,
        source_detail: str | None = None,
    ) -> None:
        """Log secret access for compliance and debugging"""
        if not self.audit_enabled:
            return

        entry = SecretAuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            secret_key=key,
            source=source,
            source_detail=source_detail,
            status=status,
            user_id=user_id,
            environment=self.environment,
        )
        self.audit_log.append(entry)

        # Log to application logger
        log_level = logging.WARNING if status == "failure" else logging.INFO
        logger.log(
            log_level,
            f"Secret {action}: key={key}, source={source.value}, status={status}",
        )

    def get_audit_trail(
        self, key: str | None = None, action: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get audit trail for compliance reporting

        Args:
            key: Filter by secret key
            action: Filter by action type
            limit: Maximum number of entries

        Returns: List[Any] of audit entries  # TODO(TYPE): replace Any with concrete type
        """
        entries = self.audit_log

        if key:
            entries = [e for e in entries if e.secret_key == key]

        if action:
            entries = [e for e in entries if e.action == action]

        return [e.model_dump() for e in entries[-limit:]]

    def validate_production_secrets(self) -> tuple[bool, list[str]]:
        """
        Validate that all required production secrets are configured.

        Returns:
            (is_valid, list_of_missing_secrets)
        """
        if self.environment != "production":
            return True, []

        required_secrets = {
            "JWT_SECRET_KEY": "Authentication token signing",
            "DATABASE_URL": "Database connection",
            "REDIS_URL": "Cache and session store",
        }

        missing: list[str] = []
        for secret_key, description in required_secrets.items():
            if not self.get_secret(secret_key):
                missing.append(f"{secret_key} ({description})")

        return len(missing) == 0, missing

    def get_loaded_env_files(self) -> dict[str, bool]:
        """Get list of .env files that were successfully loaded"""
        return self._loaded_env_files


# Global instance
_secret_provider: SecretProvider | None = None


def get_secret_provider(environment: str | None = None) -> SecretProvider:
    """
    Get or create the global SecretProvider instance

    Args:
        environment: Override environment from ENVIRONMENT env var

    Returns:
        SecretProvider instance
    """
    global _secret_provider

    if _secret_provider is None:
        env = cast(str, environment or os.getenv("ENVIRONMENT", "development"))
        _secret_provider = SecretProvider(environment=env, strict_mode=(env == "production"))

    return _secret_provider


def get_secret(key: str, default: str | None = None, allow_generation: bool = False) -> str | None:
    """
    Convenience function to get a secret using the global provider

    Usage:
        jwt_secret = get_secret("JWT_SECRET_KEY")
    """
    return get_secret_provider().get_secret(key, default, allow_generation)
