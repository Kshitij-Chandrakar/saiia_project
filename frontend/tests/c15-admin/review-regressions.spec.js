import { test, expect } from '@playwright/test';
import { setup } from '../catalog/fixtures/workspace.js';
import { checkDialogScroll } from './dialogScroll.js';

async function admin(page, section = 'campaigns') {
  await setup(page);
  const state = { subject: 'synthetic-user', role: 'super_admin', meUnavailable: false, meCalls: 0,
    campaign: { campaign_id: '11111111-1111-4111-8111-111111111111', revision: '1', name: 'Saved campaign', subject: 'Saved subject', body: 'Saved body', state: 'draft' }, confirms: [], audiences: [], searches: [], failConfirm: false, failSave: false };
  await page.route('**/api/admin/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.startsWith('/api/admin/catalog/')) return route.fallback();
    if (path === '/api/admin/me') {
      state.meCalls++;
      return route.fulfill(state.meUnavailable ? { status: 503, json: {} } : { json: { subject_id: state.subject, role: state.role, permissions: [] } });
    }
    if (path === '/api/admin/campaigns') return route.fulfill({ json: { items: [state.campaign] } });
    if (path === '/api/admin/coupons') return route.fulfill({ json: { items: [{ id: '22222222-2222-4222-8222-222222222222', code: 'EXISTING', revision: '1', redemption_available: false }] } });
    if (path.startsWith('/api/admin/coupons/')) {
      await state.couponHold;
      return route.fulfill({ json: {} });
    }
    if (path === '/api/admin/campaigns/save') {
      state.campaign = { ...state.campaign, ...request.postDataJSON(), revision: '1' };
      if (state.failSave) return route.fulfill({ status: 503, json: {} });
      return route.fulfill({ json: state.campaign });
    }
    if (path === '/api/admin/users/search') { state.searches.push(request.postDataJSON()); return route.fulfill({ json: { items: [], has_more: false } }); }
    if (path === '/api/admin/campaigns/preview') return route.fulfill({ json: state.campaign });
    if (path === '/api/admin/campaigns/read') return route.fulfill({ json: state.campaign });
    if (path === '/api/admin/campaigns/audience') { state.audiences.push(request.postDataJSON()); return route.fulfill({ json: { review_id: '33333333-3333-4333-8333-333333333333', recipient_count: 1, revision: '1', count_as_of: 'synthetic', expires_at: 'synthetic' } }); }
    if (path === '/api/admin/campaigns/confirm') {
      state.confirms.push(request.postDataJSON());
      await state.confirmHold;
      return route.fulfill(state.failConfirm ? { status: 503, json: {} } : { json: { state: 'queued' } });
    }
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto('/auth/admin?view=' + section);
  await expect(page.getByRole('button', { name: 'Verify access', exact: true })).toBeVisible();
  return state;
}
async function refresh(page, event = 'TOKEN_REFRESHED') {
  await page.evaluate(event => window.__emit(event, { ...window.__session, access_token: 'refreshed-synthetic' }), event);
}

test('same-account refresh retains unsaved campaigns and authority outages suspend instead of erase', async ({ page }) => {
  const state = await admin(page);
  await page.getByRole('button', { name: 'New campaign draft', exact: true }).click();
  await page.getByLabel('Campaign name', { exact: true }).fill('Unfinished work');
  await refresh(page);
  await expect.poll(() => state.meCalls).toBeGreaterThan(1);
  await expect(page.getByLabel('Campaign name', { exact: true })).toHaveValue('Unfinished work');
  state.meUnavailable = true;
  await refresh(page, 'SIGNED_IN');
  await expect(page.getByRole('heading', { name: 'Administration unavailable', exact: true })).toBeVisible();
  await expect(page.getByLabel('Campaign name', { exact: true })).toHaveCount(1);
  await expect(page.getByLabel('Campaign name', { exact: true })).not.toBeVisible();
  state.meUnavailable = false;
  await page.getByRole('button', { name: 'Retry access check', exact: true }).click();
  await expect(page.getByLabel('Campaign name', { exact: true })).toHaveValue('Unfinished work');
  await expect(page.getByLabel('Campaign name', { exact: true })).toBeVisible();
  state.subject = 'different-user';
  await page.evaluate(() => window.__emit('SIGNED_IN', { access_token: 'different', user: { id: 'different-user' } }));
  await expect(page.getByRole('button', { name: 'New campaign draft', exact: true })).toBeVisible();
  await expect(page.getByLabel('Campaign name', { exact: true })).toHaveCount(0);
});

test('refresh during uncertain confirmation preserves the exact retry identity', async ({ page }) => {
  const state = await admin(page);
  await page.getByRole('combobox', { name: /^Existing campaign/ }).selectOption(state.campaign.campaign_id);
  await page.getByRole('button', { name: 'Preview saved revision', exact: true }).click();
  await page.getByRole('button', { name: 'Review audience and count', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Confirm promotional campaign', exact: true });
  await expect(dialog).toBeVisible();
  let release;
  state.confirmHold = new Promise(resolve => { release = resolve; }); state.failConfirm = true;
  await dialog.getByRole('button', { name: 'Confirm campaign send', exact: true }).click();
  await expect.poll(() => state.confirms.length).toBe(1);
  await refresh(page);
  await expect.poll(() => state.meCalls).toBeGreaterThan(1);
  release();
  await expect(dialog.getByRole('button', { name: 'Confirm campaign send', exact: true })).toBeEnabled();
  state.failConfirm = false; state.confirmHold = null;
  await dialog.getByRole('button', { name: 'Confirm campaign send', exact: true }).click();
  await expect.poll(() => state.confirms.length).toBe(2);
  expect(state.confirms[1]).toEqual(state.confirms[0]);
  await expect(dialog).not.toBeVisible();
});

test('campaign audience is bound to the displayed revision and uncertain first save can be recovered', async ({ page }) => {
  const state = await admin(page);
  await page.getByRole('combobox', { name: /^Existing campaign/ }).selectOption(state.campaign.campaign_id);
  await page.getByRole('button', { name: 'Preview saved revision', exact: true }).click();
  await page.getByRole('button', { name: 'Review audience and count', exact: true }).click();
  expect(state.audiences).toEqual([{ campaign_id: state.campaign.campaign_id, revision: '1' }]);
  await page.getByRole('dialog', { name: 'Confirm promotional campaign', exact: true }).getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('button', { name: 'New campaign draft', exact: true }).click();
  await page.getByLabel('Campaign name', { exact: true }).fill('Committed without response');
  await page.getByLabel('Email subject', { exact: true }).fill('Synthetic subject');
  await page.getByLabel('Plain-text message', { exact: true }).fill('Synthetic body');
  state.failSave = true;
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Refresh campaign results', exact: true })).toBeEnabled();
  state.failSave = false;
  const read = page.waitForRequest(request => request.url().endsWith('/api/admin/campaigns/read'));
  await page.getByRole('button', { name: 'Refresh campaign results', exact: true }).click();
  await read;
  await expect(page.getByLabel('Campaign name', { exact: true })).toHaveValue('Committed without response');
  await page.getByRole('button', { name: 'Preview saved revision', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Campaign preview', exact: true })).toContainText('Revision 1.');
});

test('account switch clears customer search before the replacement account loads', async ({ page }) => {
  const state = await admin(page, 'users');
  await page.getByLabel('Exact customer email or account ID', { exact: true }).fill('private-old-account@example.test');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect.poll(() => state.searches.length).toBe(1);
  await page.evaluate(() => window.__emit('SIGNED_OUT', null));
  state.subject = 'replacement-operator';
  await page.evaluate(() => window.__emit('SIGNED_IN', { access_token: 'replacement', user: { id: 'replacement-operator' } }));
  await expect(page.getByLabel('Exact customer email or account ID', { exact: true })).toHaveValue('');
  expect(state.searches).toHaveLength(1);
});

test('coupon replacement is locked until its save finishes', async ({ page }) => {
  const state = await admin(page, 'coupons');
  await page.getByRole('button', { name: 'Create inert coupon draft', exact: true }).click();
  await page.getByLabel('Inert coupon code (uppercase)', { exact: true }).fill('PRIVATE');
  let release;
  state.couponHold = new Promise(resolve => { release = resolve; });
  await page.getByRole('button', { name: 'Save inert draft', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Create inert coupon draft', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Edit inert draft', exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole('button', { name: 'Create inert coupon draft', exact: true })).toBeEnabled();
});

test('loss of current Super-admin authority hides restricted work', async ({ page }) => {
  const state = await admin(page, 'coupons');
  await page.getByRole('button', { name: 'Create inert coupon draft', exact: true }).click();
  state.role = 'admin';
  await refresh(page);
  await expect(page.getByRole('heading', { name: 'Page not found', exact: true })).toBeVisible();
  await expect(page.getByLabel('Inert coupon code (uppercase)', { exact: true })).toHaveCount(0);
});


test('successor sign-in retains its acceptance destination', async ({ page }) => {
  await setup(page, { signed: false });
  await page.goto('/auth/admin/successor');
  await expect(page.getByRole('link', { name: 'Sign in with the designated existing account', exact: true })).toHaveAttribute('href', '/auth/login?next=/auth/admin/successor');
});


test('scroll helper rejects movement caused by the first boundary wheel', async ({ page }) => {
  await page.setContent(`<style>body{margin:0}#admin-content{height:600px;overflow-y:hidden}dialog{height:240px;width:300px;overscroll-behavior-y:none;overflow-y:auto}section{height:700px}</style><main id="admin-content"><div style="height:1000px"></div></main><dialog aria-label="Synthetic scroll probe"><h2>Probe</h2><section>Long synthetic content</section></dialog>`);
  const dialog = page.getByRole('dialog', { name: 'Synthetic scroll probe', exact: true });
  await page.locator('dialog').evaluate(el => { el.showModal(); el.addEventListener('wheel', event => { if (event.deltaY < 0) { window.__firstEdgeMoved = true; el.style.transform = 'translateY(4px)'; } }); });
  await expect(checkDialogScroll(page, dialog, { requireScroll: true })).rejects.toThrow();
  expect(await page.evaluate(()=>window.__firstEdgeMoved)).toBe(true);
});
