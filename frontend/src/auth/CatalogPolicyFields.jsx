import { registryV2 } from './catalogV2.js';
import { Field } from './CatalogDraftFields.jsx';
import { labels } from './catalogDraft.js';
export default function CatalogPolicyFields({
  form,
  setForm
}) {
  function edit(work) {
    setForm(current => {
      const next = structuredClone(current);
      work(next.terms);
      return next;
    });
  }
  return <section aria-label="Usage and presentation"><h2>Usage & presentation</h2><p>Plan allowances do not disable operational limits. No runtime enforcement is activated here.</p>
    <Field path="pricing-mode" label="Pricing mode" value={form.terms.pricing_mode} options={['unconfigured', 'free', 'priced']} onChange={value => edit(t => {
      t.pricing_mode = value;
    })} />
    <p>Models: all configured, supported and operationally available models. Model readiness remains server-controlled.</p>
    {['sessions.history', 'transcripts.export'].map(feature => <Field key={feature} path={`unmetered-${feature}`} label={`Usage ${labels[feature]}`} value={form.terms.unmetered_features.includes(feature) ? 'unlimited' : 'unconfigured'} options={['unconfigured', 'unlimited']} onChange={value => edit(t => {
      t.unmetered_features = t.unmetered_features.filter(f => f !== feature);
      if (value === 'unlimited') t.unmetered_features.push(feature);
    })} />)}
    {form.terms.allowances.map((a, i) => <fieldset className="ca-row" key={a.meter}><legend>{labels[a.feature] || a.feature} · {a.meter}</legend>
      <Field path={`allowance-${i}-mode`} label={`Allowance ${a.meter}`} value={a.mode} options={['unlimited', 'limited']} onChange={mode => edit(t => {
        t.allowances[i] = {
          ...a,
          mode,
          amount: mode === 'unlimited' ? null : '',
          period: mode === 'unlimited' ? null : {
            unit: 'month',
            anchor: 'account_signup_day',
            timezone: 'Asia/Kolkata'
          }
        };
      })} />
      {a.mode === 'limited' && <><Field path={`allowance-${i}-amount`} label={`Amount ${a.meter} (${a.unit})`} value={a.amount} inputMode="numeric" onChange={v => edit(t => {
          t.allowances[i].amount = v;
        })} />
      <Field path={`allowance-${i}-period`} label={`Reset ${a.meter}`} value={a.period.unit} options={['day', 'month']} onChange={unit => edit(t => {
          t.allowances[i].period = {
            unit,
            anchor: unit === 'day' ? 'calendar' : 'account_signup_day',
            timezone: 'Asia/Kolkata'
          };
        })} /><p>Midnight IST; monthly periods retain the original signup-day anchor. No rollover.</p></>}
    <button type="button" onClick={() => edit(t => {
        t.allowances.splice(i, 1);
      })}>Remove allowance {a.meter}</button></fieldset>)}
    <Field path="add-usage" label="Add a usage allowance" value="" options={[["", "Choose an included feature meter"], ...Object.entries(registryV2.meters).filter(([meter, s]) => s.kind === 'quota' && !form.terms.allowances.some(a => a.meter === meter) && !form.terms.limits.some(l => l.meter === meter) && form.terms.entitlements.some(e => e.feature === s.feature && e.allowed)).map(([meter]) => [meter, meter])]} onChange={meter => {
      if (meter) edit(t => {
        const spec = registryV2.meters[meter];
        t.allowances.push({
          meter,
          feature: spec.feature,
          unit: spec.unit,
          mode: 'limited',
          amount: '',
          period: {
            unit: meter === 'auto.authorized_running' ? 'day' : 'month',
            anchor: meter === 'auto.authorized_running' ? 'calendar' : 'account_signup_day',
            timezone: 'Asia/Kolkata'
          },
          basis: meter === 'auto.authorized_running' ? registryV2.auto_basis : null
        });
      });
    }} />
    {form.terms.storage_allowances?.map((a, i) => <fieldset className="ca-row" key={a.meter}><legend>Stored resumes</legend>
      <Field path="storage-mode" label="Resume storage capacity" value={a.mode} options={['limited','unlimited']} onChange={mode => edit(t => { t.storage_allowances[i] = {...a,mode,amount:mode === 'unlimited' ? null : ''}; })} />
      {a.mode === 'limited' && <Field path="storage-amount" label="Maximum stored resumes" value={a.amount} onChange={amount => edit(t => {t.storage_allowances[i].amount=amount;})} />}
      <button type="button" onClick={() => edit(t => {t.storage_allowances.splice(i,1);})}>Remove stored resume capacity</button>
    </fieldset>)}
    {form.terms.storage_allowances && !form.terms.storage_allowances.length && !form.terms.limits.some(l => l.meter === 'resume.stored_files') && <button type="button" onClick={() => edit(t => {t.storage_allowances.push({meter:'resume.stored_files',mode:'limited',amount:''});})}>Add stored resume capacity</button>}
    {form.terms.service_benefits?.map((b,i) => <fieldset className="ca-row" key={b.key}><legend>{b.key}</legend><Field path={`benefit-${i}`} label={`Service label ${b.key}`} value={b.label} onChange={label => edit(t => {t.service_benefits[i].label=label;})} /><p>Coming soon. A label cannot activate a support service or release access.</p><button type="button" onClick={() => edit(t => {t.service_benefits.splice(i,1);})}>Remove {b.key}</button></fieldset>)}
    {form.terms.service_benefits && <Field path="add-benefit" label="Add a service benefit" value="" options={[["","Choose a service benefit"], ...[['support.email','Standard email support'],['support.ai_human','AI support with human escalation'],['access.early','Early access to new features when released']].filter(([key]) => !form.terms.service_benefits.some(b => b.key===key))]} onChange={key => {if(key) edit(t => {const label={'support.email':'Standard email support','support.ai_human':'AI support with human escalation','access.early':'Early access to new features when released'}[key];t.service_benefits.push({key,label,availability:'coming_soon'});});}} />}
    {form.terms.presentation.map((p, i) => <fieldset className="ca-row" key={p.feature}><legend>{p.feature}</legend>
      <Field path={`presentation-${i}-label`} label={`Label ${p.feature}`} value={p.label} maxLength={2000} onChange={v => edit(t => {
        t.presentation[i].label = v;
      })} />
      <Field path={`presentation-${i}-info`} label={`Information ${p.feature}`} value={p.information} multiline maxLength={2000} onChange={v => edit(t => {
        t.presentation[i].information = v;
      })} />
      <p>Inclusion is controlled under Features & limits. Preview destination is unavailable.</p>
    </fieldset>)}
  </section>;
}
