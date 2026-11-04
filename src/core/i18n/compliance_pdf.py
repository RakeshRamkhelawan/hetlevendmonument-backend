"""i18n strings for the compliance PDF report (NL / EN).

Usage:
    from src.core.i18n.compliance_pdf import get_labels, parse_lang
    lang = parse_lang(request.headers.get("accept-language", ""))
    labels = get_labels(lang)
    pdf.cell(0, 12, labels["cover_title"])
"""

from __future__ import annotations

# fmt: off
_STRINGS: dict[str, dict[str, str]] = {
    "nl": {
        "cover_title": "AI Act Compliance Rapport",
        "generated_at": "Gemaakt op: {}",
        "overall_score": "Totaalscore: {}",
        "policy_header": "Beleid: {}",
        "score": "Score: {}",
        "category": "Categorie: {}",
        "status_fully": "Volledig compliant",
        "status_mostly": "Grotendeels compliant, kleine verbeterpunten",
        "status_attention": "Aandacht vereist",
        "decisions_header": "AI beslissingen laatste 30 dagen",
        "total_decisions": "Totaal beslissingen: {}",
        "high_risk_decisions": "Hoog risico beslissingen: {}",
        "meta_subject": "EU AI Act + GDPR Compliance Status",
    },
    "en": {
        "cover_title": "AI Act Compliance Report",
        "generated_at": "Generated: {}",
        "overall_score": "Overall Score: {}",
        "policy_header": "Policy: {}",
        "score": "Score: {}",
        "category": "Category: {}",
        "status_fully": "Fully compliant",
        "status_mostly": "Mostly compliant, minor improvements needed",
        "status_attention": "Attention required",
        "decisions_header": "AI Decisions Last 30 Days",
        "total_decisions": "Total decisions: {}",
        "high_risk_decisions": "High risk decisions: {}",
        "meta_subject": "EU AI Act + GDPR Compliance Status",
    },
}
# fmt: on


def parse_lang(header_value: str) -> str:
    """Parse Accept-Language header and return 'en' or 'nl'.

    Falls back to 'nl' for missing/unknown languages.
    Supports q-values (e.g. 'en-US,en;q=0.9,nl;q=0.8').
    """
    if not header_value:
        return "nl"

    # Simple parse: first 2-char language code wins
    # This is sufficient for our 2-language support
    parts = header_value.replace(";", ",").split(",")
    for part in parts:
        part = part.strip().lower()
        # Strip q-value weight if present
        if part.startswith("en"):
            return "en"
        if part.startswith("nl"):
            return "nl"

    return "nl"


def get_labels(lang: str) -> dict[str, str]:
    """Return translated labels for the given language code.

    Falls back to Dutch for unknown languages.
    """
    return _STRINGS.get(lang, _STRINGS["nl"])
