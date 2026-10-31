import { test, expect } from '@playwright/test';
const U = '10000000-0000-4000-8000-000000000001',
  D = '00000000-0000-4000-8000-000000000001',
  P = '00000000-0000-4000-8000-000000000002',
  O = '00000000-0000-4000-8000-000000000004',
  R = '00000000-0000-4000-8000-000000000005';
const terms = {
  name: 'Synthetic plan',
  description: 'Fixture terms',
  subscription_policy_ref: 'synthetic.lifecycle',
  migration_policy_ref: 'synthetic.migration',
  prices: [{
    price_id: '00000000-0000-4000-8000-000000000003',
    currency: 'USD',
    exponent: '2',
    amount_minor: '1000',
    billing: {
      unit: 'year',
      count: '1'
    }
  }],
  entitlements: [{
    feature: 'answers.generate',
    allowed: true,
    model_keys: [],
    audio_sources: []
  }],
  limits: [{
    meter: 'auto.authorized_running',
    feature: 'assistant.auto',
    amount: '125',
    kind: 'quota',
    unit: 'second',
    grant_kind: 'recurring',
    reset: {
      unit: 'month',
      count: '1',
      anchor: 'calendar',
      timezone: 'UTC'
    }
  }],
  discounts: []
};
const draft = () => ({
  draft_id: D,
  plan: {
    plan_id: P,
    code: 'synthetic'
  },
  revision: '1',
  state: 'draft',
  contract_version: 'catalog.v1',
  registry_version: 'catalog.features.v1',
  internal_notes: 'synthetic private',
  terms: structuredClone(terms)
});
class Workspace {
  constructor(page) {
    this.page = page;
  }
  async open() {
    await this.page.getByLabel('Open a draft by ID', {
      exact: true
    }).fill(D);
    await this.page.getByRole('button', {
      name: 'Open draft',
      exact: true
    }).click();
    await expect(this.page.getByLabel('Display name', {
      exact: true
    })).toHaveValue('Synthetic plan');
  }
  async prepare() {
    await this.page.getByRole('button', {
      name: 'Preview saved draft',
      exact: true
    }).click();
    await this.page.getByRole('button',{name:'Close subscription review',exact:true}).click();
    await this.page.getByLabel('Offer starts at (IST)', {
      exact: true
    }).fill('2026-01-01T00:00');
    await this.page.getByLabel('Lifecycle reason', {
      exact: true
    }).fill('Synthetic reason');
    await this.page.getByRole('button', {
      name: 'Review for publication',
      exact: true
    }).click();
    await expect(this.page.getByRole('dialog', {
      name: 'Subscription review',
      exact: true
    })).toBeVisible();
  }
  async review() {
    await this.prepare();
    await this.page.getByRole('button', {
      name: 'Confirm review',
      exact: true
    }).click();
    await expect(this.page.getByRole('button', {
      name: 'Publish reviewed offer',
      exact: true
    })).toBeVisible();
    await this.page.getByRole('button',{name:'Close subscription review',exact:true}).click();
  }
  async publish() {
    await this.page.getByRole('button', {
      name: 'Publish reviewed offer',
      exact: true
    }).click();
    await this.page.getByRole('button', {
      name: 'Confirm publication',
      exact: true
    }).click();
  }
}
async function setup(page) {
  const s = {
    draft: draft(),
    basis: null,
    review: null,
    offer: null,
    operations: {},
    writes: [],
    keys: [],
    hold: null,
    uncertain: false,
    error: null,
    permission: true,
    catalog: {catalog_revision:'1',offers:[]},
    catalogUnavailable:false
  };
  await page.addInitScript(U => {
    window.__session = {
      access_token: 'synthetic',
      user: {
        id: U
      }
    };
    window.__listeners = [];
  }, U);
  await page.route('**/src/auth/supabaseClient.js*', r => r.fulfill({
    contentType: 'application/javascript',
    body: `window.__emit=(event,s)=>{window.__session=s;window.__listeners.forEach(fn=>fn(event,s))};export const supabase={auth:{getSession:async()=>({data:{session:window.__session}}),onAuthStateChange:fn=>{window.__listeners.push(fn);return {data:{subscription:{unsubscribe(){}}}}},signOut:async()=>{window.__emit('SIGNED_OUT',null);return {error:null}}}};export function getSupabaseAuthConfig(){return {}};`
  }));
  await page.route('**/api/**', async route => {
    const q = route.request(),
      p = new URL(q.url()).pathname,
      body = q.method() === 'GET' ? null : q.postDataJSON(),
      key = q.headers()['idempotency-key'];
    const fail = code => route.fulfill({
      status: code === 'catalog_permission_denied' ? 403 : code === 'catalog_not_found' ? 404 : code === 'catalog_database_unavailable' ? 503 : 409,
      json: {
        detail: {
          code
        }
      }
    });
    if (p === '/api/commercial/admin/me') return route.fulfill({
      json: {
        permissions: s.permission ? ['subscriptions.manage'] : []
      }
    });
    if (!s.permission) return fail('catalog_permission_denied');
    if(p==='/api/catalog')return s.catalogUnavailable ? fail('catalog_database_unavailable') : route.fulfill({json:s.catalog});
    if (p.endsWith('/preview')) {
      if (body.scope !== 'publication_review') return route.fulfill({
        json: {
          draft_id: D,
          revision: s.draft.revision,
          publishable: !s.incomplete,
          validation_scope: 'structural_only',
          publication_enabled: false,
          errors: [],
          pending: s.incomplete ? [{
            path: ['terms', 'name'],
            code: 'required'
          }] : []
        }
      });
      if (s.error) return fail(s.error);
      s.basis = {
        protocol: 'catalog.review.v1',
        contract_version: 'catalog.v1',
        registry_version: 'catalog.features.v1',
        validation_policy_version: 'catalog.validation.v1',
        draft_id: D,
        plan_id: P,
        revision: s.draft.revision,
        source_hash: 'a'.repeat(64),
        terms_fingerprint: 'b'.repeat(64),
        authority: {
          valid_until: '2050-01-01T00:00:00Z'
        },
        intent: body.intent,
        current_offer: null,
        archived_offer: null
      };
      return route.fulfill({
        json: {
          basis: s.basis,
          validation_scope: 'publication_review',
          publication_enabled: false
        }
      });
    }
    if (q.method() === 'GET') {
      if (p.includes('/operations/')) return s.operations[p.split('/').pop()] ? route.fulfill({
        json: s.operations[p.split('/').pop()]
      }) : fail('catalog_not_found');
      if (p.includes('/offers/')) return route.fulfill({
        json: s.offer
      });
      return route.fulfill({
        json: s.draft
      });
    }
    if (q.method() === 'PATCH') {
      s.draft = body.document;
      return route.fulfill({
        json: s.draft
      });
    }
    if (s.hold) await s.hold;
    if (s.error) return fail(s.error);
    s.keys.push(key);
    if (!s.operations[key]) {
      s.writes.push({
        path: p,
        body,
        key,
        revision: q.headers()['if-match']
      });
      if (p.endsWith('/publication-reviews')) s.operations[key] = s.review = {
        receipt: {
          storage_version: 'catalog.review.store.v1',
          review_id: R,
          reviewer_subject: U,
          basis: body.basis
        },
        state: 'current',
        publication_enabled: false,
        consumption_state: 'not_checked'
      };else {
        const retired = p.endsWith('/retire');
        s.operations[key] = {
          receipt: {
            protocol: 'catalog.lifecycle.result.v1',
            request_id: key,
            actor_subject: U,
            operation: retired ? 'offer.retire' : 'offer.publish',
            offer_version_id: O,
            review_id: retired ? null : R,
            visibility_revision: retired ? '3' : '2',
            catalog_revision: retired ? '3' : '2'
          },
          current: {
            offer_version_id: O,
            revision: retired ? '3' : '2',
            state: retired ? 'retired' : 'visible'
          },
          current_catalog_revision: retired ? '3' : '2',
          publication_enabled: false
        };
        s.offer = {
          snapshot: {
            offer_version_id: O,
            version: '1',
            plan: s.draft.plan,
            terms: s.draft.terms,
            contract_version: 'catalog.v1',
            registry_version: 'catalog.features.v1'
          },
          current: s.operations[key].current,
          source: {
            ...s.draft,
            revision: '2',
            state: 'published'
          },
          publication: {
            fingerprint: 'c'.repeat(64)
          },
          catalog_revision: retired ? '3' : '2',
          publication_enabled: false,
          purchasable: false
        };
      }
    }
    if (s.uncertain) {
      s.uncertain = false;
      return route.abort('failed');
    }
    return route.fulfill({
      json: s.operations[key]
    });
  });
  await page.goto('/auth/admin/subscriptions');
  const ui = new Workspace(page);
  await ui.open();
  return {
    s,
    ui
  };
}
test('review, explicit confirmation, publish, terminal view and retire', async ({
  page
}, info) => {
  const {
    s,
    ui
  } = await setup(page);
  await ui.prepare();
  expect(s.basis.intent.valid_from).toBe('2025-12-31T18:30:00.000Z');
  const dialog = page.getByRole('dialog', {
    name: 'Subscription review',
    exact: true
  });
  await expect(dialog).toContainText('USD 10.00');
  await expect(dialog).toContainText('01 Jan 2026');
  await expect(dialog).toContainText('12:00:00 am IST');
  await expect(dialog).toContainText('2 min 5 sec');
  await expect(dialog.getByRole('button', {
    name: 'Close subscription review',
    exact: true
  })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole('button', {
    name: 'Review for publication',
    exact: true
  })).toBeFocused();
  expect(s.writes).toHaveLength(0);
  await ui.review();
  expect(s.writes).toHaveLength(1);
  await ui.publish();
  await expect(page.getByRole('heading', {
    name: 'Published offer · version 1',
    exact: true
  })).toBeVisible();
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toBeDisabled();
  await page.screenshot({
    path: info.outputPath('published-desktop.png'),
    fullPage: true
  });
  await page.getByRole('button', {
    name: 'Retire this offer',
    exact: true
  }).click();
  const retiring = page.getByRole('dialog', {
    name: 'Retire this offer?',
    exact: true
  });
  await expect(retiring).toContainText(O);
  await expect(retiring).toContainText('No payment or subscription cancellation');
  await retiring.getByRole('button', {
    name: 'Confirm retirement',
    exact: true
  }).click();
  await expect(page.getByRole('heading', {
    name: 'Retired offer · version 1',
    exact: true
  })).toBeVisible();
  expect(s.writes).toHaveLength(3);
  expect(s.writes[2].revision).toBe('"2"');
  expect(await page.evaluate(() => [...Object.values(localStorage), ...Object.values(sessionStorage)].join(''))).not.toContain('synthetic private');
});
test('uncertain write, Stay, same-key retry, recovery after reload never resubmits', async ({
  page
}) => {
  const {
    s,
    ui
  } = await setup(page);
  await ui.review();
  s.uncertain = true;
  await ui.publish();
  await expect(page.getByRole('alert')).toContainText('outcome is unknown');
  await expect(page.getByRole('button',{name:'Close draft',exact:true})).toBeDisabled();
  const id = await page.getByLabel('Operation ID', {
    exact: true
  }).inputValue();
  const writes = s.writes.length;
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  const dialog = page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  });
  await dialog.getByRole('button', {
    name: 'Stay',
    exact: true
  }).click();
  await expect(page.getByLabel('Operation ID', {
    exact: true
  })).toHaveValue(id);
  await page.getByRole('button', {
    name: 'Retry same action',
    exact: true
  }).click();
  await expect(page.getByRole('heading', {
    name: 'Published offer · version 1',
    exact: true
  })).toBeVisible();
  expect(s.writes.length).toBe(writes);
  expect(s.keys.at(-1)).toBe(id);
  await page.reload();
  await expect(page.getByRole('heading', {
    name: 'Review and publication',
    exact: true
  })).toBeVisible();
  expect(s.writes.length).toBe(writes);
  await page.getByLabel('Check an operation by ID', {
    exact: true
  }).fill(id);
  await page.getByRole('button', {
    name: 'Check operation',
    exact: true
  }).click();
  await expect(page.getByRole('heading', {
    name: 'Published offer · version 1',
    exact: true
  })).toBeVisible();
  expect(s.writes.length).toBe(writes);
});
for (const code of ['catalog_review_stale', 'catalog_database_unavailable', 'catalog_request_identity_conflict']) test(`safe ${code}`, async ({
  page
}) => {
  const {
    s,
    ui
  } = await setup(page);
  await ui.review();
  s.error = code;
  await ui.publish();
  await expect(page.getByRole('alert')).toContainText(code === 'catalog_review_stale' ? 'fresh review' : code === 'catalog_database_unavailable' ? 'unavailable' : 'different request details');
  expect(s.writes).toHaveLength(1);
});
test('dirty content invalidates review; incomplete preview disables requests', async ({
  page
}) => {
  const {
    s,
    ui
  } = await setup(page);
  s.incomplete = true;
  await page.getByRole('button', {
    name: 'Preview saved draft',
    exact: true
  }).click();
    await page.getByRole('button',{name:'Close subscription review',exact:true}).click();
  await expect(page.getByRole('button', {
    name: 'Review for publication',
    exact: true
  })).toBeDisabled();
  s.incomplete = false;
  await ui.review();
  await page.getByLabel('Display name', {
    exact: true
  }).fill('Changed after review');
  await expect(page.getByRole('button', {
    name: 'Publish reviewed offer',
    exact: true
  })).toHaveCount(0);
  await expect(page.getByRole('button', {
    name: 'Review for publication',
    exact: true
  })).toBeDisabled();
});
test('mutation revocation clears private state', async ({
  page
}) => {
  const {
    s,
    ui
  } = await setup(page);
  await ui.review();
  s.permission = false;
  await ui.publish();
  await expect(page.getByRole('heading', {
    name: 'Page not found',
    exact: true
  })).toBeVisible();
  await expect(page.getByText('Fixture terms', {
    exact: true
  })).toHaveCount(0);
});
for (const event of ['logout', 'switch', 'revocation']) test(`pending lifecycle ${event} clears state and ignores late success`, async ({
  page
}) => {
  const {
    s,
    ui
  } = await setup(page);
  await ui.review();
  let release;
  s.hold = new Promise(resolve => {
    release = resolve;
  });
  await ui.publish();
  await expect(page.getByRole('button', {
    name: 'Check pending operation',
    exact: true
  })).toBeDisabled();
  if (event === 'revocation') {
    s.permission = false;
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  } else await page.evaluate(event => window.__emit(event === 'logout' ? 'SIGNED_OUT' : 'SIGNED_IN', event === 'logout' ? null : {
    access_token: 'other',
    user: {
      id: '10000000-0000-4000-8000-000000000002'
    }
  }), event);
  if (event === 'switch') await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveCount(0);else await expect(page.getByRole('heading', {
    name: event === 'logout' ? 'Page not found' : 'Page not found',
    exact: true
  })).toBeVisible();
  release();
  await expect(page.getByRole('heading', {
    name: 'Published offer · version 1',
    exact: true
  })).toHaveCount(0);
  await expect(page.getByLabel('Operation ID', {
    exact: true
  })).toHaveCount(0);
  await expect(page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  })).not.toBeVisible();
});
test('policy unavailable during review creates no receipt; operation not found stays uncertain', async ({
  page
}) => {
  const {
    s,
    ui
  } = await setup(page);
  s.error = 'catalog_database_unavailable';
  await page.getByRole('button', {
    name: 'Preview saved draft',
    exact: true
  }).click();
    await page.getByRole('button',{name:'Close subscription review',exact:true}).click();
  await page.getByLabel('Offer starts at (IST)', {
    exact: true
  }).fill('2026-01-01T00:00');
  await page.getByLabel('Lifecycle reason', {
    exact: true
  }).fill('Synthetic unavailable policy');
  await page.getByRole('button', {
    name: 'Review for publication',
    exact: true
  }).click();
  await expect(page.getByRole('alert')).toContainText('unavailable');
  expect(s.writes).toHaveLength(0);
  await page.getByRole('button',{name:'Close subscription review',exact:true}).click();
  s.error = null;
  await ui.review();
  s.uncertain = true;
  await ui.publish();
  await expect(page.getByRole('alert')).toContainText('outcome is unknown');
  const id = await page.getByLabel('Operation ID', {
    exact: true
  }).inputValue();
  const recorded = s.operations[id];
  delete s.operations[id];
  await page.getByRole('button', {
    name: 'Check pending operation',
    exact: true
  }).click();
  await expect(page.getByRole('alert')).toContainText('does not prove');
  await expect(page.getByLabel('Operation ID', {
    exact: true
  })).toHaveValue(id);
  s.operations[id] = recorded;
  await page.getByRole('button', {
    name: 'Check pending operation',
    exact: true
  }).click();
  await expect(page.getByRole('heading', {
    name: 'Published offer · version 1',
    exact: true
  })).toBeVisible();
  expect(s.writes).toHaveLength(2);
});
test('double-click prevention and mobile dialog bounds', async ({
  page
}, info) => {
  const {
    s,
    ui
  } = await setup(page);
  await page.setViewportSize({
    width: 390,
    height: 844
  });
  await ui.prepare();
  const dialog = page.getByRole('dialog', {
    name: 'Subscription review',
    exact: true
  });
  expect(await dialog.evaluate(e => {
    const r = e.getBoundingClientRect();
    return r.left >= 0 && r.right <= innerWidth && r.bottom <= innerHeight;
  })).toBe(true);
  await page.screenshot({
    path: info.outputPath('review-mobile.png')
  });
  let release;
  s.hold = new Promise(r => release = r);
  await dialog.getByRole('button', {
    name: 'Confirm review',
    exact: true
  }).dblclick();
  await expect(page.getByRole('button', {
    name: 'Check pending operation',
    exact: true
  })).toBeDisabled();
  release();
  await expect(page.getByRole('button', {
    name: 'Publish reviewed offer',
    exact: true
  })).toBeVisible();
  expect(s.writes).toHaveLength(1);
});


