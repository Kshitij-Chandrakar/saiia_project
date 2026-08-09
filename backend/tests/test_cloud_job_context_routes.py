from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import job_contexts as job_contexts_api
from app.auth.supabase_auth import AUTH_ERROR_DETAIL, get_auth_verification_config
from app.cloud.cloud_job_context import (
    CloudJobContextConflictError,
    CloudJobContextError,
    CloudJobContextExtractResult,
    CloudJobContextNotFoundError,
    CloudJobContextRateLimitError,
    CloudJobContextRecord,
    CloudJobContextValidationError,
    CreateJobContextResult,
    DeleteJobContextResult,
    JobContextListPage,
)
from app.cloud.supabase_config import (
    CLOUD_MODE_ENV,
    SUPABASE_REQUIRED_ENV_VARS,
    SupabaseConfigurationError,
    get_supabase_settings,
)

TEST_SECRET = "unit-test-jwt-secret"
TEST_USER_ID = "00000000-0000-4000-8000-000000000001"
TEST_ISSUER = "https://project-ref.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"
CONTEXT_ID = "20000000-0000-4000-8000-000000000001"
RAW_JD = "PRIVATE RAW JD TEXT with compensation and internal notes"


def _record(**overrides: object) -> CloudJobContextRecord:
    payload = {
        "id": CONTEXT_ID,
        "user_id": TEST_USER_ID,
        "company": "Acme",
        "position": "Backend Engineer",
        "job_description": RAW_JD,
        "required_skills": ["Python"],
        "responsibilities": ["Build APIs"],
        "seniority": "Senior",
        "domain_keywords": ["SaaS"],
        "location": "Remote",
        "employment_type": "Full-time",
        "source_file_metadata": {"filename": "jd.txt", "mime_type": "text/plain", "byte_size": "12", "source": "upload"},
        "is_active": False,
        "created_at": "2026-08-09T00:00:00Z",
        "updated_at": "2026-08-09T00:00:00Z",
    }
    payload.update(overrides)
    return CloudJobContextRecord(**payload)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def clear_supabase_auth_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(CLOUD_MODE_ENV, raising=False)
    for name in SUPABASE_REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    yield
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    job_contexts_api._cached_cloud_job_context_service.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    monkeypatch.setenv("SUPABASE_URL", "https://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-unit-test-value")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-unit-test-value")
    monkeypatch.setenv("SUPABASE_JWT_SECRET_OR_JWKS_CONFIG", TEST_SECRET)
    monkeypatch.setenv("SUPABASE_RESUME_BUCKET", "resumes")
    monkeypatch.setenv("SUPABASE_EXPORT_BUCKET", "exports")
    get_supabase_settings.cache_clear()
    get_auth_verification_config.cache_clear()
    app = FastAPI()
    app.include_router(job_contexts_api.router, prefix="/api/job-contexts")
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _token(*, subject: str = TEST_USER_ID, secret: str = TEST_SECRET) -> str:
    return jwt.encode(
        {
            "iss": TEST_ISSUER,
            "aud": TEST_AUDIENCE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "iat": datetime.now(timezone.utc),
            "sub": subject,
            "email": "user@example.com",
            "role": "authenticated",
        },
        secret,
        algorithm="HS256",
    )


