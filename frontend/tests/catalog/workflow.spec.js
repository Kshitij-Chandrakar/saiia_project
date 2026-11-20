import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { setup, startPlan } from './fixtures/workspace.js';

const evidence=fileURLToPath(new URL('../../../docs/evidence/c15-commercial-workflow-20261106',import.meta.url));
class PlanWorkspace {
  constructor(page) { this.page=page; this.progress=page.getByRole('list',{name:'Plan setup'}); }
  async stage(name) { await expect(this.progress.locator('[aria-current=step]')).toHaveText(new RegExp(name)); }
  async capture(name) {
    await mkdir(evidence,{recursive:true});
    await this.page.evaluate(()=>{
      let note=document.querySelector('[data-workflow-fixture]');
      if(!note){note=document.createElement('p');note.dataset.workflowFixture='true';note.setAttribute('role','note');document.querySelector('#admin-content').prepend(note);}
      note.textContent='DESIGN PREVIEW / SYNTHETIC API FIXTURE';
      note.style.cssText='margin:0 0 16px;padding:10px 14px;border:1px solid #bacde4;background:#edf4fc;color:#194d87;border-radius:6px;font-size:12px;position:fixed;right:16px;bottom:12px;z-index:5;max-width:calc(100vw - 32px)';
    });
    expect(await this.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await this.page.screenshot({path:evidence+'/'+name+'.png'});
  }
}

for(const [width,height] of [[1440,900],[1366,768],[390,844]])test(`three clear stages, private saves and blockers at ${width}`,async({page})=>{
  await page.setViewportSize({width,height});const state=await setup(page);const ui=new PlanWorkspace(page);
  await ui.stage('Choose a plan');await expect(page.getByRole('region',{name:'Published plans'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Review for publication',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'New plan',exact:true}).click();
  const chooser=page.getByRole('region',{name:'Choose a starting point'});await expect(chooser.getByRole('button')).toHaveCount(4);
  await ui.capture(`stage-1-choose-${width}`);
  await chooser.getByRole('button',{name:'Start from Plus',exact:true}).click();
  await ui.stage('Edit and save');await expect(page.getByRole('region',{name:'Choose a starting point'})).toHaveCount(0);
  await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Plus');
  expect(state.writes).toBe(0);await expect(page.getByLabel('Plan code',{exact:true})).not.toBeVisible();
  await ui.capture(`stage-2-edit-${width}`);
  await page.getByLabel('Change reason',{exact:true}).fill('Synthetic workflow acceptance');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Draft saved.');await ui.stage('Review and publish');expect(state.writes).toBe(1);
  await page.getByRole('button',{name:'Preview saved draft',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Subscription review',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Close subscription review',exact:true}).click();
  await expect(page.getByRole('region',{name:'Saved preview result'})).toContainText('Before you can publish');
  await expect(page.getByRole('button',{name:'Review for publication',exact:true})).toBeDisabled();
  await page.getByRole('heading',{name:'Review and publish',exact:true}).evaluate(node=>node.scrollIntoView({block:'start'}));await ui.capture(`stage-3-review-${width}`);
  expect(state.writes).toBe(1);expect(state.previewRequests).toBe(1);
  await page.getByRole('button',{name:'Plan details',exact:true}).click();await page.getByLabel('Display name',{exact:true}).fill('Unsaved Plus changes');await ui.stage('Edit and save');
  await expect(page.getByRole('button',{name:'Review for publication',exact:true})).toBeDisabled();expect(state.writes).toBe(1);
});

test('required advanced errors reveal their field; failed save never advances',async({page})=>{
  const state=await setup(page),ui=new PlanWorkspace(page);await startPlan(page,'scratch',false);
  await page.getByLabel('Display name',{exact:true}).fill('Synthetic custom plan');await page.getByLabel('Change reason',{exact:true}).fill('Synthetic validation');
  await expect(page.getByLabel('Plan code',{exact:true})).not.toBeVisible();await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await expect(page.getByLabel('Plan code',{exact:true})).toBeVisible();await expect(page.getByLabel('Plan code',{exact:true})).toBeFocused();
  await page.getByLabel('Plan code',{exact:true}).fill('synthetic-custom');state.unavailable=true;await page.getByRole('button',{name:'Save draft',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Draft storage is unavailable');await ui.stage('Edit and save');expect(state.writes).toBe(0);
  state.unavailable=false;await page.getByRole('button',{name:'Retry same save',exact:true}).click();await expect(page.getByRole('status')).toContainText('Draft saved');await ui.stage('Review and publish');expect(state.writes).toBe(1);
});

test('changing starting plan requires explicit discard; resume stays a secondary disclosure',async({page})=>{
  const state=await setup(page);await expect(page.getByLabel('Open a draft by ID',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Resume a draft',exact:true}).click();await expect(page.getByLabel('Open a draft by ID',{exact:true})).toBeVisible();
  await startPlan(page,'Free');await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Free');
  await page.getByRole('button',{name:'New plan',exact:true}).click();await page.getByRole('button',{name:'Start from Pro',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Discard unsaved');await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Free');
  await page.getByRole('button',{name:'Keep editing',exact:true}).click();await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Free');
  await page.getByRole('button',{name:'Start from Pro',exact:true}).click();await page.getByRole('button',{name:'Discard edits and continue',exact:true}).click();
  await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Pro');expect(state.writes).toBe(0);
});
