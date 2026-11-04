"""Foundation Portal API schemas (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

# All ContentType values (BE-MIG-014 added six). Response serializers must
# accept every value the ORM can return -- including the educational types
# served by the /edu/* endpoints (BE-EP-039) -- otherwise serialization of a
# valid row fails with a 500. Upload requests keep their own, narrower set.
ContentTypeValue = Literal[
    "story",
    "artwork",
    "audio",
    "document",
    "poetry",
    "link",
    "video",
    "educational_workbook",
    "educational_video",
    "teacher_guide",
    "event_report",
    "art_documentation",
]


# ============================================================================
# Content schemas
# ============================================================================


def apply_anonymity_mask(is_anonymous: bool, creator_name: str | None) -> str | None:
    """Return creator_name masked when the uploader chose anonymity.

    Single source of truth for the BE-EP-038 masking rule: when
    is_anonymous is True, creator_name must never reach a public response.
    Reused by the content schemas below and the GeoJSON map endpoint
    (map.content_to_feature), so the rule cannot drift per serializer.
    """
    if is_anonymous:
        return None
    return creator_name


class FoundationContentListItem(BaseModel):
    """Minimal content item for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: ContentTypeValue
    title_nl: str
    title_en: str | None = None
    # De korte beschrijving; de portal toont die als samenvatting op de kaart in de lijst
    # (portal/src/api/client.ts normalizeItem: summary <- description_nl).
    description_nl: str | None = None
    description_en: str | None = None
    creator_name: str | None = None
    is_anonymous: bool = False
    status: Literal["pending", "approved", "rejected", "removed"] = "pending"
    lat: float | None = None
    lng: float | None = None
    location_name: str | None = None
    category: str | None = None
    # Doelgroep van lesmateriaal (bijv. "groep-7-8", "onderbouw-vo"); de educatieve
    # omgeving groepeert de werkbladen hierop.
    target_age_group: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _mask_creator_name(self) -> "FoundationContentListItem":
        self.creator_name = apply_anonymity_mask(self.is_anonymous, self.creator_name)
        return self


class ContentTagDetail(BaseModel):
    """Detail of a semantic tag on a FoundationContent item (ADR-029 P1-1)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tag_type: str
    value: str
    confidence: float
    is_manual: bool = False


class FoundationBestandItem(BaseModel):
    """Een extra bestand bij een verhaal (BE-EP-057); ophalen via /content/{id}/bestanden/{bestand_id}/media."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    volgorde: int
    file_mime: str
    file_size_bytes: int


