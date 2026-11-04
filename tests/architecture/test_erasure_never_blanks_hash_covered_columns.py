"""Een wisroute mag geen kolom leegmaken die in een audit-hash meegaat (ADR-036 OP-36).

**De bevinding die dit blokkeert.** OP-36 stelt "blanken bij een wisverzoek" voor als de
goedkope uitweg voor art. 17, met als onderbouwing dat `tool_input` buiten `compute_audit_hash`
valt. Die onderbouwing is verlopen: OP-28 is op 2026-08-26 gesloten door die kolom -- en vier
andere -- juist WEL in de hash op te nemen. Gemeten bewijs staat in
`tests/unit/governance/test_op36_blanking_breaks_the_audit_hash.py`.

Er is vandaag geen enkele wisroute die deze kolommen aanraakt (gemeten: nul treffers over de
vijf modules hieronder). Deze guard houdt dat zo. Zonder hem is de meest waarschijnlijke
volgende stap precies de verkeerde: iemand leest de OP-36-rij, ziet "breekt de hash niet", en
bouwt de blanking alsnog.

**Waarom een GROENE guard en geen rode test.** De CI-testgate is blokkerend. Een opzettelijk
rode test legt elke merge stil voor een bevinding die op een eigen ADR wacht (crypto-shredding,
OP-36 fase 2). Dit is de gedateerde-uitzonderingsvorm uit `.claude/rules/quality-gates.md`:
`KNOWN_BLANKING` is leeg, met een staleness-test die klaagt zodra er een regel in staat die niet
meer gevonden wordt.

**Structuur, geen tekst.** De scan werkt op de AST en kijkt naar de TOEWIJZING (`ast.Assign`,
`ast.AnnAssign`) en naar KEYWORD-argumenten (`ast.keyword`, wat `.values(tool_input=None)` en
`update(tool_input=None)` dekt). Een kolomnaam die alleen in een docstring, comment of string
voorkomt telt dus niet -- dat is exact de valkuil waar eerdere guards in dit project op
sneuvelden.

**Mutatiebewijs, een regel per element van `HASH_COVERED_COLUMNS`** (uitgevoerd 2026-09-01, via
een tijdelijke module in de wis-oppervlakte; gemeten uitkomsten in het eindrapport):
- `tool_input = None`          -> betrapt
- `task_id = None`             -> betrapt
- `error_detail = None`        -> betrapt
- `hitl_ticket_ref = None`     -> betrapt
- `hitl_approved_by = None`    -> betrapt
- `action_params = None`       -> betrapt
- `.values(tool_input=None)`   -> betrapt (keyword-vorm)
De andere richting, allemaal NIET betrapt (anders sloopt de guard legitiem wissen):
- `await db.delete(rij)`                 -> rij-verwijdering is de normale wisvorm
- `observation_data = None`              -> kolom zonder hash-dekking (OP-32)
- `tool_output = None`                   -> alleen `output_hash` zit in de preimage, niet deze
- de string `"tool_input"` in een docstring/comment
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import datetime, timezone
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: De kolommen die in een audit-hash-preimage meegaan. Leegmaken maakt de OPGESLAGEN hash
#: onreproduceerbaar. Reden per regel, want dat is wat een volgende lezer nodig heeft.
HASH_COVERED_COLUMNS: dict[str, str] = {
    # ToolAuditLog -- alle vijf sinds OP-28 (2026-08-26) in `compute_audit_hash`.
    "tool_input": "tool_audit_logs: in compute_audit_hash sinds OP-28",
    "task_id": "tool_audit_logs: in compute_audit_hash sinds OP-28",
    "error_detail": "tool_audit_logs: in compute_audit_hash sinds OP-28",
    "hitl_ticket_ref": "tool_audit_logs: in compute_audit_hash sinds OP-28",
    "hitl_approved_by": "tool_audit_logs: in compute_audit_hash sinds OP-28",
    # CouncilDecisionRow -- in compute_canonical_json EN actief herberekend door ChainVerifier.
    "action_params": "council_decisions: in compute_canonical_json, herberekend door ChainVerifier",
    "reasoning": "council_decisions: in compute_canonical_json, herberekend door ChainVerifier",
    "explanation_for_user": (
        "council_decisions: in compute_canonical_json, herberekend door ChainVerifier"
    ),
}

#: De modules die een wisverzoek of retentie-opruiming uitvoeren.
ERASURE_SURFACE: tuple[str, ...] = (
    "src/core/governance/dsar_service.py",
    "src/core/governance/retention_cleanup.py",
    "src/core/api/v1/gdpr_compliance/erasure_router.py",
    "src/core/database/gdpr_deletion.py",
    "src/core/learning/gdpr_service.py",
)

#: Gedateerde uitzonderingen: "<pad>::<kolom>" -> reden. LEEG op 2026-09-01 (gemeten: geen
#: enkele wisroute raakt vandaag een hash-gedekte kolom). Een regel hier bijzetten vereist een
#: OP-nummer en een expliciet besluit -- zie de staleness-test hieronder.
KNOWN_BLANKING: dict[str, str] = {}


#: Waarden die als "leegmaken" gelden.
def _is_blanking_value(node: ast.AST) -> bool:
    """Is dit een waarde die een kolom leegmaakt?"""
    if isinstance(node, ast.Constant) and node.value in (None, "", 0):
        return True
    if isinstance(node, ast.Dict) and not node.keys:
        return True
    if isinstance(node, ast.List) and not node.elts:
        return True
    return False


def _blanking_hits(bron: str) -> set[str]:
    """Kolomnamen uit `HASH_COVERED_COLUMNS` die in deze module worden leeggemaakt.

    Structureel: alleen toewijzingsdoelen en keyword-argumenten tellen. Een naam in een
    docstring, comment of losse string is GEEN treffer.
    """
    boom = ast.parse(bron)
    gevonden: set[str] = set()

    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.Assign) and _is_blanking_value(knoop.value):
            for doel in knoop.targets:
                naam = doel.attr if isinstance(doel, ast.Attribute) else None
                if naam is None and isinstance(doel, ast.Name):
                    naam = doel.id
                if naam in HASH_COVERED_COLUMNS:
                    gevonden.add(naam)
        elif (
            isinstance(knoop, ast.AnnAssign)
            and knoop.value is not None
            and _is_blanking_value(knoop.value)
        ):
            doel = knoop.target
            naam = doel.attr if isinstance(doel, ast.Attribute) else None
            if naam is None and isinstance(doel, ast.Name):
                naam = doel.id
            if naam in HASH_COVERED_COLUMNS:
                gevonden.add(naam)
        elif isinstance(knoop, ast.keyword):
            if knoop.arg in HASH_COVERED_COLUMNS and _is_blanking_value(knoop.value):
                gevonden.add(knoop.arg)

    return gevonden


def _scan_erasure_surface() -> dict[str, str]:
    """ "<pad>::<kolom>" -> pad, voor elke wisroute die een hash-gedekte kolom leegmaakt."""
    treffers: dict[str, str] = {}
    for relatief in ERASURE_SURFACE:
        pad = REPO_ROOT / relatief
        if not pad.exists():
            continue
        for kolom in _blanking_hits(pad.read_text(encoding="utf-8")):
            treffers[f"{relatief}::{kolom}"] = relatief
    return treffers


class TestErasureNeverBlanksHashCoveredColumns:
    def test_no_erasure_route_blanks_a_hash_covered_column(self) -> None:
        """DE GUARD. Blanken vernietigt de bewijswaarde van de rij zonder dat iets het meldt."""
        nieuw = set(_scan_erasure_surface()) - set(KNOWN_BLANKING)

        assert not nieuw, (
            "Een wisroute maakt een kolom leeg die in een audit-hash meegaat: "
            f"{sorted(nieuw)}. De opgeslagen hash wordt daarmee onreproduceerbaar. ADR-036 "
            "OP-36 noemt blanken veilig op grond van OP-28, maar OP-28 is juist gesloten door "
            "deze kolommen IN de hash te brengen. Zie "
            "tests/unit/governance/test_op36_blanking_breaks_the_audit_hash.py voor de meting. "
            "Wissen vraagt hier crypto-shredding (OP-36 fase 2, eigen ADR), niet blanken."
        )

    def test_known_blanking_is_not_stale(self) -> None:
        """Een uitzondering die is opgelost MOET uit de lijst -- anders rot hij dicht."""
        aanwezig = set(_scan_erasure_surface())
        verlopen = [regel for regel in KNOWN_BLANKING if regel not in aanwezig]

        assert not verlopen, (
            f"Deze uitzonderingen staan er nog maar worden niet meer gevonden: {verlopen}. "
            "Haal ze uit KNOWN_BLANKING."
        )

    def test_every_named_column_really_enters_the_tool_audit_hash(self) -> None:
        """Anti-drift, een regel per element: de verzameling mag niet los komen te staan.

        Zou `compute_audit_hash` ooit een kolom weer uit de preimage halen, dan bewaakt deze
        guard een kolom die er niet meer in zit -- en, erger, dekt hij een kolom die er WEL bij
        komt niet. Deze toets meet zwart-doos per kolom of de hash er daadwerkelijk op reageert.
        """
        from src.core.tool_broker.audit_utils import compute_audit_hash

        parameters = set(inspect.signature(compute_audit_hash).parameters)
        basis: dict[str, Any] = {
            "tenant_id": 1,
            "agent_id": "agent",
            "tool_name": "tool",
            "timestamp": datetime(2026, 8, 1, tzinfo=timezone.utc),
            "status": "success",
            "output_hash": "oh",
            "previous_hash": None,
            "tool_input": {"k": "v"},
            "task_id": "task",
            "error_detail": "err",
            "hitl_ticket_ref": "ticket",
            "hitl_approved_by": "user:1",
        }
        referentie = compute_audit_hash(**basis)

        for kolom in HASH_COVERED_COLUMNS:
            if kolom not in parameters:
                continue  # raadskolom, gedekt door de volgende test
            gewijzigd = dict(basis)
            gewijzigd[kolom] = None
            assert compute_audit_hash(**gewijzigd) != referentie, (
                f"`{kolom}` staat in HASH_COVERED_COLUMNS maar `compute_audit_hash` reageert "
                "er niet op. Of de kolom hoort niet in deze verzameling, of de OP-28-fix is "
                "teruggedraaid."
            )

    def test_every_named_council_column_is_in_the_recomputed_canonical_json(self) -> None:
        """Dezelfde anti-drift voor de raadsketen, die WEL een hercompute-verifier heeft."""
        from src.core.copilot.audit.chain_verifier import ChainVerifier

        bron = inspect.getsource(ChainVerifier._compute_canonical_json)
        sleutels = {
            knoop.value
            for knoop in ast.walk(ast.parse(bron.lstrip()))
            if isinstance(knoop, ast.Constant) and isinstance(knoop.value, str)
        }

        raadskolommen = {
            kolom
            for kolom, reden in HASH_COVERED_COLUMNS.items()
            if reden.startswith("council_decisions")
        }
        ontbreekt = raadskolommen - sleutels

        assert not ontbreekt, (
            f"Deze kolommen worden bewaakt als raadskolom maar staan niet in de canonieke JSON "
            f"die ChainVerifier herberekent: {sorted(ontbreekt)}."
        )
