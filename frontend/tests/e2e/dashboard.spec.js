import { test, expect } from '@playwright/test'
import { mkdir, readFile } from 'node:fs/promises'
import path from 'node:path'

const output = path.resolve('../tmp/dashboard-redesign')
const sessions = Array.from({ length: 20 }, (_, i) => ({
  id: `session-${i + 1}`, title: i === 0 ? 'Platform engineering discussion' : i === 1 ? 'Design systems discussion' : `Interview session ${i + 1}`,
  target_role: i === 0 ? 'Backend Engineer' : 'Product Engineer', company_name: 'Synthetic Company', status: i === 2 ? 'active' : 'ended',
  started_at: new Date(Date.UTC(2026, 9, 10 - i, 10)).toISOString(), ended_at: i === 2 ? null : new Date(Date.UTC(2026, 9, 10 - i, 10, 30, 15)).toISOString(),
}))
const readyResume = { id:'resume-1', original_filename:'candidate-profile.pdf', status:'confirmed', is_active:true, index_status:'ready', extraction_attempt:1 }

async function mock(page, { signedIn = true, current = null, candidate = null, listFailure = false, notesMissing = false, resumeFailure = false, email = 'candidate@example.test', records = sessions, resumeItems = [] } = {}) {
  await page.addInitScript(({ signedIn, current, candidate, listFailure, notesMissing, resumeFailure, email, records, resumeItems }) => {
    window.__session = signedIn ? { access_token:'synthetic-token', user:{ id:'synthetic-user' } } : null
    window.__current = current; window.__candidate = candidate; window.__requests = []; window.__listeners = []
    window.__listFailure = listFailure; window.__notesMissing = notesMissing; window.__resumeFailure = resumeFailure
    window.__email = email; window.__records = records; window.__resumeItems = resumeItems
    window.__emit = (event, session) => { window.__session = session; for (const listener of window.__listeners) listener(event, session) }
  }, { signedIn, current, candidate, listFailure, notesMissing, resumeFailure, email, records, resumeItems })
  await page.route('**/src/auth/supabaseClient.js*', route => route.fulfill({ contentType:'application/javascript', body:`
    export function getSupabaseAuthConfig(){return {}};
    export const supabase={auth:{
      getSession:async()=>{if(window.__authGate)await window.__authGate;return {data:{session:window.__session},error:null}},
      onAuthStateChange:callback=>{window.__listeners.push(callback);return {data:{subscription:{unsubscribe(){window.__listeners=window.__listeners.filter(x=>x!==callback)}}}}},
      signOut:async()=>{if(window.__logoutFail)return {error:{message:'private failure'}};window.__emit('SIGNED_OUT',null);return {error:null}},
      signInWithPassword:async()=>({data:{session:null},error:null}),signInWithOAuth:async()=>({error:null})}};` }))
  const deletedTranscripts = new Set()
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()), endpoint = url.pathname
    const method = route.request().method()
    let state
    try {
      state = await page.evaluate(request => {
        window.__requests.push(request)
        return { user:window.__session?.user?.id, current:window.__current, candidate:window.__candidate, listFailure:window.__listFailure, notesMissing:window.__notesMissing, resumeFailure:window.__resumeFailure, email:window.__email, records:window.__records, resumeItems:window.__resumeItems }
      }, {endpoint,query:url.search,method})
    } catch(error) {
      if (!/Execution context was destroyed|Target page.*closed/.test(error.message)) throw error
      await route.abort().catch(()=>{})
      return
    }
    if (endpoint === '/api/auth/me') return route.fulfill({ json:{ user_id:state.user, email:state.user === 'second-user' ? 'second@example.test' : state.email, role:'authenticated' } })
    if (endpoint === '/api/auth/profile/bootstrap') return route.fulfill({ json:{ profile_created:false, settings_created:false } })
    if (endpoint === '/api/interview-sessions') return route.fulfill(state.listFailure ? { status:503, json:{detail:'Synthetic list failure'} } : { json:{items:state.user === 'second-user' ? [{...sessions[1],title:'Second account session',id:'second-session'}] : url.searchParams.get('page') === '2' ? [{...sessions[0],id:'session-21',title:'Earlier session'}] : state.records,limit:20,page:Number(url.searchParams.get('page'))} })
    if (endpoint.endsWith('/transcript-entries')) {
      const id = endpoint.split('/')[3]
      if(route.request().method()==='DELETE') { deletedTranscripts.add(id);return route.fulfill({json:{deleted_count:1}}) }
      return route.fulfill({json:{items:id==='session-2'||deletedTranscripts.has(id)?[]:[{id:`entry-${id}`,session_id:id,turn_index:1,question_text:`Question for ${id}`,answer_text:'Safe <script> text',created_at:'2026-10-10T10:01:00Z'}],page:1,limit:100}})
    }
    if (endpoint.endsWith('/transcript/download')) return route.fulfill({contentType:'text/plain',headers:{'Access-Control-Expose-Headers':'Content-Disposition','Content-Disposition':`attachment; filename="interview-transcript.${url.searchParams.get('format')}"`},body:`Transcript for ${endpoint.split('/')[3]}\nQuestion and answer content`})
    if (endpoint.endsWith('/notes') || endpoint.endsWith('/notes/generate')) {
      if (state.notesMissing && endpoint.endsWith('/notes')) return route.fulfill({status:404,json:{detail:'AI notes were not found.'}})
      return route.fulfill({json:{id:'notes-1',session_id:endpoint.split('/')[3],status:'ready',summary:'Synthetic notes summary',strengths:['Clear explanation'],improvement_areas:['Add concrete details']}})
    }
    if (endpoint.endsWith('/ask-ai/messages')) return route.fulfill({json:{items:[],page:1,limit:50,next_page:null,has_more:false}})
    if (endpoint.endsWith('/ask-ai')) {
      const question=route.request().postDataJSON().question
      const record=state.records.find(record=>record.id===endpoint.split('/')[3])
      const reply=/follow[ -]up email/i.test(question) ? `Subject: Thank you for the interview - ${record?.target_role || '[Position]'} - [Your Name]\n\nDear [Interviewer Name],\n\nThank you for the opportunity to interview for the ${record?.target_role || '[Position]'} position at ${record?.company_name || '[Company]'}. I appreciate your time and look forward to the next steps.\n\nBest regards,\n[Your Name]\n[Your Phone Number]` : 'Synthetic follow-up response'
      return route.fulfill({json:{user_message:{id:'q1',session_id:endpoint.split('/')[3],role:'user',turn_index:1,message_text:question},assistant_message:{id:'a1',session_id:endpoint.split('/')[3],role:'assistant',turn_index:2,message_text:reply},answer_text:reply}})
    }
    if (endpoint === '/api/resumes/current') return route.fulfill(state.resumeFailure ? {status:503,json:{detail:'Synthetic resume failure'}} : {json:{ready:Boolean(state.current?.is_active),resume:state.current}})
    if (endpoint === '/api/resumes/review-candidate') return route.fulfill({json:{has_candidate:Boolean(state.candidate),resume:state.candidate}})
    if (endpoint === '/api/resumes' && method === 'GET') return route.fulfill({json:{items:state.resumeItems}})
    if (endpoint === '/api/resumes' && method === 'POST') return route.fulfill({json:{id:'uploaded-resume',original_filename:'profile.txt',status:'uploaded',extraction_attempt:1}})
    if (endpoint.endsWith('/status')) return route.fulfill({json:{id:'uploaded-resume',original_filename:'profile.txt',status:'uploaded'}})
    if (endpoint.endsWith('/extract')) return route.fulfill({json:{resume_id:'uploaded-resume',status:'needs_review',extraction_attempt:1,review_required:true,profile:{full_name:'Synthetic Candidate',email:'candidate@example.test'}}})
    if (endpoint.endsWith('/confirm')) { await page.evaluate(resume => {window.__current=resume;window.__candidate=null},{...readyResume,id:endpoint.split('/')[3]}); return route.fulfill({json:{ready:true,status:'confirmed'}}) }
    if (endpoint.endsWith('/rebuild-index')) return route.fulfill({json:{ready:true,status:'confirmed'}})
    if (method === 'DELETE') {await page.evaluate(()=>{window.__current=null;window.__candidate=null});return route.fulfill({json:{deleted:true}})}
    return route.fulfill({status:404,json:{detail:'Unmocked endpoint'}})
  })
}

class Workspace {
  constructor(page) { this.page = page }
  async goto(route, title) { await this.page.goto(route); await expect(this.page.getByRole('heading',{name:title,exact:true,level:1})).toBeVisible();await expect(this.page.getByRole('button',{name:'Logout',exact:true})).toBeVisible() }
  row(title) { return this.page.getByRole('row').filter({has:this.page.getByRole('button',{name:`Actions for ${title}`,exact:true})}) }
  async menu(title) { const close=this.page.getByRole('button',{name:'Close session viewer',exact:true}); if(await close.count()) { await this.page.keyboard.press('Escape'); await expect(close).toHaveCount(0) } await this.page.getByRole('button',{name:`Actions for ${title}`,exact:true}).click(); return this.page.getByRole('menu',{name:'Session actions'}) }
  async settled() { await this.page.evaluate(()=>document.fonts.ready); await expect.poll(()=>this.page.locator('.website-dashboard img').evaluateAll(images=>images.every(i=>i.complete&&i.naturalWidth>0))).toBe(true) }
}

test('downloads preserve cached session identity; opening and deleting B use only B entries', async ({page}) => {
  await mock(page)
  let bReads = 0, bDeleted = false
  await page.route('**/api/interview-sessions/session-2/transcript-entries?*', route => {
    bReads++
    return route.fulfill({json:{items:bDeleted ? [] : [{id:'b-entry',session_id:'session-2',turn_index:1,question_text:'B question only',answer_text:'B answer only'}]}})
  })
  await page.route('**/api/interview-sessions/session-2/transcript-entries', route => {
    expect(route.request().method()).toBe('DELETE'); bDeleted = true
    return route.fulfill({json:{deleted_count:1}})
  })
  const workspace = new Workspace(page)
  await workspace.goto('/auth/sessions','Call Sessions')
  await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript'}).click()
  await expect(page.getByText('Question for session-1',{exact:false})).toBeVisible()
  await workspace.menu('Design systems discussion')
  const downloaded = page.waitForEvent('download')
  await page.getByRole('menuitem',{name:'Download .txt',exact:true}).click(); await downloaded
  await workspace.menu('Platform engineering discussion'); await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  let viewer = page.getByRole('dialog',{name:'Platform engineering discussion',exact:true})
  await viewer.getByRole('button',{name:'Transcript',exact:true}).click()
  await expect(viewer.getByText('Question for session-1',{exact:false})).toBeVisible()
  expect(await page.evaluate(()=>window.__requests.filter(r=>r.endpoint==='/api/interview-sessions/session-1/transcript-entries'&&r.method==='GET').length)).toBe(1)
  expect(bReads).toBe(0)
  await workspace.menu('Design systems discussion'); await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  viewer = page.getByRole('dialog',{name:'Design systems discussion',exact:true})
  await viewer.getByRole('button',{name:'Transcript',exact:true}).click()
  await expect(viewer.getByText('B question only',{exact:false})).toBeVisible()
  await expect(viewer.getByText('Question for session-1',{exact:false})).toHaveCount(0)
  expect(bReads).toBe(1)
  await viewer.getByRole('button',{name:'Clear Transcript',exact:true}).click()
  await page.getByRole('dialog',{name:'Clear Transcript?',exact:true}).getByRole('button',{name:'Delete Transcript',exact:true}).click()
  await expect(viewer.getByText('Transcript deleted.',{exact:true})).toBeVisible()
  expect(bDeleted).toBe(true)
  expect(await page.evaluate(()=>window.__requests.filter(r=>r.method==='DELETE').length)).toBe(0)
})

test('downloading B never fences A pending transcript read or clears its loading state', async ({page}) => {
  await mock(page)
  const held = await holdRequest(page,'**/api/interview-sessions/session-1/transcript-entries?*')
  const workspace = new Workspace(page)
  await workspace.goto('/auth/sessions','Call Sessions')
  await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript'}).click(); await held.requested
  await workspace.menu('Design systems discussion')
  const downloaded = page.waitForEvent('download')
  await page.getByRole('menuitem',{name:'Download .md',exact:true}).click(); await downloaded
  await workspace.menu('Platform engineering discussion'); await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  const viewer = page.getByRole('dialog',{name:'Platform engineering discussion',exact:true})
  await viewer.getByRole('button',{name:'Transcript',exact:true}).click()
  await expect(page.getByRole('status',{name:'Loading transcript...'})).toBeVisible()
  await expect(viewer.getByRole('button',{name:'Clear Transcript',exact:true})).toBeDisabled()
  await held.release()
  await expect(viewer.getByText('Question for session-1',{exact:false})).toBeVisible()
})

