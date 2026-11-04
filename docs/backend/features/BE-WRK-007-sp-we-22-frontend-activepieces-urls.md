# BE-WRK-007: SP-WE-22 Frontend Hardcoded ActivePieces URLs

**Sprint:** SP-WE-22 (P1)
**Status:** COMPLETED
**Datum:** 2026-06-12

---

## Samenvatting

2 frontend componenten bevatten hardcoded `http://localhost:3000` URLs die breken
in staging/productie. Vervangen door `config.activepiecesUrl` uit `@/config/environment`.

## Gewijzigde bestanden

| Bestand                                                                        | Wijziging                                |
| ------------------------------------------------------------------------------ | ---------------------------------------- |
| `frontend/src/components/activepieces/ConnectionManager.tsx`                   | import config + localhost:3000 vervangen |
| `frontend/src/components/activepieces/FlowExecutionMonitor.tsx`                | import config + localhost:3000 vervangen |
| `frontend/src/components/activepieces/__tests__/FlowExecutionMonitor.test.tsx` | test assert bijgewerkt (3000->8090)      |
| `tests/architecture/test_sp_we_22_frontend_hardcoded_urls.py`                  | 1 GREEN regression guard                 |
| `docs/SPRINT_TRACKER.md`                                                       | SP-WE-22 OPEN -> CLOSED                  |

## Fix

```ts
import { config } from '@/config/environment';
// ...
href={`${config.activepiecesUrl}/connections/${connection.id}`}
href={`${config.activepiecesUrl}/runs/${run.id}`}
```

`config.activepiecesUrl` = `import.meta.env.VITE_ACTIVEPIECES_URL || 'http://localhost:8090'`

## Verificatie

```bash
python -m pytest tests/architecture/test_sp_we_22_frontend_hardcoded_urls.py -v
# 1 passed

cd frontend && npm run type-check
# 0 errors

npm run test:unit -- FlowExecutionMonitor
# 39/39 passed
```

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
