import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
const source = readFileSync(new URL('./onboardingApi.js', import.meta.url), 'utf8')
  .replace("import { supabase } from './supabaseClient'", "const supabase = {auth:{getSession:async()=>({data:{session:globalThis.__obSession}})}}")
  .replace(/import \{ fetchCloudResumeList[^\n]+/, "const fetchCloudResumeList=async()=>[];const fetchCurrentCloudResume=async()=>({resume:null});const fetchInterviewSessions=async()=>({items:[]});const uploadCloudResume=async()=>({id:'resume'});")
const api = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))
test('onboarding client keeps credentials in data layer, sends narrow mutations and rejects failures safely', async () => {
  const original = globalThis.fetch
  try {
    globalThis.__obSession = {access_token:'synthetic'}
    const calls=[]
    globalThis.fetch=async(url,request)=>{calls.push({url,request});return {ok:true,json:async()=>({onboarding_current_step:4})}}
    assert.equal((await api.onboardingRequest('http://synthetic','/step',{current_step:4},'PATCH')).onboarding_current_step,4)
    assert.equal(calls[0].request.headers.Authorization,'Bearer synthetic')
    assert.deepEqual(JSON.parse(calls[0].request.body),{current_step:4})
    globalThis.fetch=async()=>({ok:false,json:async()=>({detail:'private internals'})})
    await assert.rejects(api.onboardingRequest('http://synthetic'), /Onboarding is unavailable/)
    globalThis.__obSession=null
    await assert.rejects(api.onboardingRequest('http://synthetic'), /Sign in again/)
  } finally {globalThis.fetch=original;delete globalThis.__obSession}
})
