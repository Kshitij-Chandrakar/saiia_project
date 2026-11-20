import {expect} from '@playwright/test';

export async function checkDialogScroll(page, dialog, {port = dialog, name = 'dialog', requireScroll = false} = {}) {
  await expect(dialog).toBeVisible();
  expect(await dialog.evaluate(el => getComputedStyle(el).overscrollBehaviorY)).toBe('none');
  expect(await port.evaluate(el => getComputedStyle(el).overscrollBehaviorY)).toBe('none');
  expect(await page.locator('#admin-content').evaluate(el => getComputedStyle(el).overflowY)).toBe('hidden');
  const settle = () => port.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const snapshot = () => dialog.evaluate(el => {
    const box=el.getBoundingClientRect(),main=document.querySelector('#admin-content');
    return {x:box.x,y:box.y,width:box.width,height:box.height,background:main.scrollTop,window:window.scrollY,heading:el.querySelector('h2')?.getBoundingClientRect().y};
  });
  await page.evaluate(()=>document.fonts.ready);await settle();
  const background = await snapshot();
  const backgroundStable = async () => { const value = await snapshot(); expect(value.background).toBe(background.background); expect(value.window).toBe(background.window); };
  await port.evaluate(el => {el.scrollTop=0;});await settle();
  const bounds=await port.boundingBox();await page.mouse.move(bounds.x+Math.min(bounds.width/2,150),bounds.y+Math.min(bounds.height/2,100));
  const max=await port.evaluate(el => el.scrollHeight-el.clientHeight);
  if(requireScroll) expect(max).toBeGreaterThan(0);
  if(max>0){await page.mouse.wheel(0,160);await expect.poll(()=>port.evaluate(el=>el.scrollTop)).toBe(Math.min(160,max));}
  await backgroundStable();
  for(const edge of ['top','bottom']) {
    await port.evaluate((el,edge)=>{el.scrollTop=edge==='top'?0:el.scrollHeight;},edge);await settle();
    const before=await snapshot(),position=await port.evaluate(el=>el.scrollTop);
    await page.mouse.wheel(0,edge==='top'?-2000:2000);await settle();
    expect(await snapshot()).toEqual(before);await backgroundStable();
    for(let i=0;i<6;i++){await page.mouse.wheel(0,edge==='top'?-700:700);await settle();expect(await snapshot()).toEqual(before);expect(await port.evaluate(el=>el.scrollTop)).toBe(position);}
  }
  // Scrolling the backdrop must not move the content behind the modal either.
  const before=await snapshot();await page.mouse.move(2,2);for(let i=0;i<3;i++){await page.mouse.wheel(0,700);await settle();}expect(await snapshot()).toEqual(before);
  await backgroundStable();
  return {name,max_scroll:max,both_edges_stable:true,background_locked:true};
}
