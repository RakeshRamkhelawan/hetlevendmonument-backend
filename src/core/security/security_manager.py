#!/usr/bin/env python3
"""
Production Security Manager
Comprehensive security hardening for the Sanskriti Setu AI Multi-Agent System
"""

import ipaddress
import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
from typing import Any, Optional, cast
from collections.abc import Callable, Coroutine, Sequence

import bcrypt
import jwt

from src.core.auth.token_kind import TokenKind
from src.core.auth.types import VerifiedJWTPayload
from src.core.security.types import ThreatLevel as ThreatLevel

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security levels for different operations"""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    AUTHORIZED = "authorized"
    ADMIN = "admin"
    SYSTEM = "system"


@dataclass
class SecurityEvent:
    """Security event logging"""

    event_id: str
    event_type: str
    severity: ThreatLevel
    source_ip: str
    user_id: str | None
    endpoint: str
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )


@dataclass
class RateLimitRule:
    """Rate limiting configuration"""

    endpoint_pattern: str
    requests_per_minute: int
    requests_per_hour: int
    burst_limit: int
    security_level: SecurityLevel


class ProductionSecurityManager:
    """
    Comprehensive production security manager
    Handles authentication, authorization, rate limiting, and threat detection
    """

    def __init__(self) -> None:
        from src.core.config.unified_config import config  # Import to use JWT secret from config

        self.secret_key = (
            config.jwt_secret_key or self._get_secret_key()
        )  # Use same secret as jwt_handler
        self.jwt_algorithm = "HS256"
        self.token_expiry_hours = 24

        # Security tracking
        self.security_events: list[SecurityEvent] = []
        self.failed_attempts: dict[str, list[datetime]] = {}
        self.blocked_ips: set[str] = set()
        self.rate_limits: dict[str, list[datetime]] = {}

        # Rate limiting rules
        self.rate_limit_rules = self._initialize_rate_limits()

        # Allowed IP ranges (production should configure these)
        self.allowed_ip_ranges = self._get_allowed_ip_ranges()

        # Security headers
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }

        logger.info("Production Security Manager initialized")

    def _get_secret_key(self) -> str:
        """Get or generate secure secret key"""
        # Prefer SANSKRITI_SECRET_KEY for backward compatibility,
        # fall back to JWT_SECRET_KEY so tokens created by jwt_handler
        # can be verified by the security middleware.
        secret_key = os.getenv("SANSKRITI_SECRET_KEY") or os.getenv("JWT_SECRET_KEY")
        if not secret_key:
            # Generate secure random key for development
            secret_key = secrets.token_urlsafe(32)
            logger.warning("Using generated secret key - set SANSKRITI_SECRET_KEY in production")

        return secret_key

    def _get_allowed_ip_ranges(self) -> list[str]:
        """Expliciet ingestelde IP-ranges; leeg betekent: de ingress bewaakt dit.

        Hier stond loopback + RFC1918 als default. Dat maakte van "vergeten in te
        stellen" een stille muur: op Azure Container Apps ziet de applicatie het
        PUBLIEKE client-IP, dus viel elke bezoeker buiten de default en gaf de API
        op elk pad 403 (gemeten op staging, 2026-08-29). Productie had exact dezelfde
        val en zou bij oplevering meteen onbereikbaar zijn geweest.

        Netwerktoegang hoort op de rand van het platform (Container Apps
        ingress-restricties, afgedwongen VOOR de container en niet met een header te
        omzeilen). De grens van deze applicatie is authenticatie plus tenant-isolatie.
        Wie hier toch een lijst invult, krijgt die onverkort gehandhaafd.
        ADR-036 OP-111.
        """
        allowed_ips = os.getenv("ALLOWED_IP_RANGES", "") or ""
        return [ip.strip() for ip in allowed_ips.split(",") if ip.strip()]

    def _initialize_rate_limits(self) -> list[RateLimitRule]:
        """Initialize rate limiting rules"""
        return [
            # Public endpoints - more restrictive
            RateLimitRule("/health", 60, 500, 10, SecurityLevel.PUBLIC),
            RateLimitRule("/api/v1/cva/chat", 30, 200, 5, SecurityLevel.AUTHENTICATED),
            # Phase 1 endpoints
            RateLimitRule("/api/v1/agents/*", 120, 5000, 20, SecurityLevel.AUTHENTICATED),
            RateLimitRule("/api/v1/subagents/*", 120, 5000, 20, SecurityLevel.AUTHENTICATED),
            # Phase 2 endpoints - AI operations
            RateLimitRule("/api/v1/phase2/*", 60, 1000, 10, SecurityLevel.AUTHORIZED),
            # Phase 3 endpoints - Collaboration
            RateLimitRule("/api/v1/collaboration/*", 60, 1000, 15, SecurityLevel.AUTHORIZED),
            # Phase 4 endpoints - Autonomous systems (most restricted)
            RateLimitRule("/api/v1/autonomous/*", 30, 500, 5, SecurityLevel.ADMIN),
            # Workflow endpoints
            RateLimitRule("/api/v1/workflows/*", 60, 1000, 10, SecurityLevel.AUTHORIZED),
            # Default rule
            RateLimitRule("*", 200, 10000, 30, SecurityLevel.AUTHENTICATED),
        ]

    def generate_token(
        self, user_id: str, security_level: SecurityLevel = SecurityLevel.AUTHENTICATED
    ) -> str:
        """Generate JWT token with security level.

        NOTE: Tokens generated here lack 'sub' and 'tenant_id' claims required
        by jwt_handler.verify_token(). Use jwt_handler.create_access_token() for
        production tokens. This method is retained for development/test tooling only.
        """
        payload = {
            "user_id": user_id,
            "security_level": security_level.value,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=self.token_expiry_hours),
            "jti": secrets.token_hex(16),  # Unique token ID
        }

        # OP-182: ook deze tweede fabriek stempelt het soort in de JOSE-header. Gemeten
        # op 2026-09-11 gebruikt deze module DEZELFDE geheime sleutel als jwt_handler,
        # dus zonder stempel is een token van hier niet te onderscheiden van een
        # access- of refresh-token uit de hoofdfabriek.
        token = jwt.encode(
            payload,
            self.secret_key,
            algorithm=self.jwt_algorithm,
            headers={"typ": TokenKind.ACCESS.value},
        )
        token_str: str = token if isinstance(token, str) else token.decode("utf-8")

        self._log_security_event(
            "token_generated",
            ThreatLevel.LOW,
            "system",
            user_id,
            "auth",
            f"JWT token generated for user {user_id}",
        )

        return token_str

    def verify_token(self, token: str) -> VerifiedJWTPayload | None:
        """
        Verify JWT token and return payload

        Security Notes (OWASP A02 - Cryptographic Failures):
            - Algorithm is explicitly specified in a list (prevents "none" attack)
            - Only HS256 is accepted (algorithm confusion protection)
            - Expiration is verified and required
            - No information leakage on failure
        """
        try:
            # SECURITY: Explicit algorithm specification prevents:
            # 1. "none" algorithm attack (CVE-2015-9235)
            # 2. Algorithm confusion/substitution attacks
            # CRITICAL: Never pass algorithms=None or include "none"
            # OP-182: deze verifier controleerde alleen `exp` en was daarmee soort-blind.
            # Zolang EEN sleutel twee soorten tokens ondertekent en EEN verifier het
            # soort niet controleert, is de eis van RFC 8725 par. 3.12 (validatieregels
            # die elkaar wederzijds uitsluiten) systeembreed niet gehaald -- een
            # refresh-token kon hier als access-token langs.
            kop = jwt.get_unverified_header(token)
            if kop.get("typ") not in TokenKind.ACCESS.aanvaarde_headerwaarden:
                logger.warning("Token geweigerd op soort: verwacht=%s", TokenKind.ACCESS.value)
                return None

            decoded: dict[str, object] = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.jwt_algorithm],  # Explicit whitelist
                options={
                    # "require_exp" bestaat niet in PyJWT en werd dus genegeerd; de
                    # geldige sleutel is "require". Geen gedragswijziging: de expliciete
                    # `exp is None`-controle hieronder ving dit geval al af. Wat wel
                    # verandert is dat de bedoeling nu ook op de PyJWT-laag klopt en dat
                    # het options-dict weer matcht met PyJWT's Options-type.
                    "require": ["exp"],  # exp-claim MOET aanwezig zijn
                    "verify_exp": True,  # en moet nog geldig zijn
                },
            )
            payload: VerifiedJWTPayload = cast(VerifiedJWTPayload, decoded)

            # Check if token is expired
            exp = payload.get("exp")
            if exp is None or datetime.now(timezone.utc) > datetime.fromtimestamp(
                exp, tz=timezone.utc
            ):
                self._log_security_event(
                    "token_expired",
                    ThreatLevel.MEDIUM,
                    "unknown",
                    cast(str | None, payload.get("user_id")),
                    "auth",
                    "Expired token used",
                )
                return None

            return payload

        except jwt.InvalidTokenError as e:
            self._log_security_event(
                "token_invalid",
                ThreatLevel.HIGH,
                "unknown",
                None,
                "auth",
                f"Invalid token: {str(e)}",
            )
            return None
        except Exception:
            return None

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    def is_ip_allowed(self, ip_address: str) -> bool:
        """Check if IP address is in allowed ranges"""
        try:
            ip = ipaddress.ip_address(ip_address)

            # Geen lijst ingesteld: geen oordeel hier. Bewust NA het ontleden van het
            # adres, zodat een onzinnige waarde nog steeds onwaar oplevert.
            if not self.allowed_ip_ranges:
                return True

            for range_str in self.allowed_ip_ranges:
                if "/" in range_str:
                    # CIDR range
                    network = ipaddress.ip_network(range_str, strict=False)
                    if ip in network:
                        return True
                else:
                    # Single IP
                    allowed_ip = ipaddress.ip_address(range_str)
                    if ip == allowed_ip:
                        return True

            return False

        except ValueError:
            logger.warning(f"Invalid IP address: {ip_address}")
            return False

    def is_ip_whitelisted(self, ip_address: str) -> bool:
        """
        Check if IP address is whitelisted.

        This method provides the interface expected by security middleware tests.
        It wraps is_ip_allowed for backward compatibility.

        Args:
            ip_address: The IP address to check

        Returns:
            True if the IP is whitelisted
        """
        return self.is_ip_allowed(ip_address)

    def check_rate_limit(
        self, ip_address: str, endpoint: str, security_level: SecurityLevel
    ) -> bool:
        """Check if request is within rate limits"""
        now = datetime.now(timezone.utc)
        key = f"{ip_address}:{endpoint}"

        # Find applicable rate limit rule
        rule = self._find_rate_limit_rule(endpoint, security_level)

        if key not in self.rate_limits:
            self.rate_limits[key] = []

        # Clean old entries
        cutoff_minute = now - timedelta(minutes=1)
        cutoff_hour = now - timedelta(hours=1)

        recent_requests = [req for req in self.rate_limits[key] if req > cutoff_hour]
        self.rate_limits[key] = recent_requests

        # Check limits
        minute_requests = len([req for req in recent_requests if req > cutoff_minute])
        hour_requests = len(recent_requests)

        if minute_requests >= rule.requests_per_minute or hour_requests >= rule.requests_per_hour:
            self._log_security_event(
                "rate_limit_exceeded",
                ThreatLevel.MEDIUM,
                ip_address,
                None,
                endpoint,
                f"Rate limit exceeded: {minute_requests}/min, {hour_requests}/hour",
            )
            return False

        # Add current request
        self.rate_limits[key].append(now)
        return True

    def _find_rate_limit_rule(self, endpoint: str, security_level: SecurityLevel) -> RateLimitRule:
        """Find applicable rate limit rule for endpoint"""
        for rule in self.rate_limit_rules:
            if rule.endpoint_pattern == "*":
                continue
            if rule.endpoint_pattern.endswith("*"):
                pattern = rule.endpoint_pattern[:-1]
                if endpoint.startswith(pattern):
                    return rule
            elif endpoint == rule.endpoint_pattern:
                return rule

        # Return default rule
        return next(rule for rule in self.rate_limit_rules if rule.endpoint_pattern == "*")

    def detect_suspicious_activity(
        self,
        ip_address: str,
        user_id: str | None,
        endpoint: str,
        user_values: Sequence[str] | None = None,
    ) -> ThreatLevel:
        """Detect suspicious activity patterns.

        De SQL-injectiecontrole kijkt ALLEEN naar door de gebruiker geleverde waarden, nooit
        naar het vaste routepad: `/api/v1/autonomous/agents/create` bevat het woord `create`
        en blokkeerde zo het IP van een beheerder (Keten B nazorg, punt 1).

        Args:
            user_values: queryparameters (namen en waarden) en padparameterwaarden van het
                verzoek. None: alleen het querydeel van `endpoint` (na `?`) wordt gescand.
        """
        threat_score = 0

        # Check failed login attempts
        if ip_address in self.failed_attempts:
            recent_failures = len(
                [
                    attempt
                    for attempt in self.failed_attempts[ip_address]
                    if datetime.now(timezone.utc) - attempt < timedelta(minutes=15)
                ]
            )
            threat_score += recent_failures * 2

        # Check for pattern of requests to sensitive endpoints
        sensitive_patterns = ["/admin", "/config", "/auth", "/autonomous"]
        for pattern in sensitive_patterns:
            if pattern in endpoint:
                threat_score += 3

        # SQL-patronen tellen hier NIET meer mee (plan nazorg, deel I punt a). De regex treft
        # ook gewone invoer (`#fff`, `update address`, `--date`); de echte verdediging is de ORM
        # met gebonden parameters. De middleware vraagt `sql_injection_signal` apart en geeft
        # het signaal aan de IP-reputatie in Redis; pas herhaald gedrag geeft een blokkade.
        # `user_values` blijft in de signatuur voor bestaande aanroepers.
        del user_values

        # Determine threat level
        if threat_score >= 15:
            return ThreatLevel.CRITICAL
        elif threat_score >= 8:
            return ThreatLevel.HIGH
        elif threat_score >= 4:
            return ThreatLevel.MEDIUM
        else:
            return ThreatLevel.LOW

    def sql_injection_signal(
        self,
        ip_address: str,
        user_id: str | None,
        endpoint: str,
        user_values: Sequence[str] | None = None,
    ) -> bool:
        """True als een door de gebruiker geleverde waarde op een SQL-patroon lijkt.

        Logt dan een MEDIUM-event `sql_injection_signal`. Blokkeert niets: wat er met het
        signaal gebeurt beslist de IP-reputatie (score met drempel).

        Args:
            user_values: queryparameters (namen en waarden) en padparameterwaarden. None: alleen
                het querydeel van `endpoint` (na `?`).
        """
        if user_values is None:
            _pad, _sep, query = endpoint.partition("?")
            user_values = [query] if query else []
        if not any(self._contains_sql_injection(waarde) for waarde in user_values):
            return False
        self._log_security_event(
            "sql_injection_signal",
            ThreatLevel.MEDIUM,
            ip_address,
            user_id,
            endpoint,
            "SQL-like pattern in user-supplied value (signal, not blocked)",
        )
        return True

    def _contains_sql_injection(self, text: str) -> bool:
        """Lijkt deze waarde op een SQL-injectie? Alleen STRUCTUUR telt, geen losse woorden.

        Tot 2026-10-08 matchte elk los SQL-woord (`update`, `create`) en elk commentaarteken
        (`#`, `--`). Daardoor gaven `?color=#fff`, `?q=update address` en `?sort=--date` een
        treffer (plan nazorg, deel I punt a). Nu moet er een injectievorm staan: een
        tautologie, UNION SELECT, een gestapelde opdracht na `;`, een quote gevolgd door
        commentaar, of een volledige opdracht (SELECT .. FROM, INSERT INTO, DELETE FROM,
        UPDATE .. SET, DROP TABLE).
        """
        sql_patterns = [
            r"\b(OR|AND)\s+('[^']*'|\d+)\s*=\s*('[^']*'|\d+)",
            r"\bUNION\s+(ALL\s+)?SELECT\b",
            r"\bSELECT\b.+\bFROM\b",
            r"\bINSERT\s+INTO\b",
            r"\bDELETE\s+FROM\b",
            r"\bUPDATE\s+\S+\s+SET\b",
            r"\b(DROP|TRUNCATE|ALTER)\s+TABLE\b",
            r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|EXEC|SELECT)\b",
            r"'\s*(--|#|/\*)",
            r"/\*.*\*/",
            r"\b(EXEC|EXECUTE)\s*\(",
            r"\b(SLEEP|PG_SLEEP|BENCHMARK)\s*\(",
            r"\bWAITFOR\s+DELAY\b",
        ]

        text_upper = text.upper()
        for pattern in sql_patterns:
            if re.search(pattern, text_upper):
                return True

        return False

    def _log_security_event(
        self,
        event_type: str,
        severity: ThreatLevel,
        source_ip: str,
        user_id: str | None,
        endpoint: str,
        description: str,
    ) -> None:
        """Log security event"""
        event = SecurityEvent(
            event_id=secrets.token_hex(8),
            event_type=event_type,
            severity=severity,
            source_ip=source_ip,
            user_id=user_id,
            endpoint=endpoint,
            description=description,
        )

        self.security_events.append(event)

        # Log to system logger
        log_level = {
            ThreatLevel.LOW: logger.info,
            ThreatLevel.MEDIUM: logger.warning,
            ThreatLevel.HIGH: logger.error,
            ThreatLevel.CRITICAL: logger.critical,
        }[severity]

        log_level(
            f"SECURITY [{event_type}] {description} - IP: {source_ip}, User: {user_id}, Endpoint: {endpoint}"
        )

        # Geen automatische blokkade meer op een event (plan nazorg, deel I punt a). Blokkeren is
        # een beslissing van de IP-reputatie (`ip_reputation.py`): een score in Redis met een
        # drempel, een tijdslimiet en een allowlist.

    def get_security_headers(self) -> dict[str, str]:
        """Get security headers for responses"""
        return self.security_headers.copy()

    def get_security_report(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate security status report"""
        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)

        recent_events = [event for event in self.security_events if event.timestamp > last_24h]

        return {
            "total_events": len(self.security_events),
            "recent_events_24h": len(recent_events),
            "blocked_ips": len(self.blocked_ips),
            "threat_distribution": {
                level.name: len([e for e in recent_events if e.severity == level])
                for level in ThreatLevel
            },
            "top_threat_sources": self._get_top_threat_sources(recent_events),
            "security_status": (
                "healthy"
                if len(
                    [
                        e
                        for e in recent_events
                        if e.severity in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)
                    ]
                )
                < 5
                else "alert"
            ),
            "last_updated": now.isoformat(),
        }

    def _get_top_threat_sources(
        self, events: list[SecurityEvent]
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get top threat sources from events"""
        source_counts: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for event in events:
            if event.severity in (ThreatLevel.MEDIUM, ThreatLevel.HIGH, ThreatLevel.CRITICAL):
                source_counts[event.source_ip] = source_counts.get(event.source_ip, 0) + 1

        return [
            {"ip": ip, "threat_events": count}
            for ip, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

    def cleanup_old_data(self) -> None:
        """Cleanup old security data"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        # Keep only recent security events
        self.security_events = [event for event in self.security_events if event.timestamp > cutoff]

        # Clean old failed attempts
        cutoff_attempts = datetime.now(timezone.utc) - timedelta(hours=24)
        for ip in list(self.failed_attempts.keys()):
            self.failed_attempts[ip] = [
                attempt for attempt in self.failed_attempts[ip] if attempt > cutoff_attempts
            ]
            if not self.failed_attempts[ip]:
                del self.failed_attempts[ip]

        logger.info("Security data cleanup completed")


# Global security manager instance
_security_manager: ProductionSecurityManager | None = None


def get_security_manager() -> ProductionSecurityManager:
    """Get global security manager instance"""
    global _security_manager
    if _security_manager is None:
        _security_manager = ProductionSecurityManager()
    return _security_manager


def require_auth(
    security_level: SecurityLevel = SecurityLevel.AUTHENTICATED,
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """Decorator for requiring authentication"""

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # This would be used with FastAPI Request object
            # Implementation depends on FastAPI integration
            return await func(*args, **kwargs)

        return wrapper

    return decorator
