import {test,expect} from '@playwright/test';
const url=process.env.CATALOG_VISUAL_URL;
test('compact pricing actual catalog responsive and accessible',async({page},info)=>{
 test.skip(!url,'Requires existing isolated manual catalog URL');
 for(const [width,height] of [[1440,900],[1366,768],[820,1000],[390,844]]) {
  await page.setViewportSize({width,height});await page.goto(url);
  const section=page.getByRole('region',{name:'Your next opportunity starts here.',exact:true});
  await expect(section.getByRole('article')).toHaveCount(3);
  await expect(section.getByRole('button',{name:/Preview/})).toHaveCount(0);
  await expect(section.locator('svg.lucide-eye')).toHaveCount(0);
  await expect(section.getByRole('region',{name:'Included in every plan'})).toBeVisible();
  const free=section.getByRole('article',{name:'Free plan'}),plus=section.getByRole('article',{name:'Plus plan'}),pro=section.getByRole('article',{name:'Pro plan'});
  await expect(free.locator('s')).toHaveText('Introducing Sketch');await expect(plus.locator('s')).toHaveCount(0);
  await expect(plus).toContainText('5 hours Auto Mode / month');
  for(const [card,copy] of [[free,'5 new saves per month'],[plus,'10 new saves per month'],[pro,'unlimited new saves']]) {
   await expect(card.getByText(/Clipboard saves/)).toHaveCount(1);
   const control=card.getByRole('button',{name:'About Clipboard',exact:true});
   await control.focus();const tooltip=card.getByRole('tooltip').filter({hasText:copy});await expect(tooltip).toBeVisible();const bounds=await tooltip.boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(width);await page.keyboard.press('Escape');await expect(control).toHaveAttribute('aria-expanded','false');
   await control.click();await expect(control).toHaveAttribute('aria-expanded','true');await page.keyboard.press('Escape');
  }
  await expect(free.getByRole('link',{name:'Get started'})).toHaveAttribute('href','/auth/signup');
  await expect(plus.getByRole('button',{name:'Checkout coming soon'})).toBeDisabled();
  for(const interval of ['Monthly','Yearly']) {
   await section.getByRole('button',{name:interval,exact:true}).click();
   await expect(plus).toContainText(interval==='Monthly'?'\u20b9399':'\u20b92,999');
   await expect(pro).toContainText(interval==='Monthly'?'\u20b9899':'\u20b96,499');
   await expect(plus).toContainText(interval==='Monthly'?'Total: \u20b9470.82':'Total: \u20b93,538.82');await expect(pro).toContainText(interval==='Monthly'?'Total: \u20b91,060.82':'Total: \u20b97,668.82');await expect(section.locator('.cp-saving')).toHaveCount(0);
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await section.screenshot({path:info.outputPath(`pricing-${width}-${interval.toLowerCase()}.png`)});
  }
 }
});
