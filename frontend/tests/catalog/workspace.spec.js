import { test, expect } from '@playwright/test';
async function setup(page, {
  permissions = ['subscriptions.manage'],
  status = 200,
  signed = true
} = {}) {
  const s = {
    permissions,
    status,
    draft: null,
    writes: 0,
    keys: [],
    uncertain: false,
    conflict: false,
    unavailable: false,
    hold: null
  };
  await page.addInitScript(signed => {
    window.__session = signed ? {
      access_token: 'synthetic',
      user: {
        id: 'synthetic-user'
      }
    } : null;
    window.__listeners = [];
  }, signed);
  await page.route('**/src/auth/supabaseClient.js*', r => r.fulfill({
    contentType: 'application/javascript',
    body: `window.__emit=(event,session)=>{window.__session=session;window.__listeners.forEach(fn=>fn(event,session))};export const supabase={auth:{getSession:async()=>({data:{session:window.__session}}),onAuthStateChange:fn=>{window.__listeners.push(fn);return {data:{subscription:{unsubscribe(){}}}}},signOut:async()=>{window.__emit('SIGNED_OUT',null);return {error:null}}}};export function getSupabaseAuthConfig(){return {}};`
  }));
  await page.route('**/api/**', async r => {
    const q = r.request(),
      p = new URL(q.url()).pathname;
    if (p === '/api/commercial/admin/me') return r.fulfill({
      status: s.status,
      json: {
        permissions: s.permissions
      }
    });
    if (!p.startsWith('/api/admin/catalog/')) return r.fulfill({
      status: 404,
      json: {}
    });
    if (p.endsWith('/preview')) {
      s.previewRequests=(s.previewRequests || 0)+1;
      if(s.previewHold)await s.previewHold;
      if(s.previewError)return r.fulfill({status:503,json:{detail:{code:'catalog_database_unavailable'}}});
      return r.fulfill({
      json: {
        draft_id: s.draft.draft_id,
        revision: s.draft.revision,
        validation_scope: 'structural_only',
        publication_enabled: false,
        errors: [],
        pending: [{
          path: ['terms', 'subscription_policy_ref'],
          code: 'policy_unresolved'
        }]
      }
    });
    }
    if (q.method() === 'GET') return r.fulfill({
      json: s.draft
    });
    if (s.hold) await s.hold;
    if (s.unavailable) return r.fulfill({
      status: 503,
      json: {
        detail: {
          code: 'catalog_database_unavailable'
        }
      }
    });
    const b = q.postDataJSON(),
      k = q.headers()['idempotency-key'];
    s.keys.push(k);
    if (s.conflict) return r.fulfill({
      status: 409,
      json: {
        detail: {
          code: 'catalog_revision_conflict'
        }
      }
    });
    if (!s.keys.slice(0, -1).includes(k)) {
      s.writes++;
      s.draft = b.document;
    }
    if (s.uncertain) {
      s.uncertain = false;
      return r.abort('failed');
    }
    return r.fulfill({
      json: s.draft
    });
  });
  await page.goto('/auth/admin/subscriptions');
  return s;
}
class Workspace {
  constructor(page) {
    this.page = page;
  }
  async create() {
    await this.page.getByRole('button', {
      name: 'Create a blank draft',
      exact: true
    }).click();
    await this.page.getByLabel('Plan code', {
      exact: true
    }).fill('synthetic-plan');
    await this.page.getByLabel('Display name', {
      exact: true
    }).fill('Synthetic draft');
  }
  async save() {
    await this.page.getByLabel('Change reason', {
      exact: true
    }).fill('Synthetic test');
    await this.page.getByRole('button', {
      name: /^Save (draft|changes)$/
    }).click();
  }
  async tab(name) {
    await this.page.getByRole('button', {
      name,
      exact: true
    }).click();
  }
}
for (const [name, options, heading] of [['signed out', {
  signed: false
}, 'Page not found'], ['ordinary', {
  permissions: []
}, 'Page not found'], ['unavailable', {
  status: 503
}, 'Admin access is unavailable'], ['invalid token', {
  status: 401
}, 'Page not found']]) test(name, async ({
  page
}) => {
  await setup(page, options);
  await expect(page.getByRole('heading', {
    name: heading,
    exact: true
  })).toBeVisible();
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveCount(0);
  if (heading === 'Page not found') {
    await expect(page).toHaveTitle('Page not found | Intervucopilot');
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeFocused();
    await expect(page.getByRole('link', { name: 'Return home', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Subscription drafts', exact: true })).toHaveCount(0);
    await expect(page.getByRole('region', { name: 'Offer lifecycle', exact: true })).toHaveCount(0);
  }
});
test('create save edit preview open and responsive', async ({
  page
}, info) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  await ui.save();
  await expect(page.getByRole('status')).toContainText('Revision 1');
  await page.getByRole('button', {
    name: 'Preview saved draft',
    exact: true
  }).click();
  await expect(page.getByRole('region', {
    name: 'Draft preview'
  })).toContainText('Synthetic draft');
  await page.getByRole('button',{name:'Close subscription review',exact:true}).click();
  expect(s.writes).toBe(1);
  await page.getByLabel('Display name', {
    exact: true
  }).fill('Revised draft');
  await ui.save();
  await expect(page.getByRole('status')).toContainText('Revision 2');
  await ui.tab('Prices');
  await page.getByRole('button', {
    name: 'Add price',
    exact: true
  }).click();
  await page.getByLabel('Currency', {
    exact: true
  }).selectOption('INR');
  await page.getByLabel('Price amount', {
    exact: true
  }).fill('123.45');
  await ui.save();
  await expect(page.getByRole('status')).toContainText('Revision 3');
  expect(s.draft.terms.prices[0].amount_minor).toBe('12345');
  await page.screenshot({
    path: info.outputPath('desktop.png'),
    fullPage: true
  });
  await page.setViewportSize({
    width: 390,
    height: 844
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: info.outputPath('narrow.png'),
    fullPage: true
  });
  await page.getByLabel('Open a draft by ID', {
    exact: true
  }).fill(s.draft.draft_id);
  await page.getByRole('button', {
    name: 'Open draft',
    exact: true
  }).click();
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveValue('Revised draft');
});
test('invalid currency precision does not write', async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  await ui.tab('Prices');
  await page.getByRole('button', {
    name: 'Add price',
    exact: true
  }).click();
  await page.getByLabel('Currency', {
    exact: true
  }).selectOption('JPY');
  await page.getByLabel('Price amount', {
    exact: true
  }).fill('1.2');
  await ui.save();
  await expect(page.getByRole('alert')).toContainText('never rounded');
  expect(s.writes).toBe(0);
});
test('uncertain replay identity and CAS conflict preserve local edits', async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  s.uncertain = true;
  await ui.save();
  await expect(page.getByRole('alert')).toContainText('not confirmed');
  await page.getByRole('button', {
    name: 'Retry same save',
    exact: true
  }).click();
  await expect(page.getByRole('status')).toContainText('Revision 1');
  expect(s.writes).toBe(1);
  expect(s.keys[0]).toBe(s.keys[1]);
  s.conflict = true;
  await page.getByLabel('Display name', {
    exact: true
  }).fill('Local changes');
  await ui.save();
  await expect(page.getByRole('alert')).toContainText('changed on the server');
  await page.getByRole('button', {
    name: 'Review latest revision',
    exact: true
  }).click();
  await expect(page.getByRole('region', {
    name: 'Revision review'
  })).toContainText('Synthetic draft');
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveValue('Local changes');
});
test('revocation account switch and logout clear private data', async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  await ui.save();
  s.permissions = [];
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('heading', {
    name: 'Page not found',
    exact: true
  })).toBeVisible();
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveCount(0);
  s.permissions = ['subscriptions.manage'];
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await ui.create();
  await page.evaluate(() => window.__emit('SIGNED_IN', {
    access_token: 'other',
    user: {
      id: 'other-user'
    }
  }));
  await expect(page.getByRole('button', {
    name: 'Create a blank draft',
    exact: true
  })).toBeVisible();
  await page.evaluate(() => window.__emit('SIGNED_OUT', null));
  await expect(page.getByRole('heading', {
    name: 'Page not found',
    exact: true
  })).toBeVisible();
});
test('Auto allowance exact seconds and discount editing', async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  await ui.tab('Features & limits');
  await page.getByLabel('Auto Mode', {
    exact: true
  }).selectOption('included');
  await page.getByLabel('Combined mic + system', {
    exact: true
  }).check();
  await page.getByLabel('Add a registered limit', {
    exact: true
  }).selectOption('auto.authorized_running');
  await page.getByLabel('Auto minutes', {
    exact: true
  }).fill('30');
  await page.getByLabel('Additional seconds', {
    exact: true
  }).fill('1');
  await ui.save();
  await expect(page.getByRole('status')).toContainText('Revision 1');
  expect(s.draft.terms.limits[0].amount).toBe('1801');
  expect(s.draft.terms.entitlements[0].audio_sources).toEqual(['both']);
  await page.getByLabel('Auto minutes', {
    exact: true
  }).fill('');
  await page.getByLabel('Additional seconds', {
    exact: true
  }).fill('');
  await ui.save();
  await expect(page.getByRole('status')).toContainText('Revision 2');
  expect(s.draft.terms.limits[0].amount).toBeNull();
  await ui.tab('Discounts');
  await page.getByRole('button', {
    name: 'Add discount',
    exact: true
  }).click();
  await expect(page.getByRole('heading', {
    name: 'Discount definitions',
    exact: true
  })).toBeVisible();
  await page.getByLabel('Discount type', {
    exact: true
  }).selectOption('percentage');
  await page.getByLabel('Percentage off', {
    exact: true
  }).fill('12.50');
  await ui.save();
  await expect(page.getByRole('status')).toContainText('Revision 3');
  expect(s.draft.terms.discounts[0].basis_points).toBe('1250');
});
test('double submission and stale account response are isolated', async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  let release;
  s.hold = new Promise(r => release = r);
  await page.getByLabel('Change reason', {
    exact: true
  }).fill('Synthetic');
  await page.getByRole('button', {
    name: 'Save draft',
    exact: true
  }).dblclick();
  await expect(page.getByRole('button', {
    name: 'Checking save...',
    exact: true
  })).toBeDisabled();
  await page.evaluate(() => window.__emit('SIGNED_IN', {
    access_token: 'other',
    user: {
      id: 'other-user'
    }
  }));
  await expect(page.getByRole('button', {
    name: 'Create a blank draft',
    exact: true
  })).toBeVisible();
  release();
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveCount(0);
  expect(s.keys.length).toBeLessThanOrEqual(1);
});
test('empty state illustration, keyboard entry and storage privacy', async ({
  page
}, info) => {
  await setup(page);
  await expect(page.getByRole('heading', {
    name: 'A workspace for unfinished plans',
    exact: true
  })).toBeVisible();
  await page.screenshot({
    path: info.outputPath('empty-desktop.png'),
    fullPage: true
  });
  await page.getByRole('button', {
    name: 'Create a blank draft',
    exact: true
  }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Plan code', {
    exact: true
  })).toBeVisible();
  expect(await page.evaluate(() => Object.keys(localStorage).filter(k => /catalog|draft/i.test(k)))).toEqual([]);
  expect(await page.evaluate(() => Object.keys(sessionStorage).filter(k => /catalog|draft/i.test(k)))).toEqual([]);
});
test('database unavailable preserves edits and never claims saved', async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  s.unavailable = true;
  await ui.save();
  await expect(page.getByRole('alert')).toContainText('storage is unavailable');
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveValue('Synthetic draft');
  await expect(page.getByRole('status')).toHaveCount(0);
  expect(s.writes).toBe(0);
  await expect(page.getByRole('button', {
    name: 'Retry same save',
    exact: true
  })).toBeEnabled();
});
test('SPA Stay preserves edits and revision; Discard navigates with zero additional writes', async ({
  page
}, testInfo) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await page.setViewportSize({
    width: 390,
    height: 844
  });
  await ui.create();
  await ui.save();
  await expect(page.getByRole('status')).toContainText('Revision 1');
  await page.getByLabel('Display name', {
    exact: true
  }).fill('Unsaved revision one');
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  const dialog = page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  });
  await expect(dialog).toBeVisible();
  expect(await dialog.evaluate(el => {
    const r = el.getBoundingClientRect();
    return r.left >= 0 && r.right <= innerWidth && r.bottom <= innerHeight;
  })).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath('navigation-mobile.png')
  });
  await expect(dialog.getByRole('button', {
    name: 'Stay',
    exact: true
  })).toBeFocused();
  await dialog.getByRole('button', {
    name: 'Stay',
    exact: true
  }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page).toHaveURL(/\/auth\/admin\/subscriptions$/);
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveValue('Unsaved revision one');
  expect(s.writes).toBe(1);
  await ui.save();
  await expect(page.getByRole('status')).toContainText('Revision 2');
  expect(s.draft.revision).toBe('2');
  await page.getByLabel('Display name', {
    exact: true
  }).fill('Discard this');
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  await dialog.getByRole('button', {
    name: 'Discard and leave',
    exact: true
  }).click();
  await expect(page).toHaveURL(/\/auth\/resume$/);
  expect(s.writes).toBe(2);
});
for (const state of ['empty', 'blank', 'saved', 'reverted']) test(`clean ${state} navigation does not warn`, async ({
  page
}) => {
  await setup(page);
  const ui = new Workspace(page);
  if (state === 'blank') await page.getByRole('button', {
    name: 'Create a blank draft',
    exact: true
  }).click();
  if (['saved', 'reverted'].includes(state)) {
    await ui.create();
    await ui.save();
    await expect(page.getByRole('status')).toContainText('Revision 1');
  }
  if (state === 'reverted') {
    await page.getByLabel('Display name', {
      exact: true
    }).fill('Temporary');
    await page.getByLabel('Display name', {
      exact: true
    }).fill('Synthetic draft');
  }
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  await expect(page).toHaveURL(/\/auth\/resume$/);
  await expect(page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  })).toHaveCount(0);
});
for (const state of ['failed', 'uncertain']) test(`${state} save remains guarded; Stay retains retry identity`, async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  if (state === 'failed') s.unavailable = true;else s.uncertain = true;
  await ui.save();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  const d = page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  });
  await expect(d).toBeVisible();
  await expect(d).toContainText('not confirmed');
  await d.getByRole('button', {
    name: 'Stay',
    exact: true
  }).click();
  s.unavailable = false;
  await page.getByRole('button', {
    name: 'Retry same save',
    exact: true
  }).click();
  await expect(page.getByRole('status')).toContainText('Revision 1');
  expect(s.writes).toBe(1);
  if (state === 'uncertain') expect(s.keys[0]).toBe(s.keys[1]);
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  await expect(page).toHaveURL(/\/auth\/resume$/);
});
test('native beforeunload warning can be dismissed; saved reload does not warn', async ({
  page
}) => {
  await setup(page);
  const ui = new Workspace(page);
  await ui.create();
  const warning = page.waitForEvent('dialog');
  const reload = page.evaluate(() => location.reload()).catch(() => {});
  const d = await warning;
  expect(d.type()).toBe('beforeunload');
  await d.dismiss();
  await reload;
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveValue('Synthetic draft');
  await ui.save();
  await expect(page.getByRole('status')).toContainText('Revision 1');
  let warnings = 0;
  page.on('dialog', async dialog => {
    warnings++;
    await dialog.dismiss();
  });
  await page.reload();
  await expect(page.getByRole('button', {
    name: 'Create a blank draft',
    exact: true
  })).toBeVisible();
  expect(warnings).toBe(0);
});
for (const action of ['logout', 'switch', 'revocation']) test(`${action} clears private state even with blocked navigation`, async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  await expect(page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  })).toBeVisible();
  // An auth event can arrive while the native modal makes the rest of the page inert.
  if (action === 'logout') await page.evaluate(() => document.querySelector('button[aria-label="Logout"]').click());
  if (action === 'switch') await page.evaluate(() => window.__emit('SIGNED_IN', {
    access_token: 'other',
    user: {
      id: 'other-user'
    }
  }));
  if (action === 'revocation') {
    s.permissions = [];
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  }
  await expect(page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  })).toHaveCount(0);
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveCount(0);
  if (action === 'logout') await expect(page).toHaveURL(/\/auth\/login$/);
  if (action === 'switch') await expect(page.getByRole('button', {
    name: 'Create a blank draft',
    exact: true
  })).toBeVisible();
  if (action === 'revocation') await expect(page.getByRole('heading', {
    name: 'Page not found',
    exact: true
  })).toBeVisible();
  expect(s.writes).toBe(0);
});
test('Discard after uncertain save leaves without another mutation', async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  s.uncertain = true;
  await ui.save();
  await expect(page.getByRole('alert')).toContainText('not confirmed');
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  await page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  }).getByRole('button', {
    name: 'Discard and leave',
    exact: true
  }).click();
  await expect(page).toHaveURL(/\/auth\/resume$/);
  expect(s.writes).toBe(1);
  expect(s.keys).toHaveLength(1);
});
test('history forward is guarded and Escape stays', async ({
  page
}) => {
  await setup(page);
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  await expect(page).toHaveURL(/\/auth\/resume$/);
  await page.goBack();
  const ui = new Workspace(page);
  await ui.create();
  const navigation = page.goForward().catch(() => {});
  const d = page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  });
  await expect(d).toBeVisible();
  await page.keyboard.press('Escape');
  await navigation;
  await expect(d).not.toBeVisible();
  await expect(page).toHaveURL(/\/auth\/admin\/subscriptions$/);
  await expect(page.getByLabel('Display name', {
    exact: true
  })).toHaveValue('Synthetic draft');
});
test('confirmed save while navigation is blocked clears the obsolete warning without navigating', async ({
  page
}) => {
  const s = await setup(page),
    ui = new Workspace(page);
  await ui.create();
  let release;
  s.hold = new Promise(resolve => release = resolve);
  await ui.save();
  await expect(page.getByRole('button', {
    name: 'Checking save...',
    exact: true
  })).toBeDisabled();
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  const d = page.getByRole('dialog', {
    name: 'Leave this draft?',
    exact: true
  });
  await expect(d).toBeVisible();
  release();
  await expect(d).not.toBeVisible();
  await expect(page.getByRole('status')).toContainText('Revision 1');
  await expect(page).toHaveURL(/\/auth\/admin\/subscriptions$/);
  expect(s.writes).toBe(1);
  await page.getByRole('link', {
    name: 'Resumes',
    exact: true
  }).click();
  await expect(page).toHaveURL(/\/auth\/resume$/);
});


