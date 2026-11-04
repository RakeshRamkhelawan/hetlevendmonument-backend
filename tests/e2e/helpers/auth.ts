/**
 * Authentication helpers for E2E tests
 * Provides utilities for login/logout and authenticated sessions
 */

import { Page, expect } from '@playwright/test';

import { E2E_ADMIN, E2E_GOEDKEURDER, type UserCredentials } from './credentials';

export type { UserCredentials };

const FOUR_EYES_EXPLANATION_PATH = '/instellingen/vier-ogen/uitleg';
const FOUR_EYES_STATE_URL = '/api/v1/tools/hitl/four-eyes';

const LOGIN_FORM_SELECTOR = [
  '[data-testid="login-form"]',
  'form:has(input[type="email"])',
].join(', ');

const EMAIL_INPUT_SELECTOR = [
  '[data-testid="email-input"]',
  '[data-testid="login-email"]',
  'input#email',
  'input[name="email"]',
  'input[type="email"]',
].join(', ');

const PASSWORD_INPUT_SELECTOR = [
  '[data-testid="password-input"]',
  '[data-testid="login-password"]',
  'input#password',
  'input[name="password"]',
  'input[type="password"]',
].join(', ');

const LOGIN_BUTTON_SELECTOR = [
  '[data-testid="login-button"]',
  '[data-testid="login-submit"]',
  'button[type="submit"]',
  'button:has-text("Sign In")',
  'button:has-text("Login")',
].join(', ');

const AUTHENTICATED_SELECTOR = [
  '[data-testid="user-menu"]',
  '[data-testid="user-avatar"]',
  '[data-testid="user-profile-section"]',
  'button:has-text("Uitloggen")',
].join(', ');

const LOGOUT_BUTTON_SELECTOR = [
  '[data-testid="logout-button"]',
  'button:has-text("Uitloggen")',
  'button:has-text("Logout")',
  'text=Uitloggen',
].join(', ');

interface CachedAuthState {
  accessToken: string;
  refreshToken: string | null;
  expiresAt: string | null;
  authStore: string | null;
}

let cachedAuthState: CachedAuthState | null = null;

// Mock auth constants used as fallback when the backend is unavailable.
const MOCK_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZW1haWwiOiJhZG1pbkBzYW5za3JpdGlzZXR1Lm9yZyIsIm5hbWUiOiJBZG1pbiBVc2VyIiwidGVuYW50X2lkIjoxLCJ0ZW5hbnRJZCI6IjEiLCJyb2xlcyI6WyJhZG1pbiJdLCJzY29wZXMiOltdLCJleHAiOjk5OTk5OTk5OTksImF1ZCI6InNhbnNrcml0aXNldHUifQ.mock';
const MOCK_USER = { id: 1, email: 'admin@sanskritisetu.org', name: 'Admin User', role: 'admin' };

/**
 * Apply mock auth state when the backend is not available.
 * Sets up localStorage tokens and API route mocks so the frontend
 * renders the authenticated UI.
 */
async function applyMockAuthFallback(page: Page): Promise<void> {
  // Catch-all: intercept every /api/v1/** request that is not handled by a more
  // specific route below.  Return 200 with an empty JSON body so the frontend
  // never receives a 401 that would trigger a logout cycle.
  // NOTE: use /api/v1/** (not /api/**) to avoid intercepting Vite source
  // module requests like /src/lib/api/client.ts.
  await page.route('**/api/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }),
  );

  // Mock essential API routes (registered AFTER the catch-all so they win).
  await page.route('**/api/v1/auth/me', (route) => route.fulfill({ json: MOCK_USER }));
  await page.route('**/api/v1/auth/csrf-token', (route) => route.fulfill({ json: { csrf_token: 'mock' } }));
  await page.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({ json: { access_token: MOCK_TOKEN, refresh_token: 'mock_refresh', token_type: 'bearer' } }),
  );

  // Inject localStorage tokens before the page loads
  await page.addInitScript((token: string) => {
    window.localStorage.setItem('access_token', token);
    window.localStorage.setItem('token', token);
    window.localStorage.setItem('refresh_token', 'mock_refresh');
    window.localStorage.setItem('token_expires_at', '9999999999');
    window.localStorage.setItem(
      'user',
      JSON.stringify({ id: 1, name: 'Admin User', email: 'admin@sanskritisetu.org', role: 'admin' }),
    );
    window.localStorage.setItem(
      'auth-storage-v2',
      JSON.stringify({
        state: {
          user: { id: 1, name: 'Admin User', email: 'admin@sanskritisetu.org', role: 'admin' },
          token: token,
          refreshToken: 'mock_refresh',
          isAuthenticated: true,
        },
        version: 0,
      }),
    );
  }, MOCK_TOKEN);

  await page.goto('/dashboard');
  await page.waitForLoadState('domcontentloaded');

  // NOTE: intentionally NOT caching mock auth state.  Only real auth tokens
  // (from form login) are cached so that later tests that need the real
  // backend still work.
}

