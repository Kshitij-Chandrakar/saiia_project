import pytest
import requests

from app.nlp.answer_generator import ProviderError
from app.services.affinda_resume_parser import AffindaResumeParserError
from app.services.resume_parser_service import ResumeParserService
from app.services import resume_parser_service as resume_parser_module
from app.cloud.cloud_resume import (
    CloudResumeConflictError,
    CloudResumeError,
    CloudResumeNotFoundError,
    CloudResumeRecord,
    CloudResumeService,
    SUPABASE_ACTIVE_CHUNK_HARD_LIMIT,
    SUPABASE_ACTIVE_CHUNK_PAGE_SIZE,
    SUPABASE_HTTP_POOL_SIZE,
    SUPABASE_SELECT_ATTEMPT_TIMEOUT,
    SupabaseCloudResumeClient,
    CloudResumeValidationError,
    sanitize_resume_filename,
    validate_confirmed_profile,
    validate_resume_upload,
)

USER_A = "00000000-0000-4000-8000-000000000001"
USER_B = "00000000-0000-4000-8000-000000000002"
RESUME_ID = "10000000-0000-4000-8000-000000000001"
ALLOWED_TEST_INDEX_STATUSES = {"not_indexed", "pending", "indexed", "failed", "needs_rebuild"}


def test_supabase_client_configures_blocking_http_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-unit-test-value")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-unit-test-value")
    monkeypatch.setenv("SUPABASE_JWT_SECRET_OR_JWKS_CONFIG", "unit-test-jwt-secret")
    monkeypatch.setenv("SUPABASE_RESUME_BUCKET", "resumes")
    monkeypatch.setenv("SUPABASE_EXPORT_BUCKET", "exports")

    client = SupabaseCloudResumeClient()

    for prefix in ("https://", "http://"):
        adapter = client._session.adapters[prefix]
        assert adapter._pool_connections == SUPABASE_HTTP_POOL_SIZE
        assert adapter._pool_maxsize == SUPABASE_HTTP_POOL_SIZE
        assert adapter._pool_block is True


def _record(**overrides: object) -> CloudResumeRecord:
    payload = {
        "id": RESUME_ID,
        "user_id": USER_A,
        "storage_path": f"{USER_A}/{RESUME_ID}/resume.txt",
        "original_filename": "resume.txt",
        "mime_type": "text/plain",
        "file_size": 12,
        "status": "uploaded",
        "is_active": False,
        "extraction_attempt": 0,
    }
    payload.update(overrides)
    return CloudResumeRecord(**payload)  # type: ignore[arg-type]


def _matches_inactive_generation(
    chunk: dict[str, object],
    user_id: str,
    resume_id: str,
    active_generation_id: str,
) -> bool:
    if chunk["user_id"] != user_id or chunk["resume_id"] != resume_id:
        return False

    generation_id = chunk.get("generation_id")
    if generation_id is None:
        return True

    return generation_id not in {active_generation_id}


class FakeCloudResumeClient:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], CloudResumeRecord] = {}
        self.objects: dict[str, bytes] = {}
        self.inserts: list[dict[str, object]] = []
        self.uploads: list[tuple[str, bytes, str]] = []
        self.compare_calls: list[dict[str, object]] = []
        self.updates: list[dict[str, object]] = []
        self.chunk_inserts: list[list[dict[str, object]]] = []
        self.chunk_deletes: list[dict[str, object]] = []
        self.chunks: list[dict[str, object]] = []
        self.profiles: dict[str, dict[str, object]] = {}
        self.fail_upload = False
        self.fail_chunk_insert = False
        self.fail_activation = False
        self.fail_chunk_delete = False
        self.activation_error: Exception | None = None

    def insert_resume_metadata(self, payload: dict[str, object]) -> CloudResumeRecord:
        self.inserts.append(payload)
        record = _record(**payload)
        self.records[(record.user_id, record.id)] = record
        return record

    def upload_resume_object(self, storage_path: str, content: bytes, mime_type: str) -> None:
        if self.fail_upload:
            raise CloudResumeError("storage failed")
        self.uploads.append((storage_path, content, mime_type))
        self.objects[storage_path] = content

    def download_resume_object(self, storage_path: str) -> bytes:
        try:
            return self.objects[storage_path]
        except KeyError as exc:
            raise CloudResumeError("storage download failed") from exc

    def delete_resume_object(self, storage_path: str) -> None:
        self.objects.pop(storage_path, None)

    def get_resume(self, resume_id: str, user_id: str) -> CloudResumeRecord:
        try:
            return self.records[(user_id, resume_id)]
        except KeyError as exc:
            raise CloudResumeNotFoundError("Resume was not found.") from exc

    def get_current_resume(self, user_id: str) -> CloudResumeRecord | None:
        candidates = [
            record
            for (record_user_id, _), record in self.records.items()
            if record_user_id == user_id and record.status == "ready" and record.is_active
        ]
        return candidates[0] if candidates else None

    def get_review_candidate(self, user_id: str) -> CloudResumeRecord | None:
        candidates = [
            record
            for (record_user_id, _), record in self.records.items()
            if record_user_id == user_id and record.status == "needs_review" and not record.confirmed_at
        ]
        return candidates[0] if candidates else None

    def update_resume(self, resume_id: str, user_id: str, payload: dict[str, object]) -> CloudResumeRecord:
        self.updates.append({"resume_id": resume_id, "user_id": user_id, "payload": payload})
        if "index_status" in payload and payload["index_status"] not in ALLOWED_TEST_INDEX_STATUSES:
            raise CloudResumeError("index status check constraint failed")
        current = self.records[(user_id, resume_id)]
        updated = _record(**{**current.__dict__, **payload})
        self.records[(user_id, resume_id)] = updated
        return updated

    def insert_resume_chunks(self, chunks: list[dict[str, object]]) -> None:
        if self.fail_chunk_insert:
            raise CloudResumeError("chunk insert failed with raw text: SECRET RESUME BODY")
        self.chunk_inserts.append(chunks)
        self.chunks.extend(chunks)

    def delete_resume_chunks(self, *, user_id: str, resume_id: str, generation_id: str | None = None) -> None:
        self.chunk_deletes.append({"user_id": user_id, "resume_id": resume_id, "generation_id": generation_id})
        if self.fail_chunk_delete:
            raise CloudResumeError("chunk delete failed with raw text: SECRET RESUME BODY")
        self.chunks = [
            chunk
            for chunk in self.chunks
            if not (
                chunk["user_id"] == user_id
                and chunk["resume_id"] == resume_id
                and (generation_id is None or chunk["generation_id"] == generation_id)
            )
        ]

    def delete_inactive_resume_chunks(self, *, user_id: str, resume_id: str, active_generation_id: str) -> None:
        self.chunk_deletes.append(
            {"user_id": user_id, "resume_id": resume_id, "active_generation_id": active_generation_id}
        )
        if self.fail_chunk_delete:
            raise CloudResumeError("chunk prune failed with raw text: SECRET RESUME BODY")
        self.chunks = [
            chunk
            for chunk in self.chunks
            if not _matches_inactive_generation(chunk, user_id, resume_id, active_generation_id)
        ]

    def activate_resume(
        self,
        *,
        user_id: str,
        resume_id: str,
        extraction_attempt: int,
        generation_id: str,
        confirmed_profile: dict[str, object],
    ) -> CloudResumeRecord:
        if self.activation_error is not None:
            raise self.activation_error
        if self.fail_activation:
            raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")
        current = self.records[(user_id, resume_id)]
        if current.status != "indexing" or current.extraction_attempt != extraction_attempt:
            raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")
        if current.confirmed_profile != confirmed_profile:
            raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")
        for (record_user_id, record_id), record in list(self.records.items()):
            if record_user_id == user_id and record_id != resume_id and record.is_active:
                self.records[(record_user_id, record_id)] = _record(**{**record.__dict__, "is_active": False})
        self.profiles[user_id] = dict(confirmed_profile)
        updated = _record(
            **{
                **current.__dict__,
                "status": "ready",
                "is_active": True,
                "index_status": "indexed",
                "active_chunk_generation": generation_id,
                "failure_code": None,
                "failure_message": None,
            }
        )
        self.records[(user_id, resume_id)] = updated
        return updated

    def activate_rebuilt_resume_generation(
        self,
        *,
        user_id: str,
        resume_id: str,
        expected_active_generation: str,
        new_generation_id: str,
    ) -> CloudResumeRecord:
        current = self.records[(user_id, resume_id)]
        if (
            current.status != "ready"
            or not current.is_active
            or current.active_chunk_generation != expected_active_generation
        ):
            raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")
        updated = _record(
            **{
                **current.__dict__,
                "index_status": "indexed",
                "active_chunk_generation": new_generation_id,
                "failure_code": None,
                "failure_message": None,
                "failed_at": None,
                "last_error_at": None,
            }
        )
        self.records[(user_id, resume_id)] = updated
        return updated

    def get_active_resume_chunks(self, *, user_id: str, resume_id: str, generation_id: str) -> list[dict[str, object]]:
        return [
            chunk
            for chunk in self.chunks
            if chunk["user_id"] == user_id
            and chunk["resume_id"] == resume_id
            and chunk["generation_id"] == generation_id
        ]

    def compare_and_set_resume(
        self,
        resume_id: str,
        user_id: str,
        from_statuses: set[str],
        payload: dict[str, object],
        *,
        extraction_attempt: int | None = None,
    ) -> CloudResumeRecord:
        self.compare_calls.append(
            {
                "resume_id": resume_id,
                "user_id": user_id,
                "from_statuses": from_statuses,
                "payload": payload,
                "extraction_attempt": extraction_attempt,
            }
        )
        current = self.records[(user_id, resume_id)]
        if current.status not in from_statuses:
            raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")
        if extraction_attempt is not None and current.extraction_attempt != extraction_attempt:
            raise CloudResumeConflictError("Resume state changed. Please refresh and try again.")
        updated = _record(**{**current.__dict__, **payload})
        self.records[(user_id, resume_id)] = updated
        return updated