test('mismatched transcript response is rejected before rendering or deletion', async ({page}) => {
  await mock(page)
  await page.route('**/api/interview-sessions/session-2/transcript-entries?*',route=>route.fulfill({json:{items:[{id:'wrong-entry',session_id:'session-1',turn_index:1,question_text:'Wrong session content',answer_text:'Must not render'}]}}))
  const workspace = new Workspace(page); await workspace.goto('/auth/sessions','Call Sessions')
  await workspace.row('Design systems discussion').getByRole('button',{name:'View Transcript'}).click()
  const viewer = page.getByRole('dialog',{name:'Design systems discussion',exact:true})
  await expect(viewer.getByRole('alert')).toContainText('Could not load transcript entries.')
  await expect(viewer.getByText('Wrong session content',{exact:false})).toHaveCount(0)
  await expect(viewer.getByRole('button',{name:'Clear Transcript',exact:true})).toBeDisabled()
  expect(await page.evaluate(()=>window.__requests.filter(r=>r.method==='DELETE').length)).toBe(0)
})

test('missing Supabase configuration settles the resume panel without a TypeError or retry loop', async ({page}) => {
  await page.route('**/src/auth/supabaseClient.js*',route=>route.fulfill({contentType:'application/javascript',body:'export const supabase=null;'}))
  await page.route('**/src/main.jsx*',async route=>{
    const source = await page.request.get(new URL('/src/auth/DashboardOverview.jsx',route.request().url()).href)
    // Use Vite's exact URL so the harness and Link share one router context.
    const router = (await source.text()).match(/from ["']([^"']*react-router-dom[^"']*)["']/)[1]
    return route.fulfill({contentType:'application/javascript',body:`
    import React from '/node_modules/.vite/deps/react.js';import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
    import {BrowserRouter} from '${router}';import Overview from '/src/auth/DashboardOverview.jsx';
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(BrowserRouter,null,React.createElement(Overview,{user:{user_id:'synthetic-user'},sessions:[],loading:false})));`})
  })
  const errors = [], requests = []
  page.on('pageerror',error=>errors.push(error.message)); page.on('request',request=>{if(request.url().includes('/api/'))requests.push(request.url())})
  await page.goto('/')
  expect(errors).toEqual([])
  await expect(page.getByRole('region',{name:'Resume overview'})).toContainText('Authentication is unavailable.')
  await expect(page.getByRole('button',{name:'Retry resume status'})).toHaveCount(0)
  expect(errors).toEqual([]); expect(requests).toEqual([])
})

test('Ask AI suggestions, editable follow-up draft, nested confirmations and temporary chat clearing', async ({page}) => {
  await mock(page);const workspace=new Workspace(page)
  const saved=[{id:'saved-q',session_id:'session-1',role:'user',turn_index:1,message_text:'What can improve?'},{id:'saved-a',session_id:'session-1',role:'assistant',turn_index:2,message_text:'Use concrete examples.'}]
  let posts=0, deletes=0
  page.on('request',request=>{if(request.method()==='DELETE')deletes++})
  await page.route('**/api/interview-sessions/session-1/ask-ai/messages?*',route=>route.fulfill({json:{items:saved,page:1,limit:50,next_page:null,has_more:false}}))
  await page.route('**/api/interview-sessions/session-1/ask-ai',async route=>{
    posts++;const body=route.request().postDataJSON();expect(body.include_notes).toBe(true);expect(body.request_id).toBeTruthy()
    const reply='Subject: Thank you for the interview - Backend Engineer - [Your Name]\n\nDear [Interviewer Name],\n\nThank you for the opportunity to interview at Synthetic Company.\n\nBest regards,\n[Your Name]\n[Your Phone Number]'
    const user_message={id:`new-q-${posts}`,session_id:'session-1',role:'user',turn_index:3,message_text:body.question}
    const assistant_message={id:`new-a-${posts}`,session_id:'session-1',role:'assistant',turn_index:4,message_text:reply}
    saved.push(user_message,assistant_message);await route.fulfill({json:{user_message,assistant_message,answer_text:reply}})
  })
  await workspace.goto('/auth/sessions','Call Sessions');await workspace.menu('Platform engineering discussion');await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  const viewer=page.getByRole('dialog',{name:'Platform engineering discussion',exact:true}), clear=viewer.getByRole('button',{name:'Clear Chat',exact:true})
  await expect(viewer.getByText('Use concrete examples.',{exact:false})).toBeVisible()
  await page.screenshot({path:path.resolve('../tmp/session-popup-polish/conversation.png')})
  await clear.click();const confirmation=page.getByRole('dialog',{name:'Clear Chat?',exact:true})
  await expect(confirmation.getByRole('button',{name:'Keep Chat'})).toBeFocused()
  await page.keyboard.press('Escape');await expect(confirmation).toHaveCount(0);await expect(viewer).toBeVisible();await expect(clear).toBeFocused()
  await clear.click();await confirmation.getByRole('button',{name:'Keep Chat'}).click();await expect(viewer.getByText('Use concrete examples.',{exact:false})).toBeVisible()
  await clear.click();await confirmation.getByRole('button',{name:'Clear Chat',exact:true}).click()
  await expect(viewer.getByText('Use concrete examples.',{exact:false})).toHaveCount(0);expect(saved.length).toBe(2);expect(deletes).toBe(0)
  await expect(clear).toBeDisabled();await expect(viewer.getByText('New questions can still use the saved conversation as context.')).toBeVisible()
  await viewer.getByRole('button',{name:'Transcript',exact:true}).click();await viewer.getByRole('button',{name:'Ask AI',exact:true}).click()
  await expect(viewer.getByText('Use concrete examples.',{exact:false})).toHaveCount(0)
  const input=viewer.getByLabel('Ask about this session')
  await viewer.getByRole('button',{name:'Follow-up Email',exact:true}).click();await expect(input).toBeFocused();await expect(input).toHaveValue(/Draft a professional follow-up email/);expect(posts).toBe(0)
  await viewer.getByRole('button',{name:'Grade the call',exact:true}).click();const replace=page.getByRole('dialog',{name:'Replace your draft?',exact:true})
  await expect(replace.getByRole('button',{name:'Keep Draft'})).toBeFocused();await page.keyboard.press('Escape');await expect(viewer).toBeVisible();await expect(input).toHaveValue(/follow-up email/)
  await viewer.getByRole('button',{name:'How was the vibe?',exact:true}).click();await replace.getByRole('button',{name:'Replace Draft'}).click();await expect(input).toBeFocused();await expect(input).toHaveValue(/Describe the tone/);expect(posts).toBe(0)
  await input.fill('');await viewer.getByRole('button',{name:'Follow-up Email',exact:true}).click();await viewer.getByRole('button',{name:'Send',exact:true}).click()
  const email=viewer.getByLabel('Follow-up email draft');await expect(email).toHaveValue(/Backend Engineer/);await expect(email).toHaveValue(/\[Your Name\]/)
  expect(posts).toBe(1);await expect(viewer.getByText('Use concrete examples.',{exact:false})).toHaveCount(0)
  await email.fill('Subject: Edited locally\n\nMy reviewed email draft.');expect(saved.at(-1).message_text).not.toContain('Edited locally')
  await page.context().grantPermissions(['clipboard-read','clipboard-write']);await viewer.getByRole('button',{name:'Copy Email'}).click();await expect(viewer.getByRole('status').filter({hasText:'Email draft copied.'})).toBeVisible()
  await viewer.getByRole('button',{name:'Close session viewer'}).click();await workspace.menu('Platform engineering discussion');await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  await expect(viewer.getByText('Use concrete examples.',{exact:false})).toBeVisible();await expect(email).toHaveValue(/Edited locally/);expect(deletes).toBe(0)
})

test('permanent transcript deletion confirms server success, retains data on failure and fences stale reads', async ({page}) => {
  await mock(page);const workspace=new Workspace(page);await workspace.goto('/auth/sessions','Call Sessions')
  const trigger=workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript',exact:true})
  await trigger.click();const viewer=page.getByRole('dialog',{name:'Platform engineering discussion',exact:true})
  await expect(viewer.getByText('Question for session-1',{exact:false})).toBeVisible()
  await viewer.getByRole('button',{name:'Close session viewer'}).click()
  let release, requested, finishDelete, deletes=0, deleted=false
  const waiting=new Promise(resolve=>requested=resolve)
  await page.route('**/api/interview-sessions/session-1/transcript-entries?*',async route=>{
    if(deleted)return route.fulfill({json:{items:[],page:1,limit:100}})
    await new Promise(resolve=>{release=resolve;requested()})
    await route.fulfill({json:{items:[{id:'entry-session-1',session_id:'session-1',turn_index:1,question_text:'Stale saved question',answer_text:'Saved answer'}],page:1,limit:100}})
  })
  await page.route('**/api/interview-sessions/session-1/transcript-entries',async route=>{
    deletes++
    if(deletes===1)return route.fulfill({status:503,json:{detail:'Synthetic failure'}})
    await new Promise(resolve=>finishDelete=resolve)
    deleted=true;return route.fulfill({json:{deleted_count:1}})
  })
  await trigger.click();await waiting
  const clear=viewer.getByRole('button',{name:'Clear Transcript',exact:true});await clear.click()
  const confirmation=page.getByRole('dialog',{name:'Clear Transcript?',exact:true})
  await expect(confirmation.getByRole('button',{name:'Keep Transcript'})).toBeFocused()
  await page.keyboard.press('Escape');expect(deletes).toBe(0);await expect(viewer).toBeVisible()
  await clear.click();await confirmation.getByRole('button',{name:'Delete Transcript',exact:true}).click()
  await expect(confirmation.getByRole('alert')).toContainText('Could not delete')
  await expect(viewer.getByText('Question for session-1',{exact:false})).toBeVisible()
  await confirmation.getByRole('button',{name:'Delete Transcript',exact:true}).click()
  await expect(confirmation.getByRole('button',{name:'Deleting…'})).toBeDisabled()
  await expect(confirmation.getByRole('button',{name:'Keep Transcript'})).toBeDisabled()
  await page.keyboard.press('Escape');await expect(confirmation).toBeVisible();expect(deletes).toBe(2)
  finishDelete()
  await expect(viewer.getByText('Transcript deleted.',{exact:true})).toBeVisible();release()
  await expect(viewer.getByText('No transcript available.',{exact:true})).toBeVisible()
  await expect(viewer.getByText('Stale saved question',{exact:false})).toHaveCount(0);await expect(clear).toBeDisabled()
  await viewer.getByRole('button',{name:'AI Notes',exact:true}).click();await expect(viewer.getByText('Synthetic notes summary')).toBeVisible()
  await viewer.getByRole('button',{name:'Transcript',exact:true}).click();await expect(clear).toBeDisabled()
  await page.route('**/api/interview-sessions/session-1/transcript/download?*',route=>route.fulfill({contentType:'text/plain',headers:{'Content-Disposition':'attachment; filename="empty-transcript.txt"'},body:'Interview Transcript\n'}))
  for(const format of ['txt','md']) {
    const downloaded=page.waitForEvent('download');await viewer.getByRole('button',{name:`Download .${format}`,exact:true}).click()
    expect(await readFile(await (await downloaded).path(),'utf8')).not.toContain('Saved question')
  }
  await viewer.getByRole('button',{name:'Close session viewer'}).click();await trigger.click();await expect(viewer.getByText('No transcript available.')).toBeVisible()
  expect(deletes).toBe(2)
  await page.reload();await expect(workspace.row('Platform engineering discussion')).toBeVisible();await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript'}).click();await expect(viewer.getByText('No transcript available.')).toBeVisible()
})

test('permanent clearing is disabled for active sessions and the late-write window; confirmation fits each viewport', async ({page})=>{
  const records=[{...sessions[0],status:'active',ended_at:null},{...sessions[1],ended_at:new Date(Date.now()-60000).toISOString()}]
  await mock(page,{records});const workspace=new Workspace(page);await workspace.goto('/auth/sessions','Call Sessions')
  await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript'}).click()
  await expect(page.getByRole('button',{name:'Clear Transcript',exact:true})).toBeDisabled()
  await expect(page.getByText('Transcript deletion is available five minutes after the session ends.')).toBeVisible()
  await page.getByRole('button',{name:'Close session viewer'}).click()
  await page.addInitScript(records=>window.__records=records,[{...sessions[0],ended_at:new Date(Date.now()-60000).toISOString()}]);await page.reload()
  await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript'}).click();await expect(page.getByRole('button',{name:'Clear Transcript',exact:true})).toBeDisabled()
  await page.getByRole('button',{name:'Close session viewer'}).click()
  await page.addInitScript(records=>window.__records=records,sessions);await page.reload()
  await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript'}).click();await page.getByRole('button',{name:'Clear Transcript',exact:true}).click()
  const confirmation=page.getByRole('dialog',{name:'Clear Transcript?',exact:true})
  for(const [width,height] of [[1366,768],[1280,720],[1024,768],[768,1024],[390,844],[390,360]]) {
    await page.setViewportSize({width,height});await expect(confirmation.getByRole('button',{name:'Delete Transcript'})).toBeInViewport()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    await page.screenshot({path:path.resolve(`../tmp/session-popup-polish/permanent-clear-${width}x${height}.png`)})
  }
})

test('Ask AI reference screenshots and confirmation layouts fit desktop, tablet, mobile and keyboard-sized viewports', async ({page}) => {
  await mock(page);const workspace=new Workspace(page);await workspace.goto('/auth/sessions','Call Sessions')
  await workspace.menu('Platform engineering discussion');await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  const viewer=page.getByRole('dialog',{name:'Platform engineering discussion',exact:true}), folder=path.resolve('../tmp/session-popup-polish');await mkdir(folder,{recursive:true})
  for(const [width,height] of [[1366,768],[1280,720],[1024,768],[768,1024],[390,844],[390,360]]) {
    await page.setViewportSize({width,height});await expect(viewer.getByText('Ask a question about this session, or start with a suggestion below.')).toBeVisible()
    await viewer.getByLabel('Ask about this session').focus();await expect(viewer.getByRole('button',{name:'Send',exact:true})).toBeInViewport()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    await viewer.evaluate(async node=>{await Promise.all(node.getAnimations().map(animation=>animation.finished));await node.querySelector('.ws-viewer__mascot').decode()})
    await page.screenshot({path:path.join(folder,`ask-intro-${width}x${height}.png`)})
  }
  await page.setViewportSize({width:1366,height:768});await viewer.getByRole('button',{name:'Follow-up Email',exact:true}).click();await viewer.getByRole('button',{name:'Send',exact:true}).click()
  await expect(viewer.getByLabel('Follow-up email draft')).toBeVisible();await page.screenshot({path:path.join(folder,'email-draft.png')})
  await viewer.getByRole('button',{name:'Clear Chat',exact:true}).click();await expect(page.getByRole('dialog',{name:'Clear Chat?',exact:true})).toBeVisible();await page.screenshot({path:path.join(folder,'clear-chat-confirmation.png')})
  await page.setViewportSize({width:390,height:844});await expect(page.getByRole('dialog',{name:'Clear Chat?',exact:true}).getByRole('button',{name:'Keep Chat'})).toBeInViewport();await page.screenshot({path:path.join(folder,'clear-chat-mobile.png')});await page.setViewportSize({width:1366,height:768})
  await page.getByRole('button',{name:'Clear Chat',exact:true}).last().click();await page.screenshot({path:path.join(folder,'chat-cleared.png')})
  await viewer.getByRole('button',{name:'Transcript',exact:true}).click();await expect(viewer.getByText('Question for session-1',{exact:false})).toBeVisible();await viewer.getByRole('button',{name:'Clear Transcript',exact:true}).click()
  await expect(page.getByRole('dialog',{name:'Clear Transcript?',exact:true})).toBeVisible();await page.screenshot({path:path.join(folder,'clear-transcript-confirmation.png')})
  await page.getByRole('button',{name:'Delete Transcript',exact:true}).last().click();await page.screenshot({path:path.join(folder,'transcript-cleared.png')})
})

test('session modal sections, drafts, focus, scroll lock and responsive screenshots', async ({page}) => {
  await mock(page); const workspace=new Workspace(page)
  await workspace.goto('/auth/sessions','Call Sessions')
  let generation=0
  page.on('request',request=>{if(request.url().includes('/notes/generate'))generation++})
  const dialog=page.getByRole('dialog',{name:'Platform engineering discussion',exact:true})
  const trigger=workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript',exact:true})
  await trigger.click(); await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('heading',{name:'Transcript',exact:true})).toBeVisible()
  await expect(dialog.getByText('Question for session-1',{exact:false})).toBeVisible()
  await expect(page.locator('.wd-detail-cell')).toHaveCount(0)
  await expect(dialog.getByRole('button',{name:'Close session viewer'})).toBeFocused()
  await dialog.getByRole('button',{name:'Ask AI',exact:true}).click()
  await expect(dialog.getByText('Ask a question about this session, or start with a suggestion below.')).toBeVisible()
  await dialog.getByLabel('Ask about this session').fill('Unsent synthetic draft')
  await dialog.getByRole('button',{name:'AI Notes',exact:true}).click()
  await expect(dialog.getByText('Synthetic notes summary',{exact:true})).toBeVisible()
  await dialog.getByRole('button',{name:'Ask AI',exact:true}).click()
  await expect(dialog.getByLabel('Ask about this session')).toHaveValue('Unsent synthetic draft')
  await dialog.getByRole('button',{name:'Call Details',exact:true}).click()
  await expect(dialog).toContainText('Status: ended'); expect(generation).toBe(0)
  const folder=path.resolve('../tmp/session-viewer'); await mkdir(folder,{recursive:true})
  for(const [width,height] of [[1366,768],[1280,720],[1024,768],[768,1024],[390,844],[390,420]]) {
    await page.setViewportSize({width,height})
    await dialog.getByRole('button',{name:'Transcript',exact:true}).click()
    await expect(dialog.getByText('Question for session-1',{exact:false})).toBeVisible()
    const box=await dialog.boundingBox(); expect(box.width).toBeLessThanOrEqual(1040)
    expect(box.x).toBeGreaterThanOrEqual(12);expect(box.y).toBeGreaterThanOrEqual(12)
    expect(box.x+box.width).toBeLessThanOrEqual(width-12); expect(box.y+box.height).toBeLessThanOrEqual(height-12)
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    expect(await dialog.evaluate(el=>el.scrollHeight<=el.clientHeight)).toBe(true)
    await page.screenshot({path:path.join(folder,`transcript-${width}x${height}.png`)})
  }
  await page.keyboard.press('Tab');expect(await page.evaluate(()=>!!document.activeElement.closest('dialog'))).toBe(true)
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(trigger).toBeFocused()
  expect(await page.evaluate(()=>document.body.style.overflow)).toBe('')
  expect(await page.evaluate(()=>document.documentElement.style.overflow)).toBe('')
})

