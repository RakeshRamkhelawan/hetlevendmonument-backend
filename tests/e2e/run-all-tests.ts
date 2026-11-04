#!/usr/bin/env node
/**
 * E2E Test Runner
 * Run all frontend tests with different configurations
 */

import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

interface TestConfig {
  name: string;
  command: string;
  description: string;
}

const TEST_CONFIGS: TestConfig[] = [
  {
    name: 'smoke',
    command: 'npx playwright test tests/e2e/smoke --reporter=list',
    description: 'Quick smoke tests - verify all pages load',
  },
  {
    name: 'navigation',
    command: 'npx playwright test tests/e2e/interactions/navigation.spec.ts --reporter=list',
    description: 'Navigation tests - sidebar, mobile nav, links',
  },
  {
    name: 'forms',
    command: 'npx playwright test tests/e2e/interactions/forms.spec.ts --reporter=list',
    description: 'Form tests - login, register, settings forms',
  },
  {
    name: 'workflows',
    command: 'npx playwright test tests/e2e/workflows --reporter=list',
    description: 'Critical E2E workflows',
  },
  {
    name: 'accessibility',
    command: 'npx playwright test tests/e2e/smoke/accessibility.spec.ts --reporter=list',
    description: 'Accessibility tests - keyboard, ARIA, screen readers',
  },
  {
    name: 'full',
    command: 'npx playwright test tests/e2e --reporter=html',
    description: 'Full test suite - all tests',
  },
  {
    name: 'headed',
    command: 'npx playwright test tests/e2e --headed --reporter=list',
    description: 'Run tests with visible browser (for debugging)',
  },
  {
    name: 'debug',
    command: 'npx playwright test tests/e2e --debug',
    description: 'Run tests in debug mode',
  },
  {
    name: 'ui',
    command: 'npx playwright test --ui',
    description: 'Run tests with UI mode',
  },
  {
    name: 'report',
    command: 'npx playwright show-report',
    description: 'Show HTML test report',
  },
];

function printUsage() {
  console.log(`
╔═════════════════════════════════════════════════════╗
║     SanskritiSetu E2E Test Runner     ║
╠═════════════════════════════════════════════════════╣

Usage: npm run test:e2e:custom <command>

Commands:
`);

  TEST_CONFIGS.forEach((config) => {
    console.log(`  [36m${config.name.padEnd(15)}[0m ${config.description}`);
  });

  console.log(`
Examples:
  npm run test:e2e:custom smoke       # Quick smoke tests
  npm run test:e2e:custom full        # Full test suite
  npm run test:e2e:custom headed      # Run with visible browser
  npm run test:e2e:custom debug       # Debug mode
  npm run test:e2e:custom report      # Show test report

Prerequisites:
  - Frontend dev server must be running (npm run dev)
  - Backend must be running
  - Playwright browsers must be installed (npx playwright install)

Notes:
  - Test results are saved in test-results/
  - Screenshots are taken on failure
  - HTML report is generated after full test run
`);
}

function runTests(configName: string) {
  const config = TEST_CONFIGS.find((c) => c.name === configName);

  if (!config) {
    console.error(`\n[31mError: Unknown command "${configName}"\u001b[0m\n`);
    printUsage();
    process.exit(1);
  }

  console.log(`
╔═════════════════════════════════════════════════════╗
║  Running: ${config.name.padEnd(30)}║
║  ${config.description.padEnd(37)}║
╠═════════════════════════════════════════════════════╣
`);

  // Ensure test-results directory exists
  if (!fs.existsSync('test-results')) {
    fs.mkdirSync('test-results', { recursive: true });
  }

  try {
    execSync(config.command, { stdio: 'inherit' });
    console.log(`\n[32m✓ Tests completed successfully!\u001b[0m\n`);
  } catch (error) {
    console.error(`\n[31m✗ Tests failed\u001b[0m\n`);
    process.exit(1);
  }
}

// Main
const command = process.argv[2];

if (!command || command === '--help' || command === '-h') {
  printUsage();
  process.exit(0);
}

runTests(command);
