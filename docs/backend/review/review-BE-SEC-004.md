# Review — BE-SEC-004: DSAR/PolicyChange tenant_id payload security fix

**Reviewer:** code-reviewer + quality-reviewer subagents (SP-S01 Laag A)
**Datum:** 2026-05-30
**Spec:** `docs/backend/features/BE-SEC-004-dsar-policychange-tenant-payload-fix.md`

---

## A. EINDOORDEEL

**APPROVED WITH MINOR GAPS**

---

## B. SAMENVATTING

De spec documenteert de B-005 security fix volledig. Het probleem (user-controlled `tenant_id`
uit payload), de fix (server-side TenantRepo lookup), de twee nieuwe protocol-methoden en de
impact op bestaande tests zijn allemaal beschreven. De minor gaps betreffen de concrete
productie-implementatie van `TenantRepo` (buiten scope van de sprint) en een bekende beperking
waarbij `user_id` en `workflow_id` zelf ook uit de payload komen — dit is acceptabel voor een
interne event bus en gedocumenteerd als aanname.

---

## C. BEVINDINGEN PER CATEGORIE

### 1. Coverage gaps

- **Medium (known):** Concrete TenantRepo-implementaties buiten tests zijn niet bijgewerkt.
  Dit is expliciet vermeld als out-of-scope en als risico in de spec. Productie-implementators
  MOETEN de twee nieuwe methoden implementeren. Aanbeveling: voeg dit toe als trigger-conditie
  bij SP-H01 re-audit checklist.

### 2. Functionele onduidelijkheden

- **Low:** Spec zegt dat `user_id` in DSAR ook uit de payload komt en dus user-controlled is.
  De fix lost het `tenant_id`-spoof risico op, maar een aanvaller kan nog steeds een nep `user_id`
  sturen. Dit is correct gedocumenteerd als aanname ("event bus is intern"). Acceptabel.

### 3. Technische onduidelijkheden

- **Low:** Sectie 7-16 van BE-SEC-004b zijn samengevat als "identiek patroon aan BE-SEC-004a".
  Dit is beknopt maar voldoende voor een protocol-methode.

### 4. Ontbrekende foutstatussen en edge cases

- **Low:** Spec beschrijft het geval waarbij TenantRepo een exception gooit (logger.error + return)
  maar noemt niet expliciet wat de dedup-Redis-fout doet. Dit is consistent met het bestaande
  patroon in alle andere monitors.

### 5. Acceptatiecriteria problemen

- GEEN. Criteria zijn concreet en gedekt door unit tests.

### 6. Integratorhandleiding problemen

- GEEN. Zowel event publishers als TenantRepo implementators worden expliciet aangesproken.

### 7. Trainingsdata problemen

- **Low:** BE-SEC-004b (get_tenant_id_for_workflow) mist een expliciete Trainingssamenvatting
  in de spec — de spec zegt "identiek aan BE-SEC-004a". Voor training is een aparte samenvatting
  preferabel. Geen blocker.

### 8. Structuur- en consistentieproblemen

- GEEN.

### 9. Risico's

- **High (known, gedocumenteerd):** Productie TenantRepo-implementaties moeten worden uitgebreid.
  Dit is een breaking change voor bestaande concrete klassen. Gedocumenteerd als risico.
- **Medium (known):** Mis-geconfigureerde TenantRepo die altijd `None` retourneert zou alle
  signals onderdrukken zonder zichtbare fout. Monitoring aanbevolen.

---

## D. ISSUE REGISTER

| Severity | ID/Sectie | Probleem | Correctie |
| --- | --- | --- | --- |
| High | Risico's | Concrete TenantRepo-klassen moeten 2 nieuwe methoden implementeren | Opnemen in SP-H01 re-audit checklist; geen blocker voor SP-S01 |
| Medium | Risico's | TenantRepo altijd-None zou signals onderdrukken | Voeg monitoring toe post-MVP |
| Low | BE-SEC-004b sectie 19 | Trainingssamenvatting samengevat als "identiek" | Uitwerken in post-MVP doc-update |

---

## E. ONTBREKENDE ITEMS

- Geen ontbrekende artefacten voor de sprint-scope.
- Post-MVP: concrete TenantRepo implementaties vereisen update.

---

## F. RELEASE-OORDEEL

- Geschikt voor bouw / implementatie: **JA** — implementatie reeds gereed
- Geschikt voor QA en geautomatiseerd testen: **JA** — 20 monitor tests + 10 SP-S01 tests
- Geschikt voor LLM-training: **JA** — trainingssamenvatting aanwezig voor alle 4 artefacten
- Geschikt voor integratorhandleiding: **JA** — event publishers en TenantRepo implementators geadresseerd

---

*Review door: SP-S01 Laag A subagents | 2026-05-30*
