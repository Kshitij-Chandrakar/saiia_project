import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/website-branding', fullyParallel: true, workers: 2, retries: 0,
  reporter: [['list'], ['json', { outputFile: process.env.WEBSITE_BRANDING_DEV ? '../tmp/website-batch3/results-dev.json' : '../tmp/website-batch3/results.json' }]],
  outputDir: process.env.WEBSITE_BRANDING_DEV ? '../tmp/website-batch3/test-results-dev' : '../tmp/website-batch3/test-results',
  use: { baseURL: 'http://127.0.0.1:5321', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: { command: process.env.WEBSITE_BRANDING_DEV ? 'npx vite --host 127.0.0.1 --port 5321 --strictPort' : 'npx vite preview --outDir ../tmp/website-batch3-production --host 127.0.0.1 --port 5321 --strictPort', url: 'http://127.0.0.1:5321', reuseExistingServer: false },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
})
