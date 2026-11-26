import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'.',testMatch:'c12-installed.spec.js',workers:1,retries:0,timeout:150000,use:{trace:'off'},outputDir:'../../../tmp/c12-acceptance-installer/playwright'});