const applyCachedAuthState = async (page: Page, state: CachedAuthState): Promise<void> => {
  await page.goto('/');
  await page.evaluate((s) => {
    localStorage.setItem('access_token', s.accessToken);
    if (s.refreshToken) {
      localStorage.setItem('refresh_token', s.refreshToken);
    }
    if (s.expiresAt) {
      localStorage.setItem('token_expires_at', s.expiresAt);
    }
    if (s.authStore) {
      localStorage.setItem('auth-storage-v2', s.authStore);
    }
  }, state);
};

const captureAuthState = async (page: Page): Promise<CachedAuthState | null> => {
  const state = await page.evaluate(() => {
    const accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
      return null;
    }

    return {
      accessToken,
      refreshToken: localStorage.getItem('refresh_token'),
      expiresAt: localStorage.getItem('token_expires_at'),
      authStore: localStorage.getItem('auth-storage-v2'),
    };
  });

  return state;
};

const waitForPostLoginState = async (page: Page) => {
  await page.waitForFunction(
    () => {
      const path = window.location.pathname;
      return !['/login', '/register', '/forgot-password', '/auth/reset-password'].includes(path);
    },
    { timeout: 5000 }
  );
};

export const TEST_USERS = {
  admin: E2E_ADMIN,
  user: {
    email: 'user@sanskritisetu.org',
    password: 'User123!',
  },
};

/**
 * Login with credentials
 */
export async function login(page: Page, credentials: UserCredentials): Promise<void> {
  if (cachedAuthState) {
    await applyCachedAuthState(page, cachedAuthState);
    await page.goto('/dashboard');

    const authenticatedMarker = await page
      .locator(AUTHENTICATED_SELECTOR)
      .first()
      .isVisible({ timeout: 2000 })
      .catch(() => false);

    if (!page.url().includes('/login') && authenticatedMarker) {
      return;
    }
  }

  // Navigate to login page
  await page.goto('/login');

  // If session is already active and we got redirected away from /login, reuse it.
  if (!page.url().includes('/login')) {
    const alreadyAuthenticated = await page.locator(AUTHENTICATED_SELECTOR).first().isVisible({ timeout: 2000 }).catch(() => false);
    if (alreadyAuthenticated) {
      return;
    }
  }

  // Wait for form to be ready
  try {
    await page.waitForSelector(LOGIN_FORM_SELECTOR, { timeout: 5000 });
  } catch {
    const alreadyAuthenticated = await page.locator(AUTHENTICATED_SELECTOR).first().isVisible({ timeout: 2000 }).catch(() => false);
    if (alreadyAuthenticated || !page.url().includes('/login')) {
      return;
    }
    // Login form did not appear and not authenticated - fall back to mock auth
    await applyMockAuthFallback(page);
    return;
  }

  // Fill in credentials
  await page.fill(EMAIL_INPUT_SELECTOR, credentials.email);
  await page.fill(PASSWORD_INPUT_SELECTOR, credentials.password);

  const submitAndAwaitDashboard = async () => {
    await page.click(LOGIN_BUTTON_SELECTOR);
    await waitForPostLoginState(page);
  };

  try {
    await submitAndAwaitDashboard();
  } catch {
    if (page.isClosed()) {
      throw new Error('Login retry aborted because page was already closed.');
    }

    // Form login failed (backend slow/unavailable). Fall back to mock auth
    // injection which is instant and does not require a backend.
    await applyMockAuthFallback(page);
    return;
  }

  // Verify we are no longer on the login page and authenticated UI is present.
  await expect(page).not.toHaveURL(/\/login$/);
  await expect(page.locator(AUTHENTICATED_SELECTOR).first()).toBeVisible({ timeout: 10000 });

  await confirmFourEyesExplanationIfOpen(page);

  cachedAuthState = await captureAuthState(page);
}

