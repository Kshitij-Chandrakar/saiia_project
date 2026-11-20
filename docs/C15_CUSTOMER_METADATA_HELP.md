# Customer metadata explanations

5 November 2026. Local UI implementation in `E:/saiia_project/c15-stage1`, branch `work/c15-stage1`, baseline `682bd57520dd49ad16ba13c65104aa9deda4fffa`. Entry status contained 190 existing modified/untracked entries. No checkout, index change, migration, grant, provider operation, commit or push.

## Implemented scope

Customers → Inspect metadata now explains every displayed section and field with a reusable information button. Explanations support hover, focus, click/tap pinning, Enter/Space toggling, Escape and outside-click dismissal. Native top-layer popovers escape the dashboard's scrolling cards; bounded placement follows the anchor and closes if the anchor leaves the content viewport. Opening help does not change card height or make a network request. Changing inspection or navigating away unmounts its help.

The existing Overview tooltip was local to that component and lacked persistent-click/outside-click behavior. The new customer-only `AdminHelp` supplies the requested contract without changing Overview or adding a dependency.

The fixed account fields, dynamic resource/consent fields, three existing subscription status fields, cancellation-command state, four existing privacy-task fields and five action explanations are covered. Fetched allowances and other previously undisplayed subscription/privacy fields remain undisplayed. No extra backend fields or broader metadata access were introduced.

Labels and status values have explicit mappings. Unknown values show “Unknown value” with expandable technical detail. Missing data remains unavailable, boolean false remains “No” and numeric zero remains zero. Account, staff, accepted-deletion and plan-assignment states remain distinct. Timestamps show UTC and preserve exact source strings under “Exact timestamp”.

Sensitive-action handlers and their confirmations are retained. The cleanup-retry confirmation additionally states that staff cannot initiate deletion, expand scope, bypass holds or mark uncertain work complete. No test submits a mutation, cancellation or retry.

## Definition sources and compact inventory

| Displayed fields | Definition source and important limits |
| --- | --- |
| Account ID, Email, Registered, Email verified, Accepted deletion request, Data as of | `supabase/migrations/20261102070000_admin_metadata.sql:15`: Auth identity/creation/confirmation, existence of accepted deletion request, SQL statement timestamp. This is not proof of completed cleanup. |
| Sign-in methods | `20261103070000_admin_metadata_detail.sql:6`: distinct linked Auth identity providers, not guaranteed usable login methods. |
| Account restriction status, Staff restriction | Same migration, lines 7–8: staff restriction plus deletion/restore flags for the combined account status. “Not staff-restricted” says nothing about other restrictions or entitlement. |
| Plan code, Plan assignment status | Same migration, lines 9–10: current binding's catalog plan code and active/valid-until test, separate from payment and restrictions. |
| Last recorded activity, Activity coverage | `20261103080000_admin_telemetry.sql:8` and `:70`: maximum recorded activity completion time. Triggers record successful interview-session insertion or transition of a usage operation to `settled`, excluding restricted/staff subjects. This is not last login, polling or online presence and has no pre-tracking coverage. |
| Resumes, Active resumes, Resume processing, Sessions, Latest session start/end, Saved job details, Resource coverage | `20261103070000_admin_metadata_detail.sql:12`: current nondeleted resume counts/statuses, active resumes, current sessions and max start/end times, job-context count. Current records do not establish lifetime totals. Resume stage vocabulary: `20260803143000_add_resume_lifecycle_and_harden_cloud_writes.sql:42`. |
| Marketing opt-in, Marketing preference updated, Terms version, Privacy policy version, Latest policy acceptance | Same metadata-detail migration, lines 21–25: settings consent flags/version and later opt-in/out or terms/privacy timestamps. Marketing preference alone does not establish delivery eligibility. |
| Payment operation status, Provider subscription status, Cancellation status | `20261103070000_admin_metadata_detail.sql:35`: billing operation state, last provider state, and terminal-state/request logic. No provider references, raw evidence or staff history are displayed. Payment state machine: `20261025020000_razorpay_checkout.sql:20`. |
| Cancellation request status | `20261103040000_admin_cancellation.sql:12` and `:33`: current actor's minimal command receipt, separate from product-access status. |
| Cleanup scope, Cleanup task status, Task revision, Attempts | `20261103020000_admin_privacy_retries.sql:70`: bounded existing task metadata. Scopes/states: `20261030120000_privacy_content_jobs.sql:6`. Primary verification is not full erasure. |
| Restrict / Restore / Request cancellation / Refresh cancellation / Review cleanup retry | Existing handlers in `AdminConsole.jsx`, `20261103010000_admin_customer_access.sql`, `20261103040000_admin_cancellation.sql`, and `20261103020000_admin_privacy_retries.sql:12`. Same backend permissions, proof, review, revision, hold and idempotency enforcement. |

