# gRPC comparison for lint review ? 27 October 2026

**Both reported failures reproduce before and after the lint changes. No lint regression was found in these two cases.** No application/test source was edited by this comparison. No providers, installed/external acceptance, migrations or credentials were used.

## Why a comparison was needed

`tmp/frontend-lint-closure/preexisting-repro.log` already reproduced the permission-wait failure using the saved pre-edit App source, but used a renamed test and a different command. It was retained, not overwritten. The capture-start case lacked a paired isolated baseline record. A single paired run of only the two failing cases now establishes identical commands/environment; the full suite was not repeated.

## Baseline provenance and isolation

The baseline is the saved immediately pre-lint `tmp/frontend-lint-closure/before/src/App.jsx`, together with the seven test/dependency files untouched by the lint work. Those seven files were copied byte-identically into both isolates. The current copy contains current App.jsx. This reconstructs the affected pre-lint test inputs; it is **not** a clean Git HEAD checkout or proof of a complete historical repository/environment snapshot. Existing uncommitted gRPC changes are intentionally included in both sides and were not reverted.

Copies and complete source hashes: `tmp/frontend-lint-baseline-comparison/{baseline,current}/`. Manifest, environment attestation and command: `comparison.json` in that directory. No symlinks or file swaps targeted the working source tree. Before/after source-byte equality was asserted for all eight working files.

Both used Node v24.16.0 and the same captured environment object, with identical color settings and NODE_OPTIONS removed for isolation. No secret environment values were logged. Both use the same network-denial preload for HTTP/HTTPS/TCP/TLS/UDP/fetch/WebSocket. Test bodies use deterministic substitutes.

Identical command from each isolate root:

```text
node --require ./no-network.cjs --test --test-name-pattern "combined capture-start failure|Stop during combined permission wait" src/grpc_combined.test.js src/grpc_computer_auto.test.js
```

## Results

| Case | Isolated baseline | Isolated current | Classification |
| --- | --- | --- | --- |
| Combined capture-start failure closes both sources once, suppresses late events and never falls back | Fails: expected null, actual undefined for ended listener | Same failure | Pre-lint failure; no lint regression demonstrated |
| Stop during combined permission wait releases late tracks without opening gRPC | Fails: `TypeError: resolve is not a function` | Same failure | Pre-lint asynchronous fixture/precondition failure; no lint regression demonstrated |

Each run: **2 tests, 0 passed, 2 failed, exit 1**. Exact logs: `baseline.log` and `current.log`. Tests were not altered to hide failures, and no unrelated gRPC fix was made. This comparison establishes origin, not whether all surrounding gRPC runtime behavior is correct.

## Review readiness

**Lint changes are ready for code review**, with the existing evidence: lint 0 errors / 12 warnings, 179 focused Node tests passed, 52 catalog browser checks plus 2 new lifecycle regressions passed, build/syntax/whitespace passed. No check was rerun solely to recreate those accepted results.

The branch is **not fully CI-green**: the broader Node command previously passed 715 and failed these two cases. Twelve hook warnings remain explicitly documented in `FRONTEND_LINT_CLOSURE_20261027.md`. C11/C12/C13 remain open, Razorpay support findings are pending, and provider execution remains paused. No commit, push or release-readiness claim.
