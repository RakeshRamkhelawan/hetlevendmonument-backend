# Review: BE-SVC-043 TenantService en tenants router refactor

## Metadata

- Feature ID: BE-SVC-043
- Review datum: 2026-06-27
- Reviewer: onafhankelijke AI-agent
- Spec locatie: `docs/backend/features/BE-SVC-043-tenant-service.md`

---

## Eindoordeel

**APPROVED WITH MINOR GAPS**

De specificatie beschrijft de nieuwe TenantService, de vier sub-routers, de dependency factory, schemas en de belangrijkste flows volledig genoeg voor implementatie, QA en LLM-training. De meeste bevindingen zijn minor en betreffen uitbreidingen die buiten de huidige pilot vallen.

---

## Samenvatting

De spec is consistent met de gecommitte code in `src/core/services/tenant_service.py` en `src/core/api/v1/tenants/`. Tenant-isolatie, auth checks, foutstatussen, audit logging en cache invalidatie zijn gedocumenteerd. De structuur volgt het backend feature-spec template. Enkele onderwerpen (transactie-racecondities, prestatie-aspecten, volledige integratietestuitslagen) zijn minder diepgaand behandeld.

---

## Bevindingen per categorie

### 1. Coverage gaps

- **Minor:** De spec noemt dat duplicate checks niet atomic zijn, maar beschrijft geen concrete mitigatie of detectie van `IntegrityError`. Aanbeveling: voeg een opmerking toe dat dit een bekende pre-existing beperking is.
- **Minor:** `TenantUpdate` velden zoals `twin_hard_delete_max_hours` en `subscription_status` zijn wel genoemd in de inventory maar niet verder uitgewerkt in aparte secties.

### 2. Functionele onduidelijkheden

- Geen significante functionele onduidelijkheden.

### 3. Technische onduidelijkheden

- **Minor:** De relatie tussen `TenantContext` (JWT claim), `get_tenant_service` en `_tenant_scope` is beschreven, maar een sequentie-diagram of expliciete flow zou het voor nieuwe developers verder verduidelijken.

### 4. Ontbrekende foutstatussen en edge cases

- **Minor:** 500-fouten door database- of audit-service storingen zijn niet expliciet per endpoint beschreven (wel algemeen in het template genoemd).
- **Minor:** Raceconditie bij gelijktijdige create met zelfde slug/name/domain is niet als apart edge case uitgewerkt.

### 5. Acceptatiecriteria problemen

- Alle acceptatiecriteria zijn testbaar. De criteria voor integratietests zijn lokaal geblokkeerd door een pre-existing DB-fixture probleem; dit is correct benoemd als risico.

### 6. Integratorhandleiding / API-uitleg problemen

- De integratorhandleiding is beknopt en bruikbaar. Een voorbeeld-request/response blok zou de bruikbaarheid verhogen.

### 7. Trainingsdata problemen

- De trainingssamenvatting volgt het verplichte mini-format. Geen structurele problemen.

### 8. Structuur- en consistentieproblemen

- De spec gebruikt consistent de BE-XXX ID-conventie.
- De wijziging van feature ID van BE-SVC-034 (in oorspronkelijke commits) naar BE-SVC-043 (wegens conflict in ID-REGISTRY) is correct gedocumenteerd.

### 9. Risico's voor implementatie, security of QA

- **Medium:** Legacy `tenant_management` router is uit de canonical app factory verwijderd. Dit is een breaking change voor eventuele directe afnemers van `app_factory`. De spec benoemt dit als risico.
- **Medium:** Integratietests kunnen lokaal niet worden gedraaid door `ConnectionDoesNotExistError` in de test harness. Dit belemmert QA op Windows; CI/Linux dient te verifiëren.

---

## Issue register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Medium | Risico's | Legacy router removal is breaking | Externe scripts/tests die `app_factory` gebruiken kunnen falen | Communiceer deprecatie; monitoring na deploy |
| Medium | Integratietests | DB fixture timeout/connection error | Lokale QA kan niet verifiëren | Draai integratietests in CI/Linux; onderzoek Windows event loop |
| Low | Coverage gaps | `IntegrityError` raceconditie niet uitgewerkt | Mogelijke onverwachte 500 bij gelijktijdige creates | Documenteer als bekende beperking of voeg exceptie-afhandeling toe |
| Low | Integratorhandleiding | Geen request/response voorbeelden | Minder snel bruikbaar voor niet-backend developers | Voeg curl/JSON voorbeelden toe in volgende iteratie |

---

## Ontbrekende items

- Geen ontbrekende endpoints of services binnen scope.
- `PATCH /{tenant_id}/status` is bewust out-of-scope.

---

## Verbeterde tekstvoorstellen

Geen kritieke tekstwijzigingen noodzakelijk voor GO.

---

## Release-oordeel

- Geschikt voor bouw / implementatie: **JA**
- Geschikt voor QA en geautomatiseerd testen: **JA, mits integratietests in CI/Linux draaien**
- Geschikt voor LLM-training: **JA**
- Geschikt voor integratorhandleiding / API-documentatie: **JA, met optionele voorbeelden in volgende iteratie**

---

*Review-type: backend feature spec | Gegenereerd: 2026-06-27*
