import { chromium, expect } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const accounts = JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA, 'IntervucopilotC15Local/logins.json'), 'utf8'));
const output = path.resolve('../docs/evidence/c15-customer-help-20261105');
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const results = [];
try {
  for (const role of ['super_admin', 'admin']) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, hasTouch: true });
    const page = await context.newPage(); page.setDefaultTimeout(15000);
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');
    await page.getByLabel('Email Address', { exact: true }).fill(accounts.users[role].email);
    await page.getByLabel('Password', { exact: true }).fill(accounts.password);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Customers', exact: true })).toBeVisible();
    await page.getByLabel('Exact customer email or account ID', { exact: true }).fill(accounts.users.customer.email);
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await page.getByRole('button', { name: 'Inspect metadata', exact: true }).click();
    const detail = page.getByRole('region', { name: 'Selected customer metadata', exact: true });
    await expect(detail).toBeVisible();
    expect(await detail.locator('dt').count()).toBe(await detail.locator('dt button[aria-label^="About "]').count());
    expect(await detail.locator('h2,h3').count()).toBe(await detail.locator('h2 button,h3 button').count());
    await expect(detail.getByText('Sign-in methods', { exact: true })).toBeVisible();
    await expect(detail.locator('time').first()).toContainText('UTC');
    const timestamp = detail.getByText('Exact timestamp', { exact:true }).first();
    await timestamp.click(); await expect(timestamp.locator('..').locator('code')).toContainText('2026-'); await timestamp.click();
    await expect(detail.getByRole('button', { name: 'Restore staff-restricted access', exact: true })).toHaveCount(role === 'super_admin' ? 1 : 0);
    let requests = 0; const track = request => { if (request.url().includes('/api/admin/')) requests++; }; page.on('request', track);
    for (const [width, height] of [[1440,900],[390,844],[720,450]]) {
      await page.setViewportSize({ width, height });
      const help = detail.getByRole('button', { name: 'About Last recorded activity', exact: true });
      await help.scrollIntoViewIfNeeded();
      const before = await detail.boundingBox();
      await help.hover();
      await expect(page.getByRole('tooltip')).toContainText('not the last login');
      const popup = page.getByRole('tooltip');
      const bounds = await popup.boundingBox();
      expect(bounds.x).toBeGreaterThanOrEqual(0); expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      expect(bounds.y).toBeGreaterThanOrEqual(0); expect(bounds.y + bounds.height).toBeLessThanOrEqual(height);
      expect((await detail.boundingBox()).height).toBe(before.height);
      expect(await help.getAttribute('aria-describedby')).toBe(await popup.getAttribute('id'));
      await page.screenshot({ path: path.join(output, `${role}-${width}-field-help.png`) });
      await popup.hover(); await expect(popup).toBeVisible();
      await help.focus(); await help.press('Escape'); await expect(popup).toHaveCount(0);
      await expect(help).toBeFocused();
      await page.mouse.move(0, 0); await help.hover(); await expect(popup).toBeVisible();
      await help.click(); await page.mouse.move(0, 0); await expect(popup).toBeVisible();
      await help.click(); await expect(popup).toHaveCount(0);
      await help.press('Tab'); await help.focus(); await expect(popup).toBeVisible();
      await help.press('Space'); await help.press('Escape'); await expect(popup).toHaveCount(0);
      await help.press('Enter'); await expect(popup).toBeVisible(); await help.press('Enter'); await expect(popup).toHaveCount(0);
      if (width === 390) { await help.tap(); await expect(popup).toBeVisible(); await help.tap(); await expect(popup).toHaveCount(0); }
      await help.click(); await detail.getByRole('heading', { name: 'Account metadata', exact: true }).click(); await expect(popup).toHaveCount(0);
      const headerHelp = detail.getByRole('button', { name: 'About Account metadata', exact: true });
      await headerHelp.click();
      await page.screenshot({ path: path.join(output, `${role}-${width}-help.png`) });
      await headerHelp.press('Escape');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
      results.push({ role, width, actual_inspection: true, help_and_dismissal: true, viewport: true, no_layout_shift: true });
    }
    expect(requests).toBe(0); page.off('request', track);
    await page.setViewportSize({ width:1440, height:900 });
    await detail.getByRole('button', { name: 'About Restrict product access', exact:true }).click();
    await expect(page.getByRole('tooltip')).toContainText('without cancelling billing');
    await page.keyboard.press('Escape');
    await detail.getByRole('button', { name: 'Restrict product access', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Restrict customer product access' })).toContainText('does not cancel billing');
    await page.getByRole('button', { name: 'Cancel', exact:true }).click();
    results.push({ role, actual_confirmation_preserved: true, no_mutation_submitted: true });

    // Response-only fixtures cover optional sections and fault values. Auth/role checks stay real.
    const id = await detail.locator('dd').first().innerText();
    let release;
    let delay = false;
    const hold = new Promise(resolve => { release = resolve; });
    await page.route(`**/api/admin/users/${id}`, async route => {
      const response = await route.fetch(); const data = await response.json();
      if (delay) await hold;
      await route.fulfill({ json: { ...data, email:'fixture-first@example.invalid', email_verified:null, account_access_state:'future_state', last_product_activity_at:null, resources:{ resume_count:0, active_resume_count:false, future_count:null, resume_processing_state:{ready:0,future_stage:1} } } });
    });
    await page.route(`**/api/admin/users/${id}/subscription`, route => route.fulfill({ json:{ operations:[{subscription_id:'fixture-only',paid_status:'confirmed',renewal_state:'active',cancellation_state:'unknown'}] } }));
    await page.route(`**/api/admin/users/${id}/privacy`, route => route.fulfill({ json:{ tasks:[{task_id:'fixture-only',kind:'account',state:'blocked',revision:'0',attempts:0,retry_available:true}] } }));
    await page.getByRole('button',{name:'Inspect metadata',exact:true}).click();
    await expect(detail.getByText('fixture-first@example.invalid',{exact:true})).toBeVisible();
    await expect(detail.getByText('Unknown value',{exact:true}).first()).toBeVisible();
    await expect(detail.locator('dt').filter({hasText:'Email verified'}).locator('..').locator('dd')).toHaveText('Unavailable');
    await expect(detail.locator('dt').filter({hasText:'Resumes'}).first().locator('..').locator('dd')).toHaveText('0');
    await expect(detail.locator('dt').filter({hasText:'Active resumes'}).locator('..').locator('dd')).toHaveText('No');
    await detail.getByRole('button',{name:'About Request renewal cancellation',exact:true}).click(); await expect(page.getByRole('tooltip')).toContainText('paid access remains'); await page.keyboard.press('Escape');
    await detail.getByRole('button',{name:'About Review eligible cleanup retry',exact:true}).click(); await expect(page.getByRole('tooltip')).toContainText('original scope'); await page.keyboard.press('Escape');
    await detail.getByRole('button',{name:'Request renewal cancellation',exact:true}).click();
    await expect(page.getByRole('dialog',{name:'Cancel future subscription renewal',exact:true})).toContainText('Existing paid access remains');
    await page.getByRole('button',{name:'Cancel',exact:true}).click();
    await detail.getByRole('button',{name:'Review eligible cleanup retry',exact:true}).click();
    await expect(page.getByRole('dialog',{name:'Retry existing cleanup task',exact:true})).toContainText('cannot start deletion, expand its scope');
    await page.getByRole('button',{name:'Cancel',exact:true}).click();
    await page.evaluate(() => { const note=document.createElement('p');note.textContent='SYNTHETIC RESPONSE FIXTURE, optional sections and edge cases';document.querySelector('.ac-customer-metadata').prepend(note); });
    await page.screenshot({path:path.join(output,`${role}-fixture.png`)});
    results.push({role,response_fixture:true,missing_zero_false_unknown:true,optional_subscription_privacy_help:true});
    // A different customer must win even if the previous inspection response arrives last.
    await detail.getByRole('button',{name:'About Account ID',exact:true}).click(); await expect(page.getByRole('tooltip')).toBeVisible();
    await page.getByLabel('Exact customer email or account ID', { exact: true }).fill('');
    await page.getByRole('button', { name:'Search', exact:true }).click();
    await expect(page.getByRole('tooltip')).toHaveCount(0);
    const firstRow = page.getByRole('row').filter({has:page.getByText(accounts.users.customer.email,{exact:true})});
    const nextRow = page.getByRole('row').filter({has:page.getByText(accounts.users.delete_customer.email,{exact:true})});
    await expect(nextRow).toBeVisible();
    await page.evaluate(id => {
      const original = window.fetch;
      const paths = new Set(['','/privacy','/subscription','/allowances'].map(suffix=>'/api/admin/users/'+id+suffix));
      window.__olderInspectionReads = 0;
      window.__restoreInspectionFetch = () => { window.fetch = original; };
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (paths.has(new URL(typeof args[0] === 'string' ? args[0] : args[0].url, location.href).pathname)) {
          const parse = response.json.bind(response);
          response.json = async () => { try { return await parse(); } finally { window.__olderInspectionReads++; } };
        }
        return response;
      };
    }, id);
    delay = true;
    const waiting = page.waitForRequest(request=>request.url().endsWith('/api/admin/users/'+id));
    await firstRow.getByRole('button',{name:'Inspect metadata',exact:true}).click(); await waiting;
    await nextRow.getByRole('button',{name:'Inspect metadata',exact:true}).click();
    await expect(detail.getByText(accounts.users.delete_customer.email,{exact:true})).toBeVisible();
    const finished = page.waitForResponse(response=>response.url().endsWith('/api/admin/users/'+id));
    release();
    await finished;
    await expect.poll(()=>page.evaluate(()=>window.__olderInspectionReads)).toBe(4);
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    await page.evaluate(()=>window.__restoreInspectionFetch());
    await expect(detail.getByText('fixture-first@example.invalid',{exact:true})).toHaveCount(0);
    await expect(detail.getByText(accounts.users.delete_customer.email,{exact:true})).toBeVisible();
    expect(errors).toEqual([]);
    await page.goto('http://127.0.0.1:5400/auth/admin?view=overview'); await expect(page.getByRole('tooltip')).toHaveCount(0);
    results.push({role,late_inspection_does_not_overwrite:true,help_unmounted:true});
    await context.close();
  }
} finally { await browser.close(); await writeFile(path.join(output,'results.json'),JSON.stringify(results,null,2)); }
console.log('PASS', results.length, 'customer metadata help checks');
