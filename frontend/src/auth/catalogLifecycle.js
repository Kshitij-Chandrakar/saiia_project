import { CatalogError, checkedDraft } from './catalogApi.js';
import { integer } from './catalogDraft.js';
// datetime-local has no timezone; interpret it as IST, independently of the
// browser timezone. The existing API and immutable review still use UTC instants.
export function istToUtc(value) {
  if (typeof value !== 'string' || !/^[1-9]\d{3}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value)) return null;
  const time = Date.parse(value + '+05:30');
  if (!Number.isFinite(time) || new Date(time + 19800000).toISOString().slice(0, value.length) !== value) return null;
  return new Date(time).toISOString();
}
export function formatIst(value) {
  const time = value ? Date.parse(value) : NaN;
  if (!Number.isFinite(time)) return 'Unavailable';
  return new Intl.DateTimeFormat('en-IN', {timeZone:'Asia/Kolkata',year:'numeric',month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:true}).format(time) + ' IST';
}
export const isId = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
export const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])])) : value;
const bad = () => {
  throw new CatalogError('catalog_stored_version_invalid');
};
const positive = value => {
  try {
    return integer(value, 'revision', true);
  } catch {
    bad();
  }
};
const digest = value => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
export function checkedBasis(value, source) {
  if (!value || value.protocol !== 'catalog.review.v1' || !['catalog.v1','catalog.v2','catalog.v3'].includes(value.contract_version) || value.registry_version !== ('catalog.features.v' + value.contract_version.split('v').at(-1)) || value.validation_policy_version !== ('catalog.validation.v' + value.contract_version.split('v').at(-1)) || !isId(value.draft_id) || !isId(value.plan_id) || !digest(value.source_hash) || !digest(value.terms_fingerprint) || !['publish', 'replace'].includes(value.intent?.action) || !Number.isFinite(Date.parse(value.authority?.valid_until))) bad();
  positive(value.revision);
  for (const ref of [value.current_offer, value.archived_offer]) if (ref) {
    if (!isId(ref.offer_version_id) || !digest(ref.fingerprint)) bad();
    positive(ref.visibility_revision);
  }
  if (source && (source.draft_id !== value.draft_id || source.plan.plan_id !== value.plan_id || source.revision !== value.revision || source.contract_version !== value.contract_version || source.registry_version !== value.registry_version)) bad();
  return structuredClone(value);
}
export function checkedReview(value) {
  if (!value?.receipt || value.receipt.storage_version !== 'catalog.review.store.v1' || !isId(value.receipt.review_id) || !['current', 'draft_changed', 'draft_terminal', 'expired', 'authority_changed', 'authority_unavailable', 'head_changed'].includes(value.state) || value.publication_enabled !== false || value.consumption_state !== 'not_checked') bad();
  checkedBasis(value.receipt.basis);
  return structuredClone(value);
}
export function checkedResult(value, operation) {
  const r = value?.receipt;
  if (!r || r.protocol !== 'catalog.lifecycle.result.v1' || !isId(r.request_id) || !isId(r.offer_version_id) || !['offer.publish', 'offer.replace', 'offer.retire'].includes(r.operation) || value.current?.offer_version_id !== r.offer_version_id || !['visible', 'hidden', 'retired'].includes(value.current.state) || value.publication_enabled !== false) bad();
  for (const n of [r.visibility_revision, r.catalog_revision, value.current.revision, value.current_catalog_revision]) positive(n);
  if (operation && (r.request_id !== operation.key || r.operation !== operation.kind || operation.body.review_id && r.review_id !== operation.body.review_id || operation.offerId && r.offer_version_id !== operation.offerId)) bad();
  return structuredClone(value);
}
export function checkedOffer(value) {
  const s = value?.snapshot;
  if (!s || !isId(s.offer_version_id) || !['catalog.v1','catalog.v2','catalog.v3'].includes(s.contract_version) || s.registry_version !== ('catalog.features.v' + s.contract_version.split('v').at(-1)) || value.current?.offer_version_id !== s.offer_version_id || !['hidden', 'visible', 'retired'].includes(value.current.state) || value.publication_enabled !== false || value.purchasable !== false) bad();
  positive(s.version);
  positive(value.current.revision);
  positive(value.catalog_revision);
  // Reuse draft shape/registry validation for immutable terms, without relaxing
  // the editable-draft API validator or treating this as backend authority.
  checkedDraft({
    draft_id: value.source?.draft_id || s.offer_version_id,
    plan: s.plan,
    revision: '1',
    state: 'draft',
    contract_version: s.contract_version,
    registry_version: s.registry_version,
    terms: s.terms,
    internal_notes: ''
  });
  if (value.source) {
    if (value.source.state !== 'published' || !same(value.source.terms, s.terms) || !same(value.source.plan, s.plan)) bad();
    checkedDraft({
      ...value.source,
      state: 'draft'
    });
  }
  return structuredClone(value);
}
export function successor(source) {
  const d = checkedDraft({
    ...source,
    state: 'draft'
  });
  const prices = new Map(d.terms.prices.map(p => [p.price_id, crypto.randomUUID()]));
  d.draft_id = crypto.randomUUID();
  d.revision = '1';
  d.internal_notes = '';
  d.terms.prices = d.terms.prices.map(p => ({
    ...p,
    price_id: prices.get(p.price_id)
  }));
  d.terms.discounts = d.terms.discounts.map(x => ({
    ...x,
    discount_id: crypto.randomUUID(),
    revision: '1',
    price_ids: x.price_ids.map(id => prices.get(id))
  }));
  return d;
}
