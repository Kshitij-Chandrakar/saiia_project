from dataclasses import replace, asdict
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.email_unsubscribe import router, get_marketing_unsubscribe_service, _one_click_token
from app.email.config import EmailConfigurationError, MarketingEmailSettings, load_marketing_email_settings
from app.email.event_store import OutboundEmailEventService, OutboundEmailEventError, OutboundEmailEventConflictError
from app.email.marketing import MarketingEmailRequest, MarketingEmailService, ResendMarketingProvider
from app.email.unsubscribe import MarketingUnsubscribeService
from test_email_event_store import FakeEventClient
from test_email_unsubscribe import FakeUnsubscribeClient, TEST_USER_ID


def setup_service(settings=None):
    events = FakeEventClient()
    tokens = FakeUnsubscribeClient()
    unsubscribe = MarketingUnsubscribeService(client=tokens)
    network = Mock()
    provider = ResendMarketingProvider(settings or MarketingEmailSettings(), session=network)
    service = MarketingEmailService(event_store=OutboundEmailEventService(client=events),
        unsubscribe_service=unsubscribe, settings=settings, provider=provider)
    return service, events, tokens, network


def send(service, key='product-update-1'):
    return service.send_marketing_email(user_id=TEST_USER_ID, recipient_email='reader@example.com',
        campaign_key='release-1', template_key='product_update', idempotency_key=key)


def test_default_dry_run_and_safe_config():
    settings = load_marketing_email_settings({})
    assert settings.provider_mode == 'dry_run'
    assert not settings.enabled
    assert settings.reply_to == ''
    assert settings.from_email == 'updates@intervucopilot.in'
    with pytest.raises(EmailConfigurationError):
        load_marketing_email_settings({'EMAIL_PROVIDER_MODE': 'live'})
    for env in [{'EMAIL_PROVIDER_MODE':'unknown'}, {'MARKETING_FROM_EMAIL':'updates@evil.example'},
                {'MARKETING_REPLY_TO':'a@evil.example'}, {'MARKETING_EMAILS_ENABLED':'typo'},
                {'MARKETING_FROM_NAME':'Header\r\nInjection'}]:
        with pytest.raises(EmailConfigurationError): load_marketing_email_settings(env)
    assert 'synthetic-credential' not in repr(MarketingEmailSettings(resend_api_key='synthetic-credential'))


@pytest.mark.parametrize('consent', [False, None, 'true', 1])
def test_only_explicit_true_consent_allows_send(consent):
    service, events, tokens, network = setup_service()
    tokens.marketing_opt_in[TEST_USER_ID] = consent
    event = send(service)
    assert event.status == 'canceled'
    assert not tokens.tokens
    network.post.assert_not_called()


def test_opted_in_dry_run_safe_event_and_idempotency(caplog):
    service, events, tokens, network = setup_service()
    with caplog.at_level(logging.INFO):
        first = send(service)
        second = send(service)
    assert first.id == second.id
    assert first.status == 'sent' and first.provider == 'dry_run'
    assert len(tokens.tokens) == 1
    assert first.metadata_json == {'campaign_key':'release-1', 'template_key':'product_update', 'dry_run':True}
    assert 'reader@example.com' not in caplog.text
    assert 'https://' not in caplog.text
    assert 'token' not in str(first.metadata_json)
    assert 'text_body' not in asdict(first)
    network.post.assert_not_called()


def test_unsubscribe_failure_blocks_dispatch():
    service, events, tokens, network = setup_service()
    service._unsubscribe.create_token = Mock(side_effect=RuntimeError('sensitive-token'))
    with pytest.raises(OutboundEmailEventError, match='setup failed') as error:
        send(service)
    assert 'sensitive' not in str(error.value)
    assert next(iter(events.records.values())).status == 'failed'
    network.post.assert_not_called()


def test_opt_out_during_token_creation_blocks_send():
    service, events, tokens, network = setup_service()
    original = service._unsubscribe.create_token
    def create(**kwargs):
        token = original(**kwargs)
        service._unsubscribe.unsubscribe(raw_token=token.raw_token)
        return token
    service._unsubscribe.create_token = create
    assert send(service).status == 'canceled'
    network.post.assert_not_called()


def test_marketing_flag_blocks_real_send_in_live_mode():
    service, events, tokens, network = setup_service(MarketingEmailSettings(provider_mode='live', resend_api_key='synthetic-credential'))
    assert send(service).provider == 'dry_run'
    network.post.assert_not_called()


