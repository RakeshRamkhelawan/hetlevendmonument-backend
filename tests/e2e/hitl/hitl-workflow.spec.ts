/**
 * HITL Workflow E2E Tests
 *
 * Tests for Human-in-the-Loop functionality:
 * - Viewing pending HITL actions
 * - Approving actions
 * - Rejecting actions with feedback
 * - Viewing history
 * - Real-time updates via WebSocket
 */

import { test, expect } from '@playwright/test';

import { loginAsGoedkeurder } from '../helpers/auth';

test.describe('HITL Workflow', () => {
  test.beforeEach(async ({ page }) => {
    // Login and navigate to HITL page
    await loginAsGoedkeurder(page);

    // Navigate to HITL page
    await page.goto('/hitl');
    await page.waitForSelector('[data-testid="hitl-queue"]', { timeout: 10000 });
  });

  test('user can view pending HITL actions', async ({ page }) => {
    // Check page title
    await expect(page.getByText('Goedkeuringen')).toBeVisible();

    // Check stats are displayed
    await expect(page.getByText('Wachtende aanvragen').first()).toBeVisible();
    await expect(page.getByText('Vandaag goedgekeurd')).toBeVisible();
    await expect(page.getByText('Vandaag afgekeurd')).toBeVisible();

    // Check filter tabs
    await expect(page.getByRole('button', { name: /^wachtend$/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^goedgekeurd$/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^afgekeurd$/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /^alles$/i })).toBeVisible();
  });

  test('user can approve a HITL action', async ({ page }) => {
    // Wait for tickets to load
    await page.waitForSelector('[data-testid="hitl-action-card"]', {
      timeout: 5000,
    });

    // Click approve on first pending ticket
    const approveButton = page
      .locator('[data-testid="hitl-action-card"]')
      .first()
      .getByRole('button', { name: /goedkeuren/i });

    await approveButton.click();

    // Verify ticket shows approved status
    await expect(
      page.locator('[data-testid="hitl-action-card"]').first().getByText(/goedgekeurd/i)
    ).toBeVisible({ timeout: 5000 });
  });

  test('user can reject a HITL action with feedback', async ({ page }) => {
    // Wait for tickets to load
    await page.waitForSelector('[data-testid="hitl-action-card"]', {
      timeout: 5000,
    });

    // Click reject on first pending ticket
    const rejectButton = page
      .locator('[data-testid="hitl-action-card"]')
      .first()
      .getByRole('button', { name: /afkeuren/i });

    await rejectButton.click();

    // Fill rejection reason
    const reasonInput = page.locator('textarea[placeholder*="rejection"]').first();
    await reasonInput.fill('This action is not safe for production environment');

    // Confirm rejection
    const confirmButton = page.getByRole('button', { name: /afkeuren bevestigen/i });
    await confirmButton.click();

    // Verify ticket shows rejected status
    await expect(
      page.locator('[data-testid="hitl-action-card"]').first().getByText(/afgekeurd/i)
    ).toBeVisible({ timeout: 5000 });
  });

  test('user can view HITL history', async ({ page }) => {
    // Click on History tab
    await page.getByRole('button', { name: /geschiedenis/i }).click();

    // Wait for history to load
    await page.waitForSelector('[data-testid="hitl-history"]', { timeout: 5000 });

    // Check history table headers
    await expect(page.getByText('Status')).toBeVisible();
    await expect(page.getByText('Actie')).toBeVisible();
    await expect(page.getByText('Besluit door')).toBeVisible();
  });

  test('WebSocket shows live connection status', async ({ page }) => {
    // Check connection status indicator
    await expect(page.getByText(/verbonden|geen verbinding/i)).toBeVisible();

    // Verify live indicator when connected
    const liveIndicator = page.locator('text=Verbonden');
    if (await liveIndicator.isVisible().catch(() => false)) {
      await expect(liveIndicator).toHaveCSS('color', /rgb\(74, 222, 128\)/);
    }
  });

  test('user can refresh HITL data', async ({ page }) => {
    // Click refresh button
    const refreshButton = page.getByRole('button', { name: /verversen/i });
    await refreshButton.click();

    // Verify loading state
    await expect(page.getByRole('button', { name: /verversen/i })).toBeDisabled();

    // Wait for refresh to complete
    await page.waitForLoadState('networkidle');
  });
});

test.describe('HITL Rejection Validation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsGoedkeurder(page);
    await page.goto('/hitl');
  });

  test('rejection requires minimum 10 characters', async ({ page }) => {
    await page.waitForSelector('[data-testid="hitl-action-card"]', {
      timeout: 5000,
    });

    // Click reject
    await page
      .locator('[data-testid="hitl-action-card"]')
      .first()
      .getByRole('button', { name: /afkeuren/i })
      .click();

    // Try to submit with short reason
    const reasonInput = page.locator('textarea').first();
    await reasonInput.fill('short');

    // Confirm button should be disabled
    const confirmButton = page.getByRole('button', { name: /afkeuren bevestigen/i });
    await expect(confirmButton).toBeDisabled();

    // Add longer reason
    await reasonInput.fill('This is a valid rejection reason with enough detail');

    // Confirm button should now be enabled
    await expect(confirmButton).toBeEnabled();
  });
});

test.describe('HITL voor de goedkeurder (ADR-039 acceptatieherstel)', () => {
  test('een goedkeurder ziet de wachtrij en geen "Admin role required"', async ({ page }) => {
    await loginAsGoedkeurder(page);
    await page.goto('/hitl');
    await page.waitForSelector('[data-testid="hitl-queue"]', { timeout: 10000 });

    // De audit is beheer (403 voor een goedkeurder); die fout mag de wachtrij niet wegdrukken.
    await expect(page.getByText(/Admin role required/)).toHaveCount(0);
  });

  test('de goedkeurder haalt de audit niet op', async ({ page }) => {
    const auditAanroepen: string[] = [];
    page.on('request', (verzoek) => {
      if (verzoek.url().includes('/api/v1/tools/hitl/audit')) auditAanroepen.push(verzoek.url());
    });

    await loginAsGoedkeurder(page);
    await page.goto('/hitl');
    await page.waitForSelector('[data-testid="hitl-queue"]', { timeout: 10000 });
    await page.waitForLoadState('networkidle');

    expect(auditAanroepen).toEqual([]);
  });
});
