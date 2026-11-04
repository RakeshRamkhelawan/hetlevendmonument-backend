# Review: BE-MDL-011 -- Task ORM-model

**Reviewer:** code-review agent (AGENTIC-COPILOT-TAAKBEHEER Dag 2)
**Status:** APPROVED WITH MINOR GAPS
**Datum:** 2026-07-07

---

## A. EINDOORDEEL

APPROVED WITH MINOR GAPS

---

## B. SAMENVATTING

Het Task ORM-model in `src/domains/tasks/models.py` is correct geimplementeerd als tenant-geisoleerde entiteit met de velden, indexes en defaults zoals beschreven in de gedeelde specificatie `BE-SVC-071-agentic-task-layer.md`. De bijbehorende Alembic-migratie bevat de CHECK-constraints en RLS policy. De trainingssamenvatting is tijdens deze review toegevoegd. Overgebleven minors zijn documentatie van constraints op modelniveau versus migratieniveau en de cross-tenant parent_task_id risicoafweging.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- Geen. Model, migratie, repository, service, schemas en tests zijn geinventariseerd.

### 2. Functionele onduidelijkheden

- Geen. Het doel van een generieke, tenant-geisoleerde taak is helder.

### 3. Technische onduidelijkheden

- De spec vermeldt CHECK-constraints onder het model, maar deze zitten in de migratie. Dit is een documentatie-inconsistentie, geen implementatiefout.

### 4. Ontbrekende foutstatussen en edge cases

- De cross-tenant parent_task_id risico is benoemd in de spec; het blijft een bewuste beperking tot de applicatielaag.

### 5. Acceptatiecriteria problemen

- Alle acceptatiecriteria zijn testbaar en groen volgens de spec.

### 6. Integratorhandleiding / API-uitleg problemen

- Geen. Het codevoorbeeld is concreet.

### 7. Trainingsdata problemen

- Opgelost: trainingssamenvatting is toegevoegd.

### 8. Structuur- en consistentieproblemen

- Minor: CHECK-constraints staan in de migratie, niet in het ORM-model; spec kan dit explicieter onderscheiden.

### 9. Risico's voor implementatie, security of QA

- Medium: RLS is niet FORCE; table owner bypassed RLS. Geaccepteerd en gedocumenteerd.
- Low: parent_task_id FK is niet tenant-gescoped. Geaccepteerd en gedocumenteerd.

---

## D. ISSUE REGISTER

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | C.1 velden / constraints | CHECK-constraints in modelbeschrijving, maar pas aanwezig in migratie | Lezer kan denken dat het model ze zelf afdwingt | Spec expliciet maken: "CHECK-constraints worden in migratie BE-MIG-012 afgedwongen" |
| Low | Trainingssamenvatting | Ontbrak in oorspronkelijke spec | Vereist voor validatiescript | Toegevoegd in deze review |

---

## E. ONTBREKENDE ITEMS

- Geen. Endpoints, ToolBroker, HITL en audit zijn bewust out of scope voor dag 2.

---

## F. VERBETERDE TEKSTVOORSTELLEN

- Niet van toepassing (alleen minors).

---

## G. RELEASE-OORDEEL

- Is dit document geschikt voor bouw / implementatie? Ja
- Is dit document geschikt voor QA en geautomatiseerd testen? Ja
- Is dit document geschikt voor LLM-training? Ja (na toevoeging trainingssamenvatting)
- Is dit document geschikt voor integratorhandleiding / API-documentatie? Ja