test('late transcript response cannot replace a different session and failures retry inside modal', async ({page}) => {
  await mock(page);const workspace=new Workspace(page);await workspace.goto('/auth/sessions','Call Sessions')
  const gate=await holdRequest(page,'**/api/interview-sessions/session-1/transcript-entries?*')
  await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript'}).click();await gate.requested
  await page.getByRole('button',{name:'Close session viewer'}).click()
  await workspace.row('Design systems discussion').getByRole('button',{name:'View Transcript'}).click()
  const dialog=page.getByRole('dialog',{name:'Design systems discussion',exact:true})
  await expect(dialog.getByText('No transcript available.')).toBeVisible();await gate.release()
  await expect(dialog.getByText('Question for session-1',{exact:false})).toHaveCount(0)
  await dialog.getByRole('button',{name:'Close session viewer'}).click()
  await page.route('**/api/interview-sessions/session-2/transcript-entries?*',route=>route.fulfill({status:503,json:{detail:'Synthetic failure'}}))
  await workspace.row('Design systems discussion').getByRole('button',{name:'View Transcript'}).click()
  await expect(dialog.getByRole('alert')).toContainText('Could not load transcript')
  await page.unroute('**/api/interview-sessions/session-2/transcript-entries?*')
  await dialog.getByRole('button',{name:'Retry transcript'}).click();await expect(dialog.getByText('No transcript available.')).toBeVisible()
})

test('long content uses one internal scroll region; mobile composer remains reachable and backdrop preserves drafts', async ({page}) => {
  await mock(page); const workspace=new Workspace(page)
  await page.route('**/api/interview-sessions/session-1/transcript-entries?*',route=>route.fulfill({json:{items:Array.from({length:30},(_,i)=>({id:`entry-${i}`,session_id:'session-1',turn_index:i+1,question_text:`Question ${i}: ${'Long synthetic question. '.repeat(15)}`,answer_text:'Safe text and code-like content <script>never execute</script>\n'.repeat(15)})),page:1,limit:100}}))
  await workspace.goto('/auth/sessions','Call Sessions')
  await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript'}).click()
  const dialog=page.getByRole('dialog',{name:'Platform engineering discussion',exact:true})
  await expect(dialog.getByText('Question 29:',{exact:false})).toHaveCount(1)
  for(const [width,height] of [[1280,720],[390,420]]) {
    await page.setViewportSize({width,height})
    const metrics=await dialog.evaluate(el=>({outer:el.scrollHeight>el.clientHeight,inner:el.querySelector('.ws-viewer__body').scrollHeight>el.querySelector('.ws-viewer__body').clientHeight}))
    expect(metrics).toEqual({outer:false,inner:true})
    await dialog.getByText('Question 29:',{exact:false}).scrollIntoViewIfNeeded()
    await expect(dialog.getByRole('button',{name:'Close session viewer'})).toBeInViewport()
  }
  await dialog.getByRole('button',{name:'Ask AI',exact:true}).click()
  const input=dialog.getByLabel('Ask about this session');await input.fill('Preserve this unsent question')
  // A resized viewport approximates keyboard occlusion; no physical mobile keyboard is claimed.
  await page.setViewportSize({width:390,height:300});await input.focus()
  const send=dialog.getByRole('button',{name:'Send'});await send.scrollIntoViewIfNeeded();await expect(send).toBeInViewport()
  await page.setViewportSize({width:1366,height:768});await page.mouse.click(5,5);await expect(dialog).toHaveCount(0)
  await workspace.menu('Platform engineering discussion');await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  await expect(dialog.getByLabel('Ask about this session')).toHaveValue('Preserve this unsent question')
  await page.emulateMedia({reducedMotion:'reduce'});await expect(dialog).toHaveCSS('animation-name','none')
})

test('notes responses and Ask AI drafts stay scoped during rapid session changes', async ({page}) => {
  await mock(page);const workspace=new Workspace(page);await workspace.goto('/auth/sessions','Call Sessions')
  const notes=await holdRequest(page,'**/api/interview-sessions/session-1/notes')
  await workspace.menu('Platform engineering discussion');await page.getByRole('menuitem',{name:'View AI Notes',exact:true}).click();await notes.requested
  await workspace.menu('Design systems discussion');await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  const second=page.getByRole('dialog',{name:'Design systems discussion',exact:true})
  await expect(second.getByText('Ask a question about this session, or start with a suggestion below.')).toBeVisible();await notes.release()
  await expect(second.getByText('Synthetic notes summary',{exact:true})).toHaveCount(0)
  await second.getByLabel('Ask about this session').fill('Second session draft')
  await workspace.menu('Platform engineering discussion');await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  const first=page.getByRole('dialog',{name:'Platform engineering discussion',exact:true})
  await expect(first.getByLabel('Ask about this session')).toHaveValue('')
  await workspace.menu('Design systems discussion');await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click()
  await expect(second.getByLabel('Ask about this session')).toHaveValue('Second session draft')
})

// Hold only test traffic; the application has no artificial loading delay.
async function holdRequest(page, pattern) {
  let release, notify
  const pending = new Promise(resolve => { release = resolve })
  const requested = new Promise(resolve => { notify = resolve })
  const handler = async route => { notify(); await pending; await route.fallback() }
  await page.route(pattern, handler)
  return { requested, release: async () => { release(); await page.unroute(pattern, handler) } }
}