def test_fake_inactive_chunk_prune_removes_null_and_old_generations_for_same_resume_only() -> None:
    client = FakeCloudResumeClient()
    client.chunks.extend(
        [
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": "active-generation",
                "chunk_text": "active chunk",
            },
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": "old-generation",
                "chunk_text": "old chunk",
            },
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": None,
                "chunk_text": "null generation chunk",
            },
            {
                "user_id": USER_B,
                "resume_id": RESUME_ID,
                "generation_id": "old-generation",
                "chunk_text": "other user old chunk",
            },
            {
                "user_id": USER_B,
                "resume_id": RESUME_ID,
                "generation_id": None,
                "chunk_text": "other user null chunk",
            },
            {
                "user_id": USER_A,
                "resume_id": "other-resume",
                "generation_id": "old-generation",
                "chunk_text": "other resume old chunk",
            },
            {
                "user_id": USER_A,
                "resume_id": "other-resume",
                "generation_id": None,
                "chunk_text": "other resume null chunk",
            },
        ]
    )

    client.delete_inactive_resume_chunks(
        user_id=USER_A,
        resume_id=RESUME_ID,
        active_generation_id="active-generation",
    )

    remaining_chunks = {chunk["chunk_text"] for chunk in client.chunks}
    assert "active chunk" in remaining_chunks
    assert "old chunk" not in remaining_chunks
    assert "null generation chunk" not in remaining_chunks
    assert "other user old chunk" in remaining_chunks
    assert "other user null chunk" in remaining_chunks
    assert "other resume old chunk" in remaining_chunks
    assert "other resume null chunk" in remaining_chunks


def test_resume_readiness_requires_active_indexed_chunks() -> None:
    client = FakeCloudResumeClient()
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]
    ready_record = _record(status="ready", index_status="indexed", active_chunk_generation="active-generation")
    client.records[(USER_A, RESUME_ID)] = ready_record

    no_chunks = service.get_resume_readiness(user_id=USER_A, record=ready_record)

    assert no_chunks.can_generate is False
    assert no_chunks.chunk_count == 0
    assert no_chunks.readiness_reason == "no_chunks"

    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "active-generation",
            "chunk_text": "safe indexed chunk",
        }
    )

    with_chunks = service.get_resume_readiness(user_id=USER_A, record=ready_record)

    assert with_chunks.can_generate is True
    assert with_chunks.chunk_count == 1
    assert with_chunks.readiness_reason == "ready"


def test_resume_readiness_marks_needs_review_as_needs_confirmation() -> None:
    client = FakeCloudResumeClient()
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]
    record = _record(status="needs_review", index_status="not_indexed", review_required=True)

    readiness = service.get_resume_readiness(user_id=USER_A, record=record)

    assert readiness.can_generate is False
    assert readiness.chunk_count is None
    assert readiness.readiness_reason == "needs_confirmation"


class FakeParser:
    def extract_profile(self, *, filename: str, content: bytes) -> dict[str, object]:
        assert filename == "resume.txt"
        assert content == b"resume bytes"
        profile = {
            "full_name": "Test User",
            "professional_summary": "Backend engineer.",
            "raw_resume_text": "resume bytes",
        }
        return {
            "parser_provider": "local",
            "fallback_used": False,
            "missing_fields": [],
            "review_required": False,
            "profile": profile,
            "extracted_text_length": 12,
        }


class FailingParser:
    def extract_profile(self, *, filename: str, content: bytes) -> dict[str, object]:
        raise ProviderError("provider failed with raw text: SECRET RESUME BODY")


class RawTextOnlyParser:
    def extract_profile(self, *, filename: str, content: bytes) -> dict[str, object]:
        return {
            "parser_provider": "local",
            "fallback_used": False,
            "missing_fields": [],
            "review_required": False,
            "profile": {
                "raw_resume_text": content.decode("utf-8"),
            },
            "extracted_text_length": len(content),
        }


def test_sanitize_resume_filename_rejects_path_traversal() -> None:
    assert sanitize_resume_filename("..\\nested/Resume Final.txt") == "Resume Final.txt"
    with pytest.raises(CloudResumeValidationError):
        sanitize_resume_filename("../../resume.exe")


def test_sanitize_resume_filename_preserves_extension_when_truncated() -> None:
    filename = "a" * 200 + ".pdf"

    safe_filename = sanitize_resume_filename(filename)

    assert len(safe_filename) == 120
    assert safe_filename.endswith(".pdf")


