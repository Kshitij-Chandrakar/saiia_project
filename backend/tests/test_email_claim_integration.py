"""Optional local Supabase test against already-applied migrations; always rolls back."""
import os
import shutil
import subprocess
from urllib.parse import unquote, urlparse

import pytest


def test_local_postgres_email_claim_null_session_duplicate_and_allowlist():
    if os.environ.get('RUN_SUPABASE_INTEGRATION_TESTS') != 'true':
        pytest.skip('Explicit local Supabase integration opt-in required')
    url = os.environ.get('SUPABASE_DB_URL', '')
    parsed = urlparse(url)
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
             'PGHOST': parsed.hostname or 'localhost',
             'PGPORT': str(parsed.port or 5432),
             'PGUSER': unquote(parsed.username or 'postgres'),
             'PGPASSWORD': unquote(parsed.password or ''),
             'PGDATABASE': unquote(parsed.path.lstrip('/') or 'postgres'),
             'PGCONNECT_TIMEOUT': '5'})
    if result.returncode:
        hint = 'connection error' if result.returncode == 2 else 'SQL/RPC contract or local psql setup failure'
        pytest.fail(f'Local PostgreSQL claim regression failed: {hint}. Check the local database/migration setup.', pytrace=False)


@pytest.mark.parametrize('returncode', [0, 2, 3])
@pytest.mark.parametrize('explicit', [True, False])
def test_connection_setup_uses_explicit_libpq_environment(monkeypatch, returncode, explicit):
    from types import SimpleNamespace

    url = 'postgresql://test%20user:fake%40password@127.0.0.1:54322/test%20db' if explicit else 'postgresql://localhost'
    monkeypatch.setenv('RUN_SUPABASE_INTEGRATION_TESTS', 'true')
    monkeypatch.setenv('SUPABASE_DB_URL', url)
    monkeypatch.setenv('PGHOSTADDR', '192.0.2.1')
    monkeypatch.setenv('PGSERVICE', 'inherited-service')
    monkeypatch.setattr(shutil, 'which', lambda name: 'psql')

    def run(argv, **kwargs):
        assert argv == ['psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1']
        pg = {key: value for key, value in kwargs['env'].items() if key.upper().startswith('PG')}
        assert pg == {
            'PGHOST': '127.0.0.1' if explicit else 'localhost',
            'PGPORT': '54322' if explicit else '5432',
            'PGUSER': 'test user' if explicit else 'postgres',
            'PGPASSWORD': 'fake@password' if explicit else '',
            'PGDATABASE': 'test db' if explicit else 'postgres',
            'PGCONNECT_TIMEOUT': '5',
        }
        return SimpleNamespace(returncode=returncode, stderr='sensitive diagnostics must not be printed')

    monkeypatch.setattr(subprocess, 'run', run)
    if returncode:
        with pytest.raises(pytest.fail.Exception) as failure:
            test_local_postgres_email_claim_null_session_duplicate_and_allowlist()
        message = str(failure.value)
        assert ('connection error' if returncode == 2 else 'SQL/RPC contract') in message
        assert url not in message
        assert 'fake@password' not in message
        assert 'sensitive diagnostics' not in message
    else:
        test_local_postgres_email_claim_null_session_duplicate_and_allowlist()
