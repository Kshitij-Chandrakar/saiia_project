import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/website-progress', fullyParallel: true, workers: 2, retries: 0,
  reporter: [['list'], ['json', { outputFile: process.env.WEBSITE_PROGRESS_DEV ? '../tmp/website-batch2/results-dev.json' : '../tmp/website-batch2/results.json' }]],
  outputDir: process.env.WEBSITE_PROGRESS_DEV ? '../tmp/website-batch2/test-results-dev' : '../tmp/website-batch2/test-results',
  use: { baseURL: 'http://127.0.0.1:5311', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: { command: process.env.WEBSITE_PROGRESS_DEV ? 'npx vite --host 127.0.0.1 --port 5311 --strictPort' : 'npx vite preview --outDir ../tmp/website-batch2-production --host 127.0.0.1 --port 5311 --strictPort', url: 'http://127.0.0.1:5311', reuseExistingServer: false },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
})
