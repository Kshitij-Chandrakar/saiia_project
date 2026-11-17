# C15 actual integration acceptance preparation

Pending, 30 October 2026. No commands here were run against hosted services. No remote permission/configuration change is authorized. Preserve the recorded Windows build failure; do not repeat it.

## Required non-secret inputs

- Authorized Linux/container runtime and dedicated local workspace; no system installation in this stage.
- Official Auth **v2.197.0**, commit `4eee58f296d9698a1c2c0ae14d7a0b379c7622d3`. Source archive SHA-256 `b35bab74f6a45e0593e7a113e30f85c12c83bbb540940c3e82eeb0a9af76a297`. Resolve and record official immutable container digest rather than guessing one. PostgreSQL **17.11** and an official local catcher likewise require recorded immutable digests before launch. Do not use `latest`.
- Unused loopback ports, unique project/volume names, locally generated ephemeral JWT/encryption/matching keys and passwords; never operational dotenv or hosted keys. Internal-only network, catcher as sole SMTP destination, Google/Resend/external providers disabled. Verify no egress route before scenarios.
- Exact local Auth hook configuration and schema/migration ordering; review existing disabled `C15_AUTH_HOOKS_PENDING.toml`. The before-create and token hooks are separate. Linking/email-change transactions and existing-user login require their own tests.

## Executable independent local checks

From `E:/saiia_project/c15-stage1` with the already available portable PG directory:

```powershell
& E:/deepfake_envs/SaIIA/python.exe scripts/c15_content_local_tests.py --pg-bin C:/Users/chand/AppData/Local/Temp/c112c-native-runtime-0f19d4be3f9a436d8c761b2eaf2472a9/pgsql/bin --suite backend/tests/test_privacy_remaining_native.py --evidence-dir docs/evidence/c15-remaining-local-next --capture
```

This command deliberately uses synthetic Auth/Storage boundaries. It cannot become actual engine acceptance by relabeling the output or substituting a hosted DSN. No need to rerun unchanged checks merely to wait for a runtime.

## Actual local Auth/Storage sequence once prerequisites exist

1. Pin/inspect official image digests (`docker image inspect <official-image@sha256:verified-digest> --format '{{json .RepoDigests}}'`); record versions and config without secret values. Render the isolated project's compose config; reject non-loopback published ports, nonlocal SMTP, external networks/providers and inherited operational environment. No image digest has been fabricated in this report.
2. Start only the named disposable DB/catcher/Auth stack. Apply ordered application migrations to that local DB after actual engine bootstrap. Compare its complete relevant schema to `privacy_fields.json`; unknown columns/tables keep activation closed. Enable hooks only in this disposable stack. Keep normal deletion/export/purge disabled.
3. Execute the scenario matrix in `C15_LOCAL_AUTH_REHEARSAL.md`: actual password/TOTP endpoints, application-issued deletion/export OTP through local catcher, wrong/stale/refresh-only/subject/replay/limits/concurrent proof, final typed confirmation, direct Auth signup, token issuance, linking/email-change, bootstrap races and hook outage/malformed/timeout cases. Distinguish identity blocked, session blocked and product denied for each path. Google fixtures never prove real Google behavior.
4. Close initiating browser and process durable revocation with its implemented encrypted credential mechanism. Verify actual refresh-token rejection, unaffected second account, old access-JWT product denial, worker crash/expiry/missing-key/uncertain response. Record credential clearing without capturing values.
5. Use actual local Storage HTTP API, not `storage.objects` metadata or fake adapter, to test owned upload/read/delete, nested owner isolation, 403/404/unavailable distinction, signed URL before/after restriction and after expiry, interrupted writes, retries, archive expiry and deletion versus publication/download. Verify bytes in the object service. New download authorization must recheck server restriction/expiry; delivered bytes cannot be recalled.
6. Capture synthetic desktop/mobile UI evidence with secret/OTP fields excluded. Stop only owned stack, remove only owned volumes/mail, verify listeners/keys gone and development listeners unaffected. Record failed cases honestly; no activation from local acceptance alone.

## Hosted and processor acceptance (separate later authorization)

Required non-secret inputs: configured processor/model list, service versions, Auth hooks/identity-link settings, JWT/signed-URL lifetimes, Storage/CDN/cache settings, log drains/TTL, scheduled/PITR/manual/object backup inventory, retention contracts and external deletion capability by data category. No customer payload is needed to plan these checks.

Official capability references: [Auth hooks](https://supabase.com/docs/guides/auth/auth-hooks), [before-user-created](https://supabase.com/docs/guides/auth/auth-hooks/before-user-created-hook), [token hook](https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook), [self-hosted hooks](https://supabase.com/docs/guides/self-hosting/self-hosted-auth-hooks), [Storage downloads](https://supabase.com/docs/guides/storage/serving/downloads), [object deletion](https://supabase.com/docs/guides/storage/management/delete-objects). These document capabilities, not this project's actual configuration. Auth sign-out does not prove immediate issued-JWT or signed-URL invalidation. No processor zero-retention or backup-erasure deadline is accepted here.

External restore evidence must have an independently durable latest checkpoint/keyring outside every restored copy, a complete outbox/cutover protocol and a fail-closed deployment startup gate. Rehearse missing/newer/rolled-back evidence, key recovery and old DB/object restoration before traffic. No unverified expiry is assigned to suppression or replay markers. Billing provider operations remain paused.
