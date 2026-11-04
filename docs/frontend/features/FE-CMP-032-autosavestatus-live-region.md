# FE-CMP-032 -- AutoSaveStatus live region (A11Y-004)

**Status:** APPROVED
**Sprint:** SP-STUDIO-UI-FIX Dag 4
**Audit-bevinding:** A11Y-004

---

## Probleemstelling

AutoSaveStatus toonde de sla-status visueel (kleur + icoon) maar was niet bereikbaar voor screenreaders: er was geen `role="status"` en geen `aria-live` attribute. Statuswijzigingen werden niet door screenreaders aangekondigd.

## Implementatie

**Bestand:** `frontend/src/components/studio/AutoSaveStatus.tsx`

Alle drie de returnstatements (saving, error, saved) hebben nu identieke ARIA-attributen:

```tsx
<div
  data-testid="autosave-status"
  role="status"
  aria-live="polite"
  aria-atomic="true"
  className="..."
>
```

- `role="status"`: semantisch live-region label
- `aria-live="polite"`: screenreader wacht op natural break voor aankondiging
- `aria-atomic="true"`: hele node wordt opnieuw aangekondigd bij wijziging (niet alleen delta)

## Trainingssamenvatting

**Actor:** Screenreader-gebruiker werkt aan een workflow in de Studio editor.

**Voorwaarde:** Studio is open; gebruiker heeft de editor gefocust; auto-save wordt getriggerd.

**Actie:** Na een wijziging sla de wizard automatisch op (2s debounce).

**Systeemreactie:** Screenreader kondigt op een natural break aan: "Opslaan..." en daarna "Opgeslagen om HH:MM".

**Succesrespons:** Gebruiker weet zonder visuele inspectie dat de workflow opgeslagen is.

**Foutrespons:** Bij sla-fout kondigt screenreader aan: "Opslaan mislukt".

**Uitzonderingen:** `aria-live="assertive"` (interrupt) is bewust NIET gebruikt -- sla-status is geen urgente melding.

---

## Tests

- `AutoSaveStatus.test.tsx > Accessibility: live region (A11Y-004)` -- 3 tests GROEN
