import { defineConfig } from '@playwright/test'
export default defineConfig({ outputDir: './test-results/signup', testDir: './tests/e2e', testMatch: ['signup.spec.js', 'signup-mascot.spec.js', 'signup-verification.spec.js', 'confirm-loading.spec.js', 'website-not-found.spec.js', 'startup-setup.spec.js'], fullyParallel: true, workers: 2,
  reporter: 'list', use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1', url: 'http://127.0.0.1:5173', reuseExistingServer: true } })
