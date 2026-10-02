import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

test('static Figma landing renders completely with local assets', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const errors = [];
  const failedAssets = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('response', response => {
    if (response.url().includes('/assets/') && response.status() >= 400) failedAssets.push(response.url());
  });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator('.landing-page')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Walk into everyinterview prepared.');
  const sections = ['hero', 'problem', 'how-it-works', 'features', 'platforms', 'trusted',
    'product', 'preparation', 'desktop', 'privacy', 'pricing', 'faq', 'get-started'];
  for (const id of sections) {
    await expect(page.locator(`.landing-page section#${id}`)).toBeVisible();
  }
  const assets = await page.locator('.landing-page img').evaluateAll(images =>
    images.filter(image => !image.closest('.platform-logo-sequence[aria-hidden="true"]'))
      .map(image => ({ src: image.currentSrc, loaded: image.complete && image.naturalWidth > 0,
      width: image.getBoundingClientRect().width, height: image.getBoundingClientRect().height })));
  expect(assets.every(asset => asset.loaded)).toBe(true);
  expect(assets.every(asset => asset.width > 0 && asset.height > 0)).toBe(true);
  expect(assets.every(asset => !asset.src.includes('figma.com'))).toBe(true);
  await expect(page.locator('.landing-page')).not.toContainText('(attach video here)');
  expect(errors).toEqual([]);
  expect(failedAssets).toEqual([]);
  const output = path.resolve('..', 'tmp', 'landing-check');
  await mkdir(output, { recursive: true });
  await expect.poll(() => page.locator('.hero-floating-card').evaluateAll(cards =>
    cards.every(card => card.getAnimations().every(animation => animation.playState === 'finished')))).toBe(true);
  await page.screenshot({ path: path.join(output, 'landing-desktop-1440.png') });
  await page.screenshot({ path: path.join(output, 'landing-viewport-1440.png') });
  await page.screenshot({ path: path.join(output, 'landing-fullpage-1440.png'), fullPage: true });
});

for (const [width, height, name] of [[390, 844, 'mobile-390'], [430, 932, 'mobile-430'],
  [768, 1024, 'tablet-768'], [1024, 900, 'tablet-1024']]) {
test(`${name} keeps landing content readable and navigation accessible`, async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator('.landing-page')).toBeVisible();
  const menu = page.getByRole('button', { name: /navigation menu/ });
  await expect(menu).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeHidden();
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.landing-header').getByRole('link', { name: 'Log in', exact: true })).toBeVisible();
  await expect(page.locator('.landing-header').getByRole('link', { name: 'Get Started', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toBeFocused();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await menu.click();
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Features', exact: true }).click();
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await page.evaluate(() => window.scrollTo(0, 0));
  const geometry = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
    viewport: document.documentElement.clientWidth,
    overflowingText: [...document.querySelectorAll('.landing-page p, .landing-page h1, .landing-page h3')]
      .filter(element => {
        const bounds = element.getBoundingClientRect();
        return bounds.width > 0 && !element.closest('#trusted, #platforms') &&
          (element.scrollWidth > element.clientWidth + 3 || bounds.left < -1 || bounds.right > innerWidth + 2);
      })
      .map(element => element.textContent),
    heroOverlap: (() => {
      const elements = [...document.querySelectorAll('.hero-floating-card, #hero .figma-57, #hero .figma-63')];
      return elements.some((element, index) => elements.slice(index + 1).some(other => {
        const a = element.getBoundingClientRect(), b = other.getBoundingClientRect();
        return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      }));
    })(),
  }));
  expect(geometry.width).toBe(geometry.viewport);
  expect(geometry.bodyWidth).toBeLessThanOrEqual(width);
  expect(geometry.overflowingText).toEqual([]);
  expect(geometry.heroOverlap).toBe(false);
  expect(errors).toEqual([]);
  const output = path.resolve('..', 'tmp', 'landing-check');
  await mkdir(output, { recursive: true });
  await page.screenshot({ path: path.join(output, `landing-${name}.png`), fullPage: true });
  await page.screenshot({ path: path.join(output, `landing-${name}-viewport.png`) });
  await page.getByRole('tab', { name: 'AI Guidance', exact: true }).click();
  await expect(page.getByRole('tabpanel').locator('h3')).toHaveText('Know what to practice before the next round.');
  const preparation = page.getByRole('region', { name: 'Preparation steps' });
  await preparation.getByRole('button', { name: 'Next preparation step' }).click();
  await expect(preparation).toHaveAttribute('data-active-card', '02');
  await expect(preparation.locator('[aria-current="step"] h3')).toHaveText('Set your job target');
});
}

