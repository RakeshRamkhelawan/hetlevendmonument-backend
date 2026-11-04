"""
Schema validators for SanskritiSetu.

Provides reusable validation functions for slugs, usernames, and other
common fields.
"""

import re
from typing import Annotated

from pydantic import AfterValidator

# ============================================================================
# Slug validation
# ============================================================================

# Backwards-compatible permissieve regex (dekt alle 3 bestaande implementaties)
SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Foundation strict regex (ADR-029)
FOUNDATION_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,30}$")

# Reserved slugs for Foundation Portal tenants. "static"/"assets"/"public" MUST stay in this
# set: PublicEndpointRegistry._RESERVED_TOP_SEGMENTS (src/core/shared/public_registry.py,
# ADR-036 OP-202) fail-closes a foundation route whose slug collides with a PUBLIC_PREFIXES
# word -- a tenant that slipped past this validator with one of those slugs would find its own
# foundation page permanently non-public.
FOUNDATION_RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        "api",
        "www",
        "admin",
        "static",
        "assets",
        "public",
        "health",
        "auth",
        "login",
        "signup",
        "register",
        "app",
        "dashboard",
        "console",
        "support",
        "help",
        "docs",
        "blog",
        "mail",
        "ftp",
        "ns",
        "ns1",
        "ns2",
        "mx",
        "smtp",
        "pop",
        "imap",
        "test",
        "staging",
        "dev",
        "localhost",
        "internal",
        "levend-monument",
        "sanskritisetu",
    }
)

# Gereserveerd voor ELKE tenant, niet alleen voor een Foundation-tenant (ADR-036 OP-229).
# Het is bewust exact dezelfde verzameling, en dat is een besluit met drie redenen:
#
# 1. Een tenant-slug is een TOP-LEVEL URL-segment. De foundation-router is
#    `/{tenantSlug}/foundation/...`, dus de slug van elke tenant deelt de naamruimte met
#    `/static/`, `/assets/`, `/public/`, `/health/` en `/api/`. Dat gevaar hangt aan de
#    slug zelf, niet aan het soort tenant dat hem draagt.
# 2. Foundation is een uitbreiding op een bestaande tenant, geen apart product. Een
#    kleinere verzameling voor het algemene pad laat een tenant een slug krijgen die hem
#    permanent uitsluit van een Foundation-portal -- het defect verschuift dan van
#    "aanmaken weigert niets" naar "upgraden kan niet meer", en dat is later en duurder.
# 3. De prijs van te streng is hier laag en de prijs van te ruim hoog. Beide
#    aanmaak-endpoints zijn beheerder-only (`tenants_list_router.py` eist
#    `is_platform_superuser`, `tenant_management/crud_router.py` eist `require_admin`),
#    dus een geweigerd woord kost een beheerder een tweede poging; een doorgelaten
#    `static` kost een tenant zijn publieke pagina, permanent en stil.
#
# Daarmee vallen ook `test`, `dev`, `app`, `docs`, `blog` en `support` voor elke tenant af.
# Dat is bewust: het zijn stuk voor stuk plausibele top-level routes, en een tenant die er
# een claimt blokkeert die route voor het hele platform.
RESERVED_TENANT_SLUGS: frozenset[str] = FOUNDATION_RESERVED_SLUGS


def validate_slug(
    value: str,
    reserved: frozenset[str] | None = None,
    strict: bool = False,
) -> str:
    """Canonical slug-validator. Raises ValueError (Pydantic-compatible).

    Args:
        value: The slug string to validate.
        reserved: Optional frozenset of reserved slugs to reject.
        strict: If True, uses Foundation strict regex (3-31 chars,
            lowercase, leading letter). If False, uses permissive regex
            for backwards compatibility with existing callers.

    Returns:
        The validated slug (lowercased in non-strict mode).

    Raises:
        ValueError: If the slug does not match the pattern or is reserved.
    """
    if not isinstance(value, str):
        raise ValueError(f"Invalid slug: must be string, got {type(value).__name__}")

    pattern = FOUNDATION_SLUG_PATTERN if strict else SLUG_PATTERN

    if not pattern.match(value):
        if strict:
            raise ValueError(
                f"Invalid slug: {value!r}. Use 3-31 lowercase letters, "
                f"digits, or hyphens; must start with a letter."
            )
        else:
            raise ValueError(
                f"Invalid slug: {value!r}. Use only letters, numbers, " f"hyphens, and underscores."
            )

    # De niet-strikte tak kleint pas bij de `return`, dus de reserved-toets MOET over de
    # gekleinde waarde. Met de toets op de RUWE waarde is een hoofdletter een volledige
    # omzeiling; gemeten 2026-09-28 op commit 40798340:
    #   DOOR:      'STATIC' -> 'static'
    #   GEWEIGERD: 'static' -> Slug 'static' is reserved
    # De strikte tak heeft dit niet nodig: FOUNDATION_SLUG_PATTERN weigert hoofdletters
    # hierboven al, en laat de waarde daarna ongemoeid.
    normalized = value if strict else value.lower()

    if reserved and normalized in reserved:
        raise ValueError(f"Slug {value!r} is reserved")

    return normalized


