# Approved Free terms — 2026-10-23

Status: approved terms integrated and locally verified through the authenticated admin draft workflow (see completion evidence below). No shared/real offer created or published; only disposable synthetic imports/snapshot tests. Existing immutable catalog.v1 snapshots remain unchanged. This document is a review reference, not a second runtime catalog or executable seed.

| Capability | Approved terms | Original mapping/gap (superseded below) |
|---|---|---|
| Manual audio/transcription/answers | Explicit unlimited subscription usage | audio.transcribe, answers.generate; v1 Limit.amount=null means incomplete, not unlimited. Requires versioned explicit allowance mode, separate from operational input/concurrency limits. |
| Auto Mode | 600 cumulative seconds/account/day; unlimited starts until exhausted; silence included, stopped time excluded, combined audio once | assistant.auto / auto.authorized_running; existing basis authorized_running_including_silence_both_once. Daily reset at midnight Asia/Kolkata. v1 reset lacks day cadence. |
| Models | All configured supported models, subject to operational readiness | Existing entitlements.model_keys is explicit selection; dynamic supported-catalog selector needs versioned representation and server resolution, never a static model list. |
| Resume | One stored resume; initial upload separate from one successful replacement/month | resume.upload / resume.stored_files=1; new successful-replacement meter required. Do not charge initial upload against replacements or count failed attempts as successful replacement. |
| Screen | Five analyses/month, follow-ups excluded | screen.analyze; review New/Continue/Passage action-to-operation mapping before charging. Ambiguous action accounting remains pending. |
| Clipboard | Five NEW user-written saved answers/month; reads free; no edit/individual delete; retain old answers across reset | Existing session-scoped My Answers create/list, not OS clipboard reads or AI generations. New-save meter/registered capability needed; account-wide allowance must span sessions. |
| History/exports/notes/Ask AI | No subscription usage quota | sessions.history, transcripts.export, notes.generate, session.ask_ai; explicit unlimited, preserving retention/privacy and operational safeguards. |
| Sketch | Excluded | No Sketch catalog key exists in v1. Diagram capability must be traced before registering; exclusion presentation must not grant access. |

## Period policy

Monthly allowances use original account signup day converted to Asia/Kolkata, at midnight each month. Clamp to final calendar day when absent, retaining original anchor: Jan31 → Feb28/29 → Mar31 → Apr30. No fixed 30-day arithmetic or rollover. Daily and monthly periods are independent. New pure allowance_periods helper computes half-open UTC boundaries only; it does not meter or authorize. Trusted signup timestamp provenance, durable account identity, reservations/settlement and device-independent counters remain C13 work.

## Approved presentation copy

Sketch label: **Introducing Sketch**, struck through; excluded.

“Sketch turns a completed system-design answer into a colorful architecture diagram with clear shapes, arrows and labels. Generate it with one click below the answer, then revisit it in your session history.”

Clipboard: included, never struck through.

“Clipboard lets you paste and save your own answers, then open them during an interview. The Free plan includes 5 new saves each month. Once saved, an answer cannot be edited or deleted.”

Matching eye/preview and information controls still require implementation/verification. Existing Sketch-specific eye behavior was not established in the inspected admin workspace; do not invent a promotional destination, video or access grant. Tooltip metadata must be editable/versioned through the catalog, support hover/focus/tap, accessible names/focus, and isolated event handling. These are requirements, not verified UI behavior.

## Historical gap audit before integration

- backend/app/commercial/catalog_contract.py:193 restricts reset to month/year and calendar/subscription anniversary; :228 has no explicit unlimited; :263 has no customer presentation metadata. Extending these in place would change canonical v1 fingerprints; do not do so silently.
- frontend/src/auth/catalogRegistry.json contains neither saved-personal-answer nor Sketch feature keys. Existing admin uses this registry; do not hardcode Free in the workspace or bypass review.
- backend/app/cloud/interview_session_my_answers.py:95 lists session-owned answers; :115 creates through existing RPC. backend/app/api/interview_sessions.py:565 and :581 expose create/list. This verifies code paths, not deployed behavior or the new commercial quota. Account-wide privacy deletion remains separate.
- frontend/src/components/AnswerPanel.jsx contains My Answers paste/save/view. Its copyToClipboard function writes OS clipboard and is not the billable save operation.

