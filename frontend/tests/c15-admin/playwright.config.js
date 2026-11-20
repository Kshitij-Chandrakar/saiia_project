import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  testDir: '.',
  testMatch: 'review-regressions.spec.js',
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5397', trace: 'retain-on-failure' },
  webServer: {
    command: 'npx vite --host 127.0.0.1 --port 5397 --strictPort',
    cwd: fileURLToPath(new URL('../..', import.meta.url)),
    url: 'http://127.0.0.1:5397',
    reuseExistingServer: false,
    timeout: 30000,
  },
});
