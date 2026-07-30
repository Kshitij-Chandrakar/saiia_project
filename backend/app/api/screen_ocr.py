import logging
import re
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.nlp.coding_quality_gate import build_editor_stub_contract, build_hackerrank_problem_contract
from app.services.normalized_question_service import with_screen_extraction_envelope
from app.services.screen_intelligence_orchestrator import ScreenIntelligenceOrchestrator
from app.services.screen_ocr_service import ScreenOcrError, ScreenOcrService
from app.services.screen_vision_service import ScreenVisionService

router = APIRouter(prefix="/api/screen", tags=["Screen OCR"])
logger = logging.getLogger("screen_ocr_api")
logging.basicConfig(level=logging.INFO)

screen_ocr_service = ScreenOcrService()
screen_vision_service = ScreenVisionService()
screen_intelligence_orchestrator = ScreenIntelligenceOrchestrator()


class ScreenOcrResponse(BaseModel):
    status: str
    extracted_text: str
    confidence: float | None = None
    ocr_ms: float | None = None
    text_length: int


class ActiveWindowAnalyzeResponse(BaseModel):
    ok: bool
    capture_target: str
    window_title: str = ""
    process_name: str = ""
    image_width: int = 0
    image_height: int = 0
    vision_provider: str = ""
    vision_model: str = ""
    raw_vision_text: str = ""
    raw_vision_json: str = ""
    cleaned_text: str = ""
    extracted_question: str = ""
    question_type: str = "none"
    is_question: bool = False
    confidence: float = 0.0
    capture_ms: float = 0.0
    vision_ms: float = 0.0
    vision_latency_ms: float = 0.0
    vision_fallback_used: bool = False
    vision_fallback_reason: str = ""
    vision_http_status: int | None = None
    vision_error: str = ""
    vision_timeout: bool = False
    vision_retry_after: str = ""
    screen_vision_fallback_model: str = ""
    screen_vision_detail: str = ""
    local_ocr_used: bool = False
    local_ocr_short_circuit_used: bool = False
    local_ocr_ms: float = 0.0
    local_ocr_confidence: float = 0.0
    local_ocr_error: str = ""
    primary_vision_ms: float = 0.0
    fallback_vision_ms: float = 0.0
    vision_model_used: str = ""
    extraction_confidence: float = 0.0
    fallback_ocr_used: bool = False
    screenshot_hid_saiia_windows: bool = False
    screenshot_debug_path: str = ""
    screen_platform_detected: str = "unknown"
    crop_used: bool = False
    crop_region: str = ""
    source_region: str = "unknown"
    extraction_retry_reason: str = ""
    rejected_ui_noise: bool = False
    rejected_code_boilerplate: bool = False
    ui_noise_ratio: float = 0.0
    raw_full_window_vision_json: str = ""
    raw_cropped_vision_json: str = ""
    final_extracted_question: str = ""
    full_problem_text: str = ""
    editor_text: str = ""
    input_format: str = ""
    output_format: str = ""
    sample_input: str = ""
    sample_output: str = ""
    problem_title: str = ""
    valid_problem_found: bool = False
    groq_vision_attempted: bool = False
    groq_vision_success: bool = False
    groq_vision_error: str = ""
    groq_vision_http_status: int | None = None
    groq_vision_raw_response_preview: str = ""
    groq_vision_parse_error: str = ""
    groq_vision_timeout: bool = False
    fallback_reason: str = ""
    reason: str = ""
    error: str | None = None


class ActiveWindowAnswerResponse(BaseModel):
    ok: bool
    operation_id: str = ""
    request_id: str = ""
    source_type: str = "screen_capture"
    capture_target: str = "active_external_window"
    window_title: str = ""
    process_name: str = ""
    original_image_width: int = 0
    original_image_height: int = 0
    image_width: int = 0
    image_height: int = 0
    encoded_image_bytes: int = 0
    vision_provider: str = ""
    vision_model: str = ""
    result_mode: str = "single"
    question: str = ""
    answer: str = ""
    language: str = ""
    code: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)
    question_count: int = 0
    incomplete_question_count: int = 0
    question_type: str = "none"
    confidence: float = 0.0
    incomplete: bool = False
    capture_ms: float = 0.0
    image_prepare_ms: float = 0.0
    upload_ms: float = 0.0
    screen_model_ms: float = 0.0
    response_parse_ms: float = 0.0
    overlay_render_ms: float = 0.0
    total_screen_pipeline_ms: float = 0.0
    vision_ms: float = 0.0
    vision_latency_ms: float = 0.0
    screenshot_count: int = 1
    screen_model_request_count: int = 1
    extraction_request_count: int = 1
    generation_request_count: int = 0
    automatic_fallback_count: int = 0
    correction_request_count: int = 0
    fallback_used: bool = False
    screenshot_hid_saiia_windows: bool = False
    raw_vision_text: str = ""
    reason: str = ""
    error: str | None = None
    envelope: dict[str, Any] | None = None


def _merge_unique_text(parts: list[str]) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = _strip_json_noise(str(part or "").strip())
        if not text:
            continue
        key = re.sub(r"\s+", " ", text).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return "\n\n".join(merged).strip()


