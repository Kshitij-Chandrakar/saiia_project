"""Optional local Supabase test against already-applied migrations; always rolls back."""
import os
import shutil
import subprocess
from urllib.parse import urlsplit

import pytest


def test_local_postgres_email_claim_null_session_duplicate_and_allowlist():
    if os.environ.get('RUN_SUPABASE_INTEGRATION_TESTS') != 'true':
        pytest.skip('Explicit local Supabase integration opt-in required')
    url = os.environ.get('SUPABASE_DB_URL', '')
    parsed = urlsplit(url)
    if parsed.scheme not in {'postgres', 'postgresql'} or parsed.hostname not in {'localhost', '127.0.0.1', '::1'} or parsed.query:
        pytest.fail('Use a loopback-only SUPABASE_DB_URL without query overrides', pytrace=False)
    psql = shutil.which('psql')
    if not psql:
        pytest.skip('Local PostgreSQL psql client unavailable')
    sql = """
BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '2s';
SET LOCAL plpgsql.variable_conflict = 'error';
DO $test$
DECLARE
  test_user uuid := gen_random_uuid();
  first_claim record;
  second_claim record;
  rejected boolean := false;
  email_kind text;
BEGIN
  INSERT INTO auth.users(id, email) VALUES (test_user, 'claim-test@example.invalid');
  FOREACH email_kind IN ARRAY ARRAY['welcome','account_security','ai_notes_ready',
      'session_summary','transcript_export','marketing_product_update'] LOOP
    SELECT * INTO first_claim FROM public.claim_outbound_email_event(
      test_user, NULL, email_kind, 'claim-test@example.invalid', 'local-integration',
      '{"dry_run":true}'::jsonb, now() + interval '5 minutes');
    IF first_claim.id IS NULL OR first_claim.status <> 'pending' OR first_claim.session_id IS NOT NULL THEN
      RAISE EXCEPTION 'First claim contract failed';
    END IF;
    SELECT * INTO second_claim FROM public.claim_outbound_email_event(
      test_user, NULL, email_kind, 'claim-test@example.invalid', 'local-integration',
      '{"dry_run":true}'::jsonb, now() + interval '5 minutes');
    IF second_claim.id IS DISTINCT FROM first_claim.id OR second_claim.conflict_reason IS DISTINCT FROM 'already_processing' THEN
      RAISE EXCEPTION 'Duplicate claim contract failed';
    END IF;
  END LOOP;
  BEGIN
    PERFORM public.claim_outbound_email_event(test_user, NULL, 'unsupported',
      'claim-test@example.invalid', 'unknown', '{}'::jsonb, now() + interval '5 minutes');
  EXCEPTION WHEN SQLSTATE 'P0001' THEN
    rejected := true;
  END;
  IF NOT rejected THEN RAISE EXCEPTION 'Unsupported email type was accepted'; END IF;
END;
$test$;
ROLLBACK;
"""
    # Keep credentials out of command arguments and captured diagnostics out of failures.
    result = subprocess.run([psql, '-X', '-q', '-v', 'ON_ERROR_STOP=1'], input=sql,
        text=True, capture_output=True, timeout=30,
        env={**{key: value for key, value in os.environ.items() if not key.upper().startswith('PG')},
             'PGDATABASE': url, 'PGCONNECT_TIMEOUT': '5'})
    if result.returncode:
        pytest.fail('Local PostgreSQL claim regression failed; inspect the local database/migration setup. Provider sending is not involved.', pytrace=False)