class FakeJobContextService:
    def __init__(self) -> None:
        self.user_ids: list[str] = []
        self.idempotency_keys: list[str] = []
        self.extract_calls = 0
        self.last_create_payload: dict[str, Any] | None = None

    def list_contexts(self, *, user_id: str, limit: int, cursor: str | None):
        self.user_ids.append(user_id)
        return JobContextListPage(items=[_record(user_id=user_id, is_active=True)], active_id=CONTEXT_ID, limit=limit, next_cursor=None)

    def create_context(self, *, user_id: str, payload: dict[str, Any], idempotency_key: str):
        self.user_ids.append(user_id)
        self.idempotency_keys.append(idempotency_key)
        self.last_create_payload = payload
        return CreateJobContextResult(record=_record(user_id=user_id, is_active=bool(payload.get("activate"))), replayed=False, activated=bool(payload.get("activate")))

    def get_context(self, *, user_id: str, job_context_id: str):
        self.user_ids.append(user_id)
        return _record(user_id=user_id, id=job_context_id)

    def update_context(self, *, user_id: str, job_context_id: str, payload: dict[str, Any]):
        self.user_ids.append(user_id)
        return _record(user_id=user_id, id=job_context_id, company=payload.get("company") or "Acme")

    def delete_context(self, *, user_id: str, job_context_id: str):
        self.user_ids.append(user_id)
        return DeleteJobContextResult(job_context_id=job_context_id, deleted=True, active_id=None)

    def activate_context(self, *, user_id: str, job_context_id: str):
        self.user_ids.append(user_id)
        return _record(user_id=user_id, id=job_context_id, is_active=True)

    def extract_from_text(self, *, user_id: str, job_description_text: str):
        self.user_ids.append(user_id)
        self.extract_calls += 1
        return CloudJobContextExtractResult(
            company="Acme",
            position="Backend Engineer",
            job_description=job_description_text,
            job_description_summary="Backend role summary",
            required_skills=["Python"],
            responsibilities=["Build APIs"],
            seniority="",
            domain_keywords=[],
            location="",
            employment_type="",
            source_file_metadata={"source": "paste"},
            extraction_receipt_id="receipt-1",
            extracted_text_length=len(job_description_text),
        )

    def extract_from_file(self, *, user_id: str, filename: str, content: bytes, content_type: str | None):
        self.user_ids.append(user_id)
        self.extract_calls += 1
        return self.extract_from_text(user_id=user_id, job_description_text=content.decode("utf-8"))


@pytest.fixture
def fake_service(client: TestClient) -> FakeJobContextService:
    service = FakeJobContextService()
    client.app.dependency_overrides[job_contexts_api.get_cloud_job_context_service] = lambda: service
    return service


def test_cloud_job_context_routes_require_jwt(client: TestClient) -> None:
    response = client.get("/api/job-contexts")

    assert response.status_code == 401
    assert response.json() == {"detail": AUTH_ERROR_DETAIL}