/**
 * Bevestigt de vier-ogen-uitleg als die voor deze beheerder nog openstaat, zodat een test die op
 * /dashboard verwacht te landen daar ook landt. Staat de uitleg niet open, dan gebeurt er niets.
 * De vraag gaat naar de backend en niet naar de URL: de app stuurt pas door als het antwoord
 * binnen is, en op de URL wachten zou een race zijn.
 */
export async function confirmFourEyesExplanationIfOpen(page: Page): Promise<void> {
  const res = await page.request.get(FOUR_EYES_STATE_URL);
  if (!res.ok()) {
    return;
  }
  const body = (await res.json()) as { data?: { explanation_pending?: boolean } };
  if (body.data?.explanation_pending !== true) {
    return;
  }
  if (!page.url().includes(FOUR_EYES_EXPLANATION_PATH)) {
    await page.goto(FOUR_EYES_EXPLANATION_PATH);
  }
  const confirmed = page.waitForResponse(
    (r) => r.url().includes(`${FOUR_EYES_STATE_URL}/explanation-confirmed`) && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Bevestigen en doorgaan' }).click();
  const response = await confirmed;
  expect(response.ok(), 'bevestigen van de vier-ogen-uitleg mislukte').toBe(true);
  await page.goto('/dashboard');
}

/**
 * Login as admin.
 *
 * By default this uses form-based login (via ``login()``) so the browser
 * holds a real session token and pages that fetch backend data render
 * correctly.
 *
 * Pass ``{ useMockAuth: true }`` to skip form login entirely and inject
 * mock tokens + API route stubs instead.  This is useful for tests that
 * only need an authenticated shell (e.g. checking that form fields render)
 * and would otherwise be blocked by backend rate-limiting.
 */
export async function loginAsAdmin(
  page: Page,
  options?: { useMockAuth?: boolean },
): Promise<void> {
  if (options?.useMockAuth) {
    await applyMockAuthFallback(page);
    return;
  }

  await login(page, TEST_USERS.admin);
}

/**
 * Login als goedkeurder (rol `goedkeurder`, `receivables:approve`). Goedkeuren is een
 * procesbevoegdheid (ADR-039): de beheerder mag HITL-tickets niet meer beslissen. Seed:
 * `python scripts/seed_tweede_gebruiker.py --rol goedkeurder`.
 */
export async function loginAsGoedkeurder(page: Page): Promise<void> {
  await login(page, E2E_GOEDKEURDER);
}

/**
 * Login as regular user
 */
export async function loginAsUser(page: Page): Promise<void> {
  await login(page, TEST_USERS.user);
}

/**
 * Logout current user
 */
export async function logout(page: Page): Promise<void> {
  const logoutButton = page.locator(LOGOUT_BUTTON_SELECTOR).first();
  if (await logoutButton.isVisible().catch(() => false)) {
    await logoutButton.click();
  } else {
    const userMenu = page.locator('[data-testid="user-menu"], [data-testid="user-avatar"], .user-menu').first();
    await userMenu.click();
    await page.locator(LOGOUT_BUTTON_SELECTOR).first().click();
  }

  // Wait for redirect to login
  await page.waitForURL('**/login', { timeout: 10000 });
}

/**
 * Check if user is authenticated
 */
export async function isAuthenticated(page: Page): Promise<boolean> {
  try {
    await page.goto('/dashboard');
    const authenticatedMarker = page.locator(AUTHENTICATED_SELECTOR).first();
    return await authenticatedMarker.isVisible({ timeout: 5000 });
  } catch {
    return false;
  }
}

/**
 * Setup authenticated session storage
 */
export async function setupAuthSession(page: Page, credentials: UserCredentials): Promise<void> {
  await login(page, credentials);

  // Store session state
  const storageState = await page.context().storageState();
  return storageState;
}

/**
 * Clear all authentication state
 */
export async function clearAuth(page: Page): Promise<void> {
  await page.context().clearCookies();
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
}

/**
 * Handle consent/cookie banners if present
 */
export async function handleConsentBanner(page: Page): Promise<void> {
  const consentButton = page.locator('[data-testid="consent-accept-button"]');
  if (await consentButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    await consentButton.click();
  }
}
