"""Private, authorized cloud context for the opt-in realtime transport."""
import hashlib
import re
from dataclasses import dataclass
from uuid import UUID
from fastapi import HTTPException
from jwt.exceptions import ExpiredSignatureError
from starlette.requests import Request
from app.auth.supabase_auth import get_current_user
from app.cloud.interview_sessions import CloudInterviewSessionService
from app.cloud.cloud_resume import CloudResumeService
from app.cloud.cloud_job_context import CloudJobContextService
from app.cloud.interview_transcripts import CloudInterviewTranscriptService


class CloudContextRejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _id(value):
    try:
        return str(UUID(value)) if value else ''
    except (ValueError, TypeError):
        raise CloudContextRejected('cloud_session_invalid') from None


@dataclass
class GrpcCloudContext:
    request: Request
    session_id: str
    resume_id: str
    job_id: str
    user_id: str = ''

    @classmethod
    def authorize(cls, start, metadata):
        headers = [(str(key).lower().encode(), str(value).encode()) for key, value in metadata
                   if str(key).lower() == 'authorization']
        if len(headers) != 1:
            raise CloudContextRejected('auth_unavailable')
        request = Request({'type': 'http', 'headers': headers})
        result = cls(request, _id(start.active_session_id), _id(start.selected_resume_id), _id(start.selected_job_context_id))
        if not result.session_id:
            raise CloudContextRejected('cloud_session_invalid')
        result.load()
        request.state.grpc_cloud_context_only = True
        return result

    def load(self):
        try:
            user = get_current_user(self.request)
        except HTTPException as exc:
            cause = exc
            while cause is not None:
                if isinstance(cause, ExpiredSignatureError):
                    raise CloudContextRejected('token_expired') from None
                cause = cause.__cause__
            raise CloudContextRejected('auth_invalid' if exc.status_code == 401 else 'auth_unavailable') from None
        except Exception:
            raise CloudContextRejected('auth_unavailable') from None
        if self.user_id and self.user_id != user.user_id:
            raise CloudContextRejected('session_owner_mismatch')
        self.user_id = user.user_id
        try:
            session = CloudInterviewSessionService().get_session(user_id=user.user_id, session_id=self.session_id)
        except Exception:
            raise CloudContextRejected('cloud_session_invalid') from None
        if session.id != self.session_id:
            raise CloudContextRejected('cloud_session_invalid')
        if session.user_id != user.user_id:
            raise CloudContextRejected('session_owner_mismatch')
        if session.status != 'active':
            raise CloudContextRejected('cloud_session_ended')
        # Selected IDs must be the context of this authorized session, not substitutions.
        if self.resume_id and self.resume_id != session.selected_resume_id:
            raise CloudContextRejected('selected_context_forbidden')
        if self.job_id and self.job_id != session.job_context_id:
            raise CloudContextRejected('selected_context_forbidden')
        resume_id = session.selected_resume_id
        job_id = session.job_context_id
        try:
            if resume_id:
                CloudResumeService().get_status(user_id=user.user_id, resume_id=resume_id)
            job = CloudJobContextService().get_context(user_id=user.user_id, job_context_id=job_id) if job_id else None
        except Exception:
            raise CloudContextRejected('selected_context_forbidden') from None
        return dict(selected_resume_id=resume_id, target_role=session.target_role or '',
                    company_name=session.company_name or '',
                    job_description=job.job_description if job else session.job_description_preview or '',
                    profile={}, profile_context_used=bool(resume_id))

    def save(self, question, answer, category, provider, model):
        self.load()  # Recheck expiry/ownership/lifecycle before the cloud write.
        key = hashlib.sha256((self.session_id + '\0' + re.sub(r'[^\w]', '', question.casefold())).encode()).hexdigest()
        CloudInterviewTranscriptService().create_transcript_entry(
            user_id=self.user_id, session_id=self.session_id,
            payload={'request_id': 'grpc-' + key, 'source': 'auto', 'question_text': question,
                     'answer_text': answer, 'category': category, 'provider': provider,
                     'model': model or 'unknown', 'metadata': {}})
