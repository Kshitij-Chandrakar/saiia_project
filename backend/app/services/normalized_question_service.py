from typing import Any
from uuid import uuid4

from app.models.screen_intelligence import (
    CodeContext,
    EnvelopeStatus,
    ExtractionMetadata,
    ExtractionMetrics,
    ExtractionMethod,
    ExtractionQuestionItem,
    ExtractionResultEnvelope,
    ExtractionTiming,
    LanguageSource,
    NormalizedAnswer,
    NormalizedQuestion,
    NormalizedQuestionType,
    SafeErrorCode,
    SafeExtractionError,
    SourceType,
    SubmissionMode,
    VisualContext,
)


QUESTION_TYPE_COMPATIBILITY = {
    "coding": NormalizedQuestionType.CODING,
    "debugging": NormalizedQuestionType.DEBUGGING,
    "output": NormalizedQuestionType.OUTPUT_PREDICTION,
    "output_prediction": NormalizedQuestionType.OUTPUT_PREDICTION,
    "mcq": NormalizedQuestionType.MCQ,
    "visual": NormalizedQuestionType.DIAGRAM,
    "diagram": NormalizedQuestionType.DIAGRAM,
    "chart": NormalizedQuestionType.CHART,
    "architecture": NormalizedQuestionType.ARCHITECTURE,
    "system_design": NormalizedQuestionType.SYSTEM_DESIGN,
    "technical": NormalizedQuestionType.TECHNICAL,
    "aptitude": NormalizedQuestionType.APTITUDE,
    "interview": NormalizedQuestionType.GENERAL,
    "general": NormalizedQuestionType.GENERAL,
    "none": NormalizedQuestionType.UNKNOWN,
    "": NormalizedQuestionType.UNKNOWN,
}


def normalize_question_type(value: Any) -> NormalizedQuestionType:
    key = str(value or "").strip().lower()
    return QUESTION_TYPE_COMPATIBILITY.get(key, NormalizedQuestionType.UNKNOWN)


def build_screen_extraction_envelope(
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    operation_id: str | None = None,
) -> ExtractionResultEnvelope:
    ok = bool(payload.get("ok"))
    questions = _build_questions(payload) if ok else []
    status = EnvelopeStatus.READY if questions else EnvelopeStatus.FAILED
    error = None if status == EnvelopeStatus.READY else _build_error(payload)
    confidence = _coerce_confidence(payload.get("confidence"))

    return ExtractionResultEnvelope(
        request_id=request_id or str(payload.get("request_id") or f"screen_request_{uuid4().hex}"),
        operation_id=operation_id or str(payload.get("operation_id") or f"screen_operation_{uuid4().hex}"),
        source_type=SourceType.SCREEN_CAPTURE,
        status=status,
        browser=None,
        questions=questions,
        selected_question_id=questions[0].question_id if len(questions) == 1 else None,
        extraction=ExtractionMetadata(
            complete=status == EnvelopeStatus.READY and not bool(payload.get("incomplete")),
            confidence=confidence,
            missing_sections=[],
            warnings=_build_warnings(payload),
            method=ExtractionMethod.SCREEN_VISION,
        ),
        timing=ExtractionTiming(
            capture_ms=_coerce_nonnegative_float(payload.get("capture_ms")),
            image_prepare_ms=_coerce_nonnegative_float(payload.get("image_prepare_ms")),
            screen_model_ms=_coerce_nonnegative_float(payload.get("screen_model_ms") or payload.get("vision_ms")),
            response_parse_ms=_coerce_nonnegative_float(payload.get("response_parse_ms")),
            overlay_render_ms=_optional_nonnegative_float(payload.get("overlay_render_ms")),
            total_ms=_coerce_nonnegative_float(payload.get("total_screen_pipeline_ms")),
        ),
        metrics=ExtractionMetrics(
            screenshot_count=_coerce_nonnegative_int(payload.get("screenshot_count"), default=1),
            screen_model_request_count=_coerce_nonnegative_int(payload.get("screen_model_request_count"), default=1),
            automatic_fallback_count=_coerce_nonnegative_int(payload.get("automatic_fallback_count"), default=0),
            correction_request_count=_coerce_nonnegative_int(payload.get("correction_request_count"), default=0),
            generation_request_count=_coerce_nonnegative_int(payload.get("generation_request_count"), default=0),
        ),
        error=error,
    )


