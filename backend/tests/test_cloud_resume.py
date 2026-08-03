import pytest

from app.cloud.cloud_resume import (
    CloudResumeConflictError,
    CloudResumeError,
    CloudResumeNotFoundError,
    CloudResumeRecord,
    CloudResumeService,
    SupabaseCloudResumeClient,
    CloudResumeValidationError,
    sanitize_resume_filename,
    validate_confirmed_profile,
    validate_resume_upload,
)

USER_A = "00000000-0000-4000-8000-000000000001"
USER_B = "00000000-0000-4000-8000-000000000002"
RESUME_ID = "10000000-0000-4000-8000-000000000001"


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


class FakeCloudResumeClient:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], CloudResumeRecord] = {}
        self.objects: dict[str, bytes] = {}
        self.inserts: list[dict[str, object]] = []
        self.uploads: list[tuple[str, bytes, str]] = []
        self.compare_calls: list[dict[str, object]] = []
        self.updates: list[dict[str, object]] = []
        self.fail_upload = False

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
        return self.objects[storage_path]

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
            if record_user_id == user_id and record.status == "needs_review"
        ]
        return candidates[0] if candidates else None

    def update_resume(self, resume_id: str, user_id: str, payload: dict[str, object]) -> CloudResumeRecord:
        self.updates.append({"resume_id": resume_id, "user_id": user_id, "payload": payload})
        current = self.records[(user_id, resume_id)]
        updated = _record(**{**current.__dict__, **payload})
        self.records[(user_id, resume_id)] = updated
        return updated

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


def test_extract_uses_attempt_guard_and_returns_request_scoped_draft() -> None:
    client = FakeCloudResumeClient()
    client.records[(USER_A, RESUME_ID)] = _record(status="uploaded", extraction_attempt=0)
    client.objects[f"{USER_A}/{RESUME_ID}/resume.txt"] = b"resume bytes"
    service = CloudResumeService(client=client, parser=FakeParser())  # type: ignore[arg-type]

    result = service.extract_resume(user_id=USER_A, resume_id=RESUME_ID)

    assert result.status == "needs_review"
    assert result.extraction_attempt == 1
    assert result.profile["full_name"] == "Test User"
    assert "raw_resume_text" in result.profile
    assert client.records[(USER_A, RESUME_ID)].status == "needs_review"
    assert client.records[(USER_A, RESUME_ID)].extraction_attempt == 1
    assert client.compare_calls[0]["from_statuses"] == {"uploaded", "failed", "timeout", "cancelled", "needs_review"}
    assert client.compare_calls[1]["extraction_attempt"] == 1


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
        self.patch_response = FakeResponse(200, [_record(status="needs_review", extraction_attempt=3).__dict__])

    def patch(self, url: str, **kwargs: object) -> FakeResponse:
        self.patch_calls.append({"url": url, **kwargs})
        return self.patch_response


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


def test_confirm_writes_confirmed_profile_only_not_profiles() -> None:
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
    assert result.status == "needs_review"
    payload = client.compare_calls[-1]["payload"]
    assert payload["confirmed_profile"] == {"full_name": "Test User"}
    assert "status" not in payload
    assert "is_active" not in payload


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
