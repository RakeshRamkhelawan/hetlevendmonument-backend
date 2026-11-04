"""Prometheus-tellers voor de integriteit van de ADR-019-hashketen (ADR-036 OP-109).

De raad-keten had al een teller plus alertregel (`copilot_hash_chain_breaks_total` +
`infra/prometheus/alerts/copilot-council.yml`). De `audit_logs`-keten had niets -- terwijl dat
de keten is waarin het art.-14-bewijs van een HIGH-risk goedkeuring staat.

Zonder teller is de uitkomst van de verificatie alleen een logregel in een worker, en er komt
geen melding wanneer iets NIET gebeurt. Dat is de terugkerende faalvorm in dit project.

**Waarom drie tellers en geen gauge.** Een gauge met de rijtelling per tenant groeit met elke
tenant en staat nooit op nul, dus daar valt geen zinnige alertregel op te maken. Deze drie horen
alle drie op nul te staan; elke verhoging is een gebeurtenis.

**Cardinaliteit.** `tenant_id` als label is toegestaan op een teller (zeldzame ophogingen,
incident-response heeft de tenantcontext nodig) en NIET op een histogram -- zie
`src/core/copilot/council/metrics.py:3-6`. `user_id` nooit.
"""

from __future__ import annotations

from src.core.observability.metrics import _get_or_create_counter

#: Een gehashte rij die niet meer klopt: hercompute mislukt of de schakel naar de vorige rij is
#: verbroken. Dit is het P0-signaal -- het betekent manipulatie, geen dekkingsgat.
audit_chain_tampering_total = _get_or_create_counter(
    "audit_chain_tampering_total",
    "Detected tampering in the audit_logs hash chain (alerts on any increase).",
    ["tenant_id"],
)

#: Rijen zonder `audit_hash`. Een GAT, geen manipulatie -- maar wel iets dat de keten
#: onverifieerbaar maakt en dat na ADR-036 OP-108 niet meer hoort te ontstaan.
audit_chain_unhashed_total = _get_or_create_counter(
    "audit_chain_unhashed_total",
    "Audit log rows without a hash, found during verification (coverage gap, not tampering).",
    ["tenant_id"],
)

#: De verificatie zelf kon niet draaien. Bewust apart: een mislukte verificatie is iets anders
#: dan een geslaagde verificatie die niets vond, en die twee mogen niet op hetzelfde getal
#: uitkomen -- anders leest "nul manipulatie" als "alles in orde" terwijl er niets is gekeken.
audit_chain_verification_errors_total = _get_or_create_counter(
    "audit_chain_verification_errors_total",
    "Audit chain verification runs that failed to complete.",
    ["tenant_id"],
)
