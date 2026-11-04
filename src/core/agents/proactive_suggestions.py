"""
Static proactive suggestion table for Focus Builder session_init.

No LLM call -- avoids WebSocket latency. For each pair of connected apps
with a logical trigger->action relationship, surface a pre-written suggestion.
"""

from typing import TypedDict

SUGGESTION_PAIRS: list[tuple[str, str, str, str]] = [
    # (trigger_app, action_app, label, prompt)
    (
        "asana",
        "teams",
        "Teams-bericht bij nieuwe Asana-taak",
        "Maak een workflow die een Teams bericht stuurt wanneer een Asana taak wordt voltooid",
    ),
    (
        "asana",
        "outlook",
        "Asana-taak aanmaken vanuit Outlook-email",
        "Maak een workflow die een Asana taak aanmaakt als een email binnenkomt met label 'taak'",
    ),
    (
        "teams",
        "outlook",
        "Outlook-herinnering bij Teams-mention",
        "Maak een workflow die een Outlook agenda-item aanmaakt als iemand mij mention in Teams",
    ),
    (
        "gmail",
        "slack",
        "Slack-bericht bij nieuwe Gmail",
        "Maak een workflow die een Slack bericht stuurt bij elke nieuwe ongelezen email in Gmail",
    ),
    (
        "github",
        "teams",
        "Teams-bericht bij nieuwe GitHub PR",
        "Maak een workflow die een Teams bericht stuurt bij elke nieuwe GitHub pull request",
    ),
]

MAX_SUGGESTIONS = 3


class Suggestion(TypedDict):
    label: str
    prompt: str


def get_suggestions(connected_apps: list[str]) -> list[Suggestion]:
    """Return up to MAX_SUGGESTIONS for the given connected apps (case-insensitive)."""
    normalised = {app.lower() for app in connected_apps}
    results: list[Suggestion] = []
    for trigger, action, label, prompt in SUGGESTION_PAIRS:
        if trigger in normalised and action in normalised:
            results.append({"label": label, "prompt": prompt})
            if len(results) >= MAX_SUGGESTIONS:
                break
    return results
