# C15 hosted migration ownership correction

24 November 2026. Local verification only; hosted retry has not been performed.

## Incident and scope

The owner's hosted history confirms seven migrations through
`20261031100000` applied. `20261031120000` failed at transfer of
`privacy_auto_credentials_erase(uuid,uuid)` to `privacy_payload_owner`.
Its explicit transaction was not recorded as applied. Do not repair migration
history or rerun the seven successful files.

PostgreSQL requires SET ROLE authority and destination-schema CREATE permission
for a non-superuser ownership transfer. Source reference:
https://www.postgresql.org/docs/17/sql-alterfunction.html

Five still-pending migrations are corrected:

| Migration | Private owner |
| --- | --- |
| 20261031120000_privacy_auto_credentials.sql | privacy_payload_owner |
| 20261101030000_privacy_revocation_observer.sql | privacy_revocation_observer_owner |
| 20261102010000_privacy_identity_cleanup.sql | privacy_identity_owner |
| 20261102020000_privacy_runtime_operations.sql | privacy_runtime_owner |
| 20261102030000_privacy_runtime_notifications.sql | privacy_runtime_owner |

Each grants the named owner to CURRENT_USER with SET and INHERIT enabled and
grants that owner CREATE on public inside the existing transaction. Both grants
are revoked before commit. Existing NOLOGIN owners, fixed search paths, function
EXECUTE grants, request/lease checks, RLS and immutable guards are unchanged.
No caller gains private-owner membership. PostgreSQL 17's automatic role-creator
ADMIN-only membership remains; it has SET=false and INHERIT=false. This is not
runtime authority and is distinct from the removed temporary grant.

Do not use this pattern with arbitrary caller-supplied role names or runtime
principals. The migration identity is a privileged deployment principal already
authorized to create roles. The syntax requires PostgreSQL 16 or newer.

## Local evidence

Disposable container `c15-permissions-20261124`, image
`public.ecr.aws/supabase/postgres:17.6.1.155`, PostgreSQL 17.6. Network mode none,
no published ports; repository and private backup mounted read-only.

Restored roles and schema only from the pre-migration backup into a fresh
`c15_permission_verify` database. No customer data dump was loaded. Managed
schema restoration deferred the existing Storage deletion-barrier policy until
its public function existed; extensions/vault schemas and the Realtime
publication were prepared before public-schema restoration. Bootstrap used the
local platform superuser; **all 36 C15 migrations ran as postgres**, whose
attributes were SUPERUSER=false, CREATEROLE=true, BYPASSRLS=true. Managed
Auth/Storage tables remained owned by their platform roles; postgres had no
inherited owner authority for those tables.

Results:

- All 36 ordered migrations applied successfully, including the 29 still pending
  on the owner's hosted project. Earlier seven source files were not edited.
- `backend/tests/test_privacy_hosted_ownership.py`: **7 passed**. Tests check five
  function ownership contracts, absence of residual CREATE/SET/INHERIT grants,
  NOLOGIN/non-superuser/non-BYPASSRLS private owners, ordinary-role EXECUTE denial,
  runtime-owner membership denial, and transactional rollback of the original
  unprivileged ownership-transfer failure.
- Native SQL was executed through Docker psql against PostgreSQL, not mocked.
- Python compilation and git diff whitespace check passed.
- Ruff lint/format could not run: neither checked Python installation has Ruff.

The repository's offline pytest session removes ambient environment variables.
The explicit owned container was supplied after that boundary was installed:

```python
import os
import pytest

class OwnedFixture:
    def pytest_collection_modifyitems(self, items):
        os.environ['C15_OWNERSHIP_TEST_CONTAINER'] = 'c15-permissions-20261124'

raise SystemExit(pytest.main(
    ['backend/tests/test_privacy_hosted_ownership.py', '-q'],
    plugins=[OwnedFixture()],
))
```

Without that explicit fixture, the opt-in tests skip. An initial run skipped
because the environment value was cleared; it is not counted as acceptance.
An initial overstrict assertion also detected the platform's automatic
ADMIN-only creator membership. The final assertion checks its actual absence
of SET/INHERIT authority, while independently denying all runtime memberships.

Private per-migration execution logs are retained outside Git alongside the
backup. They are not a hosted acceptance claim or proof of feature activation.

## Release and cleanup

Review group: five pending migrations, one new regression module, one existing
gRPC test and this report (eight files). The commit hook exposed an existing
startup-notification race in `test_admin_grpc_access.py`: a read after restriction
could consume a previously authorized startup event. A ping/pong barrier now
drains that startup sequence before changing authority; the expected 403/503 RPC
denials remain unchanged. Both focused cases passed. No application gRPC code
was changed. No already-applied migration was changed. Do not apply a new
later migration to repair a failure in an earlier pending migration: the CLI
must first be able to execute the corrected pending file.

After review, repeat the hosted read-only history check and dry-run against the
same verified project. It should list 29 pending migrations, beginning at
`20261031120000`. Hosted execution and postflight remain separate operations;
the local schema rehearsal does not guarantee every hosted permission/config
matches. Never mark the failed version applied manually.

No hosted writes, commits, pushes, feature activation, provider calls or real
emails were performed by this correction. Only this run's disposable container
and its anonymous volume are removed; private backup and historical resources
remain preserved. See the final cleanup result beside the private test logs.

## PR #78 review follow-up

The rollback regression now checks CREATEROLE, successful BEGIN/CREATE ROLE/
CREATE FUNCTION command tags and the exact `must be able to SET ROLE` denial.
An unrelated setup SQL failure is explicitly rejected. Rehearsal container
`c15-review78-20261124` used the same pinned image, isolated network and schema-only
restore. All 36 migrations passed again as non-superuser postgres; all eight
ownership tests passed. No migration logic changed for this review finding.
