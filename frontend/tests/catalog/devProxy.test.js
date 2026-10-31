import {test} from 'node:test';
import assert from 'node:assert/strict';
import {catalogDevProxy} from '../../vite.config.js';

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
