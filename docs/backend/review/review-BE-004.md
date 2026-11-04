# Backend Feature Review — BE-004

## Metadata

- **Review ID:** review-BE-004
- **Feature ID:** BE-004
- **Feature naam:** Type Contract Hardening — Mypy Compliance Fixes
- **Reviewer:** Kimi Code CLI (self-review)
- **Datum:** 2026-05-28
- **Spec versie:** 1.0

---

## A. Eindoordeel

**APPROVED WITH MINOR GAPS**

De documentatie is volledig, consistent en geschikt voor implementatie, QA en LLM-training. De drie type-hardening fixes zijn correct geïnventariseerd en de acceptatiecriteria zijn testbaar. Twee minor gaps zijn benoemd onderaan.

---

## B. Samenvatting

De spec beschrijft drie gerelateerde mypy-fixes op de copilot service-laag: een Protocol-wijziging (`IAuditWriter`), een utility-uitbreiding (`GDPREnforcer.detect_pii`), en een service-uitbreiding (`CouncilAuditWriter.log_user_response`). De documentatie is concreet, scheidt functionele en technische beschrijving correct, en bevat testbare acceptatiecriteria. De integratoruitleg is correct gemarkeerd als N.v.t. omdat er geen externe API-impact is.

---

## C. Bevindingen per categorie

### 1. Coverage gaps

- **Geen significante gaps.** Alle drie de gewijzigde artefacten zijn gedocumenteerd met unieke IDs (BE-SCH-001, BE-UTL-001, BE-SVC-001).
- **Minor:** De spec vermeldt niet expliciel dat `detect_pii` ook wordt aangeroepen vanuit `PrivacyOfficer._deliberate_inner` (regel 127). Dit is impliciet duidelijk via "Gerelateerde flow", maar een expliciete call-site referentie zou de traceability verbeteren.

### 2. Functionele onduidelijkheden

- Geen. Het doel van elke fix is helder: mypy-typefout oplossen zonder runtime-gedrag te wijzigen.

### 3. Technische onduidelijkheden

- Geen. De signatures, patronen en side effects zijn expliciet beschreven.

### 4. Ontbrekende foutstatussen en edge cases

- **N.v.t.** Er zijn geen nieuwe endpoints. De bestaande foutpaden (`RuntimeError` bij ontbrekende audit writer, `VETO` bij detectie-errors) zijn gedocumenteerd.

### 5. Acceptatiecriteria problemen

- Alle acceptatiecriteria zijn testbaar en geverifieerd (47/47 tests groen, 13 nieuwe tests voor `detect_pii`).

### 6. Integratorhandleiding / API-uitleg problemen

- Correct gemarkeerd als N.v.t. Er is inderdaad geen externe API-impact.

### 7. Trainingsdata problemen

- De trainingssamenvattingen volgen het verplichte mini-format (Actor, Voorwaarde, Actie, Systeemverwerking, Succesrespons, Foutrespons, Uitzonderingen).
- **Minor:** Voor `BE-UTL-001` staat onder "Foutrespons" `Geen`, maar de uitzonderingen sectie vermeldt wel dat `PrivacyOfficer` runtime errors afvangt. Dit is een lichte inconsistentie die leesbaarheid kan beïnvloeden.

### 8. Structuur- en consistentieproblemen

- De inventory tabel gebruikt correct de prefix-gebaseerde IDs.
- De build summary is consistent met de gewijzigde bestanden.

### 9. Risico's voor implementatie, security of QA

- **Minor:** `detect_pii` gebruikt een creditcard regex (`\b(?:\d{4}[-\s]?){3,4}\d{1,4}\b`) die ook gewone 16-cijferige getallen kan matchen (bijv. ordernummers). Dit is een bekend risico dat in de risico-tabel staat, maar de mitigatie ("ML-classifier") is een backlog-item zonder tijdsinschatting.

---

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Medium | BE-UTL-001 §6 | `detect_pii` creditcard regex kan false positives geven op niet-PII 16-cijferige getallen. | Onterechte `REQUIRE_HITL` verdicts bij normale payloads. | Documenteer een expliciete TODO om de regex te vervangen door `presidio` of vergelijkbare PII-lib bij productie-hardening. |
| Low | BE-UTL-001 §19 | Trainingssamenvatting zegt "Foutrespons: Geen" maar uitzonderingen sectie noemt wel `VETO`. | Inconsistentie in trainingsdata kan verwarring geven bij LLM-training. | Hernoem "Foutrespons" naar "Foutrespons: wordt afgevangen door PrivacyOfficer → VETO" of splits explicieter. |

---

## E. Ontbrekende items

Geen vermoedelijk ontbrekende endpoints, services of flows. De scope is bewust beperkt tot type-hardening.

---

## F. Verbeterde tekstvoorstellen

**Huidig (BE-UTL-001 §19):**
> - Foutrespons: Geen — bij errors in detectie vangt `PrivacyOfficer` dit af en retourneert `VETO`.
> - Uitzonderingen: Runtime errors tijdens detectie leiden tot `VETO` verdict met reason_code `EXCEPTION`.

**Voorgesteld:**
> - Foutrespons: Runtime errors in `detect_pii` worden niet hier maar in `PrivacyOfficer._deliberate_inner` afgevangen, resulterend in een `VETO` verdict met reason_code `EXCEPTION`.
> - Uitzonderingen: Geen directe excepties vanuit `detect_pii` zelf.

---

## G. Release-oordeel

| Criterium | Oordeel |
| --- | --- |
| Geschikt voor bouw / implementatie? | **Ja** — fixes zijn reeds geïmplementeerd en getest. |
| Geschikt voor QA en geautomatiseerd testen? | **Ja** — 13 nieuwe tests + 47 bestaande tests groen. |
| Geschikt voor LLM-training? | **Ja** — documentatie is concreet, gestructureerd, en bevat trainingsdata. |
| Geschikt voor integratorhandleiding / API-documentatie? | **Ja** — correct gemarkeerd als interne wijziging zonder API-impact. |

---

*Reviewer: Kimi Code CLI | Datum: 2026-05-28*
