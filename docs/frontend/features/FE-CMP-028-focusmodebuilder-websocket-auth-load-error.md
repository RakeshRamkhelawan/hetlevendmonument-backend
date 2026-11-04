# FE-CMP-028: FocusModeBuilder WebSocket auth en load error

**Sprint:** Studio UI Fix Dag 3
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

Twee bevindingen in `FocusModeBuilder.tsx` (dead code -- vervangen door
`FocusModeBuilderEnhanced.tsx`):

- **SEC-005**: JWT-token als WebSocket subprotocol. RFC 6455 stuurt subprotocols
  als klare tekst in de HTTP Upgrade-header. Een query-parameter met URL-encoding
  is de veiligere aanpak voor dead code dat alsnog actief kan worden.
- **ERR-007**: `loadWorkflow`-fouten werden genegeerd in het catch-blok. De component
  toonde een lege staat zonder foutmelding.

## Implementatie

### `frontend/src/components/workflow/FocusModeBuilder.tsx`

**SEC-005 fix** -- WebSocket query-parameter in plaats van subprotocol:

```typescript
// Voor: ws.current = new WebSocket(wsEndpoint, ['access_token', accessToken]);
const wsWithToken = `${wsEndpoint}?token=${encodeURIComponent(accessToken)}`;
ws.current = new WebSocket(wsWithToken);
```

**ERR-007 fix** -- loadError state toegevoegd:

```typescript
const [loadError, setLoadError] = React.useState<string | null>(null);
// In init(): setLoadError(null) aan het begin
// In catch van loadWorkflow: setLoadError('Workflow laden mislukt. Probeer opnieuw.');
```

JSX na de `isInitialized`-guard:

```tsx
if (loadError) {
  return (
    <div
      role="alert"
      data-testid="load-error-msg"
      className="flex items-center justify-center h-full text-red-400 text-sm p-4"
    >
      {loadError}
    </div>
  );
}
```

**Deprecated comment** bovenaan component toegevoegd:

```typescript
// NOTE: FocusModeBuilder is deprecated -- use FocusModeBuilderEnhanced instead.
// Dead code in production: not imported by any active route.
```

**Emoji-fix** (lijn 166): `content: \`[emoji] ${data.message || 'Thinking...'}\``vervangen
door`content: data.message || 'Thinking...'` (NOOIT-lijst: geen emoji in code/logs).

## Tests

- `FocusModeBuilder.dag3.test.tsx`: 2/2 GROEN
  - load-error-msg getoond bij mislukte loadWorkflow
  - load-error-msg niet aanwezig bij succesvolle loadWorkflow

## Trainingssamenvatting

### Flow 1: Workflow laden mislukt -- foutmelding getoond

- Actor: Gebruiker die FocusModeBuilder opent met een workflowId
- Voorwaarde: getFlow API-aanroep faalt (bijv. 404, 500)
- Actie: Component probeert workflow te laden via focusBuilderApi.getFlow
- Systeemreactie: catch-blok loopt; loadError gezet; component toont role="alert" div
- Succesrespons: n.v.t.
- Foutrespons: Foutmelding zichtbaar: "Workflow laden mislukt. Probeer opnieuw."
- Uitzonderingen: Bestand is dead code -- productiegebruikers zien FocusModeBuilderEnhanced

### Flow 2: WebSocket verbinding -- query-parameter auth

- Actor: Systeem (WebSocket initialisatie)
- Voorwaarde: accessToken beschikbaar via TokenStorage.getAccessToken
- Actie: WebSocket verbinding aangemaakt met token als query-parameter
- Systeemreactie: token geencodeeerd via encodeURIComponent; geen subprotocol gebruikt
- Succesrespons: WebSocket verbinding opgezet; token niet in Upgrade-header
- Foutrespons: n.v.t.
- Uitzonderingen: accessToken null -> verbinding zonder token (bestaand gedrag ongewijzigd)
