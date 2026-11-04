# Phase 2 Frontend — Guardrails

Niet-onderhandelbare regels. Gelden voor elke dag van elke sprint.
Afwijken is alleen toegestaan met expliciete schriftelijke toestemming van Rakesh.

---

## 1. TypeScript

| Regel | Reden |
| ----- | ----- |
| **Geen `any` types** — gebruik `unknown` + type guard of een expliciet type | `any` schakelt de type checker uit en maskeert runtime bugs |
| **Strict mode** — `"strict": true` in `tsconfig.json`, 0 fouten bij `npm run type-check` | Vangt undefined, null en type-mismatch fouten voor productie |
| **Import aliases** — altijd `@/*`, nooit diepe relatieve paden zoals `../../../` | Pad-rotting bij refactoring; alias geeft stabiele referenties |
| **Geen `@ts-ignore`** — los het onderliggende type-probleem op | Ignores worden niet gerapporteerd door CI; bugs blijven verborgen |
| **Geen type-assertions zonder bewijs** — `as X` alleen na een type guard of runtime check | Onveilige cast is equivalent aan `any` in dit deel van de code |

---

## 2. Frontend Architectuur

| Regel | Reden |
| ----- | ----- |
| **Alleen Tailwind CSS** voor styling — geen inline `style={{}}`, geen CSS modules buiten `globals.css` | Tailwind purge werkt alleen op classes; inline styles worden niet getree-shaken |
| **Geen hardcoded hex, rgb of hsl kleuren** buiten `tokens.ts` en `tailwind.config.ts` | Design system breekt bij themawijziging als kleuren verspreid zijn door de codebase |
| **Dark mode**: elke kleur-class vergezeld van `dark:` variant | Ontbrekende dark-variant geeft witte tekst op witte achtergrond in dark mode |
| **Radix UI** voor alle interactieve primitieven (Dialog, Collapsible, Tabs, Select, etc.) | Toegankelijkheid (ARIA, keyboard navigation) is out-of-the-box; opnieuw implementeren introduceert fouten |
| **Geen directe DOM-manipulatie** — geen `document.getElementById`, geen `innerHTML` | XSS-aanvalsvlak; werkt niet met React reconciliation |
| **XYFlow via `React.lazy()`** — altijd gesplitst, nooit top-level import | XYFlow is groot; eager import vergroot de initieel bundle met 200-300 KB |
| **Geen barrel-exports van zware modules** — tree-shaking werkt niet over barrel files | Vite kan in sommige gevallen geen tree-shaking doorvoeren over re-exports |

---

## 3. Toegangscontrole

| Regel | Reden |
| ----- | ----- |
| **`PermissionGate`** wrappen om alle UI-elementen die scope-beveiliging nodig hebben | Zichtbaarheid ≠ toegang; gate moet in de component zitten, niet alleen in de route |
| **`ClassificationWrapper`** gebruiken voor alle velden die `CONFIDENTIAL`, `RESTRICTED` of `SECRET` data tonen | PII moet geclassificeerd zijn voor GDPR-logging en DSAR-export |
| **`tenant_id` altijd uit JWT/middleware** — nooit uit request body, query param of localStorage | Cross-tenant aanval via client-controlled waarden (CLAUDE.md regel 6) |
| **Geen PII in `localStorage` of `sessionStorage`** — tokens zijn httpOnly cookies (server-beheerd) | LocalStorage is leesbaar via XSS; httpOnly cookies niet |
| **Geen debug endpoints zonder auth** in productie-builds | Unauthenticated endpoints zijn een DoS-vector |

---

## 4. Security

| Regel | Reden |
| ----- | ----- |
| **ASCII-only** in `.ts` en `.tsx` source code — geen emoji, geen speciale Unicode tekens | Encoding-fouten in Windows PowerShell, CI-logs en cross-platform workflows (CLAUDE.md regel 10) |
| **Geen hardcoded URLs, ports of API keys** — altijd via `import.meta.env.VITE_*` | Hardcoded waarden lekken productie-adressen in source code en git history |
| **CSS-injectie via tenant-theming** — valideer hex-waarden met `/^#[0-9A-Fa-f]{3,8}$/` voor `setProperty` | Ongefilterde CSS-waarden kunnen layout-aanvallen of data-exfiltratie mogelijk maken |
| **`fontFamily` validatie** — whitelist of strikte regex, nooit direct doorgeven | `font-family: expression(...)` was een historisch XSS-vector; moderne browsers beperken dit maar valideer toch |
| **Geen `dangerouslySetInnerHTML`** zonder expliciete sanitizatie + securityreview goedkeuring | Direct HTML-injectie is de primaire React XSS-vector |