test('close imported plans discards local state and restores import focus without writes',async({page},info)=>{
 const state=await setup(page);const imports=page.getByRole('region',{name:'Approved plan imports'});
 for(const name of ['Free','Plus','Pro']) {
  await imports.getByRole('button',{name:`Import approved ${name} draft`,exact:true}).click();
  await expect(page.getByLabel('Display name',{exact:true})).toHaveValue(name);
  for(const plan of ['Free','Plus','Pro'])await expect(imports.getByRole('button',{name:`Import approved ${plan} draft`,exact:true})).toBeDisabled();
  await page.getByLabel('Display name',{exact:true}).fill('Unsaved local change');
  if(name==='Free'){await page.getByRole('button',{name:'Save draft',exact:true}).click();await expect(page.getByRole('alert')).toBeVisible();}
  const close=page.getByRole('button',{name:'Close draft',exact:true});
  await close.focus();await expect(page.getByRole('tooltip')).toContainText('discard unsaved changes');
  await page.screenshot({path:info.outputPath(`close-${name}-desktop.png`)});
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Display name',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Draft preview'})).toHaveCount(0);
  await expect(imports).toBeFocused();
  await expect(page.getByRole('alert')).toHaveCount(0);
  for(const plan of ['Free','Plus','Pro'])await expect(imports.getByRole('button',{name:`Import approved ${plan} draft`,exact:true})).toBeEnabled();
  expect(state.writes).toBe(0);
 }
 await page.setViewportSize({width:390,height:844});await imports.getByRole('button',{name:'Import approved Plus draft',exact:true}).click();
 await page.getByRole('button',{name:'Prices',exact:true}).click();await expect(page.getByLabel('Price amount',{exact:true}).first()).toHaveValue('399.00');
 const close=page.getByRole('button',{name:'Close draft',exact:true});await close.scrollIntoViewIfNeeded();
 const bounds=await close.boundingBox();expect(bounds.x+bounds.width).toBeLessThanOrEqual(390);
 await page.screenshot({path:info.outputPath('close-mobile.png')});await close.click();expect(state.writes).toBe(0);
});

