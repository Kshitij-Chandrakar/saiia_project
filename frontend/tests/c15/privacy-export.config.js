import base from './playwright.config.js'
import { defineConfig } from '@playwright/test'
export default defineConfig({ ...base, testMatch: 'privacy-export.spec.js', outputDir: 'test-results/c15-export-cleanup' })
