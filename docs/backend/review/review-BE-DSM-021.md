# Review BE-DSM-021 -- SP-DSM-008 Dag 2 MODULE_MAP Reclassificatie

**Status**: APPROVED WITH MINOR GAPS
**Datum**: 2026-06-18
**Reviewer**: code-reviewer + quality-reviewer (Gate 2)

---

## Samenvatting

De reclassificaties zijn architectureel correct. ADR-beslissing voor database.database is
onderbouwd. test_fan_out_budget fix is consistent met Ce-conventie. Grade A+ target bereikt.

---

## Bevindingen

### OK: classify() correctheid voor database.database

classify("src.core.database.database") = "shared" via longest-prefix matching.
classify("src.core.database.redis") = "infra" (niet overruled).
MODULE_MAP entry staat VOOR de generieke "src.core.database": "infra" -- correct.

**Status: GO**

### OK: ADR-beslissing database.database

database.py regels 283 en 473: function-local lazy imports voor RLS session context.
Dit is ADR-004/005 ORM tenant filtering -- foundational multi-tenant infrastructure.
SOURCE_DIRS["shared"] NIET aangepast -- test_shared_fan_out_is_zero blijft onaangetast.
Zelfde patroon als Dag 1 reclassificaties (src.core.config etc.).

**Status: GO**

### OK: resilience reclassificatie

circuit_breaker.py + retry_policy.py: zero business-imports (geen tenancy/governance/agents).
Pure infrastructuur-patroon. Reclassificatie naar shared is architectureel correct.

**Status: GO**

### OK: test_fan_out_budget fix

De fix (shared uitsluiten van budget-totaal) is consistent met de Ce-conventie die ook shared
uitsluit. Infra's niet-shared koppeling is 51 (< 80 budget). De fix maakt de test
architectureel correcter: het budget bewaakt koppeling aan business-lagen, niet aan foundation.

**Status: GO**

### OK: Dag 2 Ce-ceiling test

test_agent_runtime_ce_dag2_final_target: docstring correct (WHY niet WHAT),
assert-bericht specifiek genoeg, @pytest.mark.architecture aanwezig, ASCII-only.
Test was ROOD bij Ce=285, GROEN bij Ce=222.

**Status: GO**

### MINOR: test_agent_runtime_instability_grade_a_plus xfail marker

De test heeft strict=False. Nu de target bereikt is (XPASS), kan de xfail marker worden
verwijderd. Voordeel: xpass telt niet als failure maar is misleidend in de suite-samenvatting.
Dit is een kleine opruimtaak voor de sprint-afsluiting of een volgende sprint.

**Impact**: Geen blocker. XPASS met strict=False breekt CI niet.

**Status: MINOR**

### OK: CLAUDE.md compliance

- [x] Geen emoji of non-ASCII in code, comments, logs
- [x] Geen datetime.now() of datetime.utcnow()
- [x] Geen tenant_id uit request body
- [x] Comments beschrijven WHY, niet WHAT
- [x] pyright: 0 nieuwe errors t.o.v. onze wijzigingen (pre-existing browser.py issue buiten scope)
- [x] ruff: all checks passed

---

## Eindoordeel

**APPROVED WITH MINOR GAPS**

Go voor commit. Grade A+ target bereikt (Ce=222, I=0.499). Minor gap (xfail marker opruimen)
is geen blocker. SP-DSM-008 kan als CLOSED worden gemarkeerd na FA GO.
