import base from './playwright.config.js'
import { defineConfig } from '@playwright/test'
export default defineConfig({ ...base, testMatch: ['privacy.spec.js', 'privacy-export.spec.js'], outputDir: 'test-results/c15-remaining-local' })
