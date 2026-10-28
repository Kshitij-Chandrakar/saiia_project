import { test, expect } from '@playwright/test';
const config = process.env.CATALOG_BROWSER_NATIVE ? JSON.parse(process.env.CATALOG_BROWSER_NATIVE) : null;
test('browser JWT native lifecycle: review publish replace retire', async ({
  page
}, info) => {
  test.skip(!config, 'Requires explicit disposable native lifecycle runner');
  await page.route('**/src/auth/supabaseClient.js*', r => r.fulfill({
    contentType: 'application/javascript',
    body: `export const supabase={auth:{getSession:async()=>({data:{session:{access_token:${JSON.stringify(config?.token)},user:{id:'10000000-0000-4000-8000-000000000001'}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}};export function getSupabaseAuthConfig(){return {}};`
  }));
  await page.route('**/api/**', async r => {
    const response = await r.fetch({
      url: config.url + new URL(r.request().url()).pathname
    });
    await r.fulfill({
      response
    });
  });
  const button = name => page.getByRole('button', {
    name,
    exact: true
  });
  await page.goto('/auth/admin/subscriptions');
  await page.getByLabel('Open a draft by ID', {
    exact: true
  }).fill(config.draft_id);
  await button('Open draft').click();
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveValue('Synthetic contract');
  async function review(action) {
    await button('Preview saved draft').click();
  await button('Close subscription review').click();
    await page.getByLabel('Publication action', {
      exact: true
    }).selectOption(action);
    await page.getByLabel('Offer starts at (IST)', {
      exact: true
    }).fill('2026-01-01T00:00');
    await page.getByLabel('Lifecycle reason', {
      exact: true
    }).fill('Synthetic native browser lifecycle');
    await button('Review for publication').click();
    const dialog = page.getByRole('dialog', {
      name: 'Subscription review',
      exact: true
    });
    await expect(dialog).toContainText('USD 10.00');
    if (action === 'replace') await expect(dialog.getByRole('region', {
      name: 'Existing offer'
    })).toContainText('version 1');
    await button('Confirm review').click();
    await expect(button(action === 'replace' ? 'Replace reviewed offer' : 'Publish reviewed offer')).toBeVisible();
  }
  await review('publish');
  await button('Publish reviewed offer').click();
  await expect(page.getByRole('dialog', {
    name: 'Publish this offer?',
    exact: true
  })).toBeVisible();
  await button('Confirm publication').click();
  await expect(page.getByRole('heading', {
    name: 'Published offer · version 1',
    exact: true
  })).toBeVisible();
  await button('Create a new draft version').click();
  await page.getByLabel('Display name', {
    exact: true
  }).fill('Synthetic successor');
  await page.getByLabel('Change reason', {
    exact: true
  }).fill('Synthetic replacement draft');
  await button('Save draft').click();
  await expect(button('Save changes')).toBeVisible();
  await review('replace');
  await button('Replace reviewed offer').click();
  const replacing = page.getByRole('dialog', {
    name: 'Replace this offer?',
    exact: true
  });
  await expect(replacing).toContainText('Synthetic successor');
  await button('Confirm replacement').click();
  await expect(page.getByRole('heading', {
    name: 'Published offer · version 2',
    exact: true
  })).toBeVisible();
  await page.screenshot({
    path: info.outputPath('native-replacement-desktop.png'),
    fullPage: true
  });
  await button('Retire this offer').click();
  await expect(page.getByRole('dialog', {
    name: 'Retire this offer?',
    exact: true
  })).toContainText('Version 2');
  await button('Confirm retirement').click();
  await expect(page.getByRole('heading', {
    name: 'Retired offer · version 2',
    exact: true
  })).toBeVisible();
  await page.setViewportSize({
    width: 390,
    height: 844
  });
  await page.screenshot({
    path: info.outputPath('native-retired-mobile.png'),
    fullPage: true
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  // Test-only session source switches to a different genuinely verified JWT.
  // The authoritative SQL probe must deny it, before any private UI renders.
  await page.route('**/src/auth/supabaseClient.js*', r => r.fulfill({
    contentType: 'application/javascript',
    body: `export const supabase={auth:{getSession:async()=>({data:{session:{access_token:${JSON.stringify(config.ordinary_token)},user:{id:${JSON.stringify(config.ordinary_subject)}}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}};export function getSupabaseAuthConfig(){return {}};`
  }));
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Page not found', exact: true })).toBeFocused();
  await expect(page).toHaveTitle('Page not found | Intervucopilot');
  await expect(page.getByRole('region', { name: 'Offer lifecycle', exact: true })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('native-non-admin-404-mobile.png') });
});