def test_validate_upload_rejects_empty_oversized_and_mime_mismatch() -> None:
    with pytest.raises(CloudResumeValidationError):
        validate_resume_upload(filename="resume.txt", content=b"", content_type="text/plain")
    with pytest.raises(CloudResumeValidationError):
        validate_resume_upload(
            filename="resume.txt",
            content=b"x" * (5 * 1024 * 1024 + 1),
            content_type="text/plain",
        )
    with pytest.raises(CloudResumeValidationError):
        validate_resume_upload(filename="resume.pdf", content=b"%PDF", content_type="text/plain")


def test_upload_creates_inactive_uploaded_resume_with_owned_storage_path() -> None:
    client = FakeCloudResumeClient()
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.upload_resume(
        user_id=USER_A,
        filename="resume.txt",
        content=b"resume bytes",
        content_type="text/plain",
    )

    assert result.resume.status == "uploaded"
    assert result.resume.is_active is False
    assert result.resume.storage_path == f"{USER_A}/{result.resume.id}/resume.txt"
    assert client.uploads == [(result.resume.storage_path, b"resume bytes", "text/plain")]
    assert client.inserts[0]["user_id"] == USER_A


def test_upload_marks_resume_failed_when_storage_upload_fails() -> None:
    client = FakeCloudResumeClient()
    client.fail_upload = True
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeError):
        service.upload_resume(
            user_id=USER_A,
            filename="resume.txt",
            content=b"resume bytes",
            content_type="text/plain",
        )

    resume_id = str(client.inserts[0]["id"])
    failed_record = client.records[(USER_A, resume_id)]
    assert failed_record.status == "failed"
    assert failed_record.is_active is False
    assert failed_record.failure_code == "storage_upload_failed"
    assert client.updates[-1]["payload"]["failure_code"] == "storage_upload_failed"


def test_current_returns_only_active_ready_resume() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, "uploaded")] = _record(id="uploaded", status="uploaded", is_active=False)
    client.records[(USER_A, "ready")] = _record(id="ready", status="ready", is_active=True)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.get_current_resume(USER_A)

    assert result is not None
    assert result.id == "ready"


def test_review_candidate_returns_needs_review_separately() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review")
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.get_review_candidate(USER_A)

    assert result is not None
    assert result.status == "needs_review"


@pytest.mark.parametrize("status", ["uploaded", "failed"])
def test_review_candidate_ignores_non_review_statuses(status: str) -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status=status)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.get_review_candidate(USER_A)

    assert result is None


def test_review_candidate_ignores_confirmed_needs_review_resume() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="needs_review",
        confirmed_at="2026-08-04T00:00:00+00:00",
        confirmed_profile={"full_name": "Confirmed"},
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.get_review_candidate(USER_A)

    assert result is None


def test_extract_uses_attempt_guard_and_returns_request_scoped_draft() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="uploaded", extraction_attempt=0)
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = b"resume bytes"
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.extract_resume(user_id=USER_A, resume_id=RESUME_ID)

    assert result.status == "needs_review"
    assert result.extraction_attempt == 1
    assert result.profile["full_name"] == "Test User"
    assert "raw_resume_text" not in result.profile
    assert client.records[(USER_A, RESUME_ID)].status == "needs_review"
    assert client.records[(USER_A, RESUME_ID)].extraction_attempt == 1
    assert client.compare_calls[0]["from_statuses"] == {"uploaded", "failed", "timeout", "cancelled", "needs_review", "indexing"}
    assert client.compare_calls[1]["extraction_attempt"] == 1


def test_txt_extract_succeeds_when_affinda_and_provider_local_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resume_parser_module.settings, "RESUME_PARSER_PROVIDER", "affinda")
    monkeypatch.setattr(resume_parser_module.settings, "RESUME_PARSER_FALLBACK", "local")
    monkeypatch.setattr(resume_parser_module.settings, "GROQ_API_KEY", "")
    parser = ResumeParserService()
    monkeypatch.setattr(
        parser.affinda_parser,
        "parse",
        lambda **_: (_ for _ in ()).throw(AffindaResumeParserError("invalid API key")),
    )
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="uploaded", extraction_attempt=0)
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = (
        b"Test User\nBackend Engineer\nPython FastAPI PostgreSQL\nSynthetic resume fixture only."
    )
    service = CloudResumeService(client=client, parser=parser)

    result = service.extract_resume(user_id=USER_A, resume_id=RESUME_ID)

    updated = client.records[(USER_A, RESUME_ID)]
    assert result.status == "needs_review"
    assert result.parser_provider == "local"
    assert result.fallback_used is True
    assert result.profile["full_name"] == "Test User"
    assert updated.status == "needs_review"
    assert updated.parser_provider == "local"
    assert updated.parser_status == "completed"
    assert updated.extraction_status == "completed"


def test_cloud_extract_uses_gpt_parser_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resume_parser_module.settings, "RESUME_PARSER_PROVIDER", "gpt")
    monkeypatch.setattr(resume_parser_module.settings, "RESUME_PARSER_FALLBACK", "local")
    parser = ResumeParserService()
    monkeypatch.setattr(
        parser.gpt_parser,
        "extract_profile",
        lambda resume_text: parser.resume_service.normalize_profile_fields(
            {
                "full_name": "Cloud GPT User",
                "email": "cloud.gpt@example.com",
                "professional_summary": "Backend engineer with FastAPI projects.",
                "top_skills": "Python, FastAPI",
                "projects": "Cloud Resume UI",
                "education": "B.Tech CSE",
                "extraction_confidence": "high",
            },
            resume_text,
        ),
    )
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="uploaded", extraction_attempt=0)
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = b"Cloud GPT User\nPython FastAPI"
    service = CloudResumeService(client=client, parser=parser)

    result = service.extract_resume(user_id=USER_A, resume_id=RESUME_ID)

    assert result.status == "needs_review"
    assert result.parser_provider == "gpt"
    assert result.profile["full_name"] == "Cloud GPT User"
    assert result.profile["email"] == "cloud.gpt@example.com"
    assert client.records[(USER_A, RESUME_ID)].parser_provider == "gpt"


def test_extract_retry_from_failed_status_can_succeed() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="failed", extraction_attempt=1)
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = b"resume bytes"
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.extract_resume(user_id=USER_A, resume_id=RESUME_ID)

    assert result.status == "needs_review"
    assert result.extraction_attempt == 2
    assert client.records[(USER_A, RESUME_ID)].status == "needs_review"


def test_storage_download_failure_marks_extraction_failed_safely() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="uploaded", extraction_attempt=0)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeError):
        service.extract_resume(user_id=USER_A, resume_id=RESUME_ID)

    failed_record = client.records[(USER_A, RESUME_ID)]
    assert failed_record.status == "failed"
    assert failed_record.failure_code == "extraction_failed"
    assert failed_record.failure_message == "Resume processing failed. Please try again."


def test_parser_failure_marks_extraction_failed_and_logs_no_raw_resume_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="uploaded", extraction_attempt=0)
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = b"SECRET RESUME BODY"
    service = CloudResumeService(client=client, parser=FailingParser())  # type: ignore[arg-type]

    with caplog.at_level("WARNING", logger="cloud_resume"), pytest.raises(CloudResumeError):
        service.extract_resume(user_id=USER_A, resume_id=RESUME_ID)

    assert client.records[(USER_A, RESUME_ID)].status == "failed"
    assert "stage=local_parse" in caplog.text
    assert "ProviderError" in caplog.text
    assert "SECRET RESUME BODY" not in caplog.text