test('dashboard auth skeleton is private, inert, route-specific and aligned with independent data loading', async ({page})=>{
  await mock(page,{current:readyResume})
  await page.addInitScript(()=>{window.__authGate=new Promise(resolve=>window.__finishAuth=()=>{window.__authGate=null;resolve()})})
  const account=await holdRequest(page,'**/api/auth/me'), sessionGate=await holdRequest(page,'**/api/interview-sessions?*'), resumeGate=await holdRequest(page,'**/api/resumes/current')
  const protectedRequests=[];page.on('request',request=>{if(/\/api\/(interview-sessions|resumes)/.test(request.url()))protectedRequests.push(request.url())})
  await page.goto('/auth/dashboard')
  const status=page.getByRole('status').filter({hasText:'Loading dashboard…'})
  await expect(status).toBeVisible();await expect(page.getByRole('heading',{name:'Account',exact:true})).toHaveCount(0)
  await expect(page.getByText('Checking session...',{exact:true})).toHaveCount(0)
  await expect(page.getByText('candidate@example.test',{exact:true})).toHaveCount(0)
  expect(protectedRequests).toEqual([])
  expect(await page.evaluate(()=>window.__listeners.length)).toBe(1)
  await page.keyboard.press('Tab');expect(await page.evaluate(()=>!document.activeElement.closest('.website-dashboard'))).toBe(true)
  const folder=path.resolve('../tmp/dashboard-auth-skeleton');await mkdir(folder,{recursive:true})
  const positions=new Map()
  for(const [width,height] of [[1366,768],[1280,720],[1024,768],[768,1024],[390,844]]) {
    await page.setViewportSize({width,height})
    const shape=page.locator('.wd-stats .ws-shape').first()
    expect(await shape.evaluate(node=>getComputedStyle(node).animationName)).toBe(width>1100?'ws-shimmer':'ws-pulse')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    positions.set(width,await page.locator('.wd-stats').boundingBox())
    await page.screenshot({path:path.join(folder,`auth-loading-${width}x${height}.png`)})
  }
  await page.emulateMedia({reducedMotion:'reduce'});expect(await page.locator('.ws-shape').first().evaluate(node=>getComputedStyle(node).animationName)).toBe('none')
  await page.screenshot({path:path.join(folder,'auth-loading-reduced-motion.png')});await page.emulateMedia({reducedMotion:'no-preference'})
  await page.evaluate(()=>window.__finishAuth());await account.requested
  await expect(status).toBeVisible();expect(protectedRequests).toEqual([])
  await account.release();await sessionGate.requested;await resumeGate.requested
  await expect(status).toHaveCount(0);await expect(page.getByRole('region',{name:'Resume status summary'})).toHaveAttribute('aria-busy','true')
  for(const [width,height] of [[1366,768],[1280,720],[1024,768],[768,1024],[390,844]]) {
    await page.setViewportSize({width,height});const next=await page.locator('.wd-stats').boundingBox(),before=positions.get(width)
    expect(Math.abs(next.x-before.x)).toBeLessThan(2);expect(Math.abs(next.y-before.y)).toBeLessThan(2);expect(Math.abs(next.width-before.width)).toBeLessThan(2)
  }
  await sessionGate.release();await expect(page.getByRole('region',{name:'Recent sessions summary'})).toHaveAttribute('aria-busy','false')
  await expect(page.getByRole('region',{name:'Resume status summary'})).toHaveAttribute('aria-busy','true');await resumeGate.release()
  await expect(page.getByRole('region',{name:'Resume status summary'})).toHaveAttribute('aria-busy','false')
  for(const [width,height] of [[1366,768],[1280,720],[1024,768],[768,1024],[390,844]]) {
    await page.setViewportSize({width,height});await page.screenshot({path:path.join(folder,`loaded-${width}x${height}.png`)})
  }
  await page.evaluate(()=>window.__emit('TOKEN_REFRESHED',window.__session));await expect(status).toHaveCount(0);await expect(page.locator('.ws-shape')).toHaveCount(0)
  const switchedAccount=await holdRequest(page,'**/api/auth/me')
  await page.evaluate(()=>window.__emit('SIGNED_IN',{access_token:'synthetic-second',user:{id:'second-user'}}));await switchedAccount.requested
  await expect(status).toBeVisible();await expect(page.getByText('candidate@example.test',{exact:true})).toHaveCount(0);await expect(page.getByText('Platform engineering discussion',{exact:true})).toHaveCount(0)
  await switchedAccount.release();await expect(status).toHaveCount(0);await expect(page.getByText('second@example.test',{exact:true}).first()).toBeVisible()
  await page.reload();await expect(status).toBeVisible();await page.evaluate(()=>window.__finishAuth());await expect(status).toHaveCount(0)
  await expect(page.getByRole('region',{name:'Resume status summary'})).toHaveAttribute('aria-busy','false')
  await page.goto('/auth/sessions');await expect(page.getByText('Checking session...',{exact:true})).toBeVisible();await expect(status).toHaveCount(0)
  await page.evaluate(()=>window.__finishAuth());await expect(page.getByRole('heading',{name:'Call Sessions',level:1})).toBeVisible()
})

test('skeletons resolve independently; pagination retains usable rows and filter focus', async ({page}) => {
  await mock(page,{current:readyResume})
  const gate = await holdRequest(page,'**/api/interview-sessions?*'), workspace = new Workspace(page)
  await workspace.goto('/auth/dashboard','Dashboard'); await gate.requested
  await expect(page.getByRole('region',{name:'Resume status summary'})).toContainText('Ready')
  const history = page.getByRole('region',{name:'Interview session history'})
  await expect(history).toHaveAttribute('aria-busy','true')
  await expect(history.getByRole('columnheader',{name:'Session',exact:true})).toBeVisible()
  await expect(page.locator('.ws-table-row')).toHaveCount(5)
  await expect(page.getByText('No interview sessions yet.',{exact:true})).toHaveCount(0)
  await gate.release(); await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  await expect(page.locator('.ws-shape')).toHaveCount(0)
  await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:'Call Sessions',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Call Sessions',level:1})).toBeVisible()
  await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  await expect(page.getByRole('button',{name:'Next',exact:true})).toBeEnabled()
  const next = await holdRequest(page,'**/api/interview-sessions?*')
  await page.getByRole('button',{name:'Next',exact:true}).click(); await next.requested
  await page.getByLabel('Search loaded sessions').focus()
  await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  await expect(page.locator('.ws-shape')).toHaveCount(0)
  await expect(page.getByRole('button',{name:'Next',exact:true})).toBeDisabled()
  await expect(page.getByText('Updating sessions...',{exact:true})).toBeVisible()
  await next.release(); await expect(workspace.row('Earlier session')).toBeVisible()
  await expect(page.getByLabel('Search loaded sessions')).toBeFocused()
})

test('resume metadata skeleton settles to empty or failure and retry; session data stays visible', async ({page}) => {
  await mock(page,{records:sessions.slice(0,1)})
  const gate = await holdRequest(page,'**/api/resumes/current'), workspace = new Workspace(page)
  await workspace.goto('/auth/dashboard','Dashboard'); await gate.requested
  await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  await expect(page.getByRole('region',{name:'Resume status summary'})).toHaveAttribute('aria-busy','true')
  await expect(page.getByRole('region',{name:'Recent sessions summary'})).toContainText('Showing the latest 1 session.')
  await gate.release(); await expect(page.getByRole('link',{name:'Upload Resume',exact:true})).toBeVisible()
  const resumeGate = await holdRequest(page,'**/api/resumes/current')
  await page.getByRole('link',{name:'Resumes',exact:true}).click(); await resumeGate.requested
  await expect(page.getByRole('status',{name:'Loading resume status...'})).toBeVisible()
  await expect(page.getByRole('heading',{name:'No resumes yet'})).toHaveCount(0)
  await page.evaluate(()=>window.__resumeFailure=true); await resumeGate.release()
  await expect(page.getByRole('button',{name:'Retry resume status'})).toBeVisible()
  await expect(page.locator('.ws-shape')).toHaveCount(0)
  await page.evaluate(()=>window.__resumeFailure=false); await page.getByRole('button',{name:'Retry resume status'}).click()
  await expect(page.getByRole('heading',{name:'No resumes yet'})).toBeVisible()
  await expect(page.locator('.ws-shape')).toHaveCount(0)
})

test('detail skeletons represent GET requests; generation and sending retain operation feedback', async ({page}) => {
  await mock(page); const workspace = new Workspace(page)
  await workspace.goto('/auth/sessions','Call Sessions'); await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  const transcript = await holdRequest(page,'**/api/interview-sessions/session-1/transcript-entries?*')
  await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript',exact:true}).click(); await transcript.requested
  await expect(page.getByRole('status',{name:'Loading transcript...'})).toBeVisible()
  await transcript.release(); await expect(page.getByText('Question for session-1',{exact:false})).toBeVisible()
  const notes = await holdRequest(page,'**/api/interview-sessions/session-1/notes')
  await workspace.menu('Platform engineering discussion'); await page.getByRole('menuitem',{name:'View AI Notes',exact:true}).click(); await notes.requested
  await expect(page.getByRole('status',{name:'Loading AI notes...'})).toBeVisible()
  await notes.release(); await expect(page.getByText('Synthetic notes summary',{exact:true})).toBeVisible()
  const generation = await holdRequest(page,'**/api/interview-sessions/session-1/notes/generate')
  await workspace.menu('Platform engineering discussion'); await page.getByRole('menuitem',{name:'Generate AI Notes',exact:true}).click(); await generation.requested
  await expect(page.getByText('Generating AI notes...',{exact:true})).toBeVisible()
  await expect(page.getByRole('status',{name:'Loading AI notes...'})).toHaveCount(0)
  await generation.release(); await expect(page.getByText('Synthetic notes summary',{exact:true})).toBeVisible()
  const messages = await holdRequest(page,'**/api/interview-sessions/session-1/ask-ai/messages?*')
  await workspace.menu('Platform engineering discussion'); await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click(); await messages.requested
  await expect(page.getByRole('status',{name:'Loading Ask AI messages...'})).toBeVisible()
  await messages.release(); await expect(page.getByText('Ask a question about this session, or start with a suggestion below.',{exact:true})).toBeVisible()
  const send = await holdRequest(page,'**/api/interview-sessions/session-1/ask-ai')
  await page.getByLabel('Ask about this session').fill('What can I improve?'); await page.getByRole('button',{name:'Send',exact:true}).click(); await send.requested
  await expect(page.getByRole('status',{name:'Loading Ask AI messages...'})).toHaveCount(0)
  await expect(page.getByLabel('Ask about this session')).toHaveValue('What can I improve?')
  await send.release(); await expect(page.getByText('Synthetic follow-up response',{exact:false})).toBeVisible()
})

test('account summary skeleton ends on success; navigation during pending data is safe', async ({page}) => {
  await mock(page)
  const account = await holdRequest(page,'**/api/auth/me')
  await page.goto('/auth/status'); await account.requested
  await expect(page.getByRole('status',{name:'Loading account details...'})).toBeVisible()
  await account.release(); await expect(page.getByText('candidate@example.test',{exact:true})).toBeVisible()
  await expect(page.locator('.ws-shape')).toHaveCount(0)
  const sessionsGate = await holdRequest(page,'**/api/interview-sessions?*')
  await new Workspace(page).goto('/auth/dashboard','Dashboard'); await sessionsGate.requested
  await page.getByRole('link',{name:'Resumes',exact:true}).click()
  await expect(page.getByRole('heading',{name:'No resumes yet'})).toBeVisible()
  await sessionsGate.release(); await expect(page.getByRole('heading',{name:'Resumes',level:1})).toBeVisible()
  await expect(page.getByRole('region',{name:'Interview session history'})).toHaveCount(0)
})

test('loading motion recording, matching viewports, reduced motion and overflow', async ({browser}) => {
  const folder = path.resolve('../tmp/website-skeletons'); await mkdir(folder,{recursive:true})
  const context = await browser.newContext({baseURL:'http://127.0.0.1:5173',viewport:{width:1366,height:768},recordVideo:{dir:folder,size:{width:1366,height:1024}}})
  const page = await context.newPage()
  await mock(page,{current:readyResume,email:'long-sanitized-account-email@example.test'})
  const sessionsGate = await holdRequest(page,'**/api/interview-sessions?*'), resumeGate = await holdRequest(page,'**/api/resumes/current')
  await new Workspace(page).goto('/auth/dashboard','Dashboard'); await sessionsGate.requested; await resumeGate.requested
  // CSS selectors here inspect decorative geometry and animation, not user actions.
  const shape = page.locator('.wd-stats .ws-shape').first()
  for (const [width,height] of [[1366,768],[1280,720],[768,1024],[1024,768],[390,844]]) {
    await page.setViewportSize({width,height})
    const motion = width > 1100 ? 'ws-shimmer' : 'ws-pulse'
    await expect(shape).toHaveCSS('animation-name',motion)
    const property = width > 1100 ? 'backgroundPosition' : 'opacity'
    const initial = await shape.evaluate((element,property)=>getComputedStyle(element)[property],property)
    await expect.poll(()=>shape.evaluate((element,property)=>getComputedStyle(element)[property],property)).not.toBe(initial)
    // Responsive CSS replaces the Animation instance; its currentTime can reset.
    await expect(shape).toHaveCSS('animation-duration', width > 1100 ? '1.8s' : '2.1s')
    await expect(shape).toHaveCSS('animation-iteration-count', 'infinite')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width)
    expect(await page.evaluate(()=>visualViewport.scale)).toBe(1)
    await page.screenshot({path:path.join(folder,`loading-${width}.png`),fullPage:true})
  }
  await page.emulateMedia({reducedMotion:'reduce'}); await expect(shape).toHaveCSS('animation-name','none')
  await page.screenshot({path:path.join(folder,'loading-reduced-motion.png'),fullPage:true})
  await sessionsGate.release(); await resumeGate.release()
  await expect(page.locator('.ws-shape')).toHaveCount(0)
  await expect(page.getByRole('region',{name:'Resume status summary'})).toContainText('Ready')
  await page.screenshot({path:path.join(folder,'resolved-mobile.png'),fullPage:true})
  await page.setViewportSize({width:1366,height:768}); await page.emulateMedia({reducedMotion:'no-preference'})
  const list = await holdRequest(page,'**/api/interview-sessions?*')
  await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:'Call Sessions',exact:true}).click(); await list.requested
  await expect(page.getByRole('region',{name:'Interview session history'})).toHaveAttribute('aria-busy','true')
  await page.screenshot({path:path.join(folder,'sessions-loading.png'),fullPage:true}); await list.release()
  await expect(new Workspace(page).row('Platform engineering discussion')).toBeVisible()
  const detail = await holdRequest(page,'**/api/interview-sessions/session-1/transcript-entries?*')
  await new Workspace(page).row('Platform engineering discussion').getByRole('button',{name:'View Transcript',exact:true}).click(); await detail.requested
  await expect(page.getByRole('status',{name:'Loading transcript...'})).toBeVisible()
  await page.screenshot({path:path.join(folder,'transcript-loading.png'),fullPage:true}); await detail.release(); await page.getByRole('button',{name:'Close session viewer'}).click()
  const resume = await holdRequest(page,'**/api/resumes/current')
  await page.getByRole('link',{name:'Resumes',exact:true}).click(); await resume.requested
  await expect(page.getByRole('status',{name:'Loading resume status...'})).toBeVisible()
  await page.screenshot({path:path.join(folder,'resumes-loading.png'),fullPage:true}); await resume.release()
  await expect(page.getByRole('region',{name:'Active resume',exact:true})).toBeVisible()
  await context.close(); await page.video().saveAs(path.join(folder,'loading-motion.webm'))
})

