"""Temporary dev-only one-recipient smoke command; never imported by an API route."""
import argparse
import json
from uuid import UUID
import requests

from app.cloud.interview_sessions import _validate_supabase_url
from app.cloud.supabase_config import get_supabase_settings

from app.email.config import load_marketing_email_settings
from app.email.event_store import IDEMPOTENCY_KEY_RE, build_outbound_email_event_service
from app.email.marketing import MarketingEmailService
from app.email.provider import validate_recipient_email
from app.email.unsubscribe import build_marketing_unsubscribe_service


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Do not echo arbitrary argument values into output/logs.
        raise ValueError("Invalid smoke command arguments.")


def _safe_id(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def canonical_user_email(user_id: str) -> str:
    """Read the Auth-owned address; never trust editable profile metadata."""
    settings = get_supabase_settings().require_configured()
    if not settings.service_role_key or settings.service_role_key == settings.anon_key:
        raise ValueError("Trusted identity lookup is unavailable.")
    origin = _validate_supabase_url(settings.supabase_url)
    try:
        response = requests.get(
            f'{origin}/auth/v1/admin/users/{str(UUID(user_id))}',
            headers={'apikey': settings.service_role_key,
                     'Authorization': f'Bearer {settings.service_role_key}'},
            timeout=8, allow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError("Identity lookup failed.")
        user = response.json()
        if str(UUID(user.get('id', ''))) != user_id or not user.get('email_confirmed_at'):
            raise ValueError("Verified identity unavailable.")
        return validate_recipient_email(user.get('email', '')).strip().lower()
    except Exception:
        raise ValueError("Trusted identity lookup failed.") from None


def main(argv=None) -> int:
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--idempotency-key', required=True,
                        help='Reuse this key when checking/retrying the same smoke attempt.')
    mode = 'disabled'
    try:
        args = parser.parse_args(argv)
        user_id = str(UUID(args.user_id))
        email = validate_recipient_email(args.email)
        if not IDEMPOTENCY_KEY_RE.fullmatch(args.idempotency_key):
            raise ValueError("Invalid idempotency key.")
        settings = load_marketing_email_settings()
        mode = settings.provider_mode
        if not settings.live_delivery_requested:
            print(json.dumps({'status': 'blocked_live_flags', 'mode': mode}))
            return 2
        unsubscribe = build_marketing_unsubscribe_service()
        if not unsubscribe.is_marketing_allowed(user_id=user_id):
            print(json.dumps({'status': 'blocked_consent', 'mode': mode}))
            return 2
        canonical_email = canonical_user_email(user_id)
        if email.strip().lower() != canonical_email:
            print(json.dumps({'status': 'blocked_recipient_mismatch', 'mode': mode}))
            return 2
        service = MarketingEmailService(
            settings=settings,
            event_store=build_outbound_email_event_service(),
            unsubscribe_service=unsubscribe,
        )
        event = service.send_marketing_email(
            user_id=user_id, recipient_email=canonical_email, campaign_key='dev-smoke',
            template_key='product_update', idempotency_key=args.idempotency_key,
        )
        result = {
            'status': event.status if event.status in {'sent', 'canceled'} else 'incomplete',
            'event_id': _safe_id(event.id),
            'provider_message_id': _safe_id(event.provider_message_id),
            'mode': 'dry_run' if event.metadata_json.get('dry_run') is True else 'live',
        }
        print(json.dumps(result))
        return 0 if result['status'] == 'sent' else 2
    except Exception:
        # An exception may contain HTTP credentials or unsubscribe data. Never print it.
        print(json.dumps({'status': 'failed_check_event_before_retry', 'mode': mode}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
