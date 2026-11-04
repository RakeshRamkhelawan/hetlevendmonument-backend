# FE-SEC-005: ActivePieces project_id tenant-scoped

**Sprint:** Studio UI Fix Dag 1
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

`ConnectionManager.tsx:71` en `WorkflowBuilder.tsx:277` gebruikten `project_id: 'default'` hardcoded
bij ActivePieces API-aanroepen (`createConnection` en `createFlow`). Hierdoor werden alle
verbindingen en flows aangemaakt in een gedeeld `'default'` project, ongeacht de tenant van de gebruiker.

## Implementatie

### `ConnectionManager.tsx`

1. `import { useAuthStore } from '@/lib/stores/authStore'`
2. `const tenantId = useAuthStore((state) => state.user?.tenantId)` bovenaan component
3. Early-return guard in `handleCreateConnection` als `!tenantId` (unauthenticated)
4. `project_id: tenantId` (string, rechtstreeks uit JWT-claim via auth store)

### `WorkflowBuilder.tsx`

1. Zelfde import + selector
2. Early-return guard in `deployToActivePieces` met `setDeploymentStatus` error-bericht
3. `project_id: tenantId`

## Patroon

`tenantId` komt uit Zustand auth store, die gevuld wordt vanuit de JWT-payload bij login.
Nooit uit request body (compliant met ADR-003 + CLAUDE.md rule 1).

De fallback `|| 'default'` is bewust weggelaten -- een early-return guard is veiliger
dan stil doorgaan met een gedeeld project bij missing auth.

## Tests

- `ConnectionManager.tenant.test.tsx` -- RED voor fix, GREEN na fix
- `WorkflowBuilder.tenant.test.tsx` -- RED voor fix, GREEN na fix
- `ConnectionManager.errors.test.tsx` -- authStore mock toegevoegd, bestaande tests GROEN
- 33/33 gerichte tests GROEN


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: ActivePieces project_id tenant-scoped (SEC-002: ConnectionManager + WorkflowBuilder -- early-return guard + tenantId uit authStore) is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt ActivePieces project_id tenant-scoped (SEC-002: ConnectionManager + WorkflowBuilder -- early-return guard + tenantId uit authStore).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