Next required integration: versioned backward-compatible contract/registry, explicit unlimited/zero/unconfigured modes, daily/signup-anniversary resets, replacement/new-save meters and configurable feature presentation. Extend validators, snapshots/public projections, integrity readers, website forms and review-policy bindings together while preserving legacy v1 bytes. Then provide an unsaved, validated admin import reference (no shared seed), matching accessible icons/tooltips and browser/native compatibility tests. Production policy resolver remains unavailable; no review/publication bypass. No Plus/Pro decisions made.

Verification completed in this increment: period helper tests only. Unlimited/catalog/import/icon/enforcement acceptance remains unfinished and must not be reported passed.

## Historical isolated presentation increment (superseded below)

Added reusable website CatalogFeaturePresentation component and CSS, using existing lucide Eye/Info icons. Inclusion and information are props, not access authority or hardcoded plan allocations. Excluded labels are struck through; included labels are not. Information supports hover/focus/tap, Escape and visible focus, with click propagation stopped. Eye is disabled because a supported Sketch/Clipboard preview destination/assets were not established. No promotional media invented.

One isolated Playwright component scenario passed at desktop and 390px, checking exclusion/inclusion, disabled eye, hover/focus/tap/Escape, no adjacent action and horizontal containment. This uses synthetic presentation props, not admin/import or public-catalog acceptance. The component is not yet wired into persisted admin metadata/customer preview.

Remaining: versioned domain/registry/storage/review support and compatibility; authenticated validated draft import; persistent admin metadata editing and preview composition. Existing catalog.v1 reset/limit/model structures cannot faithfully carry the approved terms. No fallback using null as unlimited, fake high quotas, internal notes or fabricated currency was introduced. No public activation or shared database write occurred.


## Completed integration and authoritative mapping (2026-10-23)

This supersedes the historical gap/partial records above. Commercial decisions are represented in catalog.v2 / catalog.features.v2 / catalog.validation.v2, leaving v1 classes, defaults, registry normalization and immutable stored rows intact. The approved reference is `frontend/src/auth/approvedFreeTerms.json`; it has no plan/draft IDs, currency, paid interval, trial, discount or Plus/Pro allocations. It initializes an unsaved candidate only after explicit admin action; persisted, admin-edited terms remain authoritative catalog data. It is not a runtime entitlement/pricing array.

| Approved requirement | Persisted representation |
|---|---|
| Unlimited manual audio capture/transcription/answers | audio.transcribe/answers.generate allowed; audio.transcribed and answers.completed explicitly mode=unlimited, amount=null, period=null. Capture is the device input for the audio pipeline, not a new billed clipboard/read operation. Operational input/rate/concurrency limits are unchanged. |
| Auto 600 cumulative seconds per IST day | assistant.auto; auto.authorized_running limited=600 second; day/calendar/Asia/Kolkata; authorized_running_including_silence_both_once basis. Starts are unrestricted by a subscription start-count quota; stopped time excluded by the basis contract. C13 must enforce this across devices/sessions. |
| All eligible configured models | model_selection=configured_supported_available. No model ID list is seeded; conflicting static IDs are rejected. Trusted policy review binds its model-registry fingerprint; operational readiness remains mandatory. |
| Resume | resume.stored_files storage cap=1; resume.replacements limited=1 replacement per account-signup monthly period. resume_extraction_basis=initial_upload_or_replacement_operation ties supporting extraction to resume admission, without inventing a separate extraction quota or counting the initial upload as replacement. |
| Screen | screen.analyses limited=5 analysis per monthly period; screen.followups denied. |
| Clipboard | clipboard.saved_answers included; clipboard.new_saves limited=5 save per monthly period; saved_answer_policy=immutable_user_entries_retain_across_resets. New persisted user-written entries count, not reads, OS clipboard access, AI generations or stored-item count. |
| History/exports/notes/Ask AI | sessions.history/transcripts.export explicitly listed in unmetered_features; notes.generations and ask_ai.completed explicitly unlimited. Existing retention/privacy/safeguards unchanged. |
| Sketch | sketch.generate denied; presentation label Introducing Sketch, exact approved info text, preview=unavailable. Clipboard metadata uses the exact approved info text; inclusion derives from entitlements, so Clipboard is not struck through. |
| Free price | pricing_mode=free, prices=[], discounts=[]; no invented currency or billing interval. |

