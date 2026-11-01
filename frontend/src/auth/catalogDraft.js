import { hasUnsafeDisplayCharacters, validateV2 } from './catalogV2.js';
// Authoring helpers, not entitlement or publication authority. See catalog.v1.
import registry from './catalogRegistry.json' with { type: 'json' };
export { registry };
export const MAX = 9223372036854775807n;
export const labels = {
  'answers.generate': 'Answer assistance',
  'audio.transcribe': 'Audio transcription',
  'assistant.auto': 'Auto Mode',
  'resume.upload': 'Resume storage',
  'resume.extract': 'Resume extraction',
  'resume.grounding': 'Resume grounding',
  'job_context.manage': 'Job context storage',
  'job_context.extract': 'Job context extraction',
  'screen.analyze': 'Screen analysis',
  'sessions.history': 'Session history',
  'transcripts.export': 'Transcript exports',
  'notes.generate': 'AI Notes',
  'session.ask_ai': 'Session Ask AI',
  'clipboard.saved_answers':'Clipboard', 'sketch.generate':'Introducing Sketch', 'screen.followups':'Screen follow-ups'
};
export const meterLabels = {
  'answers.completed': 'Completed answers',
  'answers.concurrent': 'Concurrent answers',
  'audio.transcribed': 'Transcription seconds',
  'audio.concurrent': 'Concurrent audio streams',
  'auto.authorized_running': 'Auto allowance',
  'auto.concurrent_runs': 'Concurrent Auto runs',
  'resume.stored_files': 'Stored resume files',
  'resume.stored_bytes': 'Resume storage bytes',
  'resume.extractions': 'Resume extractions',
  'job_context.stored': 'Stored job contexts',
  'job_context.extractions': 'Job context extractions',
  'screen.analyses': 'Screen analyses',
  'screen.concurrent': 'Concurrent screen operations',
  'notes.generations': 'Notes generations',
  'ask_ai.completed': 'Ask AI answers'
};
export class FieldError extends Error {
  constructor(path, message) {
    super(message);
    this.path = path;
  }
}
export function integer(value, path, positive = false) {
  if (typeof value !== 'string' || !/^(0|[1-9]\d{0,18})$/.test(String(value))) throw new FieldError(path, 'Enter a whole number without commas or exponent notation.');
  const n = BigInt(value);
  if (n > MAX || positive && n === 0n) throw new FieldError(path, positive ? 'Enter a positive whole number within the supported range.' : 'This number is too large.');
  return n.toString();
}
export function decimalToMinor(value, exponent, path = 'amount') {
  if (value === '' || value === null) return null;
  if (!Number.isInteger(exponent) || !/^\d+(\.\d*)?$/.test(value)) throw new FieldError(path, 'Choose a currency and enter an exact non-negative amount.');
  const [whole, fraction = ''] = value.split('.');
  if (fraction.length > exponent) throw new FieldError(path, `Use at most ${exponent} decimal places. Amounts are never rounded.`);
  return integer((BigInt(whole) * 10n ** BigInt(exponent) + BigInt(fraction.padEnd(exponent, '0') || '0')).toString(), path);
}
export function minorToDecimal(value, exponent) {
  if (value === null || value === undefined || value === '') return '';
  const digits = integer(value, 'amount').padStart(exponent + 1, '0');
  return exponent ? `${digits.slice(0, -exponent)}.${digits.slice(-exponent)}` : digits;
}
export function autoSeconds(minutes, seconds, path = 'auto') {
  if ((minutes == null || minutes === '') && (seconds == null || seconds === '')) return null;
  const m = BigInt(integer(minutes || '0', path)),
    s = BigInt(integer(seconds || '0', path));
  if (s > 59n) throw new FieldError(path, 'Additional seconds must be between 0 and 59.');
  return integer((m * 60n + s).toString(), path);
}
export const newDraft = () => ({
  draft_id: crypto.randomUUID(),
  plan: {
    plan_id: crypto.randomUUID(),
    code: ''
  },
  revision: '1',
  state: 'draft',
  contract_version: 'catalog.v1',
  registry_version: registry.version,
  internal_notes: '',
  terms: {
    name: null,
    description: null,
    subscription_policy_ref: null,
    migration_policy_ref: null,
    prices: [],
    entitlements: [],
    limits: [],
    discounts: []
  }
});
export function toForm(document) {
  const result = structuredClone(document);
  result.terms.prices = result.terms.prices.map(p => ({
    ...p,
    _amount: minorToDecimal(p.amount_minor, Number(p.exponent))
  }));
  result.terms.limits = result.terms.limits.map(l => ({
    ...l,
    _minutes: l.amount == null ? '' : (BigInt(l.amount) / 60n).toString(),
    _seconds: l.amount == null ? '' : (BigInt(l.amount) % 60n).toString()
  }));
  result.terms.discounts = result.terms.discounts.map(d => ({
    ...d,
    _value: minorToDecimal(d.kind === 'percentage' ? d.basis_points : d.amount_minor, d.kind === 'percentage' ? 2 : Number(d.exponent || 0))
  }));
  return result;
}
const key = (value, path, required = false) => {
  if (!value && !required) return null;
  if (!/^[a-z][a-z0-9._:-]{0,119}$/.test(value || '')) throw new FieldError(path, 'Use a lowercase identifier starting with a letter (letters, numbers, dot, colon, underscore or hyphen).');
  return value;
};
const text = (value, path, required = false) => {
  if (!value && !required) return null;
  if (!value?.trim() || value.length > 2000 || hasUnsafeDisplayCharacters(value)) throw new FieldError(path, 'Enter plain text, up to 2,000 characters, without angle brackets or control characters.');
  return value;
};
export function serialize(form, baseRevision, reason) {
  const d = structuredClone(form);
  d.plan.code = key(d.plan.code, 'plan.code', true);
  text(reason, 'reason', true);
  d.revision = integer((BigInt(baseRevision || '0') + 1n).toString(), 'revision', true);
  for (const k of ['name', 'description']) d.terms[k] = text(d.terms[k], `terms.${k}`);
  for (const k of ['subscription_policy_ref', 'migration_policy_ref']) d.terms[k] = key(d.terms[k], `terms.${k}`);
  d.terms.prices = d.terms.prices.map((p, i) => {
    const {
        _amount,
        ...r
      } = p,
      path = `terms.prices.${i}`;
    if (!(p.currency in registry.currencies)) throw new FieldError(`${path}.currency`, 'Choose a currency or remove this price.');
    r.exponent = String(registry.currencies[p.currency]);
    r.amount_minor = decimalToMinor(_amount, Number(r.exponent), `${path}.amount_minor`);
    if (r.billing) r.billing.count = integer(r.billing.count, `${path}.billing.count`, true);
    for (const k of ['tax_policy_ref', 'rounding_policy_ref']) r[k] = key(r[k], `${path}.${k}`);
    return r;
  });
  d.terms.limits = d.terms.limits.map((l, i) => {
    const {
        _minutes,
        _seconds,
        ...r
      } = l,
      path = `terms.limits.${i}`;
    const spec = registry.meters[r.meter];
    if (!spec || !d.terms.entitlements.some(e => e.feature === spec.feature && e.allowed)) throw new FieldError(`${path}.amount`, 'Include the matching feature or remove this limit.');
    Object.assign(r, spec);
    r.amount = l.meter === 'auto.authorized_running' ? autoSeconds(_minutes, _seconds, `${path}.amount`) : r.amount == null || r.amount === '' ? null : integer(r.amount, `${path}.amount`);
    r.policy_ref = key(r.policy_ref, `${path}.policy_ref`);
    if (r.reset) {
      r.reset.count = integer(r.reset.count, `${path}.reset.count`, true);
      key(r.reset.policy_ref, `${path}.reset.policy_ref`, true);
      if (!r.reset.anchor || !r.reset.timezone) throw new FieldError(`${path}.reset.timezone`, 'Choose a reset anchor and timezone, or leave the reset cadence unconfigured.');
      try {
        new Intl.DateTimeFormat('en', {
          timeZone: r.reset.timezone
        });
      } catch {
        throw new FieldError(`${path}.reset.timezone`, 'Enter a valid IANA timezone.');
      }
    }
    return r;
  });
  d.terms.discounts = d.terms.discounts.map((discount, i) => {
    const {
        _value,
        ...r
      } = discount,
      path = `terms.discounts.${i}`;
    if (!['percentage', 'fixed'].includes(r.kind)) throw new FieldError(`${path}.kind`, 'Choose a discount type or remove this discount.');
    if (r.kind === 'percentage') {
      r.basis_points = decimalToMinor(_value, 2, `${path}.value`);
      if (r.basis_points !== null && (BigInt(r.basis_points) < 1n || BigInt(r.basis_points) > 10000n)) throw new FieldError(`${path}.value`, 'Use a percentage greater than zero and no more than 100.');
      r.amount_minor = null;
      r.currency = null;
      r.exponent = null;
    } else {
      r.basis_points = null;
      r.exponent = r.currency ? String(registry.currencies[r.currency]) : null;
      r.amount_minor = decimalToMinor(_value, r.exponent === null ? null : Number(r.exponent), `${path}.value`);
      if (r.amount_minor === '0') throw new FieldError(`${path}.value`, 'A fixed discount must be greater than zero.');
    }
    for (const k of ['total_redemptions', 'per_account_redemptions', 'cycles']) r[k] = r[k] == null || r[k] === '' ? null : integer(r[k], `${path}.${k}`, true);
    for (const k of ['eligibility_policy_ref', 'redemption_policy_ref', 'application_policy_ref']) r[k] = key(r[k], `${path}.${k}`);
    r.public_label = text(r.public_label, `${path}.public_label`);
    for (const k of ['valid_from', 'valid_until']) if (r[k] && (!/^\d{4}-\d{2}-\d{2}T.*(Z|[+-]\d{2}:\d{2})$/.test(r[k]) || !Number.isFinite(Date.parse(r[k])))) throw new FieldError(`${path}.${k}`, 'Enter a timestamp with timezone.');
    if (r.valid_from && r.valid_until && Date.parse(r.valid_from) >= Date.parse(r.valid_until)) throw new FieldError(`${path}.valid_until`, 'End time must be after start time.');
    if (r.total_redemptions && r.per_account_redemptions && BigInt(r.per_account_redemptions) > BigInt(r.total_redemptions)) throw new FieldError(`${path}.per_account_redemptions`, 'Per-account redemptions cannot exceed total redemptions.');
    return r;
  });
  if (['catalog.v2','catalog.v3'].includes(d.contract_version)) { try { validateV2(d); } catch (error) { throw new FieldError('terms.allowances', error.message); } }
  return d;
}
export const sectionFor = path => path.includes('allowances') || path.includes('presentation') || path.includes('unmetered_features') || path.includes('pricing_mode') || path.includes('model_selection') ? 'Usage & presentation' : path.includes('prices') ? 'Prices' : path.includes('limits') || path.includes('entitlements') ? 'Features & limits' : path.includes('discounts') ? 'Discounts' : 'Identity';
export const issueLabel = issue => `${issue.path.join(' / ')}: ${issue.code === 'limit_unresolved' ? 'Add an allowance for this included feature.' : issue.code === 'policy_unresolved' ? 'A value or policy is still required.' : 'Review this field.'}`;