---

## 5. React Hooks en Lifecycle

| Regel | Reden |
| ----- | ----- |
| **`useEffect` cleanup verplicht** voor alle timers, intervals en event listeners | React 18 StrictMode mount/unmount tweemaal in development; zonder cleanup dubbele requests en memory leaks |
| **`mountedRef` guard in WebSocket `onclose`** — check `mountedRef.current` voor reconnect | Reconnect na unmount veroorzaakt infinite reconnect loops buiten de React lifecycle |
| **Module-level promise-cache** voor hooks die data fetchen bij mount | Meerdere mounts (StrictMode, concurrent rendering) veroorzaken N parallelle requests voor dezelfde data |
| **Geen stale closures** — altijd `useCallback` of `useRef` voor callbacks in `useEffect` | Stale closure vangt verouderde state; debug is tijdrovend en niet vanzelfsprekend zichtbaar |
| **Cleanup-volgorde**: eerst `wsRef.current = null`, dan `close()` | Omgekeerde volgorde kan een dubbele `onclose` event triggeren |

---

## 6. Testing

| Regel | Reden |
| ----- | ----- |
| **Gebruik `npm run test:unit`** op Windows — nooit `npx vitest` direct | Zonder `cross-env NODE_OPTIONS` crasht de Vitest-worker met heap OOM op Windows |
| **`pytest --stepwise`** bij volledige backend-testruns | Stopt direct bij eerste faal; bespaart tijd bij grote suites |
| **Tests zijn geïsoleerd** — geen gedeelde module-level staat, geen afhankelijkheid van uitvoeringsvolgorde | Volgorde-afhankelijke tests falen willekeurig op CI |
| **Behavioral tests** — test wat de gebruiker ziet, niet dat een functie is aangeroepen | `expect(fn).toHaveBeenCalled` zonder argumentcontrole is geen behavioral test |
| **Radix Collapsible**: gebruik `.not.toBeVisible()`, niet `.not.toBeInTheDocument()` | Radix unmount niet — het kind krijgt `hidden` attribute maar blijft in de DOM |
| **Geen `.only()` of `.skip()`** in commits — mag alleen lokaal tijdelijk | `.only()` in CI betekent dat 99% van de tests wordt overgeslagen |

---

## 7. Documentatie en Traceerbaarheid

| Regel | Reden |
| ----- | ----- |
| **Elke dag die frontend-output oplevert vereist feature-specs** — zie `FEATURE_DOC_WORKFLOW.md` | Spec genereert testbare acceptatiecriteria en LLM-trainingsdata |
| **ID-REGISTRY.md bijhouden** na elke sprint dag | Voorkomt ID-collisions over sprints heen |
| **Geen verwijzingen naar Co-Pilot of ADR-027** in Phase 2 sprint-documenten | Phase 2 is frontend-only; Co-Pilot context hoort niet in de visuele redesign sprint |
| **ADR-028 niet wijzigen** zonder expliciete schriftelijke toestemming van Rakesh | ADR-028 is de architecturale grondslag van alle 35 werkdagen |

---

## 8. GO / NO-GO Criteria per Laag

Een sprint dag is pas klaar als:

- Laag A: alle 4 subagent-reviews groen (code, quality, security, accessibility)
- Laag B: alle 3 dag-reviews groen (performance, UX/UI, design system)
- Laag C (dag 5): alle 3 sprint-reviews groen (compatibility, privacy, release readiness) + GO-oordeel

Een feature-spec is pas klaar als:

- Review-oordeel is APPROVED of APPROVED WITH MINOR GAPS
- Geen CRITICAL of HIGH open issues

Zie `REVIEW_GATES.md` voor volledige subagent prompts.

---

*Eigenaar: Rakesh Ramkhelawan | ADR: ADR-028 | Laatste update: 2026-05-25*
