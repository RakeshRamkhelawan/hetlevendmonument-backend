# Feature: BE-EP-045 Foundation Curation Analytics & KPI Dashboard

## Metadata
- **Feature ID:** `BE-EP-045`
- **Titel:** Foundation Curation Analytics & KPI Dashboard
- **Sprint:** ADR-029 Foundation Portal (Levend Monument)
- **Status:** IMPLEMENTATION
- **Auteur:** AI Agent (Senior Architect / Developer)
- **Datum:** 2026-09-12
- **Gerelateerde ADRs:** ADR-029 (Foundation Portal Curation & Analytics), ADR-003 (Tenant Identity), ADR-004 (Tenant Isolation), ADR-015 (Safety & Rate Limiting)
- **Frontend Tegenhanger:** `FE-ANL-001`

---

## 1. Doel & Context
In de Levend Monument Foundation Portal beheren erfgoedcuratoren ingezonden verhalen en documenten. Om inzicht te krijgen in de werkvoorraad, de reactiesnelheid van de redactie, en de kwaliteit van AI-verrijking (NDE thesaurus tagging), voorziet `BE-EP-045` in een geaggregeerd analytics endpoint:
`GET /{tenantSlug}/foundation/admin/curatie/analytics` (en route alias `/admin/analytics`).

Tevens lost deze feature de route alignment op tussen de frontend client (`portal/src/api/client.ts`) en de backend (`src/core/api/v1/foundation/admin/curatie.py`) door het toevoegen van het routepad `@router.get("/curatie/queue", ...)`.

---

## 2. API Contracten & Schemas

### Endpoint
`GET /{tenantSlug}/foundation/admin/curatie/analytics`

- **Toegangscontrole:** Alleen geauthenticeerde curatoren en beheerders (`require_curator`).
- **Tenant Scoping:** Automatisch beperkt tot de tenant via `public_tenant_scope(tenantSlug, session)`.
- **Rate Limiting:** Beveiligd via `@portal_read_limit`.

### Response Schema: `CurationAnalyticsResponse`
```json
{
  "status_counts": {
    "pending": 5,
    "approved": 24,
    "rejected": 3,
    "archived": 0
  },
  "total_content": 32,
  "average_moderation_seconds": 1850.5,
  "tag_distribution": [
    {
      "tag": "Klederdracht",
      "tag_type": "THEME",
      "count": 12,
      "average_confidence": 0.89
    },
    {
      "tag": "Paramaribo",
      "tag_type": "LOCATION",
      "count": 8,
      "average_confidence": 0.94
    }
  ],
  "newsletter": {
    "total_subscribers": 142,
    "verified_subscribers": 138
  },
  "education": {
    "active_codes": 5,
    "total_codes": 9
  }
}
```

---

## 3. Database & Query Aggregaties
Geen nieuwe tabellen of migraties nodig. De statistieken worden live berekend met geoptimaliseerde SQLAlchemy queries:
1. `FoundationContent.status` tellingen gegroepeerd per status.
2. Gemiddelde curatiedoorlooptijd: `func.avg(func.extract('epoch', FoundationContent.updated_at - FoundationContent.created_at))` voor goedgekeurde en afgewezen content.
3. Top 10 NDE ContentTags via `group_by(ContentTag.tag, ContentTag.tag_type)` met `func.count(ContentTag.id)` en `func.avg(ContentTag.confidence)`.
4. Telling van `NewsletterSubscription` (totaal en `is_active == True`).
5. Telling van `EducationalAccess` (totaal en actieve niet-verlopen codes).

---

## 4. Beveiliging & Guardrails
- **Strict Tenant Isolation:** Alle queries bevatten expliciet `.where(Model.tenant_id == tenant.id)`.
- **Strict Role Enforcement:** Verwerpt niet-curatoren met HTTP 403 Forbidden.
- **Fail-Secure Defaults:** Als er geen gemodereerde items zijn, retourneert `average_moderation_seconds` `null` in plaats van een division-by-zero fout.
- **No DateTime Now:** Alle tijdstipsvergelijkingen via `src.core.shared.datetime_utils.utc_now()`.

---

## Trainingssamenvatting

- **Component**: Foundation Curation Analytics & KPI Dashboard (`BE-EP-045`)
- **Doel**: Realtime geaggregeerde KPI's leveren voor erfgoedcuratoren en redacteuren.
- **Architectuurregel**: Live aggregaties via SQL (`func.count`, `func.avg`, `func.extract`), strikt multi-tenant geïsoleerd op `tenant_id`.
- **Geverifieerd met**: `tests/unit/test_foundation_curatie_analytics.py` (5 tests PASS).
- **Actor**: Curator / Beheerder
  - **Flow**: Curator opent het beheerdersportaal -> Frontend vraagt `GET /{tenantSlug}/foundation/admin/curatie/analytics` aan -> Backend berekent live statusverdeling, gemiddelde moderatietijd, top NDE thematags, nieuwsbrief- en educatie-aantallen -> Systeem retourneert de geaggregeerde KPI metrics.

