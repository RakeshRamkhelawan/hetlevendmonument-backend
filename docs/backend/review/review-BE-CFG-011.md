# Review BE-CFG-011 -- Domain Registry Split Dag 3: analytics + realtime + tenants

**Reviewer:** AI agent (Laag C)
**Datum:** 2026-06-02
**Sprint:** SP-API-001 Dag 3

---

## EINDOORDEEL: APPROVED

---

## SAMENVATTING

Drie nieuwe Laag 2 domeinregistries conform ADR-033 (max 80 regels: 57/46/70). Logica is 1:1
overgenomen van de originele `_register_*`-functies — geen gedragswijziging. De vijf
AST-equivalentietests in `test_registry_equivalence.py` bewijzen automatisch dat elke registry
dezelfde router-modules bevat als de bron. `tenants._stub_crud_enabled()` past correct de
productie-guard toe (ENABLE_P5_STUB_CRUD_ROUTERS altijd False in production). Alle 5
equivalentietests GROEN, 94/94 unit tests GROEN, 2 verwachte fitness-failures (legacy code).

---

## BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

Geen. Alle vijf registry bestanden worden gedekt door een equivalentietest.

### 2. Functionele onduidelijkheden

Geen. `_stub_crud_enabled()` is duidelijk gedocumenteerd en de productie-guard is expliciet.

### 3. Architectuurconformiteit

Volledig conform ADR-033:
- Alle bestanden onder 80 regels
- Alleen lazy imports in `register()` functie
- `router_registry.py` delegeert via lazy `from src.core.api.registries import X; X.register(app)`
- Dode `_register_*` functies bewust bewaard (Strangler Fig protocol)

### 4. Testdekking

De AST-gebaseerde equivalentietests zijn een waardevolle toevoeging boven het patroon van Dag 2:
ze maken toekomstige registry-modificaties veilig door automatisch te detecteren als een
router-module verdwijnt uit de registry maar nog in de originele functie staat.

### 5. Volgorde-verifiëring

De equivalentietests verifiëren **aanwezigheid** van modules, niet hun **volgorde**. Als routervolgorde
van belang is voor middleware-toepassing, overweeg een aanvullende volgorde-test (aanbeveling, niet blokkend).

---

## AANBEVELING

Voeg bij Dag 4 een aanvullende volgorde-test toe aan `test_registry_equivalence.py` die de
`include_router`-aanroepreeks vergelijkt (niet alleen de aanwezige modules).
