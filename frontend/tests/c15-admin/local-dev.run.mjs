import { chromium, expect } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const state = path.join(process.env.LOCALAPPDATA, 'IntervucopilotC15Local');
const config = JSON.parse(await readFile(path.join(state, 'logins.json'), 'utf8'));
const fixture = JSON.parse(await readFile(path.join(state, 'verification-fixture.json'), 'utf8'));
const results = [];
const browser = await chromium.launch({ headless: true });
async function login(user, next) {
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:5400/auth/login?next=${next}`);
  await page.getByLabel('Email Address', { exact: true }).fill(user.email);
  await page.getByLabel('Password', { exact: true }).fill(config.password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  return { page, context };
}
try {
  for (const role of ['super_admin', 'admin']) {
    const { page, context } = await login(config.users[role], '/auth/admin');
    await expect(page.getByRole('heading', { name: 'Customers', exact: true })).toBeVisible({ timeout: 30000 });
    const nav = page.getByRole('navigation', { name: 'Administration', exact: true });
    await expect(nav.getByRole('button', { name: 'Campaigns', exact: true })).toBeVisible();
    await expect(nav.getByRole('button', { name: 'Audit history', exact: true })).toHaveCount(role === 'super_admin' ? 1 : 0);
    results.push({ scenario: role + '_actual_website_login_navigation', passed: true });
    await context.close();
  }
  const { page, context } = await login(config.users.customer, '/auth/settings');
  await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: 'Request account export', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Confirm your account export', exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('Verify your password', { exact: true }).fill(config.password);
  await dialog.getByRole('button', { name: 'Verify identity', exact: true }).click();
  const confirmation = dialog.locator('#privacy-export-confirm');
  await expect(confirmation).toBeEnabled({ timeout: 20000 });
  await confirmation.fill('export');
  await dialog.getByRole('button', { name: 'Create private export', exact: true }).click();
  const section = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Export your account data', exact: true }) });
  for (let n = 0; n < 50; n++) {
    await section.getByRole('button', { name: 'Refresh export status', exact: true }).click();
    if (await section.getByRole('button', { name: 'Download private archive', exact: true }).isEnabled()) break;
    await page.waitForTimeout(1000);
  }
  const download = page.waitForEvent('download');
  await section.getByRole('button', { name: 'Download private archive', exact: true }).click();
  await (await download).saveAs(path.join(state, 'verified-account-export.zip'));
  results.push({ scenario: 'actual_settings_password_confirm_worker_private_zip_download', passed: true });
  await context.close();
  const deleting = await login(fixture, '/auth/settings');
  await expect(deleting.page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible({ timeout: 30000 });
  await deleting.page.getByRole('button', { name: 'Delete Account', exact: true }).click();
  const danger = deleting.page.getByRole('dialog', { name: 'Delete your account?', exact: true });
  await danger.getByLabel('Reauthenticate with your password', { exact: true }).fill(config.password);
  await danger.getByRole('button', { name: 'Verify identity', exact: true }).click();
  await expect(danger.getByText('Identity verified.', { exact: false })).toBeVisible({ timeout: 20000 });
  await danger.locator('#privacy-confirm').fill('delete');
  await danger.getByRole('button', { name: 'Yes, Delete My Account', exact: true }).click();
  await expect(deleting.page.getByRole('heading', { name: 'Request accepted. Product access is restricted.', exact: true })).toBeVisible({ timeout: 30000 });
  for (let n = 0; n < 80; n++) {
    await deleting.page.getByRole('button', { name: 'Refresh request status', exact: true }).click();
    const text = await deleting.page.locator('main').innerText();
    if (text.includes('Controlled primary content removal is verified') && text.includes('original identity fields removed')) break;
    await deleting.page.waitForTimeout(1000);
  }
  await expect(deleting.page.getByText('Controlled primary content removal is verified', { exact: false })).toBeVisible();
  await expect(deleting.page.getByText('original identity fields removed', { exact: false })).toBeVisible();
  results.push({ scenario: 'actual_settings_typed_deletion_logout_workers_primary_cleanup_and_auth_cleanup', passed: true });
  await deleting.context.close();
} finally {
  await browser.close();
  await writeFile(path.join(state, 'browser-verification.json'), JSON.stringify({ results, boundaries: 'Actual website/SDK/local Auth/API/workers/Storage; no endpoint interception; synthetic only' }, null, 2));
}
console.log('PASS', results.length, 'local development website journeys');
