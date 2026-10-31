import test from 'node:test';
import assert from 'node:assert/strict';
import { checkedBasis, checkedOffer, checkedResult, checkedReview, same, successor, istToUtc, formatIst } from './catalogLifecycle.js';
import { newDraft } from './catalogDraft.js';
const id = () => crypto.randomUUID();
test('IST inputs convert exactly across midnight, year and leap-day boundaries', () => {
  assert.equal(istToUtc('2026-10-23T21:43:26'),'2026-10-23T16:13:26.000Z');
  assert.equal(istToUtc('2026-01-01T00:00'),'2025-12-31T18:30:00.000Z');
  assert.equal(istToUtc('2024-03-01T00:15:09'),'2024-02-29T18:45:09.000Z');
  assert.equal(istToUtc('2024-02-29T05:30'),'2024-02-29T00:00:00.000Z');
  for(const invalid of ['',null,'2026-02-29T10:00','2026-04-31T10:00','2026-01-01T24:00','2026-10-23T21:43Z','2026-10-23T21:43+05:30'])assert.equal(istToUtc(invalid),null);
});
test('IST conversion and display do not depend on the browser/system timezone', () => {
  const original=process.env.TZ;
  try {
    for(const tz of ['UTC','America/Los_Angeles','Asia/Tokyo']) {
      process.env.TZ=tz;
      assert.equal(istToUtc('2026-01-01T00:00'),'2025-12-31T18:30:00.000Z');
      assert.match(formatIst('2025-12-31T18:30:00Z'),/01 Jan 2026.*12:00:00 am IST/);
    }
  } finally {if(original===undefined)delete process.env.TZ;else process.env.TZ=original;}
  assert.equal(formatIst('invalid'),'Unavailable');
});
test('new version preserves terms, remaps price references, clears private notes and does not mutate source', () => {
  const source = newDraft();
  source.state = 'published';
  source.plan.code = 'synthetic';
  source.internal_notes = 'private';
  source.terms.prices = [{
    price_id: id(),
    currency: 'USD',
    exponent: '2',
    amount_minor: '9007199254740993',
    billing: null
  }];
  source.terms.discounts = [{
    discount_id: id(),
    revision: '7',
    kind: 'percentage',
    basis_points: '1250',
    price_ids: [source.terms.prices[0].price_id]
  }];
  const original = structuredClone(source),
    result = successor(source);
  assert.deepEqual(source, original);
  assert.notEqual(result.draft_id, source.draft_id);
  assert.deepEqual(result.plan, source.plan);
  assert.equal(result.state, 'draft');
  assert.equal(result.revision, '1');
  assert.equal(result.internal_notes, '');
  assert.notEqual(result.terms.prices[0].price_id, source.terms.prices[0].price_id);
  assert.equal(result.terms.prices[0].amount_minor, '9007199254740993');
  assert.notEqual(result.terms.discounts[0].discount_id, source.terms.discounts[0].discount_id);
  assert.deepEqual(result.terms.discounts[0].price_ids, [result.terms.prices[0].price_id]);
  assert.equal(result.terms.discounts[0].revision, '1');
});
test('unsafe or unsupported lifecycle DTOs fail closed', () => {
  for (const check of [checkedBasis, checkedReview, checkedResult, checkedOffer]) {
    for (const data of [null, {}, {
      publication_enabled: true
    }, {
      receipt: {
        protocol: 'future.v2'
      }
    }]) {
      assert.throws(() => check(data), error => error.code === 'catalog_stored_version_invalid');
    }
  }
  assert.equal(same({
    b: ['2'],
    a: {
      z: '1'
    }
  }, {
    a: {
      z: '1'
    },
    b: ['2']
  }), true);
  assert.equal(same({
    amount: '1'
  }, {
    amount: '2'
  }), false);
});
test('result acknowledgement must match original mutation identity and target', () => {
  const key = id(),
    offerId = id();
  const data = {
    receipt: {
      protocol: 'catalog.lifecycle.result.v1',
      request_id: key,
      operation: 'offer.retire',
      offer_version_id: offerId,
      visibility_revision: '3',
      catalog_revision: '8'
    },
    current: {
      offer_version_id: offerId,
      state: 'retired',
      revision: '3'
    },
    current_catalog_revision: '8',
    publication_enabled: false
  };
  const operation = {
    key,
    kind: 'offer.retire',
    offerId,
    body: {}
  };
  assert.deepEqual(checkedResult(data, operation), data);
  for (const override of [{
    key: id()
  }, {
    kind: 'offer.publish'
  }, {
    offerId: id()
  }]) assert.throws(() => checkedResult(data, {
    ...operation,
    ...override
  }));
  assert.throws(() => checkedResult({
    ...data,
    current: {
      ...data.current,
      revision: 3
    }
  }));
});