def _strip_json_noise(value: str) -> str:
    diagnostic_key_pattern = re.compile(
        r"^\s*(?:INFO:|DEBUG:|WARNING:|ERROR:|coding runtime audit\b|"
        r"answer generation completed\b|hackerrank_context_ready\b|"
        r"missing_context_sections\b|full_problem_text_is_summary_only\b|"
        r"full_problem_text_contains_json_noise\b|generate_full_problem_text_len\b|"
        r"editor_text_present\b|input_format_used\b|output_format_used\b|"
        r"sample_tests_found\b|raw_vision_json\b)",
        re.IGNORECASE,
    )
    lines: list[str] = []
    for line in str(value or "").replace("\r\n", "\n").splitlines():
        stripped = line.strip()
        if stripped.startswith("{") and (
            '"is_question"' in stripped
            or "'is_question'" in stripped
            or '"question_type"' in stripped
            or "'question_type'" in stripped
            or '"raw_vision_json"' in stripped
        ):
            continue
        if diagnostic_key_pattern.search(stripped):
            continue
        cleaned = re.sub(r"\s*\{\s*['\"]is_question['\"]\s*:.*$", "", line).rstrip()
        cleaned = re.sub(r"\s*\{[^{}]*['\"]question_type['\"]\s*:\s*['\"]coding['\"].*$", "", cleaned).rstrip()
        if cleaned.strip():
            lines.append(cleaned)
    return "\n".join(lines).strip()


def _candidate_text_from_payload(payload: dict) -> str:
    merged_clean_text = _merge_unique_text(
        [
            payload.get("final_merged_problem", ""),
            payload.get("final_extracted_question", ""),
            payload.get("cleaned_text", ""),
            payload.get("extracted_question", ""),
        ]
    )
    if merged_clean_text:
        return merged_clean_text
    return _strip_json_noise(str(payload.get("raw_vision_text") or ""))


def _extract_editor_text_from_analyze_payload(payload: dict, full_problem_text: str) -> str:
    explicit = str(payload.get("editor_text") or "").strip()
    if explicit:
        return explicit

    blocks = re.split(r"\n\s*\n", full_problem_text)
    code_blocks: list[str] = []
    for block in blocks:
        text = block.strip()
        if not text:
            continue
        if build_editor_stub_contract(text).get("editor_stub_used"):
            code_blocks.append(text)
            continue
        if re.search(
            r"(?im)^\s*(?:def\s+\w+\s*\(|class\s+\w+\b|\w+\s*=\s*lambda\b|if\s+__name__\s*==\s*['\"]__main__['\"]\s*:)",
            text,
        ):
            code_blocks.append(text)

    return _merge_unique_text(code_blocks)


def _enrich_hackerrank_analyze_payload(payload: dict) -> dict:
    platform = str(payload.get("screen_platform_detected") or "").strip().lower()
    haystack = " ".join(
        str(payload.get(key) or "")
        for key in ("window_title", "process_name", "raw_vision_text", "cleaned_text", "final_extracted_question", "extracted_question")
    ).lower()
    if platform != "hackerrank" and "hackerrank" not in haystack:
        return payload

    full_problem_text = _merge_unique_text(
        [
            str(payload.get("full_problem_text") or "").strip(),
            _candidate_text_from_payload(payload),
        ]
    )
    editor_text = _extract_editor_text_from_analyze_payload(payload, full_problem_text)
    contract = build_hackerrank_problem_contract(
        problem_text=full_problem_text,
        editor_text=editor_text,
        platform_title=payload.get("window_title") or "",
        selected_language="python",
    )
    sample_tests = contract.get("sample_tests") or []
    first_sample = sample_tests[0] if sample_tests else {}
    enriched = {
        **payload,
        "screen_platform_detected": "hackerrank",
        "full_problem_text": full_problem_text,
        "editor_text": editor_text,
        "input_format": contract.get("input_format") or "",
        "output_format": contract.get("output_format") or "",
        "sample_input": first_sample.get("input", ""),
        "sample_output": first_sample.get("expected_output", ""),
        "problem_title": contract.get("problem_title") or "",
    }
    logger.info(
        "HackerRank analyze context analyze_full_problem_text_len=%s analyze_editor_text_len=%s input_format_used=%s output_format_used=%s sample_tests_found=%s problem_title=%s",
        len(enriched["full_problem_text"]),
        len(enriched["editor_text"]),
        bool(enriched["input_format"]),
        bool(enriched["output_format"]),
        len(sample_tests),
        enriched["problem_title"],
    )
    return enriched


@router.post("/ocr", response_model=ScreenOcrResponse)
async def screen_ocr(file: UploadFile = File(...)):
    try:
        content = await file.read()
        payload = screen_ocr_service.extract_text(
            filename=file.filename or "",
            content=content,
            content_type=file.content_type,
        )
        logger.info(
            "Screen OCR completed filename=%s content_type=%s text_length=%s confidence=%s ocr_ms=%s",
            file.filename,
            file.content_type,
            payload["text_length"],
            payload["confidence"],
            payload["ocr_ms"],
        )
        return ScreenOcrResponse(**payload)
    except ScreenOcrError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected screen OCR error filename=%s content_type=%s",
            file.filename,
            file.content_type,
        )
        raise HTTPException(
            status_code=500,
            detail="Screen OCR failed. Please paste or type the question manually.",
        ) from exc