def slug_from_name(name: str) -> str:
    """De ENE afleiding van een tenant-slug uit een tenantnaam (ADR-036 OP-229).

    Deze afleiding stond op twee plekken los van elkaar, en ze waren al uit elkaar gelopen:
    het ORM-event `_tenant_validate_slug` (rbac_models.py) deed `.strip().lower()`, de
    uniciteitstoets in `tenant_management/crud_router.py::create_tenant` deed `.lower()`
    zonder `strip`. Gemeten 2026-09-28 op commit 15638030 met naam `' Acme '`:
        event         -> 'acme'
        uniciteitstoets -> '-acme-'
    De toets zocht dus naar een andere slug dan die werd opgeslagen, waardoor een duplicaat
    ongezien voorbij kon komen. Deze functie is letterlijk de event-variant; beide plekken
    roepen hem nu aan, zodat ze niet opnieuw kunnen divergeren.

    Deze functie VALIDEERT niet -- de aanroeper geeft het resultaat aan `validate_slug()`.
    """
    return name.strip().lower().replace(" ", "-")


Slug = Annotated[str, AfterValidator(validate_slug)]


# ============================================================================
# Username validation
# ============================================================================


def validate_username(value: str) -> str:
    """
    Validate username format.

    Only alphanumeric characters and underscores allowed.
    Must start with a letter, be at least 3 characters, and is lowercased.
    """
    if not isinstance(value, str):
        raise ValueError(f"Invalid username: must be string, got {type(value).__name__}")
    value = value.strip().lower()
    if len(value) < 3:
        raise ValueError(f"Invalid username: {value!r}. Must be at least 3 characters.")
    if not re.match(r"^[a-z][a-z0-9_]+$", value):
        raise ValueError(
            f"Invalid username: {value!r}. Use only letters, numbers, and "
            f"underscores; must start with a letter."
        )
    return value


Username = Annotated[str, AfterValidator(validate_username)]


# ============================================================================
# Phone number validation
# ============================================================================


def validate_phone_number(value: str) -> str:
    """Validate and normalize phone number."""
    if not isinstance(value, str):
        raise ValueError(f"Invalid phone number: must be string, got {type(value).__name__}")
    cleaned = value.replace(" ", "").replace("-", "").strip()
    if not cleaned:
        raise ValueError("Invalid phone number: empty")
    # Allow +, digits only after optional leading +
    if cleaned.startswith("+"):
        digits_only = cleaned[1:]
        if not digits_only.isdigit():
            raise ValueError(f"Invalid phone number: {value!r}")
    else:
        if not cleaned.isdigit():
            raise ValueError(f"Invalid phone number: {value!r}")
    if len(cleaned) < 7:
        raise ValueError(f"Invalid phone number: {value!r}. Too short.")
    return cleaned


PhoneNumber = Annotated[str, AfterValidator(validate_phone_number)]


# ============================================================================
# Email validation helpers
# ============================================================================


def normalize_email(value: str) -> str:
    """Normalize email address (lowercase, strip whitespace)."""
    if not isinstance(value, str):
        raise ValueError(f"Invalid email: must be string, got {type(value).__name__}")
    return value.strip().lower()


NormalizedEmail = Annotated[str, AfterValidator(normalize_email)]


# ============================================================================
# URL validation helpers
# ============================================================================


def validate_url(value: str) -> str:
    """Validate that a string is a valid URL with scheme."""
    if not isinstance(value, str):
        raise ValueError(f"Invalid URL: must be string, got {type(value).__name__}")
    value = value.strip()
    if "://" not in value:
        raise ValueError(f"Invalid URL: {value!r}. Must include scheme (e.g., https://).")
    scheme = value.split("://", 1)[0].lower()
    if scheme not in {"https", "http"}:
        raise ValueError(f"Invalid URL scheme: {scheme}. Allowed: http, https.")
    return value


def validate_url_scheme(value: str, allowed_schemes: set[str] | None = None) -> str:
    """Validate that a URL uses an allowed scheme."""
    if allowed_schemes is None:
        allowed_schemes = {"https", "http"}

    if "://" not in value:
        raise ValueError(f"Invalid URL: {value}. Must include scheme (e.g., https://).")

    scheme = value.split("://", 1)[0].lower()
    if scheme not in allowed_schemes:
        raise ValueError(
            f"Invalid URL scheme: {scheme}. Allowed: {', '.join(sorted(allowed_schemes))}"
        )

    return value
