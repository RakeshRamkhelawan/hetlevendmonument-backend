# FE-ARCH-001: Geen hardcoded WebSocket-URL preventietest

**Sprint:** AUDIT-SINGLE-TENANT-DB01 S7
**Datum:** 2026-07-02
**ADR:** ADR-035 D2

## Probleem

AUDIT-ST-01 (S1) verwijderde 5 hardcoded `wss://api.sanskritisetu.org`
fallbacks uit productie-bronbestanden -- deze breken single-tenant
deployments op een ander domein. Er was geen regressie-guard tegen het
opnieuw introduceren van een hardcoded productie-WS-URL.

## Oplossing

`frontend/src/__tests__/architecture/no-hardcoded-ws-urls.test.ts` scant alle
`src/**/*.{ts,tsx}` bronbestanden (excl. `__tests__`) op de literal string
`wss://api.sanskritisetu.org` via `glob` + `readFileSync`.

## Test bewijs

```
npm run test:unit -- src/__tests__/architecture/no-hardcoded-ws-urls.test.ts
1 passed
```

Huidige staat van `frontend/src/`: 0 violations in productiecode (enige
matches zijn binnen de preventietest zelf, ter documentatie van het patroon).

## Trainingssamenvatting

- Actor: ontwikkelaar die een frontend TypeScript/TSX bronbestand wijzigt
- Voorwaarde: de wijziging introduceert de literal string `wss://api.sanskritisetu.org`
- Actie: wijziging opslaan en `npm run test:unit -- src/__tests__/architecture/no-hardcoded-ws-urls.test.ts` uitvoeren
- Systeemreactie: de preventietest scant alle `src/**/*.{ts,tsx}` bestanden (exclusief tests en node_modules) op de literal string en verzamelt violations
- Succesrespons: geen hardcoded URL gevonden; test rapporteert `1 passed` en het violations-array is leeg
- Foutrespons: test faalt en toont de bestandspaden die de hardcoded URL bevatten
- Uitzonderingen: bestanden onder `__tests__`, `*.spec.*` en `node_modules` worden genegeerd; matches binnen de test zelf zijn toegestaan ter documentatie van het patroon

## Reviewers

code-reviewer: GO.
quality-reviewer: GO (glob-dependency correct resolveerbaar via
frontend/node_modules + package-lock.json, geen secrets, ASCII-only).