def test_stale_extraction_attempt_write_is_rejected() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="extracting", extraction_attempt=2)

    with pytest.raises(CloudResumeConflictError):
        client.compare_and_set_resume(
            RESUME_ID,
            USER_A,
            {"extracting"},
            {"status": "needs_review"},
            extraction_attempt=1,
        )


class FakeResponse:
    def __init__(self, status_code: int, data: object) -> None:
        self.status_code = status_code
        self._data = data
        self.text = ""

    def json(self) -> object:
        return self._data


class FakeRestSession:
    def __init__(self) -> None:
        self.patch_calls: list[dict[str, object]] = []
        self.get_calls: list[dict[str, object]] = []
        self.post_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []
        self.patch_response = FakeResponse(200, [_record(status="needs_review", extraction_attempt=3).__dict__])
        self.get_response = FakeResponse(200, [])
        self.post_response = FakeResponse(200, [_record(status="ready", is_active=True).__dict__])
        self.delete_response = FakeResponse(204, {})
        self.fail_first_get = False
        self.fail_all_gets = False

    def patch(self, url: str, **kwargs: object) -> FakeResponse:
        self.patch_calls.append({"url": url, **kwargs})
        return self.patch_response

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.get_calls.append({"url": url, **kwargs})
        if self.fail_all_gets or (self.fail_first_get and len(self.get_calls) == 1):
            raise requests.ConnectionError("synthetic stale connection")
        params = kwargs.get("params")
        if isinstance(params, dict) and url.endswith("/resume_chunks"):
            data = self.get_response.json()
            if isinstance(data, list):
                offset = int(str(params.get("offset", "0")))
                limit = int(str(params.get("limit", len(data))))
                return FakeResponse(200, data[offset : offset + limit])
        return self.get_response

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.post_calls.append({"url": url, **kwargs})
        return self.post_response

    def delete(self, url: str, **kwargs: object) -> FakeResponse:
        self.delete_calls.append({"url": url, **kwargs})
        return self.delete_response


def _supabase_client_with_session(session: FakeRestSession) -> SupabaseCloudResumeClient:
    client = SupabaseCloudResumeClient.__new__(SupabaseCloudResumeClient)
    client._rest_url = "https://project-ref.supabase.co/rest/v1"
    client._storage_url = "https://project-ref.supabase.co/storage/v1"
    client._resume_bucket = "resumes"
    client._service_role_key = "service-role-unit-test-value"
    client._session = session
    client._headers = {
        "apikey": "service-role-unit-test-value",
        "Authorization": "Bearer service-role-unit-test-value",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    return client


def test_supabase_compare_and_set_sends_status_user_resume_and_attempt_guards() -> None:
    session = FakeRestSession()
    client = _supabase_client_with_session(session)

    client.compare_and_set_resume(
        RESUME_ID,
        USER_A,
        {"extracting"},
        {"status": "needs_review"},
        extraction_attempt=3,
    )

    params = session.patch_calls[0]["params"]
    assert params["id"] == f"eq.{RESUME_ID}"
    assert params["user_id"] == f"eq.{USER_A}"
    assert params["status"] == "in.(extracting)"
    assert params["extraction_attempt"] == "eq.3"


def test_supabase_select_retries_one_transient_connection_error_without_raw_payload_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeRestSession()
    session.fail_first_get = True
    session.get_response = FakeResponse(200, [])
    client = _supabase_client_with_session(session)

    with caplog.at_level("WARNING", logger="cloud_resume"):
        result = client.get_review_candidate(USER_A)

    assert result is None
    assert len(session.get_calls) == 2
    assert session.get_calls[0]["params"]["status"] == "eq.needs_review"
    assert session.get_calls[0]["params"]["confirmed_at"] == "is.null"
    assert session.get_calls[0]["timeout"] == SUPABASE_SELECT_ATTEMPT_TIMEOUT
    assert "stage=request_retry" in caplog.text
    assert "synthetic stale connection" not in caplog.text


def test_supabase_select_exhausted_retry_logs_once_without_raw_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeRestSession()
    session.fail_all_gets = True
    client = _supabase_client_with_session(session)

    with caplog.at_level("WARNING", logger="cloud_resume"), pytest.raises(CloudResumeError):
        client.get_review_candidate(USER_A)

    assert len(session.get_calls) == 2
    request_error_records = [
        record
        for record in caplog.records
        if record.name == "cloud_resume" and "status=request_error" in record.getMessage()
    ]
    assert len(request_error_records) == 1
    assert "synthetic stale connection" not in caplog.text


def test_supabase_activate_p0001_maps_to_conflict_without_raw_payload_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeRestSession()
    session.post_response = FakeResponse(400, {"code": "P0001", "message": "raw SECRET profile text"})
    client = _supabase_client_with_session(session)

    with caplog.at_level("ERROR", logger="cloud_resume"), pytest.raises(CloudResumeConflictError):
        client.activate_resume(
            user_id=USER_A,
            resume_id=RESUME_ID,
            extraction_attempt=1,
            generation_id="20000000-0000-4000-8000-000000000001",
            confirmed_profile={"full_name": "Test User"},
        )

    assert session.post_calls[0]["url"].endswith("/rpc/activate_cloud_resume")
    assert "error_code=P0001" in caplog.text
    assert "SECRET" not in caplog.text


def test_active_chunk_select_paginates_above_fifty_and_retries_transient_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeRestSession()
    session.fail_first_get = True
    session.get_response = FakeResponse(
        200,
        [{"id": f"chunk-{index}", "chunk_text": "safe chunk"} for index in range(SUPABASE_ACTIVE_CHUNK_PAGE_SIZE + 25)],
    )
    client = _supabase_client_with_session(session)

    with caplog.at_level("WARNING", logger="cloud_resume"):
        chunks = client.get_active_resume_chunks(
            user_id=USER_A,
            resume_id=RESUME_ID,
            generation_id="20000000-0000-4000-8000-000000000001",
        )

    assert len(chunks) == SUPABASE_ACTIVE_CHUNK_PAGE_SIZE + 25
    assert len(session.get_calls) == 3
    assert session.get_calls[0]["params"]["limit"] == str(SUPABASE_ACTIVE_CHUNK_PAGE_SIZE)
    assert session.get_calls[0]["params"]["offset"] == "0"
    assert session.get_calls[-1]["params"]["offset"] == str(SUPABASE_ACTIVE_CHUNK_PAGE_SIZE)
    assert session.get_calls[0]["timeout"] == SUPABASE_SELECT_ATTEMPT_TIMEOUT
    assert "stage=request_retry" in caplog.text
    assert "synthetic stale connection" not in caplog.text


def test_active_chunk_select_is_bounded_and_filters_owner_resume_generation() -> None:
    session = FakeRestSession()
    session.get_response = FakeResponse(
        200,
        [{"id": f"chunk-{index}", "chunk_text": "safe chunk"} for index in range(SUPABASE_ACTIVE_CHUNK_HARD_LIMIT + 1)],
    )
    client = _supabase_client_with_session(session)

    chunks = client.get_active_resume_chunks(
        user_id=USER_A,
        resume_id=RESUME_ID,
        generation_id="20000000-0000-4000-8000-000000000001",
    )

    assert len(chunks) == SUPABASE_ACTIVE_CHUNK_HARD_LIMIT
    assert len(session.get_calls) == SUPABASE_ACTIVE_CHUNK_HARD_LIMIT // SUPABASE_ACTIVE_CHUNK_PAGE_SIZE
    first_params = session.get_calls[0]["params"]
    assert first_params["user_id"] == f"eq.{USER_A}"
    assert first_params["resume_id"] == f"eq.{RESUME_ID}"
    assert first_params["generation_id"] == "eq.20000000-0000-4000-8000-000000000001"


def test_active_chunk_select_exhausted_retry_raises_safe_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = FakeRestSession()
    session.fail_all_gets = True
    client = _supabase_client_with_session(session)

    with caplog.at_level("WARNING", logger="cloud_resume"), pytest.raises(CloudResumeError):
        client.get_active_resume_chunks(
            user_id=USER_A,
            resume_id=RESUME_ID,
            generation_id="20000000-0000-4000-8000-000000000001",
        )

    assert len(session.get_calls) == 2
    request_error_records = [
        record
        for record in caplog.records
        if record.name == "cloud_resume" and "target=resume_chunks" in record.getMessage() and "status=request_error" in record.getMessage()
    ]
    assert len(request_error_records) == 1
    assert "synthetic stale connection" not in caplog.text


def test_supabase_delete_inactive_chunks_uses_null_or_nonactive_generation_filter() -> None:
    session = FakeRestSession()
    client = _supabase_client_with_session(session)

    client.delete_inactive_resume_chunks(
        user_id=USER_A,
        resume_id=RESUME_ID,
        active_generation_id="20000000-0000-4000-8000-000000000001",
    )

    params = session.delete_calls[0]["params"]
    assert params["user_id"] == f"eq.{USER_A}"
    assert params["resume_id"] == f"eq.{RESUME_ID}"
    assert params["or"] == "(generation_id.is.null,generation_id.neq.20000000-0000-4000-8000-000000000001)"


def test_confirm_requires_needs_review_and_matching_attempt() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="uploaded", extraction_attempt=1)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeConflictError):
        service.confirm_resume(
            user_id=USER_A,
            resume_id=RESUME_ID,
            extraction_attempt=1,
            confirmed_profile={"full_name": "Test User"},
        )

    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=2)
    with pytest.raises(CloudResumeConflictError):
        service.confirm_resume(
            user_id=USER_A,
            resume_id=RESUME_ID,
            extraction_attempt=1,
            confirmed_profile={"full_name": "Test User"},
        )


