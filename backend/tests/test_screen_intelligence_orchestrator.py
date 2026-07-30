import json

from app.models.screen_intelligence import SourceType
from app.services.screen_intelligence_orchestrator import (
    EXTENSION_UNAVAILABLE_MESSAGE,
    ScreenIntelligenceOrchestrator,
    ScreenOperationStatus,
    can_commit_screen_result,
    cancel_operation,
    create_screen_operation,
    supersede_operation,
    transition_operation,
)


def test_screen_capture_operation_wraps_one_ocr_call_and_echoes_ids() -> None:
    orchestrator = ScreenIntelligenceOrchestrator()
    calls = 0

    def execute_ocr() -> dict:
        nonlocal calls
        calls += 1
        return {
            "ok": True,
            "question": "What is an array?",
            "answer": "A collection of values.",
            "question_type": "general",
            "confidence": 0.9,
            "screenshot_count": 1,
            "screen_model_request_count": 1,
            "generation_request_count": 0,
            "automatic_fallback_count": 0,
            "correction_request_count": 0,
        }

    payload = orchestrator.execute_screen_capture(
        operation_id="op_screen_1",
        request_id="req_screen_1",
        execute_ocr=execute_ocr,
    )

    assert calls == 1
    assert payload["operation_id"] == "op_screen_1"
    assert payload["request_id"] == "req_screen_1"
    assert payload["source_type"] == "screen_capture"
    assert payload["screenshot_count"] == 1
    assert payload["screen_model_request_count"] == 1
    assert payload["generation_request_count"] == 0
    assert payload["envelope"]["operation_id"] == "op_screen_1"
    assert payload["envelope"]["request_id"] == "req_screen_1"
    assert payload["envelope"]["status"] == "ready"


def test_extension_unavailable_is_failed_operation_without_work_or_questions() -> None:
    payload = ScreenIntelligenceOrchestrator().extension_unavailable(
        operation_id="op_extension_1",
        request_id="req_extension_1",
    )

    assert payload["ok"] is False
    assert payload["operation_id"] == "op_extension_1"
    assert payload["request_id"] == "req_extension_1"
    assert payload["source_type"] == "browser_extension"
    assert payload["question"] == ""
    assert payload["answer"] == ""
    assert payload["items"] == []
    assert payload["question_count"] == 0
    assert payload["screenshot_count"] == 0
    assert payload["screen_model_request_count"] == 0
    assert payload["generation_request_count"] == 0
    assert payload["envelope"]["status"] == "failed"
    assert payload["envelope"]["error"]["code"] == "extension_not_connected"
    assert payload["envelope"]["error"]["message"] == EXTENSION_UNAVAILABLE_MESSAGE


def test_operation_commit_gate_rejects_stale_cancelled_superseded_and_duplicate_results() -> None:
    operation = create_screen_operation(
        source_type=SourceType.SCREEN_CAPTURE,
        operation_id="op_1",
        request_id="req_1",
    )

    assert can_commit_screen_result(
        operation=operation,
        response_operation_id="op_1",
        response_request_id="req_1",
        response_source_type="screen_capture",
        response_status="ready",
    )
    assert not can_commit_screen_result(
        operation=operation,
        response_operation_id="old_op",
        response_request_id="req_1",
        response_source_type="screen_capture",
        response_status="ready",
    )
    assert not can_commit_screen_result(
        operation=operation,
        response_operation_id="op_1",
        response_request_id="old_req",
        response_source_type="screen_capture",
        response_status="ready",
    )
    assert not can_commit_screen_result(
        operation=operation,
        response_operation_id="op_1",
        response_request_id="req_1",
        response_source_type="browser_extension",
        response_status="ready",
    )
    assert not can_commit_screen_result(
        operation=operation,
        response_operation_id="op_1",
        response_request_id="req_1",
        response_source_type="screen_capture",
        response_status="failed",
    )
    assert not can_commit_screen_result(
        operation=operation,
        response_operation_id="op_1",
        response_request_id="req_1",
        response_source_type="screen_capture",
        response_status="ready",
        committed_operation_ids={"op_1"},
    )
    assert not can_commit_screen_result(
        operation=cancel_operation(operation),
        response_operation_id="op_1",
        response_request_id="req_1",
        response_source_type="screen_capture",
        response_status="ready",
    )
    assert not can_commit_screen_result(
        operation=supersede_operation(operation, "op_2"),
        response_operation_id="op_1",
        response_request_id="req_1",
        response_source_type="screen_capture",
        response_status="ready",
    )


def test_operation_transitions_and_private_payload_are_safe() -> None:
    operation = create_screen_operation(source_type="screen_capture", operation_id="", request_id="")
    assert operation.operation_id.startswith("screen_operation_")
    assert operation.request_id.startswith("screen_request_")

    capturing = transition_operation(operation, ScreenOperationStatus.CAPTURING)
    processing = transition_operation(capturing, ScreenOperationStatus.PROCESSING)
    assert capturing.status == ScreenOperationStatus.CAPTURING
    assert processing.status == ScreenOperationStatus.CAPTURING

    payload = ScreenIntelligenceOrchestrator().execute_screen_capture(
        operation_id="op_private",
        request_id="req_private",
        execute_ocr=lambda: {
            "ok": True,
            "question": "Visible question?",
            "answer": "Visible answer.",
            "question_type": "general",
            "raw_vision_text": "private model trace",
        },
    )
    assert "private model trace" not in json.dumps(payload["envelope"])
