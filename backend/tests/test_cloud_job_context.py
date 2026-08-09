import base64
import json

import pytest

from app.cloud.cloud_job_context import (
    CloudJobContextConflictError,
    CloudJobContextRateLimitError,
    CloudJobContextService,
    CloudJobContextValidationError,
    ExtractionLimiter,
    ExtractionReceiptStore,
    JobContextListPage,
    MAX_ARRAY_ITEMS,
    MAX_JOB_DESCRIPTION_PREVIEW_CHARS,
    build_source_file_metadata,
    decode_cursor,
    encode_cursor,
    job_description_preview,
    normalize_job_context_payload,
    normalized_payload_hash,
    SupabaseCloudJobContextClient,
    validate_idempotency_key,
)
from app.cloud.supabase_config import CLOUD_MODE_ENV, get_supabase_settings

RAW_JD = "This is a private job description for a backend engineer. Python and FastAPI are required."


class FakeClient:
    def __init__(self) -> None:
        self.create_calls = []

    def create_context(self, **kwargs):
        self.create_calls.append(kwargs)

        class Result:
            record = kwargs
            replayed = False
            activated = bool(kwargs["payload"].get("activate"))

        return Result()


class FakeLocalJobContext:
    def __init__(self) -> None:
        self.provider_calls = 0

    def build_context_fields(self, raw_text: str):
        self.provider_calls += 1
        return {
            "company_name": "Acme",
            "target_role": "Backend Engineer",
            "job_description": "Short summary",
            "required_skills": "Python, FastAPI",
            "responsibilities": "Build APIs\nOwn services",
        }

    def extract_text(self, *, filename: str, content: bytes) -> str:
        return content.decode("utf-8")


def test_idempotency_key_validation_rejects_invalid_values() -> None:
    assert validate_idempotency_key("create:abc-123_OK") == "create:abc-123_OK"

    for key in ("", "x" * 81, "bad key", "snowman-☃"):
        with pytest.raises(CloudJobContextValidationError):
            validate_idempotency_key(key)


def test_payload_normalization_bounds_arrays_and_rejects_source_metadata() -> None:
    payload = normalize_job_context_payload(
        {
            "company": " Acme ",
            "required_skills": ["Python", "Python", " FastAPI "],
            "job_description": RAW_JD,
        }
    )

    assert payload["company"] == "Acme"
    assert payload["required_skills"] == ["Python", "FastAPI"]

    with pytest.raises(CloudJobContextValidationError):
        normalize_job_context_payload({"source_file_metadata": {"filename": "client.txt"}})
    with pytest.raises(CloudJobContextValidationError):
        normalize_job_context_payload({"required_skills": [str(i) for i in range(MAX_ARRAY_ITEMS + 1)]})


def test_payload_hash_includes_server_metadata_without_exposing_raw_jd_storage() -> None:
    payload = normalize_job_context_payload({"company": "Acme", "job_description": RAW_JD})
    first = normalized_payload_hash(payload, {"source": "paste"})
    second = normalized_payload_hash(payload, {"source": "upload", "filename": "jd.txt"})

    assert first != second
    assert len(first) == 64


def test_cursor_round_trip_and_preview_bound() -> None:
    cursor = encode_cursor("2026-08-09T00:00:00Z", "20000000-0000-4000-8000-000000000001")

    assert decode_cursor(cursor) == ("2026-08-09T00:00:00Z", "20000000-0000-4000-8000-000000000001")
    assert len(job_description_preview("x" * 500)) == MAX_JOB_DESCRIPTION_PREVIEW_CHARS


def _cursor_payload(value: object) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@pytest.mark.parametrize(
    "cursor",
    [
        "!!!!",
        base64.urlsafe_b64encode(b"not json").decode("ascii").rstrip("="),
        _cursor_payload(["not", "a", "dict"]),
        _cursor_payload({"updated_at": "2026-08-09T00:00:00Z"}),
        _cursor_payload({"id": "20000000-0000-4000-8000-000000000001"}),
        _cursor_payload({"updated_at": "2026-08-09T00:00:00Z\nor=true", "id": "20000000-0000-4000-8000-000000000001"}),
        _cursor_payload({"updated_at": "2026-08-09T00:00:00Z", "id": "id);drop table"}),
    ],
)
def test_decode_cursor_rejects_malformed_non_dict_missing_and_unsafe_payloads(cursor: str) -> None:
    with pytest.raises(CloudJobContextValidationError):
        decode_cursor(cursor)


def test_source_file_metadata_is_server_derived_and_validated() -> None:
    metadata = build_source_file_metadata(
        filename="../Unsafe JD.txt",
        content=b"hello",
        content_type="text/plain",
        source="upload",
    )

    assert metadata == {
        "filename": "Unsafe JD.txt",
        "mime_type": "text/plain",
        "byte_size": "5",
        "source": "upload",
    }
    with pytest.raises(CloudJobContextValidationError):
        build_source_file_metadata(
            filename="jd.txt",
            content=b"hello",
            content_type="application/pdf",
            source="upload",
        )


def test_extraction_quota_blocks_provider_call() -> None:
    local = FakeLocalJobContext()
    service = CloudJobContextService(
        client=FakeClient(),
        local_job_context=local,  # type: ignore[arg-type]
        limiter=ExtractionLimiter(max_calls=0),
    )

    with pytest.raises(CloudJobContextRateLimitError):
        service.extract_from_text(user_id="user-1", job_description_text=RAW_JD)

    assert local.provider_calls == 0