def test_confirm_creates_chunks_marks_ready_and_activates_resume() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.confirm_resume(
        user_id=USER_A,
        resume_id=RESUME_ID,
        extraction_attempt=1,
        confirmed_profile={"full_name": "Test User"},
    )

    assert result.confirmed_profile_saved is True
    assert result.chunks_indexed is True
    assert result.chunk_count == 1
    assert result.status == "ready"
    assert result.ready is True
    assert result.active is True
    assert result.next_step == "resume_ready"
    payload = client.compare_calls[-1]["payload"]
    assert payload["confirmed_profile"] == {"full_name": "Test User"}
    assert payload["status"] == "indexing"
    ready_record = client.records[(USER_A, RESUME_ID)]
    assert ready_record.status == "ready"
    assert ready_record.is_active is True
    assert ready_record.active_chunk_generation
    assert client.chunk_inserts[0][0]["generation_id"] == ready_record.active_chunk_generation
    assert client.chunk_deletes[0] == {
        "user_id": USER_A,
        "resume_id": RESUME_ID,
        "active_generation_id": ready_record.active_chunk_generation,
    }
    assert client.profiles[USER_A] == {"full_name": "Test User"}


def test_confirm_deactivates_previous_active_resume() -> None:
    previous_id = "10000000-0000-4000-8000-000000000099"
    client = FakeCloudResumeClient()
    client.records[(USER_A, previous_id)] = _record(id=previous_id, status="ready", is_active=True)
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    service.confirm_resume(
        user_id=USER_A,
        resume_id=RESUME_ID,
        extraction_attempt=1,
        confirmed_profile={"professional_summary": "New active profile"},
    )

    assert client.records[(USER_A, previous_id)].is_active is False
    assert client.records[(USER_A, RESUME_ID)].is_active is True


def test_review_candidate_excludes_ready_confirmed_active_resume() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=True,
        confirmed_at="2026-08-04T00:00:00+00:00",
        confirmed_profile={"full_name": "Confirmed"},
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    assert service.get_review_candidate(USER_A) is None


def test_confirm_skips_empty_fields_and_does_not_store_raw_resume_text_in_chunks() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    service.confirm_resume(
        user_id=USER_A,
        resume_id=RESUME_ID,
        extraction_attempt=1,
        confirmed_profile={
            "professional_summary": "Backend engineer",
            "projects": "",
            "achievements": "Reduced latency",
        },
    )

    chunks = client.chunk_inserts[0]
    assert {chunk["section"] for chunk in chunks} == {"professional_summary", "achievements"}
    assert "raw_resume_text" not in str(chunks)


def test_confirm_indexes_project_details_from_uploaded_resume_text_when_confirmed_profile_is_sparse() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = (
        b"DEVANSHU CHANDRAKAR\n"
        b"PROJECTS\n"
        b"AI Study Assistant - Built document processing, chunking, embeddings, RAG, Chroma, LangChain, Gemini API, and FastAPI.\n"
        b"EDUCATION\n"
        b"B.TECH CSE\n"
    )
    service = CloudResumeService(client=client, parser=RawTextOnlyParser())  # type: ignore[arg-type]

    service.confirm_resume(
        user_id=USER_A,
        resume_id=RESUME_ID,
        extraction_attempt=1,
        confirmed_profile={
            "full_name": "Devanshu Chandrakar",
            "professional_summary": "Computer Science undergraduate.",
            "projects": "AI Study Assistant",
        },
    )

    chunks = client.chunk_inserts[0]
    assert any(chunk["section"] == "projects" for chunk in chunks)
    assert any("chunking" in str(chunk["chunk_text"]).lower() for chunk in chunks if chunk["section"] == "projects")
    assert "raw_resume_text" not in str(chunks)


def test_confirmed_profile_projects_survive_storage_and_are_indexed() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    service.confirm_resume(
        user_id=USER_A,
        resume_id=RESUME_ID,
        extraction_attempt=1,
        confirmed_profile={
            "full_name": "Test User",
            "projects": "AI Study Assistant - FastAPI and LangChain",
            "experience": "Backend Intern - built APIs",
        },
    )

    assert client.profiles[USER_A]["projects"] == "AI Study Assistant - FastAPI and LangChain"
    assert any(chunk["section"] == "projects" for chunk in client.chunk_inserts[0])


