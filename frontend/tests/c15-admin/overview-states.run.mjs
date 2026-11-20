import { chromium, expect } from '@playwright/test';
import { createHmac } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const config = JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA, 'IntervucopilotC15Local/logins.json'), 'utf8'));
const output = path.resolve(process.env.C15_EVIDENCE_DIR || '../docs/evidence/c15-admin-overview-20261105');
const browser = await chromium.launch();
const results = [];
function fixture() {
  const now = Date.now();
  return {
    as_of: new Date(now).toISOString(), start: new Date(now - 30 * 86400000).toISOString(), end: new Date(now).toISOString(), timezone: 'Asia/Kolkata',
    total_users: 585, new_users: 95, growth_percent: 19.39, active_7_days: 143, active_30_days: 271, current_activity_5_minutes: 8,
    registration_coverage: 'synthetic_fixture', activity_coverage: 'synthetic_fixture', attempt_coverage: 'synthetic_fixture', coverage_started_at: new Date(now - 90 * 86400000).toISOString(),
    daily_registrations: [490, 503, 519, 534, 552, 571, 585].map((total, index) => ({ day_bucket: new Date(now - (6 - index) * 86400000).toISOString().slice(0, 10), total_users: total, new_users: [11, 13, 16, 15, 18, 19, 14][index] })),
    models: [
      { provider: 'fixture-provider-a', model: 'Fixture small model', attempts: 183, completed: 161, failed: 15, aborted: 7, token_covered: 183 },
      { provider: 'fixture-provider-b', model: 'Fixture reasoning model', attempts: 119, completed: 103, failed: 12, aborted: 4, token_covered: 119 },
      { provider: 'fixture-local', model: 'Fixture local model', attempts: 77, completed: 64, failed: 9, aborted: 4, token_covered: 0 },
    ], costs: [{ currency: 'USD', estimated_amount: '31.46', covered_attempts: 302 }], cost_unknown_attempts: 77,
  };
}
function totp(secret) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits = [...secret.replaceAll('=', '').toUpperCase()].map(char => alphabet.indexOf(char).toString(2).padStart(5, '0')).join('');
  const key = Buffer.from((bits.match(/.{8}/g) || []).map(byte => parseInt(byte, 2)));
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const digest = createHmac('sha1', key).update(counter).digest(), offset = digest[19] & 15;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1000000).padStart(6, '0');
}
class Dashboard {
  constructor(page) { this.page = page; }
  async login(role) {
    this.page.setDefaultTimeout(15000);
    await this.page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');
    await this.page.getByLabel('Email Address', { exact: true }).fill(config.users[role].email);
    await this.page.getByLabel('Password', { exact: true }).fill(config.password);
    await this.page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await expect(this.page.getByRole('heading', { name: 'Customers', exact: true })).toBeVisible({ timeout: 30000 });
  }
  async overview(data, { code = 200, hold } = {}) {
    await this.page.unroute('**/api/admin/metrics');
    await this.page.route('**/api/admin/metrics', async route => {
      if (hold) await hold;
      await route.fulfill({ status: code, json: data });
    });
    await this.page.goto('http://127.0.0.1:5400/auth/admin?view=overview&keep=retained');
    if (!hold) { if (code === 200) await expect(this.page.getByRole('button', { name: /^(Verify access|Verified)$/ })).toBeVisible(); else await expect(this.page.getByRole('button', { name: 'Retry access check', exact: true })).toBeVisible(); }
  }
  async label() {
    await this.page.evaluate(() => {
      const note = document.createElement('p'); note.setAttribute('role', 'note'); note.textContent = 'DESIGN PREVIEW / SAMPLE DATA / browser-only fixture';
      note.style.cssText = 'max-width:none;padding:12px 16px;background:#e7f1ff;color:#075ac4;border:1px solid #1671ed;border-radius:8px;margin:0 0 20px;';
      document.querySelector('main').prepend(note);
    });
  }
  async capture(name) {
    await this.label(); await this.page.evaluate(() => document.fonts.ready);
    expect(await this.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await this.page.screenshot({ path: path.join(output, name + '.png'), fullPage: true, timeout: 20000 });
  }
}
try {
  await Promise.all(['super_admin', 'admin'].map(async role => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
    const page = await context.newPage(), dashboard = new Dashboard(page);
    try {
      await dashboard.login(role);
      await dashboard.overview(fixture());
      const nav = page.getByRole('navigation', { name: 'Administration', exact: true });
      await expect(nav.getByRole('button', { name: 'Audit history', exact: true })).toHaveCount(role === 'super_admin' ? 1 : 0);
      await expect(nav.getByRole('button', { name: 'Administrators', exact: true })).toHaveCount(role === 'super_admin' ? 1 : 0);
      for (const [width, height] of [[1440, 900], [1366, 768], [768, 1024], [390, 844]]) {
        await page.setViewportSize({ width, height });
        await dashboard.capture(`fixture-${role}-${width}`);
        results.push({ scenario: 'labelled_populated_fixture', role, width, passed: true });
      }
      const menu = page.getByRole('button', { name: 'Open navigation', exact: true });
      await menu.click();
      const drawer = page.getByRole('dialog', { name: 'Administration navigation', exact: true });
      await expect(drawer).toBeVisible();
      await expect(drawer.getByRole('button', { name: 'Customers', exact: true })).toBeVisible();
      await expect(drawer.getByRole('button', { name: 'Audit history', exact: true })).toHaveCount(role === 'super_admin' ? 1 : 0);
      await page.keyboard.press('Shift+Tab');
      expect(await drawer.evaluate(node => node.contains(document.activeElement))).toBeTruthy();
      await page.keyboard.press('Escape'); await expect(drawer).not.toBeVisible(); await expect(menu).toBeFocused();
      await menu.click(); await drawer.getByRole('button', { name: 'Customers', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Customers', exact: true })).toBeVisible();
      expect(new URL(page.url()).searchParams.get('keep')).toBe('retained');
      results.push({ scenario: 'mobile_drawer_focus_escape_role_navigation_query_preserved', role, passed: true });
      await page.setViewportSize({ width: 1440, height: 900 });
      await dashboard.overview(fixture());
      const posted = page.waitForRequest(request => request.url().endsWith('/api/admin/metrics') && request.method() === 'POST');
      await page.getByRole('combobox', { name: 'Rolling window', exact: true }).selectOption('7');
      expect((new Date((await posted).postDataJSON().end) - new Date((await posted).postDataJSON().start)) / 86400000).toBeCloseTo(7, 3);
      const zoneRequest = page.waitForRequest(request => request.url().endsWith('/api/admin/metrics') && request.method() === 'POST');
      await page.getByRole('combobox', { name: 'Chart timezone', exact: true }).selectOption('UTC');
      expect((await zoneRequest).postDataJSON().timezone).toBe('UTC');
      await expect(page.getByRole('button', { name: 'Refresh metrics', exact: true })).toBeEnabled();
      await page.getByRole('button', { name: 'New users', exact: true }).click();
      await page.getByRole('button', { name: 'Total users', exact: true }).click();
      const point = page.getByRole('img', { name: /total verified users$/ });
      expect(await point.count()).toBe(7);
      await page.getByRole('img', { name: /490 total verified users$/ }).focus();
      await expect(page.locator('figcaption').filter({ hasText: ': 490 verified users' })).toBeVisible();
      await page.getByText('Metric definitions / Data coverage', { exact: true }).click();
      await page.getByText('View user data', { exact: true }).click();
      await expect(page.getByRole('region', { name: 'Daily verified user counts', exact: true })).toBeVisible();
      await expect(page.getByText('No prior-period comparison is inferred.', { exact: false })).toBeVisible();
      results.push({ scenario: 'range_timezone_chart_toggle_accessible_data_definitions', role, passed: true });
      const verification = page.getByRole('button', { name: 'Verify access', exact: true });
      await verification.click();
      const auth = page.getByRole('dialog', { name: 'Verify sensitive access', exact: true });
      await expect(auth).toBeVisible(); await page.keyboard.press('Escape'); await expect(verification).toBeFocused();
      await verification.click();
      await auth.getByRole('textbox', { name: 'Authenticator code', exact: true }).fill(totp(config.users[role].totp_secret));
      await auth.getByRole('button', { name: 'Verify authenticator', exact: true }).click();
      await expect(auth).not.toBeVisible({ timeout: 15000 });
      await expect(page.getByRole('button', { name: 'Verified', exact: true })).toBeVisible();
      results.push({ scenario: 'actual_auth_totp_compact_dialog_cancel_and_verification', role, passed: true });
      // All following scenarios are browser-only metrics fixtures; Auth and permissions stay actual.
      const unknown = fixture(); unknown.models = []; unknown.costs = []; unknown.daily_registrations = []; unknown.total_users = null; unknown.new_users = null; unknown.growth_percent = null;
      await dashboard.overview(unknown); await dashboard.capture(`fixture-unavailable-${role}`);
      await expect(page.getByText('Earlier growth history unavailable', { exact: true })).toBeVisible();
      const partial = fixture(); partial.growth_percent = -3.57; partial.costs.push({ currency: 'EUR', estimated_amount: '12.57', covered_attempts: 20 }); partial.as_of = new Date(Date.now() - 600000).toISOString();
      await dashboard.overview(partial); await dashboard.capture(`fixture-multiple-currency-stale-${role}`);
      await expect(page.getByText('Multiple currencies', { exact: true })).toBeVisible();
      await expect(page.getByText('-3.57% growth in selected window', { exact: true })).toBeVisible();
      await expect(page.getByText('Older snapshot. Refresh for current data.', { exact: true })).toBeVisible();
      let release; const hold = new Promise(resolve => { release = resolve; });
      await dashboard.overview(fixture(), { hold });
      await expect(page.getByText('Loading authorized metrics...', { exact: true })).toBeVisible();
      await dashboard.capture(`fixture-loading-${role}`); release();
      await expect(page.getByRole('button', { name: /^(Verify access|Verified)$/ })).toBeVisible();
      await dashboard.overview({}, { code: 503 }); await dashboard.capture(`fixture-error-${role}`);
      await expect(page.getByRole('button', { name: 'Retry access check', exact: true })).toBeVisible();
      results.push({ scenario: 'unavailable_partial_multiple_currency_stale_loading_failure', role, passed: true });
      const gap = fixture(); gap.daily_registrations.splice(2, 2); gap.total_users = 987654321098;
      await dashboard.overview(gap);
      expect(await page.locator('svg polyline').count()).toBe(2);

      await page.setViewportSize({ width: 390, height: 844 });
      await page.evaluate(() => { const name = document.querySelector('.ac-account strong'); if (name) name.textContent = 'Synthetic account name with exceptionally long unbrokencharactersforlayoutverification'; });
      await dashboard.capture(`fixture-large-gap-${role}`);
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.evaluate(() => { document.documentElement.style.zoom = '2'; });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      await page.evaluate(() => { document.documentElement.style.zoom = ''; });
      results.push({ scenario: 'unknown_date_gap_not_joined_large_value_zoom_long_name', role, passed: true });
      // A late old metrics response must not restore a previous section.
      let releaseLate; const late = new Promise(resolve => { releaseLate = resolve; });
      await page.unroute('**/api/admin/metrics');
      await page.route('**/api/admin/metrics', async route => { await late; await route.fulfill({ json: fixture() }).catch(() => {}); });
      const outstanding = page.waitForRequest(request => request.url().endsWith('/api/admin/metrics'));
      await page.getByRole('button', { name: 'Refresh metrics', exact: true }).click();
      await outstanding;
      const releasedMetrics = Promise.race([
        page.waitForResponse(response => response.url().endsWith('/api/admin/metrics')),
        page.waitForEvent('requestfailed', request => request.url().endsWith('/api/admin/metrics')),
      ]);
      await page.getByRole('navigation',{name:'Administration',exact:true}).getByRole('button',{name:'Customers',exact:true}).click();
      releaseLate(); await releasedMetrics;
      await expect(page.getByRole('heading', { level: 1, name: 'Customers', exact: true })).toBeVisible();
      await expect(page.locator('tbody tr').first()).toBeVisible();
      await expect(page.getByRole('heading', { name: 'User growth', exact: true })).toHaveCount(0);
      results.push({ scenario: 'late_metrics_response_cannot_restore_old_section', role, passed: true });
      if (role === 'admin') {
        await page.unroute('**/api/admin/metrics');
        await page.goto('http://127.0.0.1:5400/auth/admin?view=audit');
        await expect(page.getByRole('heading', { name: 'Page not found', exact: true })).toBeVisible();
        await expect(page).toHaveTitle('Page not found | Intervucopilot');
        results.push({ scenario: 'actual_admin_forbidden_deep_link_not_found', passed: true });
      }
    } finally { await context.close(); }
  }));
} finally {
  await browser.close();
  await writeFile(path.join(output, 'state-results-reference.json'), JSON.stringify({ results, fixture_boundary: 'Only metrics responses replaced inside isolated browser contexts; no fixture metrics written to DB or runtime code. Actual Auth and role endpoints unchanged.' }, null, 2));
}
console.log('PASS', results.length, 'dashboard state and interaction checks');
