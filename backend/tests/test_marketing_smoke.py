import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.email import marketing_smoke as smoke
from app.email.config import MarketingEmailSettings


USER = '00000000-0000-4000-8000-000000000001'
ARGS = ['--user-id', USER, '--email', 'test@example.com', '--idempotency-key', 'dev-smoke-1']


@pytest.fixture
def deps(monkeypatch):
    monkeypatch.setattr(smoke, 'canonical_user_email', Mock(return_value='test@example.com'))
    settings = MarketingEmailSettings(provider_mode='live', enabled=True, resend_api_key='synthetic-key')
    monkeypatch.setattr(smoke, 'load_marketing_email_settings', lambda: settings)
    unsubscribe = Mock()
    unsubscribe.is_marketing_allowed.return_value = True
    token_factory = Mock(return_value=unsubscribe)
    events = Mock()
    service = Mock()
    service.send_marketing_email.return_value = SimpleNamespace(
        status='sent', id=USER, provider_message_id=USER, metadata_json={'dry_run': False})
    factory = Mock(return_value=service)
    monkeypatch.setattr(smoke, 'build_marketing_unsubscribe_service', token_factory)
    monkeypatch.setattr(smoke, 'build_outbound_email_event_service', events)
    monkeypatch.setattr(smoke, 'MarketingEmailService', factory)
    return unsubscribe, token_factory, events, service, factory


@pytest.mark.parametrize('mode,enabled', [('dry_run', False), ('dry_run', True), ('live', False)])
def test_smoke_requires_both_live_flags(monkeypatch, deps, capsys, mode, enabled):
    monkeypatch.setattr(smoke, 'load_marketing_email_settings', lambda: MarketingEmailSettings(
        provider_mode=mode, enabled=enabled, resend_api_key='synthetic-key'))
    assert smoke.main(ARGS) == 2
    deps[1].assert_not_called()
    deps[3].send_marketing_email.assert_not_called()
    assert json.loads(capsys.readouterr().out)['status'] == 'blocked_live_flags'


def test_smoke_requires_consent(deps, capsys):
    deps[0].is_marketing_allowed.return_value = False
    assert smoke.main(ARGS) == 2
    deps[2].assert_not_called()
    deps[3].send_marketing_email.assert_not_called()
    assert json.loads(capsys.readouterr().out)['status'] == 'blocked_consent'


def test_smoke_calls_service_once_and_prints_only_safe_fields(deps, capsys):
    assert smoke.main(ARGS) == 0
    deps[3].send_marketing_email.assert_called_once_with(
        user_id=USER, recipient_email='test@example.com', campaign_key='dev-smoke',
        template_key='product_update', idempotency_key='dev-smoke-1')
    output = json.loads(capsys.readouterr().out)
    assert output == {'status':'sent', 'event_id':USER, 'provider_message_id':USER, 'mode':'live'}


@pytest.mark.parametrize('args', [[], ['--email', 'test@example.com'], ARGS[:-2], ARGS + ['--unknown', 'private-value']])
def test_smoke_requires_explicit_valid_arguments(deps, capsys, args):
    assert smoke.main(args) == 1
    deps[1].assert_not_called()
    assert 'private-value' not in capsys.readouterr().out


def test_smoke_redacts_provider_failure(deps, capsys):
    deps[3].send_marketing_email.side_effect = RuntimeError('Authorization: synthetic-key token=private')
    assert smoke.main(ARGS) == 1
    assert json.loads(capsys.readouterr().out) == {'status':'failed_check_event_before_retry', 'mode':'live'}


def test_smoke_rejects_recipient_mismatch(monkeypatch, deps, capsys):
    monkeypatch.setattr(smoke, 'canonical_user_email', Mock(return_value='owner@example.com'))
    assert smoke.main(ARGS) == 2
    deps[3].send_marketing_email.assert_not_called()
    deps[2].assert_not_called()
    assert json.loads(capsys.readouterr().out) == {'status':'blocked_recipient_mismatch', 'mode':'live'}


def test_smoke_dispatches_canonical_email_after_normalized_match(deps):
    args = ARGS.copy()
    args[3] = ' TEST@EXAMPLE.COM '
    assert smoke.main(args) == 0
    assert deps[3].send_marketing_email.call_args.kwargs['recipient_email'] == 'test@example.com'


def test_smoke_refuses_identity_lookup_failure(monkeypatch, deps, capsys):
    monkeypatch.setattr(smoke, 'canonical_user_email', Mock(side_effect=RuntimeError('private token https://private.example')))
    assert smoke.main(ARGS) == 1
    deps[3].send_marketing_email.assert_not_called()
    assert json.loads(capsys.readouterr().out) == {'status':'failed_check_event_before_retry', 'mode':'live'}


@pytest.mark.parametrize('status,user,ok', [
    (200, {'id':USER, 'email':' TEST@Example.com ', 'email_confirmed_at':'2026-01-01'}, True),
    (200, {'id':USER, 'email':'test@example.com'}, False),
    (200, {'id':'00000000-0000-4000-8000-000000000002', 'email':'test@example.com', 'email_confirmed_at':'2026-01-01'}, False),
    (404, {}, False),
])
def test_canonical_lookup_uses_trusted_auth_user(monkeypatch, status, user, ok):
    settings = SimpleNamespace(supabase_url='https://project.supabase.co', service_role_key='synthetic-service', anon_key='synthetic-anon')
    monkeypatch.setattr(smoke, 'get_supabase_settings', lambda: SimpleNamespace(require_configured=lambda:settings))
    get = Mock(return_value=SimpleNamespace(status_code=status, json=lambda:user))
    monkeypatch.setattr(smoke.requests, 'get', get)
    if ok:
        assert smoke.canonical_user_email(USER) == 'test@example.com'
    else:
        with pytest.raises(ValueError, match='Trusted identity lookup failed'):
            smoke.canonical_user_email(USER)
    assert get.call_args.args[0] == f'https://project.supabase.co/auth/v1/admin/users/{USER}'
    assert get.call_args.kwargs['allow_redirects'] is False
    assert get.call_args.kwargs['timeout'] == 8