def test_chunk_insert_failure_does_not_activate_resume_and_logs_no_raw_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeCloudResumeClient()
    client.fail_chunk_insert = True
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with caplog.at_level("WARNING", logger="cloud_resume"), pytest.raises(CloudResumeError):
        service.confirm_resume(
            user_id=USER_A,
            resume_id=RESUME_ID,
            extraction_attempt=1,
            confirmed_profile={"professional_summary": "Backend engineer"},
        )

    failed_record = client.records[(USER_A, RESUME_ID)]
    assert failed_record.status == "failed"
    assert failed_record.is_active is False
    assert failed_record.failure_code == "indexing_failed"
    assert "SECRET RESUME BODY" not in caplog.text


def test_successful_activation_prunes_prior_chunks_for_same_resume_only() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    client.chunks.extend(
        [
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": None,
                "section": "legacy",
                "chunk_text": "legacy null generation chunk",
                "metadata": {},
            },
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": "old-generation",
                "section": "summary",
                "chunk_text": "old private chunk",
                "metadata": {},
            },
            {
                "user_id": USER_A,
                "resume_id": "other-resume",
                "generation_id": "other-generation",
                "section": "summary",
                "chunk_text": "other resume chunk",
                "metadata": {},
            },
            {
                "user_id": USER_A,
                "resume_id": "other-resume",
                "generation_id": None,
                "section": "legacy",
                "chunk_text": "other resume null generation chunk",
                "metadata": {},
            },
            {
                "user_id": USER_B,
                "resume_id": RESUME_ID,
                "generation_id": "other-user-generation",
                "section": "summary",
                "chunk_text": "other user chunk",
                "metadata": {},
            },
            {
                "user_id": USER_B,
                "resume_id": RESUME_ID,
                "generation_id": None,
                "section": "legacy",
                "chunk_text": "other user null generation chunk",
                "metadata": {},
            },
        ]
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    service.confirm_resume(
        user_id=USER_A,
        resume_id=RESUME_ID,
        extraction_attempt=1,
        confirmed_profile={"professional_summary": "new chunk"},
    )

    ready_record = client.records[(USER_A, RESUME_ID)]
    assert client.chunk_deletes[0] == {
        "user_id": USER_A,
        "resume_id": RESUME_ID,
        "active_generation_id": ready_record.active_chunk_generation,
    }
    assert not any(chunk["chunk_text"] == "legacy null generation chunk" for chunk in client.chunks)
    assert not any(chunk["chunk_text"] == "old private chunk" for chunk in client.chunks)
    assert any(chunk["chunk_text"] == "other resume chunk" for chunk in client.chunks)
    assert any(chunk["chunk_text"] == "other resume null generation chunk" for chunk in client.chunks)
    assert any(chunk["chunk_text"] == "other user chunk" for chunk in client.chunks)
    assert any(chunk["chunk_text"] == "other user null generation chunk" for chunk in client.chunks)
    assert any(chunk["generation_id"] == ready_record.active_chunk_generation for chunk in client.chunks)


def test_activation_conflict_does_not_mark_resume_failed_or_create_duplicate_active_resume(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeCloudResumeClient()
    client.fail_activation = True
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with caplog.at_level("WARNING", logger="cloud_resume"), pytest.raises(CloudResumeConflictError):
        service.confirm_resume(
            user_id=USER_A,
            resume_id=RESUME_ID,
            extraction_attempt=1,
            confirmed_profile={"professional_summary": "Backend engineer"},
        )

    conflict_record = client.records[(USER_A, RESUME_ID)]
    assert conflict_record.status == "indexing"
    assert conflict_record.is_active is False
    assert conflict_record.failure_code is None
    assert client.chunks == []
    assert "stage=activate_resume" in caplog.text


def test_activation_failure_discards_current_generation_and_marks_failed() -> None:
    client = FakeCloudResumeClient()
    client.activation_error = CloudResumeError("activation failed")
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "old-active-generation",
            "section": "summary",
            "chunk_text": "previous active chunk",
            "metadata": {},
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeError):
        service.confirm_resume(
            user_id=USER_A,
            resume_id=RESUME_ID,
            extraction_attempt=1,
            confirmed_profile={"professional_summary": "Backend engineer"},
        )

    failed_record = client.records[(USER_A, RESUME_ID)]
    assert failed_record.status == "failed"
    assert failed_record.failure_code == "indexing_failed"
    assert [chunk["chunk_text"] for chunk in client.chunks] == ["previous active chunk"]
    assert client.chunk_deletes[-1]["generation_id"] is not None


def test_indexing_resume_can_retry_extraction_without_affecting_active_ready_resume() -> None:
    active_id = "10000000-0000-4000-8000-000000000099"
    client = FakeCloudResumeClient()
    client.records[(USER_A, active_id)] = _record(
        id=active_id,
        status="ready",
        is_active=True,
        active_chunk_generation="active-generation",
    )
    client.records[(USER_A, RESUME_ID)] = _record(status="indexing", extraction_attempt=1, is_active=False)
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = b"resume bytes"
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.extract_resume(user_id=USER_A, resume_id=RESUME_ID)

    assert result.status == "needs_review"
    assert result.extraction_attempt == 2
    assert client.compare_calls[0]["from_statuses"] == {"uploaded", "failed", "timeout", "cancelled", "needs_review", "indexing"}
    assert client.records[(USER_A, active_id)].status == "ready"
    assert client.records[(USER_A, active_id)].is_active is True


def test_failed_chunk_cleanup_logs_safely_and_preserves_original_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class DiscardFailClient(FakeCloudResumeClient):
        def insert_resume_chunks(self, chunks: list[dict[str, object]]) -> None:
            super().insert_resume_chunks(chunks)
            self.fail_chunk_delete = True

    client = DiscardFailClient()
    client.activation_error = CloudResumeError("activation failed with raw text: SECRET RESUME BODY")
    client.records[(USER_A, RESUME_ID)] = _record(status="needs_review", extraction_attempt=1)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with caplog.at_level("WARNING", logger="cloud_resume"), pytest.raises(CloudResumeError):
        service.confirm_resume(
            user_id=USER_A,
            resume_id=RESUME_ID,
            extraction_attempt=1,
            confirmed_profile={"professional_summary": "Backend engineer"},
        )

    assert "Could not discard inactive cloud resume chunk generation" in caplog.text
    assert "SECRET RESUME BODY" not in caplog.text


def test_active_cloud_resume_retrieval_filters_active_generation() -> None:
    client = FakeCloudResumeClient()
    generation_id = "20000000-0000-4000-8000-000000000001"
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=True,
        active_chunk_generation=generation_id,
    )
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": generation_id,
            "section": "projects",
            "chunk_text": "Built FastAPI services.",
            "metadata": {
                "chunk_id": "resume-1",
                "source": "cloud_resume",
                "preview": "Built FastAPI services.",
                "tokens": ["built", "fastapi", "services"],
            },
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    retrieval = service.retrieve_active_resume_chunks(
        user_id=USER_A,
        question="Tell me about FastAPI",
        category="technical",
    )

    assert retrieval["retrieval_used"] is True
    assert retrieval["retrieved_chunks"][0]["source"] == "cloud_resume"


