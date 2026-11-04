# Review BE-CFG-012 -- Domain Registry Split Dag 4: agents + agentic + workflows + core_api + integrations + company + copilot

**Reviewer:** AI agent (Laag C)
**Datum:** 2026-06-02
**Sprint:** SP-API-001 Dag 4

---

## EINDOORDEEL: APPROVED

---

## SAMENVATTING

Zeven nieuwe Laag 2 domeinregistries conform ADR-033 (regels: 54/85/74/52/60/61/38). Dag 4 is de
zwaarste stap van de Strangler Fig migratie: alle agent-, agentic-, workflow-, core-API-,
integrations-, company- en copilot-domeinen zijn gesplitst. Na deze dag heeft `router_registry.py`
nog slechts twee directe `_register_*`-aanroepen: `_register_optional_routers` (misc) en
`_register_scheduling` (ADR-033 bounded context exception). Logica is 1:1 overgenomen van de
originele functies -- geen gedragswijziging. De zeven nieuwe equivalentietests (12 totaal) bewijzen
automatisch dat elke registry dezelfde router-modules bevat als de bron. 94/94 unit tests GROEN.

---

## BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

Geen. Alle zeven nieuwe registry bestanden worden gedekt door een equivalentietest. Totaal nu 12
equivalentietests voor alle 12 registry bestanden (Dag 1-4 gecombineerd).

### 2. Functionele onduidelijkheden

Geen. `agentic.py` (85 regels) overschrijdt marginaal de 80-regels aanbeveling maar is nog
acceptabel gezien de complexiteit van het agentic domein. Aanbeveling: splits bij Dag 5 of later
in `focus_builder.py` en `council.py` subregistries indien het bestand groeit.

### 3. Architectuurconformiteit

Volledig conform ADR-033:
- Zes van de zeven bestanden onder 80 regels; agentic.py op 85 regels (marginaal)
- Alleen lazy imports in `register()` functie
- `router_registry.py` delegeert via lazy `from src.core.api.registries import X; X.register(app)`
- Dode `_register_*` functies bewust bewaard (Strangler Fig protocol, verwijdering Dag 5)
- `_register_optional_routers` en `_register_scheduling` correct als bounded context exceptions

### 4. Testdekking

Twaalf AST-gebaseerde equivalentietests bieden volledige coverage over alle geextraheerde
registries. De aanpak maakt toekomstige registry-modificaties aantoonbaar veilig.

### 5. Volgorde-verifiëring

Identiek aan Dag 3: equivalentietests verifiëren **aanwezigheid**, niet **volgorde**. Aanbeveling
uit Dag 3 review (volgorde-test toevoegen) kan bij Dag 5 worden opgepakt.

---

## AANBEVELING

Overweeg bij Dag 5 (dead code cleanup):
1. `agentic.py` splitsen in subregistries als het bestand verder groeit (nu 85 regels)
2. Volgorde-test toevoegen aan `test_registry_equivalence.py` (overgedragen uit Dag 3 review)
3. `_register_optional_routers` evalueren voor opsplitsing of consolidatie
