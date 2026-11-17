import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'../catalog',testMatch:['workspace.spec.js','lifecycle.spec.js','workflow.spec.js'],workers:2,reporter:'list',
  use:{baseURL:process.env.C15_COMMERCIAL_BASE_URL || 'http://127.0.0.1:5400',trace:'off',screenshot:'only-on-failure'},
  outputDir:process.env.C15_COMMERCIAL_EVIDENCE || '../../../docs/evidence/c15-commercial-shell-20261105/regression-artifacts',
});
