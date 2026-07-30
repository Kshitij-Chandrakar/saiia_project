from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any
from uuid import uuid4

from app.models.screen_intelligence import (
    EnvelopeStatus,
    ExtractionMetadata,
    ExtractionMetrics,
    ExtractionMethod,
    ExtractionResultEnvelope,
    ExtractionTiming,
    SafeErrorCode,
    SafeExtractionError,
    SourceType,
)
from app.services.normalized_question_service import with_screen_extraction_envelope

EXTENSION_UNAVAILABLE_MESSAGE = "Browser extension connection is not available yet."


class ScreenOperationStatus(str, Enum):
    IDLE = "idle"
    CREATED = "created"
    CAPTURING = "capturing"
    EXTRACTING = "extracting"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


VALID_TRANSITIONS = {
    ScreenOperationStatus.IDLE: {ScreenOperationStatus.CREATED},
    ScreenOperationStatus.CREATED: {
        ScreenOperationStatus.CAPTURING,
        ScreenOperationStatus.EXTRACTING,
        ScreenOperationStatus.FAILED,
        ScreenOperationStatus.CANCELLED,
        ScreenOperationStatus.SUPERSEDED,
    },
    ScreenOperationStatus.CAPTURING: {
        ScreenOperationStatus.EXTRACTING,
        ScreenOperationStatus.FAILED,
        ScreenOperationStatus.CANCELLED,
        ScreenOperationStatus.SUPERSEDED,
    },
    ScreenOperationStatus.EXTRACTING: {
        ScreenOperationStatus.PROCESSING,
        ScreenOperationStatus.FAILED,
        ScreenOperationStatus.CANCELLED,
        ScreenOperationStatus.SUPERSEDED,
    },
    ScreenOperationStatus.PROCESSING: {
        ScreenOperationStatus.READY,
        ScreenOperationStatus.FAILED,
        ScreenOperationStatus.CANCELLED,
        ScreenOperationStatus.SUPERSEDED,
    },
    ScreenOperationStatus.READY: set(),
    ScreenOperationStatus.FAILED: set(),
    ScreenOperationStatus.CANCELLED: set(),
    ScreenOperationStatus.SUPERSEDED: set(),
}


@dataclass(frozen=True)
class ScreenOperation:
    operation_id: str
    request_id: str
    source_type: SourceType
    status: ScreenOperationStatus = ScreenOperationStatus.CREATED
    committed: bool = False
    cancellation_reason: str = ""
    superseded_by_operation_id: str = ""

    @property
    def is_cancelled(self) -> bool:
        return self.status == ScreenOperationStatus.CANCELLED

    @property
    def is_superseded(self) -> bool:
        return self.status == ScreenOperationStatus.SUPERSEDED


def create_screen_operation(
    *,
    source_type: SourceType | str,
    operation_id: str | None = None,
    request_id: str | None = None,
) -> ScreenOperation:
    return ScreenOperation(
        operation_id=_safe_id(operation_id, "screen_operation"),
        request_id=_safe_id(request_id, "screen_request"),
        source_type=SourceType(source_type),
    )


def transition_operation(operation: ScreenOperation, next_status: ScreenOperationStatus | str) -> ScreenOperation:
    status = ScreenOperationStatus(next_status)
    if status == operation.status:
        return operation
    if status not in VALID_TRANSITIONS[operation.status]:
        return operation
    return replace(operation, status=status)


def cancel_operation(operation: ScreenOperation, reason: str = "operation_cancelled") -> ScreenOperation:
    if operation.status == ScreenOperationStatus.CANCELLED:
        return operation
    return replace(operation, status=ScreenOperationStatus.CANCELLED, cancellation_reason=reason)


def supersede_operation(operation: ScreenOperation, superseded_by_operation_id: str) -> ScreenOperation:
    if operation.status in {ScreenOperationStatus.READY, ScreenOperationStatus.FAILED, ScreenOperationStatus.CANCELLED}:
        return operation
    return replace(
        operation,
        status=ScreenOperationStatus.SUPERSEDED,
        superseded_by_operation_id=str(superseded_by_operation_id or ""),
    )


