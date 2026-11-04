# 🎯 E2E Test Suite - SanskritiSetu Frontend

Deze uitgebreide Playwright test suite test **elke knop, button en functie** in de frontend.

## 📋 Inhoud

- **Smoke Tests** - Basis tests om te verifiëren dat alle pagina's laden
- **Navigatie Tests** - Sidebar, mobile nav, links, breadcrumbs
- **Formulier Tests** - Login, register, settings, company forms
- **Interactie Tests** - Knoppen, modals, dropdowns, zoeken
- **Workflow Tests** - Kritieke gebruikerspaden
- **Accessibility Tests** - Toetsenbord, ARIA, screen readers

## 🚀 Snel Starten

### 1. Prerequisites

```bash
# Installeer Playwright browsers
npx playwright install

# Zorg dat frontend draait
npm run dev

# Zorg dat backend draait
docker compose up backend
```

### 1b. Goedkeurder voor de HITL-tests

Goedkeuren is sinds 2026-10-09 een procesbevoegdheid (ADR-039): de beheerder mag HITL-tickets niet meer
beslissen. `tests/e2e/hitl/` logt daarom in als `loginAsGoedkeurder`. Maak die gebruiker lokaal aan:

```bash
python scripts/seed_tweede_gebruiker.py --rol goedkeurder
```

### 2. Alle tests draaien

```bash
# Complete test suite
npm run test:e2e:custom full

# Of met het standaard commando
npm run test:e2e
```

### 3. Specifieke test suites

```bash
# Alleen smoke tests (snel)
npm run test:e2e:custom smoke

# Alleen navigatie tests
npm run test:e2e:custom navigation

# Alleen formulieren
npm run test:e2e:custom forms

# Alleen workflows
npm run test:e2e:custom workflows

# Alleen accessibility
npm run test:e2e:custom accessibility
```

### 4. Debug modes

```bash
# Met zichtbare browser
npm run test:e2e:custom headed

# Debug mode met breakpoints
npm run test:e2e:custom debug

# UI mode
npm run test:e2e:custom ui
```

## 🗓️ Test Commandos

| Commando | Beschrijving |
|----------|--------------|
| `npm run test:e2e` | Alle E2E tests |
| `npm run test:e2e:headed` | Tests met zichtbare browser |
| `npm run test:e2e:debug` | Debug mode |
| `npm run test:e2e:smoke` | Alleen smoke tests |
| `npm run test:e2e:ui` | UI mode voor interactief testen |
| `npm run test:e2e:report` | Toon HTML rapport |
| `npm run test:e2e:custom <name>` | Specifieke test suite |

## 📁 Test Structuur

```
tests/e2e/
├── helpers/
│   ├── auth.ts              # Authenticatie helpers
│   └── pageTester.ts        # Test utilities
├── smoke/
│   ├── all-pages.spec.ts    # Alle pagina's laden test
│   └── accessibility.spec.ts # Accessibility tests
├── interactions/
│   ├── navigation.spec.ts   # Navigatie tests
│   └── forms.spec.ts        # Formulier tests
├── workflows/
│   └── critical-paths.spec.ts # Kritieke workflows
├── run-all-tests.ts        # Test runner script
└── README.md              # Deze file
```

## 📊 Wat wordt getest?

### ✅ Smoke Tests
- [x] Alle pagina's laden zonder errors
- [x] Geen 404 errors
- [x] Geen React error boundaries
- [x] Authenticatie redirect werkt
- [x] 404 pagina toont correct

### 🔗 Navigatie Tests
- [x] Sidebar links werken
- [x] Mobile navigation
- [x] Settings tabs
- [x] Company sub-navigatie
- [x] Breadcrumbs
- [x] Actieve link highlighting

### 📝 Formulier Tests
- [x] Login formulier
- [x] Register formulier
- [x] Validatie errors
- [x] Settings formulieren
- [x] Company creation
- [x] Goal creation
- [x] Search & filter

### 🚀 Workflow Tests
- [x] Login → Dashboard → Logout flow
- [x] Dashboard widgets
- [x] Workflow builder
- [x] CVA chat
- [x] Company layer
- [x] Settings management
- [x] Error handling

### ♿ Accessibility Tests
- [x] Keyboard navigatie
- [x] Tab volgorde
- [x] ARIA labels
- [x] Alt teksten
- [x] Heading structuur
- [x] Focus management
- [x] Screen reader support

## 📸 Screenshots

Screenshots worden automatisch gemaakt:
- Bij falende tests
- Van elke pagina tijdens smoke tests
- Van responsive design
- Van errors

Locatie: `test-results/`

## 📊 Rapporten

### HTML Rapport
```bash
npm run test:e2e:custom full
npm run test:e2e:custom report
```

### CI/CD
```bash
# Voor CI omgevingen
npm run test:e2e -- --reporter=junit
```

## 🔧 Troubleshooting

### Tests falen met "browser not found"
```bash
npx playwright install
```

### Frontend niet bereikbaar
```bash
# Zorg dat frontend draait op http://localhost:5174
npm run dev
```

### Backend niet bereikbaar
```bash
# Zorg dat backend draait
docker compose up backend
```

### Timeouts
Pas timeouts aan in `playwright.config.ts`:
```typescript
timeout: 60000, // 60 seconden
```

## 📝 Nieuw Test Toevoegen

### 1. Maak een nieuwe test file
```bash
touch tests/e2e/interactions/my-feature.spec.ts
```

### 2. Basis template
```typescript
import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../helpers/auth';

test.describe('My Feature', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('my test case', async ({ page }) => {
    await page.goto('/my-feature');

    // Test code hier
    await expect(page.locator('text=Expected')).toBeVisible();
  });
});
```

### 3. Run de test
```bash
npx playwright test tests/e2e/interactions/my-feature.spec.ts
```

## 📔 Best Practices

1. **Gebruik data-testid attributen** voor betrouwbare selectors
2. **Gebruik de auth helpers** voor authenticatie
3. **Maak screenshots** bij belangrijke stappen
4. **Test zowel happy path als error cases**
5. **Test responsive design**
6. **Voeg accessibility tests toe**

## 🆘 Belangrijke Test Data

### Test Gebruikers
```typescript
const TEST_USERS = {
  admin: {
    email: 'admin@sanskritisetu.org',
    password: 'Admin123!',
  },
  user: {
    email: 'user@sanskritisetu.org',
    password: 'User123!',
  },
};
```

### Belangrijke Routes
Alle routes zijn gedefinieerd in:
- `tests/e2e/smoke/all-pages.spec.ts`

## 🚀 CI/CD Integratie

### GitHub Actions
```yaml
- name: Run E2E Tests
  run: |
    npm ci
    npx playwright install
    npm run test:e2e
```

### Docker
```bash
# Run tests in container
docker run --rm -v $(pwd):/app -w /app mcr.microsoft.com/playwright npm run test:e2e
```

## 🎨 Visual Regression Testing

```bash
# Update baseline screenshots
npm run test:e2e -- --update-snapshots

# Run visual tests
npm run test:e2e -- --project=chromium
```

## 📍 Contact

Voor vragen over de E2E tests, zie:
- [Playwright Docs](https://playwright.dev/)
- `tests/e2e/helpers/auth.ts` - Authenticatie helpers
- `tests/e2e/helpers/pageTester.ts` - Test utilities