class FoundationContentDetail(BaseModel):
    """Full content detail for single item view."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    type: ContentTypeValue
    title_nl: str
    title_en: str | None = None
    description_nl: str | None = None
    description_en: str | None = None
    body_nl: str | None = None
    body_en: str | None = None
    creator_name: str | None = None
    is_anonymous: bool = False
    language: str = "nl"
    privacy: Literal["public", "community"] = "public"
    status: Literal["pending", "approved", "rejected", "removed"] = "pending"
    rights_confirmed: bool = False
    file_url: str | None = None
    file_mime: str | None = None
    file_size_bytes: int | None = None
    #: BE-EP-057: bestanden na het eerste, op volgorde. Alleen gevuld door GET /content/{id}.
    bestanden: list[FoundationBestandItem] = Field(default_factory=list)
    external_url: str | None = None
    lat: float | None = None
    lng: float | None = None
    location_name: str | None = None
    license: str | None = None
    category: str | None = None
    ai_tagging_failed: bool = False
    moderation_score: float | None = None
    tags: list[ContentTagDetail] = Field(default_factory=list)
    metadata_: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        None,
        validation_alias="metadata_",
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _mask_creator_name(self) -> "FoundationContentDetail":
        self.creator_name = apply_anonymity_mask(self.is_anonymous, self.creator_name)
        return self


class FoundationContentCreateRequest(BaseModel):
    """Request body for content upload (metadata only, file is separate)."""

    type: Literal["story", "artwork", "audio", "document", "poetry", "link"]
    title_nl: str = Field(..., min_length=1, max_length=255)
    title_en: str | None = Field(None, max_length=255)
    description_nl: str | None = None
    description_en: str | None = None
    body_nl: str | None = None
    body_en: str | None = None
    creator_name: str | None = Field(None, max_length=255)
    is_anonymous: bool = False
    language: str = "nl"
    privacy: Literal["public", "community"] = "public"
    rights_confirmed: bool = False
    external_url: str | None = Field(None, max_length=1024)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    location_name: str | None = Field(None, max_length=200)
    license: str | None = Field(None, max_length=50)
    category: str | None = Field(None, max_length=100)
    metadata: dict[str, Any] | None = Field(None, description="Flexible JSONB metadata")


class FoundationContentUpdateRequest(BaseModel):
    """Request body for updating existing content (ADR-029 P1-2)."""

    title_nl: str | None = Field(None, min_length=1, max_length=255)
    title_en: str | None = Field(None, max_length=255)
    description_nl: str | None = None
    description_en: str | None = None
    body_nl: str | None = None
    body_en: str | None = None
    creator_name: str | None = Field(None, max_length=255)
    is_anonymous: bool | None = None
    language: str | None = None
    privacy: Literal["public", "community"] | None = None
    external_url: str | None = Field(None, max_length=1024)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    location_name: str | None = Field(None, max_length=200)
    license: str | None = Field(None, max_length=50)
    category: str | None = Field(None, max_length=100)
    metadata: dict[str, Any] | None = Field(None, description="Flexible JSONB metadata")


class FoundationContentDeleteResponse(BaseModel):
    """Response after soft-deleting content (ADR-029 P1-2)."""

    id: int
    status: Literal["removed"] = "removed"
    message: str = "Content successfully removed"


class FoundationContentListResponse(BaseModel):
    """Paginated list response."""

    items: list[FoundationContentListItem]
    total: int
    page: int
    page_size: int


class FoundationFileUploadResponse(BaseModel):
    """Response after a successful file upload onto existing content (BE-EP-036)."""

    file_url: str
    file_mime: str
    file_size_bytes: int
    sha256: str
    #: BE-EP-057: id van het extra bestand; None als dit het hoofdbestand van het verhaal is.
    bestand_id: int | None = None


class FoundationMediaResponse(BaseModel):
    """Response containing a secure media access URL (ADR-029 P1-4)."""

    url: str
    mime_type: str | None = None
    file_size_bytes: int | None = None
    expires_in_seconds: int = 1800


# ============================================================================
# Admin schemas
# ============================================================================


class CuratieQueueItem(BaseModel):
    """Content item in moderation queue."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: ContentTypeValue
    title_nl: str
    creator_name: str | None = None
    is_anonymous: bool = False
    status: str
    ai_tagging_failed: bool = False
    moderation_score: float | None = None
    tags: list[ContentTagDetail] = Field(default_factory=list)
    created_at: datetime


class CuratieQueueResponse(BaseModel):
    """Moderation queue response."""

    items: list[CuratieQueueItem]
    total: int
    page: int
    page_size: int
    status_filter: str


class RejectContentRequest(BaseModel):
    """Request body for rejecting content."""

    rejection_reason: str | None = Field(None, max_length=1000)


class BulkApproveRequest(BaseModel):
    """Request body for approving multiple content items in bulk."""

    content_ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of content IDs to approve (max 100)",
    )


class BulkRejectRequest(BaseModel):
    """Request body for rejecting multiple content items in bulk (DSA Art. 17)."""

    content_ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of content IDs to reject (max 100)",
    )
    rejection_reason: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Mandatory statement of reasons for rejections (DSA Art. 17)",
    )


class BulkFailedItem(BaseModel):
    """Representation of an item that could not be processed in a bulk operation."""

    id: int
    reason: str


class BulkModerationResponse(BaseModel):
    """Response after bulk curation approval or rejection."""

    total_requested: int
    processed_count: int
    success_ids: list[int]
    failed_items: list[BulkFailedItem]
    message: str


class ReTagResponse(BaseModel):
    """Response after triggering AI re-tagging (ADR-029 P1-1)."""

    content_id: int
    status: str
    message: str