test('preparation arrows navigate all Figma cards and wrap in both directions', async ({ page }) => {
  await page.goto('/');
  const slider = page.getByRole('region', { name: 'Preparation steps' });
  const next = slider.getByRole('button', { name: 'Next preparation step' });
  const previous = slider.getByRole('button', { name: 'Previous preparation step' });
  const titles = ['Upload your resume', 'Set your job target', 'Connect desktop app',
    'Capture live questions', 'Receive AI guidance', 'Review and iterate'];
  for (let index = 0; index < titles.length; index += 1) {
    const number = String(index + 1).padStart(2, '0');
    await expect(slider).toHaveAttribute('data-active-card', number);
    await expect(slider.locator('[aria-current="step"] h3')).toHaveText(titles[index]);
    await expect(slider.locator('.preparation-card')).toHaveCount(3);
    const neighbors = await slider.locator('.preparation-card').evaluateAll(cards =>
      cards.map(card => card.dataset.cardNumber));
    expect(neighbors).toEqual([
      String((index + 5) % 6 + 1).padStart(2, '0'), number,
      String((index + 1) % 6 + 1).padStart(2, '0'),
    ]);
    await expect.poll(() => slider.locator('img').evaluateAll(images =>
      images.every(image => image.complete && image.naturalWidth > 0))).toBe(true);
    await next.click();
  }
  await expect(slider).toHaveAttribute('data-active-card', '01');
  await previous.focus();
  await page.keyboard.press('Enter');
  await expect(slider).toHaveAttribute('data-active-card', '06');
  await next.focus();
  await page.keyboard.press('Space');
  await expect(slider).toHaveAttribute('data-active-card', '01');
});