def test_list_returns_preview_only_and_bounds_limit(client: TestClient, fake_service: FakeJobContextService) -> None:
    response = client.get("/api/job-contexts?limit=50", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    body = response.json()
    assert body["active_id"] == CONTEXT_ID
    assert body["items"][0]["job_description_preview"] == RAW_JD
    assert body["items"][0]["job_description_length"] == len(RAW_JD)
    assert "job_description" not in body["items"][0]
    assert "source_file_metadata" not in body["items"][0]
    assert fake_service.user_ids == [TEST_USER_ID]


def test_detail_returns_raw_jd_for_owner(client: TestClient, fake_service: FakeJobContextService) -> None:
    response = client.get(f"/api/job-contexts/{CONTEXT_ID}", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 200
    assert response.json()["job_description"] == RAW_JD
    assert response.json()["source_file_metadata"]["filename"] == "jd.txt"
    assert fake_service.user_ids == [TEST_USER_ID]


def test_create_requires_idempotency_key_and_uses_verified_user(client: TestClient, fake_service: FakeJobContextService) -> None:
    payload = {"company": "Acme", "job_description": RAW_JD, "activate": True}

    missing = client.post("/api/job-contexts", headers={"Authorization": f"Bearer {_token()}"}, json=payload)
    response = client.post(
        "/api/job-contexts",
        headers={"Authorization": f"Bearer {_token()}", "Idempotency-Key": "create:1"},
        json={**payload, "user_id": "11111111-1111-4111-8111-111111111111"},
    )

    assert missing.status_code == 400
    assert response.status_code == 422
    assert fake_service.user_ids == []

    valid = client.post(
        "/api/job-contexts",
        headers={"Authorization": f"Bearer {_token()}", "Idempotency-Key": "create:2"},
        json=payload,
    )
    assert valid.status_code == 201
    assert fake_service.user_ids == [TEST_USER_ID]
    assert fake_service.idempotency_keys == ["create:2"]
    assert valid.json()["activated"] is True
    assert "job_description" not in valid.json()["job_context"]


def test_create_rejects_client_source_file_metadata(client: TestClient, fake_service: FakeJobContextService) -> None:
    response = client.post(
        "/api/job-contexts",
        headers={"Authorization": f"Bearer {_token()}", "Idempotency-Key": "create:metadata"},
        json={"company": "Acme", "source_file_metadata": {"filename": "evil.txt"}},
    )

    assert response.status_code == 422
    assert fake_service.user_ids == []


def test_update_delete_and_activate_are_user_owned(client: TestClient, fake_service: FakeJobContextService) -> None:
    headers = {"Authorization": f"Bearer {_token()}"}

    patch = client.patch(f"/api/job-contexts/{CONTEXT_ID}", headers=headers, json={"company": "Updated"})
    delete = client.delete(f"/api/job-contexts/{CONTEXT_ID}", headers=headers)
    activate = client.post(f"/api/job-contexts/{CONTEXT_ID}/activate", headers=headers)

    assert patch.status_code == 200
    assert patch.json()["company"] == "Updated"
    assert "job_description" not in patch.json()
    assert delete.status_code == 200
    assert delete.json()["active_id"] is None
    assert activate.status_code == 200
    assert activate.json()["is_active"] is True
    assert fake_service.user_ids == [TEST_USER_ID, TEST_USER_ID, TEST_USER_ID]


def test_extract_requires_consent_and_rejects_dual_source_before_service_call(
    client: TestClient,
    fake_service: FakeJobContextService,
) -> None:
    headers = {"Authorization": f"Bearer {_token()}"}

    no_consent = client.post("/api/job-contexts/extract", headers=headers, data={"job_description_text": RAW_JD})
    dual_source = client.post(
        "/api/job-contexts/extract",
        headers=headers,
        data={"job_description_text": RAW_JD, "provider_processing_consent": "true"},
        files={"file": ("jd.txt", b"file jd", "text/plain")},
    )

    assert no_consent.status_code == 400
    assert dual_source.status_code == 400
    assert fake_service.extract_calls == 0


def test_extract_rejects_client_submitted_source_metadata(client: TestClient, fake_service: FakeJobContextService) -> None:
    response = client.post(
        "/api/job-contexts/extract",
        headers={"Authorization": f"Bearer {_token()}"},
        data={
            "job_description_text": RAW_JD,
            "provider_processing_consent": "true",
            "source_file_metadata": '{"filename":"client.txt"}',
        },
    )

    assert response.status_code == 400
    assert fake_service.extract_calls == 0


def test_extract_success_can_return_raw_jd_and_receipt(client: TestClient, fake_service: FakeJobContextService) -> None:
    response = client.post(
        "/api/job-contexts/extract",
        headers={"Authorization": f"Bearer {_token()}"},
        data={"job_description_text": RAW_JD, "provider_processing_consent": "true"},
    )

    assert response.status_code == 200
    assert response.json()["job_description"] == RAW_JD
    assert response.json()["extraction_receipt_id"] == "receipt-1"
    assert fake_service.extract_calls == 1


def test_route_errors_are_safe_and_do_not_echo_raw_jd(client: TestClient) -> None:
    class RaisingService(FakeJobContextService):
        def get_context(self, *, user_id: str, job_context_id: str):
            raise CloudJobContextError(f"backend failed while handling {RAW_JD}")

    service = RaisingService()
    client.app.dependency_overrides[job_contexts_api.get_cloud_job_context_service] = lambda: service

    response = client.get(f"/api/job-contexts/{CONTEXT_ID}", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == 502
    assert response.json() == {"detail": "Supabase cloud job context operation failed."}
    assert RAW_JD not in response.text


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_detail"),
    [
        (CloudJobContextValidationError("bad request"), 400, "bad request"),
        (CloudJobContextNotFoundError("missing"), 404, "Job context was not found."),
        (CloudJobContextConflictError("stale"), 409, "stale"),
        (CloudJobContextRateLimitError("quota"), 429, "Job description extraction quota exceeded."),
        (SupabaseConfigurationError("missing config"), 503, "Supabase cloud configuration is not ready."),
        (TypeError("boom"), 502, "Supabase cloud job context operation failed."),
    ],
)
def test_cloud_job_context_error_mapping(
    client: TestClient,
    exc: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    class RaisingService(FakeJobContextService):
        def list_contexts(self, *, user_id: str, limit: int, cursor: str | None):
            raise exc

    client.app.dependency_overrides[job_contexts_api.get_cloud_job_context_service] = lambda: RaisingService()

    response = client.get("/api/job-contexts", headers={"Authorization": f"Bearer {_token()}"})

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert RAW_JD not in response.text
