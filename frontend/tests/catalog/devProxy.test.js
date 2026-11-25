import {test} from 'node:test';
import assert from 'node:assert/strict';
import {catalogDevProxy} from '../../vite.config.js';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

test('installed-test cleanup attempts every close without replacing the primary failure',async()=>{
  const source=readFileSync(new URL('./c12-installed.spec.js',import.meta.url),'utf8').replace(/\r\n/g,'\n');
  const start=source.indexOf('  let cleanupFailure;');
  const block=source.slice(start,source.indexOf('\n }\n});',start));
  assert.ok(start>0&&block.includes('if(!primaryFailure&&cleanupFailure)'));
  for(const primaryFailure of [undefined,new Error('original failure')]){
    const calls=[],releaseFailure=new Error('release failed');
    const cleanup=vm.runInNewContext(`async()=>{${block}}`,{
      primaryFailure,
      control:async()=>{calls.push('release');throw releaseFailure;},
      app:{close:async()=>{calls.push('app');}},
      browser:{close:async()=>{calls.push('browser');throw Error('browser failed');}}
    });
    if(primaryFailure)await cleanup();
    else await assert.rejects(cleanup(),error=>error===releaseFailure);
    assert.deepEqual(calls,['release','app','browser']);
  }
});

test('checkout fixtures preserve explicit offer and price query parameters',()=>{
  const source=readFileSync(new URL('./fixtures/razorpay.jsx',import.meta.url),'utf8');
  const block=source.slice(source.indexOf("if(location.pathname"),source.indexOf('createRoot('));
  for(const search of ['?case=2&offer=selected&price=selected-price&keep=yes','?case=2']){
    let target;
    vm.runInNewContext(block,{URLSearchParams,location:{pathname:'/auth/checkout',search},index:'2',data:{offer:'default',price:'default-price'},history:{replaceState:(_a,_b,url)=>target=url}});
    const params=new URL(target,'http://localhost').searchParams;
    assert.equal(params.get('offer'),search.includes('offer=')?'selected':'default');
    assert.equal(params.get('price'),search.includes('price=')?'selected-price':'default-price');
    assert.equal(params.get('case'),'2');
  }
});

test('local preview is explicit, exact GET only, and preserves configured targets',()=>{
  for(const [enabled,method,url,override,target] of [
    [false,'GET','/api/catalog',undefined,'http://127.0.0.1:8000'],
    [true,'GET','/api/catalog',undefined,'http://127.0.0.1:5188'],
    [true,'POST','/api/catalog',undefined,'http://127.0.0.1:8000'],
    [true,'GET','/api/admin/catalog/drafts',undefined,'http://127.0.0.1:8000'],
    [true,'GET','/api/catalog/',undefined,'http://127.0.0.1:8000'],
    [true,'GET','/api/catalog','http://127.0.0.1:9000','http://127.0.0.1:9000']
  ]) {
    const config=catalogDevProxy({CATALOG_DEV_PROXY_TARGET:override},()=>enabled);
    const req={method,url};
    let forwarded;const listeners={},removed=[];
    const proxy={web(_req,_res,options){forwarded=options.target;},on(event,fn){listeners[event]=fn;}};
    config.configure(proxy);proxy.web(req,{},{});
    assert.equal(forwarded,target);
    listeners.proxyReq({removeHeader(name){removed.push(name);}},req);
    assert.deepEqual(removed,target==='http://127.0.0.1:5188'?['authorization','cookie']:[]);
    const response={headers:{}};listeners.proxyRes(response,req);
    assert.equal(response.headers['x-catalog-environment'],target==='http://127.0.0.1:5188'?'isolated-demo':undefined);
  }
});

test('a stopped catalog returns unavailable without retrying another environment',()=>{
  for (const preview of [false,true]) {
    let calls=0,status,headers,body;
    const proxy={on(){},web(_req,_res,_options,callback){calls++;callback(Object.assign(new Error('refused'),{code:'ECONNREFUSED'}));}};
    catalogDevProxy({},()=>preview).configure(proxy);
    proxy.web({method:'GET',url:'/api/catalog'},{
      writeHead(code,value){status=code;headers=value;},
      end(value){body=JSON.parse(value);}
    },{});
    assert.equal(calls,1);
    assert.equal(status,503);
    assert.equal(headers['Cache-Control'],'no-store');
    assert.deepEqual(body,{error:'catalog_unavailable'});
  }
});

test('proxy failure does not write over a closed or started response',()=>{
  const proxy={on(){},web(_req,_res,_options,callback){callback(new Error('closed'));}};
  catalogDevProxy({},()=>true).configure(proxy);
  for (const state of [{destroyed:true},{writableEnded:true},{headersSent:true}]) {
    let destroyed=false;
    proxy.web({method:'GET',url:'/api/catalog'},{...state,
      writeHead(){assert.fail('must not write headers');},
      end(){assert.fail('must not write body');},
      destroy(){destroyed=true;}
    },{});
    assert.equal(destroyed,Boolean(state.headersSent));
  }
});