test('closing subscription review preserves pending identity and receipt without replay or publication',async({page})=>{
 const {s,ui}=await setup(page);await ui.prepare();
 const modal=page.getByRole('dialog',{name:'Subscription review',exact:true});
 let release;s.hold=new Promise(resolve=>release=resolve);
 await modal.getByRole('button',{name:'Confirm review',exact:true}).click();
 const key=await modal.getByLabel('Operation ID',{exact:true}).inputValue();
 await modal.getByRole('button',{name:'Close subscription review',exact:true}).click();
 await page.getByRole('button',{name:'Open subscription review',exact:true}).click();
 await expect(modal.getByLabel('Operation ID',{exact:true})).toHaveValue(key);expect(s.writes).toHaveLength(0);
 release();s.hold=null;await expect(modal.getByRole('button',{name:'Publish reviewed offer',exact:true})).toBeEnabled();
 expect(s.writes).toHaveLength(1);await page.keyboard.press('Escape');
 await expect(page.getByRole('button',{name:'Open subscription review',exact:true})).toBeFocused();
 await page.getByRole('button',{name:'Open subscription review',exact:true}).click();
 await expect(modal).toContainText('Review recorded for revision 1');expect(s.writes).toHaveLength(1);
 await modal.getByRole('button',{name:'Publish reviewed offer',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Publish this offer?',exact:true})).toBeVisible();
 expect(await page.locator('dialog[open]').count()).toBe(1);expect(s.writes).toHaveLength(1);
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.getByLabel('Display name',{exact:true}).fill('New local terms');
 await expect(page.getByRole('button',{name:'Publish reviewed offer',exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('New local terms');expect(s.writes).toHaveLength(1);
});


test('expired review is shown inside popup without recording a receipt',async({page})=>{
 const {s,ui}=await setup(page);await ui.prepare();
 await page.clock.install({time:new Date('2051-01-01T00:00:00Z')});
 await page.getByRole('button',{name:'Confirm review',exact:true}).click();
 const modal=page.getByRole('dialog',{name:'Subscription review',exact:true});
 await expect(modal.getByRole('alert')).toContainText('approval changed');
 expect(s.writes).toHaveLength(0);await page.keyboard.press('Escape');
 await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Synthetic plan');
});

test('logout while review popup write is pending clears private modal and late response cannot reopen it',async({page})=>{
 const {s,ui}=await setup(page);await ui.prepare();let release;s.hold=new Promise(resolve=>release=resolve);
 await page.getByRole('button',{name:'Confirm review',exact:true}).click();
 await expect(page.getByLabel('Operation ID',{exact:true})).toBeVisible();
 await page.evaluate(()=>window.__emit('SIGNED_OUT',null));
 await expect(page.getByRole('heading',{name:'Page not found',exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.body.style.overflow)).not.toBe('hidden');
 release();s.hold=null;await expect(page.getByRole('dialog',{name:'Subscription review',exact:true})).toHaveCount(0);
 await expect(page.getByText('Synthetic plan',{exact:true})).toHaveCount(0);
});


test('published offers list opens current terms and creates a draft version without copying identifiers',async({page})=>{
 const {s}=await setup(page);
 s.catalog={catalog_revision:'2',offers:[{name:'Synthetic plan',offer_version_id:O,version:'1'}]};
 const source={...draft(),state:'published'};
 s.offer={snapshot:{contract_version:'catalog.v1',registry_version:'catalog.features.v1',plan:source.plan,offer_version_id:O,version:'1',terms:source.terms},current:{offer_version_id:O,revision:'2',state:'visible',valid_from:'2026-01-01T00:00:00Z',valid_until:null,retired_at:null},publication:{fingerprint:'b'.repeat(64)},source,catalog_revision:'2',publication_enabled:false,purchasable:false};
 const list=page.getByRole('region',{name:'Published offers',exact:true});
 await list.getByRole('button',{name:'Refresh offers',exact:true}).click();
 await expect(list).toContainText('Version 1');await expect(list).toContainText(O);
 await list.getByRole('button',{name:'Open Synthetic plan offer',exact:true}).click();
 await expect(page.getByRole('heading',{name:/Published offer.*version 1/})).toBeVisible();
 await list.getByRole('button',{name:'Create draft version for Synthetic plan',exact:true}).click();
 await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Synthetic plan');
 await expect(page.getByLabel('Plan code',{exact:true})).toHaveValue('synthetic');
 await expect(page.getByText('Not saved yet',{exact:false})).toBeVisible();
 expect(s.writes).toHaveLength(0);
 await page.getByLabel('Display name',{exact:true}).fill('Keep local edits');
 await list.getByRole('button',{name:'Create draft version for Synthetic plan',exact:true}).click();
 await expect(page.getByText('Discard unsaved local edits and continue?',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Keep editing',exact:true}).click();
 await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Keep local edits');
 expect(s.writes).toHaveLength(0);
});

test('published offers distinguishes empty and unavailable and refresh clears stale entries',async({page})=>{
 const {s}=await setup(page);const list=page.getByRole('region',{name:'Published offers',exact:true});
 await expect(list).toContainText('No currently visible published offers');
 s.catalog={catalog_revision:'2',offers:[{name:'Synthetic plan',offer_version_id:O,version:'1'}]};
 await list.getByRole('button',{name:'Refresh offers',exact:true}).click();
 await expect(list.getByRole('button',{name:'Open Synthetic plan offer',exact:true})).toBeVisible();
 s.catalogUnavailable=true;await list.getByRole('button',{name:'Refresh offers',exact:true}).click();
 await expect(list).toContainText('Published offers are unavailable');
 await expect(list.getByRole('button',{name:'Open Synthetic plan offer',exact:true})).toHaveCount(0);
 s.catalogUnavailable=false;s.catalog={catalog_revision:'3',offers:[]};await list.getByRole('button',{name:'Refresh offers',exact:true}).click();
 await expect(list).toContainText('No currently visible published offers');expect(s.writes).toHaveLength(0);
});