test('polish comparison screenshots at fixed viewport and zoom', async ({page}) => {
  test.skip(!process.env.DASHBOARD_CAPTURE, 'Explicit before/after capture only')
  await mock(page, {current:readyResume, email:'a-very-long-candidate-account-address@example.test'})
  const workspace = new Workspace(page), folder = path.resolve('../tmp/dashboard-polish',process.env.DASHBOARD_CAPTURE)
  await mkdir(folder,{recursive:true})
  for (const [width,height] of [[1366,768],[1920,1080],[1024,768],[390,844]]) {
    await page.setViewportSize({width,height}); await workspace.goto('/auth/dashboard','Dashboard')
    await expect(workspace.row('Platform engineering discussion')).toBeVisible(); await expect(page.locator('.wd-stats').getByText('Ready',{exact:true})).toBeVisible(); await workspace.settled()
    expect(await page.evaluate(()=>visualViewport.scale)).toBe(1)
    expect(await page.evaluate(()=>getComputedStyle(document.documentElement).zoom)).toBe('1')
    console.log(process.env.DASHBOARD_CAPTURE,width,await page.evaluate(()=>({sidebar:document.querySelector('.wd-sidebar').getBoundingClientRect().width,recent:document.querySelector('.wd-section-heading').getBoundingClientRect().top,firstRow:document.querySelector('.wd-table tbody tr').getBoundingClientRect().top})))
    await page.screenshot({path:path.join(folder,`dashboard-${width}.png`),fullPage:true,animations:'disabled'})
    await page.getByRole('button',{name:'Collapse sidebar'}).click(); await page.screenshot({path:path.join(folder,`dashboard-collapsed-${width}.png`),fullPage:true,animations:'disabled'})
    await workspace.goto('/auth/sessions','Call Sessions');await workspace.menu('Platform engineering discussion');await page.screenshot({path:path.join(folder,`sessions-menu-${width}.png`),fullPage:true,animations:'disabled'})
  }
})

test('three routes, active navigation, refresh, back/forward and six screenshots',async({page})=>{
  test.setTimeout(60_000)
  await mock(page); await page.emulateMedia({reducedMotion:'reduce'}); const workspace = new Workspace(page)
  const errors=[];page.on('pageerror',e=>errors.push(e.message));await mkdir(output,{recursive:true})
  for (const [width,height] of [[1440,1024],[390,844]]) {
    await page.setViewportSize({width,height})
    for (const [route,title,file] of [['/auth/dashboard','Dashboard','dashboard'],['/auth/sessions','Call Sessions','sessions'],['/auth/resume','Resumes','resumes']]) {
      await workspace.goto(route,title);await workspace.settled()
      await expect(page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:title,exact:true})).toHaveAttribute('aria-current','page')
      const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('*')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(e).position!=='fixed').map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right})).slice(0,15)}));expect(geometry.scroll,JSON.stringify(geometry)).toBe(width)
      await expect(page.getByText('Documents',{exact:true})).toHaveCount(0);await expect(page.getByText('Create AI Resume',{exact:true})).toHaveCount(0)
      if (file==='sessions') {await expect(workspace.row('Platform engineering discussion')).toBeVisible();await workspace.menu('Platform engineering discussion')}
      if (file==='resumes') await expect(page.getByRole('heading',{name:'No resumes yet'})).toBeVisible()
      await page.screenshot({path:path.join(output,`${file}-${width}.png`),fullPage:true,animations:'disabled'})
      if(file==='sessions')await page.keyboard.press('Escape')
      await page.reload();await expect(page.getByRole('heading',{name:title,exact:true,level:1})).toBeVisible()
    }
  }
  await page.getByRole('link',{name:'Call Sessions',exact:true}).click();await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:'Dashboard',exact:true}).click();await page.goBack();await expect(page.getByRole('heading',{name:'Call Sessions',level:1})).toBeVisible();await page.goForward();await expect(page.getByRole('heading',{name:'Dashboard',level:1})).toBeVisible()
  await expect(page.locator('.wd-stats').getByText('Recent sessions',{exact:true})).toBeVisible();await expect(page.getByText('Showing the latest 20 sessions.')).toBeVisible();await expect(page.getByText('Average Score')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('row menu keyboard, outside click, stable IDs after filter/sort, all existing actions and downloads',async({page})=>{
  await mock(page);const workspace=new Workspace(page);await workspace.goto('/auth/sessions','Call Sessions')
  await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  const trigger=page.getByRole('button',{name:'Actions for Platform engineering discussion',exact:true});await trigger.focus();await page.keyboard.press('ArrowDown')
  await expect(page.getByRole('menuitem',{name:'Generate AI Notes',exact:true})).toBeFocused();await page.keyboard.press('End');await expect(page.getByRole('menuitem',{name:'Download .md',exact:true})).toBeFocused();await page.keyboard.press('Escape');await expect(trigger).toBeFocused()
  expect((await page.evaluate(()=>window.__requests)).filter(x=>x.method==='POST')).toHaveLength(0)
  await workspace.menu('Platform engineering discussion');await page.getByRole('heading',{name:'Call Sessions',level:1}).click();await expect(page.getByRole('menu')).toHaveCount(0)
  await page.getByLabel('Sort loaded sessions').selectOption('title');await page.getByLabel('Search loaded sessions').fill('Design systems')
  await workspace.row('Design systems discussion').getByRole('button',{name:'View Transcript',exact:true}).click();await expect(page.getByText('No transcript available.',{exact:true})).toBeVisible()
  await workspace.menu('Design systems discussion');await page.getByRole('menuitem',{name:'Generate AI Notes',exact:true}).click();await expect(page.getByText('Synthetic notes summary',{exact:true})).toBeVisible()
  await workspace.menu('Design systems discussion');await page.getByRole('menuitem',{name:'View AI Notes',exact:true}).click();await workspace.menu('Design systems discussion');await page.getByRole('menuitem',{name:'View AI Notes',exact:true}).click();await expect(page.getByText('Synthetic notes summary',{exact:true})).toBeVisible()
  await workspace.menu('Design systems discussion');await page.getByRole('menuitem',{name:'Ask AI',exact:true}).click();await expect(page.getByText('Ask a question about this session, or start with a suggestion below.')).toBeVisible();await page.getByLabel('Ask about this session').fill('What can I improve?');await page.getByRole('button',{name:'Send',exact:true}).click();await expect(page.getByText('Synthetic follow-up response',{exact:false})).toBeVisible()
  for (const format of ['txt','md']) {await workspace.menu('Design systems discussion');const downloaded=page.waitForEvent('download',{timeout:5000});await page.getByRole('menuitem',{name:`Download .${format}`,exact:true}).click();const download=await downloaded;expect(download.suggestedFilename()).toBe(`interview-transcript.${format}`);expect(await readFile(await download.path(),'utf8')).toContain('Transcript for session-2')}
  const requests=await page.evaluate(()=>window.__requests);expect(requests.filter(r=>r.method==='POST'&&r.endpoint.includes('/interview-sessions/')).every(r=>r.endpoint.includes('/session-2/'))).toBe(true)
})

test('pagination scope, failed list retry, unavailable metrics and missing notes',async({page})=>{
  await mock(page,{listFailure:true,notesMissing:true});const workspace=new Workspace(page);await workspace.goto('/auth/dashboard','Dashboard');await expect(page.getByText('Unavailable',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Retry session history'})).toBeVisible();await page.evaluate(()=>window.__listFailure=false);await page.getByRole('button',{name:'Retry session history'}).click();await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:'Call Sessions',exact:true}).click();await expect(workspace.row('Platform engineering discussion')).toBeVisible();await page.getByRole('button',{name:'Next',exact:true}).click();await expect(workspace.row('Earlier session')).toBeVisible();await expect(page.getByRole('button',{name:'Next',exact:true})).toBeDisabled();await page.getByRole('button',{name:'Previous',exact:true}).click();await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  await workspace.menu('Platform engineering discussion');await page.getByRole('menuitem',{name:'View AI Notes',exact:true}).click();await expect(page.getByText('No AI notes yet. Generate AI Notes to create them.',{exact:true})).toBeVisible()
})

test('resume empty, upload restriction, extraction, review, confirmation, rebuild and delete with synthetic records',async({page})=>{
  await mock(page);const workspace=new Workspace(page);await workspace.goto('/auth/resume','Resumes');await expect(page.getByRole('heading',{name:'No resumes yet'})).toBeVisible();await page.getByRole('button',{name:'Upload Resume',exact:true}).click()
  await page.getByLabel('Resume file',{exact:true}).setInputFiles({name:'invalid.exe',mimeType:'application/octet-stream',buffer:Buffer.from('invalid')});await expect(page.getByText(/Upload a PDF, DOCX, or TXT/)).toBeVisible();await expect(page.getByRole('button',{name:'Upload and Extract'})).toBeDisabled()
  await page.getByLabel('Resume file',{exact:true}).setInputFiles({name:'profile.txt',mimeType:'text/plain',buffer:Buffer.from('Synthetic candidate profile')});await page.getByRole('button',{name:'Upload and Extract',exact:true}).click();await expect(page.getByRole('heading',{name:'Review Extracted Profile'})).toBeVisible();await page.getByLabel('Full name',{exact:true}).fill('Reviewed Candidate');await page.getByRole('button',{name:'Confirm Reviewed Profile'}).click();await expect(page.getByText('Resume confirmed and activated.',{exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'candidate-profile.pdf',exact:true})).toBeVisible();await page.getByRole('button',{name:'Rebuild Index'}).click();await expect(page.getByText('Resume index rebuilt.',{exact:true})).toBeVisible();page.once('dialog',dialog=>dialog.accept());await page.getByRole('region',{name:'Active resume',exact:true}).getByRole('button',{name:'Delete Resume',exact:true}).click();await expect(page.getByRole('heading',{name:'No resumes yet'})).toBeVisible()
})

test('populated, processing and failed resume states remain truthful',async({page})=>{
  await mock(page,{current:readyResume});const workspace=new Workspace(page);await workspace.goto('/auth/resume','Resumes');await expect(page.getByRole('heading',{name:'candidate-profile.pdf',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'No resumes yet'})).toHaveCount(0)
  await page.evaluate(()=>{window.__current={id:'processing',original_filename:'processing.pdf',status:'indexing',index_status:'building',is_active:false}});await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:'Dashboard',exact:true}).click();await page.getByRole('link',{name:'Resumes',exact:true}).click();await expect(page.getByRole('region',{name:'Resume candidate'})).toContainText('indexing');await expect(page.getByRole('heading',{name:'No resumes yet'})).toHaveCount(0)
  await page.evaluate(()=>window.__resumeFailure=true);await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:'Dashboard',exact:true}).click();await page.getByRole('link',{name:'Resumes',exact:true}).click();await expect(page.getByRole('button',{name:'Retry resume status'})).toBeVisible();await expect(page.getByText('Synthetic resume failure',{exact:true})).toBeVisible()
})

test('signed-out deep links, account switching and logout failures',async({page})=>{
  await mock(page,{signedIn:false});const workspace=new Workspace(page);await page.goto('/auth/sessions');await expect(page).toHaveURL(/\/auth\/login\?next=%2Fauth%2Fsessions/)
  await page.evaluate(()=>window.__session={access_token:'synthetic-token',user:{id:'synthetic-user'}});await page.getByRole('link',{name:'Create free account',exact:true}).click();await expect(page).toHaveURL(/\/auth\/dashboard/);await expect(page.locator('.wd-account strong').filter({hasText:'candidate@example.test'})).toBeVisible()
  await page.evaluate(()=>window.__emit('SIGNED_IN',{access_token:'synthetic-second',user:{id:'second-user'}}));await expect(page.locator('.wd-account strong').filter({hasText:'second@example.test'})).toBeVisible();await expect(page.locator('.wd-account strong').filter({hasText:'candidate@example.test'})).toHaveCount(0);await expect(workspace.row('Second account session')).toBeVisible();await expect(workspace.row('Platform engineering discussion')).toHaveCount(0)
  await page.evaluate(()=>window.__logoutFail=true);await page.getByRole('button',{name:'Logout',exact:true}).click();await expect(page.getByText('Sign out failed. Please try again.',{exact:true})).toBeVisible();await expect(page.locator('.wd-account strong').filter({hasText:'second@example.test'})).toBeVisible();await page.evaluate(()=>window.__logoutFail=false);await page.getByRole('button',{name:'Logout',exact:true}).click();await expect(page).toHaveURL(/\/auth\/login$/);await expect(page.locator('.wd-account strong').filter({hasText:'second@example.test'})).toHaveCount(0)
})

