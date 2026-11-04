"""Het art.-5(1)(e)-bewijs van de opruimactor binden aan de onuitwisbare keten (ADR-036 OP-121).

**De bevinding.** `HashChainVerifier._compute_hash` dekt vijf velden: `tenant_id`, `action`,
`resource`, `timestamp` en de vorige hash. `records_deleted`, `cutoff_date` en
`regulatory_basis` staan sinds 2026-08-10 in `event_metadata` (ADR-036 OP-108) en dus BUITEN de
hash. `category` en `jurisdiction` zitten wel gedekt, want die staan al in `resource`
(`retention_cleanup:{category}_{jurisdiction}`). Wie met UPDATE-recht `records_deleted` van 0
naar 40.000 zet, blijft onzichtbaar voor de ketenverificatie.

**De gekozen weg: binden, niet de hashfunctie verbreden.** Zelfde besluit als H-2
(`hitl_evidence.py`): `_compute_hash` uitbreiden breekt elke bestaande keten en is een besluit
van Rakesh. Een digest over het bewijs gaat in `resource`, en `resource` WORDT gehasht.

**Waarom kaal en niet met een sleutel.** Dezelfde afweging als `hitl_evidence.py`: de drie
waarden staan al leesbaar naast de digest in `event_metadata`. Een sleutel voegt daar geen
vertrouwelijkheid toe -- geen van de drie is een geheim of een persoonsgegeven -- maar neemt wel
het vermogen weg van een auditor zonder sleutel om na te rekenen.

**Eigen domeinscheiding en resource-vorm**, zodat deze digest nooit met een `hitl_evidence`-
digest kan samenvallen en `HashChainVerifier` de twee vormen uit elkaar kan houden.
"""

from __future__ import annotations

import hashlib
import json
import re

#: Eigen domeinscheiding, zodat deze digest nooit gelijk kan zijn aan een `hitl_evidence`- of
#: `value_digest`-digest over dezelfde invoer.
_DOMEIN = "sanskritisetu:retention-evidence:v1"

#: 32 hex = 128 bit, zelfde lengte-afweging als `hitl_evidence.py`.
_DIGEST_LENGTE = 32

#: `retention_cleanup:<category>_<jurisdiction>|ev=<32 hex>`. Het voorvoegsel blijft
#: ongewijzigd, zodat bestaande prefix-queries op `retention_cleanup:` blijven werken.
_RESOURCE_VORM = re.compile(r"^(?P<basis>retention_cleanup:[^|]+)\|ev=(?P<digest>[0-9a-f]{32})$")


def evidence_digest(
    *,
    records_deleted: int | None,
    cutoff_date: str | None,
    regulatory_basis: str | None,
) -> str:
    """De digest over het bewijs dat buiten `_compute_hash` valt.

    Geef exact de waarden mee zoals ze in `event_metadata` worden opgeslagen: `cutoff_date` is
    dus de `.isoformat()`-string, niet het `datetime`-object. Canonieke JSON (gesorteerde
    sleutels, vaste scheidingstekens) in plaats van naieve aaneenschakeling.
    """
    kanoniek = json.dumps(
        {
            "domein": _DOMEIN,
            "records_deleted": records_deleted,
            "cutoff_date": cutoff_date,
            "regulatory_basis": regulatory_basis,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(kanoniek.encode("utf-8")).hexdigest()[:_DIGEST_LENGTE]


def build_resource(
    *,
    category: str,
    jurisdiction: str,
    records_deleted: int,
    cutoff_date: str,
    regulatory_basis: str,
) -> str:
    """De `resource`-waarde voor een opruim-auditregel, met het bewijs eraan gebonden."""
    digest = evidence_digest(
        records_deleted=records_deleted,
        cutoff_date=cutoff_date,
        regulatory_basis=regulatory_basis,
    )
    return f"retention_cleanup:{category}_{jurisdiction}|ev={digest}"


def evidence_matches(
    resource: str | None,
    *,
    records_deleted: int | None,
    cutoff_date: str | None,
    regulatory_basis: str | None,
) -> bool | None:
    """Klopt de digest in `resource` nog met wat er in `event_metadata` staat?

    Geeft `None` terug als `resource` niet de opruim-vorm heeft -- dan valt er niets na te
    rekenen en is dat geen fout. Ook `None` voor rijen van voor deze fix: die hebben geen
    `|ev=`-deel en zijn niet gedekt.
    """
    if not resource:
        return None
    overeenkomst = _RESOURCE_VORM.match(resource)
    if overeenkomst is None:
        return None
    verwacht = evidence_digest(
        records_deleted=records_deleted,
        cutoff_date=cutoff_date,
        regulatory_basis=regulatory_basis,
    )
    return overeenkomst.group("digest") == verwacht
