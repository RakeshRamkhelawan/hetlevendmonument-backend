/**
 * Smoke tests - Verify all pages load correctly
 * Tests every route to ensure no 404s or crashes
 */

import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../helpers/auth';
import { runPageTest } from '../helpers/pageTester';

// All protected routes that require authentication
const PROTECTED_ROUTES = [
  // Main navigation
  { path: '/dashboard', name: 'Dashboard' },
  { path: '/mission-control', name: 'Mission Control' },
  { path: '/company', name: 'Company' },
  { path: '/cva', name: 'CVA Chat' },
  { path: '/agents', name: 'Agents' },
  { path: '/workflows', name: 'Workflows' },
  { path: '/focus-builder', name: 'Workflow Builder' },
  { path: '/templates', name: 'Templates' },

  // AI Features
  { path: '/execution-monitor', name: 'Execution Monitor' },
  { path: '/rag-pipeline', name: 'RAG Pipeline' },
  { path: '/evaluation', name: 'Evaluation' },
  { path: '/meta-learning', name: 'Meta-Learning' },
  { path: '/tool-broker', name: 'Tool Broker' },
  { path: '/sandbox-logs', name: 'Sandbox Logs' },

  // System
  { path: '/analytics', name: 'Analytics' },
  { path: '/system-health', name: 'System Health' },
  { path: '/notifications', name: 'Notifications' },
  { path: '/governance', name: 'Governance' },

  // Admin
  { path: '/audit-logs', name: 'Audit Logs' },
  { path: '/user-management', name: 'User Management' },
  { path: '/settings', name: 'Settings' },

  // Settings sub-pages
  { path: '/settings/general', name: 'Settings - General' },
  { path: '/settings/rbac', name: 'Settings - RBAC' },
  { path: '/settings/audit', name: 'Settings - Audit' },
  { path: '/settings/governance', name: 'Settings - Governance' },

  // Company sub-pages
  { path: '/company/org-chart', name: 'Company - Org Chart' },
  { path: '/company/goals', name: 'Company - Goals' },
  { path: '/company/external-agents', name: 'Company - External Agents' },
  { path: '/board', name: 'Board' },
];

// Public routes
const PUBLIC_ROUTES = [
  { path: '/login', name: 'Login' },
  { path: '/register', name: 'Register' },
  { path: '/forgot-password', name: 'Forgot Password' },
];

test.describe('✅ Smoke Tests - All Pages Load', () => {

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
  });

  test.describe('Public Pages', () => {
    for (const route of PUBLIC_ROUTES) {
      test(`${route.name} loads without errors`, async ({ page }) => {
        await page.goto(route.path);
        await page.waitForLoadState('domcontentloaded');

        const errorBoundary = page.locator('[data-testid="error-boundary"], .error-boundary');
        await expect(errorBoundary).not.toBeVisible();

        const body = page.locator('body');
        await expect(body).not.toBeEmpty();

        await page.screenshot({
          path: `test-results/smoke-${route.name.toLowerCase().replace(/\s+/g, '-')}.png`,
          fullPage: true
        });
      });
    }
  });

  test.describe('Protected Pages', () => {
    // Pages with many interactive elements need extra time for runPageTest
    test.setTimeout(60000);

    test.beforeEach(async ({ page }) => {
      await loginAsAdmin(page);
    });

    for (const route of PROTECTED_ROUTES) {
      test(`${route.name} loads without errors`, async ({ page }) => {
        await page.goto(route.path);
        await page.waitForLoadState('domcontentloaded');
        await page.waitForTimeout(1000);

        const notFound = page.locator('text=404, text=Not Found, text=not found');
        await expect(notFound).not.toBeVisible({ timeout: 3000 });

        const errorBoundary = page.locator('[data-testid="error-boundary"], .error-boundary');
        await expect(errorBoundary).not.toBeVisible();

        // Verify some content rendered (main element, root div, or body content)
        const mainContent = page.locator('main, [role="main"], #root, body');
        await expect(mainContent.first()).toBeVisible();

        await runPageTest(page, route.path, {
          testButtons: true,
          testLinks: true,
          testLoading: true,
          testErrors: true,
        });

        await page.screenshot({
          path: `test-results/smoke-${route.name.toLowerCase().replace(/\s+/g, '-')}.png`,
          fullPage: true
        });
      });
    }
  });

  test.describe('Authentication Protection', () => {
    for (const route of PROTECTED_ROUTES.slice(0, 5)) {
      test(`${route.name} redirects to login when not authenticated`, async ({ page }) => {
        // Fresh browser context per test = empty localStorage = no auth tokens
        await page.goto(route.path);
        await page.waitForURL('**/login', { timeout: 10000 });
        await page.waitForLoadState('domcontentloaded');
        await page.waitForTimeout(500);
        await expect(page.locator('[data-testid="login-page"]').first()).toBeVisible({ timeout: 10000 });
      });
    }
  });

  test('404 page shows for unknown routes', async ({ page }) => {
    await page.goto('/this-route-does-not-exist-12345');
    await page.waitForLoadState('domcontentloaded');
    // Check for any of these 404 indicators
    const has404 = page.getByText('404').first();
    await expect(has404).toBeVisible({ timeout: 10000 });
  });
});
