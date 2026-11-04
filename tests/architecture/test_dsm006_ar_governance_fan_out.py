"""Architecture test: agent_runtime -> governance runtime coupling MUST be <= 9.

SP-DSM-006: Decoupling agent_runtime from governance via event-bus pattern.
Target: 26 -> <= 5 runtime imports (TYPE_CHECKING blocks excluded by scan_module).
Raised to <= 7 in SP-DSM-013: scheduler.py (cleanup_council_decisions) reclassified
as agent_runtime. workflow_worker.py is NOT in SOURCE_DIRS["agent_runtime"] (ghost worker).

Verhoogd naar <= 8 in SP-COUNCIL-GATE-001 (2026-08-16). Reden: `_PranaAdapter` in
`copilot/council/factory.py` moet het ECHTE tenantbudget raadplegen via
`governance.prana_guard`. Daarvoor keek hij in een leeg woordenboek dat op `agent_id` was
gesleuteld, waardoor de ResourceOfficer ELK voorstel uitstelde -- op het agent-pad en op
het copilot-pad. De richting copilot->governance is expliciet by design (ADR-027, en
import-linter Contract 5 verbiedt alleen de omgekeerde richting).

**Het plafond is nu het GEMETEN aantal, zonder buffer.** De vorige tekst rekende 6 voor
en gaf 1 buffer, maar er waren er feitelijk 7: `copilot/api/audit_endpoints.py` stond niet
in de opsomming en at de buffer stilletjes op. Een buffer die niemand bijhoudt is geen
ruimte voor de toekomst maar een blinde vlek. Volledige, gemeten opsomming (2026-08-16,
via `scan_module`):

  1. copilot/council/models.py:9  -> governance.models   (ADR-027 bridge, re-export)
  2. copilot/council/models.py:10 -> governance.models   (ADR-027 bridge, re-export)
  3. copilot/council/types.py:28  -> governance.models   (ADR-027 bridge, re-export)
  4. copilot/council/types.py:29  -> governance.models   (ADR-027 bridge, re-export)
  5. copilot/api/turn_endpoint.py:36 -> governance.rate_limiter   (SP-SEC-RL-001)
  6. workers/scheduler.py:364        -> governance.retention_cleanup (SP-DSM-013)
  7. copilot/api/audit_endpoints.py:29 -> governance.audit  (niet eerder verantwoord)
  8. copilot/council/factory.py:265    -> governance.prana_guard (SP-COUNCIL-GATE-001)
  +. copilot/service.py::handle_turn   -> governance.input_guard (2026-09-22)
  +. als/agents/specialist_base.py::_reject_before_council -> governance.input_guard (idem)

LET OP bij die nummering, en dit is een CORRECTIE op wat er eerst stond. Ik schreef dat
`scan_module` er negen meet terwijl de opsomming acht regels had, en dat ik niet had
vastgesteld welke rand ontbrak. Verkeerde richting: de lijst telt te VEEL, niet te weinig.
Gemeten 2026-09-22: `scan_module` zag er VOOR de InputGuard zeven, en regel 8 hierboven
(`copilot/council/factory.py -> governance.prana_guard`) is inmiddels een
`importlib.import_module`-aanroep en daarmee onzichtbaar voor de scanner. De opsomming en
de meting liepen dus al uiteen, maar andersom dan ik opschreef.

Overwogen en NIET gedaan: de InputGuard ook via `importlib.import_module` importeren. Dat
patroon staat op DRIE plekken in deze codebase (`copilot/council/factory.py`,
`copilot/service.py` bij prana, en `specialist_base._get_prana_guard`), elke keer met een
comment dat naar DEZE test verwijst -- het is dus een bekende en gebruikte uitweg, en hij
had dit plafond op 8 gehouden. Ik gebruik hem niet: een echte afhankelijkheid voor de meter
verstoppen is erger dan de +2 betalen, want dan groeit de koppeling terwijl het getal
stilstaat. Maar het hoort genoemd te worden, anders concludeert de volgende lezer dat ik
die uitweg niet kende. En het is een eerlijke waarschuwing bij dit plafond: de werkelijke
governance-afhankelijkheid is hoger dan negen, want drie randen zijn per ontwerp
onzichtbaar.

De laatste twee zijn de twee deuren waar VRIJE TEKST het systeem binnenkomt, en ze horen
bij elkaar. De reden dat deze koppeling niet te vermijden is: de Council beoordeelt de
VORM van een actie en krijgt per ontwerp alleen de toolnaam en de argumentNAMEN
(BE-AGT-043, ADR-036 OP-25), omdat alles wat hij ziet de onuitwisbare ADR-019-keten in
gaat -- vrije tekst daarin botst met AVG art. 16/17. Een BSN in een opdracht reisde
daardoor ongehinderd langs de hele governance-laag, en op het chatpad stond helemaal
geen inhoudscontrole (gemeten 2026-09-21: nul treffers op `detect_pii` in
`copilot/service.py`).

Overwogen en NIET gedaan: de wachter in de `shared`-bak zetten, die niet meetelt in de
fan-out. Dan was dit getal op 8 gebleven -- en precies daarom is het verkeerd. Een
wachter die AVG-categorieen toetst is een governance-zorg en hoort naast
`gdpr_enforcer.py`, wiens detector hij hergebruikt. Hem elders parkeren om de meter te
ontwijken is de optimalisatie waar `scan_module` zelf voor waarschuwt.

Elke NIEUWE koppeling valt hier nu direct op, want er is geen ruimte meer om in te
verdwijnen. Wie er een toevoegt hoort de regel hierboven uit te breiden met de reden.
Uses the same scan_module function as scripts/dsm_full_analysis.py to stay in sync
with the official DSM measurement.
"""

import pytest

from scripts.dsm_full_analysis import SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_agent_runtime_governance_coupling_below_5() -> None:
    """agent_runtime -> governance MUST be <= 8 runtime imports (SP-DSM-006, ADR-034).

    TODO(SP-DSM-006): Reduce to <= 5 via event-bus decoupling + shared-layer moves.
    Currently 26 (target <= 5). Fix: see docs/SPRINT_TRACKER.md#SP-DSM-006.
    """
    counts, _, _ = scan_module("agent_runtime", SOURCE_DIRS.get("agent_runtime", []))
    gov_count = counts.get("governance", 0)
    assert gov_count <= 9, (
        f"agent_runtime->governance: {gov_count} coupling imports (target <=9). "
        f"Run: python scripts/dsm_full_analysis.py for details. "
        f"Plafond 9 = het gemeten aantal na de InputGuard (2026-09-22), zonder buffer. De volledige "
        f"opsomming met reden per import staat in de docstring van dit bestand; een "
        f"nieuwe koppeling hoort daar te worden verantwoord of te verdwijnen."
    )
