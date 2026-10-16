"""Authenticated onboarding state; no browser-supplied ownership identifiers."""
from datetime import datetime, timezone
import requests
from app.cloud.supabase_config import get_supabase_settings

FIELDS = 'onboarding_current_step,onboarding_completed_at'
class OnboardingUnavailable(RuntimeError):
    pass

class OnboardingService:
    def __init__(self, session=None, settings=None):
        settings = settings or get_supabase_settings().require_configured()
        self.url = settings.supabase_url.rstrip('/') + '/rest/v1/user_settings'
        self.headers = {'apikey': settings.service_role_key, 'Authorization': 'Bearer ' + settings.service_role_key,
                        'Content-Type': 'application/json', 'Prefer': 'return=representation'}
        self.session = session or requests

    def request(self, user_id, changes=None, incomplete_only=False):
        params = {'user_id': 'eq.' + user_id, 'select': FIELDS}
        if incomplete_only: params['onboarding_completed_at'] = 'is.null'
        try:
            response = self.session.request('GET' if changes is None else 'PATCH', self.url,
                headers=self.headers, params=params, **({} if changes is None else {'json': changes}), timeout=10)
            if response.status_code not in (200, 201): raise OnboardingUnavailable()
            rows = response.json()
            if not isinstance(rows, list): raise OnboardingUnavailable()
            if not rows:
                if changes is not None and incomplete_only: return self.request(user_id)
                raise OnboardingUnavailable()
            row = rows[0]
            if not isinstance(row.get('onboarding_current_step'), int) or not 1 <= row['onboarding_current_step'] <= 5:
                raise OnboardingUnavailable()
            return {key: row.get(key) for key in FIELDS.split(',')}
        except (requests.RequestException, ValueError, KeyError, TypeError):
            raise OnboardingUnavailable() from None

    def read(self, user_id): return self.request(user_id)
    def step(self, user_id, step): return self.request(user_id, {'onboarding_current_step': step}, True)
    def complete(self, user_id):
        return self.request(user_id, {'onboarding_completed_at': datetime.now(timezone.utc).isoformat()}, True)
