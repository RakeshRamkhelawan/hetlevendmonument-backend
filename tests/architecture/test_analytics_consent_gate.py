"""Architecture guard -- analytics ingest enforces consent (GDPR-004).

Dag 8 (BE-GDPR-002) sloot een gat: `POST /events` (`submit_events`) persisteerde elk
`AnalyticsEvent` zonder de opgeslagen analytics-consent van de gebruiker te checken.
De fix hangt de ingest aan de `analytics_consent_allowed`-dependency (ADR-033 facade,
fail-closed) en slaat events zonder consent over.

Deze guard faalt als die enforcement verdwijnt. Regressie-guard voor SP dag 8
BE-GDPR-002. Alleen stdlib (pathlib, re) -- geen src-imports.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVENTS_ROUTER = (
    _REPO_ROOT / "src" / "core" / "api" / "v1" / "analytics_ingest" / "events_router.py"
)


def _submit_events_body() -> str:
    assert _EVENTS_ROUTER.exists(), (
        f"Bestand niet gevonden: {_EVENTS_ROUTER}. Pad incorrect of bestand verplaatst."
    )
    source = _EVENTS_ROUTER.read_text(encoding="utf-8")
    func_match = re.search(
        r"async def submit_events\b.*?(?=\n@router|\nasync def |\ndef |\Z)",
        source,
        re.DOTALL,
    )
    assert func_match is not None, (
        "BE-GDPR-002 [REGRESSION]: submit_events niet gevonden in "
        f"{_EVENTS_ROUTER.relative_to(_REPO_ROOT)}. De ingest-endpoint moet bestaan EN "
        "de analytics-consent afdwingen."
    )
    return func_match.group(0)


def test_submit_events_depends_on_consent_gate() -> None:
    """submit_events hangt aan de analytics_consent_allowed-dependency. [BE-GDPR-002]"""
    body = _submit_events_body()
    assert re.search(r"Depends\(\s*analytics_consent_allowed\s*\)", body), (
        "BE-GDPR-002 [REGRESSION]: submit_events hangt niet meer aan "
        "Depends(analytics_consent_allowed). Zonder deze dependency wordt consent niet "
        "gecheckt en worden events zonder toestemming opgeslagen (GDPR art. 6/7). "
        "Fixt door SP dag 8 BE-GDPR-002."
    )


def test_submit_events_skips_persistence_without_consent() -> None:
    """Zonder consent wordt het event NIET gepersisteerd (rejected). [BE-GDPR-002]"""
    body = _submit_events_body()
    # De persistentie (db.add van het AnalyticsEvent) mag alleen achter een
    # 'not analytics_allowed'-guard gebeuren die het event overslaat.
    assert "not analytics_allowed" in body, (
        "BE-GDPR-002 [REGRESSION]: de 'not analytics_allowed'-guard in de event-loop is weg. "
        "Events van een gebruiker zonder analytics-consent moeten worden overgeslagen "
        "(niet gepersisteerd). Fixt door SP dag 8 BE-GDPR-002."
    )
