import { createHmac } from 'node:crypto';
import { chromium, expect } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
const configuration = JSON.parse(process.env.C15_ADMIN_FIXTURES);
const evidence = process.env.C15_ADMIN_EVIDENCE;
const base = process.env.C15_ADMIN_BROWSER;
const full = process.env.C15_ADMIN_FULL_APP === 'true';
const prefix = full ? 'full-' : '';
function totp(secret) {
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';let bits='';
  for(const char of secret.toUpperCase().replaceAll('=','')) bits+=alphabet.indexOf(char).toString(2).padStart(5,'0');
  const bytes=Buffer.from((bits.match(/.{8}/g)||[]).map(byte=>parseInt(byte,2)));
  const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
  const digest=createHmac('sha1',bytes).update(counter).digest();const offset=digest[19]&15;
  return String((digest.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');
}
const usedCodes=new Map();
async function stepUp(page,user) {
  if (!await page.getByLabel('Authenticator code',{exact:true}).isVisible()) await page.getByRole('button',{name:/^(Verify access|Verified)$/}).click();
  for(let attempt=0;attempt<2;attempt++) {
    // Actual Auth counters cannot be reused across independent browser sessions.
    if(usedCodes.get(user.email)===totp(user.factor_secret)) await page.waitForTimeout(30100-Date.now()%30000);
    const code=totp(user.factor_secret);usedCodes.set(user.email,code);
    await page.getByLabel('Authenticator code',{exact:true}).fill(code);
    const verified=page.waitForResponse(response=>new URL(response.url()).pathname.endsWith('/verify') && response.request().method()==='POST');
    await page.getByRole('button',{name:'Verify authenticator',exact:true}).click();
    if((await verified).status()===200) {await expect(page.getByLabel('Authenticator code',{exact:true})).toHaveValue('');return;}
  }
  throw Error('authenticator_verification_failed');
}
class ConsolePage {
  constructor(page) { this.page = page; }
  async login(user) {
    await this.page.goto(base + (full ? '/auth/login?next=/auth/admin' : '/auth/login'));
    await this.page.getByLabel(full ? 'Email Address' : 'Synthetic email', { exact: true }).fill(user.email);
    await this.page.getByLabel(full ? 'Password' : 'Synthetic password', { exact: true }).fill(configuration.password);
    await this.page.getByRole('button', { name: full ? 'Sign In' : 'Sign in', exact: true }).click();
    await expect(this.page.getByRole('heading', { name: 'Customers', exact: true })).toBeVisible();
  }
  async open(name) { await this.page.getByRole('navigation', { name: 'Administration', exact: true }).getByRole('button', { name, exact: true }).click(); }
}
const browser = await chromium.launch({ headless: true });
const results = [];
try {
  await Promise.all([['admin', 1], ['super_admin', 0]].flatMap(([role, index]) => [1440, 390].map(async width => {
    const context = await browser.newContext({ viewport: { width, height: 980 } });
    const network = [];
    let activePage;
    try {
      const page = await context.newPage(), screen = new ConsolePage(page);
      activePage = page;
      page.on('response', response => { const path = new URL(response.url()).pathname; if (path.startsWith('/api/admin/')) network.push({ path: path.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, ':uuid'), status: response.status() }); });
      await screen.login(configuration.users[index]);
      await expect(page.getByRole('region', { name: 'Customers records' })).toBeVisible();
      await screen.open('Overview');
      await expect(page.getByRole('region', { name: 'Operational overview' })).toBeVisible();
      await expect(page.getByText('Provider-confirmed charges: unavailable.',{exact:false})).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
      await page.screenshot({path:`${evidence}/${prefix}${role}-${width}-overview.png`,fullPage:true});
      await screen.open('Campaigns');
      await expect(page.getByRole('heading',{name:'Campaigns',exact:true})).toBeVisible();
      if(full && width===1440) {
        await stepUp(page,configuration.users[index]);
        await expect(page.getByRole('heading',{name:'Campaigns',exact:true})).toBeVisible();
        await page.getByRole('button',{name:'New campaign draft',exact:true}).click();
        await page.getByLabel('Campaign name',{exact:true}).fill('Synthetic browser '+role);
        await page.getByLabel('Email subject',{exact:true}).fill('Synthetic browser '+role);
        await page.getByLabel('Plain-text message',{exact:true}).fill('Synthetic mentor-free local acceptance content.');
        await page.getByRole('button',{name:'Save draft',exact:true}).click();
        await expect(page.getByRole('button',{name:'Preview saved revision',exact:true})).toBeEnabled();
        await page.getByRole('button',{name:'Preview saved revision',exact:true}).click();
        await expect(page.getByRole('region',{name:'Campaign preview',exact:true})).toBeVisible();
        await page.getByRole('button',{name:'Review audience and count',exact:true}).click();
        await expect(page.getByRole('dialog',{name:'Confirm promotional campaign',exact:true})).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog',{name:'Confirm promotional campaign',exact:true})).not.toBeVisible();
        await expect(page.getByRole('button',{name:'Review audience and count',exact:true})).toBeFocused();
        await page.getByRole('button',{name:'Review audience and count',exact:true}).click();
        await page.getByRole('button',{name:'Confirm campaign send',exact:true}).click();
        await expect(page.getByText('Send requested.',{exact:false})).toBeVisible();
        await page.getByRole('button',{name:'Refresh campaign results',exact:true}).click();
        await expect(page.getByRole('status').filter({hasText:'Campaign state:'})).toBeVisible();
      }
      await screen.open('Customers');
      const navigation = page.getByRole('navigation', { name: 'Administration', exact: true });
      if (role === 'admin') {
        await expect(navigation.getByRole('button', { name: 'Coupon drafts', exact: true })).toHaveCount(0);
        await expect(navigation.getByRole('button', { name: 'Audit history', exact: true })).toHaveCount(0);
        await expect(navigation.getByRole('button', { name: 'Administrators', exact: true })).toHaveCount(0);
      } else {
        await screen.open('Audit history');
        await expect(page.getByRole('heading', { name: 'Audit history', exact: true })).toBeVisible();
        await screen.open('Administrators');
        await page.getByText('Recovery and safeguards', { exact: true }).click();
        await expect(page.getByText('Emergency recovery is unavailable', { exact: false })).toBeVisible();
        await page.getByRole('button', { name: 'Add administrator' }).click();
        await expect(page.getByRole('dialog')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog')).not.toBeVisible();
        await expect(page.getByRole('button', { name: 'Add administrator' })).toBeFocused();
        await screen.open('Coupon drafts');
        await expect(page.getByText('Configuration only.', { exact: false })).toBeVisible();
        await page.getByRole('button', { name: 'Create inert coupon draft' }).click();
        await expect(page.getByLabel('Inert coupon code (uppercase)')).toBeVisible();
        await page.getByRole('button', { name: 'Cancel draft' }).click();
        await screen.open('Customers');
      }
      await page.getByLabel('Exact customer email or account ID').fill(configuration.users[2].email);
      await page.getByRole('button', { name: 'Search', exact: true }).click();
      await expect(page.getByRole('cell', { name: configuration.users[2].email, exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Inspect metadata', exact: true }).click();
      await expect(page.getByRole('region', { name: 'Selected customer metadata' })).toBeVisible();
      await page.getByRole('button', { name: 'Restrict product access', exact: true }).click();
      await expect(page.getByRole('dialog', { name: 'Restrict customer product access' })).toBeVisible();
      await expect(page.getByRole('dialog', { name: 'Restrict customer product access' })).toContainText('does not cancel billing');
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog', { name: 'Restrict customer product access' })).not.toBeVisible();
      await expect(page.getByRole('button', { name: 'Restrict product access', exact: true })).toBeFocused();
      await expect(page.getByRole('button', { name: 'Restore staff-restricted access', exact: true })).toHaveCount(role === 'super_admin' ? 1 : 0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
      await page.screenshot({ path: `${evidence}/${prefix}${role}-${width}-customers.png`, fullPage: true });
      await page.getByLabel('Exact customer email or account ID').fill(configuration.users[0].email);
      await page.getByRole('button', { name: 'Search', exact: true }).click();
      await expect(page.getByText('No matching records.', { exact: true })).toBeVisible();
      results.push({ role, width, result: 'passed', boundary: full ? 'full normal App + actual SDK/Auth/main API; read/support dialog journeys' : 'actual SDK/Auth/main API; component harness' });
    } catch (error) {
      let diagnostic = String(error.message);
      for (const value of [configuration.password, ...configuration.users.map(user => user.email)]) diagnostic = diagnostic.split(value).join('[REDACTED]');
      let headings = await activePage?.getByRole('heading').allTextContents().catch(() => []);
      results.push({ role, width, result: 'failed', error_type: error.name, diagnostic: diagnostic.replace(/\b[0-9]{6}\b/g,'[OTP]').slice(0, 2500), headings, network });
      throw Error(`admin_browser_failed:${role}:${width}`);
    } finally { await context.close(); }
  })));
  if(full) {
    const actorContext=await browser.newContext(),recipientContext=await browser.newContext();
    let stage='login';const specialNetwork=[];let specialPage;
    try {
      const actor=await actorContext.newPage(),recipient=await recipientContext.newPage();specialPage=actor;actor.on('response',response=>{const path=new URL(response.url()).pathname;if(path.startsWith('/api/admin/'))specialNetwork.push({path:path.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g,':uuid'),status:response.status()});});
      const screen=new ConsolePage(actor);await screen.login(configuration.users[0]);await screen.open('Customers');
      await stepUp(actor,configuration.users[0]);
      await actor.getByLabel('Exact customer email or account ID').fill(configuration.users[2].email);
      await actor.getByRole('button',{name:'Search',exact:true}).click();
      await actor.getByRole('button',{name:'Inspect metadata',exact:true}).click();
      await expect(actor.getByRole('region',{name:'Selected customer metadata'})).toBeVisible();
      await recipient.goto(base+'/auth/login?next=/auth/admin/successor');
      await recipient.getByLabel('Email Address',{exact:true}).fill(configuration.users[2].email);
      await recipient.getByLabel('Password',{exact:true}).fill(configuration.password);
      await recipient.getByRole('button',{name:'Sign In',exact:true}).click();
      await expect(recipient.getByRole('heading',{name:'Accept successor responsibility',exact:true})).toBeVisible();
      const secondTab=await recipientContext.newPage();await secondTab.goto(base+'/auth/admin/successor');
      const access=page=>page.evaluate(async()=>{const {supabase}=await import('/src/auth/supabaseClient.js');const {data}=await supabase.auth.getSession();return (await fetch('/api/auth/me',{headers:{Authorization:'Bearer '+data.session.access_token},cache:'no-store'})).status;});
      expect(await access(recipient)).toBe(200);
      stage='restriction';
      await actor.getByRole('button',{name:'Restrict product access',exact:true}).click();
      stage='access_review';await actor.getByRole('button',{name:'Review access change',exact:true}).click();
      stage='access_confirm';await actor.getByRole('button',{name:'Confirm access change',exact:true}).click();
      await expect(actor.getByRole('dialog')).not.toBeVisible();
      expect(await access(recipient)).toBe(403);expect(await access(secondTab)).toBe(403);
      stage='restore_reinspect';
      await actor.getByRole('button',{name:'Inspect metadata',exact:true}).click();
      await expect(actor.getByRole('region',{name:'Selected customer metadata'})).toBeVisible();
      await actor.getByRole('button',{name:'Restore staff-restricted access',exact:true}).click();
      stage='access_review';await actor.getByRole('button',{name:'Review access change',exact:true}).click();
      stage='access_confirm';await actor.getByRole('button',{name:'Confirm access change',exact:true}).click();
      await expect(actor.getByRole('dialog')).not.toBeVisible();
      expect(await access(recipient)).toBe(200);expect(await access(secondTab)).toBe(200);
      await secondTab.close();
      results.push({scenario:'full_app_staff_restriction_and_super_admin_restoration_existing_jwt_two_tabs',result:'passed'});
      stage='successor_offer';
      await screen.open('Administrators');
      await stepUp(actor,configuration.users[0]);
      await actor.getByText('Appoint a successor', { exact: false }).first().click();
      await actor.getByLabel('Successor Account ID',{exact:true}).fill(configuration.users[2].user_id);
      await actor.getByRole('button',{name:'Send successor offer',exact:true}).click();
      const reference=actor.getByText('Transfer reference:',{exact:false});await expect(reference).toBeVisible();
      const id=(await reference.textContent()).match(/[0-9a-f]{8}-[0-9a-f-]{27}/)[0];
      await recipient.goto(base+'/auth/admin/successor');
      await expect(recipient.getByRole('heading',{name:'Accept successor responsibility',exact:true})).toBeVisible();
      await stepUp(recipient,configuration.users[2]);
      stage='successor_accept';
      await recipient.getByLabel('Transfer reference',{exact:true}).fill(id);
      await recipient.getByRole('button',{name:'Accept Super admin responsibility',exact:true}).click();
      await expect(recipient.getByText('Transfer accepted.',{exact:false})).toBeVisible();
      await recipient.getByRole('button',{name:'Verify administration access',exact:true}).click();
      await expect(recipient.getByText('Successor administration access verified.',{exact:true})).toBeVisible();
      await recipient.getByRole('link',{name:'Open administration',exact:true}).click();
      await expect(recipient.getByRole('navigation',{name:'Administration',exact:true}).getByRole('button',{name:'Audit history',exact:true})).toBeVisible();
      await actor.getByRole('button',{name:'Verify successor access status',exact:true}).click();
      await expect(actor.getByText('State: verified.',{exact:false})).toBeVisible();
      results.push({scenario:'full_normal_app_successor_independent_existing_account_mfa_acceptance_access_verification',result:'passed'});
    } catch(error) {results.push({scenario:'full_app_access_and_successor',result:'failed',stage,error_type:error.name,network:specialNetwork,buttons:await specialPage?.getByRole('button').allTextContents().catch(()=>[]),alerts:await specialPage?.getByRole('alert').allTextContents().catch(()=>[])});throw Error('access_successor_browser_failed');} finally {await actorContext.close();await recipientContext.close();}
  }
} finally {
  await writeFile(evidence + '/' + prefix + 'browser-results.json', JSON.stringify({ chromium: browser.version(), results }, null, 2));
  await browser.close();
}
