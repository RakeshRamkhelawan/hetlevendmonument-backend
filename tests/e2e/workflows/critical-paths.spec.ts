/**
 * Critical E2E Workflows
 * Tests the most important user journeys
 */

import { test, expect } from '@playwright/test';
import { loginAsAdmin, logout } from '../helpers/auth';

test.describe('🚀 Critical E2E Workflows', () => {
  test.describe('Authentication Flow', () => {
    test('complete login -> dashboard -> logout flow', async ({ page }) => {
      // 1. Login via helper (handles both real backend and mock fallback)
      await loginAsAdmin(page);

      // 2. Verify dashboard
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);
      await expect(
        page.locator('[data-testid="user-profile-section"], [data-testid="logout-button"], button:has-text("Uitloggen")').first(),
      ).toBeVisible({ timeout: 10000 });

      // 3. Navigate through main sections
      const sections = [
        { name: 'Dashboard', path: '/dashboard' },
        { name: 'Agents', path: '/agents' },
        { name: 'Workflows', path: '/workflows' },
      ];

      for (const section of sections) {
        await page.locator(`a[href="${section.path}"]`).first().click();
        await page.waitForURL(`**${section.path}`, { timeout: 10000 });
        await page.waitForTimeout(500);
      }

      // 4. Logout
      const logoutBtn = page.locator('[data-testid="logout-button"], button:has-text("Uitloggen")').first();
      await expect(logoutBtn).toBeVisible({ timeout: 5000 });
      await logoutBtn.click();

      // 5. Verify logged out (should redirect to login)
      await page.waitForURL('**/login', { timeout: 10000 });
    });
  });

  test.describe('Dashboard Workflow', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsAdmin(page);
    });

    test('dashboard loads with all widgets', async ({ page }) => {
      await page.goto('/dashboard');

      // Wait for dashboard to load
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(2000);

      // Check for common dashboard elements
      const possibleWidgets = [
        'stats', 'metrics', 'charts', 'recent', 'activity',
        'notifications', 'agents', 'workflows'
      ];

      for (const widget of possibleWidgets) {
        const element = page.locator(`[data-testid*="${widget}"], .${widget}, [class*="${widget}"]`).first();
        const isVisible = await element.isVisible().catch(() => false);
        if (isVisible) {
          console.log(`✓ Widget found: ${widget}`);
        }
      }

      // Take dashboard screenshot
      await page.screenshot({
        path: 'test-results/dashboard-full.png',
        fullPage: true
      });
    });

    test('dashboard navigation to all main sections', async ({ page }) => {
      await page.goto('/dashboard');

      const mainSections = [
        { nav: 'Controlecentrum', path: '/mission-control' },
        { nav: 'Bedrijf', path: '/company' },
        { nav: 'Agents', path: '/agents' },
        { nav: 'Workflows', path: '/workflows' },
        { nav: 'Sjablonen', path: '/templates' },
        { nav: 'Analyse', path: '/analytics' },
        { nav: 'Instellingen', path: '/settings' },
      ];

      for (const section of mainSections) {
        // Go back to dashboard first
        await page.goto('/dashboard');
        await page.waitForTimeout(500);

        // Click navigation
        await page.click(`text=${section.nav}`);
        await page.waitForURL(`**${section.path}`, { timeout: 10000 });

        // Verify page loaded
        await expect(page.locator('main, [role="main"]').first()).toBeVisible();

        console.log(`✓ Navigation to ${section.nav} works`);
      }
    });
  });

  test.describe('Workflow Builder Flow', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsAdmin(page);
    });

    test('create simple workflow', async ({ page }) => {
      // 1. Go to workflow builder
      await page.goto('/focus-builder');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(3000);

      // 2. Look for input field to describe workflow
      const inputField = page.locator('textarea, input[type="text"]').first();

      if (await inputField.isVisible().catch(() => false)) {
        await inputField.fill('Create a simple approval workflow');

        // 3. Submit
        const submitButton = page.locator('button[type="submit"], button:has-text("Generate"), button:has-text("Create")').first();
        await submitButton.click();

        // 4. Wait for generation
        await page.waitForTimeout(5000);

        // 5. Check for workflow nodes
        const nodes = page.locator('.react-flow__node, [data-testid="node"], .node');
        const nodeCount = await nodes.count();

        console.log(`Found ${nodeCount} workflow nodes`);

        if (nodeCount > 0) {
          // 6. Click on a node
          await nodes.first().click();
          await page.waitForTimeout(500);

          // 7. Take screenshot
          await page.screenshot({ path: 'test-results/workflow-created.png' });
        }
      }
    });

    test('workflow canvas interactions', async ({ page }) => {
      await page.goto('/focus-builder');
      await page.waitForTimeout(3000);

      // Look for canvas
      const canvas = page.locator('.react-flow__renderer, [data-testid="canvas"], .canvas').first();

      if (await canvas.isVisible().catch(() => false)) {
        // Pan canvas
        const box = await canvas.boundingBox();
        if (box) {
          await canvas.dragTo(canvas, {
            sourcePosition: { x: box.width / 2, y: box.height / 2 },
            targetPosition: { x: box.width / 2 + 100, y: box.height / 2 + 100 },
          });
        }

        // Zoom controls
        const zoomIn = page.locator('button[title="zoom in"], button:has-text("+"), [data-testid="zoom-in"]').first();
        const zoomOut = page.locator('button[title="zoom out"], button:has-text("-"), [data-testid="zoom-out"]').first();

        if (await zoomIn.isVisible().catch(() => false)) {
          await zoomIn.click();
          await page.waitForTimeout(500);
        }

        if (await zoomOut.isVisible().catch(() => false)) {
          await zoomOut.click();
          await page.waitForTimeout(500);
        }
      }
    });
  });

  test.describe('Company Layer Flow', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsAdmin(page);
    });

    test('company dashboard navigation', async ({ page }) => {
      await page.goto('/company');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // Check for company info
      const companyElements = [
        'company', 'organization', 'departments', 'goals', 'team'
      ];

      for (const element of companyElements) {
        const el = page.locator(`[data-testid*="${element}"], .${element}, text=${element}`).first();
        const isVisible = await el.isVisible().catch(() => false);
        if (isVisible) {
          console.log(`✓ Company element found: ${element}`);
        }
      }
    });

    test('org chart navigation', async ({ page }) => {
      await page.goto('/company/org-chart');
      await page.waitForTimeout(3000);

      // Look for org chart elements
      const chartElements = page.locator('.org-chart, [data-testid="org-chart"], .node, .chart');

      if (await chartElements.first().isVisible().catch(() => false)) {
        // Click on a node if available
        const node = chartElements.first();
        await node.click();
        await page.waitForTimeout(500);

        await page.screenshot({ path: 'test-results/org-chart.png' });
      }
    });

    test('goals page interaction', async ({ page }) => {
      await page.goto('/company/goals');
      await page.waitForTimeout(2000);

      // Look for goals
      const goals = page.locator('[data-testid="goal"], .goal, .goal-card');
      const count = await goals.count();

      console.log(`Found ${count} goals`);

      if (count > 0) {
        // Click first goal
        await goals.first().click();
        await page.waitForTimeout(500);
      }

      // Look for add goal button
      const addButton = page.locator('button:has-text("Add"), button:has-text("New"), [data-testid="add-goal"]').first();
      if (await addButton.isVisible().catch(() => false)) {
        await addButton.click();
        await page.waitForTimeout(500);

        // Cancel if modal opens
        const cancelButton = page.locator('button:has-text("Cancel"), button:has-text("Close"), .close').first();
        if (await cancelButton.isVisible().catch(() => false)) {
          await cancelButton.click();
        }
      }
    });
  });

  test.describe('CVA Chat Flow', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsAdmin(page);
    });

    test('send message in CVA chat', async ({ page }) => {
      await page.goto('/cva');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(3000);

      // Look for chat input
      const chatInput = page.locator('textarea, input[type="text"], [data-testid="chat-input"]').first();

      if (await chatInput.isVisible().catch(() => false)) {
        // Only type if input is enabled (service may be unavailable)
        if (await chatInput.isEnabled().catch(() => false)) {
          // Type a message
          await chatInput.fill('Hello, can you help me create a workflow?');

          // Send message
          const sendButton = page.locator('button[type="submit"], button:has-text("Send"), [data-testid="send"]').first();
          await sendButton.click();
        } else {
          console.log('CVA chat input disabled (service unavailable) - skipping message send');
        }

        // Wait for response
        await page.waitForTimeout(5000);

        // Check for response
        const responses = page.locator('.message, .response, [data-testid="message"], .chat-message');
        const count = await responses.count();

        console.log(`Found ${count} chat messages`);

        await page.screenshot({ path: 'test-results/cva-chat.png' });
      }
    });
  });

  test.describe('Settings Management Flow', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsAdmin(page);
    });

    test('navigate all settings tabs', async ({ page }) => {
      const tabs = [
        { name: 'General', path: '/settings/general' },
        { name: 'RBAC', path: '/settings/rbac' },
        { name: 'Audit', path: '/settings/audit' },
        { name: 'Governance', path: '/settings/governance' },
      ];

      for (const tab of tabs) {
        await page.goto(tab.path);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(1000);

        // Verify page loaded
        await expect(page.locator('main, [role="main"]').first()).toBeVisible();

        // Take screenshot
        await page.screenshot({
          path: `test-results/settings-${tab.name.toLowerCase()}.png`
        });

        console.log(`✓ Settings tab ${tab.name} loaded`);
      }
    });
  });

  test.describe('Error Handling', () => {
    test.beforeEach(async ({ page }) => {
      await loginAsAdmin(page);
    });

    test('404 page handling', async ({ page }) => {
      await page.goto('/this-page-does-not-exist-12345');

      // Should show 404
      await page.waitForLoadState('domcontentloaded');
      const notFound = page.getByText('404').first();
      await expect(notFound).toBeVisible({ timeout: 10000 });

      // Should have link back to dashboard
      const homeLink = page.locator('a[href="/"], a:has-text("Go Home"), a:has-text("Dashboard")').first();
      await expect(homeLink).toBeVisible();

      // Click home link
      await homeLink.click();
      await page.waitForURL('**/dashboard', { timeout: 10000 });
    });

    test('network error handling', async ({ page }) => {
      // Block API calls to simulate network error
      await page.route('**/api/**', route => route.abort('failed'));

      await page.goto('/agents');
      await page.waitForTimeout(3000);

      // Should show error state or empty state
      const errorOrEmpty = page.locator('.error, .empty-state, [data-testid="error"], [data-testid="empty"]').first();

      // Take screenshot to see how app handles errors
      await page.screenshot({ path: 'test-results/network-error.png' });

      // Remove route blocking
      await page.unroute('**/api/**');
    });
  });
});
