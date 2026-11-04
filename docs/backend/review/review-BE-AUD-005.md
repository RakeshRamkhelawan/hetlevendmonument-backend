# Review: BE-AUD-005 -- session=db wiring (15 call-sites, 7 bestanden)

**Datum:** 2026-06-30
**Sprint:** SP-AUDIT-004
**Reviewer:** BE-review-agent

---

## A. Eindoordeel

**APPROVED**

---

## B. Samenvatting

Specificatie dekt alle 7 bestanden en 15 call-sites. De twee ordering-fixes (delete_user,
delete_tenant) zijn correct beschreven inclusief de ORM-attribute-expiration motivatie.
Het get_db() auto-commit mechanisme is correct beschreven en geverifieerd via een bestaand
referentiepatroon (tenants_list_router.py). Architecture test als kwaliteitspoort is vermeld.
Backlog voor domains/verticals expliciet benoemd. Geen CRITICAL of HIGH bevindingen.

---

## C. Bevindingen per categorie

### 1. Coverage gaps

- Geen. Alle 7 bestanden opgesomd in inventory. Domains/verticals (3 bestanden) terecht als out-of-scope gemarkeerd met backlog-melding.

### 2. Functionele onduidelijkheden

- Geen.

### 3. Technische onduidelijkheden

- MINOR: de spec noemt "get_db() auto-commit op database.py:489" maar verwijst niet naar het referentiebestand (tenants_list_router.py) dat dit bewijst. Dit is geverifieerd tijdens implementatie maar niet geciteerd in de spec.

### 4. Ontbrekende foutstatussen en edge cases

- Geen relevante HTTP-statuscodes; edge cases (delete, expired ORM attrs) zijn beschreven.

### 5. Acceptatiecriteria problemen

- Geen. Zeven criteria, elk direct testbaar via architecture test of unit test.

### 6. Integratorhandleiding / API-uitleg problemen

- Geen. Correct beperkt tot "geen wijziging in request/response format".

### 7. Trainingsdata problemen

- Geen.

### 8. Structuur- en consistentieproblemen

- Geen.

### 9. Risico's voor implementatie, security of QA

- LAAG: domains/verticals (3 bestanden) nog niet gefixed; audit entries voor nonprofit/media/healthcare workflows zijn nog steeds silent None. Backlog correct gedocumenteerd.

---

## D. Issue register

| Severity | Sectie | Probleem | Waarom | Correctie |
| --- | --- | --- | --- | --- |
| Low | Sectie 6 | get_db() auto-commit referentiebestand niet geciteerd | Toekomstige lezer kan claim niet snel verifieren | Optioneel: voeg "geverifieerd in tenants_list_router.py:44" toe |
| Low | Open aannames | Domains/verticals backlog niet voorzien van sprint-ID | Kan vergeten worden | Optioneel: koppel aan SP-AUDIT-005 backlog-item |

---

## E. Ontbrekende items

- Geen ontbrekende artefacten.

---

## F. Verbeterde tekstvoorstellen

- Geen correcties noodzakelijk.

---

## G. Release-oordeel

- Geschikt voor bouw / implementatie: JA
- Geschikt voor QA en geautomatiseerd testen: JA (architecture test als primaire poort)
- Geschikt voor LLM-training: JA
- Geschikt voor integratorhandleiding / API-documentatie: JA (interne change, geen extern interface-impact)
