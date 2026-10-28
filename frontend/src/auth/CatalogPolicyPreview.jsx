import CatalogFeaturePresentation from './CatalogFeaturePresentation.jsx';
import { labels } from './catalogDraft.js';
// Customer-safe renderer; accepts validated terms, never internal notes or URLs.
// Can be placed inside the existing landing pricing card at C11.4 activation.
export default function CatalogPolicyPreview({
  terms
}) {
  return <section aria-label="Plan allowances and features">
    <p>{terms.pricing_mode === 'free' ? 'Free; no charge or paid billing interval.' : terms.pricing_mode === 'unconfigured' ? 'Pricing not configured.' : 'Prices shown separately.'}</p>
    <p>Models: all configured, supported and available models.</p>
    <ul>{terms.allowances.map(a => <li key={a.meter}>{a.meter === 'resume.replacements' ? 'Successful resume replacements' : a.meter === 'clipboard.new_saves' ? 'New Clipboard saves' : labels[a.feature] || a.feature}: {a.mode === 'unlimited' ? 'Unlimited' : `${a.amount} ${a.unit}(s) per ${a.period.unit}, midnight Asia/Kolkata${a.period.unit === 'month' ? ', original signup day (clamped and restored)' : ''}`}</li>)}
    {terms.unmetered_features.map(f => <li key={f}>{labels[f] || f}: Unlimited</li>)}</ul>
    <p>Resume storage: {terms.limits.find(l => l.meter === 'resume.stored_files')?.amount ?? (terms.storage_allowances?.[0]?.mode === 'unlimited' ? 'Unlimited' : terms.storage_allowances?.[0]?.amount ?? 'Not configured')}. Initial upload is separate from successful replacement allowance.</p>
    <p>Manual audio capture and transcription: {terms.allowances.find(a => a.meter === 'audio.transcribed')?.mode === 'unlimited' ? 'Unlimited subscription usage' : 'See the configured audio allowance'}, subject to operational safeguards. Screen-analysis follow-ups: {terms.entitlements.some(e => e.feature === 'screen.followups' && e.allowed) ? 'Included' : 'Not included'}.</p>
    <p>Auto usage is cumulative across any number of starts and includes silence; stopped time is excluded, combined microphone/system audio counts once. Saved-answer reads do not consume new saves; resets retain older answers. Users cannot individually edit or delete saved answers.</p>
    {terms.service_benefits?.map(b => <p key={b.key}>{b.label}: Coming soon</p>)}
    {terms.presentation.map(p => <CatalogFeaturePresentation key={p.feature} label={p.label} information={p.information} included={terms.entitlements.some(e => e.feature === p.feature && e.allowed)} />)}
  </section>;
}
