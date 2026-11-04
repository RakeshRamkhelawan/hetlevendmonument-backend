# FE-SEC-008: React Query cache keys tenant-scoped

**Sprint:** Studio UI Fix Dag 1
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

`useTemplates.ts` en `useWorkflowLearning.ts` gebruikten React Query cache-keys zonder `tenantId`.
Bij account-switches of gedeelde browser-sessies konden templates en learning-data van tenant A
aan tenant B worden getoond tot de stale-time verliep (5 minuten bij templates).

## Implementatie

### `useTemplates.ts`

Aan elke hook `tenantId` toegevoegd via `useAuthStore`:

```typescript
const tenantId = useAuthStore((state) => state.user?.tenantId ?? "");
```

Query keys:

- `['templates', category]` → `['templates', tenantId, category]`
- `['template', templateId]` → `['template', tenantId, templateId]`
- `['templates', 'search', query]` → `['templates', 'search', tenantId, query]`

`useInstantiateTemplate` invalidation: `['templates']` → `['templates', tenantId]`
(voorkomt cross-tenant cache flush bij multi-tenant QueryClient)

### `useWorkflowLearning.ts`

```typescript
const tenantId = useAuthStore((state) => state.user?.tenantId ?? "");
```

Query keys:

- `['learning', 'rules', workflowId]` → `['learning', 'rules', tenantId, workflowId]`
- `['learning', 'metrics', workflowId]` → `['learning', 'metrics', tenantId, workflowId]`

Backend-URL's bevatten geen tenantId (correct -- ADR-003: tenant via JWT, niet via URL-params).

## Pre-existing bug gefixed

`useInstantiateTemplate.onSuccess` had `queryKey: ['templates']` als bare property
(geen `queryClient.invalidateQueries()` aanroep). Gelijktijdig gecorrigeerd naar
`queryClient.invalidateQueries({ queryKey: ['templates', tenantId] })`.

## Tests

- `useTemplates.test.ts` -- authStore mock + tenant isolation test GREEN (8/8)
- `useWorkflowLearning.test.ts` -- authStore mock + tenant isolation test GREEN (14/14)
- Bestaande tests volledig GROEN


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: React Query cache keys tenant-scoped (SEC-004: useTemplates + useWorkflowLearning -- tenantId in alle queryKeys) is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt React Query cache keys tenant-scoped (SEC-004: useTemplates + useWorkflowLearning -- tenantId in alle queryKeys).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
