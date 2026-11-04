# Review: BE-UTL-048 Workflow Tasks Tenant Context Cleanup Fix

**Feature:** `docs/backend/features/BE-UTL-048-workflow-tasks-tenant-cleanup.md`
**Reviewer:** independent backend documentation reviewer
**Datum:** 2026-07-29

---

## Eindoordeel

**APPROVED WITH MINOR GAPS**

De specificatie is technisch correct, goed gestructureerd en de implementatie komt overeen met de beschrijving. Alle oorspronkelijke documentaire bevindingen (ID-REGISTRY, unieke flow-ID, type-checker vermelding) zijn gecorrigeerd. Tijdens de onafhankelijke final review zijn twee additionele pre-existing tenant-cleanup inconsistenties in andere Dramatiq-actors gevonden (FA-001 en FA-002); deze zijn inmiddels opgelost en voorzien van regressietests. Een resterende LOW bevinding over het test-ID suffix in de inventory is administratief en heeft geen impact op implementatie of tests.

---

## Samenvatting

De spec beschrijft een gerichte utility-fix in `src/core/tasks/workflow_tasks.py`: de `AutonomousAgent`-instantiering staat nu binnen het `try`-blok, waardoor `set_tenant_id(None)` in `finally` altijd wordt bereikt, ook bij een constructiefout. De bijbehorende regressietest is concreet en matcht de code. De rest van de documentatie voldoet bijna volledig aan het template, maar de ID-administratie is onvolledig.

---

## Bevindingen per categorie

### 1. Coverage gaps

- ID `BE-UTL-048` is **niet opgenomen** in `docs/backend/features/ID-REGISTRY.md`. De template voorschrijft: "Voeg elk nieuw ID direct toe na het aanmaken van de bijbehorende spec." Zonder registratie is `BE-UTL-048` geen formeel erkend artefact en kan een toekomstige auteur per ongeluk hetzelfde nummer toewijzen.
- De `Backend inventory` bevat `BE-UTL-048-TEST` voor de unit test. Het ID-conventie-document kent geen aparte test-ID-prefix; dit is acceptabel als inventaris-item, maar dient consistent te zijn met de registry.

### 2. Functionele onduidelijkheden

- Geen. Het doel (voorkomen van tenant-context-lekkage tussen hergebruikte Dramatiq worker-threads) is helder.

### 3. Technische onduidelijkheden

- Geen. De verplaatsing van `agent = AutonomousAgent()` en het `finally`-pad zijn precies beschreven.

### 4. Ontbrekende foutstatussen en edge cases

- De flow beschrijft correct dat ongeldige/missende `tenant_id` faalt vóór het zetten van de ContextVar, waardoor cleanup dan niet van toepassing is. De constructiefout-edge case is goed gedekt.

### 5. Acceptatiecriteria problemen

- De criteria zijn testbaar. Let op: criterium 5 verwijst naar `pyright`, maar de AGENTS.md/ADR-project gebruikt `mypy` als type-checker. Controleer of `pyright` hier het juiste tool-argument is, of vervang door `mypy src/core/tasks/workflow_tasks.py`.

### 6. Integratorhandleiding / API-uitleg problemen

- Geen. De integratoruitleg is kort en accuraat: geen externe impact, interne robuustheidsverbetering.

### 7. Trainingsdata problemen

- Geen. De trainingssamenvatting bevat alle verplichte velden (Actor, Voorwaarde, Actie, Systeemverwerking, Succesrespons, Foutrespons, Uitzonderingen).

### 8. Structuur- en consistentieproblemen

- De flow-ID `BE-FLW-001` is hergebruikt. Er bestaat al een aparte feature `BE-FLW-001-copilot-turn-e2e.md` en een review `review-BE-FLW-001.md`. Binnen de ID-conventie moet elke flow een uniek ID hebben. Voorstel: wijzig de lokale flow-ID naar `BE-FLW-048` (of een ander nog niet gebruikt nummer).

### 9. Risico's voor implementatie, security of QA