def test_live_request_template_headers_and_no_duplicate():
    settings = MarketingEmailSettings(provider_mode='live', enabled=True, resend_api_key='synthetic-credential')
    service, events, tokens, network = setup_service(settings)
    network.post.return_value = SimpleNamespace(status_code=200, json=lambda: {'id':'00000000-0000-4000-8000-000000000002'})
    first = send(service)
    assert send(service).id == first.id
    assert network.post.call_count == 1
    args, kwargs = network.post.call_args
    assert args == ('https://api.resend.com/emails',)
    body = kwargs['json']
    assert body['subject'] == 'What’s new in Intervu AI'
    assert 'Unsubscribe: https://intervucopilot.in/unsubscribe?token=' in body['text']
    assert body['headers']['List-Unsubscribe-Post'] == 'List-Unsubscribe=One-Click'
    assert '/api/email/unsubscribe/one-click?token=' in body['headers']['List-Unsubscribe']
    assert 'reply_to' not in body
    assert kwargs['allow_redirects'] is False
    assert kwargs['headers']['Idempotency-Key'] == f'marketing:{first.id}'
    assert first.metadata_json['dry_run'] is False
    assert 'https://' not in str(first.metadata_json)


def test_uncertain_provider_result_is_safe_and_not_retried():
    settings = MarketingEmailSettings(provider_mode='live', enabled=True, resend_api_key='synthetic-credential')
    service, events, tokens, network = setup_service(settings)
    network.post.side_effect = RuntimeError('sensitive body and key')
    with pytest.raises(OutboundEmailEventError, match='reconciliation') as error: send(service)
    assert 'sensitive' not in str(error.value)
    with pytest.raises(OutboundEmailEventConflictError): send(service)
    assert network.post.call_count == 1


def test_marketing_request_requires_token():
    with pytest.raises(ValueError):
        MarketingEmailRequest('reader@example.com', '', 'id', {})


def test_one_click_consumes_token_and_scrubs_query():
    tokens = FakeUnsubscribeClient()
    service = MarketingUnsubscribeService(client=tokens)
    token = service.create_token(user_id=TEST_USER_ID, recipient_email='reader@example.com').raw_token
    app = FastAPI()
    app.include_router(router, prefix='/api/email')
    app.dependency_overrides[get_marketing_unsubscribe_service] = lambda: service
    with TestClient(app) as client:
        response = client.post('/api/email/unsubscribe/one-click', params={'token':token},
                               data={'List-Unsubscribe':'One-Click'})
    assert response.status_code == 200
    assert not service.is_marketing_allowed(user_id=TEST_USER_ID)
    request = SimpleNamespace(query_params={'token':token}, scope={'query_string':b'sensitive'})
    assert _one_click_token(request) == token
    assert request.scope['query_string'] == b''


def test_forward_migration_preserves_atomic_claim_and_restricted_grants():
    root = Path(__file__).resolve().parents[2]
    sql = (root/'supabase/migrations/20260922120000_add_marketing_email_event_type.sql').read_text()
    assert sql.count("'marketing_product_update'") == 2
    constraint = sql.split('add constraint outbound_email_events_type_check', 1)[1].split(';', 1)[0]
    assert constraint.rstrip().lower().endswith('not valid')
    assert 'validate constraint' not in sql.lower()
    for email_type in ('welcome', 'account_security', 'ai_notes_ready', 'session_summary', 'transcript_export', 'marketing_product_update'):
        assert f"'{email_type}'" in constraint
    assert 'on conflict (user_id, email_type, recipient_email, session_id, idempotency_key) do nothing' in sql
    assert 'from public, anon, authenticated' in sql
    assert 'to service_role' in sql
    assert 'disable row level security' not in sql
    for path in (root/'frontend/src').rglob('*'):
        if path.is_file() and path.suffix in {'.js','.jsx'} and '.test.' not in path.name:
            assert 'RESEND_API_KEY' not in path.read_text(encoding='utf-8')
            assert 'api.resend.com' not in path.read_text(encoding='utf-8')


def test_access_log_filter_redacts_rejected_method_urls():
    from app.api.email_unsubscribe import UnsubscribeAccessLogFilter
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 1, '%s %s %s %s %s',
        ('local', 'GET', '/api/email/unsubscribe/one-click?token=synthetic-private-token', '1.1', 405), None)
    assert UnsubscribeAccessLogFilter().filter(record)
    assert 'synthetic-private-token' not in record.getMessage()