test('close keeps saved data and clears preview, local discard prompt and unsaved edits',async({page})=>{
 const state=await setup(page),workspace=new Workspace(page);await workspace.create();await workspace.save();
 const saved=structuredClone(state.draft);await page.getByRole('button',{name:'Preview saved draft',exact:true}).click();
 await expect(page.getByRole('region',{name:'Draft preview'})).toContainText('Synthetic draft');
 await page.getByRole('button',{name:'Close subscription review',exact:true}).click();
 await page.getByLabel('Display name',{exact:true}).fill('Discard me');
 await page.getByRole('button',{name:'New draft',exact:true}).click();await expect(page.getByText('Discard unsaved local edits and continue?',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Close draft',exact:true}).click();
 await expect(page.getByText('Discard unsaved local edits and continue?',{exact:true})).toHaveCount(0);
 expect(state.writes).toBe(1);expect(state.draft).toEqual(saved);
 await page.getByLabel('Open a draft by ID',{exact:true}).fill(saved.draft_id);await page.getByRole('button',{name:'Open draft',exact:true}).click();
 await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Synthetic draft');
 await page.getByRole('button',{name:'Close draft',exact:true}).click();expect(state.writes).toBe(1);
});

test('close is locked during active and uncertain saves and preserves retry identity',async({page})=>{
 const state=await setup(page),workspace=new Workspace(page);await workspace.create();
 let release;state.hold=new Promise(resolve=>release=resolve);state.uncertain=true;
 await workspace.save();const close=page.getByRole('button',{name:'Close draft',exact:true});await expect(close).toBeDisabled();
 release();state.hold=null;await expect(page.getByRole('button',{name:'Retry same save',exact:true})).toBeVisible();
 await expect(close).toBeDisabled();await close.hover();await expect(page.getByRole('tooltip')).toContainText('Resolve the unconfirmed operation');
 await page.getByRole('button',{name:'Retry same save',exact:true}).click();await expect(close).toBeEnabled();
 expect(state.keys).toHaveLength(2);expect(state.keys[0]).toBe(state.keys[1]);expect(state.writes).toBe(1);
 await close.click();await page.getByRole('button',{name:'Import approved Pro draft',exact:true}).click();await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Pro');
});

test('late read is serialized before close and cannot overwrite a different imported session',async({page})=>{
 const state=await setup(page),workspace=new Workspace(page);await workspace.create();await workspace.save();
 let release,entered;const barrier=new Promise(resolve=>release=resolve),started=new Promise(resolve=>entered=resolve);
 await page.route('**/api/admin/catalog/drafts/*',async route=>{if(route.request().method()==='GET'){entered();await barrier;await route.fulfill({json:state.draft});}else await route.fallback();});
 await page.getByRole('button',{name:'Open draft',exact:true}).click();await started;
 await expect(page.getByRole('button',{name:'Close draft',exact:true})).toBeDisabled();release();
 await expect(page.getByRole('button',{name:'Close draft',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'Close draft',exact:true}).click();
 await page.getByRole('button',{name:'Import approved Pro draft',exact:true}).click();
 await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Pro');expect(state.writes).toBe(1);
});


test('subscription preview is centered, keyboard trapped, scroll bounded and restores editor focus',async({page},info)=>{
 const state=await setup(page),ui=new Workspace(page);await ui.create();await ui.save();
 const trigger=page.getByRole('button',{name:'Preview saved draft',exact:true});
 for(const viewport of [{width:1366,height:768},{width:390,height:844}]){
  await page.setViewportSize(viewport);await trigger.click();
  const modal=page.getByRole('dialog',{name:'Subscription review',exact:true});
  await expect(modal).toContainText('Synthetic draft');
  await expect(page.getByRole('complementary',{name:'Draft preview'})).toHaveCount(0);
  await expect(modal.getByRole('button',{name:'Close subscription review',exact:true})).toBeFocused();
  expect(await page.evaluate(()=>document.body.style.overflow)).toBe('hidden');
  const bounds=await modal.boundingBox();expect(Math.abs(bounds.x+bounds.width/2-viewport.width/2)).toBeLessThan(2);
  expect(bounds.y).toBeGreaterThanOrEqual(0);expect(bounds.y+bounds.height).toBeLessThanOrEqual(viewport.height);
  const header=modal.locator('header'),top=(await header.boundingBox()).y;
  await modal.locator('.ca-subscription-modal-body').evaluate(e=>{e.scrollTop=e.scrollHeight;});
  expect((await header.boundingBox()).y).toBe(top);
  for(let i=0;i<12;i++){await page.keyboard.press('Tab');expect(await modal.evaluate(e=>e.contains(document.activeElement))).toBe(true);}
  await page.screenshot({path:info.outputPath(viewport.width===1366?'subscription-review-desktop.png':'subscription-review-mobile.png')});
  await page.keyboard.press('Escape');await expect(modal).not.toBeVisible();await expect(trigger).toBeFocused();
  expect(await page.evaluate(()=>document.body.style.overflow)).not.toBe('hidden');
 }
 expect(state.writes).toBe(1);await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Synthetic draft');
 await page.getByLabel('Display name',{exact:true}).fill('Preserved unsaved edit');
 await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Preserved unsaved edit');expect(state.writes).toBe(1);
});

test('closing loading preview does not reopen it; unavailable states stay inside modal and retry is read only',async({page})=>{
 const state=await setup(page),ui=new Workspace(page);await ui.create();await ui.save();
 let release;state.previewHold=new Promise(resolve=>release=resolve);
 const trigger=page.getByRole('button',{name:'Preview saved draft',exact:true});await trigger.click();
 const modal=page.getByRole('dialog',{name:'Subscription review',exact:true});
 await expect(modal.getByRole('status')).toContainText('Loading saved draft preview');
 await modal.getByRole('button',{name:'Close subscription review',exact:true}).click();
 release();state.previewHold=null;await expect(trigger).toBeEnabled();await expect(modal).not.toBeVisible();
 await expect(trigger).toBeFocused();state.previewError=true;await trigger.click();
 await expect(modal.getByRole('alert')).toContainText('unavailable');
 await page.keyboard.press('Escape');state.previewError=false;await trigger.click();
 await expect(modal).toContainText('Synthetic draft');expect(state.writes).toBe(1);
 await page.keyboard.press('Escape');await page.getByRole('button',{name:'Close draft',exact:true}).click();
 await page.getByRole('button',{name:'Import approved Plus draft',exact:true}).click();
 await expect(modal).not.toBeVisible();await expect(page.getByLabel('Display name',{exact:true})).toHaveValue('Plus');
});


for(const name of ['Free','Plus','Pro'])test(`duplicate ${name} import explains plan code conflict without implying an unsaved draft changed`,async({page})=>{
 const state=await setup(page);await page.getByRole('button',{name:`Import approved ${name} draft`,exact:true}).click();
 state.conflict=true;await page.getByLabel('Change reason',{exact:true}).fill('Synthetic duplicate candidate');
 await page.getByRole('button',{name:'Save draft',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText(`The ${name.toLowerCase()} plan code already exists or this candidate is stale`);
 await expect(page.getByRole('alert')).toContainText('Create a new draft version');
 await expect(page.getByRole('alert')).not.toContainText('This draft changed on the server');
 await expect(page.getByLabel('Display name',{exact:true})).toHaveValue(name);
 expect(state.writes).toBe(0);
});