test('workflow cycles, pauses on hover or focus, and updates exact Figma details', async ({ page }) => {
  await page.clock.install();
  await page.goto('/');
  const workflow = page.locator('#how-it-works');
  const names = ['Your Resume', 'Target Role', 'Live Interview', 'AI Guidance', 'Session Insights'];
  const titles = ['Your experience becomes structured context.', 'Your preparation adapts to the role.',
    'Relevant context during the session.', 'Guidance grounded in your experience.', 'Learn from every interview.'];
  for (let index = 0; index < names.length; index += 1) {
    await expect(workflow.getByRole('button', { name: names[index], exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#workflow-detail .figma-105')).toHaveText(titles[index]);
    await page.clock.runFor(2000);
  }
  await expect(workflow.getByRole('button', { name: 'Your Resume', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await workflow.getByRole('button', { name: 'Live Interview', exact: true }).locator('img').click();
  await page.clock.runFor(12000);
  await expect(page.locator('#workflow-detail .figma-105')).toHaveText(titles[2]);
  await page.evaluate(() => document.activeElement.blur());
  await page.clock.runFor(4000);
  await expect(page.locator('#workflow-detail .figma-105')).toHaveText(titles[2]);
  await page.mouse.move(0, 0);
  await page.clock.runFor(2000);
  await expect(page.locator('#workflow-detail .figma-105')).toHaveText(titles[3]);
  const target = workflow.getByRole('button', { name: 'Target Role', exact: true });
  await target.focus();
  await page.keyboard.press('Space');
  await page.clock.runFor(8000);
  await expect(page.locator('#workflow-detail .figma-105')).toHaveText(titles[1]);
  await workflow.getByRole('button', { name: 'Session Insights', exact: true }).focus();
  await page.clock.runFor(4000);
  await expect(page.locator('#workflow-detail .figma-105')).toHaveText(titles[1]);
  await page.keyboard.press('Enter');
  await expect(page.locator('#workflow-detail .figma-105')).toHaveText(titles[4]);
  await page.evaluate(() => document.activeElement.blur());
  await page.clock.runFor(2000);
  await expect(page.locator('#workflow-detail .figma-105')).toHaveText(titles[0]);
  await workflow.getByRole('button', { name: 'Intervucopilot core engine', exact: true }).click();
  await expect(page.locator('#workflow-detail .figma-105')).toHaveText('One engine connecting your interview context.');
});

test('workflow reduced motion disables autoplay but preserves manual selection', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.clock.install();
  await page.goto('/');
  await page.clock.runFor(20000);
  const workflow = page.locator('#how-it-works');
  await expect(workflow.getByRole('button', { name: 'Your Resume', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await workflow.getByRole('button', { name: 'AI Guidance', exact: true }).click();
  await page.mouse.move(0, 0);
  await page.clock.runFor(12000);
  await expect(page.locator('#workflow-detail .figma-105')).toHaveText('Guidance grounded in your experience.');
});

test('feature tabs cycle every two seconds and continue from manual selection', async ({ page }) => {
  await page.clock.install();
  await page.clock.pauseAt(await page.evaluate(() => Date.now()));
  await page.goto('/');
  const section = page.locator('#features');
  const names = ['Resume', 'Job Match', 'Live Assist', 'AI Guidance'];
  const titles = ['Turn your experience into interview-ready answers.', 'Prepare for the role, not just the interview.',
    'Stay grounded when the interview gets tough.', 'Know what to practice before the next round.'];
  for (let index = 0; index < names.length; index += 1) {
    await expect(section.getByRole('tab', { name: names[index], exact: true })).toHaveAttribute('aria-selected', 'true');
    await expect(section.getByRole('tabpanel').locator('h3')).toHaveText(titles[index]);
    expect(await section.locator('.feature-tab-card').evaluateAll(cards => cards.map(card => card.dataset.cardNumber)))
      .toEqual([String((index + 3) % 4 + 1).padStart(2, '0'), String(index + 1).padStart(2, '0'), String((index + 1) % 4 + 1).padStart(2, '0')]);
    await expect.poll(() => section.locator('img').evaluateAll(images => images.every(image => image.complete && image.naturalWidth > 0))).toBe(true);
    await page.clock.runFor(2200);
  }
  await expect(section.getByRole('tab', { name: 'Resume', exact: true })).toHaveAttribute('aria-selected', 'true');
  await section.getByRole('tab', { name: 'Live Assist', exact: true }).click();
  await expect(section.getByRole('tabpanel').locator('h3')).toHaveText(titles[2]);
  await page.clock.runFor(1900);
  await expect(section.getByRole('tabpanel').locator('h3')).toHaveText(titles[2]);
  await page.clock.runFor(300);
  await expect(section.getByRole('tabpanel').locator('h3')).toHaveText(titles[3]);
});

test('feature tabs preserve manual keyboard selection with reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.clock.install();
  await page.goto('/');
  const section = page.locator('#features');
  await page.clock.runFor(15000);
  await expect(section.getByRole('tab', { name: 'Resume', exact: true })).toHaveAttribute('aria-selected', 'true');
  await section.getByRole('tab', { name: 'Job Match', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(section.getByRole('tab', { name: 'Job Match', exact: true })).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('ArrowRight');
  await expect(section.getByRole('tab', { name: 'Live Assist', exact: true })).toBeFocused();
  await page.keyboard.press('End');
  await expect(section.getByRole('tab', { name: 'AI Guidance', exact: true })).toHaveAttribute('aria-selected', 'true');
  await section.getByRole('tab', { name: 'Resume', exact: true }).focus();
  await page.keyboard.press('Space');
  await page.clock.runFor(15000);
  await expect(section.getByRole('tab', { name: 'Resume', exact: true })).toHaveAttribute('aria-selected', 'true');
});

test('desktop route retains its separate application', async ({ page }) => {
  await page.goto('/desktop');
  await expect(page.locator('.landing-page')).toHaveCount(0);
  await expect(page.locator('#root')).not.toBeEmpty();
});

test('platform marquee loops only on mobile and shows all logos with reduced motion', async ({ page }) => {
  await page.goto('/');
  const track = page.locator('.platform-marquee-track');
  const duplicate = page.locator('.platform-logo-sequence[aria-hidden="true"]');
  await expect(duplicate).toBeHidden();
  expect(await track.evaluate(element => element.getAnimations().length)).toBe(0);
  for (const width of [390, 430, 768]) {
    await page.setViewportSize({ width, height: 900 });
    const loop = await track.evaluate(element => {
      const animation = element.getAnimations()[0];
      animation.pause();
      animation.currentTime = 0;
      const groups = [...element.children];
      const start = groups[0].getBoundingClientRect().left;
      const groupWidth = groups[0].getBoundingClientRect().width;
      const matchingWidths = Math.abs(groupWidth - groups[1].getBoundingClientRect().width) < .1;
      animation.currentTime = 11000;
      const midpoint = groups[0].getBoundingClientRect().left;
      animation.currentTime = 21999;
      const boundary = groups[1].getBoundingClientRect().left;
      animation.play();
      return { duration: animation.effect.getTiming().duration, matchingWidths,
        halfLoopDistance: start - midpoint, groupWidth, boundaryDifference: Math.abs(start - boundary),
        overflow: getComputedStyle(element.parentElement).overflowX,
        localAssets: [...element.querySelectorAll('img')].every(image => !image.src.includes('figma.com')) };
    });
    expect(loop.duration).toBe(22000);
    expect(loop.matchingWidths).toBe(true);
    expect(loop.halfLoopDistance).toBeCloseTo(loop.groupWidth / 2, 1);
    expect(loop.boundaryDifference).toBeLessThan(.1);
    expect(loop.overflow).toBe('hidden');
    expect(loop.localAssets).toBe(true);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    expect(await track.evaluate(element => element.getAnimations().length)).toBe(0);
    await expect(duplicate).toBeHidden();
    expect(await page.locator('.platform-logo-sequence').first().evaluate(element => {
      const container = element.parentElement.parentElement.getBoundingClientRect();
      return [...element.children].every(logo => {
        const bounds = logo.getBoundingClientRect();
        return bounds.left >= container.left && bounds.right <= container.right &&
          bounds.top >= container.top && bounds.bottom <= container.bottom;
      });
    })).toBe(true);
    expect(await page.evaluate(() => document.body.scrollWidth <= innerWidth)).toBe(true);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
  }
});
