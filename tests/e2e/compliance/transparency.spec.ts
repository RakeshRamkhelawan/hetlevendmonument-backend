/**
 * AI Transparency Compliance E2E Tests
 *
 * Tests for EU AI Act compliance features:
 * - AI transparency banners on agent output
 * - Compliance dashboard accessibility
 * - Model information display
 * - Risk level indicators
 */

import { test, expect } from '@playwright/test';

test.describe('AI Transparency Compliance', () => {
  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto('/login');
    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'testpassword');
    await page.click('[data-testid="login-button"]');
    await page.waitForURL('/dashboard');
  });

  test('AI transparency banner visible on agents page', async ({ page }) => {
    // Navigate to agents page
    await page.goto('/agents');

    // Verify AI transparency banner is visible
    await expect(
      page.locator('text=AI-gegenereerd').first()
    ).toBeVisible({ timeout: 5000 });

    // Verify banner contains agent name
    await expect(page.locator('text=Agent Registry')).toBeVisible();
  });

  test('compliance dashboard is accessible', async ({ page }) => {
    // Navigate to compliance dashboard
    await page.goto('/compliance');

    // Verify page title
    await expect(page.getByText('AI Compliance Dashboard')).toBeVisible();

    // Verify tabs are present
    await expect(page.getByRole('button', { name: /AI Systems/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Transparency Log/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Risk Classification/i })).toBeVisible();
  });

  test('compliance dashboard shows AI systems', async ({ page }) => {
    await page.goto('/compliance');

    // Wait for systems tab content
    await page.waitForSelector('text=GPT-4o', { timeout: 5000 });

    // Verify model information is displayed
    await expect(page.getByText('OpenAI')).toBeVisible();
    await expect(page.getByText('Claude 3.5 Sonnet')).toBeVisible();
  });

  test('risk levels are displayed correctly', async ({ page }) => {
    await page.goto('/compliance');

    // Check for risk badges
    const riskBadges = page.locator('.AIActRiskBadge, [data-testid*="risk"]').first();
    await expect(riskBadges).toBeVisible();
  });

  test('transparency log shows AI usage records', async ({ page }) => {
    await page.goto('/compliance');

    // Click on Transparency Log tab
    await page.getByRole('button', { name: /Transparency Log/i }).click();

    // Verify log entries are displayed
    await expect(page.getByText('HR Assistant')).toBeVisible();
    await expect(page.getByText('Finance Agent')).toBeVisible();

    // Verify timestamps are present
    await expect(page.locator('text=/\\d{1,2}:\\d{2}/').first()).toBeVisible();
  });

  test('risk classification information is accessible', async ({ page }) => {
    await page.goto('/compliance');

    // Click on Risk Classification tab
    await page.getByRole('button', { name: /Risk Classification/i }).click();

    // Verify risk levels are explained
    await expect(page.getByText('Minimal Risk')).toBeVisible();
    await expect(page.getByText('Limited Risk')).toBeVisible();
    await expect(page.getByText('High Risk')).toBeVisible();
    await expect(page.getByText('Unacceptable Risk')).toBeVisible();
  });

  test('export report button is available', async ({ page }) => {
    await page.goto('/compliance');

    // Verify export button exists
    const exportButton = page.getByRole('button', { name: /Export Report/i });
    await expect(exportButton).toBeVisible();
    await expect(exportButton).toBeEnabled();
  });
});

test.describe('AI Transparency Banner', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'testpassword');
    await page.click('[data-testid="login-button"]');
    await page.waitForURL('/dashboard');
  });

  test('banner shows correct information structure', async ({ page }) => {
    await page.goto('/agents');

    // Verify banner structure
    const banner = page.locator('[role="note"]').first();
    await expect(banner).toBeVisible();

    // Check for AI indicator
    await expect(banner.locator('text=AI')).toBeVisible();

    // Check for model information
    await expect(page.locator('text=Model:').first()).toBeVisible();
  });

  test('compact banner mode works', async ({ page }) => {
    await page.goto('/compliance');

    // Navigate to transparency log for compact banners
    await page.getByRole('button', { name: /Transparency Log/i }).click();

    // Verify compact AI indicators are present
    const compactBadges = page.locator('text=AI').filter({ has: page.locator('..') });
    await expect(compactBadges.first()).toBeVisible();
  });
});
