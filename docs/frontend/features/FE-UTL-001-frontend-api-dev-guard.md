# FE-UTL-001: Frontend API Dev Guard

## Samenvatting

Voegt een runtime dev-guard toe in `publicClient.ts` die een `console.warn` toont wanneer `localhost:8110` direct wordt gebruikt in development mode. Dit helpt ontwikkelaars om de Vite proxy te gebruiken i.p.v. directe backend calls.

## Scope

- `frontend/src/lib/api/publicClient.ts`

## Wijzigingen

```typescript
if (import.meta.env.DEV && BASE_URL.includes('localhost:8110')) {
  console.warn('[DEV GUARD] Direct localhost:8110 detected. Using Vite proxy is recommended.');
}
```

## Tests

- `tests/unit/frontend/test_api_dev_guard.py` — 3 tests (guard present, normalize used in publicClient, normalize used in config/api)

## ADR Impact

- ADR-028 (Phase 2 Frontend): consistent API client gedrag

## Trainingssamenvatting

- Actor: frontend developer (development-mode)
- Voorwaarde: applicatie draait in development mode (`import.meta.env.DEV === true`)
- Actie: API client wordt geinitaliseerd met `VITE_API_URL` die `localhost:8110` bevat
- Systeemverwerking: dev-guard detecteert directe backend URL en toont `console.warn`
- Succesrespons: developer ziet waarschuwing en schakelt over naar Vite proxy
- Foutrespons: guard is passief (`console.warn`), blokkeert geen requests
- Uitzonderingen: guard actief ALLEEN in dev-mode; productie-builds tonen nooit waarschuwing

> Gebruik runtime guards in development om veelvoorkomende configuratie fouten te detecteren. Een `console.warn` is goedkoop en voorkomt dat ontwikkelaars uren debuggen op CORS/timeout problemen.