def test_selected_cloud_resume_retrieval_falls_back_to_indexed_selected_chunks() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=False,
        active_chunk_generation="active-generation",
        confirmed_profile={"full_name": "Devanshu Chandrakar"},
    )
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "active-generation",
            "section": "projects",
            "chunk_text": "Project: Low-resolution deepfake detection using TensorFlow and FastAPI.",
            "metadata": {
                "chunk_id": "selected-1",
                "source": "cloud_resume",
                "section": "projects",
                "preview": "Project: Low-resolution deepfake detection",
                "tokens": ["low", "resolution", "deepfake", "detection"],
            },
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    retrieval = service.retrieve_resume_chunks(
        user_id=USER_A,
        resume_id=RESUME_ID,
        question="Introduce yourself",
        category="personal",
    )

    assert retrieval["retrieval_used"] is True
    assert retrieval["retrieved_chunk_count"] == 1
    assert retrieval["retrieved_chunks"][0]["text"].startswith("Project: Low-resolution deepfake detection")
    assert retrieval["selected_resume_candidate_name"] == "Devanshu Chandrakar"
    assert retrieval["selected_resume_candidate_name_source"] == "metadata"


def test_selected_cloud_resume_retrieval_extracts_header_candidate_name_when_metadata_missing() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=False,
        active_chunk_generation="active-generation",
    )
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "active-generation",
            "section": "resume",
            "chunk_text": "DEVANSHU CHANDRAKAR\nB.TECH - COMPUTER SCIENCE & ENGINEERING\nProject: Unique work",
            "metadata": {"chunk_id": "header-1", "source": "cloud_resume", "section": "resume"},
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    retrieval = service.retrieve_resume_chunks(
        user_id=USER_A,
        resume_id=RESUME_ID,
        question="Introduce yourself",
        category="personal",
    )

    assert retrieval["selected_resume_candidate_name"] == "DEVANSHU CHANDRAKAR"
    assert retrieval["selected_resume_candidate_name_source"] == "header"


def test_selected_cloud_resume_project_question_prefers_project_sections() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=False,
        active_chunk_generation="active-generation",
        confirmed_profile={"full_name": "Devanshu Chandrakar"},
    )
    client.chunks.extend(
        [
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": "active-generation",
                "section": "professional_summary",
                "chunk_text": "Computer Science undergraduate focused on AI and backend engineering.",
                "metadata": {"chunk_id": "summary-1", "source": "cloud_resume", "section": "professional_summary"},
            },
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": "active-generation",
                "section": "projects",
                "chunk_text": "AI Study Assistant built with LangChain, Gemini API, RAG, Chroma, and FastAPI.",
                "metadata": {"chunk_id": "project-1", "source": "cloud_resume", "section": "projects"},
            },
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": "active-generation",
                "section": "work_experience",
                "chunk_text": "Developed backend APIs and document-processing workflows for resume-grounded answers.",
                "metadata": {"chunk_id": "work-1", "source": "cloud_resume", "section": "work_experience"},
            },
        ]
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    retrieval = service.retrieve_resume_chunks(
        user_id=USER_A,
        resume_id=RESUME_ID,
        question="can you explain your projects",
        category="hr",
        limit=2,
    )

    assert retrieval["project_context_source"] == "selected_resume_projects"
    assert retrieval["project_context_chunks_found"] >= 1
    assert all(
        chunk["section"] in {"projects", "work_experience", "experience", "internship", "project"}
        for chunk in retrieval["retrieved_chunks"]
    )
    assert any("AI Study Assistant" in chunk["text"] for chunk in retrieval["retrieved_chunks"])


def test_selected_cloud_resume_specific_project_question_prefers_exact_project_match() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=False,
        active_chunk_generation="active-generation",
        confirmed_profile={"full_name": "Devanshu Chandrakar"},
    )
    client.chunks.extend(
        [
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": "active-generation",
                "section": "projects",
                "chunk_text": "LLM Coding Agent Assistant - Built a coding helper using FastAPI and prompt orchestration.",
                "metadata": {"chunk_id": "project-1", "source": "cloud_resume", "section": "projects"},
            },
            {
                "user_id": USER_A,
                "resume_id": RESUME_ID,
                "generation_id": "active-generation",
                "section": "projects",
                "chunk_text": "AI-Powered Medical Insights Platform - Built semantic search with Streamlit, FAISS, and MiniLM.",
                "metadata": {"chunk_id": "project-2", "source": "cloud_resume", "section": "projects"},
            },
        ]
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    retrieval = service.retrieve_resume_chunks(
        user_id=USER_A,
        resume_id=RESUME_ID,
        question="Explain your AI-Powered Medical Insights Platform",
        category="hr",
        limit=2,
    )

    assert retrieval["specific_project_intent_detected"] is True
    assert retrieval["matched_project_name"] == "AI-Powered Medical Insights Platform"
    assert retrieval["project_match_confidence"] == "exact"
    assert retrieval["project_answer_mode"] == "detailed_specific_project"
    assert "AI-Powered Medical Insights Platform" in retrieval["retrieved_chunks"][0]["text"]


def test_selected_cloud_resume_specific_project_question_rejects_missing_project() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=False,
        active_chunk_generation="active-generation",
    )
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "active-generation",
            "section": "projects",
            "chunk_text": "AI Study Assistant - Built document processing and RAG workflows.",
            "metadata": {"chunk_id": "project-1", "source": "cloud_resume", "section": "projects"},
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeValidationError, match="specific project was not found"):
        service.retrieve_resume_chunks(
            user_id=USER_A,
            resume_id=RESUME_ID,
            question="Explain your Smart Product Scanning System",
            category="hr",
        )


def test_selected_cloud_resume_project_question_requires_project_details() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=False,
        active_chunk_generation="active-generation",
    )
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "active-generation",
            "section": "education",
            "chunk_text": "B.TECH - COMPUTER SCIENCE & ENGINEERING",
            "metadata": {"chunk_id": "education-1", "source": "cloud_resume", "section": "education"},
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeValidationError, match="does not contain enough project details"):
        service.retrieve_resume_chunks(
            user_id=USER_A,
            resume_id=RESUME_ID,
            question="can you explain your projects",
            category="hr",
        )


def test_selected_cloud_resume_retrieval_rejects_unindexed_selected_resume() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="needs_review",
        is_active=False,
        active_chunk_generation=None,
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeValidationError):
        service.retrieve_resume_chunks(
            user_id=USER_A,
            resume_id=RESUME_ID,
            question="Introduce yourself",
            category="personal",
        )


def test_delete_active_resume_marks_deleted_clears_chunks_and_current() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=True,
        active_chunk_generation="active-generation",
        confirmed_profile={"professional_summary": "Private profile"},
    )
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = b"private resume"
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "active-generation",
            "section": "summary",
            "chunk_text": "Private profile",
            "metadata": {},
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.delete_resume(user_id=USER_A, resume_id=RESUME_ID)

    deleted = client.records[(USER_A, RESUME_ID)]
    assert result.status == "deleted"
    assert result.ready is False
    assert deleted.status == "deleted"
    assert deleted.is_active is False
    assert deleted.active_chunk_generation is None
    assert deleted.index_status == "not_indexed"
    assert client.chunks == []
    assert client.objects == {}
    assert service.get_current_resume(USER_A) is None


def test_delete_already_deleted_resume_is_idempotent() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="deleted", is_active=False, active_chunk_generation=None)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.delete_resume(user_id=USER_A, resume_id=RESUME_ID)

    assert result.status == "deleted"
    assert result.is_active is False
    assert client.records[(USER_A, RESUME_ID)].status == "deleted"


