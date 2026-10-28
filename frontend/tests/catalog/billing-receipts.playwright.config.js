import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'billing-receipts.spec.js',
  fullyParallel: true,
  workers: 2,
  retries: 0,
  outputDir: '../../../tmp/c12-billing-email-redesign/playwright',
  use: { trace: 'retain-on-failure', screenshot: 'only-on-failure' },
});