Exact label/help text for all **34 explicit field definitions**, including formatting, is in [field-help-inventory.json](evidence/c15-customer-help-20261105/field-help-inventory.json). Unknown future resource/consent fields receive a neutral explanation and exact technical key, not invented business meaning.

## Demonstrated defect fixed

`inspect()` previously checked only the page-load ticket. Two overlapping requests on the same page could let an older customer's reply overwrite the latest selection. Each inspection now has a monotonically increasing local sequence, clears previous details/cancellation receipt immediately, and accepts only the latest response/error. Cancellation-status refresh also checks the inspection sequence. No API contract changed.

The browser test delays one customer's metadata response, selects a different real synthetic customer, then releases the older response. The newer customer's details remain visible. Help and old command receipts cannot survive the selection change.

## Changed files and review placement

- `frontend/src/auth/AdminHelp.jsx`: customer help interaction and top-layer placement.
- `frontend/src/auth/AdminCustomerMetadata.jsx`: presentation, explicit field definitions and value/status formatting.
- `frontend/src/auth/AdminConsole.jsx`: component wiring, inspection sequence and privacy confirmation explanation.
- `frontend/src/auth/admin-console.css`: scoped metadata/help styles only; existing shell and other forms retained.
- `frontend/tests/c15-admin/customer-help.run.mjs`: focused actual-app and labelled response-fixture coverage.
- This report and fresh `docs/evidence/c15-customer-help-20261105/` evidence.

These are a bounded addition to the existing admin presentation review group, not a new backend or permission slice. Historical reports and protected leftovers remain untouched.

## Verification and limitations

- **12 scenario groups passed**: both roles, real local login/inspection at 1440×900, 390×844 and 720×450; help on every field/heading, zero help-triggered API calls, hover/pointer transfer, keyboard/Enter/Space, touch tap, Escape/outside click, viewport bounds, unchanged card height, exact timestamp access, cancellation/restriction/privacy confirmation opening and cancellation, selected-customer/unmount cleanup, no page errors, and no page-wide horizontal overflow.
- Optional subscription/privacy-task states and missing/zero/false/unknown values use clearly identified browser-response fixtures; real local Auth and role checks remain active. No fixture is written to the database or application metrics.
- **5 existing actual authorization/verification checks passed**, using the existing safety runner with evidence redirected to this directory. Missing proof still opens verification without submitting a mutation; account switching still removes restricted navigation.
- Scoped ESLint passed. Full Vite build passed with operational env files disabled and output writes disabled. No TypeScript files changed; JSX compilation is included in the build. No formatter dependency was added.
- Desktop/mobile screenshots were visually inspected. Effective 200% layout is exercised by a 720×450 viewport for a 1440×900 screen, not physical-device or cross-browser certification.
- Only synthetic local identities were used. The authorized local services remain running at http://127.0.0.1:5400/auth/admin?view=users. No environment reset/teardown was performed, and no historical evidence output path was reused.
