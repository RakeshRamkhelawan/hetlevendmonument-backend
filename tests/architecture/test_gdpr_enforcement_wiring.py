"""Architecture tests for GDPR enforcement wiring gaps.

These tests are INTENTIONALLY FAILING at commit time because the detected
problems are present in the codebase. They become green once the corresponding
sprint backlog items are implemented.

Sprint backlog reference: SP-DLP-001

Each test detects one concrete gap in GDPR enforcement wiring:
  GDPR-003  has_consent hardcoded True in consent_router.py
  GDPR-005  portability_router exports all tenant users without user_id filter
  GDPR-011  access_router audit-trail query does not filter on user_id
  GDPR-009  log_ai_decision in ai_transparency_service.py does not call
            check_profiling_opt_out before persisting the decision

Only Python stdlib is used (pathlib, re). No src.core imports.
"""

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (relative to repo root -- resolved from this file's location)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]

_CONSENT_ROUTER = _REPO_ROOT / "src" / "core" / "api" / "v1" / "privacy" / "consent_router.py"
_PORTABILITY_ROUTER = (
    _REPO_ROOT / "src" / "core" / "api" / "v1" / "gdpr_compliance" / "portability_router.py"
)
_ACCESS_ROUTER = _REPO_ROOT / "src" / "core" / "api" / "v1" / "gdpr_compliance" / "access_router.py"
_AI_TRANSPARENCY_SERVICE = _REPO_ROOT / "src" / "core" / "governance" / "ai_transparency_service.py"
_COUNCIL_FACTORY = _REPO_ROOT / "src" / "core" / "copilot" / "council" / "factory.py"


# ---------------------------------------------------------------------------
# GDPR-003
# ---------------------------------------------------------------------------
def test_gdpr_003_has_consent_not_hardcoded_true() -> None:
    """Verify has_consent is derived from ConsentRecord, not hardcoded True. [SP-DLP-001 GDPR-003 FIXED]

    The GET /consent-status endpoint must return has_consent derived from
    the consent object returned by CookieConsentManager, not a literal True.
    Hardcoding True violates GDPR Art. 7 (verifiable, freely given consent).
    """
    assert _CONSENT_ROUTER.exists(), (
        f"Bestand niet gevonden: {_CONSENT_ROUTER}. Pad is incorrect of het bestand is verplaatst."
    )

    source = _CONSENT_ROUTER.read_text(encoding="utf-8")

    # Pattern matches both:
    #   "has_consent": True
    #   "has_consent" : True
    #   'has_consent': True
    pattern = re.compile(r"""["']has_consent["']\s*:\s*True""")
    match = pattern.search(source)

    assert match is None, (
        f"GDPR-003 [SP-DLP-001 REGRESSION]: 'has_consent' is weer hardcoded True in "
        f"{_CONSENT_ROUTER.relative_to(_REPO_ROOT)}. "
        "Consent-status moet worden afgeleid uit de ConsentRecord die "
        "CookieConsentManager teruggeeft, niet als literal True worden "
        "teruggegeven. Dit schendt GDPR Art. 7 (aantoonbare toestemming). "
        "Fixt door SP-DLP-001 GDPR-003."
    )


# ---------------------------------------------------------------------------
# GDPR-005
# ---------------------------------------------------------------------------
def test_gdpr_005_portability_export_filters_on_current_user() -> None:
    """Detect missing user_id filter in portability_router.py personal-data export.

    The POST /api/gdpr/export endpoint queries ``select(User).filter(
    User.tenant_id == tenant_id)`` on lines 109-111, which returns ALL
    users in the tenant. A regular user requesting their own data export
    (GDPR Art. 20) would receive data belonging to all other users in
    the same tenant -- a serious data leak.

    What fixes it: SP-DLP-001 GDPR-005 -- add
    ``User.id == current_user.id`` (or equivalent ``current_user.id``)
    to the User query so that only the requesting user's own records are
    exported.

    This test MUST be red until that fix is applied.
    """
    assert _PORTABILITY_ROUTER.exists(), (
        f"Bestand niet gevonden: {_PORTABILITY_ROUTER}. "
        "Pad is incorrect of het bestand is verplaatst."
    )

    source = _PORTABILITY_ROUTER.read_text(encoding="utf-8")

    # Detect the User query block: find 'select(User)' and check whether
    # 'current_user.id' appears within the same filter() expression.
    # Strategy: extract the slice of source starting at 'select(User)'
    # up to the next 'scalars()' call, and check for 'current_user.id'
    # in that slice.  This avoids false positives from the function
    # signature (``current_user: User = Depends(...)``).
    user_query_match = re.search(r"select\(User\).*?\.scalars\(\)", source, re.DOTALL)

    if user_query_match is None:
        # No User query at all -- also unexpected but not the specific gap.
        assert False, (  # noqa: B011
            "GDPR-005 [SP-DLP-001]: 'select(User)...scalars()' niet gevonden "
            f"in {_PORTABILITY_ROUTER.relative_to(_REPO_ROOT)}. "
            "Controleer of de structuur is gewijzigd. "
            "Fixt door SP-DLP-001 GDPR-005."
        )

    user_query_block = user_query_match.group(0)
    has_user_id_filter = "current_user.id" in user_query_block

    assert has_user_id_filter, (
        "GDPR-005 [SP-DLP-001]: portability_router.py exporteert ALLE "
        "gebruikers van de tenant (select(User).filter(User.tenant_id == ...)) "
        "zonder te filteren op de aanvragende gebruiker. "
        "Het User.id == current_user.id filter ontbreekt in de query-expressie. "
        "Dit lekt persoonsgegevens van andere gebruikers in dezelfde tenant "
        "en schendt GDPR Art. 20 (recht op dataportabiliteit is persoonsgebonden). "
        "Voeg 'User.id == current_user.id' toe aan de User-query. "
        "Fixt door SP-DLP-001 GDPR-005."
    )


# ---------------------------------------------------------------------------
# GDPR-011
# ---------------------------------------------------------------------------
def test_gdpr_011_audit_trail_query_filters_on_user_id() -> None:
    """Detect missing user_id filter in access_router.py audit-trail query.

    The _build_audit_query function in access_router.py filters only on
    tenant_id, action_type and date range. It never restricts results to
    the requesting user's own records. A user can therefore query audit
    logs for actions performed by other users in the same tenant.

    What fixes it: SP-DLP-001 GDPR-011 -- add a
    ``AuditLog.user_id == current_user.id`` filter inside
    _build_audit_query (or thread current_user.id through the call site).

    This test MUST be red until that fix is applied.
    """
    assert _ACCESS_ROUTER.exists(), (
        f"Bestand niet gevonden: {_ACCESS_ROUTER}. Pad is incorrect of het bestand is verplaatst."
    )

    source = _ACCESS_ROUTER.read_text(encoding="utf-8")

    # Check whether '_build_audit_query' contains a user_id filter.
    # Strategy: extract the function body and check for 'user_id'.
    func_match = re.search(
        r"def _build_audit_query\b.*?(?=\ndef |\nclass |\Z)",
        source,
        re.DOTALL,
    )

    if func_match is None:
        # Function does not exist at all -- also a gap.
        assert False, (  # noqa: B011
            "GDPR-011 [SP-DLP-001]: _build_audit_query niet gevonden in "
            f"{_ACCESS_ROUTER.relative_to(_REPO_ROOT)}. "
            "De functie moet bestaan EN een user_id-filter bevatten. "
            "Fixt door SP-DLP-001 GDPR-011."
        )

    func_body = func_match.group(0)
    has_user_id_filter = "user_id" in func_body

    assert has_user_id_filter, (
        f"GDPR-011 [SP-DLP-001]: _build_audit_query in "
        f"{_ACCESS_ROUTER.relative_to(_REPO_ROOT)} filtert NIET op user_id. "
        "De audit-trail query retourneert acties van alle gebruikers in de "
        "tenant, waardoor gebruikers elkaars activiteitslog kunnen inzien. "
        "Dit schendt GDPR Art. 15 (inzagerecht is persoonsgebonden). "
        "Voeg 'AuditLog.user_id == current_user_id' toe aan de query. "
        "Fixt door SP-DLP-001 GDPR-011."
    )


# ---------------------------------------------------------------------------
# GDPR-009
# ---------------------------------------------------------------------------
def test_gdpr_009_log_ai_decision_calls_check_profiling_opt_out() -> None:
    """Detect missing check_profiling_opt_out call in log_ai_decision.

    AITransparencyService.log_ai_decision persists an AI decision (which
    may involve profiling) without first verifying that the user has not
    opted out of profiling under GDPR Art. 21. The check_profiling_opt_out
    method exists on the service but is never called from log_ai_decision.

    What fixes it: SP-DLP-001 GDPR-009 -- call check_profiling_opt_out
    before creating the AIDecision database record inside log_ai_decision.
    If the user has opted out AND profiling_involved=True, raise an
    appropriate error or skip the profiling-related data.

    This test MUST be red until that fix is applied.
    """
    assert _AI_TRANSPARENCY_SERVICE.exists(), (
        f"Bestand niet gevonden: {_AI_TRANSPARENCY_SERVICE}. "
        "Pad is incorrect of het bestand is verplaatst."
    )

    source = _AI_TRANSPARENCY_SERVICE.read_text(encoding="utf-8")

    # Step 1: verify check_profiling_opt_out exists anywhere in the file.
    if "check_profiling_opt_out" not in source:
        assert False, (  # noqa: B011
            "GDPR-009 [SP-DLP-001]: check_profiling_opt_out is NIET aanwezig "
            f"in {_AI_TRANSPARENCY_SERVICE.relative_to(_REPO_ROOT)}. "
            "De methode moet bestaan EN worden aangeroepen vanuit "
            "log_ai_decision voordat de beslissing wordt opgeslagen. "
            "Fixt door SP-DLP-001 GDPR-009."
        )

    # Step 2: extract the body of log_ai_decision and verify the call is present.
    func_match = re.search(
        r"async def log_ai_decision\b.*?(?=\n    async def |\n    def |\nclass |\Z)",
        source,
        re.DOTALL,
    )

    if func_match is None:
        assert False, (  # noqa: B011
            "GDPR-009 [SP-DLP-001]: log_ai_decision niet gevonden in "
            f"{_AI_TRANSPARENCY_SERVICE.relative_to(_REPO_ROOT)}. "
            "De methode moet bestaan EN check_profiling_opt_out aanroepen. "
            "Fixt door SP-DLP-001 GDPR-009."
        )

    func_body = func_match.group(0)
    calls_opt_out_check = "check_profiling_opt_out" in func_body

    assert calls_opt_out_check, (
        "GDPR-009 [SP-DLP-001]: log_ai_decision in "
        f"{_AI_TRANSPARENCY_SERVICE.relative_to(_REPO_ROOT)} "
        "roept check_profiling_opt_out NIET aan voor de opslag van de beslissing. "
        "Een gebruiker die profiling heeft geweigerd (GDPR Art. 21) wordt nog "
        "steeds geprofileerd omdat de opt-out niet wordt gecheckt. "
        "Voeg await self.check_profiling_opt_out(...) toe aan het begin van "
        "log_ai_decision (voor db.add). "
        "Fixt door SP-DLP-001 GDPR-009."
    )


# ---------------------------------------------------------------------------
# AUDIT-002
# ---------------------------------------------------------------------------
def test_audit_002_build_council_does_not_inject_null_gdpr_enforcer() -> None:
    """Detect a no-op GDPR enforcer wired into the Council's PrivacyOfficer.

    build_council() constructs PrivacyOfficer with gdpr_enforcer=_NullGDPREnforcer(),
    a stub whose detect_pii() always returns []. Every Council decision -- including
    the future ADR-036 D2 background_gate.py entry point -- is therefore approved
    without any real PII check, regardless of how good src.core.governance.gdpr_enforcer's
    detection logic is.

    What fixes it: AUDIT-002 -- inject a real GDPREnforcer() instance instead.

    This test MUST be red until that fix is applied.
    """
    assert _COUNCIL_FACTORY.exists(), (
        f"Bestand niet gevonden: {_COUNCIL_FACTORY}. Pad is incorrect of het bestand is verplaatst."
    )

    source = _COUNCIL_FACTORY.read_text(encoding="utf-8")

    func_match = re.search(
        r"async def build_council\b.*?\Z",
        source,
        re.DOTALL,
    )
    assert func_match is not None, (
        f"AUDIT-002: build_council niet gevonden in {_COUNCIL_FACTORY.relative_to(_REPO_ROOT)}."
    )

    func_body = func_match.group(0)
    assert "_NullGDPREnforcer()" not in func_body, (
        "AUDIT-002 [REGRESSION]: build_council() injecteert weer _NullGDPREnforcer() "
        f"in {_COUNCIL_FACTORY.relative_to(_REPO_ROOT)}. Dit maakt de PrivacyOfficer's "
        "PII-detectie een no-op voor elke Council-beslissing, ook via de toekomstige "
        "achtergrondingang (ADR-036 D2). Injecteer een echte GDPREnforcer()-instantie "
        "(src.core.governance.gdpr_enforcer.GDPREnforcer) i.p.v. de stub."
    )
