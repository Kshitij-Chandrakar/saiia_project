// Explicit isolated-test entry only; never imported by the normal Vite config.
import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
const bridge=process.env.SUBSCRIPTION_DEMO_BRIDGE;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(bridge || '')) throw Error('Disposable bridge required');
const sessionModule=`
export function getSupabaseAuthConfig(){return {url:'http://127.0.0.1',anonKey:'synthetic-only'}}
export function hasSupabaseAuthConfig(){return true}
async function getSession(){const r=await fetch('/__demo/session',{cache:'no-store'});return {data:{session:(await r.json()).session}}}
export const supabase={auth:{getSession,onAuthStateChange(callback){const timer=setInterval(()=>getSession().then(r=>callback('TOKEN_REFRESHED',r.data.session)).catch(()=>{}),120000);return {data:{subscription:{unsubscribe(){clearInterval(timer)}}}}},async signOut(){await fetch('/__demo/logout');location.href='/__demo';return {error:null}}}};
export function createSupabaseBrowserClient(){return supabase}
`;
export default defineConfig({
  envFile:false,
  define:{'import.meta.env.VITE_BACKEND_URL':JSON.stringify('http://127.0.0.1:5187')},
  plugins:[{
    name:'isolated-demo-only',enforce:'pre',
    load(id){if(id.replaceAll('\\','/').endsWith('/src/auth/supabaseClient.js')) return sessionModule;},
    transformIndexHtml(html){return html.replace('<body>',`<body><div style="position:sticky;top:0;z-index:10000;background:#172554;color:white;padding:10px 16px;font:14px system-ui;text-align:center">Isolated demo — disposable data; no payments or AI calls. <a style="color:#a5f3fc" href="/__demo">Demo controls / switch account</a></div>`);}
  },react()],
  server:{host:'127.0.0.1',port:5187,strictPort:true,proxy:{'/api/':bridge,'/__demo':bridge}}
});
