"""
Generic refusal messages for BLOCKED Co-Pilot responses.

Per ADR-027 and copilot-architecture.md section 6:
    - BLOCKED verdicts MUST NOT leak Officer veto reasons to the user.
    - Only a generic, i18n-aware refusal is returned.
    - The internal reason is logged server-side with full context.

Per CLAUDE.md regel 10: ASCII-only in source code.
"""

from __future__ import annotations

GENERIC_REFUSALS: dict[str, str] = {
    "nl": "Deze actie kan niet worden uitgevoerd.",
    "en": "This action cannot be completed.",
    "hi": "\u092f\u0939 \u0915\u093e\u0930\u094d\u092f \u092a\u0942\u0930\u093e \u0928\u0939\u0940\u0902 \u0915\u093f\u092f\u093e \u091c\u093e \u0938\u0915\u0924\u093e\u0964",
    "sa": "\u090f\u0924\u0924\u094d \u0915\u093e\u0930\u094d\u092f\u0902 \u092a\u0942\u0930\u094d\u0923\u0902 \u0915\u093er\u094d\u0924\u0941\u0902 \u0928 \u0936\u0915\u094d\u092f\u0924\u0947\u0964",
}


def generic_refusal(language: str) -> str:
    """Return a generic refusal message in the requested language.

    Falls back to English if the language is not supported.
    """
    return GENERIC_REFUSALS.get(language, GENERIC_REFUSALS["en"])


# Weigering als de copilot een tool voorstelt die buiten zijn eigen profiel valt
# (`config/tool_permissions.yml`, agent `copilot`). Dat is geen veto-reden van een Officer, dus
# ADR-027 staat het noemen van de route toe: de gebruiker moet weten waar het WEL kan, anders
# is de weigering een muur zonder deur. Alleen tools waarvoor een bevoegde agent bestaat staan
# hier; voor de rest valt de tekst terug op de generieke weigering.
_AGENT_ROUTE_FOR_TOOL: dict[str, dict[str, str]] = {
    "send_payment_reminder": {
        "nl": (
            "De copilot mag zelf geen betalingsherinnering aanvragen. Dat doet de "
            "debiteurenagent: start die voor deze debiteur, dan komt de herinnering ter "
            "goedkeuring bij je terug."
        ),
        "en": (
            "The copilot may not request a payment reminder itself. The receivables agent "
            "(debiteurenagent) does that: start it for this debtor and the reminder comes "
            "back to you for approval."
        ),
    },
}


def not_authorized_refusal(language: str, tool_name: str) -> str:
    """Weigering voor een tool buiten het copilot-profiel, met de bevoegde route als die er is."""
    texts = _AGENT_ROUTE_FOR_TOOL.get(tool_name)
    if texts is None:
        return generic_refusal(language)
    return texts.get(language, texts["en"])
