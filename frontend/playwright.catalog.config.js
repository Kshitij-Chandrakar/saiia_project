import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './tests/catalog',
  fullyParallel: true,
  workers: 2,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5186',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome']
  },
  webServer: {
    command: 'npx vite --host 127.0.0.1 --port 5186 --strictPort',
    url: 'http://127.0.0.1:5186',
    reuseExistingServer: false
  },
  outputDir: process.env.CATALOG_BROWSER_NATIVE ? '../tmp/c113d-native-playwright' : '../tmp/c113d-playwright'
});
