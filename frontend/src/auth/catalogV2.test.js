import test from 'node:test';
import assert from 'node:assert/strict';
import { approvedFreeDraft, validateV2, hasUnsafeDisplayCharacters } from './catalogV2.js';
import { serialize, toForm } from './catalogDraft.js';
import { checkedDraft } from './catalogApi.js';

test('plain display text rejects every ASCII control and angle bracket without rejecting Unicode', () => {
  for (let code = 0; code < 32; code++) assert.equal(hasUnsafeDisplayCharacters(`safe${String.fromCharCode(code)}text`), true);
  for (const text of ['<label', 'label>']) assert.equal(hasUnsafeDisplayCharacters(text), true);
  assert.equal(hasUnsafeDisplayCharacters('Clipboard · ₹399 — readable text'), false);
});
test('approved import roundtrip retains versioned policy and safe presentation without currency', () => {
  const draft = approvedFreeDraft(),
    other = approvedFreeDraft();
  assert.notEqual(draft.draft_id, other.draft_id);
  assert.equal(draft.plan.code, other.plan.code);
  const saved = checkedDraft(serialize(toForm(draft), null, 'Synthetic import'));
  assert.deepEqual(saved, draft);
  assert.equal(saved.terms.pricing_mode, 'free');
  assert.deepEqual(saved.terms.prices, []);
  assert.deepEqual(saved.terms.allowances.find(a => a.meter === 'auto.authorized_running').period, {
    unit: 'day',
    anchor: 'calendar',
    timezone: 'Asia/Kolkata'
  });
  assert.equal(saved.terms.allowances.find(a => a.meter === 'clipboard.new_saves').amount, '5');
  assert.equal(saved.terms.entitlements.find(e => e.feature === 'sketch.generate').allowed, false);
  assert.equal(saved.terms.entitlements.find(e => e.feature === 'clipboard.saved_answers').allowed, true);
});
test('unlimited cannot mean zero, missing or denied; incompatible input fails before save', () => {
  const draft = approvedFreeDraft();
  draft.terms.allowances[4].amount = '0';
  assert.equal(validateV2(draft).terms.allowances[4].mode, 'limited');
  for (const change of [d => {
    d.terms.allowances[0].amount = '0';
  }, d => {
    d.terms.allowances[4].amount = null;
  }, d => {
    d.terms.allowances[4].period.anchor = 'account_signup_day';
  }, d => {
    d.terms.entitlements.find(e => e.feature === 'audio.transcribe').allowed = false;
  }, d => {
    d.terms.presentation[0].information = '<script>bad</script>';
  }, d => {
    d.contract_version = 'catalog.v99';
  }]) {
    const d = approvedFreeDraft();
    change(d);
    assert.throws(() => validateV2(d));
  }
});

test('approved Plus and Pro imports retain price identities, storage modes and monthly saves',async()=>{
  const {approvedPaidDraft}=await import('./catalogV2.js');
  for(const code of ['plus','pro']) {
    const d=approvedPaidDraft(code),saved=checkedDraft(serialize(toForm(d),null,'Synthetic paid import'));
    assert.equal(saved.contract_version,'catalog.v3');assert.deepEqual(saved,d);
    assert.deepEqual(saved.terms.prices.map(p=>p.amount_minor),code==='plus'?['39900','299900']:['89900','649900']);
    assert.equal(saved.terms.allowances.find(a=>a.meter==='clipboard.new_saves').amount,code==='plus'?'10':null);
    assert.equal(saved.terms.service_benefits[0].availability,'coming_soon');
    const bad=structuredClone(saved);bad.terms.storage_allowances[0]={meter:'resume.stored_files',mode:'unlimited',amount:'0'};
    assert.throws(()=>validateV2(bad));
  }
});
