import registry3 from './catalogRegistryV3.json' with { type: 'json' };
import plus from './approvedPlusTerms.json' with { type: 'json' };
import pro from './approvedProTerms.json' with { type: 'json' };
import registry from './catalogRegistryV2.json' with { type: 'json' };
import reference from './approvedFreeTerms.json' with { type: 'json' };
export { registry as registryV2, registry3 as registryV3 };
export const hasUnsafeDisplayCharacters = value => [...value].some(character => character.charCodeAt(0) < 32 || character === '<' || character === '>');
export function validateV2(document) {
  const v3 = document.contract_version === 'catalog.v3';
  if (!['catalog.v2','catalog.v3'].includes(document.contract_version) || document.registry_version !== (v3 ? registry3.version : registry.version) || document.terms.validation_policy_version !== (v3 ? 'catalog.validation.v3' : 'catalog.validation.v2')) throw Error('Unsupported catalog version');
  const t = document.terms,
    seen = new Set();
  if (t.resume_extraction_basis !== 'initial_upload_or_replacement_operation' || t.saved_answer_policy !== 'immutable_user_entries_retain_across_resets') throw Error('Unsupported operation policy');
  if (!['unconfigured', 'free', 'priced'].includes(t.pricing_mode) || t.pricing_mode === 'free' && (t.prices.length || t.discounts.length)) throw Error('Free pricing cannot contain paid prices or discounts');
  for (const a of t.allowances) {
    const spec = registry.meters[a.meter];
    if (!spec || spec.feature !== a.feature || spec.unit !== a.unit || seen.has(a.meter) || t.limits.some(l => l.meter === a.meter) || !t.entitlements.some(e => e.feature === a.feature && e.allowed)) throw Error('Allowance must match one included registered feature and meter');
    seen.add(a.meter);
    if (a.mode === 'unlimited') {
      if (a.amount !== null || a.period !== null) throw Error('Unlimited has no amount or reset');
    } else if (a.mode !== 'limited' || typeof a.amount !== 'string' || !/^(0|[1-9]\d{0,18})$/.test(a.amount) || BigInt(a.amount) > 9223372036854775807n || !['day', 'month'].includes(a.period?.unit) || a.period.timezone !== 'Asia/Kolkata' || a.period.anchor !== (a.period.unit === 'day' ? 'calendar' : 'account_signup_day')) throw Error('Limited allowance needs an exact amount and IST calendar period');
    if (a.meter === 'auto.authorized_running' !== (a.basis === registry.auto_basis)) throw Error('Invalid measurement basis');
  }
  if (t.model_selection !== 'configured_supported_available') throw Error('Unsupported model selector');
  if (t.entitlements.some(e => e.model_keys.length)) throw Error('Dynamic model selection cannot contain a hardcoded model list');
  if (!Array.isArray(t.unmetered_features) || new Set(t.unmetered_features).size !== t.unmetered_features.length || t.unmetered_features.some(f => !['sessions.history', 'transcripts.export'].includes(f) || !t.entitlements.some(e => e.feature === f && e.allowed))) throw Error('Invalid unlimited feature permissions');
  const display = new Set();
  for (const p of t.presentation) {
    if (!registry.features.includes(p.feature) || display.has(p.feature) || p.preview !== 'unavailable' || !t.entitlements.some(e => e.feature === p.feature)) throw Error('Unsupported or duplicate presentation');
    display.add(p.feature);
    for (const value of [p.label, p.information]) if (typeof value !== 'string' || !value.trim() || value.length > 2000 || hasUnsafeDisplayCharacters(value)) throw Error('Presentation must be bounded plain text');
  }
  if (v3) {
    const keys = new Set();
    for (const a of document.terms.storage_allowances) {
      if (a.meter !== 'resume.stored_files' || keys.has(a.meter) || t.limits.some(l => l.meter === a.meter) || !t.entitlements.some(e => e.feature === 'resume.upload' && e.allowed) || (a.mode === 'unlimited' ? a.amount !== null : a.mode !== 'limited' || typeof a.amount !== 'string' || !/^(0|[1-9]\d{0,18})$/.test(a.amount) || BigInt(a.amount) > 9223372036854775807n)) throw Error('Invalid storage capacity');
      keys.add(a.meter);
    }
    keys.clear();
    for (const b of t.service_benefits) {
      if (!['support.email','support.ai_human','access.early'].includes(b.key) || keys.has(b.key) || b.availability !== 'coming_soon' || typeof b.label !== 'string' || !b.label.trim() || b.label.length > 2000 || hasUnsafeDisplayCharacters(b.label)) throw Error('Invalid service benefit');
      keys.add(b.key);
    }
  }
  return document;
}
export function approvedFreeDraft() {
  return validateV2({
    draft_id: crypto.randomUUID(),
    plan: {
      plan_id: crypto.randomUUID(),
      code: 'free'
    },
    revision: '1',
    state: 'draft',
    contract_version: 'catalog.v2',
    registry_version: registry.version,
    internal_notes: '',
    terms: structuredClone(reference)
  });
}

export function approvedPaidDraft(code) {
  if (!['plus','pro'].includes(code)) throw Error('Unknown approved reference');
  const terms = structuredClone(code === 'plus' ? plus : pro);
  terms.prices.forEach(p => { p.price_id = crypto.randomUUID(); });
  return validateV2({draft_id:crypto.randomUUID(),plan:{plan_id:crypto.randomUUID(),code},revision:'1',state:'draft',contract_version:'catalog.v3',registry_version:registry3.version,internal_notes:'',terms});
}
