import { test, expect } from '@playwright/test';

import { confirmFourEyesExplanationIfOpen } from '../helpers/auth';
import { E2E_ADMIN } from '../helpers/credentials';

/**
 * Browser verification for P0 dashboard auth fixes.
 *
 * Scenario:
 * 1. Log in via the real backend on /login.
 * 2. Verify cookies are set.
 * 3. Clear localStorage / sessionStorage (simulating a fresh browser context
 *    where the persisted Zustand state is gone but HttpOnly cookies remain).
 * 4. Navigate directly to /dashboard.
 * 5. Verify the dashboard loads instead of redirecting back to /login.
 */

const DEMO_EMAIL = E2E_ADMIN.email;
const DEMO_PASSWORD = E2E_ADMIN.password;

test('cookie session restore keeps user on dashboard after fresh context', async ({ page, context }) => {
  // 1. Log in via real backend
  await page.goto('/login');
  await page.locator('input[id="email"]').fill(DEMO_EMAIL);
  await page.locator('input[id="password"]').fill(DEMO_PASSWORD);
  await page.getByTestId('login-button').click();

  // Wait for redirect away from /login; a still-open four-eyes explanation is confirmed first.
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 60000 });
  await confirmFourEyesExplanationIfOpen(page);
  await page.waitForURL('**/dashboard', { timeout: 60000 });
  await expect(page.locator('text=Dashboard').first()).toBeVisible();

  // 2. Verify cookies exist (HttpOnly cookies are visible to the browser API)
  const cookies = await context.cookies();
  const accessToken = cookies.find((c) => c.name === 'access_token');
  const refreshToken = cookies.find((c) => c.name === 'refresh_token');
  expect(accessToken).toBeDefined();
  expect(refreshToken).toBeDefined();

  // 3. Simulate fresh browser context: clear all storage but keep cookies.
  await page.evaluate(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  // 4. Hard reload to /dashboard — this triggers restoreSession() with no persisted user.
  await page.goto('/dashboard');

  // 5. We should end up on dashboard, not be redirected back to /login.
  await expect(page).toHaveURL(/.*\/dashboard/);
  await expect(page.locator('text=Dashboard').first()).toBeVisible();
});
