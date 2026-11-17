import { chromium, expect } from '@playwright/test';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

const config = JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA, 'IntervucopilotC15Local/logins.json'), 'utf8'));
const output = path.resolve('../docs/evidence/c15-admin-overview-20261105');
const before = process.argv.includes('--before');
const phase = before ? 'before' : process.env.C15_DESIGN_RUN || 'after-final';
const browser = await chromium.launch();
const results = [];
const sizes = [[1440, 900], [1366, 768], [768, 1024], [390, 844]];
class OverviewPage {
  constructor(page) { this.page = page; }
  async login(role) {
    await this.page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');
    await this.page.getByLabel('Email Address', { exact: true }).fill(config.users[role].email);
    await this.page.getByLabel('Password', { exact: true }).fill(config.password);
    await this.page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await expect(this.page.getByRole('heading', { name: 'Customers', exact: true })).toBeVisible({ timeout: 30000 });
    await this.page.goto('http://127.0.0.1:5400/auth/admin?view=overview');
    await expect(this.page.getByRole('heading', { name: before ? 'Executed model attempts' : 'Most used models', exact: true })).toBeVisible({ timeout: 30000 });
    if (!before) await expect(this.page.getByRole('button', { name: /^(Verify access|Verified)$/ })).toBeVisible();
  }
}
try {
  await mkdir(output, { recursive: true });
  await Promise.all(['super_admin', 'admin'].map(async role => { for (const [width, height] of sizes) {
    const context = await browser.newContext({ viewport: { width, height } });
    const page = await context.newPage();
    page.setDefaultTimeout(15000); page.setDefaultNavigationTimeout(30000);
    try {
      await new OverviewPage(page).login(role);
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: path.join(output, `${phase}-${role}-${width}.png`), fullPage: true, timeout: 20000 });
      if (!before) {
        await expect(page.getByRole('heading', { level: 1, name: 'Overview', exact: true })).toHaveCount(1);
        await expect(page).toHaveTitle('Administration | Intervucopilot');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      }
      results.push({ role, width, height, passed: true });
    } finally { await context.close(); }
  } }));
} finally {
  await browser.close();
  await writeFile(path.join(output, `${phase}-results.json`), JSON.stringify(results, null, 2));
}
console.log('PASS', results.length, before ? 'before captures' : 'responsive actual Overview views');