class ArchiveExportItem(BaseModel):
    """Een BagIt-archiefexport zoals de beheerder hem ziet (BE-EP-054)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bag_name: str
    item_count: int
    payload_file_count: int
    size_bytes: int
    sha256: str
    trigger: str
    created_at: datetime


class ArchiveExportListResponse(BaseModel):
    items: list[ArchiveExportItem]
    total: int
    limit: int
    offset: int


# ============================================================================
# Auth schemas (magic link)
# ============================================================================


class MagicLinkRequest(BaseModel):
    """Request a magic link via email."""

    email: str = Field(..., min_length=3, max_length=255)
    hcaptcha_token: str | None = Field(None, description="hCaptcha response token")
    aanmelden: bool = Field(
        False,
        description=(
            "BE-EP-056: true = maak een bezoekersaccount aan als dit e-mailadres "
            "nog onbekend is (verteller die een verhaal wil insturen). Het antwoord "
            "blijft generiek, zodat niet te zien is of het adres al bestond."
        ),
    )


class MagicLinkVerifyRequest(BaseModel):
    """Verify a magic link token."""

    token: str = Field(..., min_length=1)


class MagicLinkResponse(BaseModel):
    """Response after magic link request (always generic in prod)."""

    message: str = "If the email exists, a login link has been sent."
    dev_magic_link_url: str | None = None
    dev_token: str | None = None


class PortalUserResponse(BaseModel):
    """Basic portal user info returned with tokens."""

    email: str
    role: str


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    user: PortalUserResponse | None = None


class PasswordLoginRequest(BaseModel):
    """Password login request for administrators and staff."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class QuickLoginRequest(BaseModel):
    """Development quick login request (bypasses email delivery)."""

    role: Literal["admin", "curator", "bezoeker", "visitor"] = "bezoeker"


# ============================================================================
# Edu session schemas (BE-EP-039)
# ============================================================================


class EduSessionRequest(BaseModel):
    """Request body for creating an edu session with an access code.

    The code is exactly 8 alphanumeric characters (ADR-029). Hash
    normalization (spec open aannames): sha256 over the code exactly as
    entered (UTF-8); there is no case-folding because no code-issuing
    feature exists yet -- the future issuing feature MUST follow the same
    normalization.
    """

    code: str = Field(..., pattern=r"^[A-Za-z0-9]{8}$")


class EduSessionResponse(BaseModel):
    """Edu session info: role comes from the DB on every request (O2).

    expires_at is the access-code expiry (None = no expiry); the session
    itself lives 4 hours (14.400 s) server-side.
    """

    role: str
    expires_at: datetime | None = None


class CreateEduCodeRequest(BaseModel):
    """Request body for generating a new educational access code (BE-EP-044)."""

    class_name: str = Field(
        ..., min_length=1, max_length=100, description="Name of the class or group"
    )
    teacher_email: EmailStr = Field(..., description="Teacher or school contact email")
    role: Literal["student", "teacher"] = Field(
        default="student", description="Role granted by the code"
    )
    valid_hours: int = Field(
        default=4, ge=1, le=168, description="Validity period in hours (1h to 7d)"
    )


class EduCodeCreateResponse(BaseModel):
    """Response returned upon code creation (code is returned ONLY once)."""

    id: int
    code: str
    class_name: str
    teacher_email: str
    role: str
    expires_at: datetime | None = None
    created_at: datetime
    is_active: bool = True


class EduCodeItem(BaseModel):
    """Educational access code item for management lists (plaintext code excluded)."""

    id: int
    class_name: str
    teacher_email: str
    role: str
    expires_at: datetime | None = None
    created_at: datetime
    is_active: bool = True


class EduCodeListResponse(BaseModel):
    """List of educational access codes."""

    items: list[EduCodeItem]
    total: int


# ============================================================================
# Portal settings schemas
# ============================================================================


class PortalSettingsResponse(BaseModel):
    """Public portal settings (white-label branding)."""

    model_config = ConfigDict(from_attributes=True)

    platform_name_nl: str
    platform_name_en: str | None = None
    primary_color: str = "#1a2f45"
    accent_color: str = "#e8b86d"
    logo_url: str | None = None
    favicon_url: str | None = None
    guidelines_nl: str | None = None
    guidelines_en: str | None = None
    about_nl: str | None = None
    about_en: str | None = None
    contact_email: str | None = None


HEX_COLOR_PATTERN: str = r"^#[0-9a-fA-F]{6}$"