test('pending generation prevents duplicate actions; failures and retry remain on the selected session',async({page})=>{
  await mock(page);const workspace=new Workspace(page);await workspace.goto('/auth/sessions','Call Sessions');await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  let finishGeneration, requests=0, notified
  const requested=new Promise(resolve=>notified=resolve)
  await page.route('**/api/interview-sessions/session-1/notes/generate',async route=>{requests++;await new Promise(resolve=>{finishGeneration=resolve;notified()});await route.fulfill({status:409,json:{detail:'No transcript entries are available for AI notes.'}})})
  await workspace.menu('Platform engineering discussion');await page.getByRole('menuitem',{name:'Generate AI Notes',exact:true}).click();await requested
  await workspace.menu('Design systems discussion');await expect(page.getByRole('menuitem',{name:'Generate AI Notes',exact:true})).toBeDisabled();expect(requests).toBe(1);await page.keyboard.press('Escape');finishGeneration()
  await workspace.menu('Platform engineering discussion');await page.getByRole('menuitem',{name:'View AI Notes',exact:true}).click();await expect(page.getByRole('dialog',{name:'Platform engineering discussion'})).toContainText('No transcript entries are available for AI notes.');await page.getByRole('button',{name:'Close session viewer'}).click()
  let transcriptRequests=0
  await page.route('**/api/interview-sessions/session-2/transcript-entries?*',route=>{transcriptRequests++;return route.fulfill(transcriptRequests===1?{status:503,json:{detail:'Synthetic transcript failure'}}:{json:{items:[],page:1,limit:100}})})
  await workspace.row('Design systems discussion').getByRole('button',{name:'View Transcript',exact:true}).click();await expect(page.getByRole('button',{name:'Retry transcript'})).toBeVisible();await page.getByRole('button',{name:'Retry transcript'}).click();await expect(page.getByText('No transcript available.',{exact:true})).toBeVisible();expect(transcriptRequests).toBe(2)
  await page.route('**/api/interview-sessions/session-2/transcript/download?*',route=>route.fulfill({status:503,json:{detail:'Synthetic download failure'}}))
  await workspace.menu('Design systems discussion');await page.getByRole('menuitem',{name:'Download .txt',exact:true}).click();await expect(page.getByRole('dialog',{name:'Design systems discussion'})).toContainText('Could not download the transcript. Please try again.')
})

test('late transcript response cannot populate a new account; expiry removes protected content',async({page})=>{
  await mock(page);const workspace=new Workspace(page);await workspace.goto('/auth/sessions','Call Sessions');await expect(workspace.row('Platform engineering discussion')).toBeVisible()
  let release, notified
  const requested=new Promise(resolve=>notified=resolve)
  await page.route('**/api/interview-sessions/session-1/transcript-entries?*',async route=>{await new Promise(resolve=>{release=resolve;notified()});await route.fulfill({json:{items:[{id:'old-entry',session_id:'session-1',turn_index:1,question_text:'Old account private question',answer_text:'Old account private answer'}],page:1,limit:100}})})
  await workspace.row('Platform engineering discussion').getByRole('button',{name:'View Transcript',exact:true}).click();await requested
  await page.evaluate(()=>window.__emit('SIGNED_IN',{access_token:'synthetic-second',user:{id:'second-user'}}));await expect(workspace.row('Second account session')).toBeVisible();const response=page.waitForResponse(r=>r.url().includes('/session-1/transcript-entries'));release();await response
  await expect(page.getByText('Old account private question',{exact:false})).toHaveCount(0);await expect(page.locator('.wd-account strong').filter({hasText:'second@example.test'})).toBeVisible()
  await page.evaluate(()=>window.__emit('SIGNED_OUT',null));await expect(page).toHaveURL(/\/auth\/login/);await expect(page.getByRole('navigation',{name:'Workspace navigation'})).toHaveCount(0)
})

test('tablet and narrow mobile remain contained; sidebar toggle and edge menu stay accessible',async({page})=>{
  await mock(page);const workspace=new Workspace(page)
  for(const width of [768,360]) {
    await page.setViewportSize({width,height:800});await workspace.goto('/auth/sessions','Call Sessions');await expect(workspace.row('Platform engineering discussion')).toBeVisible();await workspace.menu('Interview session 20')
    const menu=page.getByRole('menu',{name:'Session actions'});const rect=await menu.boundingBox();expect(rect.x).toBeGreaterThanOrEqual(8);expect(rect.x+rect.width).toBeLessThanOrEqual(width-8);expect(rect.y+rect.height).toBeLessThanOrEqual(792);await page.keyboard.press('Escape')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width);await page.getByRole('button',{name:'Collapse sidebar'}).click();await expect(page.getByRole('navigation',{name:'Workspace navigation'})).toBeHidden();await page.getByRole('button',{name:'Expand sidebar'}).click();await expect(page.getByRole('navigation',{name:'Workspace navigation'})).toBeVisible()
  }
})

test('public login and landing retain their own layout',async({page})=>{
  await mock(page,{signedIn:false});await page.goto('/auth/login');await expect(page.getByRole('heading',{name:'Welcome back!',exact:true})).toBeVisible();await expect(page.getByRole('navigation',{name:'Workspace navigation'})).toHaveCount(0)
  await page.goto('/');await expect(page.getByRole('navigation',{name:'Workspace navigation'})).toHaveCount(0);await expect(page.getByRole('link',{name:'Log in',exact:true})).toHaveCount(2)
})

test('compact sidebar, focused full email, metadata and account setup stay website scoped',async({page})=>{
  const email='a-very-long-candidate-account-address@example.test'
  await mock(page,{current:{...readyResume,original_filename:'a-very-long-resume-filename-without-spaces-candidate-profile.pdf'},email})
  const workspace=new Workspace(page)
  for (const width of [1366,1920,1024,390]) {
    await page.setViewportSize({width,height:width===1920?1080:768});await workspace.goto('/auth/dashboard','Dashboard');await workspace.settled()
    await expect(page).toHaveTitle('Dashboard | Intervucopilot');await expect(page.locator('link[rel="icon"][href="/vite.svg"]')).toHaveCount(0)
    const account=page.locator('.wd-account'),address=account.locator('strong')
    await expect(address).toHaveText(email);await address.focus();await expect(account.getByRole('tooltip')).toHaveText(email)
    const geometry=await page.evaluate(()=>{const email=document.querySelector('.wd-account strong'),account=document.querySelector('.wd-account'),logout=account.querySelector('button');return {overflow:document.documentElement.scrollWidth,sidebar:document.querySelector('.wd-sidebar').getBoundingClientRect().width,emailHeight:email.getBoundingClientRect().height,lineHeight:parseFloat(getComputedStyle(email).lineHeight),ellipsis:getComputedStyle(email).textOverflow,logoutRight:logout.getBoundingClientRect().right,accountRight:account.getBoundingClientRect().right,recent:document.querySelector('.wd-section-heading').getBoundingClientRect().top}})
    expect(geometry.overflow).toBe(width);expect(geometry.ellipsis).toBe('ellipsis');expect(geometry.emailHeight).toBe(geometry.lineHeight);expect(geometry.logoutRight).toBeLessThanOrEqual(geometry.accountRight)
    if(width>800)expect(geometry.sidebar).toBe(280)
    if(width===1366)expect(geometry.recent).toBeLessThan(600)
    await expect(page.getByText('authenticated',{exact:true})).toHaveCount(0)
    await expect(page.getByRole('link',{name:'Cloud resume',exact:true})).toHaveCount(0);await expect(page.getByRole('link',{name:'Auth status',exact:true})).toHaveCount(0)
    await page.getByRole('button',{name:'Collapse sidebar'}).click();if(width>800)expect((await page.locator('.wd-sidebar').boundingBox()).width).toBe(80)
    await page.getByRole('button',{name:'Expand sidebar'}).click()
  }
  await page.getByText('Account setup',{exact:true}).click();await page.getByRole('button',{name:'Prepare Profile',exact:true}).click();await expect(page.getByText('Your account profile and settings are ready.')).toBeVisible()
  await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:'Call Sessions',exact:true}).click();await expect(page).toHaveTitle('Call Sessions | Intervucopilot')
  await page.getByRole('navigation',{name:'Workspace navigation'}).getByRole('link',{name:'Resumes',exact:true}).click();await expect(page).toHaveTitle('Resumes | Intervucopilot')
  await page.goto('/');await expect(page).toHaveTitle('Vite + React');await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href','/vite.svg')
})

for (const [reason,heading,label] of [
  ['processing','Your resume is processing.','Processing'],
  ['needs_confirmation','Your resume needs review.','Needs confirmation'],
  ['failed','Resume processing needs attention.','Needs attention'],
  ['not_indexed','Your resume is not ready yet.','Not ready'],
]) test(`dashboard uses server resume readiness: ${reason}`,async({page})=>{
  await mock(page,{resumeItems:[{id:'resume-pending',original_filename:'pending-profile.pdf',status:reason==='processing'?'extracting':reason==='needs_confirmation'?'needs_review':reason,readiness_reason:reason,is_active:false}]})
  const workspace=new Workspace(page);await workspace.goto('/auth/dashboard','Dashboard')
  await expect(page.getByRole('region',{name:'Resume overview'}).getByRole('heading')).toHaveText(heading)
  await expect(page.locator('.wd-stats').getByText(label,{exact:true})).toBeVisible()
  await expect(page.getByRole('link',{name:'Manage Resumes',exact:true})).toHaveAttribute('href','/auth/resume')
  await expect(page.getByText('Upload and review your resume through the Resumes page.')).toHaveCount(0)
})

test('resume missing, ready, loading, failure and retry never invent readiness',async({page})=>{
  await mock(page);const workspace=new Workspace(page);await workspace.goto('/auth/dashboard','Dashboard')
  await expect(page.getByRole('link',{name:'Upload Resume',exact:true})).toHaveAttribute('href','/auth/resume')
  await page.evaluate(()=>window.__current={id:'ready',original_filename:'ready.pdf',is_active:true,status:'ready',index_status:'indexed'})
  const navigation=page.getByRole('navigation',{name:'Workspace navigation'})
  await navigation.getByRole('link',{name:'Call Sessions',exact:true}).click();await navigation.getByRole('link',{name:'Dashboard',exact:true}).click();await expect(page.getByRole('heading',{name:'Review your resume and recent conversations.',exact:true})).toBeVisible()
  let release,notify;const requested=new Promise(resolve=>notify=resolve)
  await page.route('**/api/resumes/current',async route=>{await new Promise(resolve=>{release=resolve;notify()});await route.fulfill({status:503,json:{detail:'Synthetic failure'}})})
  await navigation.getByRole('link',{name:'Call Sessions',exact:true}).click();await navigation.getByRole('link',{name:'Dashboard',exact:true}).click();await requested
  const banner=page.getByRole('region',{name:'Resume overview'});await expect(banner).toHaveAttribute('aria-busy','true');await expect(banner.getByRole('heading')).toHaveText('Checking your resume status.');await expect(page.locator('.wd-stats').getByText('Ready',{exact:true})).toHaveCount(0)
  release();await expect(banner.getByRole('heading')).toHaveText('Resume status is unavailable.')
  await page.unroute('**/api/resumes/current');await page.getByRole('button',{name:'Retry resume status',exact:true}).click();await expect(banner.getByRole('heading')).toHaveText('Review your resume and recent conversations.')
})

for(const count of [0,1,20])test(`dashboard count and distinct subtitles with ${count} sessions`,async({page})=>{
  const records=sessions.slice(0,count).map((item,i)=>({...item,title:i===0?'Backend Engineer':item.title,target_role:i===0?'Backend Engineer':null,company_name:null}))
  await mock(page,{records});const workspace=new Workspace(page);await workspace.goto('/auth/dashboard','Dashboard')
  await expect(page.getByText(`Showing the latest ${count} ${count===1?'session':'sessions'}.`,{exact:true})).toBeVisible()
  await expect(page.locator('.wd-stats section').first().locator('strong')).toHaveText(String(count))
  await expect(page.locator('.wd-session-name div > span')).toHaveCount(0)
  await expect(page.getByText('Account total unavailable',{exact:false})).toHaveCount(0)
  if(count===0)await expect(page.getByText('No interview sessions yet.',{exact:true})).toBeVisible()
  else await expect(workspace.row('Backend Engineer')).toBeVisible()
})

test('pending and failed session history are not a zero count',async({page})=>{
  await mock(page);let release,notify;const requested=new Promise(resolve=>notify=resolve)
  await page.route('**/api/interview-sessions?*',async route=>{await new Promise(resolve=>{release=resolve;notify()});await route.fulfill({status:503,json:{detail:'Synthetic failure'}})})
  await new Workspace(page).goto('/auth/dashboard','Dashboard');await requested
  const count=page.locator('.wd-stats section').first();await expect(count.locator('strong')).toHaveText('Loading…');await expect(count).not.toContainText('Showing the latest 0')
  release();await expect(count.locator('strong')).toHaveText('Unavailable');await expect(count).not.toContainText('Showing the latest 0')
})


