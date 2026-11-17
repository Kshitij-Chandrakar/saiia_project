import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: '.', testMatch: 'review-regressions.spec.js', workers: 1, reporter: 'list', use: { baseURL: 'http://127.0.0.1:5493' }, outputDir: process.env.C15_REVIEW_EVIDENCE || '../../../docs/evidence/c15-5-review-ui-20261117' });
