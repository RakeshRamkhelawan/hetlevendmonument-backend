# Review: BE-EP-009 Sync Snapshot + Awareness JSON Endpoints

## Eindoordeel: APPROVED WITH MINOR GAPS

---

## Samenvatting

De specificatie voor SP-E02 Dag 1 is functioneel volledig, technisch accuraat, en geschikt voor bouw, QA en integratie. Alle artefacten zijn geinventariseerd, tenant-isolatie en auth zijn beschreven, en de integratoruitleg is begrijpelijk voor niet-backend developers.

---

## Bevindingen per categorie

### 1. Coverage gaps — GEEN

Alle endpoints, modellen, schemas, migraties en decorators zijn gedocumenteerd.

### 2. Functionele onduidelijkheden — MINOR

- **M1**: De awareness endpoint beschrijft dat het data uit Redis haalt, maar er staat niet expliciet dat het schrijven naar Redis buiten scope is (Dag 2). Dit staat wel onder "Out of scope" maar kan explicieter in de awareness flow zelf.
- **M2**: "Append-only" wordt meerdere keren genoemd maar er is geen uitleg waarom dit design choice is (eenvoud, audit trail, versiegeschiedenis).

### 3. Technische onduidelijkheden — MINOR

- **M3**: De `best_effort` audit logging wrapper wordt genoemd maar de spec zegt "Audit log is secondary; primary operation already committed". Het is onduidelijk of er daadwerkelijk een audit record wordt geschreven of alleen een log entry. Aanbeveling: verduidelijk dat dit een `logger.info` call is, geen DB insert.
- **M4**: De rate limit key functie `_snapshot_key` is beschreven in de rate_limiter.py wijziging maar niet expliciet in de endpoint spec. Aanbeveling: voeg toe aan BE-EP-009 sectie 12.

### 4. Ontbrekende foutstatussen en edge cases — MINOR

- **M5**: 503 Service Unavailable staat in de template maar wordt niet beschreven voor de sync endpoints. Deze is relevant voor Redis-down scenarios bij awareness. Aanbeveling: vermeld dat Redis failure resulteert in 200 + lege lijst (geen 503), of beschrijf wanneer wel 503.

### 5. Acceptatiecriteria problemen — MINOR

- **M6**: "Rate limiting retourneert 429 na overschrijding" is een acceptatiecriterium maar er is geen test die dit expliciet verifieert. De unit tests mocken `get_db` en testen de decorator niet. Aanbeveling: markeer als integratietest voor Dag 2, of voeg toe aan backlog.

### 6. Integratorhandleiding / API-uitleg problemen — GEEN

De integratorhandleiding is helder, concreet en geschikt voor API-consumenten.

### 7. Trainingsdata problemen — GEEN

Trainingssamenvattingen zijn compact, eenduidig en bruikbaar per artefact.

### 8. Structuur- en consistentieproblemen — GEEN

Alle secties volgen het verplichte format. IDs zijn uniek en consistent.

### 9. Risico's voor implementatie, security of QA — MINOR

- **M7**: Onbegrensde tabelgroei door append-only gedrag wordt genoemd onder risico's maar er is geen concrete mitigatie (bijv. "retentie actor in sprint X"). Aanbeveling: concrete sprint toevoegen aan backlog.

---

## Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
|----------|-------------|----------|---------------------------|-------------------|
| Medium | BE-EP-009 / M3 | `best_effort` audit logging is verwarrend | Spec suggereert DB audit maar is alleen logging | **FIXED** — best_effort wrapper verwijderd, directe logging |
| Medium | BE-EP-009 / M6 | Geen 429 test coverage | Acceptatiecriterium niet geautomatiseerd getest | **FIXED** — 3 rate limit tests toegevoegd (429 PUT, 429 GET, tenant scope) |
| Low | BE-EP-009 / M1 | Awareness schrijven niet expliciet out-of-scope | Integrator kan verwachten dat POST awareness bestaat | Voeg toe aan awareness flow: "Schrijven naar Redis is Dag 2 scope" |
| Low | BE-EP-009 / M7 | Geen concrete retentie sprint | Risico blijft open zonder actie | **FIXED** — Retentie van max 100 snapshots per workflow geimplementeerd in PUT endpoint |

---

## Ontbrekende items

Geen. Alle verwachte endpoints, modellen, schemas, migraties en utilities zijn gedocumenteerd.

---

## Verbeterde tekstvoorstellen

**M3 fix — BE-EP-009 sectie 14:**
> Oorspronkelijk: "Audit log: best_effort wrapper (secundair, mag niet falen)"
> Verbeterd: "Audit logging: best_effort wrapper met logger.info call (geen DB insert; puur voor observability)"

**M1 fix — BE-FLW-003:**
> Toevoegen aan "Eindtoestand": "Awareness state in Redis blijft ongewijzigd; schrijven is Dag 2 scope."

---

## Release-oordeel

| Criterium | Oordeel |
|-----------|---------|
| Geschikt voor bouw / implementatie | JA |
| Geschikt voor QA en geautomatiseerd testen | JA (met kanttekening: 429 integratietest nodig) |
| Geschikt voor LLM-training | JA |
| Geschikt voor integratorhandleiding / API-documentatie | JA |

---

## GO/NO-GO

**GO** — SP-E02 Dag 1 feature documentatie is goedgekeurd met minor gaps. De 4 MEDIUM issues zijn geen blockers voor merge naar develop, maar dienen te worden opgepakt in Dag 2 of de volgende sprint.

*Reviewer: AI Agent | Datum: 2026-05-29*
