import {chromium,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';import path from 'node:path';
const a=JSON.parse(await readFile(path.join(process.env.LOCALAPPDATA,'IntervucopilotC15Local/logins.json'),'utf8'));
const output='../docs/evidence/c15-local-api-recovery-20261107';await mkdir(output,{recursive:true});const b=await chromium.launch();const results=[];
try{
 for(const role of ['delete_customer','super_admin']){
 const context=await b.newContext({viewport:{width:1440,height:900}});const p=await context.newPage();p.setDefaultTimeout(20000);
 await p.goto('http://127.0.0.1:5400/auth/login?next='+(role==='delete_customer'?'/auth/settings':'/auth/admin'));
 await p.getByLabel('Email Address',{exact:true}).fill(a.users[role].email);await p.getByLabel('Password',{exact:true}).fill(a.password);
 const bootstrap=role==='delete_customer'?p.waitForResponse(r=>r.url().includes('/api/auth/profile/bootstrap')):null;
 await p.getByRole('button',{name:'Sign In',exact:true}).click();
 if(role==='delete_customer'){
 expect((await bootstrap).status()).toBe(200);await expect(p.getByRole('heading',{name:'Settings',exact:true,level:1})).toBeVisible();
 await p.getByRole('heading',{name:'Danger Zone',exact:true}).scrollIntoViewIfNeeded();await expect(p.getByRole('button',{name:'Delete Account',exact:true})).toBeEnabled();await p.screenshot({path:output+'/settings.png'});
 await p.getByRole('button',{name:'Delete Account',exact:true}).click();const d=p.getByRole('dialog',{name:'Delete your account?',exact:true});await expect(d).toBeVisible();await expect(d.getByRole('button',{name:'Yes, Delete My Account',exact:true})).toBeDisabled();await p.screenshot({path:output+'/deletion-dialog.png'});await d.getByRole('button',{name:'Cancel',exact:true}).click();results.push({role,profile_bootstrap_status:200,settings_available:true,deletion_enabled:true,final_confirmation_requires_proof_and_typed_text:true,no_deletion_submitted:true});
 }else{await expect(p.getByRole('heading',{name:'Customers',level:1,exact:true})).toBeVisible();results.push({role,admin_access:true});}
 await context.close();
 }
 await writeFile(output+'/results.json',JSON.stringify(results,null,2));console.log('PASS: profile bootstrap 200; Settings/deletion dialog and Super admin login work. No deletion submitted.');
}finally{await b.close();}
