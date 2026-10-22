"""Server-owned canonical answer identity; never trust client transcript metadata."""
from functools import lru_cache
import logging

import requests

logger = logging.getLogger('answer_diagrams')

from app.cloud.supabase_config import get_supabase_settings, SupabaseConfigurationError


class DiagramError(Exception):
    def __init__(self, code='unavailable', status=503):
        self.code, self.status = code, status
        super().__init__(code)


class DiagramStore:
    def __init__(self):
        config = get_supabase_settings().require_configured()
        if config.service_role_key == config.anon_key:
            raise DiagramError('configuration_missing')
        self.url = config.supabase_url.rstrip('/') + '/rest/v1'
        self.headers = {'apikey': config.service_role_key, 'Authorization': 'Bearer ' + config.service_role_key}

    def request(self, method, path, **kwargs):
        stage = ('source_provenance' if path == '/interview_answer_sources' else
                 'diagram_storage' if path in {'/interview_answer_diagrams', '/rpc/answer_diagram_operation'} else
                 'canonical_transcript')
        try:
            response = requests.request(method, self.url + path, headers=self.headers, timeout=(3, 8), **kwargs)
            if response.status_code >= 300:
                try:
                    code = response.json().get('code')
                except (ValueError, AttributeError):
                    code = None
                if not isinstance(code, str):
                    code = None
                missing = stage != 'canonical_transcript' and code in {'PGRST205', 'PGRST202', '42P01'}
                # Never log URLs, identifiers, headers, provider/DB messages or content.
                logger.warning('Diagram storage failure stage=%s status=%s code=%s',
                    stage, response.status_code, code if code in {'PGRST205', 'PGRST202', '42P01', '42501'} else 'other')
                if missing:
                    raise DiagramError('schema_unavailable')
                raise DiagramError()
            return response.json()
        except (requests.RequestException, ValueError):
            logger.warning('Diagram storage failure stage=%s code=transport_or_response', stage)
            raise DiagramError() from None

    def source(self, user, session, *, transcript=None, request=None):
        params = {'select': 'id,session_id,question_text,answer_text,source', 'user_id': 'eq.' + user,
                  'session_id': 'eq.' + session, 'limit': '1'}
        params.update({'id': 'eq.' + transcript} if transcript else {'request_id': 'eq.' + request})
        rows = self.request('GET', '/interview_session_transcript_entries', params=params)
        if not rows:
            raise DiagramError('source_not_found', 404) if transcript else DiagramError('source_pending', 202)
        row = rows[0]
        sources = self.request('GET', '/interview_answer_sources', params={
            'select': 'source_revision,answer_type,provenance', 'transcript_id': 'eq.' + row['id'],
            'user_id': 'eq.' + user, 'session_id': 'eq.' + session, 'limit': '1'})
        trusted = sources[0] if sources else {}
        eligible = trusted.get('answer_type') == 'system_design' and row['source'] in ('answer', 'auto', 'chat')
        descriptor = dict(transcript_id=row['id'], session_id=session,
                          source_revision=trusted.get('source_revision'), answer_type=trusted.get('answer_type'),
                          provenance=trusted.get('provenance'), eligible=eligible,
                          reason=None if eligible else 'unverified_source')
        return descriptor, row

    def operation(self, operation, user, session, transcript, revision, operation_id=None, **kwargs):
        result = self.request('POST', '/rpc/answer_diagram_operation', json=dict(
            p_operation=operation, p_user_id=user, p_session_id=session, p_transcript_id=transcript,
            p_revision=revision, p_operation_id=operation_id, **{'p_' + k: v for k, v in kwargs.items()}))
        if result.get('error'):
            raise DiagramError(result['error'] if result['error'] in {
                'source_not_found', 'ineligible_source', 'stale_source', 'stale_operation'} else 'unavailable', 409)
        return result


def diagram_projection(row):
    """Only this projection crosses the backend boundary; fences stay private."""
    state = row.get('state', 'absent')
    return dict(state=state, attempt=row.get('attempt', 0), operation_id=row.get('operation_id'),
                graph_schema=row.get('graph_schema', 1),
                source_revision=row.get('source_revision'),
                graph=row.get('graph') if state == 'ready' else None,
                failure_code=row.get('failure_code'), retry_allowed=state == 'failed' and row.get('attempt') == 1)


@lru_cache(maxsize=1)
def diagram_store():
    try:
        return DiagramStore()
    except SupabaseConfigurationError:
        raise DiagramError('configuration_missing') from None
