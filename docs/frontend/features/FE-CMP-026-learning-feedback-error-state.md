# FE-CMP-026: Learning feedback error state

**Sprint:** Studio UI Fix Dag 3
**Status:** APPROVED
**Datum:** 2026-06-27

## Probleem

ERR-004: `useWorkflowLearning` exposeerde de feedback mutation error niet. De
`LearningSuggestionsPanel` renderde geen foutmelding wanneer een feedback-submit
mislukte. Gebruikers kregen geen terugkoppeling bij netwerk- of serverfouten.

## Implementatie

### `frontend/src/lib/studio/useWorkflowLearning.ts`

Interface uitgebreid:

```typescript
export interface UseWorkflowLearningReturn {
  qualityScore: number;
  rules: LearningRule[];
  isLoading: boolean;
  error: unknown | null;
  feedbackError: Error | null;
  feedbackPending: boolean;
  submitFeedback: (feedback: FeedbackRequest) => Promise<unknown>;
}
```

Return object bijgewerkt:

```typescript
return {
  ...
  feedbackError: feedbackMutation.error ?? null,
  feedbackPending: feedbackMutation.isPending,
  submitFeedback: feedbackMutation.mutateAsync,
};
```

### `frontend/src/components/studio/LearningSuggestionsPanel.tsx`

Props interface uitgebreid met `feedbackError?: unknown`. JSX toegevoegd
na de rules-lijst:

```tsx
{
  !!feedbackError && (
    <p
      role="alert"
      data-testid="feedback-error-msg"
      className="mt-2 text-xs text-red-400"
    >
      {copy.studio.learning.feedbackError}
    </p>
  );
}
```

Boolean-cast `!!feedbackError` gebruikt omdat `feedbackError: unknown` niet
direct als `ReactNode` rendert.

### `frontend/src/lib/copy.ts`

Sleutel `feedbackError` toegevoegd aan `copy.studio.learning`:

```typescript
feedbackError: 'Feedback verzenden mislukt. Probeer opnieuw.',
```

## Tests

- `useWorkflowLearning.dag3.test.ts`: 3/3 GROEN
  - feedbackError geexposeerd na mislukte submit (waitFor TanStack async flush)
  - feedbackError null bij geen submit
  - feedbackPending true tijdens pending submit
- `LearningSuggestionsPanel.dag3.test.tsx`: 13/13 GROEN
  - feedback-error-msg getoond bij feedbackError prop
  - feedback-error-msg niet aanwezig bij geen feedbackError

## Trainingssamenvatting

### Flow 1: Feedback verzenden mislukt

- Actor: Gebruiker in de LearningSuggestionsPanel
- Voorwaarde: Rules zijn geladen; gebruiker klikt thumbs-up of thumbs-down
- Actie: submitFeedback wordt aangeroepen; server geeft fout terug
- Systeemreactie: feedbackMutation.error gevuld; feedbackError geexposeerd via hook;
  panel toont role="alert" foutmelding met tekst uit copy.studio.learning.feedbackError
- Succesrespons: n.v.t.
- Foutrespons: rode foutmelding zichtbaar; debounce-timer gereset zodat gebruiker opnieuw kan klikken
- Uitzonderingen: Geen

### Flow 2: Feedback verzenden slaagt

- Actor: Gebruiker in de LearningSuggestionsPanel
- Voorwaarde: Rules zijn geladen; gebruiker klikt thumbs-up of thumbs-down
- Actie: submitFeedback wordt aangeroepen; server antwoordt 200
- Systeemreactie: feedbackError blijft null; geen foutmelding getoond; debounce-timer loopt 2s
- Succesrespons: Geen foutmelding; knop tijdelijk disabled (debounce)
- Foutrespons: n.v.t.
- Uitzonderingen: Geen
