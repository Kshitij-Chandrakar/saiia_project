import { chromium, expect } from '@playwright/test'
import { writeFile, mkdir } from 'node:fs/promises'
const config = JSON.parse(process.env.C15_BROWSER_USERS)
const out = process.env.C15_BROWSER_EVIDENCE
const results = []
const protectedValues=[config.password,...config.users.map(user=>user.email)]
function redact(value) { for(const secret of protectedValues) value=value.split(secret).join("[REDACTED]"); return value }
let browser, activePage
const network=[]
async function check(name, work) { try { await work(); results.push({ name, result: 'passed', boundary: 'actual SDK and local engines; no route interception' }) } catch (error) { results.push({ name, result: 'failed', error_type: error.name, diagnostic: redact(String(error.message)).slice(0,1800) }); throw Error(name) } }
try {
  browser = await chromium.launch({ headless: true })
  await writeFile(out+'/browser-versions.json',JSON.stringify({chromium:browser.version(),node:process.versions.node},null,2))
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage(); activePage=page
  page.on("response", response => { const url=new URL(response.url()); if(url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/v1/")) network.push({path:url.pathname,status:response.status()}) })
  await check('real_login_and_settings', async () => {
    await page.goto('http://127.0.0.1:5397/auth/login?next=/auth/settings', { waitUntil: 'networkidle' })
    await page.getByLabel('Email Address', { exact: true }).fill(config.users[0].email)
    await page.getByLabel('Password', { exact: true }).fill(config.password)
    await page.getByRole('button', { name: /sign in|log in/i }).filter({ hasNotText: 'Google' }).click()
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible({ timeout: 20000 })
    await expect(page.getByRole('button', { name: 'Delete Account', exact: true })).toBeEnabled()
    await page.screenshot({ path: out + '/actual-desktop-settings.png', fullPage: true })
  })
  await check('actual_password_export_and_zip', async () => {
    await page.getByRole('button', { name: 'Request account export', exact: true }).click()
    await page.getByRole('dialog').getByLabel('Verify your password', { exact: true }).fill(config.password)
    await page.getByRole('button', { name: 'Verify identity', exact: true }).click()
    await expect(page.getByRole('dialog').getByLabel('Type export to confirm')).toBeEnabled()
    await page.getByRole('dialog').getByLabel('Type export to confirm').fill('export')
    await page.getByRole('button', { name: 'Create private export', exact: true }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
    const response = await fetch(process.env.C15_GATEWAY + '/__fixture/work', { method: 'POST', headers: { 'X-C15-Control': process.env.C15_BROWSER_CONTROL } })
    if (!response.ok) throw Error('worker failed')
    await page.getByRole('button', { name: 'Refresh export status' }).click()
    await expect(page.getByText('Export status: ready.', { exact: false })).toBeVisible()
    const downloaded = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download private archive' }).click()
    const file = await downloaded
    if (file.suggestedFilename() !== 'account-export.zip' || await file.failure()) throw Error('archive download failed')
    const stream = await file.createReadStream(); let bytes=0; for await (const data of stream) bytes+=data.length
    if (bytes<22) throw Error('empty zip')
    await file.delete()
  })
  await check('actual_session_and_history_confirmations_and_cleanup', async () => {
    for (const scope of ['session','history']) {
      const title=scope==='session'?'Erase one full session':'Erase all session history'
      const region=page.getByRole('region',{name:title,exact:true})
      if(scope==='session') {
        await region.getByRole('button',{name:'Load your sessions'}).click()
        await expect(region.getByLabel('Session to erase').getByRole('option',{name:'Synthetic Session A'})).toHaveCount(1)
        await region.getByLabel('Session to erase').selectOption({label:'Synthetic Session A'})
      }
      await region.getByRole('button',{name:title,exact:true}).click()
      const dialog=page.getByRole('dialog')
      await dialog.getByLabel('Verify your password',{exact:true}).fill(config.password)
      await dialog.getByRole('button',{name:'Verify identity',exact:true}).click()
      await expect(dialog.getByLabel('Type delete to confirm')).toBeEnabled()
      await dialog.getByLabel('Type delete to confirm').fill('delete')
      await dialog.getByRole('button',{name:'Yes, erase selected history'}).click()
      await expect(dialog).not.toBeVisible()
      const worked=await fetch(process.env.C15_GATEWAY+'/__fixture/work',{method:'POST',headers:{'X-C15-Control':process.env.C15_BROWSER_CONTROL}})
      if(!worked.ok) throw Error('scope worker unavailable')
      await region.getByRole('button',{name:'Refresh export status'}).click()
      await expect(region.getByText('Erasure status: primary_verified.',{exact:false})).toBeVisible()
      const checked=await fetch(process.env.C15_GATEWAY+'/__fixture/scope-check',{headers:{'X-C15-Control':process.env.C15_BROWSER_CONTROL}})
      const state=await checked.json()
      if(state.profiles!==1 || state.sessions!==(scope==='session'?1:0)) throw Error('incorrect erasure scope')
    }
  })
  await check('actual_mobile_cancel_and_password_final_confirmation', async () => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: 'Delete Account', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Delete your account?' })).toBeFocused()
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Delete Account', exact: true })).toBeFocused()
    await page.getByRole('button', { name: 'Delete Account', exact: true }).click()
    await page.getByRole('dialog').getByLabel('Reauthenticate with your password').fill(config.password)
    await page.getByRole('button', { name: 'Verify identity', exact: true }).click()
    await expect(page.getByText('Identity verified.', { exact: false })).toBeVisible()
    await page.getByRole('dialog').getByLabel('Type delete to confirm').fill('Delete')
    await expect(page.getByRole('button', { name: 'Yes, Delete My Account' })).toBeDisabled()
    await page.getByRole('dialog').getByLabel('Type delete to confirm').fill('delete')
    await page.screenshot({ path: out + '/actual-mobile-confirmation.png', fullPage: true })
    const stale=await context.newPage(); await stale.goto('http://127.0.0.1:5397/auth/settings'); await expect(stale.getByRole('heading',{name:'Settings',exact:true})).toBeVisible()
    await page.getByRole('button', { name: 'Yes, Delete My Account' }).click()
    await expect(stale.getByRole('button',{name:'Delete Account',exact:true})).not.toBeVisible(); await stale.close()
    await expect(page).toHaveURL(/privacy-status/)
    await expect(page.getByRole('heading', {name:'Request accepted. Product access is restricted.',exact:true})).toBeVisible({timeout:15000})
    await expect(page.getByText('This does not confirm that all files, backups or processor copies have been erased.', {exact:false})).toBeVisible()
    await expect(page.getByText('Further charges may remain possible', { exact: false })).toBeVisible()
  })
  await check('unaffected_account_still_logs_in_and_reads_settings', async () => {
    const clean=await browser.newContext({viewport:{width:1440,height:1000}})
    const second=await clean.newPage()
    await second.goto('http://127.0.0.1:5397/auth/login?next=/auth/settings')
    await second.getByLabel('Email Address',{exact:true}).fill(config.users[1].email)
    await second.getByLabel('Password',{exact:true}).fill(config.password)
    await second.getByRole('button',{name:'Sign In',exact:true}).click()
    await expect(second.getByRole('heading',{name:'Settings',exact:true})).toBeVisible()
    await expect(second.getByRole('button',{name:'Delete Account',exact:true})).toBeEnabled()
    await clean.close()
  })
  await check('actual_mailbox_export_then_distinct_deletion_proof', async () => {
    const clean=await browser.newContext({viewport:{width:390,height:844}})
    const third=await clean.newPage(); activePage=third
    third.on("response", response => { const url=new URL(response.url()); if(url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/v1/")) network.push({path:url.pathname,status:response.status()}) })
    await third.goto('http://127.0.0.1:5397/auth/login?next=/auth/settings')
    await third.getByLabel('Email Address',{exact:true}).fill(config.users[2].email)
    await third.getByLabel('Password',{exact:true}).fill(config.password)
    await third.getByRole('button',{name:'Sign In',exact:true}).click()
    await expect(third.getByRole('heading',{name:'Settings',exact:true})).toBeVisible()
    await third.getByRole('button',{name:'Request account export',exact:true}).click()
    await third.getByRole('button',{name:'Send mailbox code',exact:true}).click()
    async function mailbox() {
      const response=await fetch(process.env.C15_GATEWAY+'/__fixture/code',{method:'POST',headers:{'X-C15-Control':process.env.C15_BROWSER_CONTROL,'Content-Type':'application/json'},body:JSON.stringify({index:2})})
      if(!response.ok) throw Error('local catcher unavailable')
      const code=(await response.json()).code; protectedValues.push(code); return code
    }
    const exportCode=await mailbox()
    await third.getByRole('dialog').getByLabel('Mailbox code',{exact:true}).fill(exportCode==='00000000'?'11111111':'00000000')
    await third.getByRole('button',{name:'Verify identity',exact:true}).click()
    await expect(third.getByRole('button',{name:'Create private export',exact:true})).toBeDisabled()
    await third.getByRole('dialog').getByLabel('Mailbox code',{exact:true}).fill(exportCode)
    await third.getByRole('button',{name:'Verify identity',exact:true}).click()
    await expect(third.getByRole('dialog').getByLabel('Type export to confirm')).toBeEnabled()
    await third.getByRole('button',{name:'Cancel',exact:true}).click()
    await third.getByRole('button',{name:'Delete Account',exact:true}).click()
    await third.getByRole('button',{name:'Send email code',exact:true}).click()
    await expect(third.getByRole('button',{name:'Verify email code',exact:true})).toBeVisible()
    const deleteCode=await mailbox()
    await third.getByRole('dialog').getByLabel('Email confirmation code').fill(exportCode)
    await third.getByRole('button',{name:'Verify email code',exact:true}).click()
    await expect(third.getByRole('button',{name:'Yes, Delete My Account'})).toBeDisabled()
    await third.getByRole('dialog').getByLabel('Email confirmation code').fill(deleteCode)
    await third.getByRole('button',{name:'Verify email code',exact:true}).click()
    await expect(third.getByText('Identity verified.',{exact:false})).toBeVisible()
    await third.getByRole('dialog').getByLabel('Type delete to confirm').fill('delete')
    await third.getByRole('button',{name:'Yes, Delete My Account'}).click()
    await expect(third).toHaveURL(/privacy-status/)
    await clean.close()
  })
  await check('actual_sdk_totp_confirmation', async () => {
    // A newly published decision deliberately quarantines product ingress until
    // the normal coordinator acknowledges coverage. Verify recovery, do not bypass it.
    await expect.poll(async () => (await fetch(process.env.C15_GATEWAY+'/api/auth/me')).status, {timeout:20000}).toBe(401)
    const clean=await browser.newContext({viewport:{width:1440,height:1000}})
    const mfa=await clean.newPage(); activePage=mfa
    await mfa.goto('http://127.0.0.1:5397/auth/login?next=/auth/settings')
    await mfa.getByLabel('Email Address',{exact:true}).fill(config.users[3].email)
    await mfa.getByLabel('Password',{exact:true}).fill(config.password)
    await mfa.getByRole('button',{name:'Sign In',exact:true}).click()
    await expect(mfa.getByRole('heading',{name:'Settings',exact:true})).toBeVisible()
    await mfa.getByRole('button',{name:'Delete Account',exact:true}).click()
    await expect(mfa.getByRole('dialog').getByLabel('Authenticator code')).toBeVisible()
    const response=await fetch(process.env.C15_GATEWAY+'/__fixture/totp',{headers:{'X-C15-Control':process.env.C15_BROWSER_CONTROL}})
    const code=(await response.json()).code;protectedValues.push(code)
    await mfa.getByRole('dialog').getByLabel('Authenticator code').fill(code)
    await mfa.getByRole('button',{name:'Verify identity',exact:true}).click()
    await expect(mfa.getByText('Identity verified.',{exact:false})).toBeVisible()
    await mfa.getByRole('dialog').getByLabel('Type delete to confirm').fill('delete')
    await mfa.getByRole('button',{name:'Yes, Delete My Account'}).click()
    await expect(mfa).toHaveURL(/privacy-status/)
    await clean.close()
  })
  await context.close()
} catch (error) { console.error('Actual browser scenario failed:', error.message); if(activePage) { const body=await activePage.locator('body').innerText().catch(()=> 'unavailable'); await writeFile(out+'/browser-diagnostic.json',JSON.stringify({network,body:redact(body)},null,2)) }; process.exitCode=1 }
finally { await browser?.close(); await mkdir(out,{recursive:true}); await writeFile(out+'/browser-results.json',JSON.stringify(results,null,2)); console.log(JSON.stringify(results)) }
