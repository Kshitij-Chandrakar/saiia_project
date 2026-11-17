import { chromium, expect } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const config = JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA, 'IntervucopilotC15Local/logins.json'), 'utf8'));
const output = path.resolve('../docs/evidence/c15-admin-overview-20261105');
const browser = await chromium.launch();
const results = [];
class StaffPage {
  constructor(page) { this.page = page; }
  async login(role) {
    await this.page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');
    await this.page.getByLabel('Email Address', { exact: true }).fill(config.users[role].email);
    await this.page.getByLabel('Password', { exact: true }).fill(config.password);
    await this.page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await expect(this.page.getByRole('heading', { level: 1, name: 'Customers', exact: true })).toBeVisible({ timeout: 30000 });
  }
  async switchTo(role) {
    await this.page.evaluate(async credentials => {
      const { supabase } = await import('/src/auth/supabaseClient.js');
      const result = await supabase.auth.signInWithPassword(credentials);
      if (result.error) throw Error('synthetic_account_switch_failed');
    }, { email: config.users[role].email, password: config.password });
  }
}
try {
  await Promise.all(['super_admin', 'admin'].map(async role => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage(); page.setDefaultTimeout(15000);
    const staff = new StaffPage(page);
    try {
      await staff.login(role);
      await expect(page.getByRole('button', { name: 'Verify access', exact: true })).toBeVisible();
      await page.getByLabel('Exact customer email or account ID', { exact: true }).fill(config.users.customer.email);
      await page.getByRole('button', { name: 'Search', exact: true }).click();
      await page.getByRole('button', { name: 'Inspect metadata', exact: true }).click();
      await page.getByRole('button', { name: 'Restrict product access', exact: true }).click();
      const access = page.getByRole('dialog', { name: 'Restrict customer product access', exact: true });
      const denied = page.waitForResponse(response => response.url().endsWith('/api/admin/access/review') && response.request().method() === 'POST');
      await access.getByRole('button', { name: 'Review access change', exact: true }).click();
      expect((await denied).status()).toBe(403);
      const verification = page.getByRole('dialog', { name: 'Verify sensitive access', exact: true });
      await expect(verification).toBeVisible();
      await expect(verification.getByRole('textbox', { name: 'Authenticator code', exact: true })).toBeFocused();
      await verification.getByRole('button', { name: 'Close verification', exact: true }).click();
      await access.getByRole('button', { name: 'Cancel', exact: true }).click();
      results.push({ scenario: 'actual_missing_proof_403_surfaces_verification_without_mutation', role, passed: true });
      if (role === 'super_admin') {
        await staff.switchTo('admin');
        await expect(page.getByRole('heading', { level: 1, name: 'Customers', exact: true })).toBeVisible();
        await expect(page.getByRole('navigation', { name: 'Administration', exact: true }).getByRole('button', { name: 'Administrators', exact: true })).toHaveCount(0);
        await expect(page.getByRole('navigation', { name: 'Administration', exact: true }).getByRole('button', { name: 'Audit history', exact: true })).toHaveCount(0);
        results.push({ scenario: 'actual_super_to_admin_account_switch_clears_privileged_navigation', passed: true });
      }
      await staff.switchTo('customer');
      await expect(page.getByRole('heading', { name: 'Page not found', exact: true })).toBeVisible();
      await expect(page.getByRole('navigation', { name: 'Administration', exact: true })).toHaveCount(0);
      await expect(page).toHaveTitle('Page not found | Intervucopilot');
      results.push({ scenario: 'actual_customer_switch_clears_staff_shell_and_retains_404', role, passed: true });
    } finally { await context.close(); }
  }));
} finally {
  await browser.close();
  await writeFile(path.join(output, 'safety-results.json'), JSON.stringify({ results, boundary: 'Actual local SDK/Auth/application endpoints; no interception; access review denied before any mutation or confirmation' }, null, 2));
}
console.log('PASS', results.length, 'actual authorization/verification shell checks');
