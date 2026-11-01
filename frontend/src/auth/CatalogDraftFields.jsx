import { registryV2, registryV3 } from './catalogV2.js';
import CatalogPolicyFields from './CatalogPolicyFields.jsx';
import { labels, meterLabels, registry as legacyRegistry } from './catalogDraft.js';
export function Field({
  path,
  label,
  value,
  onChange,
  options,
  help,
  error,
  disabled = false,
  multiline = false,
  ...rest
}) {
  const id = `catalog-${path}`;
  return <label className="ca-field" htmlFor={id}><span id={`${id}-label`}>{label}</span>{options ? <select id={id} aria-labelledby={`${id}-label`} autoComplete="off" value={value ?? ''} disabled={disabled} onChange={e => onChange(e.target.value)} aria-invalid={error ? true : undefined} aria-describedby={help || error ? `${id}-help` : undefined} {...rest}>{options.map(o => <option key={Array.isArray(o) ? o[0] : o} value={Array.isArray(o) ? o[0] : o}>{Array.isArray(o) ? o[1] : o}</option>)}</select> : multiline ? <textarea id={id} aria-labelledby={`${id}-label`} autoComplete="off" value={value ?? ''} onChange={e => onChange(e.target.value)} disabled={disabled} rows={3} aria-describedby={help || error ? `${id}-help` : undefined} aria-invalid={error ? true : undefined} {...rest} /> : <input id={id} aria-labelledby={`${id}-label`} autoComplete="off" value={value ?? ''} disabled={disabled} onChange={e => onChange(e.target.value)} aria-invalid={error ? true : undefined} aria-describedby={help || error ? `${id}-help` : undefined} {...rest} />} {(help || error) && <small id={`${id}-help`} className={error ? 'ca-field-error' : ''}>{error || help}</small>}</label>;
}
const pending = [['', 'Not configured']];
const currency = [['', 'Choose currency'], ...Object.keys(legacyRegistry.currencies)];
export default function CatalogDraftFields({
  form,
  setForm,
  section,
  baseRevision,
  errors
}) {
  const registry = form.contract_version === 'catalog.v3' ? registryV3 : form.contract_version === 'catalog.v2' ? registryV2 : legacyRegistry;
  if (section === 'Usage & presentation') return <CatalogPolicyFields form={form} setForm={setForm} />;
  function update(path, value) {
    setForm(current => {
      const next = structuredClone(current);
      let cursor = next;
      const keys = path.split('.');
      for (const k of keys.slice(0, -1)) cursor = cursor[k];
      cursor[keys.at(-1)] = value;
      return next;
    });
  }
  const f = (path, label, options = {}) => {
    let value = form;
    for (const k of path.split('.')) value = value?.[k];
    return <Field key={path} path={path} label={label} value={value} onChange={v => update(path, v === '' ? null : v)} error={errors[path]} {...options} />;
  };
  const remove = (list, i) => update(`terms.${list}`, form.terms[list].filter((_, n) => n !== i));
  const add = (list, value) => update(`terms.${list}`, [...form.terms[list], value]);
  const policies = (path, fields) => <details className="ca-details"><summary>Policy references</summary><div className="ca-grid">{fields.map(([k, label]) => f(`${path}.${k}`, label))}</div><p>References record a decision; they do not approve a policy.</p></details>;
  if (section === 'Identity') return <section aria-labelledby="ca-identity"><h2 id="ca-identity">Plan identity</h2><p className="ca-muted">A stable code identifies the plan. Customer-facing wording can change in a draft.</p><div className="ca-grid">
    {f('plan.code', 'Plan code', {
        disabled: Boolean(baseRevision),
        help: baseRevision ? 'Plan identity is fixed after the first save.' : 'Lowercase, for example your own internal identifier. No offer is created automatically.'
      })}
    {f('terms.name', 'Display name', {
        maxLength: 2000
      })}
    <div className="ca-wide">{f('terms.description', 'Description', {
          multiline: true,
          maxLength: 2000
        })}</div>
    <div className="ca-wide">{f('internal_notes', 'Internal notes', {
          multiline: true,
          help: 'Visible only in this protected admin workspace. Excluded from the customer preview.'
        })}</div>
  </div>{policies('terms', [['subscription_policy_ref', 'Subscription policy'], ['migration_policy_ref', 'Subscriber migration policy']])}</section>;
  if (section === 'Prices') return <section aria-labelledby="ca-prices"><h2 id="ca-prices">Prices & billing</h2><p className="ca-muted">Billing frequency is separate from allowance resets. Blank amounts remain unresolved.</p>
    {!form.terms.prices.length && <p className="ca-empty">No prices configured. You can save the draft and decide these later.</p>}
    {form.terms.prices.map((p, i) => <fieldset className="ca-row" key={p.price_id}><legend>Price {i + 1}</legend><div className="ca-grid">
      <Field path={`terms.prices.${i}.currency`} label="Currency" value={p.currency} options={currency} error={errors[`terms.prices.${i}.currency`]} onChange={v => update(`terms.prices.${i}`, {
          ...p,
          currency: v,
          exponent: String(registry.currencies[v] ?? ''),
          _amount: '',
          amount_minor: null
        })} />
      {f(`terms.prices.${i}._amount`, 'Price amount', {
          inputMode: 'decimal',
          help: p.currency ? `${p.currency}: ${registry.currencies[p.currency]} decimal places. Changing currency clears the amount.` : 'Choose currency before recording an amount.',
          error: errors[`terms.prices.${i}.amount_minor`]
        })}
      <Field path={`terms.prices.${i}.billing`} label="Billing frequency" value={p.billing?.unit || ''} options={[...pending, ['month', 'Months'], ['year', 'Years']]} onChange={v => update(`terms.prices.${i}.billing`, v ? {
          unit: v,
          count: '1'
        } : null)} />
      {p.billing && f(`terms.prices.${i}.billing.count`, 'Bill every (count)', {
          inputMode: 'numeric'
        })}
    </div>{policies(`terms.prices.${i}`, [['tax_policy_ref', 'Tax policy'], ['rounding_policy_ref', 'Rounding policy']])}<button type="button" onClick={() => remove('prices', i)}>Remove price {i + 1}</button></fieldset>)}
    <button type="button" onClick={() => add('prices', {
      price_id: crypto.randomUUID(),
      currency: '',
      exponent: '',
      amount_minor: null,
      _amount: '',
      billing: null,
      tax_policy_ref: null,
      rounding_policy_ref: null,
      currency_version: 'catalog.currency.v1'
    })}>Add price</button></section>;
  if (section === 'Features & limits') return <section aria-labelledby="ca-features"><h2 id="ca-features">Features & allowances</h2><p className="ca-muted">Only registered app capabilities are available. Empty limits never mean unlimited.</p><div className="ca-features">
    {registry.features.map(feature => {
        const item = form.terms.entitlements.find(e => e.feature === feature);
        return <div className="ca-feature" key={feature}><Field path={`feature-${feature}`} label={labels[feature]} value={item ? item.allowed ? 'included' : 'excluded' : ''} options={[["", "Not set"], ["included", "Included"], ["excluded", "Excluded"]]} onChange={value => update('terms.entitlements', [...form.terms.entitlements.filter(e => e.feature !== feature), ...(value ? [{
            feature,
            allowed: value === 'included',
            model_keys: [],
            audio_sources: []
          }] : [])])} />
      {item?.allowed && feature === 'answers.generate' && form.contract_version === 'catalog.v1' && <Field path="eligible-models" label="Eligible model IDs" help="Optional, comma-separated registered IDs. Empty means no model restriction recorded, not unlimited access. The backend validates compatibility." value={item.model_keys.join(', ')} onChange={v => update('terms.entitlements', form.terms.entitlements.map(e => e.feature === feature ? {
            ...e,
            model_keys: v.split(',').map(x => x.trim()).filter(Boolean)
          } : e))} />}
      {item?.allowed && feature === 'assistant.auto' && <div className="ca-audio"><span>Audio sources</span>{['microphone', 'system', 'both'].map(source => <label key={source}><input type="checkbox" checked={item.audio_sources.includes(source)} onChange={event => update('terms.entitlements', form.terms.entitlements.map(e => e.feature === feature ? {
                ...e,
                audio_sources: event.target.checked ? [...e.audio_sources, source] : e.audio_sources.filter(x => x !== source)
              } : e))} />{source === 'both' ? 'Combined mic + system' : source === 'system' ? 'System audio' : 'Microphone'}</label>)}</div>}</div>;
      })}</div>
    <h3>Limits</h3>{form.terms.limits.map((l, i) => <fieldset key={l.meter} className="ca-row"><legend>{meterLabels[l.meter] || l.meter}</legend><p className="ca-muted">{l.kind === 'quota' ? 'Usage allowance' : l.kind === 'storage' ? 'Storage cap' : 'Concurrency limit'} · {l.unit === 'second' ? 'seconds' : l.unit}</p><div className="ca-grid">
      {l.meter === 'auto.authorized_running' ? <>{f(`terms.limits.${i}._minutes`, 'Auto minutes', {
            inputMode: 'numeric',
            error: errors[`terms.limits.${i}.amount`],
            help: 'Whole minutes. Includes silence; combined audio counts once.'
          })}{f(`terms.limits.${i}._seconds`, 'Additional seconds', {
            inputMode: 'numeric',
            help: 'Optional remainder, 0 through 59. No rounding.'
          })}</> : f(`terms.limits.${i}.amount`, 'Limit amount', {
          inputMode: 'numeric',
          help: `${l.unit} units; blank is not configured, zero is an explicit zero.`
        })}
      {f(`terms.limits.${i}.policy_ref`, 'Limit policy reference')}
      {l.kind === 'quota' && <Field path={`terms.limits.${i}.grant_kind`} label="Allowance type" value={l.grant_kind} options={[...pending, ['one_time', 'One-time allowance'], ['recurring', 'Recurring allowance']]} onChange={v => update(`terms.limits.${i}`, {
          ...l,
          grant_kind: v || null,
          reset: null
        })} />}
    </div>{l.grant_kind === 'recurring' && <div className="ca-reset"><h4>Allowance reset, independent of billing</h4><div className="ca-grid"><Field path={`terms.limits.${i}.reset`} label="Reset frequency" value={l.reset?.unit || ''} options={[...pending, ['month', 'Months'], ['year', 'Years']]} onChange={v => update(`terms.limits.${i}.reset`, v ? {
            unit: v,
            count: '1',
            anchor: '',
            timezone: '',
            policy_ref: ''
          } : null)} />{l.reset && <>{f(`terms.limits.${i}.reset.count`, 'Reset every (count)', {
              inputMode: 'numeric'
            })}{f(`terms.limits.${i}.reset.anchor`, 'Reset anchor', {
              options: [['', 'Choose anchor'], ['calendar', 'Calendar period'], ['subscription_anniversary', 'Subscription anniversary']]
            })}{f(`terms.limits.${i}.reset.timezone`, 'Reset timezone', {
              placeholder: 'IANA timezone, e.g. UTC'
            })}{f(`terms.limits.${i}.reset.policy_ref`, 'Reset policy reference')}</>}</div></div>}
      <button type="button" onClick={() => remove('limits', i)}>Remove {meterLabels[l.meter]}</button></fieldset>)}
    <Field path="add-limit" label="Add a registered limit" value="" options={[["", "Choose a limit"], ...Object.entries(registry.meters).filter(([meter, s]) => !(['catalog.v2','catalog.v3'].includes(form.contract_version) && s.kind === 'quota') && !form.terms.limits.some(l => l.meter === meter) && form.terms.entitlements.some(e => e.feature === s.feature && e.allowed)).map(([meter]) => [meter, meterLabels[meter]])]} onChange={meter => {
      if (meter) add('limits', {
        meter,
        ...registry.meters[meter],
        amount: null,
        grant_kind: null,
        reset: null,
        policy_ref: null,
        basis: meter === 'auto.authorized_running' ? registry.auto_basis : null,
        _minutes: '',
        _seconds: ''
      });
    }} />
  </section>;
  return <section aria-labelledby="ca-discounts"><h2 id="ca-discounts">Discount definitions</h2><p className="ca-muted">Draft rules only. Discounts do not change billing periods or allowances.</p>{!form.terms.discounts.length && <p className="ca-empty">No discounts configured.</p>}
    {form.terms.discounts.map((d, i) => <fieldset key={d.discount_id} className="ca-row"><legend>Discount {i + 1}</legend><div className="ca-grid">
      <Field path={`terms.discounts.${i}.kind`} label="Discount type" value={d.kind} error={errors[`terms.discounts.${i}.kind`]} options={[["", "Choose type"], ['percentage', 'Percentage'], ['fixed', 'Fixed amount']]} onChange={v => update(`terms.discounts.${i}`, {
          ...d,
          kind: v,
          _value: '',
          basis_points: null,
          amount_minor: null,
          currency: null,
          exponent: null
        })} />
      {d.kind === 'fixed' && <Field path={`terms.discounts.${i}.currency`} label="Discount currency" value={d.currency} options={currency} onChange={v => update(`terms.discounts.${i}`, {
          ...d,
          currency: v || null,
          exponent: v ? String(registry.currencies[v]) : null,
          _value: '',
          amount_minor: null
        })} />}
      {f(`terms.discounts.${i}._value`, d.kind === 'percentage' ? 'Percentage off' : 'Discount amount', {
          inputMode: 'decimal',
          error: errors[`terms.discounts.${i}.value`]
        })}
      {f(`terms.discounts.${i}.public_label`, 'Customer-facing discount label')}
      <Field path={`terms.discounts.${i}.scope`} label="Applies to" value={d.scope} options={[...pending, ['offer', 'This offer'], ['prices', 'Selected prices'], ['account_policy', 'Account eligibility policy']]} onChange={v => update(`terms.discounts.${i}`, {
          ...d,
          scope: v || null,
          price_ids: []
        })} />
      {f(`terms.discounts.${i}.duration`, 'Duration', {
          options: [...pending, ['once', 'Once'], ['repeating', 'Repeating billing cycles'], ['ongoing', 'Ongoing']],
          onChange: v => update(`terms.discounts.${i}`, {
            ...d,
            duration: v || null,
            cycles: null
          })
        })}
      {d.duration === 'repeating' && f(`terms.discounts.${i}.cycles`, 'Discount cycles', {
          inputMode: 'numeric'
        })}
      {f(`terms.discounts.${i}.total_redemptions`, 'Total redemption limit', {
          inputMode: 'numeric'
        })}{f(`terms.discounts.${i}.per_account_redemptions`, 'Per-account redemption limit', {
          inputMode: 'numeric'
        })}
      <Field path={`terms.discounts.${i}.stacking`} label="Discount stacking" value={d.stacking === false ? 'false' : ''} options={[["", "Not decided"], ['false', 'Do not stack']]} help="Stacking multiple discounts is not supported by this contract." onChange={v => update(`terms.discounts.${i}.stacking`, v ? false : null)} />
      {['valid_from', 'valid_until'].map(k => f(`terms.discounts.${i}.${k}`, k === 'valid_from' ? 'Valid from (UTC)' : 'Valid until (UTC)', {
          placeholder: 'YYYY-MM-DDTHH:mm:ssZ',
          help: 'An explicit UTC/offset timestamp. Leave empty if undecided.'
        }))}
    </div>{d.scope === 'prices' && <div className="ca-audio"><span>Eligible prices</span>{form.terms.prices.map((p, n) => <label key={p.price_id}><input type="checkbox" checked={d.price_ids.includes(p.price_id)} onChange={e => update(`terms.discounts.${i}.price_ids`, e.target.checked ? [...d.price_ids, p.price_id] : d.price_ids.filter(id => id !== p.price_id))} />Price {n + 1} {p.currency}</label>)}</div>}
      {policies(`terms.discounts.${i}`, [['eligibility_policy_ref', 'Eligibility policy'], ['redemption_policy_ref', 'Redemption policy'], ['application_policy_ref', 'Application policy']])}<button type="button" onClick={() => remove('discounts', i)}>Remove discount {i + 1}</button></fieldset>)}
    <button type="button" onClick={() => add('discounts', {
      discount_id: crypto.randomUUID(),
      revision: '1',
      kind: '',
      basis_points: null,
      amount_minor: null,
      currency: null,
      exponent: null,
      _value: '',
      scope: null,
      price_ids: [],
      eligibility_policy_ref: null,
      valid_from: null,
      valid_until: null,
      total_redemptions: null,
      per_account_redemptions: null,
      redemption_policy_ref: null,
      duration: null,
      cycles: null,
      stacking: null,
      application_policy_ref: null,
      public_label: null
    })}>Add discount</button>
  </section>;
}