All recurring monthly entries use month/account_signup_day/Asia/Kolkata. Periods are calendar arithmetic, midnight IST, retain the original anchor after clamping and do not roll over. The existing allowance_period helper is reused; one additional UTC-to-IST signup-day test supplements the original eight tests.

An authorized administrator clicks Import approved Free draft, reviews/edits it, supplies change reason and saves through the existing create operation. Import itself writes nothing and publication is separate. The button disables for the current v2 candidate; subsequent imports never silently update an existing draft. The unique stable free code rejects another saved plan of that code, with guidance to reopen the original draft ID. Saves/replays use existing verified actor/current database permission/CAS/durable key/audit paths. Uncertain writes retain the same identity; invalid input never writes. Confirmed saves now populate Open draft by ID, fixing the previously demonstrated missing reopen ID. Normal reopened editing and customer-safe preview preserve every field.

Usage & presentation controls edit allowance modes/amounts/cadence, pricing mode, unmetered usage and label/info copy. Inclusion is edited in Features & limits. Dynamic model selection is shown without an editable static-ID list. Plain text is bounded; unknown controls, HTML, URLs-as-controls, contradictory versions/units/allowances and paid prices on a free offer fail validation. Customer-safe projection excludes notes and internal policy references. Presentation changes participate in canonical terms/review binding.

CatalogFeaturePresentation is reused by CatalogPolicyPreview in the admin preview and tested as a reusable pricing renderer inside the existing landing #pricing layout. Matching lucide Eye/Info controls share spacing; hover/focus/tap info, Escape retaining focus, accessible names/focus and event isolation are verified. No supported Sketch/Clipboard preview asset/destination was established, so eyes stay disabled. No promotional video/modal/access grant was invented. The existing landing headline remains; fabricated sample paid plans/discounts were removed and replaced with a pending-catalog notice. No public catalog activation occurred.

Source/readiness limits: Clipboard maps to session-scoped My Answers create/list in `backend/app/cloud/interview_session_my_answers.py` and `frontend/src/components/AnswerPanel.jsx`, not OS clipboard functions. Account-wide metering is new future C13 work. The app passes completed diagram sources through `frontend/src/App.jsx` to the answer display, but this audit does not establish a branded Sketch preview destination or deployed Sketch guarantee; registry readiness is conservative. `frontend/src/components/ScreenContextControls.jsx:34` exposes Continue, :36 New and :38 Passage/Data. Continue may extend an existing question or use a passage for another question, and Passage can be reference capture without generation. Do not automatically equate every Continue with a denied follow-up or charge each reference capture as an analysis. Action classification and retry/failure counting remain explicit C13 integration work, not fabricated commercial rules.

Completion evidence is recorded in [implementation plan section 26](C11_C13_SUBSCRIPTION_IMPLEMENTATION_PLAN.md#26-approved-free-plan-integration-2026-10-23). Publication remains blocked by missing production policy authority/configuration and unresolved approval references; no real admin, offer, shared SQL, payment or enforcement activation.


## Subsequent C11.4 integration

The approved Free reference, v2 contracts/registry and IST helper remain unchanged during Plus/Pro integration. Free synthetic publication now reaches the read-only public catalog and existing landing pricing through the same reviewed workflow. See [Plus/Pro and C11.4 acceptance](PLUS_PRO_APPROVED_DECISIONS.md); C13 enforcement/real activation remain pending.
