import test from 'node:test';
import assert from 'node:assert/strict';
import { decimalToMinor, minorToDecimal, autoSeconds, integer, newDraft, toForm, serialize } from './catalogDraft.js';
import { catalogRequest } from './catalogApi.js';
test('currency precision and large values remain exact', () => {
  assert.equal(decimalToMinor('90071992547409.93', 2), '9007199254740993');
  assert.equal(minorToDecimal('9007199254740993', 2), '90071992547409.93');
  for (const [value, e, result] of [['123', 0, '123'], ['1.001', 3, '1001'], ['0', 2, '0'], ['', 2, null]]) assert.equal(decimalToMinor(value, e), result);
  for (const [value, e] of [['1.01', 0], ['1.001', 2], ['-1', 2], ['1e3', 2]]) assert.throws(() => decimalToMinor(value, e));
  assert.throws(() => integer(9007199254740992));
  assert.throws(() => integer('9223372036854775808'));
});
test('Auto counts integer seconds exactly without inferring unlimited', () => {
  assert.equal(autoSeconds('30', '1'), '1801');
  assert.equal(autoSeconds('', ''), null);
  assert.equal(autoSeconds(null, ''), null);
  assert.equal(autoSeconds(null, null), null);
  assert.equal(autoSeconds('0', '0'), '0');
  for (const v of [['0', '60'], ['1.5', '0'], ['9223372036854775807', '0']]) assert.throws(() => autoSeconds(...v));
});
test('incomplete draft and revision contracts', () => {
  const d = toForm(newDraft());
  d.plan.code = 'synthetic-test';
  assert.equal(serialize(d, null, 'Test').revision, '1');
  assert.equal(serialize(d, '9', 'Test').revision, '10');
  assert.deepEqual(serialize(d, null, 'Test').terms.prices, []);
  assert.throws(() => serialize(d, null, ''));
  d.plan.code = 'Bad';
  assert.throws(() => serialize(d, null, 'Test'));
});
test('HTTP preserves identity and uncertainty without automatic retries', async () => {
  let calls = 0,
    options;
  await assert.rejects(catalogRequest('http://synthetic', 'token', '/draft', {
    method: 'PATCH',
    key: 'same',
    revision: '4',
    body: {
      x: 1
    },
    fetchImpl: async (u, o) => {
      calls++;
      options = o;
      throw Error('secret');
    }
  }), e => e.code === 'catalog_write_uncertain' && !e.message.includes('secret'));
  assert.equal(calls, 1);
  assert.equal(options.headers['Idempotency-Key'], 'same');
  assert.equal(options.headers['If-Match'], '"4"');
  assert.equal(options.cache, 'no-store');
  await assert.rejects(catalogRequest('http://synthetic', 'token', '/draft', {
    fetchImpl: async () => new Response('', {
      status: 403
    })
  }), e => e.code === 'catalog_permission_denied');
});