- Geen substantiële risico's. De tenant-isolatiebeschrijving is correct (`tenant_id` uit payload, geen request-body, ContextVar cleanup). De open risico's in de spec zijn proportioneel.

---

## Issue register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie | Status |
| --- | --- | --- | --- | --- | --- |
| HIGH | Metadata / Backend inventory | `BE-UTL-048` staat niet in `docs/backend/features/ID-REGISTRY.md`. | ID-REGISTRY is de formele bron voor unieke ID's; zonder registratie kan een volgende auteur hetzelfde nummer hergebruiken. | Voeg toe aan `ID-REGISTRY.md`: `BE-UTL-048 \| Workflow Tasks Tenant Context Cleanup Fix \| docs/backend/features/BE-UTL-048-workflow-tasks-tenant-cleanup.md \| ADR-036 Fase A Dag 1 \| 2026-07-28`. | **Gefixt** |
| HIGH | API-flows | Flow-ID `BE-FLW-001` is niet uniek. | Er bestaat al een andere feature/review met ID `BE-FLW-001`; de ID-conventie eist unieke artefact-ID's. | Wijzig `Flow ID: BE-FLW-001` naar `Flow ID: BE-FLW-048` en pas gerelateerde verwijzingen in de spec aan. | **Gefixt** |
| MEDIUM | Acceptatiecriteria 5 | Verwijzing naar `pyright`. | Project gebruikt `mypy` als type-checker; verwijzing naar een andere tool kan verwarring veroorzaken. | Vervang "pyright" door "mypy" in acceptatiecriterium 5. | **Gefixt** |
| MINOR | Security / Architecture (FA-001) | `src/core/tasks/cva_tasks.py` zet tenant ContextVar maar ruimt niet op. | Inconsistent met gecorrigeerde `workflow_tasks.py`; potentieel tenant-context-lekkage in hergebruikte Dramatiq worker-threads. | Wrap werk na `set_tenant_id` in `try/finally` en roep `set_tenant_id(None)` aan. Voeg regressietest toe. | **Gefixt** |
| MINOR | Security / Architecture (FA-002) | `src/core/copilot/audit/report_jobs.py` zet tenant ContextVar maar ruimt niet op. | Zelfde audit-problematiek als FA-001; potentieel tenant-context-lekkage. | Wrap werk na `set_tenant_id` in `try/finally` en roep `set_tenant_id(None)` aan. Voeg regressietest toe. | **Gefixt** |
| LOW | Backend inventory | Test-ID `BE-UTL-048-TEST` voldoet niet strikt aan de ID-conventie. | Template/ID-conventie kent geen suffix-ID's voor tests. | Acceptabel als inventaris-item, maar niet als formeel backend-artefact-ID geregistreerd. | **Open — minor gap, geen impact op implementatie** |

---

## Ontbrekende items

- Geen ontbrekende endpoints, services, modellen of flows.

---

## Verbeterde tekstvoorstellen

Geen tekstuele herschrijvingen nodig; enkel bovenstaande correcties.

---

## Release-oordeel

| Criterium | Geschikt? |
| --- | --- |
| Geschikt voor bouw / implementatie | Ja, nadat ID- en flow-uniciteit zijn gecorrigeerd. |
| Geschikt voor QA en geautomatiseerd testen | Ja. |
| Geschikt voor LLM-training | Ja, mits de spec uiteindelijk in de registry staat. |
| Geschikt voor integratorhandleiding / API-documentatie | Ja, geen externe API-wijzigingen. |

---

## Voorwaarde voor GO

1. Registreer `BE-UTL-048` in `docs/backend/features/ID-REGISTRY.md`.
2. Wijzig de flow-ID van `BE-FLW-001` naar een unieke ID (`BE-FLW-048` wordt voorgesteld).
3. (Aanbevolen) Controleer of acceptatiecriterium 5 `pyright` of `mypy` moet noemen.

Na deze correcties kan de spec worden bijgewerkt naar **APPROVED** of **APPROVED WITH MINOR GAPS**.
