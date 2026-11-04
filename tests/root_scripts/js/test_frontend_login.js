const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  try {
    console.log('\n═══════════════════════════════════════════════════');
    console.log('FRONTEND LOGIN TEST - Playwright');
    console.log('═══════════════════════════════════════════════════\n');

    // 1. Navigate to frontend
    console.log('📍 Navigating to localhost:5173...');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
    console.log('✓ Page loaded\n');

    // 2. Wait for login form
    console.log('🔍 Looking for login form...');
    await page.waitForSelector('input[type="email"]', { timeout: 10000 });
    console.log('✓ Login form found\n');

    // 3. Fill credentials
    console.log('📝 Entering credentials...');
    console.log('   Email: admin@sanskritisetu.org');
    console.log('   Password: admin123\n');

    await page.fill('input[type="email"]', 'admin@sanskritisetu.org');
    await page.fill('input[type="password"]', 'admin123');
    console.log('✓ Credentials entered\n');

    // 4. Submit form
    console.log('🚀 Submitting login form...');
    const submitButton = await page.$('button[type="submit"]');
    if (!submitButton) {
      // Try alternative selector
      await page.click('button:has-text("Login")');
    } else {
      await submitButton.click();
    }
    console.log('✓ Form submitted\n');

    // 5. Wait for redirect or dashboard
    console.log('⏳ Waiting for login response...');
    await page.waitForTimeout(2000);

    // Check if we're on dashboard or error
    const currentUrl = page.url();
    console.log(`📍 Current URL: ${currentUrl}\n`);

    // Check for error messages
    const errorMsg = await page.$('.error, [role="alert"]');
    if (errorMsg) {
      const text = await errorMsg.textContent();
      console.log(`❌ ERROR FOUND: ${text}\n`);
    }

    // Check for success (redirected away from login)
    if (!currentUrl.includes('login')) {
      console.log('✅ LOGIN SUCCESSFUL!\n');
      console.log('📊 Page title:', await page.title());

      // Wait a bit to see the page
      await page.waitForTimeout(3000);
    } else {
      console.log('⚠️  Still on login page\n');
      const pageContent = await page.content();
      if (pageContent.includes('invalid')) {
        console.log('❌ Invalid credentials error detected\n');
      }
    }

  } catch (error) {
    console.error('\n❌ TEST FAILED:', error.message);
  } finally {
    console.log('\n═══════════════════════════════════════════════════');
    console.log('Test complete - close browser window to exit');
    console.log('═══════════════════════════════════════════════════\n');
    // Keep browser open so you can see result
    // await browser.close();
  }
})();
