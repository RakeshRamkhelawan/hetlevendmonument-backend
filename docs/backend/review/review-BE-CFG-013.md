# Review BE-CFG-013 -- router_registry.py Dead Code Removal -- Strangler Fig Voltooiing

**Reviewer:** AI agent (Laag C)
**Datum:** 2026-06-02
**Sprint:** SP-API-001 Dag 5

---

## EINDOORDEEL: APPROVED

---

## SAMENVATTING

Finale Strangler Fig stap conform ADR-033: 23 dode `_register_*` functies en 2 helpers
verwijderd uit `router_registry.py`. Het bestand krimpt van ~1100 naar ~320 regels en is nu een
zuivere dunne orkestrator die uitsluitend delegeert naar Laag 2 domeinregistries.
`_register_optional_routers` en `_register_scheduling` zijn bewust behouden als actieve
functies. De 12 AST-equivalentietests in `tests/architecture/` bevestigen dat geen router
verloren is gegaan. 94/94 unit tests GROEN.

---

## BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

Geen. Alle 12 equivalentietests dekken elk domein dat via een Laag 2 registry wordt beheerd.

### 2. Functionele onduidelijkheden

Geen. De beslissing om `_register_optional_routers` en `_register_scheduling` te bewaren is
gedocumenteerd in de spec en de code. Toekomstige developers weten welke functies nog actief zijn.

### 3. Architectuurconformiteit

Volledig conform ADR-033:
- `router_registry.py` is nu een dunne orkestrator (~320 regels, ruim onder het maximum)
- Geen nieuwe `_register_*` functies geintroduceerd
- Alle domeinlogica in Laag 2 registries geisoleerd
- Lazy imports behouden in `register_all_routers()`

### 4. Testdekking

De 12 AST-equivalentietests vormen een adequate veiligheidsnet voor dit type
dead-code-verwijdering. Alle 12 tests bleven GROEN na de verwijdering, wat bewijst dat de Laag
2 registries een volledige superset bevatten van de verwijderde originele functies.

### 5. Risico-assessment

Laag risico. De Strangler Fig aanpak (Dag 1-4 first, delete last) garandeert dat de registries
correct zijn voordat de originele functies worden verwijderd. De equivalentietests zijn de
formele bewijsvoering. De volledige unit suite (94/94) geeft aanvullende regressiezekerheid.

---

## AANBEVELING

Geen blocking bevindingen. SP-API-001 is hiermee volledig afgesloten. Bij toekomstige
uitbreidingen: altijd eerst een Laag 2 registry aanmaken en equivalentietest schrijven voordat
een `_register_*` functie wordt verwijderd -- dit protocol is nu bewezen effectief.