def test_delete_cross_user_resume_is_rejected() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_B, RESUME_ID)] = _record(user_id=USER_B, status="ready", is_active=True)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeNotFoundError):
        service.delete_resume(user_id=USER_A, resume_id=RESUME_ID)


def test_delete_chunk_cleanup_failure_raises_retryable_error_without_success() -> None:
    client = FakeCloudResumeClient()
    client.fail_chunk_delete = True
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=True,
        active_chunk_generation="active-generation",
    )
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "active-generation",
            "section": "summary",
            "chunk_text": "Private profile",
            "metadata": {},
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeError):
        service.delete_resume(user_id=USER_A, resume_id=RESUME_ID)

    assert client.chunks
    assert client.records[(USER_A, RESUME_ID)].status == "deleted"
    client.fail_chunk_delete = False

    result = service.delete_resume(user_id=USER_A, resume_id=RESUME_ID)

    assert result.status == "deleted"
    assert client.chunks == []


def test_rebuild_ready_active_resume_switches_generation_and_prunes_old_chunks() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=True,
        confirmed_profile={"professional_summary": "Updated cloud profile"},
        active_chunk_generation="old-generation",
    )
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "old-generation",
            "section": "summary",
            "chunk_text": "Old profile",
            "metadata": {},
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.rebuild_resume_index(user_id=USER_A, resume_id=RESUME_ID)

    ready_record = client.records[(USER_A, RESUME_ID)]
    assert result.status == "ready"
    assert result.index_status == "indexed"
    assert result.chunk_count == 1
    assert result.active_chunk_generation == ready_record.active_chunk_generation
    assert ready_record.active_chunk_generation != "old-generation"
    assert any(chunk["generation_id"] == ready_record.active_chunk_generation for chunk in client.chunks)
    assert not any(chunk["generation_id"] == "old-generation" for chunk in client.chunks)
    assert "raw_resume_text" not in str(client.chunk_inserts)


def test_rebuild_rejects_deleted_or_unconfirmed_resume() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="deleted", is_active=False, confirmed_profile=None)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeConflictError):
        service.rebuild_resume_index(user_id=USER_A, resume_id=RESUME_ID)


def test_rebuild_failure_preserves_existing_active_generation() -> None:
    class FailingRebuildClient(FakeCloudResumeClient):
        def activate_rebuilt_resume_generation(
            self,
            *,
            user_id: str,
            resume_id: str,
            expected_active_generation: str,
            new_generation_id: str,
        ) -> CloudResumeRecord:
            raise CloudResumeError("update failed with raw text: SECRET RESUME BODY")

    client = FailingRebuildClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=True,
        confirmed_profile={"professional_summary": "Updated cloud profile"},
        active_chunk_generation="old-generation",
    )
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "old-generation",
            "section": "summary",
            "chunk_text": "Old active profile",
            "metadata": {},
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeError):
        service.rebuild_resume_index(user_id=USER_A, resume_id=RESUME_ID)

    assert client.records[(USER_A, RESUME_ID)].active_chunk_generation == "old-generation"
    assert [chunk["chunk_text"] for chunk in client.chunks] == ["Old active profile"]


def test_stale_rebuild_activation_discards_new_generation_and_preserves_active_resume() -> None:
    class StaleRebuildClient(FakeCloudResumeClient):
        def insert_resume_chunks(self, chunks: list[dict[str, object]]) -> None:
            super().insert_resume_chunks(chunks)
            current = self.records[(USER_A, RESUME_ID)]
            self.records[(USER_A, RESUME_ID)] = _record(
                **{**current.__dict__, "active_chunk_generation": "concurrent-generation"}
            )

    client = StaleRebuildClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=True,
        confirmed_profile={"professional_summary": "Updated cloud profile"},
        active_chunk_generation="old-generation",
    )
    client.chunks.append(
        {
            "user_id": USER_A,
            "resume_id": RESUME_ID,
            "generation_id": "old-generation",
            "section": "summary",
            "chunk_text": "Old active profile",
            "metadata": {},
        }
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeConflictError):
        service.rebuild_resume_index(user_id=USER_A, resume_id=RESUME_ID)

    assert client.records[(USER_A, RESUME_ID)].active_chunk_generation == "concurrent-generation"
    assert [chunk["chunk_text"] for chunk in client.chunks] == ["Old active profile"]


def test_concurrent_delete_blocks_rebuild_from_restoring_deleted_resume() -> None:
    class DeleteDuringRebuildClient(FakeCloudResumeClient):
        def insert_resume_chunks(self, chunks: list[dict[str, object]]) -> None:
            super().insert_resume_chunks(chunks)
            current = self.records[(USER_A, RESUME_ID)]
            self.records[(USER_A, RESUME_ID)] = _record(
                **{
                    **current.__dict__,
                    "status": "deleted",
                    "is_active": False,
                    "active_chunk_generation": None,
                    "index_status": "not_indexed",
                }
            )

    client = DeleteDuringRebuildClient()
    client.records[(USER_A, RESUME_ID)] = _record(
        status="ready",
        is_active=True,
        confirmed_profile={"professional_summary": "Updated cloud profile"},
        active_chunk_generation="old-generation",
    )
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeConflictError):
        service.rebuild_resume_index(user_id=USER_A, resume_id=RESUME_ID)

    deleted = client.records[(USER_A, RESUME_ID)]
    assert deleted.status == "deleted"
    assert deleted.is_active is False
    assert deleted.active_chunk_generation is None
    assert client.chunks == []


def test_confirm_rejects_unknown_raw_or_oversized_profile_fields() -> None:
    with pytest.raises(CloudResumeValidationError):
        validate_confirmed_profile({"unknown": "value"})
    with pytest.raises(CloudResumeValidationError):
        validate_confirmed_profile({"raw_resume_text": "raw text"})
    with pytest.raises(CloudResumeValidationError):
        validate_confirmed_profile({"full_name": "x" * (64 * 1024)})


def test_extract_completion_failure_marks_attempt_failed() -> None:
    class CompletionFailClient(FakeCloudResumeClient):
        def compare_and_set_resume(
            self,
            resume_id: str,
            user_id: str,
            from_statuses: set[str],
            payload: dict[str, object],
            *,
            extraction_attempt: int | None = None,
        ) -> CloudResumeRecord:
            if payload.get("status") == "needs_review":
                raise CloudResumeError("completion write failed")
            return super().compare_and_set_resume(
                resume_id,
                user_id,
                from_statuses,
                payload,
                extraction_attempt=extraction_attempt,
            )

    client = CompletionFailClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="uploaded", extraction_attempt=0)
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = b"resume bytes"
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeError):
        service.extract_resume(user_id=USER_A, resume_id=RESUME_ID)

    failed_record = client.records[(USER_A, RESUME_ID)]
    assert failed_record.status == "failed"
    assert failed_record.failure_code == "extraction_state_write_failed"


def test_user_b_cannot_access_user_a_resume() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(user_id=USER_A)
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    with pytest.raises(CloudResumeNotFoundError):
        service.get_status(user_id=USER_B, resume_id=RESUME_ID)
