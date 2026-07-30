import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.screen_intelligence import (
    BrowserMetadata,
    EnvelopeStatus,
    ExtractionMetadata,
    ExtractionQuestionItem,
    ExtractionResultEnvelope,
    ExtractionTiming,
    NormalizedAnswer,
    NormalizedQuestion,
    QuestionRegion,
    SafeErrorCode,
    SafeExtractionError,
    SourceType,
)
from app.services.normalized_question_service import (
    build_screen_extraction_envelope,
    normalize_question_type,
    with_screen_extraction_envelope,
)


def _legacy_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "ok": True,
        "result_mode": "single",
        "question": "What is an array?",
        "answer": "A contiguous collection of values.",
        "question_type": "mcq",
        "language": "",
        "code": "",
        "items": [],
        "question_count": 1,
        "incomplete_question_count": 0,
        "confidence": 0.9,
        "incomplete": False,
        "capture_ms": 1.0,
        "image_prepare_ms": 2.0,
        "screen_model_ms": 3.0,
        "response_parse_ms": 4.0,
        "total_screen_pipeline_ms": 10.0,
        "screenshot_count": 1,
        "screen_model_request_count": 1,
        "generation_request_count": 0,
        "automatic_fallback_count": 0,
        "correction_request_count": 0,
        "raw_vision_text": "private model output",
    }
    payload.update(overrides)
    return payload


def _question_item(question_id: str = "question_1") -> ExtractionQuestionItem:
    return ExtractionQuestionItem(
        question_id=question_id,
        question=NormalizedQuestion(
            question_type="mcq",
            statement="The chief ore of Aluminium is?",
            answer=NormalizedAnswer(text="c. Bauxite"),
        ),
    )


def _envelope(**overrides: Any) -> ExtractionResultEnvelope:
    payload = {
        "request_id": "request_1",
        "operation_id": "operation_1",
        "source_type": SourceType.SCREEN_CAPTURE,
        "status": EnvelopeStatus.READY,
        "questions": [_question_item()],
        "selected_question_id": "question_1",
        "extraction": ExtractionMetadata(complete=True, confidence=0.95, method="screen_vision"),
    }
    payload.update(overrides)
    return ExtractionResultEnvelope(**payload)


def test_single_mcq_envelope_validates_and_serializes_stable_enums() -> None:
    envelope = _envelope()
    dumped = envelope.model_dump(mode="json")

    assert dumped["schema_version"] == "1.0"
    assert dumped["mode"] == "screen"
    assert dumped["source_type"] == "screen_capture"
    assert dumped["status"] == "ready"
    assert dumped["questions"][0]["question"]["question_type"] == "mcq"


def test_batch_coding_and_debugging_envelopes_validate() -> None:
    coding = _question_item("coding_1")
    coding.question.question_type = "coding"
    coding.question.answer.code = "print('ok')"
    debugging = _question_item("debugging_1")
    debugging.question.question_type = "debugging"

    envelope = _envelope(questions=[coding, debugging], selected_question_id=None)

    assert len(envelope.questions) == 2
    assert envelope.selected_question_id is None


def test_failed_and_ready_status_invariants_are_enforced() -> None:
    with pytest.raises(ValidationError):
        _envelope(status=EnvelopeStatus.FAILED, questions=[], selected_question_id=None, error=None)

    with pytest.raises(ValidationError):
        _envelope(questions=[], selected_question_id=None)

    failed = _envelope(
        status=EnvelopeStatus.FAILED,
        questions=[],
        selected_question_id=None,
        error=SafeExtractionError(code=SafeErrorCode.UNREADABLE_SCREEN, message="Could not read."),
    )
    assert failed.error is not None


def test_selected_question_duplicate_ids_confidence_and_region_validation() -> None:
    with pytest.raises(ValidationError):
        _envelope(selected_question_id="missing")

    with pytest.raises(ValidationError):
        _envelope(questions=[_question_item("same"), _question_item("same")], selected_question_id=None)

    with pytest.raises(ValidationError):
        _envelope(extraction=ExtractionMetadata(complete=True, confidence=1.2, method="screen_vision"))

    with pytest.raises(ValidationError):
        QuestionRegion(x=0, y=-1, width=10, height=10)


def test_browser_metadata_is_nullable_and_rejects_unsafe_extra_fields() -> None:
    assert _envelope(browser=None).browser is None
    with pytest.raises(ValidationError):
        BrowserMetadata(name="chrome", full_url="https://example.com/private?token=1")  # type: ignore[call-arg]


def test_legacy_single_response_maps_to_screen_capture_envelope_without_private_fields() -> None:
    envelope = build_screen_extraction_envelope(
        _legacy_payload(),
        request_id="request_1",
        operation_id="operation_1",
    )
    dumped = envelope.model_dump(mode="json")
    serialized = json.dumps(dumped)

    assert dumped["source_type"] == "screen_capture"
    assert dumped["browser"] is None
    assert dumped["selected_question_id"] == "screen_question_1"
    assert dumped["questions"][0]["question"]["answer"]["text"] == "A contiguous collection of values."
    assert "raw_vision_text" not in serialized
    assert "private model output" not in serialized


def test_legacy_batch_response_maps_multiple_items_and_preserves_counts() -> None:
    payload = _legacy_payload(
        result_mode="batch",
        question="Q7\nQ8",
        answer="7. c. Bauxite\n8. d. Thane",
        question_count=2,
        incomplete_question_count=1,
        items=[
            {
                "question_id": "screen_question_1",
                "display_number": "7",
                "question": "The chief ore of Aluminium is?",
                "question_type": "mcq",
                "answer": "c. Bauxite",
                "confidence": 0.96,
            },
            {
                "question_id": "screen_question_2",
                "display_number": "8",
                "question": "The first train in India ran from Bombay to ...?",
                "question_type": "mcq",
                "answer": "d. Thane",
                "confidence": 0.93,
            },
        ],
    )

    response = with_screen_extraction_envelope(payload, request_id="request_1", operation_id="operation_1")

    assert response["answer"] == "7. c. Bauxite\n8. d. Thane"
    assert response["question_count"] == 2
    assert len(response["envelope"]["questions"]) == 2
    assert response["envelope"]["selected_question_id"] is None
    assert response["envelope"]["metrics"]["screenshot_count"] == 1
    assert response["envelope"]["metrics"]["screen_model_request_count"] == 1
    assert response["envelope"]["metrics"]["generation_request_count"] == 0
    assert response["envelope"]["extraction"]["warnings"] == ["incomplete_questions_ignored"]


def test_compatibility_mapping_preserves_legacy_question_type_values() -> None:
    assert normalize_question_type("output") == "output_prediction"
    assert normalize_question_type("visual") == "diagram"
    assert normalize_question_type("interview") == "general"
    assert normalize_question_type("none") == "unknown"
    assert normalize_question_type("surprise") == "unknown"


def test_contract_conversion_is_local_and_preserves_request_counts() -> None:
    payload = _legacy_payload(screenshot_count=1, screen_model_request_count=1, automatic_fallback_count=0)

    response = with_screen_extraction_envelope(payload, request_id="request_1", operation_id="operation_1")

    assert response["screenshot_count"] == 1
    assert response["screen_model_request_count"] == 1
    assert response["automatic_fallback_count"] == 0
    assert response["envelope"]["metrics"]["screenshot_count"] == 1
    assert response["envelope"]["metrics"]["screen_model_request_count"] == 1
