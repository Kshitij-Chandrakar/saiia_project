import { test, expect } from '@playwright/test';
const config = process.env.CATALOG_BROWSER_NATIVE ? JSON.parse(process.env.CATALOG_BROWSER_NATIVE) : null;
test('native browser create read edit preview through accepted API', async ({
  page
}) => {
  test.skip(!config, 'Run explicit disposable PostgreSQL Python runner');
  await page.route('**/src/auth/supabaseClient.js*', r => r.fulfill({
    contentType: 'application/javascript',
    body: `export const supabase={auth:{getSession:async()=>({data:{session:{access_token:${JSON.stringify(config.token)},user:{id:'10000000-0000-4000-8000-000000000001'}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}};export function getSupabaseAuthConfig(){return {}};`
  }));
  await page.route('**/api/**', async r => {
    const response = await r.fetch({
      url: config.url + new URL(r.request().url()).pathname
    });
    await r.fulfill({
      response
    });
  });
  await page.goto('/auth/admin/subscriptions');
  await page.getByRole('button', {
    name: 'Create a blank draft',
    exact: true
  }).click();
  await page.getByLabel('Plan code', {
    exact: true
  }).fill('native-synthetic');
  await page.getByLabel('Display name', {
    exact: true
  }).fill('Native synthetic');
  await page.getByLabel('Change reason', {
    exact: true
  }).fill('Native browser fixture');
  await page.getByRole('button', {
    name: 'Save draft',
    exact: true
  }).click();
  await expect(page.getByRole('status')).toContainText('Revision 1');
  await page.getByLabel('Display name', {
    exact: true
  }).fill('Native revised');
  await page.getByLabel('Change reason', {
    exact: true
  }).fill('Native edit');
  await page.getByRole('button', {
    name: 'Save changes',
    exact: true
  }).click();
  await expect(page.getByRole('status')).toContainText('Revision 2');
  await page.getByRole('button', {
    name: 'Preview saved draft',
    exact: true
  }).click();
    await page.getByRole('button',{name:'Close subscription review',exact:true}).click();
  await expect(page.getByRole('complementary', {
    name: 'Draft preview'
  })).toContainText('Native revised');
  await expect(page.getByRole('complementary', {
    name: 'Draft preview'
  })).toContainText('Requirements to resolve');
});
