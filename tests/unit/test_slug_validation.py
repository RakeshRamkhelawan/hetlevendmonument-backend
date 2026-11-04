"""
Unit tests for canonical slug validation (Task 6).

Covers: pattern matching, reserved names, strict vs permissive mode,
all 3 callers (TenantBase, APIValidation, Tenant event listener).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.core.schemas.validators import (
    FOUNDATION_RESERVED_SLUGS,
    FOUNDATION_SLUG_PATTERN,
    RESERVED_TENANT_SLUGS,
    SLUG_PATTERN,
    validate_slug,
)


class TestSlugPattern:
    @pytest.mark.unit
    def test_foundation_pattern_accepts_valid(self) -> None:
        assert FOUNDATION_SLUG_PATTERN.match("abc")
        assert FOUNDATION_SLUG_PATTERN.match("ketikoti")
        assert FOUNDATION_SLUG_PATTERN.match("a" * 31)

    @pytest.mark.unit
    def test_foundation_pattern_rejects_too_short(self) -> None:
        assert not FOUNDATION_SLUG_PATTERN.match("ab")
        assert not FOUNDATION_SLUG_PATTERN.match("a")

    @pytest.mark.unit
    def test_foundation_pattern_rejects_too_long(self) -> None:
        assert not FOUNDATION_SLUG_PATTERN.match("a" * 32)

    @pytest.mark.unit
    def test_foundation_pattern_rejects_leading_digit(self) -> None:
        assert not FOUNDATION_SLUG_PATTERN.match("1abc")

    @pytest.mark.unit
    def test_foundation_pattern_rejects_underscore(self) -> None:
        assert not FOUNDATION_SLUG_PATTERN.match("abc_def")

    @pytest.mark.unit
    def test_permissive_pattern_accepts_underscore(self) -> None:
        assert SLUG_PATTERN.match("abc_def")
        assert SLUG_PATTERN.match("ABC-DEF")

    @pytest.mark.unit
    def test_permissive_pattern_rejects_special_chars(self) -> None:
        assert not SLUG_PATTERN.match("abc!def")
        assert not SLUG_PATTERN.match("abc def")


class TestValidateSlug:
    @pytest.mark.unit
    def test_strict_valid(self) -> None:
        assert validate_slug("ketikoti", strict=True) == "ketikoti"

    @pytest.mark.unit
    def test_strict_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid slug"):
            validate_slug("ab", strict=True)

    @pytest.mark.unit
    def test_strict_leading_digit_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid slug"):
            validate_slug("1abc", strict=True)

    @pytest.mark.unit
    def test_strict_reserved_raises(self) -> None:
        with pytest.raises(ValueError, match="reserved"):
            validate_slug("api", reserved=FOUNDATION_RESERVED_SLUGS, strict=True)

    @pytest.mark.unit
    def test_permissive_valid(self) -> None:
        assert validate_slug("ABC-DEF") == "abc-def"

    @pytest.mark.unit
    def test_permissive_no_reserved_check_by_default(self) -> None:
        assert validate_slug("api") == "api"

    @pytest.mark.unit
    def test_permissive_reserved_when_provided(self) -> None:
        with pytest.raises(ValueError, match="reserved"):
            validate_slug("api", reserved=FOUNDATION_RESERVED_SLUGS)

    @pytest.mark.unit
    def test_non_string_raises(self) -> None:
        with pytest.raises(ValueError, match="must be string"):
            validate_slug(123)  # type: ignore[arg-type]


class TestTenantBaseDelegation:
    @pytest.mark.unit
    def test_valid_slug(self) -> None:
        from src.core.api.v1.tenants.schemas import TenantBase

        t = TenantBase(slug="valid-slug", name="Test")
        assert t.slug == "valid-slug"

    @pytest.mark.unit
    def test_invalid_slug_raises(self) -> None:
        from src.core.api.v1.tenants.schemas import TenantBase

        with pytest.raises(ValueError, match="Invalid slug"):
            TenantBase(slug="bad slug!", name="Test")


class TestAPIValidationDelegation:
    @pytest.mark.unit
    def test_valid_slug(self) -> None:
        from src.core.security.api_validation import ValidatedPathParams

        assert ValidatedPathParams.validate_slug("valid-slug") == "valid-slug"

    @pytest.mark.unit
    def test_invalid_slug_raises_http_exception(self) -> None:
        from src.core.security.api_validation import ValidatedPathParams

        with pytest.raises(HTTPException) as exc_info:
            ValidatedPathParams.validate_slug("bad slug!")
        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_empty_slug_raises_http_exception(self) -> None:
        from src.core.security.api_validation import ValidatedPathParams

        with pytest.raises(HTTPException) as exc_info:
            ValidatedPathParams.validate_slug("")
        assert exc_info.value.status_code == 400


class TestTenantEventListener:
    @pytest.mark.unit
    def test_auto_slug_generation(self) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Stichting Test")
        # Simulate what the event listener does on before_insert
        from src.core.models.rbac_models import _tenant_validate_slug

        _tenant_validate_slug(None, None, tenant)
        assert tenant.slug == "stichting-test"

    @pytest.mark.unit
    def test_invalid_slug_raises_on_flush(self) -> None:
        from src.core.models.rbac_models import Tenant

        tenant = Tenant(name="Stichting Test!")
        from src.core.models.rbac_models import _tenant_validate_slug

        # The auto-generated slug will be "stichting-test!" which fails validation
        with pytest.raises(ValueError, match="Invalid slug"):
            _tenant_validate_slug(None, None, tenant)


# ============================================================================
# OP-229 -- gereserveerde slugs op de tenant-aanmaakpaden
#
# Gemeten op commit 89cdcbeb, 2026-09-28:
#   TenantCreate(name='X', slug='static')  -> GEACCEPTEERD
#   TenantCreate(name='X', slug='STATIC')  -> GEACCEPTEERD, wordt 'static'
# validate_slug() toetst de reserved-verzameling op de RUWE waarde
# (src/core/schemas/validators.py:104) en kleint pas bij de return (regel 107).
# Een fix die alleen de verzameling meegeeft en regel 104 laat staan, haalt groen
# op 'static' en laat 'STATIC' door -- terwijl die er als 'static' uitkomt.
# ============================================================================

# 'static', 'assets' en 'public' zijn de drie woorden met een PUBLIEK gevolg: ze botsen met
# PublicEndpointRegistry._RESERVED_TOP_SEGMENTS (src/core/shared/public_registry.py).
RESERVED_MET_PUBLIEKE_GEVOLGEN = ("static", "assets", "public")

# 'admin' valt BUITEN dat drietal en bewaakt daarmee de rest van de verzameling.
# Zonder dit lid haalt een reparatie die ALLEEN de drie publieke woorden hardcodeert alles
# groen, terwijl de andere 31 leden van FOUNDATION_RESERVED_SLUGS onbewaakt blijven.
RESERVED_BUITEN_HET_PUBLIEKE_DRIETAL = ("admin",)

RESERVED_STEEKPROEF = RESERVED_MET_PUBLIEKE_GEVOLGEN + RESERVED_BUITEN_HET_PUBLIEKE_DRIETAL

# Zelfde woorden, andere schrijfwijze. Wordt tegen RESERVED_STEEKPROEF aan gehouden door
# test_de_hoofdletter_steekproef_dekt_dezelfde_woorden, zodat de twee lijsten niet uit de pas
# kunnen lopen.
RESERVED_STEEKPROEF_MET_HOOFDLETTERS = ("STATIC", "Assets", "PUBLIC", "Admin")

# De naam die een klant intypt wanneer hij GEEN slug meestuurt. De slugify in het ORM-event
# (lowercase, spaties naar streepjes) maakt er het gereserveerde woord van.
NAMEN_DIE_EEN_GERESERVEERDE_SLUG_OPLEVEREN = tuple(w.capitalize() for w in RESERVED_STEEKPROEF)


@pytest.mark.unit
@pytest.mark.parametrize("slug", RESERVED_STEEKPROEF)
def test_de_steekproef_staat_echt_in_de_gereserveerde_verzameling(slug: str) -> None:
    """Een woord dat niet in de verzameling zit, kan nooit op de reserved-regel sneuvelen.

    Zonder deze regel maakt een typefout in de steekproef elke reserved-test hieronder hol:
    die zou dan groen worden op een PATROONfout in plaats van op de reserved-regel.
    """
    assert slug in RESERVED_TENANT_SLUGS


@pytest.mark.unit
def test_de_hoofdletter_steekproef_dekt_dezelfde_woorden() -> None:
    """De hoofdletter-variant mag niet uit de pas lopen met de steekproef zelf."""
    assert tuple(w.lower() for w in RESERVED_STEEKPROEF_MET_HOOFDLETTERS) == RESERVED_STEEKPROEF


class TestAanmaakpadWeigertGereserveerdeSlug:
    """Het canonieke aanmaakpad (TenantBase/TenantCreate) weigert gereserveerde slugs."""

    @pytest.mark.unit
    @pytest.mark.parametrize("slug", RESERVED_STEEKPROEF)
    def test_tenantcreate_weigert_gereserveerde_slug(self, slug: str) -> None:
        from src.core.schemas.tenant_schemas import TenantCreate

        with pytest.raises(ValueError, match="reserved"):
            TenantCreate(name="Acme Corporation", slug=slug)

    @pytest.mark.unit
    @pytest.mark.parametrize("slug", RESERVED_STEEKPROEF_MET_HOOFDLETTERS)
    def test_tenantcreate_weigert_gereserveerde_slug_in_hoofdletters(self, slug: str) -> None:
        """Hoofdletters zijn een volledige omzeiling: 'STATIC' komt er als 'static' uit."""
        from src.core.schemas.tenant_schemas import TenantCreate

        with pytest.raises(ValueError, match="reserved"):
            TenantCreate(name="Acme Corporation", slug=slug)


class TestAanmaakpadAccepteertGewoneSlug:
    """De tegenkant: zonder deze helft is 'weiger alles' een geldige oplossing."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "ingevoerd,verwacht",
        (
            ("acme-corp", "acme-corp"),
            ("valid_slug", "valid_slug"),
            ("MyTenant", "mytenant"),
        ),
    )
    def test_tenantcreate_accepteert_gewone_slug(self, ingevoerd: str, verwacht: str) -> None:
        from src.core.schemas.tenant_schemas import TenantCreate

        assert TenantCreate(name="Acme Corporation", slug=ingevoerd).slug == verwacht


