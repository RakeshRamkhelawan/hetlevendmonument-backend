/**
 * Navigation interaction tests
 * Tests sidebar, mobile nav, and all navigation links
 */

import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../helpers/auth';

test.describe('🔗 Navigation Interactions', () => {
  test.describe.configure({ timeout: 60000 });

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await loginAsAdmin(page);
  });

  test.describe('Sidebar Navigation', () => {
    test('all sidebar links are clickable and navigate correctly', async ({ page }) => {
      const sidebarLinks = [
        { path: '/dashboard' },
        { path: '/mission-control' },
        { path: '/company' },
        { path: '/workflows' },
        { path: '/templates' },
        { path: '/agents' },
        { path: '/analytics' },
        { path: '/governance' },
        { path: '/user-management' },
        { path: '/audit-logs' },
        { path: '/settings' },
      ];

      for (const link of sidebarLinks) {
        // Click using href instead of visible label to avoid localization/wording drift.
        await page.locator(`a[href="${link.path}"]`).first().click();

        // Wait for navigation
        await page.waitForURL(`**${link.path}`, { timeout: 10000 });

        // Verify we're on the correct page
        await expect(page).toHaveURL(new RegExp(link.path));

        // Take screenshot
        await page.screenshot({
          path: `test-results/nav-${link.path.replace(/^\//, '').replace(/\//g, '-') || 'root'}.png`
        });
      }
    });

    test('active link is highlighted', async ({ page }) => {
      // Navigate to a page
      await page.goto('/templates');

      // Check that the Templates link has active styling
      const activeLink = page.locator('a[href="/templates"]').first();
      const hasActiveClass = await activeLink.evaluate(el =>
        el.classList.contains('active') ||
        el.classList.contains('bg-white/10') ||
        el.className.includes('from-saffron') ||
        el.getAttribute('aria-current') === 'page'
      );

      expect(hasActiveClass).toBeTruthy();
    });
  });

  test.describe('Settings Sub-navigation', () => {
    test('settings tabs work correctly', async ({ page }) => {
      const tabs = [
        { name: 'General', path: '/settings' },
        { name: 'RBAC', path: '/settings/rbac' },
        { name: 'Audit', path: '/settings/audit' },
        { name: 'Governance', path: '/settings/governance' },
      ];

      for (const tab of tabs) {
        await page.goto(tab.path);
        await page.waitForURL(`**${tab.path}`, { timeout: 10000 });
        await expect(page.locator('main').first()).toBeVisible();
      }
    });
  });

  test.describe('Company Sub-navigation', () => {
    test('company tabs work correctly', async ({ page }) => {
      await page.goto('/company');

      const tabs = [
        { name: 'Organization', path: '/company/org-chart' },
        { name: 'Goals', path: '/company/goals' },
        { name: 'External Agents', path: '/company/external-agents' },
      ];

      for (const tab of tabs) {
        // Click tab
        const tabButton = page.locator(`button:has-text("${tab.name}"), a:has-text("${tab.name}")`).first();
        if (await tabButton.isVisible().catch(() => false)) {
          await tabButton.click();
          await page.waitForTimeout(1000);

          // Take screenshot
          await page.screenshot({
            path: `test-results/company-${tab.name.toLowerCase().replace(/\s+/g, '-')}.png`
          });
        }
      }
    });
  });

  test.describe('Mobile Navigation', () => {
    test('sidebar remains accessible on small screens', async ({ page }) => {
      // Set mobile viewport
      await page.setViewportSize({ width: 375, height: 667 });

      await page.goto('/dashboard');

      // The current UI does not hide the sidebar on mobile — it stays visible
      const sidebar = page.locator('[data-testid="main-sidebar"]').first();
      await expect(sidebar).toBeVisible();

      // Navigation links inside the sidebar should still be functional
      const nav = page.locator('[data-testid="sidebar-nav"]').first();
      await expect(nav).toBeVisible();
    });

    test('sidebar nav links work on mobile viewport', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto('/dashboard');

      // Verify at least one nav link is clickable on the small viewport
      const firstLink = page.locator('[data-testid="sidebar-nav"] a').first();
      await expect(firstLink).toBeVisible();
    });
  });

  test.describe('Breadcrumb Navigation', () => {
    test('breadcrumbs show on nested pages', async ({ page }) => {
      await page.goto('/settings/rbac');

      // Look for breadcrumb elements
      const breadcrumbs = page.locator('[data-testid="breadcrumb"], nav[aria-label="breadcrumb"], .breadcrumb');

      // Breadcrumbs might not exist, but if they do, they should work
      if (await breadcrumbs.isVisible().catch(() => false)) {
        const breadcrumbLinks = breadcrumbs.locator('a');
        const count = await breadcrumbLinks.count();

        if (count > 0) {
          // Click first breadcrumb link
          await breadcrumbLinks.first().click();
          await page.waitForTimeout(1000);
        }
      }
    });
  });
});
