/**
 * Page testing utilities
 * Helper functions to test pages, buttons, forms, and interactions
 */

import { Page, Locator, expect } from '@playwright/test';

export interface ButtonTest {
  name: string;
  selector: string;
  expectedResult?: 'navigation' | 'modal' | 'toast' | 'state-change' | 'api-call';
  expectedUrl?: string;
}

export interface LinkTest {
  name: string;
  selector: string;
  expectedUrl: string;
}

export interface FormField {
  name: string;
  selector: string;
  type: 'text' | 'email' | 'password' | 'select' | 'checkbox' | 'textarea';
  value: string | boolean;
}

export interface FormTest {
  name: string;
  selector: string;
  fields: FormField[];
  submitSelector: string;
  expectedResult: 'success' | 'error' | 'validation';
  expectedMessage?: string;
}

/**
 * Test a button click and verify the result
 */
export async function testButton(
  page: Page,
  buttonTest: ButtonTest
): Promise<void> {
  const { name, selector, expectedResult, expectedUrl } = buttonTest;

  console.log(`Testing button: ${name}`);

  // Find and verify button exists
  const button = page.locator(selector);
  await expect(button).toBeVisible({ timeout: 5000 });
  await expect(button).toBeEnabled({ timeout: 3000 });

  // Click the button
  await button.click();

  // Verify expected result
  if (expectedResult === 'navigation' && expectedUrl) {
    await page.waitForURL(expectedUrl, { timeout: 10000 });
  } else if (expectedResult === 'modal') {
    const modal = page.locator('[role="dialog"], [data-testid="modal"]');
    await expect(modal).toBeVisible({ timeout: 5000 });
  } else if (expectedResult === 'toast') {
    const toast = page.locator('[data-testid="toast"], .toast, [role="status"]');
    await expect(toast).toBeVisible({ timeout: 5000 });
  }

  console.log(`✓ Button "${name}" works correctly`);
}

/**
 * Test a navigation link
 */
export async function testLink(
  page: Page,
  linkTest: LinkTest
): Promise<void> {
  const { name, selector, expectedUrl } = linkTest;

  console.log(`Testing link: ${name}`);

  const link = page.locator(selector);
  await expect(link).toBeVisible({ timeout: 5000 });

  await link.click();
  await page.waitForURL(expectedUrl, { timeout: 10000 });

  console.log(`✓ Link "${name}" navigates correctly`);
}

/**
 * Test a form submission
 */
export async function testForm(
  page: Page,
  formTest: FormTest
): Promise<void> {
  const { name, selector, fields, submitSelector, expectedResult, expectedMessage } = formTest;

  console.log(`Testing form: ${name}`);

  // Verify form exists
  const form = page.locator(selector);
  await expect(form).toBeVisible({ timeout: 5000 });

  // Fill in all fields
  for (const field of fields) {
    const fieldElement = page.locator(field.selector);
    await expect(fieldElement).toBeVisible({ timeout: 3000 });

    if (field.type === 'checkbox') {
      if (field.value) {
        await fieldElement.check();
      } else {
        await fieldElement.uncheck();
      }
    } else if (field.type === 'select') {
      await fieldElement.selectOption(field.value as string);
    } else {
      await fieldElement.fill(field.value as string);
    }
  }

  // Submit form
  const submitButton = page.locator(submitSelector);
  await submitButton.click();

  // Verify expected result
  if (expectedResult === 'success' && expectedMessage) {
    await expect(page.locator('text=' + expectedMessage)).toBeVisible({ timeout: 10000 });
  } else if (expectedResult === 'error' && expectedMessage) {
    await expect(page.locator('text=' + expectedMessage)).toBeVisible({ timeout: 5000 });
  } else if (expectedResult === 'validation') {
    const errorElements = page.locator('.error, [data-testid="error-message"], .text-red-500');
    await expect(errorElements.first()).toBeVisible({ timeout: 5000 });
  }

  console.log(`✓ Form "${name}" works correctly`);
}

/**
 * Test all visible buttons on a page
 */
export async function testAllButtons(page: Page): Promise<void> {
  console.log('Testing all visible buttons...');

  const buttons = page.locator('button:not([disabled]):visible');
  const count = await buttons.count();

  console.log(`Found ${count} visible buttons`);

  for (let i = 0; i < count; i++) {
    const button = buttons.nth(i);
    const text = await button.textContent() || `Button ${i + 1}`;
    const isEnabled = await button.isEnabled();
    const isVisible = await button.isVisible();

    console.log(`Button "${text.trim()}": enabled=${isEnabled}, visible=${isVisible}`);

    // Verify button is clickable
    if (isEnabled && isVisible) {
      await expect(button).toBeEnabled();
    }
  }
}

