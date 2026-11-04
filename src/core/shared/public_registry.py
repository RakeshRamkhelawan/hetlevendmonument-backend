"""Public Endpoint Registry -- central source of truth for unauthenticated endpoints.
Moved from src/core/middleware/public_registry.py to break auth <-> tenancy circular dep.
Used by TenantMiddleware, SecurityMiddleware, and QuotaMiddleware.
"""

from src.core.shared.config import is_setup_mode_enabled


class PublicEndpointRegistry:
    """Registry of endpoints that do not require authentication or tenant context."""

    SETUP_PUBLIC_PATHS: set[str] = {
        "/api/v1/setup/init",
    }

    # Exact paths that are always public
    PUBLIC_PATHS: set[str] = {
        "/",
        "/health",
        "/health/db",
        "/health/ready",
        "/health/live",
        "/metrics",
        "/api/metrics",
        "/auth/login",  # Deprecated but still functional (security_endpoints.py:99)
        "/auth/register",  # Public registration endpoint
        "/auth/token",
        "/auth/refresh",
        "/auth/verify-email",
        "/auth/forgot-password",
        "/auth/reset-password",
        "/auth/csrf-token",  # CSRF token endpoint must be public
        "/api/v1/auth/login",
        "/api/v1/auth/token",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/verify-email",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/csrf-token",  # CSRF token endpoint must be public
        # Token introspection (router_token.py::validate_token) takes the token as a
        # query param and has no auth dependency by design -- a caller checking "is my
        # stored token still valid" cannot already hold a valid session. Missing here
        # meant TenantMiddleware 401'd every request before it reached the endpoint,
        # regardless of token validity (only Authorization header/cookie are checked,
        # never query params). Found via tests/integration/test_oauth2_integration.py.
        "/api/v1/auth/validate",
        # ADR-029 / BE-EP-042: Foundation Portal tenant resolution discovery endpoint
        "/api/v1/foundation/tenant/resolve",
        # ADR-029 / BE-EP-043: Foundation Portal sitemap XML discovery endpoint
        "/api/v1/foundation/sitemap.xml",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }

    # Path prefixes that are always public (e.g., static files)
    # NOTE: /admin/ is intentionally NOT listed here -- admin endpoints require
    # a valid JWT with tenant_id. TenantMiddleware must run for those paths.
    PUBLIC_PREFIXES: set[str] = {
        "/static/",
        "/assets/",
        "/public/",
        "/health/",
        "/api/v1/workflow-templates",
        "/api/v1/demo",
        "/api/v1/webhooks/",
        "/api/v1/sops/",
        "/api/v1/integrations/catalog",
        "/api/v1/public/",
    }

    #: Eerste padsegment van elke `PUBLIC_PREFIXES`-entry (ADR-036 OP-202). De foundation-
    #: router is `/{tenantSlug}/foundation/...` -- de aanvrager kiest het eerste segment.
    #: Kiest die toevallig een van deze gereserveerde woorden, dan mag de foundation-
    #: uitzondering hieronder niet gelden: anders matcht `/static/foundation/admin/curatie`
    #: via de generieke `/static/`-prefix, ook al sluit de admin-regel hem daar terecht uit.
    #: Fail-closed op de botsing. `FOUNDATION_RESERVED_SLUGS`
    #: (`src/core/schemas/validators.py`) weigert deze woorden bij het aanmaken van een
    #: Foundation-tenant -- die twee sets MOETEN in sync blijven, anders krijgt een net
    #: aangemaakte tenant met zo'n slug een permanent niet-publieke foundation-pagina.
    #: Geen bescherming voor NIET-Foundation-tenants: `TenantBase.validate_slug`
    #: (`src/core/schemas/tenant_schemas.py`) geeft geen `reserved`-set mee aan
    #: `validate_slug()`, dus algemene tenant-aanmaak controleert helemaal geen gereserveerd
    #: woord. Dat is een apart, breder gat (raakt elke `PUBLIC_PREFIXES`-achtige naam, niet
    #: alleen deze vijf) en wordt hier niet meegefixed -- zie ADR-036 OP-229.
    _RESERVED_TOP_SEGMENTS: frozenset[str] = frozenset(
        p.strip("/").split("/")[0] for p in PUBLIC_PREFIXES if p.strip("/")
    )

    @staticmethod
    def _matches_prefix(path: str, prefix: str) -> bool:
        """Segmentgrens-geankerde prefixmatch (ADR-036 OP-202).

        Een kale `path.startswith(prefix)` kent geen segmentgrenzen: de prefix
        `/api/v1/demo` matchte ook `/api/v1/demoagents`, want die string begint er
        toevallig mee. Vereist nu dat het teken NA de prefix een `/` is (of dat het
        pad daar exact eindigt).

        Bijwerking (Gate 2-review, 2026-09-10): voor een `PUBLIC_PREFIXES`-entry met een
        trailing slash (bijv. `/static/`) matcht het exacte pad ZONDER die slash (`/static`)
        nu ook, waar de oude kale `startswith` dat niet deed. Vandaag onschadelijk: geen van
        de prefix-eigenaren heeft een echte handler op precies dat pad (geverifieerd: geen
        `StaticFiles`-mount in `src/`).
        """
        anchor = prefix.rstrip("/")
        return path == anchor or path.startswith(anchor + "/")

    @classmethod
    def is_public(cls, path: str) -> bool:
        """Check if a path is public."""
        if path in cls.PUBLIC_PATHS:
            return True
        if is_setup_mode_enabled() and path in cls.SETUP_PUBLIC_PATHS:
            return True
        # ADR-029/OP-202: Foundation Portal public endpoints, geankerd op de werkelijke
        # routevorm `/{tenantSlug}/foundation/...` of `/api/v1/{tenantSlug}/foundation/...`.
        # segments[0] is altijd "" (absoluut pad).
        segments = path.split("/")
        tenant_slug: str | None = None
        if len(segments) > 2 and segments[2] == "foundation":
            tenant_slug = segments[1]
        elif (
            len(segments) > 4
            and segments[1] == "api"
            and segments[2] == "v1"
            and segments[4] == "foundation"
        ):
            tenant_slug = segments[3]

        if tenant_slug is not None:
            if tenant_slug in cls._RESERVED_TOP_SEGMENTS:
                return False
            # Het subpad na het "foundation"-segment, geankerd op segmentgrenzen
            # (BE-QA, 2026-09-24): de substring-toetsen die hier stonden maakten het
            # meervoud `/edu/sessions` en verzonnen namen als `/edu/contentevil` ten
            # onrechte publiek via de prefixes `/edu/session` en `/edu/content`.
            # Bewaakt door tests/architecture/test_public_registry_prefixes_are_anchored.py
            # ::test_foundation_subpaths_are_segment_anchored.
            rest = segments[3:] if segments[2] == "foundation" else segments[5:]
            sub_path = "/" + "/".join(rest)
            # Admin curatie endpoints zijn NIET publiek (require auth + role). Ook een
            # aanvrager-gekozen slug "admin" mag de foundation-regel niet openen: het
            # segment "admin" maakt het hele pad niet-publiek (zelfde bereik als de
            # oude substring-toets "/admin/" in path, maar dan segment-geankerd).
            if "admin" in segments:
                return False
            # Auth endpoints are public (magic-link request/verify/logout)
            if cls._matches_prefix(sub_path, "/auth"):
                return True
            # Settings is public
            if cls._matches_prefix(sub_path, "/settings"):
                return True
            # Newsletter is public
            if cls._matches_prefix(sub_path, "/newsletter"):
                return True
            # Content list/detail is public
            if cls._matches_prefix(sub_path, "/content"):
                return True
            # Map bbox endpoint is public (BE-EP-037, O1: showcase endpoint)
            if cls._matches_prefix(sub_path, "/map"):
                return True
            # Edu leeromgeving (BE-EP-039): authenticatie loopt via een opake
            # sessie-cookie, NIET via een JWT. De TenantMiddleware moet de
            # cookie-flow-paden daarom doorlaten (ook zonder token); de
            # sessie-eis wordt per endpoint afgedwongen door require_edu_session.
            # BE-SEC-057: /edu/codes* (code-beheer: minten, PII-lijst, revoke)
            # valt hier BEWUST buiten -- die endpoints vereisen een
            # curator/admin-JWT via require_curator en mogen de middleware
            # nooit tokenloos passeren.
            if cls._matches_prefix(sub_path, "/edu/session"):
                return True
            if cls._matches_prefix(sub_path, "/edu/content"):
                return True
            # Docentenomgeving (BE-EP-055): leerlingantwoorden lopen via dezelfde
            # sessie-cookie als /edu/content (require_edu_session per endpoint).
            if cls._matches_prefix(sub_path, "/edu/antwoorden"):
                return True
            # Docentaccount aanvragen (BE-EP-055): publiek, hCaptcha + rate limit in de
            # handler. ALLEEN dit pad: de rest van /docent/* vereist een docent-JWT.
            if cls._matches_prefix(sub_path, "/docent/aanvraag"):
                return True
            # OAI-PMH metadata harvest endpoint (BE-EP-040, Cat 4 subsidie-eis):
            # Publiek protocol voor externe harvesters (Europeana, NDE) zonder JWT.
            if cls._matches_prefix(sub_path, "/oai-pmh"):
                return True
            # Sitemap XML discovery endpoint (BE-EP-043, ADR-029 P2-5):
            # Publiek endpoint voor zoekmachines en NDE erfgoed-crawlers zonder JWT.
            if cls._matches_prefix(sub_path, "/sitemap.xml"):
                return True
            # Donations checkout and transparency stats (BE-EP-046, ADR-029 P2-2):
            # Publiek endpoint voor erfgoed-adopties en donaties zonder JWT.
            if cls._matches_prefix(sub_path, "/donations"):
                return True
            # Contact inquiry endpoint (BE-EP-048, ADR-029 P2):
            # Publiek endpoint voor burgers en contactvragen zonder JWT.
            if cls._matches_prefix(sub_path, "/contact"):
                return True
            # Webhook callbacks endpoint (BE-EP-049, ADR-029 P1-5):
            # Publiek endpoint voor externe Brevo webhook callbacks zonder JWT.
            if cls._matches_prefix(sub_path, "/webhooks"):
                return True
            return False

        return any(cls._matches_prefix(path, prefix) for prefix in cls.PUBLIC_PREFIXES)

    @classmethod
    def get_public_paths(cls) -> set[str]:
        """Get all public paths (returns a copy -- callers must not mutate)."""
        return set(cls.PUBLIC_PATHS)

    @classmethod
    def get_public_prefixes(cls) -> set[str]:
        """Get all public prefixes (returns a copy -- callers must not mutate)."""
        return set(cls.PUBLIC_PREFIXES)
