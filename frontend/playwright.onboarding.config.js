import { defineConfig } from '@playwright/test'
export default defineConfig({testDir:'./tests/e2e',testMatch:'onboarding.spec.js',outputDir:'./test-results/onboarding',workers:2,
 reporter:'list',use:{baseURL:'http://127.0.0.1:5173',trace:'off',screenshot:'only-on-failure'},
 webServer:{command:'npm run dev -- --host 127.0.0.1',url:'http://127.0.0.1:5173',reuseExistingServer:true}})
