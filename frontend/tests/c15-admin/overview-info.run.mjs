import { chromium, expect } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const accounts = JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA, 'IntervucopilotC15Local/logins.json'), 'utf8'));
const output = path.resolve(process.env.C15_EVIDENCE_DIR || '../docs/evidence/c15-admin-info-20261105');
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const results = [];
try {
  for (const width of [1440, 1366, 390]) {
    const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : width === 1366 ? 768 : 900 }, hasTouch: width === 390 });
    const page = await context.newPage(); page.setDefaultTimeout(15000);
    await page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');
    await page.getByLabel('Email Address', { exact: true }).fill(accounts.users.admin.email);
    await page.getByLabel('Password', { exact: true }).fill(accounts.password);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Customers', exact: true })).toBeVisible({ timeout: 30000 });
    await page.goto('http://127.0.0.1:5400/auth/admin?view=overview');
    await expect(page.getByRole('button', { name: 'Verify access', exact: true })).toBeVisible();
    for (const label of ['Activity', 'API cost breakdown']) {
      const button = page.getByRole('button', { name: 'About ' + label, exact: true });
      if (width === 390) await button.tap(); else await button.hover();
      const tooltip = page.getByRole('tooltip');
      await expect(tooltip).toBeVisible();
      await expect(tooltip).toContainText(label === 'Activity' ? 'completed attempts' : 'not a provider invoice');
      expect(await button.getAttribute('aria-describedby')).toBe(await tooltip.getAttribute('id'));
      const bounds = await tooltip.boundingBox();
      expect(bounds.y).toBeGreaterThanOrEqual(0); expect(bounds.y + bounds.height).toBeLessThanOrEqual(width === 390 ? 844 : width === 1366 ? 768 : 900);
      expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      if (width !== 390) { await tooltip.hover(); await expect(tooltip).toBeVisible(); }
      await page.screenshot({ path: path.join(output, `${width}-${label.replaceAll(' ', '-')}.png`), fullPage: false });
      await button.focus(); await button.press('Escape'); await expect(tooltip).toHaveCount(0);
      await page.getByRole('button', { name: 'Refresh metrics', exact: true }).focus();
      await button.focus(); await expect(page.getByRole('tooltip')).toBeVisible();
      await button.press('Escape');
      results.push({ width, label, hover_or_tap: true, keyboard_focus_escape: true, hoverable: width === 1440, viewport_contained: true });
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await context.close();
  }
} finally {
  await browser.close();
  await writeFile(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
}
console.log('PASS', results.length, 'section tooltip checks');