test('long session titles wrap inside the table without expanding the page',async({page})=>{
  const title='VeryLongSessionTitle'.repeat(20)
  await mock(page,{records:[{...sessions[0],title,target_role:null,company_name:null}]})
  const workspace=new Workspace(page)
  for(const width of [1366,390]){
    await page.setViewportSize({width,height:768});await workspace.goto('/auth/dashboard','Dashboard');await expect(workspace.row(title)).toBeVisible()
    await expect(page.locator('.wd-session-name strong')).toHaveCSS('overflow-wrap','anywhere')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width)
    await workspace.menu(title);await expect(page.getByRole('menu',{name:'Session actions'})).toBeVisible();await page.keyboard.press('Escape')
  }
})

test('final content alignment and sidebar tooltips work at fixed desktop, tablet and mobile viewports',async({page})=>{
  await mock(page,{current:readyResume,email:'very-long-account-address-that-must-stay-on-one-line@example.test'})
  const workspace=new Workspace(page)
  for(const [width,height] of [[1920,1080],[1366,768],[1024,768],[390,844]]){
    await page.setViewportSize({width,height});await workspace.goto('/auth/dashboard','Dashboard')
    await expect(page.getByRole('heading',{name:'Review your resume and recent conversations.',exact:true})).toBeVisible()
    await expect(page.getByRole('region',{name:'Resume overview'})).toContainText('Manage your resume or revisit transcripts and AI notes from your sessions.')
    for(const collapsed of [false,true]){
      const content=await page.locator('.wd-content').boundingBox();expect(content.width).toBeLessThanOrEqual(1200)
      const boxes=await page.locator('.wd-welcome, .wd-stats, .wd-banner, .wd-section-heading, .wd-table-scroll').evaluateAll(elements=>elements.map(element=>{const r=element.getBoundingClientRect();return {x:r.x,right:r.right}}))
      for(const box of boxes){expect(box.x).toBeCloseTo(boxes[0].x,1);expect(box.right).toBeCloseTo(boxes[0].right,1)}
      expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width)
      const toggle=page.getByRole('button',{name:collapsed?'Expand sidebar':'Collapse sidebar',exact:true})
      await expect(toggle).toHaveAttribute('aria-expanded',String(!collapsed));await expect(toggle).toHaveAttribute('aria-controls','wd-workspace-navigation')
      const controls=[page.locator('.wd-logo'),toggle]
      if(!collapsed || width>800){
        const nav=page.getByRole('navigation',{name:'Workspace navigation'})
        for(const label of ['Dashboard','Call Sessions','Resumes'])controls.push(nav.getByRole('link',{name:label,exact:true}))
        controls.push(page.getByRole('button',{name:'Logout',exact:true}))
        await expect(nav.getByRole('link',{name:'Dashboard',exact:true})).toHaveAttribute('aria-current','page')
      }
      for(const control of controls){
        await page.mouse.move(width-1,height-1);await page.keyboard.press('Tab');await control.focus();const tooltip=control.getByRole('tooltip');await expect(tooltip).toBeVisible()
        const rect=await tooltip.boundingBox();expect(rect.x).toBeGreaterThanOrEqual(0);expect(rect.y).toBeGreaterThanOrEqual(0);expect(rect.x+rect.width).toBeLessThanOrEqual(width);expect(rect.y+rect.height).toBeLessThanOrEqual(height)
        await expect(control).toHaveCSS('outline-style','solid');await page.keyboard.press('Escape');await expect(tooltip).toBeHidden()
        await control.hover();await expect(tooltip).toBeVisible();await page.mouse.move(width-1,height-1)
      }
      if(collapsed && width>800){
        const centers=await page.locator('.wd-logo, .wd-brand button, .wd-navigation a, .wd-account button').evaluateAll(elements=>elements.map(e=>{const r=e.getBoundingClientRect();return r.x+r.width/2}))
        for(const center of centers)expect(center).toBeCloseTo(centers[0],1)
      }
      if(!collapsed)await toggle.click()
    }
    await page.getByRole('button',{name:'Expand sidebar',exact:true}).click();await expect(page.locator('.wd-account strong')).toBeVisible()
  }
})

