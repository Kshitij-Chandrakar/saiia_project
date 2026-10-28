import { registryV2, registryV3, validateV2 } from './catalogV2.js';
import { registry, integer, toForm } from './catalogDraft.js';
export class CatalogError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}
const known = new Set(['catalog_not_found', 'catalog_permission_denied', 'catalog_revision_conflict', 'catalog_request_identity_conflict', 'catalog_invalid_data', 'catalog_stored_version_invalid', 'catalog_database_unavailable', 'catalog_write_uncertain', 'catalog_review_stale', 'catalog_not_publishable', 'commercial_path_unreviewed']);
export async function catalogRequest(base, token, path, {
  method = 'GET',
  body,
  key,
  revision,
  signal,
  fetchImpl = fetch
} = {}) {
  const control = new AbortController(),
    cancel = () => control.abort();
  signal?.addEventListener('abort', cancel, {
    once: true
  });
  if (signal?.aborted) cancel();
  const timer = setTimeout(cancel, 30000);
  const write = ['POST', 'PATCH'].includes(method) && !path.endsWith('/preview');
  try {
    const response = await fetchImpl(base.replace(/\/$/, '') + path, {
      method,
      cache: 'no-store',
      credentials: 'omit',
      redirect: 'error',
      signal: control.signal,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body ? {
          'Content-Type': 'application/json'
        } : {}),
        ...(key ? {
          'Idempotency-Key': key
        } : {}),
        ...(revision ? {
          'If-Match': `"${revision}"`
        } : {})
      },
      ...(body ? {
        body: JSON.stringify(body)
      } : {})
    });
    if (response.status === 401) throw new CatalogError('unauthenticated');
    if (response.status === 403) throw new CatalogError('catalog_permission_denied');
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new CatalogError(known.has(data?.detail?.code) ? data.detail.code : write ? 'catalog_write_uncertain' : 'catalog_database_unavailable');
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error();
    return data;
  } catch (error) {
    if (error instanceof CatalogError) throw error;
    throw new CatalogError(write ? 'catalog_write_uncertain' : 'catalog_database_unavailable');
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}
export function checkedDraft(data) {
  const selected = data?.contract_version === 'catalog.v3' ? registryV3 : data?.contract_version === 'catalog.v2' ? registryV2 : registry;
  if (!['catalog.v1','catalog.v2','catalog.v3'].includes(data?.contract_version) || data.registry_version !== selected.version || data.state !== 'draft' || typeof data.revision !== 'string' || !/^[1-9]\d{0,18}$/.test(data.revision) || !data.plan || !data.terms || !['prices', 'limits', 'entitlements', 'discounts'].every(k => Array.isArray(data.terms[k]))) throw new CatalogError('catalog_stored_version_invalid');
  try {
    const id = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
    if (!id.test(data.draft_id) || !id.test(data.plan.plan_id) || typeof data.plan.code !== 'string' || !data.plan.code || typeof data.internal_notes !== 'string') throw new Error();
    for (const k of ['name', 'description']) if (data.terms[k] !== null && typeof data.terms[k] !== 'string') throw new Error();
    for (const p of data.terms.prices) {
      if (!(p.currency in registry.currencies) || p.exponent !== String(registry.currencies[p.currency])) throw new Error();
      if (p.amount_minor !== null) integer(p.amount_minor, 'amount');
    }
    for (const l of data.terms.limits) {
      if (!registry.meters[l.meter]) throw new Error();
      if (l.amount !== null) integer(l.amount, 'amount');
    }
    for (const e of data.terms.entitlements) if (!selected.features.includes(e.feature) || typeof e.allowed !== 'boolean' || !Array.isArray(e.model_keys) || !Array.isArray(e.audio_sources)) throw new Error();
    if (['catalog.v2','catalog.v3'].includes(data.contract_version)) validateV2(data);
    toForm(data);
  } catch {
    throw new CatalogError('catalog_stored_version_invalid');
  }
  return structuredClone(Object.fromEntries(['draft_id', 'plan', 'revision', 'state', 'contract_version', 'registry_version', 'terms', 'internal_notes'].map(k => [k, data[k]])));
}
