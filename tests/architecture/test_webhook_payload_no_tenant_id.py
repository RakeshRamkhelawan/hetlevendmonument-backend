"""VERVANGEN op 2026-09-18 door `test_geen_tenant_id_in_een_request_body.py`.

Deze guard toetste EEN klasse (`WebhookPayload`) in EEN bestand
(`src/core/activepieces/schemas.py`). Gemeten die dag: die klasse heeft nul importeurs, dus
hij bewaakte dode code -- en hij stond groen terwijl er elders in de repo wel degelijk een
`tenant_id` in een request body zat (`ExecutionEvent` in
`src/core/api/webhooks/activepieces_handler.py`, gebruikt door twee webhook-endpoints).

De vervanger scant de HELE `src/`, onderscheidt request-bodies van dependencies en
response-modellen, en heeft mutatiebewijs in beide richtingen.

Dit bestand blijft bestaan met de oorspronkelijke controle erin, zodat de al gedane
opruiming van `WebhookPayload` niet stilletjes kan terugkeren -- maar de brede guard is
sinds vandaag de echte bewaker.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SCHEMAS_FILE = Path(__file__).parents[2] / "src" / "core" / "activepieces" / "schemas.py"


def test_webhook_payload_has_no_tenant_id() -> None:
    """`WebhookPayload` mag geen `tenant_id`-veld bevatten (CLAUDE.md NOOIT-lijst)."""
    boom = ast.parse(_SCHEMAS_FILE.read_text(encoding="utf-8"))
    velden = [
        item.target.id
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.ClassDef) and knoop.name == "WebhookPayload"
        for item in ast.walk(knoop)
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
    ]

    assert "tenant_id" not in velden, (
        "WebhookPayload bevat weer een `tenant_id`-veld. De tenant komt bij een webhook uit "
        "de eigenaar van de resource in de database, nooit uit de payload."
    )
