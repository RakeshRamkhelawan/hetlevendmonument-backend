# Code Review: BE-EP-045 Foundation Curation Analytics & KPI Dashboard

STATUS: APPROVED

## Metadata
- **Feature ID:** `BE-EP-045`
- **Sprint:** ADR-029 Foundation Portal (Levend Monument)
- **Reviewer:** AI Red Team / Senior Architect
- **Datum:** 2026-09-12
- **Resultaat:** GO (Approved with Devil's Advocate analysis)

---

## 1. Scope van Wijzigingen
- **Bestanden Gewijzigd:**
  - `src/core/api/v1/foundation/schemas.py`: toevoeging van `TagDistributionItem`, `NewsletterAnalytics`, `EducationalAnalytics`, `CurationAnalyticsResponse`.
  - `src/core/api/v1/foundation/admin/curatie.py`:
    - Toegevoegd route alias `@router.get("/curatie/queue", ...)`.
    - Toegevoegd endpoint `GET /{tenantSlug}/foundation/admin/curatie/analytics` (alias `/admin/analytics`).
  - `tests/unit/test_foundation_curatie_analytics.py`: unit tests voor aggregatielogica, schema validatie, tenant scoping en authenticatie.

---

## 2. Red Team Beoordeling & Kwaliteitspoorten

### A. Gate 1 (Specificatie & Contract)
- Goedgekeurd contract conform ADR-029 P2-3.
- Response model dekt alle vereiste statistieken: curatie status counts, gemiddelde doorlooptijd, NDE tag betrouwbaarheid/tellingen, nieuwsbrief abonnees en educatieve klassen.

### B. Gate 2 (Beveiliging, Multi-Tenancy & Datamodellering)
- **Tenant Isolatie (ADR-003 / ADR-004):**
  - Alle queries filteren expliciet op `tenant_id == tenant.id`.
  - Geen `tenant_id` uit request body of query parameters.
  - Cruciaal: `ContentTag` heeft conform ADR-029 geen eigen `tenant_id`, dus de tag aggregatie query maakt een expliciete `JOIN` op `FoundationContent` om isolatie te garanderen.
- **Autorisatie:**
  - Vereist `require_curator` dependency; ongeautoriseerde gebruikers worden geblokkeerd met 401/403.
- **Tijdzones:**
  - Gebruikt `utc_now()` in plaats van `datetime.now()` conform de strikte projectstandaard.

### C. Gate 3 (Tests & Code Kwaliteit)
- 100% ASCII conform; geen emojis.
- Geen division-by-zero bij een lege database of als er nog geen goedgekeurde/afgewezen items zijn (`average_moderation_seconds` wordt `None`).

---

## 3. Devil's Advocate (Waarom deze oplossing in de toekomst kan falen)

1. **Schaalbaarheid bij miljoenen rijen:**
   - De live SQL-aggregatie (`func.count`, `func.avg`, `func.extract`) voert live berekeningen uit over de tabellen. Bij tientallen miljoenen erfgoeditems kan een live `JOIN` en `GROUP BY` tussen `content_tags` en `foundation_content` traag worden als er geen dedicated index op `(content_id, tag_type, value)` of een materialized view/Redis cache aanwezig is.
   - *Mitigatie voor de toekomst:* Bij hoge schaal (post-launch) kan een Redis cache met een TTL van bijvoorbeeld 60 seconden worden geplaatst voor de curator KPI's, of een dagelijkse roll-up tabel.
2. **Klokverschillen & Tijdzone conversies:**
   - Het berekenen van `updated_at - created_at` via `func.extract('epoch', ...)` is afhankelijk van database klokconsistentie. Als een beheerder handmatig een timestamp aanpast in het verleden, kan dit resulteren in een negatieve duur.
   - *Mitigatie:* Het endpoint bevat een expliciete filter `FoundationContent.updated_at > FoundationContent.created_at` om eventuele inconsistente data uit te sluiten.