async function openResumeUpload(page) {
  await expect(page.getByRole('button',{name:'Upload Resume',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Upload Resume',exact:true}).click()
  await expect(page.getByRole('dialog',{name:'Upload Resume',exact:true})).toBeVisible()
}

async function extractFixtureResume(page) {
  await openResumeUpload(page)
  await page.getByLabel('Resume file',{exact:true}).setInputFiles({name:'profile.txt',mimeType:'text/plain',buffer:Buffer.from('Sanitized candidate profile')})
  await page.getByRole('button',{name:'Upload and Extract',exact:true}).click()
  await expect(page.getByRole('dialog',{name:'Review Extracted Profile',exact:true})).toBeVisible()
}

test('resume dialogs preserve all field edits and confirm exact schema and candidate attempt',async({page})=>{
  await mock(page,{current:readyResume});await new Workspace(page).goto('/auth/resume','Resumes');await extractFixtureResume(page)
  const fields={full_name:'Reviewed Candidate',email:'reviewed@example.test',phone:'+1234567890',location:'Synthetic City',current_title:'Engineer',target_role:'Senior Engineer',professional_summary:'Long sanitized summary. '.repeat(50),education:'Synthetic degree description',degree:'BSc',branch:'Computing',college:'Synthetic University',graduation_year:'2025',top_skills:'Communication, Design',technical_skills:'JavaScript, Python',tools_frameworks:'React, FastAPI',projects:'Synthetic project details',experience:'Synthetic experience details',certifications:'Synthetic certification',achievements:'Synthetic achievement'}
  const labels=['Full name','Email','Phone','Location','Current title','Target role','Professional summary','Education','Degree','Branch','College / university','Graduation year','Top skills','Technical skills','Tools / frameworks','Projects','Experience','Certifications','Achievements']
  for(const [i,value] of Object.values(fields).entries())await page.getByRole('dialog').getByLabel(labels[i],{exact:true}).fill(value)
  await page.getByRole('button',{name:'Close Review Extracted Profile',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.getByRole('button',{name:'Upload Resume',exact:true})).toBeFocused()
  expect((await page.evaluate(()=>window.__requests)).filter(r=>r.endpoint.endsWith('/confirm'))).toHaveLength(0)
  await page.getByRole('button',{name:'Review Profile',exact:true}).click()
  for(const [i,value] of Object.values(fields).entries())await expect(page.getByRole('dialog').getByLabel(labels[i],{exact:true})).toHaveValue(value)
  let body;await page.route('**/api/resumes/uploaded-resume/confirm',async route=>{body=route.request().postDataJSON();await route.fallback()})
  await page.getByRole('button',{name:'Confirm Reviewed Profile',exact:true}).click();await expect(page.getByText('Resume confirmed and activated.',{exact:true})).toBeVisible();expect(body).toEqual({extraction_attempt:1,profile:fields})
  await expect(page.getByRole('region',{name:'Active resume'})).toContainText('candidate-profile.pdf');await expect(page.getByRole('button',{name:'Review Profile',exact:true})).toHaveCount(0)
})

test('manual editor opens empty and remains an explicitly unsaved draft without cloud mutations',async({page})=>{
  await mock(page);await new Workspace(page).goto('/auth/resume','Resumes');await openResumeUpload(page);await page.getByRole('button',{name:'Input Manually',exact:true}).click()
  const dialog=page.getByRole('dialog',{name:'Enter Profile Manually',exact:true});await expect(dialog.getByLabel('Full name',{exact:true})).toHaveValue('');await dialog.getByLabel('Full name',{exact:true}).fill('Manual Draft');await expect(dialog).toContainText('Saving without an uploaded resume is not currently supported.');await expect(dialog.getByRole('button',{name:'Confirm Reviewed Profile',exact:true})).toBeDisabled()
  await page.keyboard.press('Escape');await openResumeUpload(page);await page.getByRole('button',{name:'Input Manually',exact:true}).click();await expect(page.getByLabel('Full name',{exact:true})).toHaveValue('Manual Draft');await page.keyboard.press('Escape')
  expect((await page.evaluate(()=>window.__requests)).filter(r=>r.method!=='GET')).toHaveLength(0)
})

test('upload selection validates unsupported, empty and oversized files and accepts drag and drop',async({page})=>{
  await mock(page);await new Workspace(page).goto('/auth/resume','Resumes');await openResumeUpload(page)
  for(const [name,mimeType,buffer,error] of [
    ['image.png','image/png',Buffer.from('image'),'Upload a PDF, DOCX, or TXT resume.'],
    ['empty.txt','text/plain',Buffer.alloc(0),'The selected resume file is empty.'],
    ['large.txt','text/plain',Buffer.alloc(5*1024*1024+1),'Upload a resume under 5 MB.'],
  ]){await page.getByLabel('Resume file',{exact:true}).setInputFiles({name,mimeType,buffer});await expect(page.getByRole('alert')).toHaveText(error);await expect(page.getByRole('button',{name:'Upload and Extract',exact:true})).toBeDisabled()}
  const transfer=await page.evaluateHandle(()=>{const data=new DataTransfer();data.items.add(new File(['Sanitized candidate'],'dropped.txt',{type:'text/plain'}));return data})
  await page.locator('.wr-dropzone').dispatchEvent('drop',{dataTransfer:transfer});await expect(page.getByText('dropped.txt',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Upload and Extract',exact:true})).toBeEnabled();await page.getByRole('button',{name:'Upload and Extract',exact:true}).click();await expect(page.getByRole('dialog',{name:'Review Extracted Profile'})).toBeVisible()
})

test('processing is indeterminate, dismissible, duplicate guarded and automatically opens review',async({page})=>{
  await mock(page,{current:readyResume});await new Workspace(page).goto('/auth/resume','Resumes');await openResumeUpload(page)
  let releaseUpload,uploadNotify,releaseExtract,extractNotify,uploads=0
  const uploading=new Promise(resolve=>uploadNotify=resolve),extracting=new Promise(resolve=>extractNotify=resolve)
  await page.route('**/api/resumes',async route=>{if(route.request().method()!=='POST')return route.fallback();uploads++;await new Promise(resolve=>{releaseUpload=resolve;uploadNotify()});await route.fulfill({json:{id:'uploaded-resume',original_filename:'replacement.txt',status:'uploaded'}})})
  await page.route('**/api/resumes/uploaded-resume/extract',async route=>{await new Promise(resolve=>{releaseExtract=resolve;extractNotify()});await route.fulfill({json:{status:'needs_review',extraction_attempt:3,review_required:true,profile:{full_name:'Replacement Candidate'}}})})
  await page.getByLabel('Resume file',{exact:true}).setInputFiles({name:'replacement.txt',mimeType:'text/plain',buffer:Buffer.from('Sanitized replacement')});await page.getByRole('button',{name:'Upload and Extract',exact:true}).click();await uploading
  await expect(page.getByRole('heading',{name:'Uploading resume.',exact:true})).toBeVisible();await expect(page.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow',/.+/);await expect(page.getByText(/% complete/)).toHaveCount(0);await page.keyboard.press('Escape');await expect(page.getByRole('region',{name:'Active resume'})).toContainText('candidate-profile.pdf');await expect(page.getByRole('button',{name:'Upload Resume',exact:true})).toBeDisabled();expect(uploads).toBe(1)
  releaseUpload();await extracting;await page.getByRole('button',{name:'View progress',exact:true}).click();await expect(page.getByRole('heading',{name:'Extracting profile details.',exact:true})).toBeVisible();await expect(page.getByText('You can close this dialog. Closing does not cancel the server operation.',{exact:true})).toBeVisible();await page.keyboard.press('Escape');releaseExtract();await expect(page.getByRole('dialog',{name:'Review Extracted Profile'})).toBeVisible();await expect(page.getByLabel('Full name',{exact:true})).toHaveValue('Replacement Candidate')
})

test('corrupt extraction and confirmation failure preserve the active resume and support retries',async({page})=>{
  await mock(page,{current:readyResume});await new Workspace(page).goto('/auth/resume','Resumes');let extractions=0
  await page.route('**/api/resumes/uploaded-resume/extract',route=>{extractions++;return extractions===1?route.fulfill({status:422,json:{detail:'The resume could not be parsed. Upload another file or retry.'}}):route.fallback()})
  await openResumeUpload(page);await page.getByLabel('Resume file',{exact:true}).setInputFiles({name:'corrupt.pdf',mimeType:'application/pdf',buffer:Buffer.from('not a PDF')});await page.getByRole('button',{name:'Upload and Extract',exact:true}).click();await expect(page.getByRole('alert')).toContainText('could not be parsed');await page.getByRole('button',{name:'Retry processing',exact:true}).click();await expect(page.getByRole('dialog',{name:'Review Extracted Profile'})).toBeVisible()
  await page.getByLabel('Full name',{exact:true}).fill('Keep this edited draft');let confirms=0
  await page.route('**/api/resumes/uploaded-resume/confirm',route=>{confirms++;return confirms===1?route.fulfill({status:503,json:{detail:'Resume activation failed. Please refresh and try again.'}}):route.fallback()})
  await page.getByRole('button',{name:'Confirm Reviewed Profile',exact:true}).click();await expect(page.getByRole('dialog',{name:'Review Extracted Profile'})).toBeVisible();await expect(page.getByRole('alert')).toContainText('activation failed');await expect(page.getByLabel('Full name',{exact:true})).toHaveValue('Keep this edited draft');await page.keyboard.press('Escape');await expect(page.getByRole('region',{name:'Active resume'})).toContainText('candidate-profile.pdf');await page.getByRole('button',{name:'Review Profile',exact:true}).click();await page.getByRole('button',{name:'Confirm Reviewed Profile',exact:true}).click();await expect(page.getByText('Resume confirmed and activated.',{exact:true})).toBeVisible()
})

test('candidate deletion is specific and cancelled replacement never overwrites unconfirmed edits',async({page})=>{
  await mock(page,{current:readyResume});await new Workspace(page).goto('/auth/resume','Resumes');await extractFixtureResume(page);await page.getByLabel('Full name',{exact:true}).fill('Preserved Candidate');await page.keyboard.press('Escape')
  await openResumeUpload(page);await page.getByLabel('Resume file',{exact:true}).setInputFiles({name:'another.txt',mimeType:'text/plain',buffer:Buffer.from('Another candidate')});page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'Upload and Extract',exact:true}).click();await page.keyboard.press('Escape');await page.getByRole('button',{name:'Review Profile',exact:true}).click();await expect(page.getByLabel('Full name',{exact:true})).toHaveValue('Preserved Candidate')
  let target;await page.route('**/api/resumes/uploaded-resume',async route=>{target=route.request().url();await page.evaluate(()=>window.__candidate=null);await route.fulfill({json:{deleted:true}})})
  page.once('dialog',dialog=>{expect(dialog.message()).toContain('profile.txt');return dialog.accept()});await page.getByRole('dialog').getByRole('button',{name:'Delete Resume',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);expect(target).toContain('/uploaded-resume');await expect(page.getByRole('region',{name:'Active resume'})).toContainText('candidate-profile.pdf');await expect(page.getByRole('region',{name:'Resume candidate'})).toHaveCount(0)
})

test('late resume extraction cannot populate a switched account or expired session',async({page})=>{
  await mock(page,{current:readyResume});await new Workspace(page).goto('/auth/resume','Resumes');await openResumeUpload(page)
  let release,notify;const started=new Promise(resolve=>notify=resolve)
  await page.route('**/api/resumes/uploaded-resume/extract',async route=>{await new Promise(resolve=>{release=resolve;notify()});await route.fulfill({json:{status:'needs_review',extraction_attempt:1,profile:{full_name:'Old account private draft'}}}).catch(()=>{})})
  await page.getByLabel('Resume file',{exact:true}).setInputFiles({name:'profile.txt',mimeType:'text/plain',buffer:Buffer.from('Sanitized profile')});await page.getByRole('button',{name:'Upload and Extract',exact:true}).click();await started
  await page.evaluate(()=>{window.__current=null;window.__candidate=null;window.__emit('SIGNED_IN',{access_token:'synthetic-second',user:{id:'second-user'}})});await expect(page.locator('.wd-account strong')).toHaveText('second@example.test');release();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.getByText('Old account private draft',{exact:false})).toHaveCount(0)
  await openResumeUpload(page);await page.evaluate(()=>window.__emit('SIGNED_OUT',null));await expect(page).toHaveURL(/\/auth\/login/);await expect(page.getByRole('dialog',{name:'Upload Resume',exact:true})).toHaveCount(0);await expect(page.getByRole('dialog',{name:'You’ve been signed out',exact:true})).toBeVisible()
})

test('resume screenshots, keyboard file selection, modal focus and internal scrolling at three viewports',async({page})=>{
  await mock(page);await page.emulateMedia({reducedMotion:'reduce'});const workspace=new Workspace(page),folder=path.resolve('../tmp/resume-redesign')
  await mkdir(folder,{recursive:true});const errors=[];page.on('pageerror',error=>errors.push(error.message))
  for(const [width,height] of [[1366,768],[1280,720],[390,844]]){
    await page.setViewportSize({width,height});await workspace.goto('/auth/resume','Resumes');await expect(page.getByRole('heading',{name:'No resumes yet',exact:true})).toBeVisible();await workspace.settled()
    await page.screenshot({path:path.join(folder,`empty-${width}.png`),animations:'disabled'})
    await openResumeUpload(page);await page.screenshot({path:path.join(folder,`upload-${width}.png`),animations:'disabled'})
    await page.getByLabel('Resume file',{exact:true}).focus();const choosing=page.waitForEvent('filechooser');await page.keyboard.press('Space');await (await choosing).setFiles({name:'long-sanitized-candidate-filename-for-responsive-testing.txt',mimeType:'text/plain',buffer:Buffer.from('Sanitized candidate')})
    let release,notify;const started=new Promise(resolve=>notify=resolve)
    const intercept=async route=>{await new Promise(resolve=>{release=resolve;notify()});await route.fulfill({json:{status:'needs_review',extraction_attempt:2,review_required:true,profile:{full_name:'Synthetic Candidate',email:'candidate@example.test',projects:'Long project details. '.repeat(80)}}})}
    await page.route('**/api/resumes/uploaded-resume/extract',intercept);await page.getByRole('button',{name:'Upload and Extract',exact:true}).click();await started;await expect(page.getByRole('heading',{name:'Extracting profile details.',exact:true})).toBeVisible();await page.screenshot({path:path.join(folder,`processing-${width}.png`),animations:'disabled'});release()
    const dialog=page.getByRole('dialog',{name:'Review Extracted Profile',exact:true});await expect(dialog).toBeVisible();await page.unroute('**/api/resumes/uploaded-resume/extract',intercept)
    await page.getByLabel('Professional summary',{exact:true}).fill('Long sanitized summary. '.repeat(100));await page.getByLabel('Projects',{exact:true}).fill('Editable projects. '.repeat(100));await dialog.locator('.wr-dialog-body').evaluate(body=>body.scrollTop=0)
    expect(await page.evaluate(()=>document.body.style.overflow)).toBe('hidden');const rect=await dialog.boundingBox();expect(rect.width).toBeLessThanOrEqual(width-32);expect(rect.height).toBeLessThanOrEqual(height-32);expect(rect.x).toBeGreaterThanOrEqual(0);expect(rect.y).toBeGreaterThanOrEqual(0)
    const scroll=await dialog.locator('.wr-dialog-body').evaluate(body=>({scroll:body.scrollHeight,client:body.clientHeight}));expect(scroll.scroll).toBeGreaterThan(scroll.client)
    await expect(dialog.locator('.wr-dialog-header')).toBeInViewport();await expect(dialog.locator('.wr-dialog-footer')).toBeInViewport();await page.getByRole('button',{name:'Close Review Extracted Profile',exact:true}).focus()
    for(let i=0;i<28;i++){await page.keyboard.press('Tab');expect(await dialog.evaluate(element=>element.contains(document.activeElement))).toBe(true)}
    await page.getByRole('button',{name:'Close Review Extracted Profile',exact:true}).focus();await dialog.locator('.wr-dialog-body').evaluate(body=>body.scrollTop=0);await page.screenshot({path:path.join(folder,`review-${width}.png`),animations:'disabled'})
    await page.keyboard.press('Escape');expect(await page.evaluate(()=>document.body.style.overflow)).not.toBe('hidden');await page.getByRole('button',{name:'Review Profile',exact:true}).click();await expect(page.getByLabel('Projects',{exact:true})).toHaveValue('Editable projects. '.repeat(100));await page.getByRole('button',{name:'Confirm Reviewed Profile',exact:true}).click();await expect(page.getByText('Resume confirmed and activated.',{exact:true})).toBeVisible();await page.screenshot({path:path.join(folder,`populated-${width}.png`),animations:'disabled'})
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(width)
  }
  expect(errors).toEqual([])
})

test('confirmation shows real indexing progress and prevents duplicates until the server responds',async({page})=>{
  await mock(page,{current:readyResume});await new Workspace(page).goto('/auth/resume','Resumes');await extractFixtureResume(page)
  let release,notify,requests=0;const started=new Promise(resolve=>notify=resolve)
  await page.route('**/api/resumes/uploaded-resume/confirm',async route=>{requests++;await new Promise(resolve=>{release=resolve;notify()});await route.fulfill({status:503,json:{detail:'Indexing failed. Please try confirmation again.'}})})
  await page.getByRole('button',{name:'Confirm Reviewed Profile',exact:true}).click();await started;await expect(page.getByRole('heading',{name:'Confirming profile and indexing resume.',exact:true})).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('region',{name:'Active resume'})).toContainText('candidate-profile.pdf');await expect(page.getByRole('button',{name:'Review Profile',exact:true})).toBeDisabled();expect(requests).toBe(1)
  await expect(page.getByText('Resume confirmed and activated.',{exact:true})).toHaveCount(0);release();await expect(page.getByRole('dialog',{name:'Review Extracted Profile'})).toBeVisible();await expect(page.getByRole('alert')).toContainText('Indexing failed')
})

test('confirmation refresh failure preserves the old active card and offers status refresh',async({page})=>{
  await mock(page,{current:{...readyResume,original_filename:'active-before.pdf'}});await new Workspace(page).goto('/auth/resume','Resumes');await extractFixtureResume(page)
  await page.route('**/api/resumes/current',route=>route.fulfill({status:503,json:{detail:'Synthetic refresh failure'}}))
  await page.getByRole('button',{name:'Confirm Reviewed Profile',exact:true}).click();await expect(page.getByText('Resume confirmed. Refresh to load active resume status.',{exact:true})).toBeVisible();await expect(page.getByRole('region',{name:'Active resume'})).toContainText('active-before.pdf');await expect(page.getByRole('button',{name:'Extract Again',exact:true})).toHaveCount(0)
  await page.unroute('**/api/resumes/current');await page.getByRole('button',{name:'Refresh status',exact:true}).click();await expect(page.getByRole('region',{name:'Active resume'})).toContainText('candidate-profile.pdf');await expect(page.getByRole('region',{name:'Resume candidate'})).toHaveCount(0)
})

test('resumed server processing uses status refresh, and rebuilding never changes the review target',async({page})=>{
  await mock(page,{current:readyResume,resumeItems:[{id:'pending-resume',original_filename:'pending.pdf',status:'extracting',is_active:false,readiness_reason:'processing'}]});await new Workspace(page).goto('/auth/resume','Resumes')
  await expect(page.getByRole('region',{name:'Resume candidate'})).toContainText('extracting');await expect(page.getByRole('button',{name:'Extract Again',exact:true})).toHaveCount(0)
  await page.evaluate(()=>{window.__resumeItems=[];window.__candidate={id:'pending-resume',original_filename:'pending.pdf',status:'needs_review',extraction_attempt:2}});await page.getByRole('button',{name:'Refresh status',exact:true}).click();await page.getByRole('button',{name:'Extract Again',exact:true}).click();await expect(page.getByRole('dialog',{name:'Review Extracted Profile'})).toBeVisible();await page.getByLabel('Full name',{exact:true}).fill('Pending Candidate');await page.keyboard.press('Escape')
  await page.getByRole('button',{name:'Rebuild Index',exact:true}).click();await expect(page.getByText('Resume index rebuilt.',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Review Profile',exact:true}).click();await expect(page.getByLabel('Full name',{exact:true})).toHaveValue('Pending Candidate')
  let target;await page.route('**/api/resumes/pending-resume/confirm',async route=>{target=route.request().url();await route.fulfill({status:409,json:{detail:'Synthetic attempt protection'}})})
  await page.getByRole('button',{name:'Confirm Reviewed Profile',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Synthetic attempt protection');expect(target).toContain('/pending-resume/confirm')
})

test('manual and extracted candidate drafts remain separate when reopened',async({page})=>{
  await mock(page,{current:readyResume});await new Workspace(page).goto('/auth/resume','Resumes');await extractFixtureResume(page);await page.getByLabel('Full name',{exact:true}).fill('Extracted Candidate');await page.keyboard.press('Escape')
  await openResumeUpload(page);await page.getByRole('button',{name:'Input Manually',exact:true}).click();await page.getByLabel('Full name',{exact:true}).fill('Separate Manual Draft');await page.keyboard.press('Escape')
  await page.getByRole('button',{name:'Review Profile',exact:true}).click();await expect(page.getByLabel('Full name',{exact:true})).toHaveValue('Extracted Candidate');await page.keyboard.press('Escape');await openResumeUpload(page);await page.getByRole('button',{name:'Input Manually',exact:true}).click();await expect(page.getByLabel('Full name',{exact:true})).toHaveValue('Separate Manual Draft')
  expect((await page.evaluate(()=>window.__requests)).filter(request=>request.endpoint.endsWith('/confirm'))).toHaveLength(0)
})
