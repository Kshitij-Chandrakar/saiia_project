import { defineConfig } from '@playwright/test'

export default defineConfig({
  outputDir: './test-results/dashboard',
  testDir: './tests/e2e', testMatch: ['dashboard.spec.js', 'session-loss.spec.js', 'callback-loading.spec.js'], fullyParallel: true, workers: 2,
  reporter: 'list', use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1', url: 'http://127.0.0.1:5173', reuseExistingServer: true },
})
