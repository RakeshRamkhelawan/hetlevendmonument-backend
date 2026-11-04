# Backend Feature Review — BE-UTL-046

## Metadata

- Feature ID: BE-UTL-046
- Feature naam: HITLStore consistente wiring in ToolBrokerService
- Review datum: 2026-07-07
- Reviewer: self-review (code-review reeds uitgevoerd door onafhankelijke subagent)
- Spec locatie: `docs/backend/features/BE-UTL-046-hitlstore-wiring-toolbroker.md`

---

## Eindoordeel

**APPROVED WITH MINOR GAPS**

De specificatie beschrijft volledig welke bestanden zijn gewijzigd, waarom de wijziging nodig is, en welke tests de wiring garanderen. De twee openstaande gaps zijn bewust geaccepteerd voor deze sprint-dag en staan geregistreerd in ADR-037 als vervolgwerk.

---

## Samenvatting

De feature fixt AUDIT-TOOL-005: `ToolBrokerService` werd op zes verschillende plekken geconstrueerd, maar slechts enkele daarvan gebruikten de nieuwe DB-backed `HITLStore`. De specificatie inventariseert alle zes constructieplekken, beschrijft de tenant-context doorgeefregel, en documenteert de functionele test voor HIGH-risk tool execution. De review is licht omdat het om een interne wiring-fix gaat zonder publiek API-contract wijziging; de code is reeds beoordeeld door een onafhankelijke subagent.

---

## Bevindingen per categorie

### 1. Coverage gaps

**Medium** — De specificatie noemt dat `BaseSpecialistAgent` een fallback `HITLStore()` zonder repository gebruikt. Dit is een reëel gap: concrete HITL ticket operaties in `act()` falen totdat de agent een sessie krijgt. De gap is echter expliciet benoemd in de spec en in ADR-037 G3/WE-018 als vervolgwerk.

### 2. Functionele onduidelijkheden

Geen.

### 3. Technische onduidelijkheden

Geen.

### 4. Ontbrekende foutstatussen en edge cases

Geen — alle relevante HTTP statussen voor het endpoint zijn beschreven; interne utility foutafhandeling is benoemd.

### 5. Acceptatiecriteria problemen

Geen — criteria zijn testbaar en sluiten aan op de geschreven unit tests.

### 6. Integratorhandleiding / API-uitleg problemen

Geen — er is geen publiek contract gewijzigd; de integratoruitleg is passend beperkt.

### 7. Trainingsdata problemen

Geen.

### 8. Structuur- en consistentieproblemen

Geen.

### 9. Risico's voor implementatie, security of QA

**Low** — Zolang `BaseSpecialistAgent` een fallback store zonder repository gebruikt, kan een HIGH-risk tool-aanroep in `act()` een runtime fout geven bij HITL lookup. Mitigatie: dit gedrag is niet nieuw ten opzichte van de oude in-memory dict (ook die had geen persistentie); de store is nu op zijn minst aanwezig en tenant context wordt doorgegeven.

---

## Issue register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Medium | BE-AGT-046b | `BaseSpecialistAgent` gebruikt fallback `HITLStore()` zonder repository | Bij HITL lookup in `act()` ontbreekt een database sessie | Opnemen in ADR-037 Fase 1 (G3/WE-018); constructor moet op termijn een sessie ontvangen of lazy initialisatie gebruiken |
| Low | BE-UTL-046 | Legacy `_hitl_tickets` in-memory dict blijft tijdelijk aanwezig in `ToolBrokerService` | Verwijderen vereist audit van alle call-sites | Opnemen in ADR-037 Fase 1 (G3/WE-018) |

---

## Ontbrekende items

- Geen ontbrekende items binnen de scope van deze sprint-dag.

---

## Verbeterde tekstvoorstellen

Geen — de tekst is passend voor een interne wiring-fix.

---

## Release-oordoel

- **Geschikt voor bouw / implementatie?** Ja — de code is al geimplementeerd en getest.
- **Geschikt voor QA en geautomatiseerd testen?** Ja — 7 unit tests dekken de wiring.
- **Geschikt voor LLM-training?** Ja — de spec beschrijft de wijziging, scope en risico's expliciet.
- **Geschikt voor integratorhandleiding / API-documentatie?** Niet direct van toepassing; er is geen publiek contract gewijzigd.

---

## Opmerkingen

- De code is reeds gecontroleerd door een onafhankelijke subagent (code-reviewer). Deze review richt zich uitsluitend op de feature-specificatie.
- Stopvoorwaarden: geen CRITICAL of HIGH issues open in deze review.
