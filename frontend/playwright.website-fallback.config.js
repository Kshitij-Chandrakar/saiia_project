import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/website-fallback',
  fullyParallel: true,
  workers: 2,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: process.env.WEBSITE_FALLBACK_DEV === '1' ? '../tmp/website-batch1/results-dev.json' : '../tmp/website-batch1/results.json' }]],
  outputDir: process.env.WEBSITE_FALLBACK_DEV === '1' ? '../tmp/website-batch1/test-results-dev' : '../tmp/website-batch1/test-results',
  use: { baseURL: 'http://127.0.0.1:5301', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: {
    command: process.env.WEBSITE_FALLBACK_DEV === '1'
      ? 'npx vite --host 127.0.0.1 --port 5301 --strictPort'
      : 'npx vite preview --outDir ../tmp/website-batch1-production --host 127.0.0.1 --port 5301 --strictPort',
    url: 'http://127.0.0.1:5301',
    reuseExistingServer: false,
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
})
