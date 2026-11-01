import { test, expect } from '@playwright/test';

test('shared presentation: exclusion, included Clipboard, hover focus tap and no adjacent action', async ({ page }) => {
  await page.goto('/');
  await page.evaluate(async () => {
    const react = await import('/node_modules/.vite/deps/react.js');
    const React = react.default || react;
    const client = await import('/node_modules/.vite/deps/react-dom_client.js');
    const createRoot = client.createRoot || client.default.createRoot;
    const { default: Feature } = await import('/src/auth/CatalogFeaturePresentation.jsx');
    const host = document.createElement('div'); document.body.replaceChildren(host);
    window.presentationClicks = 0;
    createRoot(host).render(React.createElement('section', { onClick: () => window.presentationClicks++ },
      React.createElement(Feature, { label: 'Introducing Sketch', included: false, information: 'Synthetic Sketch information' }),
      React.createElement(Feature, { label: 'Clipboard', included: true, information: 'Synthetic Clipboard information' })));
  });
  const sketch = page.getByRole('button', { name: 'About Introducing Sketch', exact: true });
  await expect(page.locator('s')).toHaveText('Introducing Sketch');
  await expect(page.getByRole('button', { name: 'Preview Clipboard unavailable', exact: true })).toHaveCount(0);
  await sketch.hover(); await expect(page.getByRole('tooltip').filter({ hasText: 'Synthetic Sketch' })).toBeVisible();
  await page.mouse.move(0, 500);
  const clipboard = page.getByRole('button', { name: 'About Clipboard', exact: true });
  await clipboard.focus(); await expect(page.getByRole('tooltip').filter({ hasText: 'Synthetic Clipboard' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('tooltip').filter({ hasText: 'Synthetic Clipboard' })).not.toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await clipboard.click(); await expect(clipboard).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('tooltip').filter({ hasText: 'Synthetic Clipboard' })).toBeVisible();
  expect(await page.evaluate(() => window.presentationClicks)).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('reusable policy renderer fits the existing landing pricing section without activating offers', async ({page})=>{
  await page.route('**/api/catalog', r => r.fulfill({json:{catalog_revision:'1',offers:[]}}));
  await page.goto('/');
  const pricing=page.locator('section#pricing');
  await expect(pricing).toContainText('Your next opportunity starts here.');
  await expect(pricing).toContainText('No published plans are available yet.');
  await expect(pricing).not.toContainText('Save 33%');
  await page.evaluate(async()=>{
    const react=await import('/node_modules/.vite/deps/react.js'),React=react.default||react;
    const client=await import('/node_modules/.vite/deps/react-dom_client.js');
    const {default:Preview}=await import('/src/auth/CatalogPolicyPreview.jsx');
    const {default:terms}=await import('/src/auth/approvedFreeTerms.json');
    const host=document.createElement('div');host.id='pricing-test-fixture';host.style.cssText='max-width:340px;width:100%;margin:auto;padding:16px;box-sizing:border-box';
    document.querySelector('section#pricing').append(host);
    (client.createRoot||client.default.createRoot)(host).render(React.createElement(Preview,{terms}));
  });
  const fixture=page.locator('#pricing-test-fixture');
  for(const width of [1280,390]){
    await page.setViewportSize({width,height:844});await fixture.scrollIntoViewIfNeeded();
    await expect(fixture).toContainText('600 second(s) per day');
    await expect(fixture.locator('s')).toHaveText('Introducing Sketch');
    await expect(fixture.getByRole('button',{name:'Preview Clipboard unavailable'})).toHaveCount(0);
    expect(await fixture.evaluate(e=>e.scrollWidth<=e.clientWidth)).toBe(true);
  }
});
