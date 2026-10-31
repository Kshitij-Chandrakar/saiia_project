import { test, expect } from '@playwright/test';
const config = process.env.CATALOG_BROWSER_NATIVE ? JSON.parse(process.env.CATALOG_BROWSER_NATIVE) : null;
test('approved Free import save reopen edit preview over JWT native PostgreSQL', async ({
  page
}, info) => {
  test.skip(!config, 'Requires explicit disposable Free browser runner');
  await page.route('**/src/auth/supabaseClient.js*', r => r.fulfill({
    contentType: 'application/javascript',
    body: `export const supabase={auth:{getSession:async()=>({data:{session:{access_token:${JSON.stringify(config?.token)},user:{id:'10000000-0000-4000-8000-000000000001'}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}};export function getSupabaseAuthConfig(){return {}};`
  }));
  let loseResponse = true;
  const keys = [];
  let writes = 0;
  let reads = 0;
  await page.route('**/api/**', async r => {
    const q = r.request();
    if (q.method() === 'GET' && new URL(q.url()).pathname.includes('/drafts/')) reads++;
    const create = q.method() === 'POST' && new URL(q.url()).pathname.endsWith('/drafts');
    if (q.method() === 'PATCH' || create) writes++;
    if (create) keys.push(q.headers()['idempotency-key']);
    const response = await r.fetch({
      url: config.url + new URL(q.url()).pathname
    });
    if (create && loseResponse) {
      loseResponse = false;
      await r.abort('failed');
    } else await r.fulfill({
      response
    });
  });
  const button = name => page.getByRole('button', {
    name,
    exact: true
  });
  await page.goto('/auth/admin/subscriptions');
  await button('Import approved Free draft').click();
  expect(writes).toBe(0);
  await expect(button('Import approved Free draft')).toBeDisabled();
  await page.getByLabel('Change reason', {
    exact: true
  }).fill('Approved Free synthetic acceptance');
  await button('Save draft').click();
  await expect(page.getByRole('alert')).toContainText('not confirmed');
  await button('Retry same save').click();
  await expect.poll(() => keys.length).toBe(2);
  expect(keys[0]).toBe(keys[1]);
  await expect(button('Save changes')).toBeVisible();
  await button('Open draft').click();
  await button('Preview saved draft').click();
  expect(reads).toBe(1);
  const preview = page.getByRole('region', {
    name: 'Draft preview'
  });
  await expect(preview).toContainText('600 second(s) per day');
  await expect(preview).toContainText('5 save(s) per month');
  await expect(preview).toContainText('Unlimited');
  await expect(preview.locator('s')).toHaveText('Introducing Sketch');
  await expect(preview.getByRole('button', {
    name: 'Preview Clipboard unavailable'
  })).toHaveCount(0);
  await preview.getByRole('button', {
    name: 'About Clipboard',
    exact: true
  }).focus();
  await expect(preview.getByRole('tooltip').filter({
    hasText: 'Clipboard lets'
  })).toBeVisible();
  await button('Close subscription review').click();
  await button('Usage & presentation').click();
  const beforeInvalid = writes;
  await page.getByLabel('Amount clipboard.new_saves (save)', {
    exact: true
  }).fill('1.5');
  await page.getByLabel('Change reason', {
    exact: true
  }).fill('Invalid synthetic edit');
  await button('Save changes').click();
  await expect(page.getByRole('alert')).toBeVisible();
  expect(writes).toBe(beforeInvalid);
  await page.getByLabel('Amount clipboard.new_saves (save)', {
    exact: true
  }).fill('5');
  await page.getByLabel('Label clipboard.saved_answers', {
    exact: true
  }).fill('Personal Clipboard');
  await page.getByLabel('Change reason', {
    exact: true
  }).fill('Synthetic metadata edit');
  await button('Save changes').click();
  await button('Open draft').click();
  await button('Preview saved draft').click();
  expect(reads).toBe(2);
  await expect(preview.getByRole('button', {
    name: 'About Personal Clipboard',
    exact: true
  })).toBeVisible();
  await page.screenshot({
    path: info.outputPath('free-desktop.png'),
    fullPage: true
  });
  await page.setViewportSize({
    width: 390,
    height: 844
  });
  await preview.getByRole('button', {
    name: 'About Personal Clipboard',
    exact: true
  }).click();
  await expect(preview.getByRole('tooltip').filter({
    hasText: 'Clipboard lets'
  })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: info.outputPath('free-mobile.png'),
    fullPage: true
  });
  await button('Close subscription review').click();
  await button('Close draft').click();
  await button('Import approved Free draft').click();
  await page.getByLabel('Change reason', {
    exact: true
  }).fill('Duplicate import attempt');
  await button('Save draft').click();
  await expect(page.getByRole('alert')).toContainText('free plan code already exists');
});
