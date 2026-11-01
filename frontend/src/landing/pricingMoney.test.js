import test from 'node:test';
import assert from 'node:assert/strict';
import {money,annualComparison} from './pricingMoney.js';
const price=amount=>({amount_minor:String(amount),currency:'INR',exponent:'2'});
test('annual integer savings are floored and currency is correct',()=>{
 assert.equal(money(price(39900)),'\u20b9399');
 assert.deepEqual(annualComparison(price(39900),price(299900)),{full:'\u20b94,788',saving:'37',equivalent:'\u20b9249.92'});
 assert.equal(annualComparison(price(89900),price(649900)).saving,'39');
 assert.equal(annualComparison(price(0),price(0)).saving,'0');
 assert.equal(annualComparison(price(100),{...price(100),currency:'USD'}),null);
 assert.equal(money(price('9223372036854775807')),'\u20b992,23,37,20,36,85,47,758.07');
});
