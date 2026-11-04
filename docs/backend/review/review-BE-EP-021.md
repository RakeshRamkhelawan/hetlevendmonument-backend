# Review BE-EP-021 — Tenant Stats Real DB Queries

## A. Eindoordeel

APPROVED

## B. Samenvatting

De specificatie beschrijft de vervanging van hardcoded nulwaarden in `GET /tenants/{tenant_id}/stats` door echte DB-aggregatiequeries. De broncode in `src/core/api/v1/tenants/tenants_stats_router.py` toont de permission check (own tenant of superuser) en de delegatie naar `TenantService.get_tenant_stats()`. De spec is concreet over de vier metrieken en de best-effort opslagberekening.

## C. Bevindingen per categorie

### 1. Coverage gaps

- Geen. De vier metrieken zijn expliciet benoemd.
- De spec noemt niet precies in welk bestand de queries zitten (`tenants_stats_router.py` is de router; de service zit in `src/core/api/v1/tenants/dependencies.py` of een service-module). TODO: bestandspad van de service toevoegen.

### 2. Functionele onduidelijkheden

- Geen. Het doel (admin-dashboard met echte data) is helder.

### 3. Technische onduidelijkheden

- De spec legt uit dat `AuditLog.timestamp` gebruikt wordt en dat `tenant_id` nullable is in `AuditLog`. Dat is een waardevolle nuance.
- De best-effort opslagberekening met try/except is goed gemotiveerd.

### 4. Ontbrekende foutstatussen en edge cases

- De spec noemt 403 en 500. 404 wordt veroorzaakt als `service.get_tenant_stats()` `None` retourneert. Dat is correct toegelicht in de broncode.
- Een edge case ontbreekt: als `Document.file_size_bytes` NULL is voor alle rijen, retourneert `func.sum()` `None`; de spec noemt `storage_used_gb=0.0` maar niet hoe de `None` naar `0.0` wordt afgehandeld.

### 5. Acceptatiecriteria problemen

- De testverwijzing is concreet. Een expliciete checklist ontbreekt, maar de testnamen dekken het.

### 6. Integratorhandleiding / API-uitleg problemen

- De Trainingssamenvatting is voldoende.

### 7. Trainingsdata problemen

- Geschikt voor LLM-training.

### 8. Structuur- en consistentieproblemen

- Compacte feature-note, passend voor een kleine endpoint-fix.

### 9. Risico's voor implementatie, security of QA

- Laag risico. Tenant-isolatie en permission check zijn aanwezig.

## D. Issue Register

| Severity | ID of sectie | Probleem | Waarom dit een probleem is | Concrete correctie |
| --- | --- | --- | --- | --- |
| Low | Broncode / service-locatie | Servicebestand met queries niet vermeld | Reviewers kunnen de aggregatiequeries niet direct vinden | Voeg toe: queries zitten in `TenantService` (te vinden via `src/core/api/v1/tenants/dependencies.py`) |
| Low | Edge case | Afhandeling van `func.sum()` = None niet gedocumenteerd | Kan leiden tot verwarring over `storage_used_gb=0.0` | Noteer expliciet dat `None` naar `0.0` wordt gecast |

## E. Ontbrekende items

- Geen.

## F. Verbeterde tekstvoorstellen

- "Opslagberekening is best-effort" -> "Opslagberekening is best-effort; `func.sum(Document.file_size_bytes)` retourneert `None` als alle waarden NULL zijn, wat door de service naar `0.0` wordt gecast."

## G. Release-oordeel

- Geschikt voor bouw / implementatie: ja.
- Geschikt voor QA en geautomatiseerd testen: ja.
- Geschikt voor LLM-training: ja.
- Geschikt voor integratorhandleiding / API-documentatie: ja.