class PortalSettingsUpdateRequest(BaseModel):
    """Request to update portal white-label branding and settings (BE-EP-047)."""

    platform_name_nl: str | None = Field(None, min_length=1, max_length=120)
    platform_name_en: str | None = Field(None, max_length=120)
    primary_color: str | None = Field(None, pattern=HEX_COLOR_PATTERN)
    accent_color: str | None = Field(None, pattern=HEX_COLOR_PATTERN)
    logo_url: str | None = Field(None, max_length=500)
    favicon_url: str | None = Field(None, max_length=500)
    guidelines_nl: str | None = None
    guidelines_en: str | None = None
    about_nl: str | None = None
    about_en: str | None = None
    contact_email: str | None = Field(None, max_length=255)


# ============================================================================
# Takedown schemas
# ============================================================================


class TakedownCreateRequest(BaseModel):
    """Request a content takedown."""

    content_id: int = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=2000)
    contact_email: str = Field(..., min_length=3, max_length=255)
    hcaptcha_token: str | None = Field(None, description="hCaptcha response token")


class TakedownResponse(BaseModel):
    """Takedown request created."""

    id: int
    status: str = "pending"
    message: str = "Takedown request submitted successfully."


class TakedownListItem(BaseModel):
    """Notice & Takedown item in curator overview (BE-EP-051)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    content_id: int
    content_title: str | None = None
    content_type: str | None = None
    content_status: str | None = None
    requester_name: str
    requester_email: str
    legal_basis: str
    status: str
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class TakedownListResponse(BaseModel):
    """Paginated Notice & Takedown curation queue response."""

    items: list[TakedownListItem]
    total: int
    page: int = 1
    page_size: int = 20
    status_filter: str | None = None


class TakedownDetailResponse(BaseModel):
    """Detailed Notice & Takedown report for curator inspection."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    content_id: int
    content_title: str | None = None
    content_type: str | None = None
    content_status: str | None = None
    content_description: str | None = None
    content_creator_name: str | None = None
    content_file_url: str | None = None
    requester_name: str
    requester_email: str
    legal_basis: str
    status: str
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class TakedownResolveRequest(BaseModel):
    """Curator action to resolve or escalate a takedown request (DSA Art. 16/17)."""

    status: str = Field(
        ...,
        description="Target status: approved (content taken down), rejected (unfounded), or escalated",
    )
    resolution_note: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Mandatory motivation / statement of reasons for the decision",
    )
    notify_requester: bool = Field(
        True,
        description="Whether to send automated decision notice via Brevo to requester",
    )


class TakedownResolveResponse(BaseModel):
    """Result of resolving a Notice & Takedown request."""

    id: int
    content_id: int
    status: str
    content_status: str
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    message: str = "Notice & Takedown melding succesvol afgehandeld."


# ============================================================================
# Newsletter schemas
# ============================================================================


class NewsletterSubscribeRequest(BaseModel):
    """Subscribe to newsletter."""

    email: str = Field(..., min_length=3, max_length=255)
    hcaptcha_token: str | None = Field(None, description="hCaptcha response token")


class NewsletterUnsubscribeRequest(BaseModel):
    """Unsubscribe from newsletter."""

    email: str = Field(..., min_length=3, max_length=255)
    token: str = Field(..., min_length=1)


class NewsletterConfirmRequest(BaseModel):
    """Confirm newsletter subscription via double opt-in token."""

    email: str = Field(..., min_length=3, max_length=255)
    token: str = Field(..., min_length=1, max_length=128)


class NewsletterResponse(BaseModel):
    """Generic newsletter response (no enumeration)."""

    message: str


# ============================================================================
# Tenant Resolution schemas (BE-EP-042)
# ============================================================================