def can_commit_screen_result(
    *,
    operation: ScreenOperation,
    response_operation_id: str,
    response_request_id: str,
    response_source_type: str,
    response_status: str,
    committed_operation_ids: set[str] | None = None,
    has_usable_result: bool = True,
) -> bool:
    if committed_operation_ids and operation.operation_id in committed_operation_ids:
        return False
    return (
        operation.operation_id == response_operation_id
        and operation.request_id == response_request_id
        and operation.source_type.value == response_source_type
        and operation.status not in {
            ScreenOperationStatus.CANCELLED,
            ScreenOperationStatus.SUPERSEDED,
            ScreenOperationStatus.FAILED,
        }
        and response_status == EnvelopeStatus.READY.value
        and has_usable_result
    )


class ScreenIntelligenceOrchestrator:
    def execute_screen_capture(
        self,
        *,
        operation_id: str | None,
        request_id: str | None,
        execute_ocr: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        operation = create_screen_operation(
            source_type=SourceType.SCREEN_CAPTURE,
            operation_id=operation_id,
            request_id=request_id,
        )
        payload = execute_ocr()
        payload.update(
            {
                "operation_id": operation.operation_id,
                "request_id": operation.request_id,
                "source_type": SourceType.SCREEN_CAPTURE.value,
            }
        )
        return with_screen_extraction_envelope(
            payload,
            operation_id=operation.operation_id,
            request_id=operation.request_id,
        )

    def extension_unavailable(
        self,
        *,
        operation_id: str | None,
        request_id: str | None,
    ) -> dict[str, Any]:
        operation = create_screen_operation(
            source_type=SourceType.BROWSER_EXTENSION,
            operation_id=operation_id,
            request_id=request_id,
        )
        envelope = ExtractionResultEnvelope(
            request_id=operation.request_id,
            operation_id=operation.operation_id,
            source_type=SourceType.BROWSER_EXTENSION,
            status=EnvelopeStatus.FAILED,
            questions=[],
            selected_question_id=None,
            extraction=ExtractionMetadata(
                complete=False,
                confidence=0.0,
                missing_sections=[],
                warnings=[],
                method=ExtractionMethod.GENERIC_DOM,
            ),
            timing=ExtractionTiming(total_ms=0.0),
            metrics=ExtractionMetrics(
                screenshot_count=0,
                screen_model_request_count=0,
                automatic_fallback_count=0,
                correction_request_count=0,
                generation_request_count=0,
            ),
            error=SafeExtractionError(
                code=SafeErrorCode.EXTENSION_NOT_CONNECTED,
                message=EXTENSION_UNAVAILABLE_MESSAGE,
                retryable=True,
            ),
        )
        return {
            "ok": False,
            "operation_id": operation.operation_id,
            "request_id": operation.request_id,
            "source_type": SourceType.BROWSER_EXTENSION.value,
            "result_mode": "single",
            "question": "",
            "answer": "",
            "language": "",
            "code": "",
            "items": [],
            "question_count": 0,
            "incomplete_question_count": 0,
            "question_type": "none",
            "confidence": 0.0,
            "incomplete": True,
            "capture_ms": 0.0,
            "image_prepare_ms": 0.0,
            "upload_ms": 0.0,
            "screen_model_ms": 0.0,
            "response_parse_ms": 0.0,
            "overlay_render_ms": 0.0,
            "total_screen_pipeline_ms": 0.0,
            "vision_ms": 0.0,
            "vision_latency_ms": 0.0,
            "screenshot_count": 0,
            "screen_model_request_count": 0,
            "extraction_request_count": 0,
            "generation_request_count": 0,
            "automatic_fallback_count": 0,
            "correction_request_count": 0,
            "fallback_used": False,
            "screenshot_hid_saiia_windows": False,
            "raw_vision_text": "",
            "reason": "extension_not_connected",
            "error": EXTENSION_UNAVAILABLE_MESSAGE,
            "envelope": envelope.model_dump(mode="json"),
        }


def _safe_id(value: str | None, prefix: str) -> str:
    normalized = str(value or "").strip()
    return normalized or f"{prefix}_{uuid4().hex}"
