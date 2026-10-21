import {test} from 'node:test'
import assert from 'node:assert/strict'
import {createHash} from 'node:crypto'
import {layoutGraph} from './diagram_layout.js'
import {canonicalRevision} from './diagram_source_revision.js'
test('bounded Dagre graph with cycles and full labels produces finite geometry',()=>{
 const nodes=Array.from({length:20},(_,i)=>({id:`n${i}`,label:'A meaningful technical component '.repeat(3).slice(0,80),kind:'service'}))
 const edges=Array.from({length:32},(_,i)=>({source:`n${i%20}`,target:`n${(i+1+Math.floor(i/20))%20}`,label:'Data flow'}))
 const result=layoutGraph({nodes,edges})
 assert.equal(result.nodes.length,20);assert.equal(result.edges.length,32)
 assert.ok(result.width<10000&&result.height<20000)
 for(const edge of result.edges)assert.ok(edge.points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)))
})
test('local canonical hash uses versioned server representation and normalizes transport line endings',async()=>{
 const question=' Design a queue\r\n',answer='Unicode \u03bb \ud83d\ude00, "quoted" \\ API\r\nQueue. '
 const q=question.trim(),a=answer.replace(/\r\n/g,'\n').trim()
 const expected='v1:'+createHash('sha256').update(`[${JSON.stringify(q)}, ${JSON.stringify(a)}]`).digest('hex')
 assert.equal(await canonicalRevision(question,answer),expected)
})