class TenantPublicInfo(BaseModel):
    """Public tenant information for frontend bootstrapping."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    domain: str | None = None
    is_active: bool = True


# ============================================================================
# Curation Analytics schemas (BE-EP-045 / ADR-029 P2-3)
# ============================================================================


class TagDistributionItem(BaseModel):
    """Distribution metric for an AI-generated or curated content tag."""

    model_config = ConfigDict(from_attributes=True)

    tag: str
    tag_type: str
    count: int = Field(..., ge=0)
    average_confidence: float = Field(..., ge=0.0, le=1.0)


class NewsletterAnalytics(BaseModel):
    """Newsletter subscription metrics for a tenant."""

    model_config = ConfigDict(from_attributes=True)

    total_subscribers: int = Field(..., ge=0)
    verified_subscribers: int = Field(..., ge=0)


class EducationalAnalytics(BaseModel):
    """Educational access metrics for a tenant."""

    model_config = ConfigDict(from_attributes=True)

    active_codes: int = Field(..., ge=0)
    total_codes: int = Field(..., ge=0)


class CurationAnalyticsResponse(BaseModel):
    """Aggregated curation and platform KPIs for curators and admins."""

    model_config = ConfigDict(from_attributes=True)

    status_counts: dict[str, int]
    total_content: int = Field(..., ge=0)
    average_moderation_seconds: float | None = None
    tag_distribution: list[TagDistributionItem] = Field(default_factory=list)
    newsletter: NewsletterAnalytics
    education: EducationalAnalytics


# ============================================================================
# Donation schemas (BE-EP-046 / ADR-029 P2-2)
# ============================================================================

DonationFrequency = Literal["one_time", "monthly"]


class DonationCheckoutRequest(BaseModel):
    """Request a Stripe Checkout session for a foundation donation/adoption."""

    amount_cents: int = Field(
        ..., ge=100, le=500000, description="Amount in eurocents (min EUR 1, max EUR 5000)"
    )
    frequency: DonationFrequency = Field(
        "one_time", description="Donation frequency: one_time or monthly"
    )
    donor_email: EmailStr = Field(..., description="Email address for payment confirmation")
    donor_name: str | None = Field(None, max_length=255, description="Donor name or company")
    is_anonymous: bool = Field(False, description="Whether to mask donor name in public stats/wall")
    monument_id: int | None = Field(
        None, description="Optional foundation_content id for specific monument adoption"
    )
    message: str | None = Field(
        None, max_length=500, description="Optional message for the supporters wall"
    )
    hcaptcha_token: str | None = Field(
        None, description="hCaptcha response token for bot protection"
    )


class DonationCheckoutResponse(BaseModel):
    """Stripe Checkout session response."""

    checkout_url: str
    session_id: str
    amount_cents: int
    frequency: str


class DonationHistoryItem(BaseModel):
    """Public donation item for supporters wall / statistics."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    amount_cents: int
    frequency: str
    donor_name: str | None
    message: str | None
    created_at: str
    is_anonymous: bool


class DonationStatsResponse(BaseModel):
    """Public transparency metrics for foundation donations."""

    model_config = ConfigDict(from_attributes=True)

    total_raised_cents: int = Field(..., ge=0)
    total_donations_count: int = Field(..., ge=0)
    monthly_supporters_count: int = Field(..., ge=0)
    recent_donations: list[DonationHistoryItem] = Field(default_factory=list)


class DonationAdminItem(BaseModel):
    """Admin-only donation record with full details including email and status."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    amount_cents: int
    frequency: str
    donor_email: str
    donor_name: str | None
    is_anonymous: bool
    monument_id: int | None
    message: str | None
    status: str
    stripe_session_id: str | None
    created_at: str


class DonationAdminListResponse(BaseModel):
    """List of donation records for curators and foundation admins."""

    model_config = ConfigDict(from_attributes=True)

    total: int
    items: list[DonationAdminItem] = Field(default_factory=list)


# ============================================================================
# Contact & Support schemas (BE-EP-048 / ADR-029 P2)
# ============================================================================

ContactCategory = Literal["algemeen", "educatie", "donatie", "archief", "samenwerking"]


class ContactSubmissionRequest(BaseModel):
    """Request body for submitting a contact message to the foundation."""

    name: str = Field(..., min_length=2, max_length=120, description="Full name of submitter")
    email: EmailStr = Field(..., description="Valid email address for response")
    subject: str = Field(..., min_length=3, max_length=200, description="Subject of the message")
    category: ContactCategory = Field("algemeen", description="Category of the inquiry")
    message: str = Field(..., min_length=10, max_length=5000, description="Message body or inquiry")
    hcaptcha_token: str | None = Field(None, description="hCaptcha token for spam protection")


class ContactSubmissionResponse(BaseModel):
    """Response returned upon successfully receiving a contact inquiry."""

    reference_id: str = Field(..., description="Unique reference ticket ID (CON-YYYYMMDD-XXXX)")
    status: str = Field("received", description="Status of submission")
    message: str = Field(..., description="Confirmation message in Dutch")
    created_at: str = Field(..., description="ISO 8601 timestamp of receipt")
