# FE-CMP-023: FirstUseWizard isPending en error props

**Sprint:** Studio UI Fix Dag 2
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

`FirstUseWizard` had geen feedback wanneer de `onComplete`-callback een asynchrone operatie
startte (bijv. API-aanroep). De submit-knop bleef klikbaar, chips bleven actief, en er was
geen foutmelding bij een mislukte aanroep (ERR-002).

## Implementatie

### `frontend/src/components/studio/FirstUseWizard.tsx`

Props interface uitgebreid:

```typescript
export interface FirstUseWizardProps {
  templates: TemplateItem[];
  onComplete: (prompt: string) => void;
  onSelectTemplate: (templateId: string) => void;
  isPending?: boolean;
  error?: string | null;
}
```

Wijzigingen in de render:

- Submit-knop: `disabled={!inputValue.trim() || isPending}` (OR met bestaande check)
- Voorbeeld-chips: `disabled={isPending}` toegevoegd zodat chips ook geblokkeerd zijn
- Laad-indicator: `<span role="status" aria-live="polite" data-testid="wizard-loading-indicator">`
  getoond wanneer `isPending === true`
- Foutmelding: `<p role="alert" data-testid="wizard-error-message">` getoond wanneer
  `error` een niet-lege string is

Beide nieuwe props zijn optioneel met default `false`/`null` -- bestaande callers
hoeven niet te worden aangepast.

## Tests

- `FirstUseWizard.test.tsx` -- ERR-002: 2 nieuwe tests GREEN
  - isPending true -> submit disabled, loading indicator zichtbaar
  - error prop -> foutmelding zichtbaar
- Bestaande 8 tests volledig GROEN (10/10 totaal)

## Trainingssamenvatting

### Flow 1: Wizard indienen -- laadstatus

- Actor: Gebruiker die de Studio voor het eerst opent
- Voorwaarde: Step 1 actief; gebruiker heeft tekst ingevoerd; parent-component roept onComplete aan en start een async operatie (isPending: true)
- Actie: Gebruiker klikt op "Maken" of een voorbeeld-chip
- Systeemreactie: Submit-knop en alle chips krijgen `disabled`; laad-indicator (`data-testid="wizard-loading-indicator"`) verschijnt
- Succesrespons: isPending terug naar false -> knop en chips weer klikbaar; wizard sluit
- Foutrespons: Zie Flow 2
- Uitzonderingen: isPending false (standaard) -> geen laad-indicator, gewoon gedrag

### Flow 2: Wizard indienen -- fout

- Actor: Gebruiker die de Studio voor het eerst opent
- Voorwaarde: onComplete heeft gefaald; parent-component geeft error string terug via error-prop
- Actie: Parent stelt error-prop in na mislukte aanroep
- Systeemreactie: Foutmelding (`data-testid="wizard-error-message"`, `role="alert"`) zichtbaar onder de submit-knop
- Succesrespons: n.v.t.
- Foutrespons: Foutmelding blijft zichtbaar totdat error-prop null wordt of gebruiker opnieuw indient
- Uitzonderingen: error null (standaard) -> geen foutmelding