@router.post("/analyze-active-window", response_model=ActiveWindowAnalyzeResponse)
async def analyze_active_window(
    file: UploadFile = File(...),
    window_title: str = Form(""),
    process_name: str = Form(""),
    capture_ms: float = Form(0.0),
    hid_saiia_windows: bool = Form(False),
):
    try:
        content = await file.read()
        payload = screen_vision_service.analyze_image(
            filename=file.filename or "",
            content=content,
            content_type=file.content_type,
            window_title=window_title,
            process_name=process_name,
            capture_ms=capture_ms,
            hid_saiia_windows=hid_saiia_windows,
        )
        payload = _enrich_hackerrank_analyze_payload(payload)
        logger.info(
            "Active window analyzed ok=%s provider=%s fallback_ocr=%s question_type=%s window_title=%s process_name=%s image=%sx%s vision_ms=%s analyze_full_problem_text_len=%s analyze_editor_text_len=%s",
            payload["ok"],
            payload["vision_provider"],
            payload["fallback_ocr_used"],
            payload["question_type"],
            payload["window_title"],
            payload["process_name"],
            payload["image_width"],
            payload["image_height"],
            payload["vision_ms"],
            len(str(payload.get("full_problem_text") or "")),
            len(str(payload.get("editor_text") or "")),
        )
        return ActiveWindowAnalyzeResponse(**payload)
    except Exception as exc:
        logger.exception(
            "Unexpected active window analysis error filename=%s window_title=%s process_name=%s",
            file.filename,
            window_title,
            process_name,
        )
        return ActiveWindowAnalyzeResponse(
            ok=False,
            capture_target="active_external_window",
            window_title=window_title,
            process_name=process_name,
            error="Active window analysis failed. Please try again.",
            reason=str(exc),
        )


@router.post("/analyze-active-window-answer", response_model=ActiveWindowAnswerResponse)
async def analyze_active_window_answer(
    file: UploadFile = File(...),
    window_title: str = Form(""),
    process_name: str = Form(""),
    capture_ms: float = Form(0.0),
    hid_saiia_windows: bool = Form(False),
    operation_id: str = Form(""),
    request_id: str = Form(""),
    source_type: str = Form("screen_capture"),
):
    try:
        content = await file.read()
        if source_type != "screen_capture":
            raise ValueError("OCR endpoint requires source_type=screen_capture")
        payload = screen_intelligence_orchestrator.execute_screen_capture(
            operation_id=operation_id,
            request_id=request_id,
            execute_ocr=lambda: screen_vision_service.answer_image(
                filename=file.filename or "",
                content=content,
                content_type=file.content_type,
                window_title=window_title,
                process_name=process_name,
                capture_ms=capture_ms,
                hid_saiia_windows=hid_saiia_windows,
            ),
        )
        logger.info(
            "Active window answered ok=%s provider=%s question_type=%s image=%sx%s sent=%sx%s encoded_bytes=%s prepare_ms=%s model_ms=%s parse_ms=%s screenshot_count=%s model_request_count=%s fallback_count=%s correction_count=%s",
            payload["ok"],
            payload["vision_provider"],
            payload["question_type"],
            payload["original_image_width"],
            payload["original_image_height"],
            payload["image_width"],
            payload["image_height"],
            payload["encoded_image_bytes"],
            payload["image_prepare_ms"],
            payload["screen_model_ms"],
            payload["response_parse_ms"],
            payload["screenshot_count"],
            payload["screen_model_request_count"],
            payload["automatic_fallback_count"],
            payload["correction_request_count"],
        )
        if not payload.get("ok"):
            payload["error"] = "The question could not be read clearly."
        return ActiveWindowAnswerResponse(**payload)
    except Exception as exc:
        logger.exception(
            "Unexpected active window answer error filename=%s window_title=%s process_name=%s",
            file.filename,
            window_title,
            process_name,
        )
        payload = with_screen_extraction_envelope(
            {
                "ok": False,
                "operation_id": operation_id,
                "request_id": request_id,
                "source_type": "screen_capture",
                "window_title": window_title,
                "process_name": process_name,
                "error": "The question could not be read clearly.",
                "reason": str(exc),
                "capture_ms": capture_ms,
                "screenshot_count": 1,
                "screen_model_request_count": 1,
                "automatic_fallback_count": 0,
                "correction_request_count": 0,
                "generation_request_count": 0,
            }
        )
        return ActiveWindowAnswerResponse(**payload)


@router.post("/extension-unavailable", response_model=ActiveWindowAnswerResponse)
async def extension_unavailable(
    operation_id: str = Form(""),
    request_id: str = Form(""),
):
    payload = screen_intelligence_orchestrator.extension_unavailable(
        operation_id=operation_id,
        request_id=request_id,
    )
    return ActiveWindowAnswerResponse(**payload)