def with_screen_extraction_envelope(
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    envelope = build_screen_extraction_envelope(
        payload,
        request_id=request_id,
        operation_id=operation_id,
    )
    return {**payload, "envelope": envelope.model_dump(mode="json")}


def _build_questions(payload: dict[str, Any]) -> list[ExtractionQuestionItem]:
    raw_items = payload.get("items")
    if isinstance(raw_items, list) and raw_items:
        return [
            item
            for index, raw_item in enumerate(raw_items, start=1)
            if isinstance(raw_item, dict)
            for item in [_build_question_item(raw_item, index)]
            if item is not None
        ]

    item = _build_question_item(payload, 1)
    return [item] if item else []


def _build_question_item(raw_item: dict[str, Any], index: int) -> ExtractionQuestionItem | None:
    statement = str(raw_item.get("question") or "").strip()
    answer_text = str(raw_item.get("answer") or "").strip()
    if not statement or not answer_text:
        return None

    question_type = normalize_question_type(raw_item.get("question_type"))
    language = str(raw_item.get("language") or "").strip() or None
    code = str(raw_item.get("code") or "").strip() or None

    return ExtractionQuestionItem(
        question_id=str(raw_item.get("question_id") or f"screen_question_{index}").strip(),
        display_number=str(raw_item.get("display_number") or "").strip(),
        question=NormalizedQuestion(
            question_type=question_type,
            statement=statement,
            answer=NormalizedAnswer(text=answer_text, code=code),
            visual_context=VisualContext(
                diagram_present=question_type in {NormalizedQuestionType.DIAGRAM, NormalizedQuestionType.ARCHITECTURE},
                chart_present=question_type == NormalizedQuestionType.CHART,
                image_context_required=question_type in {
                    NormalizedQuestionType.DIAGRAM,
                    NormalizedQuestionType.CHART,
                    NormalizedQuestionType.ARCHITECTURE,
                },
            ),
            code_context=CodeContext(
                selected_language=language,
                language_source=LanguageSource.UNKNOWN if language else None,
                submission_mode=_submission_mode_for(question_type, has_code=bool(code)),
            ),
        ),
        region=None,
    )


def _submission_mode_for(question_type: NormalizedQuestionType, *, has_code: bool) -> SubmissionMode | None:
    if question_type == NormalizedQuestionType.DEBUGGING:
        return SubmissionMode.DEBUG_FIX
    if question_type == NormalizedQuestionType.OUTPUT_PREDICTION:
        return SubmissionMode.OUTPUT_PREDICTION
    if question_type == NormalizedQuestionType.CODING:
        return SubmissionMode.STANDALONE_PROGRAM if has_code else None
    return None


def _build_error(payload: dict[str, Any]) -> SafeExtractionError:
    message = str(payload.get("error") or "The question could not be read clearly.").strip()
    reason = str(payload.get("reason") or "").lower()
    code = SafeErrorCode.UNREADABLE_SCREEN
    if "parse" in reason or "json" in reason:
        code = SafeErrorCode.RESPONSE_PARSE_FAILED
    elif "empty" in reason or "invalid" in reason:
        code = SafeErrorCode.INVALID_MODEL_RESPONSE
    elif "timeout" in reason:
        code = SafeErrorCode.PROVIDER_TIMEOUT
    elif "capture" in message.lower():
        code = SafeErrorCode.CAPTURE_FAILED
    return SafeExtractionError(code=code, message=message, retryable=True, details=None)


def _build_warnings(payload: dict[str, Any]) -> list[str]:
    ignored = _coerce_nonnegative_int(payload.get("incomplete_question_count"), default=0)
    return ["incomplete_questions_ignored"] if ignored else []


def _coerce_confidence(value: Any) -> float:
    return max(0.0, min(1.0, _coerce_nonnegative_float(value)))


def _coerce_nonnegative_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _optional_nonnegative_float(value: Any) -> float | None:
    if value is None:
        return None
    return _coerce_nonnegative_float(value)


def _coerce_nonnegative_int(value: Any, *, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
