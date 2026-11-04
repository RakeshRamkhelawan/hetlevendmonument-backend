"""Het bewijs van een HITL-beslissing binden aan de onuitwisbare keten (ADR-036 H-2).

**De bevinding.** `HashChainVerifier._compute_hash` dekt vijf velden: `tenant_id`, `action`,
`resource`, `timestamp` en de vorige hash. `event_metadata`, `description` en `user_id` staan
daarbuiten. Gemeten: twee auditregels met een verschillende `tool_name` EN een verschillende
`user_id` leveren dezelfde hash op.

Dat raakt de kern van de art.-14-claim. Van een goedgekeurde HIGH-risk actie is WIE hem
goedkeurde (`user_id`) en WAT er is goedgekeurd (`tool_name`, `approval_binding`) precies het
bewijs -- en dat is achteraf te wijzigen zonder dat de ketenverificatie breekt.

**De gekozen weg: binden, niet de hashfunctie verbreden.** `_compute_hash` uitbreiden breekt
elke bestaande keten en is een besluit van Rakesh; dat is geregistreerd. Wat hier gebeurt is
non-destructief: een digest over het bewijs gaat in `resource`, en `resource` WORDT gehasht.

**Waarom een digest en niet de rauwe waarden achter elkaar.** Twee gemeten redenen:

1. `_compute_hash` plakt zijn velden aan elkaar met `":"` en `action` bevat op het faalpad zelf
   al een `":"` (`approved_execution_failed:TimeoutError`). Meer scheidingstekens in `resource`
   vergroot de kans op een verschuivingscollisie. Een digest van vaste lengte doet dat niet.
2. De schema-variant die door `scripts/init_prod_db.py` wordt opgebouwd zet `resource` op
   `VARCHAR(255)`. De rauwe vorm komt in het slechtste geval (een onbekende tool levert een
   pseudoniem van 81 tekens) op ongeveer 236 tekens. Dat is 19 tekens speling, en een
   overschrijding zou binnen `best_effort` stil de hele auditregel laten vallen.

**Waarom over de OPGESLAGEN waarden en niet over de rauwe.** Dit was de scherpste bevinding uit
de Gate 2-review, en de eerste opzet had hem fout. `event_metadata["tool_name"]` bevat NIET de
rauwe toolnaam maar `_safe_tool_name(...)` -- voor een onbekende tool een pseudoniem. Een digest
over de rauwe naam is door niemand na te rekenen, want die naam staat nergens in de rij. Dan is
het geen bewijs maar een ondoorzichtige waarde. Daarom exact de strings zoals ze in de rij
staan.

**Waarom kaal en niet met een sleutel.** De drie waarden staan leesbaar naast de digest in
`event_metadata`. Een sleutel voegt daar geen vertrouwelijkheid toe, maar neemt wel het vermogen
weg van een auditor zonder die sleutel om na te rekenen. Er is ook geen brute-force-orakel:
`approval_binding` is zelf al een keyed HMAC, dus de invoerruimte is niet af te lopen ook al
zijn `tool_name` en `user_id` laag-entropisch. Dit is bewust ANDERS dan `value_digest` in
`redaction.py`, dat wel keyed is omdat het pseudonimiseert -- deze twee horen niet
"geharmoniseerd" te worden.
"""

from __future__ import annotations

import hashlib
import json
import re

#: Eigen domeinscheiding, zodat deze digest nooit gelijk kan zijn aan een `value_digest`
#: over dezelfde invoer.
_DOMEIN = "sanskritisetu:hitl-evidence:v1"

#: Lengte van het digest-deel in `resource`. 32 hex = 128 bit. De aanval is second-preimage
#: (een andere combinatie vinden met dezelfde digest), niet birthday: de aanvaller kan maar
#: een kant kiezen, want de andere ligt al vast in de keten.
_DIGEST_LENGTE = 32

#: `hitl_ticket:<ref>|ev=<32 hex>`. Het voorvoegsel blijft ongewijzigd, zodat bestaande
#: prefix-queries op `hitl_ticket:` blijven werken.
_RESOURCE_VORM = re.compile(r"^(?P<basis>hitl_ticket:[^|]+)\|ev=(?P<digest>[0-9a-f]{32})$")


def evidence_digest(
    *,
    tool_name: str | None,
    user_id: int | None,
    binding: str | None,
) -> str:
    """De digest over het bewijs dat buiten `_compute_hash` valt.

    Geef exact de waarden mee zoals ze in de auditregel worden OPGESLAGEN:
    `event_metadata["tool_name"]` (dus de uitkomst van `_safe_tool_name`), de `user_id`-kolom,
    en `event_metadata["approval_binding"]`.

    `binding` is `None` op het afwijspad; dat wordt als JSON-`null` gecodeerd en is dus een
    andere invoer dan de lege string. Canonieke JSON (gesorteerde sleutels, vaste scheidings-
    tekens) in plaats van naieve aaneenschakeling: `("a", "bc")` en `("ab", "c")` moeten
    verschillende digests opleveren.
    """
    kanoniek = json.dumps(
        {
            "domein": _DOMEIN,
            "tool_name": tool_name,
            "user_id": user_id,
            "binding": binding,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(kanoniek.encode("utf-8")).hexdigest()[:_DIGEST_LENGTE]


def build_resource(
    *,
    ticket_ref: str,
    tool_name: str | None,
    user_id: int | None,
    binding: str | None,
) -> str:
    """De `resource`-waarde voor een HITL-auditregel, met het bewijs eraan gebonden."""
    digest = evidence_digest(tool_name=tool_name, user_id=user_id, binding=binding)
    return f"hitl_ticket:{ticket_ref}|ev={digest}"


def evidence_matches(
    resource: str | None,
    *,
    tool_name: str | None,
    user_id: int | None,
    binding: str | None,
) -> bool | None:
    """Klopt de digest in `resource` met deze waarden?

    Geeft `None` terug als `resource` niet de HITL-vorm heeft -- dan valt er niets na te rekenen
    en is dat geen fout. Dat onderscheid is belangrijk: een verifier die "geen HITL-regel" als
    "manipulatie" leest, meldt elke gewone auditregel als gebroken.

    Oudere HITL-regels van voor 2026-08-09 hebben geen `|ev=`-deel en leveren dus ook `None`.
    Ze zijn niet gedekt, en dat is eerlijker dan doen alsof.
    """
    if not resource:
        return None
    overeenkomst = _RESOURCE_VORM.match(resource)
    if overeenkomst is None:
        return None
    verwacht = evidence_digest(tool_name=tool_name, user_id=user_id, binding=binding)
    return overeenkomst.group("digest") == verwacht