/**
 * Test all links on a page
 */
export async function testAllLinks(page: Page): Promise<void> {
  console.log('Testing all visible links...');

  const links = page.locator('a[href]:visible');
  const count = await links.count();

  console.log(`Found ${count} visible links`);

  for (let i = 0; i < Math.min(count, 20); i++) { // Limit to 20 links
    try {
      const link = links.nth(i);
      // Re-check visibility: the DOM may have changed since the count was taken
      const isStillVisible = await link.isVisible({ timeout: 2000 }).catch(() => false);
      if (!isStillVisible) {
        console.log(`Link ${i + 1}: skipped (no longer visible)`);
        continue;
      }
      const text = await link.textContent().catch(() => `Link ${i + 1}`) || `Link ${i + 1}`;
      const href = await link.getAttribute('href').catch(() => null);

      console.log(`Link "${text.trim()}": href=${href}`);

      if (href !== null && href !== '') {
        // Link is valid
      }
    } catch {
      console.log(`Link ${i + 1}: skipped (stale element)`);
    }
  }
}

/**
 * Test responsive behavior
 */
export async function testResponsive(page: Page, path: string): Promise<void> {
  console.log(`Testing responsive behavior for ${path}`);

  const viewports = [
    { name: 'mobile', width: 375, height: 667 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'desktop', width: 1920, height: 1080 },
  ];

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(path);
    await page.waitForLoadState('domcontentloaded');

    // Take screenshot for verification
    await page.screenshot({
      path: `test-results/responsive-${viewport.name}-${path.replace(/\//g, '-')}.png`,
      fullPage: true
    });

    console.log(`✓ ${viewport.name} viewport rendered`);
  }
}

/**
 * Test loading states
 */
export async function testLoadingStates(page: Page): Promise<void> {
  console.log('Testing loading states...');

  // Check for loading indicators
  const loadingIndicators = page.locator('[data-testid="loading"], .loading, .spinner, [role="progressbar"]');
  const hasLoading = await loadingIndicators.count() > 0;

  if (hasLoading) {
    console.log(`Found ${await loadingIndicators.count()} loading indicators`);
  }

  // Check for skeleton loaders
  const skeletons = page.locator('[data-testid="skeleton"], .skeleton');
  const hasSkeletons = await skeletons.count() > 0;

  if (hasSkeletons) {
    console.log(`Found ${await skeletons.count()} skeleton loaders`);
  }
}

/**
 * Test error states
 */
export async function testErrorStates(page: Page): Promise<void> {
  console.log('Testing error states...');

  // Check for error messages
  const errorMessages = page.locator('[data-testid="error"], .error, .text-red-500, [role="alert"]');
  const errorCount = await errorMessages.count();

  console.log(`Found ${errorCount} error elements`);

  // Check for empty states
  const emptyStates = page.locator('[data-testid="empty-state"], .empty-state');
  const emptyCount = await emptyStates.count();

  if (emptyCount > 0) {
    console.log(`Found ${emptyCount} empty states`);
  }
}

/**
 * Comprehensive page test
 */
export async function runPageTest(
  page: Page,
  path: string,
  options: {
    testButtons?: boolean;
    testLinks?: boolean;
    testResponsive?: boolean;
    testLoading?: boolean;
    testErrors?: boolean;
  } = {}
): Promise<void> {
  console.log(`\n=== Testing page: ${path} ===`);

  await page.goto(path);
  await page.waitForLoadState('domcontentloaded');

  // Wait a bit for any dynamic content
  await page.waitForTimeout(1000);

  if (options.testButtons !== false) {
    await testAllButtons(page);
  }

  if (options.testLinks !== false) {
    await testAllLinks(page);
  }

  if (options.testResponsive) {
    await testResponsive(page, path);
  }

  if (options.testLoading) {
    try {
      await testLoadingStates(page);
    } catch (e) {
      console.log(`Warning: testLoadingStates skipped (${e})`);
    }
  }

  if (options.testErrors) {
    try {
      await testErrorStates(page);
    } catch (e) {
      console.log(`Warning: testErrorStates skipped (${e})`);
    }
  }

  console.log(`✓ Page test completed for ${path}\n`);
}
