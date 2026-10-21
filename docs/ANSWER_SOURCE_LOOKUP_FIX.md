# Diagram source lookup degradation and request lifecycle

2026-10-21. Local fix only; no migration, hosted query, environment edit, activation,
provider call, commit or staging. Prior quality/diagram/presentation work is preserved.

## Evidence and diagnosis

Parent remains `bff9827ab7ebbcfb560dcac5178a9391f530c5a9`, branch dev/current-work;
entry index was empty. Entry hashes/index are retained outside Git in
`%TEMP%/saiia-source-lookup-0sncnw78/baseline.json`. Applicable instructions/Graphify
were checked; the existing graph does not establish current diagram source behavior.
Read-only queries were used; artifacts were not regenerated.

The user's repeated 503 report is the runtime observation. Content-free inspection
of existing backend-run.out/err and Electron dev logs found no answer-sources
requests or relevant database error codes. No authenticated live response/body was
available here; no hosted request or credential retrieval was made to manufacture
one. Therefore the exact upstream database code in that manual run remains
**unconfirmed**. Missing prepared migrations are a reproducible explanation, not
claimed as a remotely verified deployment fact.

Confirmed old production path:
`GET answer-sources -> api.answer_diagrams.resolve_source -> DiagramStore.source
-> DiagramStore.request -> PostgREST`. Every HTTP failure raised the same
`DiagramError('unavailable',503)`, losing missing-table/function versus permissions,
transport and other failures. The route returned only `detail.code=unavailable`.
Missing new provenance schema (PGRST205/42P01) therefore reproduced this exact 503.
That was not enough evidence to distinguish the live case from another DB failure.

Separately, App's diagramSource required UI status=complete and savedRequestId/
savedSessionId, but did not retain/check `transcript_entry_stored`. An answer could
be available while its transcript save failed or had not been confirmed. This
causes premature lookups, although an absent canonical row by itself previously
returned 404 source_not_found, **not** 503. A disabled generation flag also does
not itself throw 503: the old resolver still consulted storage to support saved
reads. These cases must not be conflated.

DiagramSection did not poll source resolution; it resolves on its identity/API
lifecycle. Ordinary re-renders with the same identity do not independently repeat
it. StrictMode/remounts, multiple consumers or changed answer identities can repeat
requests; there was no bridge coalescing. Existing one-second polling is only for
an already claimed diagram's processing/checkpoint read, not source resolution.
The live repetition mechanism cannot be inferred from absent logs alone.

## Minimal fixes

Backend:
- Recognize only known missing-schema codes PGRST205/PGRST202/42P01 at new diagram/
  provenance storage boundaries. Canonical transcript table failures remain genuine
  service errors; arbitrary 404/500 responses are not reclassified as missing schema.
- Resolve returns explicit `state=unavailable, reason=schema_unavailable` for this
  expected staged-deployment case. A missing request-ID answer returns
  `state=pending, reason=source_pending`; neither authorizes generation or exposes
  answer text. Explicit missing transcript IDs keep source_not_found/404.
- Missing diagram schema during saved read also returns unavailable with the
  requested source revision. Normal provider/mutation failures retain existing policy.
- Other DB/transport failures retain 503 unavailable; configuration_missing remains
  503. There is no blanket 503-to-200 conversion or disabled-flag bypass of ownership.
- Safe diagnostic lines contain only fixed stage, upstream HTTP status and a bounded
  code whitelist (or other/transport_or_response). No URL, user/session/request ID,
  headers, credentials, DB/provider messages or interview content is logged.

Frontend/Electron:
- App now retains explicit save confirmation from HTTP final metadata and from
  negotiated coordinated gRPC durable completion (or an already observed saved
  status). `completedDiagramSource` requires it, canonical displayed text equality,
  completed status, same session/request and non-Screen/non-provisional display.
  Unknown legacy live completion is not assumed durable; owned stored history can
  still resolve independently. No transcript is created or answer generation changed.
- Resolve requests share one in-flight promise and bounded 64-entry safe descriptor
  cache, fenced by existing auth generation/connection epoch. A confirmed missing
  diagram schema suppresses subsequent source requests across answers for that auth
  generation, not just the same answer. Logout/invalidation clears it; reconnect/
  desktop restart after a separately approved schema deployment refreshes capability.
