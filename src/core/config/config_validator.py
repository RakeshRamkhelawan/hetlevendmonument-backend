"""
SC-11.2: Configuration Validation at Startup
Validates all configuration on application startup.
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ConfigSeverity(str, Enum):
    ERROR = "error"  # Application cannot start
    WARNING = "warning"  # Application can start but feature may not work
    INFO = "info"  # Informational


@dataclass
class ConfigIssue:
    """Represents a configuration issue."""

    key: str
    message: str
    severity: ConfigSeverity
    current_value: Any = None
    suggested_value: Any = None


@dataclass
class ConfigValidationResult:
    """Result of configuration validation."""

    valid: bool
    issues: list[ConfigIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ConfigIssue]:
        return [i for i in self.issues if i.severity == ConfigSeverity.ERROR]

    @property
    def warnings(self) -> list[ConfigIssue]:
        return [i for i in self.issues if i.severity == ConfigSeverity.WARNING]


class ConfigValidator:
    """
    SC-11.2: Validates application configuration at startup.

    Checks:
    - Required environment variables
    - Valid formats (URLs, ports, etc.)
    - Sensible defaults
    - Security concerns
    """

    # Required environment variables (PRODUCTION-CRITICAL)
    REQUIRED_VARS = [
        ("DATABASE_URL", "Database connection string"),
        ("SECRET_KEY", "Secret key for session management"),
        ("JWT_SECRET_KEY", "JWT signing secret key"),
    ]

    # Required in production only
    # NOTE: POSTGRES_USER/POSTGRES_PASSWORD omitted -- app uses DATABASE_URL (full connection
    # string) directly. Separate user/password vars are not set by the CD workflow.
    PRODUCTION_REQUIRED_VARS = [
        ("REDIS_URL", "Redis connection URL"),
        ("API_BASE_URL", "Production API base URL"),
        ("FRONTEND_URL", "Production frontend URL"),
        # ADR-036 OP-27. Zonder deze sleutel weigert elke tool-uitvoering; falen bij het
        # opstarten is dus beter dan bij de eerste tool-aanroep. Toegevoegd nadat de sleutel in
        # beide CD-workflows en de blue/green-compose is geprovisioneerd -- die volgorde is de
        # kern: eerder toevoegen verplaatst een luide deploy-fout naar een stille toolstoring.
        #
        # Deze lijst wordt doorlopen voor ENVIRONMENT "production", "staging", "blue" en
        # "green" (zie `validate()`) -- ADR-036 OP-30, gesloten 2026-08-27: blue/green is ook
        # een productietechniek, en de compose-bestanden in deployment/blue_green/ zetten
        # inmiddels ALLE vier de variabelen hierboven (geen ontbrekende meer, gemeten).
        (
            "TOOL_PAYLOAD_PSEUDONYM_KEY",
            "HMAC key for tool payload pseudonymisation (ADR-036 OP-27)",
        ),
    ]

    # Optional but recommended
    RECOMMENDED_VARS = [
        ("REDIS_URL", "Redis connection for caching"),
        ("GOOGLE_API_KEY", "Google AI API key"),
        ("OPENAI_API_KEY", "OpenAI API key"),
        ("SENTRY_DSN", "Error tracking"),
    ]

    # LLM provider -> required API key mapping
    _LLM_PROVIDER_KEYS: dict[str, tuple[str, str]] = {
        "mistral": ("MISTRAL_API_KEY", "Mistral AI (EU) API key for LLM requests"),
        "deepseek": ("DEEPSEEK_API_KEY", "DeepSeek API key for LLM requests"),
        "google": ("GOOGLE_API_KEY", "Google Gemini API key for LLM requests"),
        "anthropic": ("ANTHROPIC_API_KEY", "Anthropic Claude API key for LLM requests"),
    }

    # Security-sensitive defaults to warn about
    INSECURE_DEFAULTS = {
        "SECRET_KEY": [
            "secret",
            "changeme",
            "your-secret-key",
            "supersecret",
            "dev-secret",
            "a_default_secret_key_that_must_be_overridden_in_production",
            "dev-static-secret-key-for-stability-12345",
            "your-secret-key-change-in-production",
        ],
        "JWT_SECRET_KEY": [
            "secret",
            "changeme",
            "your-jwt-key",
            "dev-jwt-secret",
            "a_default_secret_key_that_must_be_overridden_in_production",
            "dev-static-secret-key-for-stability-12345",
            "your-secret-key-change-in-production",
        ],
        "POSTGRES_PASSWORD": ["postgres", "password", "admin"],
        "REDIS_PASSWORD": ["changeme", "redis"],
        "DEBUG": ["true", "1", "yes"],
    }

    def __init__(self) -> None:
        self.issues: list[ConfigIssue] = []

    def validate(self) -> ConfigValidationResult:
        """Run all configuration validations."""
        self.issues = []
        environment = os.getenv("ENVIRONMENT", "development")

        self._check_required_vars()

        # ONGECONDITIONEERD, en dat is het verschil met `_check_secret_strength()` hieronder.
        # De runtime (`redaction.pseudonymisation_key()`) weigert een zwakke sleutel in ELKE
        # omgeving zodra hij gezet is -- niet alleen in production/staging. Zat deze check achter
        # de omgevingsgate, dan haalt een zwakke sleutel de boot-check in development, test, blue
        # en green terwijl de runtime hem daar weigert. Dat is dezelfde stille storing waarvoor de
        # sterkte-eis hier staat, alleen langs de omgevingsas. (ADR-036 OP-27 ronde 5; de gate
        # zelf is OP-30 en blijft open voor de overige variabelen.)
        self._check_pseudonymisation_key_strength()

        # Production requires additional checks. Blue/green zijn ADR-036 OP-30: blue/green is
        # ook een productietechniek (deployment/blue_green/), en de compose-bestanden daar
        # zetten nu ook API_BASE_URL/FRONTEND_URL (zie docker-compose.blue.yml/green.yml) zodat
        # deze gate ze niet als ontbrekend meldt.
        if environment in ("production", "staging", "blue", "green"):
            self._check_production_required_vars()
            self._check_secret_strength()

        self._check_recommended_vars()
        self._check_llm_provider_config()
        self._check_security_issues()
        self._check_pydantic_placeholder_defaults()
        self._check_database_url()
        self._check_ports()

        has_errors = any(i.severity == ConfigSeverity.ERROR for i in self.issues)

        return ConfigValidationResult(valid=not has_errors, issues=self.issues)

    def _check_required_vars(self) -> None:
        """Check for required environment variables."""
        environment = os.getenv("ENVIRONMENT", "development")
        for var_name, description in self.REQUIRED_VARS:
            # SECRET_KEY and JWT_SECRET_KEY are optional in development (auto-generated if missing)
            if var_name in ("JWT_SECRET_KEY", "SECRET_KEY") and environment != "production":
                continue

            value = os.getenv(var_name)
            if not value:
                self.issues.append(
                    ConfigIssue(
                        key=var_name,
                        message=f"Required variable not set: {description}",
                        severity=ConfigSeverity.ERROR,
                    )
                )

    def _check_production_required_vars(self) -> None:
        """Check for production-specific required variables."""
        for var_name, description in self.PRODUCTION_REQUIRED_VARS:
            value = os.getenv(var_name)
            if not value:
                self.issues.append(
                    ConfigIssue(
                        key=var_name,
                        message=f"Production: Required variable not set: {description}",
                        severity=ConfigSeverity.ERROR,
                    )
                )

    def _check_pseudonymisation_key_strength(self) -> None:
        """De tool-payload-pseudonimiseringssleutel, met DEZELFDE eis als de runtime.

        ADR-036 OP-27: aanwezigheid is niet genoeg. Een zwakke sleutel komt door de
        aanwezigheidscheck heen en wordt daarna door de runtime geweigerd -- dus de deploy slaagt
        en elke tool-aanroep faalt. Dat is exact de stille storing die deze boot-check moet
        voorkomen.

        De eis komt uit `redaction.key_strength_problem()`: DEZELFDE functie die
        `pseudonymisation_key()` gebruikt. Een eigen kopie van de eis hier zou precies de
        divergentie toelaten die deze docstring beschrijft. Tot 2026-08-04 was de eis aan beide
        kanten "lengte", en dat viel toevallig samen; een entropie-eis die alleen in de runtime
        zou landen, bouwt de storing opnieuw. Een functie, twee aanroepers.
        """
        from src.core.tool_broker.redaction import KEY_ENV_VAR, key_strength_problem

        pseudonym_key = os.getenv(KEY_ENV_VAR, "")
        if not pseudonym_key:
            # Afwezigheid is hier geen fout: buiten production/staging mag de runtime een
            # ephemere sleutel gebruiken, en voor die twee omgevingen dekt
            # PRODUCTION_REQUIRED_VARS de aanwezigheid al.
            return

        problem = key_strength_problem(pseudonym_key)
        if problem is not None:
            self.issues.append(
                ConfigIssue(
                    key=KEY_ENV_VAR,
                    message=(
                        f"Tool payload pseudonymisation key {problem} "
                        'Generate with: python -c "import secrets; '
                        'print(secrets.token_urlsafe(32))"'
                    ),
                    severity=ConfigSeverity.ERROR,
                    current_value=f"[Length: {len(pseudonym_key)}]",
                )
            )

    def _check_secret_strength(self) -> None:
        """Check that secrets meet minimum security requirements."""

        # Check SECRET_KEY strength (min 32 chars for hex, 32 bytes for base64)
        secret_key = os.getenv("SECRET_KEY", "")
        if secret_key and len(secret_key) < 32:
            self.issues.append(
                ConfigIssue(
                    key="SECRET_KEY",
                    message=f"Secret key too short (min 32 chars, got {len(secret_key)})",
                    severity=ConfigSeverity.ERROR,
                    current_value=f"[Length: {len(secret_key)}]",
                )
            )

        # Check JWT_SECRET_KEY strength
        jwt_secret = os.getenv("JWT_SECRET_KEY", "")
        if jwt_secret and len(jwt_secret) < 32:
            self.issues.append(
                ConfigIssue(
                    key="JWT_SECRET_KEY",
                    message=f"JWT secret key too short (min 32 chars, got {len(jwt_secret)})",
                    severity=ConfigSeverity.ERROR,
                    current_value=f"[Length: {len(jwt_secret)}]",
                )
            )

        # Check database password strength
        db_password = os.getenv("POSTGRES_PASSWORD", "")
        if db_password and len(db_password) < 16:
            self.issues.append(
                ConfigIssue(
                    key="POSTGRES_PASSWORD",
                    message=f"Database password too weak (min 16 chars, got {len(db_password)})",
                    severity=ConfigSeverity.WARNING,
                    current_value=f"[Length: {len(db_password)}]",
                )
            )

    def _check_recommended_vars(self) -> None:
        """Check for recommended but optional variables."""
        for var_name, description in self.RECOMMENDED_VARS:
            value = os.getenv(var_name)
            if not value:
                self.issues.append(
                    ConfigIssue(
                        key=var_name,
                        message=f"Recommended variable not set: {description}",
                        severity=ConfigSeverity.WARNING,
                    )
                )

    def _check_llm_provider_config(self) -> None:
        """Validate that the configured LLM_PROVIDER has its required API key."""
        provider = os.getenv("LLM_PROVIDER", "auto").lower()
        if provider == "deepseek":
            # ADR-041 B14: DeepSeek (China, geen verwerkersovereenkomst) mag niet met klantgegevens.
            self.issues.append(
                ConfigIssue(
                    key="LLM_PROVIDER",
                    severity=ConfigSeverity.WARNING,
                    message="LLM_PROVIDER=deepseek: DeepSeek mag niet met klantgegevens "
                    "(ADR-041 B14); zet LLM_PROVIDER=mistral en MISTRAL_API_KEY.",
                )
            )
        if provider == "auto" or provider not in self._LLM_PROVIDER_KEYS:
            # auto = GuaranteedLLMService picks from available keys; checked below
            for p, (key_name, description) in self._LLM_PROVIDER_KEYS.items():
                if os.getenv("LLM_PROVIDER") is None and not os.getenv(key_name):
                    self.issues.append(
                        ConfigIssue(
                            key=key_name,
                            severity=ConfigSeverity.WARNING,
                            message=f"No LLM provider key set - {description}. "
                            f"Fallback chain will skip {p}.",
                        )
                    )
            return

        key_name, description = self._LLM_PROVIDER_KEYS[provider]
        if not os.getenv(key_name):
            self.issues.append(
                ConfigIssue(
                    key=key_name,
                    severity=ConfigSeverity.ERROR,
                    message=f"LLM_PROVIDER={provider} requires {key_name} but it is not set.",
                )
            )

    def _check_security_issues(self) -> None:
        """Check for insecure default values."""
        env = os.getenv("ENVIRONMENT", "development")

        if env in ("production", "staging"):
            for var_name, insecure_values in self.INSECURE_DEFAULTS.items():
                value = os.getenv(var_name, "").lower()
                if value in [v.lower() for v in insecure_values]:
                    self.issues.append(
                        ConfigIssue(
                            key=var_name,
                            message=f"Insecure default value in {env} environment",
                            severity=ConfigSeverity.ERROR,
                            current_value="[REDACTED]",
                        )
                    )

            # Check DEBUG mode
            if os.getenv("DEBUG", "").lower() in ("true", "1", "yes"):
                self.issues.append(
                    ConfigIssue(
                        key="DEBUG",
                        message="DEBUG mode should be disabled in production",
                        severity=ConfigSeverity.ERROR,
                        current_value="true",
                        suggested_value="false",
                    )
                )

    def _check_pydantic_placeholder_defaults(self) -> None:
        """Check that Pydantic Settings are not using known placeholder defaults."""
        environment = os.getenv("ENVIRONMENT", "development")
        severity = (
            ConfigSeverity.ERROR
            if environment in ("production", "staging")
            else ConfigSeverity.WARNING
        )
        known_placeholders: frozenset[str] = frozenset(
            [
                "a_default_secret_key_that_must_be_overridden_in_production",
                "dev-static-secret-key-for-stability-12345",
                "your-secret-key-change-in-production",
            ]
        )

        # Check src.core.config settings singleton
        try:
            from src.core.config import settings as settings_v1

            for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
                value = getattr(settings_v1, key, "")
                if value in known_placeholders:
                    self.issues.append(
                        ConfigIssue(
                            key=f"src.core.config.{key}",
                            message=(
                                "Placeholder secret detected in Settings - must be overridden"
                            ),
                            severity=severity,
                            current_value="[REDACTED]",
                        )
                    )
        except Exception:
            pass

        # Check src.core.config.config Settings instance
        try:
            from src.core.config.config import Settings as SettingsV2

            settings_v2 = SettingsV2()
            for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
                value = getattr(settings_v2, key, "")
                if value in known_placeholders:
                    self.issues.append(
                        ConfigIssue(
                            key=f"src.core.config.config.{key}",
                            message=(
                                "Placeholder secret detected in Settings - must be overridden"
                            ),
                            severity=severity,
                            current_value="[REDACTED]",
                        )
                    )
        except Exception:
            pass

    def _check_database_url(self) -> None:
        """Validate database URL format."""
        db_url = os.getenv("DATABASE_URL", "")

        if db_url and not any(
            db_url.startswith(p)
            for p in [
                "postgresql://",
                "postgres://",
                "postgresql+asyncpg://",
                "sqlite://",
                "sqlite+aiosqlite://",
                "mysql://",
            ]
        ):
            self.issues.append(
                ConfigIssue(
                    key="DATABASE_URL",
                    message="Invalid database URL format",
                    severity=ConfigSeverity.ERROR,
                    suggested_value="postgresql://<user>:<password>@<host>:<port>/<dbname>",
                )
            )

    def _check_ports(self) -> None:
        """Validate port configurations."""
        port_vars = ["PORT", "APP_PORT", "API_PORT"]

        for var_name in port_vars:
            value = os.getenv(var_name)
            if value:
                try:
                    port = int(value)
                    if not (1 <= port <= 65535):
                        raise ValueError("Port out of range")
                except ValueError:
                    self.issues.append(
                        ConfigIssue(
                            key=var_name,
                            message=f"Invalid port number: {value}",
                            severity=ConfigSeverity.ERROR,
                            current_value=value,
                            suggested_value="8000",
                        )
                    )


def validate_config_at_startup(exit_on_error: bool = True) -> ConfigValidationResult:
    """
    Validate configuration at application startup.

    Args:
        exit_on_error: Exit the application if critical errors are found

    Returns:
        ConfigValidationResult
    """
    validator = ConfigValidator()
    result = validator.validate()

    # Log issues
    for issue in result.issues:
        if issue.severity == ConfigSeverity.ERROR:
            logger.error(f"CONFIG ERROR - {issue.key}: {issue.message}")
        elif issue.severity == ConfigSeverity.WARNING:
            logger.warning(f"CONFIG WARNING - {issue.key}: {issue.message}")
        else:
            logger.info(f"CONFIG INFO - {issue.key}: {issue.message}")

    if result.valid:
        logger.info("Configuration validation passed")
    else:
        logger.error(f"Configuration validation failed with {len(result.errors)} errors")

        if exit_on_error:
            logger.critical("Exiting due to configuration errors")
            sys.exit(1)

    return result


# Export for startup
__all__ = [
    "ConfigValidator",
    "ConfigValidationResult",
    "ConfigIssue",
    "ConfigSeverity",
    "validate_config_at_startup",
]
