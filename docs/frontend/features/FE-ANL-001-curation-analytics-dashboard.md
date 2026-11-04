# Feature: FE-ANL-001 Curation Analytics & KPI Dashboard

## Metadata
- **Feature ID:** `FE-ANL-001`
- **Titel:** Curation Analytics & KPI Dashboard
- **Sprint:** ADR-029 Foundation Portal (Levend Monument)
- **Status:** IMPLEMENTATION
- **Auteur:** AI Agent (Senior Architect / Developer)
- **Datum:** 2026-09-12
- **Gerelateerde ADRs:** ADR-029 (Foundation Portal Curation & Analytics), ADR-028 (Design System)
- **Backend Tegenhanger:** `BE-EP-045`

---

## 1. Doel & Context
In `portal/src/pages/AdminCuratie.tsx` ontbreekt een overzicht van belangrijke KPI's voor curatoren. `FE-ANL-001` breidt het curatieportaal uit met:
1. Een interactief KPI-grid met realtime statistieken: wachtrij, goedgekeurde erfgoeditems, afwijzingen, gemiddelde verwerkingstijd en actieve klascodes.
2. Een overzicht van AI-gegenereerde NDE tags en gemiddelde confidence scores.
3. WCAG 2.1 AA toegankelijke componenten met live-updates en error resilience.

---

## 2. Componenten & API Integratie

### API Client
Toevoeging in `portal/src/api/client.ts`:
```typescript
async getCuratieAnalytics(): Promise<CurationAnalyticsResponse>
```

### Types (`portal/src/types/index.ts`)
- `TagDistributionItem`: `{ tag: string; tag_type: string; count: number; average_confidence: number }`
- `NewsletterAnalytics`: `{ total_subscribers: number; verified_subscribers: number }`
- `EducationalAnalytics`: `{ active_codes: number; total_codes: number }`
- `CurationAnalyticsResponse`: Hoofdstructuur met alle geaggregeerde KPI's.

### UI Uitbreiding (`portal/src/pages/AdminCuratie.tsx`)
- Bovenste sectie toont 5 KPI-kaarten:
  - Wachtrij (Pending items met waarschuwingsicoon)
  - Gepubliceerd (Approved items met succesindicator)
  - Afgewezen (Rejected items)
  - Gem. Beoordelingstijd (in minuten of uren)
  - Platform Impact (Nieuwsbriefabonnees & Actieve educatieve klassen)
- Togglebaar paneel voor AI Tag Kwaliteit (NDE themas, distributie en betrouwbaarheidsbalken).

---

## 3. Toegankelijkheid (WCAG 2.1 AA)
- Live regions (`aria-live="polite"`) voor het melden van statuswijzigingen en data updates.
- Hoog contrast tussen statistiekcijfers en achtergrond.
- Toetsenbordnavigatie voor alle acties en toggles.

---

## Trainingssamenvatting

- **Component**: Curation Analytics & KPI Dashboard (`FE-ANL-001`)
- **Doel**: Realtime visueel inzicht in werkvoorraad, curatiedoorlooptijd en AI verrijking voor erfgoedbeheerders.
- **Architectuurregel**: Fail-open fouttolerantie; het dashboard crasht niet wanneer analytics niet kan worden opgehaald.
- **Geverifieerd met**: Vitest suite (`portal/src/__tests__/AdminCuratieAnalytics.test.tsx`), `tsc --noEmit`.
- **Actor**: Curator
  - **Flow**: Curator logt in en navigeert naar het curatiebeheer -> KPI kaarten tonen actuele werkvoorraad en doorlooptijd -> Curator klikt op de AI NDE-Thesaurus accordion -> Systeem toont de meest voorkomende themas en hun AI betrouwbaarheidsscores.