class TestLeespadBlijftLeesbaar:
    """TenantResponse erft van TenantBase; een reserved-toets daar breekt het LEESPAD.

    mro nagemeten 2026-09-28: TenantResponse -> TenantBase -> BaseModel. Een bestaande
    tenant met slug 'static' moet ophaalbaar blijven -- de weigering hoort bij AANMAKEN,
    niet bij LEZEN. Zonder deze test verandert de fix een aanmaakweigering stilletjes in
    een leesfout op bestaande rijen.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("slug", RESERVED_STEEKPROEF)
    def test_bestaande_tenant_met_gereserveerde_slug_blijft_leesbaar(self, slug: str) -> None:
        from datetime import datetime, timezone

        from src.core.models.rbac_models import Tenant
        from src.core.schemas.tenant_schemas import TenantResponse

        bestaande_rij = Tenant(
            id=1,
            name="Tenant Van Voor De Fix",
            slug=slug,
            domain=None,
            settings={},
            is_active=True,
            max_users=10,
            max_agents=50,
            max_storage_gb=5,
            subscription_tier="free",
            subscription_status="active",
            data_residency="global",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=None,
        )

        assert TenantResponse.model_validate(bestaande_rij).slug == slug


class TestTweedeAanmaakpadWeigertGereserveerdeSlug:
    """Het pad van crud_router.py:273 slaat TenantBase.validate_slug over.

    Dat pad bouwt een `Tenant`-rij uit een EIGEN `TenantCreate`
    (src/core/api/v1/tenant_management/crud_router.py:62) zonder slug-validator. De enige
    controle die de rij raakt is het ORM-event `before_insert`
    (src/core/models/rbac_models.py:189-196).

    Deze test heeft GEEN draaiende database nodig: hij bouwt de rij zoals de router dat
    doet en vuurt vervolgens de geregistreerde `before_insert`-listeners af via de
    mapper-dispatch -- precies wat een echte flush doet. Daardoor is de test niet gebonden
    aan EEN reparatieplek: een weigering in het schema van de router, of in het ORM-event,
    maakt hem allebei groen (pydantic's ValidationError is een ValueError).

    Wat deze test NIET dekt: de uniciteitscontrole en de commit van de echte handler --
    daarvoor is een database nodig.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("slug", RESERVED_STEEKPROEF + RESERVED_STEEKPROEF_MET_HOOFDLETTERS)
    def test_tweede_aanmaakpad_weigert_gereserveerde_slug(self, slug: str) -> None:
        from sqlalchemy import inspect as sa_inspect

        from src.core.api.v1.tenant_management.crud_router import (
            TenantCreate as RouterTenantCreate,
        )
        from src.core.models.rbac_models import Tenant

        # `match="reserved"` is niet optioneel: zonder die eis wordt deze test ook groen op
        # een PATROONfout. Gemeten door de reviewer op 2026-09-28 met een listener die
        # `strict=True` zet zonder `reserved`: de parameter [STATIC] werd groen op
        # "Invalid slug: 'STATIC'. Use 3-31 lowercase letters..." -- de hoofdletter-casus,
        # juist de subtiele helft, was op dat pad dus onbewaakt.
        with pytest.raises(ValueError, match="reserved"):
            invoer = RouterTenantCreate(name="Acme Corporation", slug=slug)
            rij = Tenant(name=invoer.name, slug=invoer.slug, domain=invoer.domain)
            Tenant.__mapper__.dispatch.before_insert(Tenant.__mapper__, None, sa_inspect(rij))

    @pytest.mark.unit
    def test_de_afgevuurde_listener_valideert_echt(self) -> None:
        """Controlegroep: bewijst dat de dispatch hierboven de validator BEREIKT.

        Zonder deze regel is een groene reserved-test niet te onderscheiden van een
        dispatch die niets aanroept.
        """
        from sqlalchemy import inspect as sa_inspect

        from src.core.models.rbac_models import Tenant

        rij = Tenant(name="Acme Corporation", slug="bad slug!")
        with pytest.raises(ValueError, match="Invalid slug"):
            Tenant.__mapper__.dispatch.before_insert(Tenant.__mapper__, None, sa_inspect(rij))

    @pytest.mark.unit
    def test_tweede_aanmaakpad_accepteert_gewone_slug(self) -> None:
        """De tegenkant op dit pad: een gewone slug blijft hem HELEMAAL doorlopen.

        Wat de assertie waarmaakt, en niet meer dan dat: geen enkele schakel gooit
        (routerschema noch `before_insert`), en de meegegeven slug staat na afloop
        onveranderd op de rij. Het ORM-event gooit de returnwaarde van `validate_slug()`
        weg (rbac_models.py:196), dus deze assertie zegt NIETS over normalisatie -- die
        wordt op het routerschema getoetst in
        TestAanmaakpadAccepteertGewoneSlug::test_tenantcreate_accepteert_gewone_slug.
        """
        from sqlalchemy import inspect as sa_inspect

        from src.core.api.v1.tenant_management.crud_router import (
            TenantCreate as RouterTenantCreate,
        )
        from src.core.models.rbac_models import Tenant

        invoer = RouterTenantCreate(name="Acme Corporation", slug="acme-corp")
        rij = Tenant(name=invoer.name, slug=invoer.slug, domain=invoer.domain)
        Tenant.__mapper__.dispatch.before_insert(Tenant.__mapper__, None, sa_inspect(rij))

        assert rij.slug == "acme-corp"


class TestNaamAfgeleidPadWeigertGereserveerdeSlug:
    """Het DERDE pad: de slug die uit de NAAM wordt afgeleid, langs elke reserved-toets heen.

    `slug` is optioneel op het routerschema (crud_router.py:62-70). Stuurt een klant hem niet
    mee -- `POST /tenants {"name": "Static"}` -- dan is het ORM-event `_tenant_validate_slug`
    (rbac_models.py:189-196) de enige controle die de rij nog raakt, en dat event roept
    `validate_slug(target.slug)` aan ZONDER `reserved`. De reserved-toets op het routerschema
    kijkt naar een waarde die er dan niet is.

    Gemeten op de huidige, gefixte boom (2026-09-28), met de TenantCreate van crud_router:

        R(name='Static').slug  -> None
        na before_insert       -> 'static'

    Deze test is niet aan EEN reparatieplek gebonden: een weigering in het routerschema (een
    validator die de slug eerst afleidt en dan toetst) en een weigering in het ORM-event maken
    hem allebei groen, want pydantic's ValidationError is een ValueError.

    Dat de mapper-dispatch de validator werkelijk BEREIKT, staat los bewezen in
    TestTweedeAanmaakpadWeigertGereserveerdeSlug::test_de_afgevuurde_listener_valideert_echt.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("naam", NAMEN_DIE_EEN_GERESERVEERDE_SLUG_OPLEVEREN)
    def test_naam_zonder_slug_weigert_gereserveerd_woord(self, naam: str) -> None:
        from sqlalchemy import inspect as sa_inspect

        from src.core.api.v1.tenant_management.crud_router import (
            TenantCreate as RouterTenantCreate,
        )
        from src.core.models.rbac_models import Tenant

        with pytest.raises(ValueError, match="reserved"):
            invoer = RouterTenantCreate(name=naam)
            rij = Tenant(name=invoer.name, slug=invoer.slug, domain=invoer.domain)
            Tenant.__mapper__.dispatch.before_insert(Tenant.__mapper__, None, sa_inspect(rij))

    @pytest.mark.unit
    def test_gewone_naam_zonder_slug_levert_nog_steeds_een_werkende_slug(self) -> None:
        """De tegenkant, en tegelijk de controlegroep op de afleiding zelf.

        Zonder deze helft is "weiger elke naam-afgeleide slug" een geldige oplossing, en die
        sloopt het aanmaakpad voor iedereen. Hij toont bovendien dat het ORM-event de naam
        WEL kleint en spaties WEL vervangt -- exact de twee stappen die van 'Static' een
        'static' maken. Staat deze test rood, dan is de afleiding zelf stuk en zegt de
        reserved-test hierboven niets meer.
        """
        from sqlalchemy import inspect as sa_inspect

        from src.core.api.v1.tenant_management.crud_router import (
            TenantCreate as RouterTenantCreate,
        )
        from src.core.models.rbac_models import Tenant

        invoer = RouterTenantCreate(name="Acme Corporation")
        rij = Tenant(name=invoer.name, slug=invoer.slug, domain=invoer.domain)
        Tenant.__mapper__.dispatch.before_insert(Tenant.__mapper__, None, sa_inspect(rij))

        assert rij.slug == "acme-corporation"