def test_extraction_limiter_prunes_expired_entries_and_deletes_empty_users(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = ExtractionLimiter(max_calls=1, window_seconds=10)
    times = iter([100.0, 111.0])
    monkeypatch.setattr("app.cloud.cloud_job_context.time.time", lambda: next(times))

    limiter.consume("user-1")
    assert "user-1" in limiter._calls
    limiter.consume("user-2")

    assert "user-1" not in limiter._calls
    assert "user-2" in limiter._calls


class OpenCircuit:
    def __init__(self) -> None:
        self.checked = 0

    def ensure_available(self) -> None:
        self.checked += 1
        raise CloudJobContextConflictError("circuit open")

    def record_success(self) -> None:
        raise AssertionError("provider should not run")

    def record_failure(self) -> None:
        raise AssertionError("provider should not run")


class CountingLimiter:
    def __init__(self) -> None:
        self.calls = 0

    def consume(self, user_id: str) -> None:
        self.calls += 1


def test_circuit_open_does_not_consume_extraction_quota() -> None:
    local = FakeLocalJobContext()
    limiter = CountingLimiter()
    circuit = OpenCircuit()
    service = CloudJobContextService(
        client=FakeClient(),
        local_job_context=local,  # type: ignore[arg-type]
        limiter=limiter,  # type: ignore[arg-type]
        circuit_breaker=circuit,  # type: ignore[arg-type]
    )

    with pytest.raises(CloudJobContextConflictError):
        service.extract_from_text(user_id="user-1", job_description_text=RAW_JD)

    assert circuit.checked == 1
    assert limiter.calls == 0
    assert local.provider_calls == 0


def test_cloud_extraction_returns_raw_jd_and_receipt_without_saving() -> None:
    local = FakeLocalJobContext()
    service = CloudJobContextService(
        client=FakeClient(),
        local_job_context=local,  # type: ignore[arg-type]
        receipt_store=ExtractionReceiptStore(),
        limiter=ExtractionLimiter(max_calls=10),
    )

    result = service.extract_from_text(user_id="user-1", job_description_text=RAW_JD)

    assert result.job_description == RAW_JD
    assert result.job_description_summary == "Short summary"
    assert result.required_skills == ["Python", "FastAPI"]
    assert result.responsibilities == ["Build APIs", "Own services"]
    assert result.source_file_metadata == {"source": "paste"}
    assert result.extraction_receipt_id
    assert local.provider_calls == 1


def test_create_uses_receipt_metadata_and_atomic_idempotency_inputs() -> None:
    client = FakeClient()
    receipt_store = ExtractionReceiptStore()
    receipt_id = receipt_store.create(
        user_id="user-1",
        job_description=RAW_JD,
        source_file_metadata={"source": "upload", "filename": "jd.txt"},
    )
    service = CloudJobContextService(client=client, receipt_store=receipt_store)

    service.create_context(
        user_id="user-1",
        payload={"company": "Acme", "job_description": RAW_JD, "extraction_receipt_id": receipt_id},
        idempotency_key="create:receipt",
    )

    assert client.create_calls[0]["source_file_metadata"] == {"source": "upload", "filename": "jd.txt"}
    assert client.create_calls[0]["idempotency_key"] == "create:receipt"
    assert len(client.create_calls[0]["request_hash"]) == 64

    with pytest.raises(CloudJobContextValidationError):
        service.create_context(
            user_id="user-2",
            payload={"company": "Acme", "job_description": RAW_JD, "extraction_receipt_id": receipt_id},
            idempotency_key="create:receipt-2",
        )


def test_list_limit_is_bounded_before_client_call() -> None:
    class EmptyClient:
        def list_contexts(self, *, user_id: str, limit: int, cursor: str | None):
            return []

    service = CloudJobContextService(client=EmptyClient())
    assert service.list_contexts(user_id="user-1", limit=50, cursor=None) == JobContextListPage(
        items=[],
        active_id=None,
        limit=50,
        next_cursor=None,
    )
    with pytest.raises(CloudJobContextValidationError):
        service.list_contexts(user_id="user-1", limit=51, cursor=None)


def test_supabase_job_context_client_rejects_non_https_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    monkeypatch.setenv("SUPABASE_URL", "http://project-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-unit-test-value")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-unit-test-value")
    monkeypatch.setenv("SUPABASE_JWT_SECRET_OR_JWKS_CONFIG", "unit-test-secret")
    monkeypatch.setenv("SUPABASE_RESUME_BUCKET", "resumes")
    monkeypatch.setenv("SUPABASE_EXPORT_BUCKET", "exports")
    get_supabase_settings.cache_clear()
    try:
        with pytest.raises(Exception, match="HTTPS"):
            SupabaseCloudJobContextClient()
    finally:
        get_supabase_settings.cache_clear()


def test_supabase_job_context_client_allows_local_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CLOUD_MODE_ENV, "cloud")
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-unit-test-value")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-unit-test-value")
    monkeypatch.setenv("SUPABASE_JWT_SECRET_OR_JWKS_CONFIG", "unit-test-secret")
    monkeypatch.setenv("SUPABASE_RESUME_BUCKET", "resumes")
    monkeypatch.setenv("SUPABASE_EXPORT_BUCKET", "exports")
    get_supabase_settings.cache_clear()
    try:
        client = SupabaseCloudJobContextClient()
    finally:
        get_supabase_settings.cache_clear()

    assert client._rest_url == "http://localhost:54321/rest/v1"