- Pending and genuine failures are not retained as permanent descriptor cache entries;
  later explicit resolution can recover. No automatic source polling/retry is added.
  Generic service failures are not globally suppressed/cached as missing schema.
- IPC exposes only safe state/reason enums. Stale delivery checks remain. Renderer
  distinguishes pending, unsupported schema/unavailable and ineligible provenance;
  service errors no longer masquerade as ineligibility or written-answer failure.
- Disabled generation still resolves owned saved sources and reads ready diagrams.
  It never creates a generation call. Unavailable/pending lookup does not schedule
  diagram polling; the written answer remains intact.

No audio/STT, protobuf, provider, answer-save owner or persistence-policy changes.
No diagram activation or new endpoint/dependency. Expected states are additive HTTP
response fields; new backend/client should be deployed together for the full benefit.
Old backends still emit their generic error; the client cannot diagnose an unknown
upstream code from that. Previously prepared patch files remain historical; these
changes belong to diagram patch B, which must be refreshed/reverified before commit.

## Changed files

- `backend/app/api/answer_diagrams.py`
- `backend/app/cloud/answer_diagrams.py`
- `backend/tests/test_answer_diagrams.py`
- `frontend/electron/answer_diagrams.cjs`
- `frontend/src/App.jsx`
- `frontend/src/components/DiagramSection.jsx`
- `frontend/src/diagram_source_revision.js`
- `frontend/src/grpc_auto_session.js`
- `frontend/src/grpc_manual_session.js`
- `frontend/src/answer_stream_phase3.test.js`
- `frontend/tests/answer_diagrams.test.cjs`
- `frontend/tests/answer_diagrams.browser.test.mjs`
- `docs/ANSWER_SOURCE_LOOKUP_FIX.md`

## Verification

All Python runs enter the existing offline harness before app imports: synthetic
credentials, dotenv disabled, mocked retrieval/storage/providers and forbidden
unexpected outbound HTTP. Browser and Node networking are loopback-only. Logs and
raw results remain outside Git in the evidence directory above.

```powershell
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests/test_answer_diagrams.py -q --tb=short
& E:/deepfake_envs/SaIIA/python.exe -B backend/scripts/answer_quality_baseline.py --tests backend/tests -q --tb=short
$env:NODE_OPTIONS='--require "E:/saiia_project/saiia_project/frontend/tests/fixtures/loopback_only.cjs"'
$tests=@(rg --files frontend | Where-Object {$_ -match '\.test\.(cjs|js|mjs)$' -and $_ -notmatch '\.browser\.test\.' -and $_ -notmatch 'node_modules'})
node --test @tests
node --test frontend/tests/answer_diagrams.browser.test.mjs frontend/tests/answer_stream_phase3.browser.test.mjs frontend/tests/answer_presentation.browser.test.mjs
node --test frontend/src/answer_stream_phase3.test.js frontend/tests/answer_diagrams.test.cjs
# From frontend:
npm run build
# From root:
node --check frontend/electron/answer_diagrams.cjs
git diff --check
```

Results: focused backend **54 passed**; full backend **1614 passed, 2 existing
skips (72.25s)**. Frontend/Electron **683 passed**. Rendered integration **18 passed**,
including pending/unavailable without polling, disabled generation restoring a saved
diagram, main/overlay primary/fallback streaming across three audio modes and safe
canonical/history presentation. Build passed in 4.31s with the existing chunk-size
warning. Final saved/provisional assertions additionally exercise all three actual
negotiated client/consumer paths. Safe logging tests seed forbidden synthetic header
and message content and verify neither appears in captured logs.

These tests establish the reproduced exception mapping and lifecycle fix, not the
exact hosted deployment state. Native/manual retest should inspect only response
`state/reason` or `detail.code`, and the new content-free stage/status/code diagnostic.
If a genuine 503 remains, retain it and investigate that specific safe upstream code;
do not assume missing migration or enable diagrams to silence it. Diagram migration
application and recovery hardening remain separately unauthorized/paused.
