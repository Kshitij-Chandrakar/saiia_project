import { chromium, expect } from '@playwright/test';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const accounts = JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA, 'IntervucopilotC15Local/logins.json'), 'utf8'));
const output = fileURLToPath(new URL('../../../docs/evidence/c15-audit-actor-20261105', import.meta.url)); await mkdir(output, { recursive:true });
const browser = await chromium.launch(); const results=[];
try {
  for (const role of ['super_admin','admin']) {
    const context=await browser.newContext({viewport:{width:1440,height:900}}); const page=await context.newPage(); page.setDefaultTimeout(15000);
    await page.goto('http://127.0.0.1:5400/auth/login?next=/auth/admin');
    await page.getByLabel('Email Address',{exact:true}).fill(accounts.users[role].email);
    await page.getByLabel('Password',{exact:true}).fill(accounts.password);
    await page.getByRole('button',{name:'Sign In',exact:true}).click();
    await expect(page.getByRole('heading',{level:1,name:'Customers',exact:true})).toBeVisible();
    const response=page.waitForResponse(r=>r.url().endsWith('/api/admin/audit'));
    await page.goto('http://127.0.0.1:5400/auth/admin?view=audit');
    if(role==='admin') {
      await expect(page.getByRole('heading',{name:'Page not found',exact:true})).toBeVisible();
      // Frontend admission may reject before requesting the endpoint; verify its boundary directly too.
      const status=await page.evaluate(async()=>{const {supabase}=await import('/src/auth/supabaseClient.js');const {data}=await supabase.auth.getSession();return (await fetch('/api/admin/audit',{headers:{Authorization:'Bearer '+data.session.access_token}})).status;});
      expect(status).toBe(404); await response;
      expect(await page.locator('.ac-audit-actor').count()).toBe(0);results.push({role,api_status:status,no_audit_identity_leak:true});
    } else {
      const data=await (await response).json(); expect(data.items.length).toBeGreaterThan(0);
      const known=new Map(Object.values(accounts.users).map(user=>[user.id,user.email]));
      for(const row of data.items){if(known.has(row.actor_ref))expect(row.actor_email).toBe(known.get(row.actor_ref));}
      for(const [width,height] of [[1440,900],[1366,768],[390,844]]){
        await page.setViewportSize({width,height});
        const table=page.getByRole('region',{name:'Audit history records',exact:true}); await expect(table).toBeVisible();
        expect(await table.getByRole('columnheader').allTextContents()).toEqual(['Time (UTC)','Performed by','Action','Role at action','Outcome','Reason']);
        await expect(table.locator('.ac-audit-actor strong').first()).toBeVisible();
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
        if(width===390){expect(await table.evaluate(e=>e.scrollWidth>e.clientWidth)).toBeTruthy();await table.evaluate(e=>e.scrollLeft=130);}
        await page.screenshot({path:path.join(output,`super-admin-${width}.png`)});
        results.push({role,width,actor_identity:true,columns:6,no_page_overflow:true});
      }
      await page.route('**/api/admin/audit',route=>route.fulfill({json:{items:[{event_id:'fixture',actor_ref:null,actor_email:null,timestamp:null,action:'audit.read',actor_role_at_action:'super_admin',outcome:'confirmed',reason_code:null}],has_more:false}}));
      await page.reload();await expect(page.getByText('Email unavailable',{exact:true})).toBeVisible();await expect(page.locator('.ac-audit-actor>span')).toContainText('Account ID unavailable');results.push({role,unavailable_identity_honest:true});
    }
    await context.close();
  }
}finally{await browser.close();await writeFile(path.join(output,'results.json'),JSON.stringify(results,null,2));}
console.log('PASS',results.length,'audit actor checks');
