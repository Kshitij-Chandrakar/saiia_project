export async function startPlan(page, template = 'scratch', advanced = true) {
  const label = template === 'scratch' ? 'Start from scratch' : 'Start from ' + template;
  if (!await page.getByRole('button', { name: label, exact: true }).isVisible()) await page.getByRole('button', { name: 'New plan', exact: true }).click();
  await page.getByRole('button', { name: label, exact: true }).click();
  if (advanced && template === 'scratch' && !await page.getByLabel('Plan code', { exact: true }).isVisible()) await page.getByText('Advanced settings', { exact: true }).click();
}
export async function resumeDraft(page) {
  if (!await page.getByLabel('Open a draft by ID', { exact: true }).isVisible()) await page.getByRole('button', { name: 'Resume a draft', exact: true }).click();
}
export async function troubleshooting(page) {
  if (!await page.getByLabel('Check an operation by ID', { exact: true }).isVisible()) await page.getByText('Troubleshooting', { exact: true }).click();
}
export async function setup(page, {
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
        id: 'synthetic-user', email: 'synthetic-super-admin@example.invalid', user_metadata: { full_name: 'Synthetic Super admin' }
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
    if (p === '/api/commercial/admin/me') {
      const status = s.status, permissions = [...s.permissions];
      s.meStarted?.();
      if (s.meHold) await s.meHold;
      return r.fulfill({
      status,
      json: {
        permissions
      }
    });
    }
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
    if (s.hold) {
      s.heldRequests = (s.heldRequests || 0) + 1;
      await s.hold;
    }
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
export class Workspace {
  constructor(page) {
    this.page = page;
  }
  async create() {
    await startPlan(this.page);
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
      name: ({ Identity: 'Plan details', Prices: 'Pricing' })[name] || name,
      exact: true
    }).click();
  }
}
