import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve('..', 'tmp', 'c12-billing-email-redesign');
const variants = [
  ['billing_payment', 'Payment received'],
  ['billing_renewal', 'Your subscription is renewed'],
];

class ReceiptPreview {
  constructor(page) { this.page = page; }

  async open(kind, blocked) {
    // These are local HTML fixtures and local raster assets only.
    await this.page.route(/^https?:\/\//, route => route.abort());
    await this.page.goto(pathToFileURL(resolve(root, 'previews', `${kind}${blocked ? '-images-blocked' : ''}.html`)).href);
    await this.page.waitForFunction(() => [...document.images].every(image => image.complete));
  }

  async verify(heading, blocked) {
    await expect(this.page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    await expect(this.page.getByText('INR 470.82', { exact: true })).toBeVisible();
    await expect(this.page.getByText('SYNTHETIC C12 TEST', { exact: false })).toBeVisible();
    await expect(this.page.getByText('This payment receipt is not a GST tax invoice.', { exact: true })).toBeVisible();
    await expect(this.page.getByRole('link', { name: 'View your account', exact: true })).toHaveAttribute('href', 'http://localhost:5173/auth/dashboard');
    const dimensions = await this.page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth > innerWidth,
      imageWidths: [...document.images].map(image => image.naturalWidth),
      tableMax: Math.max(...[...document.querySelectorAll('table')].map(table => table.getBoundingClientRect().width)),
      cardWidth: document.querySelector('table[bgcolor="#ffffff"]').getBoundingClientRect().width,
    }));
    expect(dimensions.overflow).toBe(false);
    expect(dimensions.cardWidth).toBeLessThanOrEqual(600);
    expect(dimensions.tableMax).toBeLessThanOrEqual(Math.min(800, await this.page.evaluate(() => innerWidth)));
    expect(dimensions.imageWidths).toHaveLength(2);
    expect(dimensions.imageWidths.every(width => blocked ? width === 0 : width > 0)).toBe(true);
  }
}

for (const [kind, heading] of variants) {
  for (const width of [800, 600, 390]) {
    for (const blocked of [false, true]) {
      test(`${kind} at ${width}px, images ${blocked ? 'blocked' : 'loaded'}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 });
        const receipt = new ReceiptPreview(page);
        await receipt.open(kind, blocked);
        await receipt.verify(heading, blocked);
        await mkdir(resolve(root, 'screenshots'), { recursive: true });
        await page.screenshot({ path: resolve(root, 'screenshots', `${kind}-${width}${blocked ? '-images-blocked' : ''}.png`), fullPage: true });
      });
    }
  }
}
