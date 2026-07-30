import json
import logging
import re
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.nlp.classifier import (
    classify_personal_subtype,
    classify_question_by_rules,
    looks_like_coding_implementation_request,
    personal_question_allows_professional_context,
)
from app.nlp.answer_generator import AnswerGenerator, ProviderError
from app.nlp.answer_planner import build_answer_plan
from app.nlp.followup_resolver import FollowUpResolution, resolve_live_followup
from app.nlp.followup_intent_compiler import FollowUpIntentPlan, compile_followup_intent
from app.nlp.internal_marker_sanitizer import InternalMarkerStreamSanitizer, strip_internal_control_markers
from app.nlp.coding_quality_gate import (
    apply_hackerrank_context_gate as _quality_apply_hackerrank_context_gate,
    clean_extracted_problem_text as _quality_clean_extracted_problem_text,
    contains_extracted_problem_json_noise as _quality_contains_json_noise,
    evaluate_hackerrank_context_readiness as _quality_evaluate_hackerrank_context_readiness,
    force_context_not_ready_for_json_noise as _quality_force_context_not_ready_for_json_noise,
)
from app.services.job_context_service import JobContextError, JobContextService
from app.services.refinement_service import RefinementService
from app.services.resume_index_service import ResumeIndexError, ResumeIndexService

router = APIRouter()
logger = logging.getLogger("generate_api")
logging.basicConfig(level=logging.INFO)

generator = AnswerGenerator(include_context=True)
resume_index_service = ResumeIndexService()
job_context_service = JobContextService()
refinement_service = RefinementService()


def _infer_screen_problem_type(question: str, requested_type: str) -> str:
    normalized_type = str(requested_type or "").strip().lower()
    if normalized_type in {"coding", "debugging", "output"}:
        return normalized_type

    normalized_question = str(question or "").strip().lower()
    if not normalized_question:
        return normalized_type

    if any(
        marker in normalized_question
        for marker in (
            "find the output",
            "what is the output",
            "predict the output",
            "final output",
        )
    ):
        return "output"

    if any(
        marker in normalized_question
        for marker in (
            "debug this",
            "debug the following",
            "fix the bug",
            "correct the code",
        )
    ):
        return "debugging"

    coding_markers = (
        "hackerrank",
        "leetcode",
        "geeksforgeeks",
        "given an",
        "given a",
        "given the",
        "input format",
        "output format",
        "constraints",
        "sample input",
        "sample output",
        "write a function",
        "return the",
        "complete the function",
        "class solution",
        "def ",
        "print weird",
        "time complexity",
        "space complexity",
    )
    if any(marker in normalized_question for marker in coding_markers):
        return "coding"

    return normalized_type


def _analyze_coding_prompt_flags(question: str, answer: str) -> Dict[str, Any]:
    normalized_question = str(question or "").lower()
    normalized_answer = str(answer or "").lower()

    input_format_used = "input format" in normalized_question or "sample input" in normalized_question
    output_format_used = "output format" in normalized_question or "sample output" in normalized_question
    count_prefix_detected = bool(
        re.search(
            r"\b(ni|ki|n|k|m)\b|number of elements|number of integers|followed by \w+ space separated integers",
            normalized_question,
        )
    )
    hardcoded_sample_detected = any(
        marker in normalized_answer
        for marker in (
            "example usage",
            "student_marks = {",
            "alpha':",
            "beta':",
            "john",
            "alice",
        )
    )
    submission_ready_code = (
        "input()" in normalized_answer
        or "sys.stdin" in normalized_answer
        or "class solution" in normalized_answer
    ) and not hardcoded_sample_detected

    return {
        "input_format_used": input_format_used,
        "output_format_used": output_format_used,
        "count_prefix_detected": count_prefix_detected,
        "submission_ready_code": submission_ready_code,
        "hardcoded_sample_detected": hardcoded_sample_detected,
    }


def _excerpt(value: str, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _contains_json_noise(value: str) -> bool:
    return _quality_contains_json_noise(value)


def clean_extracted_problem_text(text: str) -> str:
    return _quality_clean_extracted_problem_text(text)


def _strip_json_noise(value: str) -> str:
    return clean_extracted_problem_text(value)


def _compose_problem_text_from_request(req: "GenerateRequest") -> str:
    base = _strip_json_noise(str(req.full_problem_text or req.question or "").strip())
    sections: list[tuple[str, str]] = [
        ("Problem Title", _strip_json_noise(str(req.problem_title or "").strip())),
        ("Input Format", _strip_json_noise(str(req.input_format or "").strip())),
        ("Output Format", _strip_json_noise(str(req.output_format or "").strip())),
        ("Sample Input 0", _strip_json_noise(str(req.sample_input or "").strip())),
        ("Sample Output 0", _strip_json_noise(str(req.sample_output or "").strip())),
    ]
    parts = [base] if base else []
    normalized_base = base.lower()
    for label, value in sections:
        if not value:
            continue
        if label.lower() in normalized_base and value.lower() in normalized_base:
            continue
        parts.append(f"{label}\n{value}")
    return "\n\n".join(parts).strip()


def _evaluate_hackerrank_context_readiness(
    *,
    platform: str,
    coding_answer_mode: bool,
    problem_text: str,
    input_format: str,
    output_format: str,
    sample_input: str,
    sample_output: str,
    sample_tests_found: int,
) -> dict:
    return _quality_evaluate_hackerrank_context_readiness(
        platform=platform,
        coding_answer_mode=coding_answer_mode,
        problem_text=problem_text,
        input_format=input_format,
        output_format=output_format,
        sample_input=sample_input,
        sample_output=sample_output,
        sample_tests_found=sample_tests_found,
    )


def _apply_hackerrank_context_gate(result: Dict[str, Any], context_status: dict) -> Dict[str, Any]:
    return _quality_apply_hackerrank_context_gate(result, context_status)


def _force_context_not_ready_for_json_noise(context_status: dict, json_noise_detected: bool) -> dict:
    return _quality_force_context_not_ready_for_json_noise(context_status, json_noise_detected)


class GenerateRequest(BaseModel):
    question: str
    original_question: Optional[str] = None
    followup_mode: Optional[str] = None
    followup_context: Optional[list[Dict[str, Any]]] = None
    full_problem_text: Optional[str] = None
    editor_text: Optional[str] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    sample_input: Optional[str] = None
    sample_output: Optional[str] = None
    problem_title: Optional[str] = None
    screen_platform_detected: Optional[str] = None
    category: str
    profile: Optional[Dict[str, Any]] = None
    source: Optional[str] = None
    question_type: Optional[str] = None
    screen_question_type: Optional[str] = None
    force_technical: Optional[bool] = False
    coding_answer_mode: Optional[bool] = False
    profile_context_used: Optional[bool] = True
    recording_ms: Optional[float] = None
    upload_ms: Optional[float] = None
    transcription_ms: Optional[float] = None
    classification_ms: Optional[float] = None
    profile_fetch_ms: Optional[float] = None
    total_pipeline_ms: Optional[float] = None


class GenerateResponse(BaseModel):
    answer: str
    provider: str
    model: str
    fallback_used: bool
    primary_provider: Optional[str] = None
    primary_model: Optional[str] = None
    refinement_provider: Optional[str] = None
    refinement_model: Optional[str] = None
    refinement_used: Optional[bool] = None
    refinement_status: Optional[str] = None
    refinement_job_id: Optional[str] = None
    error: Optional[str] = None
    generation_ms: float
    generation_time_ms: Optional[float] = None
    primary_generation_ms: Optional[float] = None
    refinement_generation_ms: Optional[float] = None
    recording_ms: Optional[float] = None
    upload_ms: Optional[float] = None
    transcription_ms: Optional[float] = None
    classification_ms: Optional[float] = None
    profile_fetch_ms: Optional[float] = None
    rag_ms: Optional[float] = None
    prompt_build_ms: Optional[float] = None
    groq_generation_ms: Optional[float] = None
    performance_mode: Optional[str] = None
    total_pipeline_ms: Optional[float] = None
    retrieval_used: Optional[bool] = None
    retrieved_chunk_count: Optional[int] = None
    profile_context_used: Optional[bool] = None
    generate_source: Optional[str] = None
    generate_question_type: Optional[str] = None
    generate_category: Optional[str] = None
    answer_mode: Optional[str] = None
    personal_subtype: Optional[str] = None
    personal_context_used: Optional[bool] = None
    creative_generation_used: Optional[bool] = None
    target_word_range: Optional[str] = None
    personal_validation_errors: Optional[list[str]] = None
    personal_answer_repaired: Optional[bool] = None
    answer_type: Optional[str] = None
    plan_confidence: Optional[float] = None
    profile_context_policy: Optional[str] = None
    job_context_policy: Optional[str] = None
    general_knowledge_policy: Optional[str] = None
    job_context_used: Optional[bool] = None
    validation_status: Optional[str] = None
    validation_issues_count: Optional[int] = None
    reasoning_effort: Optional[str] = None
    deterministic_validation_ms: Optional[float] = None
    semantic_validation_used: Optional[bool] = None
    semantic_validation_ms: Optional[float] = None
    semantic_validation_status: Optional[str] = None
    correction_ms: Optional[float] = None
    correction_status: Optional[str] = None
    answer_verified: Optional[bool] = None
    repetition_detected: Optional[bool] = None
    repetition_count: Optional[int] = None
    variation_enabled: Optional[bool] = None
    variation_profile: Optional[str] = None
    variation_applied: Optional[bool] = None
    variation_rewrite_used: Optional[bool] = None
    variation_status: Optional[str] = None
    similarity_score: Optional[float] = None
    previous_answer_count: Optional[int] = None
    variation_ms: Optional[float] = None
    coding_answer_mode: Optional[bool] = None
    coding_prompt_used: Optional[bool] = None
    refinement_coding_prompt_used: Optional[bool] = None
    input_format_used: Optional[bool] = None
    output_format_used: Optional[bool] = None
    count_prefix_detected: Optional[bool] = None
    submission_ready_code: Optional[bool] = None
    hardcoded_sample_detected: Optional[bool] = None
    coding_input_contract: Optional[Dict[str, Any]] = None
    regex_contract: Optional[Dict[str, Any]] = None
    llm_contract_used: Optional[bool] = None
    llm_contract: Optional[Dict[str, Any]] = None
    merged_coding_contract: Optional[Dict[str, Any]] = None
    contract_conflicts: Optional[list[str]] = None
    platform_detected: Optional[str] = None
    platform_adapter: Optional[str] = None
    hackerrank_contract_used: Optional[bool] = None
    hackerrank_full_problem_used: Optional[bool] = None
    problem_title: Optional[str] = None
    hackerrank_subdomain: Optional[str] = None
    problem_family: Optional[str] = None
    contract_sections_found: Optional[Dict[str, bool]] = None
    hackerrank_context_ready: Optional[bool] = None
    missing_context_sections: Optional[list[str]] = None
    full_problem_text_is_summary_only: Optional[bool] = None
    full_problem_text_contains_json_noise: Optional[bool] = None
    clean_full_problem_text_len: Optional[int] = None
    context_readiness_hard_block_applied: Optional[bool] = None
    submission_ready_block_reason: Optional[str] = None
    code_generation_mode: Optional[str] = None
    editor_stub_used: Optional[bool] = None
    editor_stub_mode: Optional[str] = None
    editor_required_symbols: Optional[list[str]] = None
    editor_required_functions: Optional[list[str]] = None
    editor_required_lambdas: Optional[list[str]] = None
    editor_required_classes: Optional[list[str]] = None
    editor_runner_detected: Optional[bool] = None
    editor_placeholder_lines: Optional[list[str]] = None
    editor_stub_validation_used: Optional[bool] = None
    editor_stub_validation_passed: Optional[bool] = None
    editor_stub_validation_errors: Optional[list[str]] = None
    function_stub_detected: Optional[bool] = None
    function_name: Optional[str] = None
    coding_quality_gate_used: Optional[bool] = None
    code_validation_used: Optional[bool] = None
    code_validation_passed: Optional[bool] = None
    code_validation_errors: Optional[list[str]] = None
    python_syntax_validation_used: Optional[bool] = None
    python_syntax_valid: Optional[bool] = None
    incomplete_code_detected: Optional[bool] = None
    incomplete_code_errors: Optional[list[str]] = None
    required_stub_preserved: Optional[bool] = None
    standalone_solution_rejected: Optional[bool] = None
    function_stub_completeness_validation_used: Optional[bool] = None
    function_stub_completeness_passed: Optional[bool] = None
    function_stub_completeness_errors: Optional[list[str]] = None
    duplicate_function_definition_detected: Optional[bool] = None
    partial_function_snippet_detected: Optional[bool] = None
    class_stub_detected: Optional[bool] = None
    class_name: Optional[str] = None
    required_methods: Optional[list[str]] = None
    missing_required_methods: Optional[list[str]] = None
    custom_class_validation_used: Optional[bool] = None
    custom_class_validation_passed: Optional[bool] = None
    custom_class_validation_errors: Optional[list[str]] = None
    builtin_complex_only_rejected: Optional[bool] = None
    output_format_requires_custom_complex: Optional[bool] = None
    output_decimal_places: Optional[int] = None
    output_order_validation_used: Optional[bool] = None
    output_order_validation_passed: Optional[bool] = None
    output_order_validation_errors: Optional[list[str]] = None
    sample_tests_found: Optional[int] = None
    sample_tests_source: Optional[str] = None
    sample_tests_ran: Optional[bool] = None
    sample_tests_skipped_reason: Optional[str] = None
    sample_tests_passed: Optional[bool] = None
    sample_test_errors: Optional[list[str]] = None
    sample_actual_output: Optional[str] = None
    sample_expected_output: Optional[str] = None
    function_test_harness_used: Optional[bool] = None
    function_test_harness_name: Optional[str] = None
    class_test_harness_used: Optional[bool] = None
    class_test_harness_name: Optional[str] = None
    correction_pass_used: Optional[bool] = None
    correction_attempts: Optional[int] = None
    correction_reason: Optional[str] = None
    correction_pass_needed: Optional[bool] = None
    correction_skip_reason: Optional[str] = None
    correction_failure_reason: Optional[str] = None
    correction_pass_failed: Optional[bool] = None
    correction_prompt_len: Optional[int] = None
    correction_model: Optional[str] = None
    correction_retry_used: Optional[bool] = None
    coding_prompt_len: Optional[int] = None
    compact_contract_used: Optional[bool] = None
    raw_context_trimmed: Optional[bool] = None
    coding_max_tokens: Optional[int] = None
    prompt_token_estimate: Optional[int] = None
    requested_completion_tokens: Optional[int] = None
    primary_generation_rate_limited: Optional[bool] = None
    retry_after_seconds: Optional[float] = None
    primary_retry_used: Optional[bool] = None
    primary_retry_skipped_reason: Optional[str] = None
    unverified_code_warning: Optional[str] = None
    fallback_enabled: Optional[bool] = None
    fallback_reason: Optional[str] = None
    fallback_unavailable_reason: Optional[str] = None
    coding_runtime_audit: Optional[Dict[str, Any]] = None
    original_question: Optional[str] = None
    resolved_question: Optional[str] = None
    follow_up_detected: Optional[bool] = None
    follow_up_confidence: Optional[float] = None
    follow_up_resolution_status: Optional[str] = None
    follow_up_resolution_method: Optional[str] = None
    follow_up_context_entry_ids: Optional[list[str]] = None
    follow_up_topic: Optional[str] = None
    follow_up_resolution_ms: Optional[float] = None
    clarification_required: Optional[bool] = None
    clarification_question: Optional[str] = None
    reference_status: Optional[str] = None
    reference_topic: Optional[str] = None
    requested_action: Optional[str] = None
    requested_output: Optional[str] = None
    resolved_language: Optional[str] = None
    platform_mode: Optional[str] = None
    context_entry_count: Optional[int] = None
    compilation_method: Optional[str] = None
    compilation_confidence: Optional[float] = None
    task_compilation_ms: Optional[float] = None
    structured_coding_answer_used: Optional[bool] = None
    coding_validation_status: Optional[str] = None
    coding_answer: Optional[Dict[str, Any]] = None


class RefinementStatusResponse(BaseModel):
    job_id: str
    refinement_provider: str
    model: str
    refinement_status: str
    refined_answer: Optional[str] = None
    error: Optional[str] = None


def _queue_parallel_refinement(
    *,
    req: GenerateRequest,
    saved_job_context: Optional[Dict[str, Any]],
    retrieval: Dict[str, Any],
    result: Dict[str, Any],
) -> Optional[str]:
    return None


def _stream_event(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str) + "\n"


def _stream_safe_metadata(
    *,
    result: Dict[str, Any],
    req: GenerateRequest,
    retrieval: Dict[str, Any],
    retrieved_chunks: list[dict[str, Any]],
    use_profile_context: bool,
    use_job_context: bool,
    saved_job_context: Dict[str, Any],
    source: str,
    screen_question_type: str,
    routed_category: str,
    coding_answer_mode: bool,
    total_pipeline_ms: Optional[float],
    followup_resolution: Optional[FollowUpResolution] = None,
    followup_intent: Optional[FollowUpIntentPlan] = None,
) -> Dict[str, Any]:
    metadata = {
        "answer": result.get("answer") or "",
        "provider": result.get("provider") or "",
        "model": result.get("model") or "",
        "primary_provider": result.get("primary_provider"),
        "primary_model": result.get("primary_model"),
        "fallback_used": bool(result.get("fallback_used")),
        "fallback_reason": result.get("fallback_reason"),
        "fallback_enabled": result.get("fallback_enabled"),
        "error": result.get("error"),
        "generation_ms": result.get("generation_ms"),
        "generation_time_ms": result.get("generation_time_ms", result.get("generation_ms")),
        "primary_generation_ms": result.get("primary_generation_ms"),
        "openai_generation_ms": result.get("openai_generation_ms"),
        "groq_generation_ms": result.get("groq_generation_ms"),
        "recording_ms": req.recording_ms,
        "upload_ms": req.upload_ms,
        "transcription_ms": req.transcription_ms,
        "classification_ms": req.classification_ms,
        "profile_fetch_ms": req.profile_fetch_ms,
        "rag_ms": retrieval.get("retrieval_ms"),
        "prompt_build_ms": result.get("prompt_build_ms"),
        "performance_mode": settings.PERFORMANCE_MODE,
        "total_pipeline_ms": total_pipeline_ms,
        "retrieval_used": bool(retrieval.get("retrieval_used")),
        "retrieved_chunk_count": len(retrieved_chunks),
        "profile_context_used": use_profile_context,
        "job_context_used": bool(use_job_context and saved_job_context.get("saved")),
        "answer_type": result.get("answer_type"),
        "plan_confidence": result.get("plan_confidence"),
        "profile_context_policy": result.get("profile_context_policy"),
        "job_context_policy": result.get("job_context_policy"),
        "general_knowledge_policy": result.get("general_knowledge_policy"),
        "validation_status": result.get("validation_status"),
        "validation_issues_count": result.get("validation_issues_count"),
        "reasoning_effort": result.get("reasoning_effort"),
        "deterministic_validation_ms": result.get("deterministic_validation_ms"),
        "semantic_validation_used": result.get("semantic_validation_used"),
        "semantic_validation_ms": result.get("semantic_validation_ms"),
        "semantic_validation_status": result.get("semantic_validation_status"),
        "correction_ms": result.get("correction_ms"),
        "correction_status": result.get("correction_status"),
        "answer_verified": result.get("answer_verified"),
        "repetition_detected": result.get("repetition_detected"),
        "repetition_count": result.get("repetition_count"),
        "variation_enabled": result.get("variation_enabled"),
        "variation_profile": result.get("variation_profile"),
        "variation_applied": result.get("variation_applied"),
        "variation_rewrite_used": result.get("variation_rewrite_used"),
        "variation_status": result.get("variation_status"),
        "similarity_score": result.get("similarity_score"),
        "previous_answer_count": result.get("previous_answer_count"),
        "variation_ms": result.get("variation_ms"),
        "generate_source": source or None,
        "generate_question_type": screen_question_type or None,
        "generate_category": result.get("answer_category") or routed_category,
        "coding_answer_mode": coding_answer_mode,
        "coding_prompt_used": result.get("coding_prompt_used"),
        "refinement_provider": result.get("refinement_provider"),
        "refinement_model": result.get("refinement_model"),
        "refinement_used": result.get("refinement_used"),
        "refinement_status": result.get("refinement_status"),
        "refinement_job_id": None,
        "coding_runtime_audit": result.get("coding_runtime_audit"),
        "structured_coding_answer_used": bool(result.get("coding_answer")),
        "coding_validation_status": result.get("coding_validation_status"),
        "coding_answer": result.get("coding_answer"),
    }
    if followup_resolution:
        metadata.update(followup_resolution.to_metadata())
    metadata.update(_followup_intent_metadata(followup_intent, req.followup_context))
    return metadata


def _resolve_request_followup(req: GenerateRequest, *, source: str) -> FollowUpResolution:
    screen_kind = str(req.question_type or req.screen_question_type or "").strip().lower()
    if source == "screen" and screen_kind in {"coding", "debugging", "output"}:
        original = str(req.original_question or req.question or "").strip()
        return FollowUpResolution(
            False,
            original,
            original,
            "standalone",
            "none",
            context_mode="screen",
            reason="screen_structured_problem",
        )
    mode = str(req.followup_mode or ("screen" if source == "screen" else "answer")).strip().lower()
    if mode not in {"answer", "screen", "chat"}:
        mode = "answer"
    return resolve_live_followup(
        question=str(req.original_question or req.question or ""),
        mode=mode,
        context_entries=req.followup_context or [],
        enabled=settings.ENABLE_LIVE_FOLLOWUP_RESOLUTION,
        history_limit=settings.FOLLOWUP_HISTORY_LIMIT,
        ttl_seconds=settings.FOLLOWUP_CONTEXT_TTL_SECONDS,
    )


def _compile_request_followup_intent(
    req: GenerateRequest,
    *,
    source: str,
    followup_resolution: FollowUpResolution,
) -> FollowUpIntentPlan:
    mode = str(req.followup_mode or ("screen" if source == "screen" else "answer")).strip().lower()
    if mode not in {"answer", "screen", "chat"}:
        mode = "answer"
    return compile_followup_intent(
        question=str(req.original_question or req.question or ""),
        mode=mode,
        context_entries=req.followup_context or [],
        resolution=followup_resolution,
        default_language="python",
    )


def _followup_intent_metadata(plan: Optional[FollowUpIntentPlan], context_entries: Optional[list[Dict[str, Any]]]) -> Dict[str, Any]:
    if not plan:
        return {}
    return {
        "reference_status": plan.reference_status,
        "reference_topic": plan.reference_topic,
        "requested_action": plan.requested_action,
        "requested_output": plan.requested_output,
        "resolved_language": plan.programming_language,
        "platform_mode": plan.platform_mode,
        "context_entry_count": len(context_entries or []),
        "compilation_method": plan.resolution_method,
        "compilation_confidence": plan.confidence,
        "task_compilation_ms": plan.resolution_ms,
    }


@router.post("/stream")
async def generate_answer_stream(req: GenerateRequest):
    if not settings.ENABLE_TRUE_ANSWER_STREAMING:
        raise HTTPException(status_code=404, detail="True answer streaming is disabled.")
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="`question` field cannot be empty.")
    if not req.category or not req.category.strip():
        raise HTTPException(status_code=400, detail="`category` field cannot be empty.")

    request_id = uuid.uuid4().hex
    request_started = time.perf_counter()

    async def events():
        source = str(req.source or "").strip().lower()
        followup_resolution = _resolve_request_followup(req, source=source)
        followup_intent = (
            _compile_request_followup_intent(req, source=source, followup_resolution=followup_resolution)
            if settings.ENABLE_FOLLOWUP_INTENT_COMPILER
            else None
        )
        effective_question = (
            followup_intent.resolved_question
            if followup_intent and followup_intent.follow_up_detected and not followup_intent.needs_clarification
            else followup_resolution.resolved_question or str(req.question or "").strip()
        )
        if followup_resolution.resolution_status == "needs_clarification":
            clarification = followup_resolution.clarification_question or "Which earlier topic should I connect this follow-up to?"
            yield _stream_event(
                {
                    "type": "start",
                    "request_id": request_id,
                    "provider": "local",
                    "model": "deterministic_followup_resolver",
                }
            )
            yield _stream_event({"type": "delta", "request_id": request_id, "text": clarification})
            metadata = {
                "answer": clarification,
                "provider": "local",
                "model": "deterministic_followup_resolver",
                "primary_provider": "local",
                "primary_model": "deterministic_followup_resolver",
                "fallback_used": False,
                "generation_ms": 0.0,
                "generation_time_ms": 0.0,
                "primary_generation_ms": 0.0,
                "recording_ms": req.recording_ms,
                "upload_ms": req.upload_ms,
                "transcription_ms": req.transcription_ms,
                "classification_ms": req.classification_ms,
                "profile_fetch_ms": req.profile_fetch_ms,
                "rag_ms": 0.0,
                "retrieval_used": False,
                "retrieved_chunk_count": 0,
                "profile_context_used": False,
                "job_context_used": False,
                "generate_source": source or None,
                "generate_category": req.category,
                "total_pipeline_ms": round((time.perf_counter() - request_started) * 1000, 2),
            }
            metadata.update(followup_resolution.to_metadata())
            metadata.update(_followup_intent_metadata(followup_intent, req.followup_context))
            yield _stream_event({"type": "metadata", "request_id": request_id, "metadata": metadata})
            yield _stream_event({"type": "done", "request_id": request_id})
            return
        requested_question_type = str(req.question_type or req.screen_question_type or "").strip().lower()
        screen_question_type = (
            _infer_screen_problem_type(effective_question, requested_question_type)
            if source == "screen"
            else requested_question_type
        )
        effective_category = "technical" if req.force_technical else req.category
        if source == "screen" and screen_question_type in {"coding", "debugging", "output"}:
            effective_category = "technical"
        routed_category = classify_question_by_rules(effective_question) or effective_category
        personal_professional_context_allowed = personal_question_allows_professional_context(effective_question)
        coding_intent = looks_like_coding_implementation_request(effective_question)
        if followup_intent and followup_intent.requested_output in {
            "structured_coding_answer",
            "coding_optimization",
            "code_explanation",
            "complexity_analysis",
        }:
            coding_intent = followup_intent.requested_output == "structured_coding_answer"
        if coding_intent and not screen_question_type:
            screen_question_type = "coding"
        coding_answer_mode = bool(req.coding_answer_mode) or coding_intent or (
            source == "screen" and screen_question_type in {"coding", "debugging", "output"}
        )
        generation_question = str(effective_question or "").strip()
        generation_problem_text = _compose_problem_text_from_request(req)
        generation_editor_text = str(req.editor_text or "").strip()
        if source == "screen" and screen_question_type in {"coding", "debugging", "output"} and generation_problem_text:
            generation_question = generation_problem_text
        answer_plan = build_answer_plan(
            question=generation_question,
            category=effective_category,
            source=source,
            screen_question_type=screen_question_type,
        )
        suppress_personal_context = (
            source == "screen"
            and screen_question_type in {"coding", "debugging", "output", "visual", "mcq", "architecture"}
        )
        suppress_personal_context = suppress_personal_context or (
            routed_category == "personal" and not personal_professional_context_allowed
        )
        use_profile_context = (
            bool(req.profile_context_used)
            and not suppress_personal_context
            and answer_plan.profile_context_policy != "FORBIDDEN"
        )
        use_job_context = answer_plan.job_context_policy != "FORBIDDEN"
        accumulated_answer = ""
        first_delta_ms = None
        primary_result = None
        stream_sanitizer = InternalMarkerStreamSanitizer()
        stream_sanitizer_ms = 0.0
        prefix_hold_started: Optional[float] = None
        initial_prefix_hold_ms = 0.0

        yield _stream_event(
            {
                "type": "start",
                "request_id": request_id,
                "provider": "openai",
                "model": settings.OPENAI_MODEL,
            }
        )
        try:
            saved_job_context = job_context_service.get_context() if use_job_context else {"saved": False}
            retrieval = (
                resume_index_service.retrieve(
                    question=generation_question,
                    category=effective_category,
                    limit=settings.RAG_RETRIEVAL_LIMIT,
                )
                if use_profile_context
                else {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0}
            )
            retrieval_used = retrieval["retrieval_used"]
            retrieved_chunks = retrieval["retrieved_chunks"]
            if retrieval["retrieval_ms"] > settings.RAG_TIMEOUT_MS:
                retrieval_used = False
                retrieved_chunks = []
            retrieval["retrieval_used"] = retrieval_used
            retrieval["retrieved_chunks"] = retrieved_chunks

            for stream_item in generator.stream_openai_primary_answer(
                question=generation_question,
                question_type=effective_category,
                profile=(req.profile or {}) if use_profile_context else {},
                retrieved_snippets=retrieved_chunks,
                job_context=saved_job_context if use_profile_context and saved_job_context.get("saved") else None,
                source=source,
                question_context_type=screen_question_type,
                screen_question_type=screen_question_type,
                coding_answer_mode=coding_answer_mode,
                profile_context_enabled=use_profile_context,
                editor_text=generation_editor_text,
                answer_plan=answer_plan,
            ):
                if stream_item.get("type") == "delta":
                    text = str(stream_item.get("text") or "")
                    if not text:
                        continue
                    sanitize_started = time.perf_counter()
                    text = stream_sanitizer.feed(text)
                    stream_sanitizer_ms += (time.perf_counter() - sanitize_started) * 1000
                    if not text and stream_sanitizer.stats.stream_prefix_buffered and prefix_hold_started is None:
                        prefix_hold_started = time.perf_counter()
                    if first_delta_ms is None:
                        if not text:
                            continue
                        if prefix_hold_started is not None and initial_prefix_hold_ms == 0.0:
                            initial_prefix_hold_ms = round((time.perf_counter() - prefix_hold_started) * 1000, 2)
                        first_delta_ms = round((time.perf_counter() - request_started) * 1000, 2)
                    accumulated_answer += text
                    yield _stream_event({"type": "delta", "request_id": request_id, "text": text})
                elif stream_item.get("type") == "primary_result":
                    primary_result = stream_item.get("result")

            sanitize_started = time.perf_counter()
            remaining_text = stream_sanitizer.flush()
            stream_sanitizer_ms += (time.perf_counter() - sanitize_started) * 1000
            if remaining_text:
                if first_delta_ms is None:
                    if prefix_hold_started is not None and initial_prefix_hold_ms == 0.0:
                        initial_prefix_hold_ms = round((time.perf_counter() - prefix_hold_started) * 1000, 2)
                    first_delta_ms = round((time.perf_counter() - request_started) * 1000, 2)
                accumulated_answer += remaining_text
                yield _stream_event({"type": "delta", "request_id": request_id, "text": remaining_text})

            if primary_result is None:
                raise ProviderError(
                    "OpenAI stream ended without a usable answer.",
                    provider="openai",
                    model=settings.OPENAI_MODEL,
                    error_type="empty_response",
                    phase="primary_generation_stream",
                )

            result = generator.generate_answer(
                question=generation_question,
                question_type=effective_category,
                profile=(req.profile or {}) if use_profile_context else {},
                retrieved_snippets=retrieved_chunks,
                job_context=saved_job_context if use_profile_context and saved_job_context.get("saved") else None,
                source=source,
                question_context_type=screen_question_type,
                screen_question_type=screen_question_type,
                coding_answer_mode=coding_answer_mode,
                profile_context_enabled=use_profile_context,
                editor_text=generation_editor_text,
                answer_plan=answer_plan,
                primary_result_override=primary_result,
            )
            context_status = _evaluate_hackerrank_context_readiness(
                platform=str(req.screen_platform_detected or result.get("platform_detected") or ""),
                coding_answer_mode=coding_answer_mode,
                problem_text=generation_problem_text,
                input_format=str(req.input_format or ""),
                output_format=str(req.output_format or ""),
                sample_input=str(req.sample_input or ""),
                sample_output=str(req.sample_output or ""),
                sample_tests_found=int(result.get("sample_tests_found") or 0),
            )
            original_json_noise_detected = _contains_json_noise(str(req.full_problem_text or req.question or ""))
            context_status = _force_context_not_ready_for_json_noise(context_status, original_json_noise_detected)
            result = _apply_hackerrank_context_gate(result, context_status)
            total_pipeline_ms = req.total_pipeline_ms
            if total_pipeline_ms is None:
                total_pipeline_ms = round(
                    (
                        (req.recording_ms or 0)
                        + (req.upload_ms or 0)
                        + (req.transcription_ms or 0)
                        + (req.classification_ms or 0)
                        + (req.profile_fetch_ms or 0)
                        + retrieval["retrieval_ms"]
                        + (result.get("generation_ms") or 0)
                    ),
                    2,
                )
            final_answer = str(result.get("answer") or "")
            if final_answer and final_answer != accumulated_answer:
                yield _stream_event({"type": "replace", "request_id": request_id, "answer": final_answer})
            metadata = _stream_safe_metadata(
                result=result,
                req=req,
                retrieval=retrieval,
                retrieved_chunks=retrieved_chunks,
                use_profile_context=use_profile_context,
                use_job_context=use_job_context,
                saved_job_context=saved_job_context,
                source=source,
                screen_question_type=screen_question_type,
                routed_category=routed_category,
                coding_answer_mode=coding_answer_mode,
                total_pipeline_ms=total_pipeline_ms,
                followup_resolution=followup_resolution,
                followup_intent=followup_intent,
            )
            metadata["time_to_first_visible_text_ms"] = first_delta_ms
            metadata["stream_duration_ms"] = round((time.perf_counter() - request_started) * 1000, 2)
            metadata["stream_sanitizer_ms"] = round(stream_sanitizer_ms, 4)
            metadata["initial_prefix_hold_ms"] = initial_prefix_hold_ms
            metadata["internal_marker_removed_count"] = stream_sanitizer.stats.marker_removed_count
            metadata["stream_prefix_buffered"] = stream_sanitizer.stats.stream_prefix_buffered
            metadata["stream_sanitizer_flush_used"] = stream_sanitizer.stats.flush_used
            metadata["category_metadata_separated"] = True
            metadata["category_source"] = "classifier"
            if stream_sanitizer.stats.marker_removed_count:
                logger.info(
                    "internal_marker_detected request_id=%s mode=%s internal_marker_removed_count=%s stream_prefix_buffered=%s stream_sanitizer_flush_used=%s category_metadata_separated=%s category_source=%s stream_sanitizer_ms=%s",
                    request_id,
                    source or "answer",
                    stream_sanitizer.stats.marker_removed_count,
                    stream_sanitizer.stats.stream_prefix_buffered,
                    stream_sanitizer.stats.flush_used,
                    True,
                    "classifier",
                    round(stream_sanitizer_ms, 4),
                )
            yield _stream_event({"type": "metadata", "request_id": request_id, "metadata": metadata})
            yield _stream_event({"type": "done", "request_id": request_id})
        except ProviderError as exc:
            logger.warning(
                "stream_generation_provider_error request_id=%s provider=%s model=%s error_type=%s partial=%s",
                request_id,
                exc.provider,
                exc.model,
                exc.error_type,
                bool(accumulated_answer.strip()),
            )
            if not accumulated_answer.strip() and settings.ENABLE_ANSWER_PROVIDER_FALLBACK:
                try:
                    fallback = generator.generate_answer(
                        question=generation_question,
                        question_type=effective_category,
                        profile=(req.profile or {}) if use_profile_context else {},
                        retrieved_snippets=[],
                        job_context=None,
                        source=source,
                        question_context_type=screen_question_type,
                        screen_question_type=screen_question_type,
                        coding_answer_mode=coding_answer_mode,
                        profile_context_enabled=use_profile_context,
                        editor_text=generation_editor_text,
                        answer_plan=answer_plan,
                    )
                    fallback_answer = str(fallback.get("answer") or "")
                    if fallback_answer:
                        fallback_answer = strip_internal_control_markers(fallback_answer)
                        yield _stream_event({"type": "delta", "request_id": request_id, "text": fallback_answer})
                    fallback["fallback_used"] = True
                    fallback["fallback_reason"] = str(exc.error_type or "openai_stream_failed")
                    metadata = _stream_safe_metadata(
                        result=fallback,
                        req=req,
                        retrieval={"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0},
                        retrieved_chunks=[],
                        use_profile_context=use_profile_context,
                        use_job_context=False,
                        saved_job_context={"saved": False},
                        source=source,
                        screen_question_type=screen_question_type,
                        routed_category=routed_category,
                        coding_answer_mode=coding_answer_mode,
                        total_pipeline_ms=round((time.perf_counter() - request_started) * 1000, 2),
                        followup_resolution=followup_resolution,
                        followup_intent=followup_intent,
                    )
                    yield _stream_event({"type": "metadata", "request_id": request_id, "metadata": metadata})
                    yield _stream_event({"type": "done", "request_id": request_id})
                    return
                except Exception:
                    logger.warning("stream_generation_fallback_failed request_id=%s", request_id)
            yield _stream_event(
                {
                    "type": "error",
                    "request_id": request_id,
                    "error": str(exc.error_type or "provider_error"),
                    "partial": bool(accumulated_answer.strip()),
                }
            )
            yield _stream_event({"type": "done", "request_id": request_id, "incomplete": bool(accumulated_answer.strip())})
        except Exception as exc:
            logger.exception("stream_generation_failed request_id=%s error_type=%s", request_id, exc.__class__.__name__)
            yield _stream_event(
                {
                    "type": "error",
                    "request_id": request_id,
                    "error": "stream_generation_failed",
                    "partial": bool(accumulated_answer.strip()),
                }
            )
            yield _stream_event({"type": "done", "request_id": request_id, "incomplete": bool(accumulated_answer.strip())})

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/", response_model=GenerateResponse)
async def generate_answer(req: GenerateRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="`question` field cannot be empty.")
    if not req.category or not req.category.strip():
        raise HTTPException(status_code=400, detail="`category` field cannot be empty.")

    started = time.perf_counter()
    source = str(req.source or "").strip().lower()
    followup_resolution = _resolve_request_followup(req, source=source)
    followup_intent = (
        _compile_request_followup_intent(req, source=source, followup_resolution=followup_resolution)
        if settings.ENABLE_FOLLOWUP_INTENT_COMPILER
        else None
    )
    effective_question = (
        followup_intent.resolved_question
        if followup_intent and followup_intent.follow_up_detected and not followup_intent.needs_clarification
        else followup_resolution.resolved_question or str(req.question or "").strip()
    )
    if followup_resolution.resolution_status == "needs_clarification":
        clarification = followup_resolution.clarification_question or "Which earlier topic should I connect this follow-up to?"
        metadata = followup_resolution.to_metadata()
        metadata.update(_followup_intent_metadata(followup_intent, req.followup_context))
        return GenerateResponse(
            answer=clarification,
            provider="local",
            model="deterministic_followup_resolver",
            fallback_used=False,
            primary_provider="local",
            primary_model="deterministic_followup_resolver",
            error=None,
            generation_ms=0.0,
            generation_time_ms=0.0,
            primary_generation_ms=0.0,
            recording_ms=req.recording_ms,
            upload_ms=req.upload_ms,
            transcription_ms=req.transcription_ms,
            classification_ms=req.classification_ms,
            profile_fetch_ms=req.profile_fetch_ms,
            rag_ms=0.0,
            prompt_build_ms=0.0,
            performance_mode=settings.PERFORMANCE_MODE,
            total_pipeline_ms=round((time.perf_counter() - started) * 1000, 2),
            retrieval_used=False,
            retrieved_chunk_count=0,
            profile_context_used=False,
            job_context_used=False,
            generate_source=source or None,
            generate_category=req.category,
            original_question=metadata["original_question"],
            resolved_question=metadata["resolved_question"],
            follow_up_detected=metadata["follow_up_detected"],
            follow_up_confidence=metadata["follow_up_confidence"],
            follow_up_resolution_status=metadata["follow_up_resolution_status"],
            follow_up_resolution_method=metadata["follow_up_resolution_method"],
            follow_up_context_entry_ids=metadata["follow_up_context_entry_ids"],
            follow_up_topic=metadata["follow_up_topic"],
            follow_up_resolution_ms=metadata["follow_up_resolution_ms"],
            clarification_required=metadata["clarification_required"],
            clarification_question=metadata["clarification_question"],
            reference_status=metadata.get("reference_status"),
            reference_topic=metadata.get("reference_topic"),
            requested_action=metadata.get("requested_action"),
            requested_output=metadata.get("requested_output"),
            resolved_language=metadata.get("resolved_language"),
            platform_mode=metadata.get("platform_mode"),
            context_entry_count=metadata.get("context_entry_count"),
            compilation_method=metadata.get("compilation_method"),
            compilation_confidence=metadata.get("compilation_confidence"),
            task_compilation_ms=metadata.get("task_compilation_ms"),
        )
    requested_question_type = str(req.question_type or req.screen_question_type or "").strip().lower()
    screen_question_type = (
        _infer_screen_problem_type(effective_question, requested_question_type)
        if source == "screen"
        else requested_question_type
    )
    effective_category = "technical" if req.force_technical else req.category
    if source == "screen" and screen_question_type in {"coding", "debugging", "output"}:
        effective_category = "technical"
    routed_category = classify_question_by_rules(effective_question) or effective_category
    personal_subtype = classify_personal_subtype(effective_question)
    personal_professional_context_allowed = personal_question_allows_professional_context(effective_question)
    coding_intent = looks_like_coding_implementation_request(effective_question)
    if followup_intent and followup_intent.requested_output in {
        "structured_coding_answer",
        "coding_optimization",
        "code_explanation",
        "complexity_analysis",
    }:
        coding_intent = followup_intent.requested_output == "structured_coding_answer"
    if coding_intent and not screen_question_type:
        screen_question_type = "coding"
    coding_answer_mode = bool(req.coding_answer_mode) or coding_intent or (
        source == "screen" and screen_question_type in {"coding", "debugging", "output"}
    )
    generation_question = str(effective_question or "").strip()
    generation_problem_text = _compose_problem_text_from_request(req)
    generation_editor_text = str(req.editor_text or "").strip()
    if source == "screen" and screen_question_type in {"coding", "debugging", "output"} and generation_problem_text:
        generation_question = generation_problem_text
    answer_plan = build_answer_plan(
        question=generation_question,
        category=effective_category,
        source=source,
        screen_question_type=screen_question_type,
    )
    coding_runtime_audit = {
        "request_question_excerpt": _excerpt(req.question),
        "full_problem_text_present": bool(generation_problem_text),
        "generate_full_problem_text_len": len(generation_problem_text),
        "full_problem_text_excerpt": _excerpt(generation_problem_text),
        "editor_text_present": bool(generation_editor_text),
        "generate_editor_text_len": len(generation_editor_text),
        "editor_text_excerpt": _excerpt(generation_editor_text),
        "input_format_used": bool(str(req.input_format or "").strip()) or "input format" in generation_problem_text.lower(),
        "output_format_used": bool(str(req.output_format or "").strip()) or "output format" in generation_problem_text.lower(),
        "generation_question_excerpt": _excerpt(generation_question),
        "source": source or "unknown",
        "screen_question_type": screen_question_type or "none",
        "coding_answer_mode": coding_answer_mode,
    }
    suppress_personal_context = (
        source == "screen"
        and screen_question_type in {"coding", "debugging", "output", "visual", "mcq", "architecture"}
    )
    suppress_personal_context = suppress_personal_context or (
        routed_category == "personal" and not personal_professional_context_allowed
    )
    use_profile_context = (
        bool(req.profile_context_used)
        and not suppress_personal_context
        and answer_plan.profile_context_policy != "FORBIDDEN"
    )
    use_job_context = answer_plan.job_context_policy != "FORBIDDEN"

    def _apply_personal_validation(result: Dict[str, Any]) -> None:
        if (result.get("answer_category") or routed_category) != "personal" and not personal_subtype:
            return
        repaired, errors, repaired_used = generator.repair_personal_answer_if_needed(
            question=generation_question,
            answer=str(result.get("answer") or ""),
        )
        result["answer"] = repaired
        result["personal_validation_errors"] = errors
        result["personal_answer_repaired"] = repaired_used
        result.update(
            generator.personal_generation_metadata(
                question=generation_question,
                profile=(req.profile or {}) if use_profile_context else {},
            )
        )

    def _response_personal_kwargs(result: Dict[str, Any]) -> Dict[str, Any]:
        metadata = generator.personal_generation_metadata(
            question=generation_question,
            profile=(req.profile or {}) if use_profile_context else {},
        )
        metadata.update(
            {
                "personal_validation_errors": result.get("personal_validation_errors"),
                "personal_answer_repaired": result.get("personal_answer_repaired"),
            }
        )
        return metadata

    try:
        saved_job_context = job_context_service.get_context() if use_job_context else {"saved": False}
        retrieval = (
            resume_index_service.retrieve(
                question=generation_question,
                category=effective_category,
                limit=settings.RAG_RETRIEVAL_LIMIT,
            )
            if use_profile_context
            else {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0}
        )
        retrieval_used = retrieval["retrieval_used"]
        retrieved_chunks = retrieval["retrieved_chunks"]
        if retrieval["retrieval_ms"] > settings.RAG_TIMEOUT_MS:
            logger.warning(
                "Resume retrieval exceeded live latency budget rag_ms=%s limit_ms=%s question_len=%s",
                retrieval["retrieval_ms"],
                settings.RAG_TIMEOUT_MS,
                len(req.question.strip()),
            )
            retrieval_used = False
            retrieved_chunks = []
        result = generator.generate_answer(
            question=generation_question,
            question_type=effective_category,
            profile=(req.profile or {}) if use_profile_context else {},
            retrieved_snippets=retrieved_chunks,
            job_context=saved_job_context if use_profile_context and saved_job_context.get("saved") else None,
            source=source,
            question_context_type=screen_question_type,
            screen_question_type=screen_question_type,
            coding_answer_mode=coding_answer_mode,
            profile_context_enabled=use_profile_context,
            editor_text=generation_editor_text,
            answer_plan=answer_plan,
        )
        context_status = _evaluate_hackerrank_context_readiness(
            platform=str(req.screen_platform_detected or result.get("platform_detected") or ""),
            coding_answer_mode=coding_answer_mode,
            problem_text=generation_problem_text,
            input_format=str(req.input_format or ""),
            output_format=str(req.output_format or ""),
            sample_input=str(req.sample_input or ""),
            sample_output=str(req.sample_output or ""),
            sample_tests_found=int(result.get("sample_tests_found") or 0),
        )
        original_json_noise_detected = _contains_json_noise(str(req.full_problem_text or req.question or ""))
        context_status = _force_context_not_ready_for_json_noise(context_status, original_json_noise_detected)
        result = _apply_hackerrank_context_gate(result, context_status)
        _apply_personal_validation(result)
        coding_runtime_audit.update(
            {
                "code_generation_mode": result.get("code_generation_mode"),
                "function_stub_detected": result.get("function_stub_detected"),
                "function_name": result.get("function_name"),
                "required_stub_preserved": result.get("required_stub_preserved"),
                "standalone_solution_rejected": result.get("standalone_solution_rejected"),
                "code_validation_passed": result.get("code_validation_passed"),
                "sample_tests_found": result.get("sample_tests_found"),
                "hackerrank_context_ready": result.get("hackerrank_context_ready"),
                "missing_context_sections": result.get("missing_context_sections"),
                "full_problem_text_is_summary_only": result.get("full_problem_text_is_summary_only"),
                "full_problem_text_contains_json_noise": result.get("full_problem_text_contains_json_noise"),
                "clean_full_problem_text_len": result.get("clean_full_problem_text_len"),
                "context_readiness_hard_block_applied": result.get("context_readiness_hard_block_applied"),
                "submission_ready_block_reason": result.get("submission_ready_block_reason"),
                "correction_pass_used": result.get("correction_pass_used"),
                "output_order_validation_used": result.get("output_order_validation_used"),
                "output_order_validation_passed": result.get("output_order_validation_passed"),
            }
        )
        coding_prompt_flags = _analyze_coding_prompt_flags(generation_question, result["answer"])
        refinement_job_id = _queue_parallel_refinement(
            req=req,
            saved_job_context=saved_job_context,
            retrieval={**retrieval, "retrieved_chunks": retrieved_chunks},
            result=result,
        )

        total_pipeline_ms = req.total_pipeline_ms
        if total_pipeline_ms is None:
            total_pipeline_ms = round(
                (
                    (req.recording_ms or 0)
                    + (req.upload_ms or 0)
                    + (req.transcription_ms or 0)
                    + (req.classification_ms or 0)
                    + (req.profile_fetch_ms or 0)
                    + retrieval["retrieval_ms"]
                    + result["generation_ms"]
                ),
                2,
            )

        logger.info(
            "Answer generation completed source=%s question_type=%s category=%s coding_answer_mode=%s provider=%s primary_provider=%s refinement_provider=%s refinement_used=%s refinement_status=%s model=%s fallback_used=%s recording_ms=%s upload_ms=%s transcription_ms=%s classification_ms=%s profile_fetch_ms=%s retrieval_ms=%s prompt_build_ms=%s groq_generation_ms=%s generation_ms=%s total_pipeline_ms=%s retrieved_chunk_count=%s job_context_used=%s profile_context_used=%s question_len=%s profile_keys=%s input_format_used=%s output_format_used=%s count_prefix_detected=%s submission_ready_code=%s hardcoded_sample_detected=%s generate_full_problem_text_len=%s generate_editor_text_len=%s editor_text_present=%s sample_tests_found=%s hackerrank_context_ready=%s missing_context_sections=%s full_problem_text_is_summary_only=%s full_problem_text_contains_json_noise=%s clean_full_problem_text_len=%s context_readiness_hard_block_applied=%s submission_ready_block_reason=%s",
            source or "",
            screen_question_type,
            effective_category,
            coding_answer_mode,
            result["provider"],
            result.get("primary_provider"),
            result.get("refinement_provider"),
            result.get("refinement_used"),
            result.get("refinement_status"),
            result["model"],
            result["fallback_used"],
            req.recording_ms,
            req.upload_ms,
            req.transcription_ms,
            req.classification_ms,
            req.profile_fetch_ms,
            retrieval["retrieval_ms"],
            result.get("prompt_build_ms"),
            result.get("groq_generation_ms"),
            result["generation_ms"],
            total_pipeline_ms,
            len(retrieved_chunks),
            bool(use_profile_context and saved_job_context.get("saved")),
            use_profile_context,
            len(req.question.strip()),
            sorted(((req.profile or {}) if use_profile_context else {}).keys()),
            coding_prompt_flags["input_format_used"],
            coding_prompt_flags["output_format_used"],
            coding_prompt_flags["count_prefix_detected"],
            result.get("submission_ready_code"),
            coding_prompt_flags["hardcoded_sample_detected"],
            len(generation_problem_text),
            len(generation_editor_text),
            bool(generation_editor_text),
            result.get("sample_tests_found"),
            result.get("hackerrank_context_ready"),
            result.get("missing_context_sections"),
            result.get("full_problem_text_is_summary_only"),
            result.get("full_problem_text_contains_json_noise"),
            result.get("clean_full_problem_text_len"),
            result.get("context_readiness_hard_block_applied"),
            result.get("submission_ready_block_reason"),
        )
        if coding_answer_mode:
            logger.info("Coding runtime audit %s", coding_runtime_audit)

        return GenerateResponse(
            answer=result["answer"],
            provider=result["provider"],
            model=result["model"],
            fallback_used=result["fallback_used"],
            primary_provider=result.get("primary_provider"),
            primary_model=result.get("primary_model"),
            refinement_provider=result.get("refinement_provider"),
            refinement_model=result.get("refinement_model"),
            refinement_used=result.get("refinement_used"),
            refinement_status=result.get("refinement_status"),
            refinement_job_id=refinement_job_id,
            error=result["error"],
            generation_ms=result["generation_ms"],
            generation_time_ms=result.get("generation_time_ms", result["generation_ms"]),
            primary_generation_ms=result.get("primary_generation_ms"),
            refinement_generation_ms=result.get("refinement_generation_ms"),
            recording_ms=req.recording_ms,
            upload_ms=req.upload_ms,
            transcription_ms=req.transcription_ms,
            classification_ms=req.classification_ms,
            profile_fetch_ms=req.profile_fetch_ms,
            rag_ms=retrieval["retrieval_ms"],
            prompt_build_ms=result.get("prompt_build_ms"),
            groq_generation_ms=result.get("groq_generation_ms"),
            performance_mode=settings.PERFORMANCE_MODE,
            total_pipeline_ms=total_pipeline_ms,
            retrieval_used=retrieval_used,
            retrieved_chunk_count=len(retrieved_chunks),
            profile_context_used=use_profile_context,
            answer_type=result.get("answer_type"),
            plan_confidence=result.get("plan_confidence"),
            profile_context_policy=result.get("profile_context_policy"),
            job_context_policy=result.get("job_context_policy"),
            general_knowledge_policy=result.get("general_knowledge_policy"),
            job_context_used=bool(use_job_context and saved_job_context.get("saved")),
            validation_status=result.get("validation_status"),
            validation_issues_count=result.get("validation_issues_count"),
            reasoning_effort=result.get("reasoning_effort"),
            deterministic_validation_ms=result.get("deterministic_validation_ms"),
            semantic_validation_used=result.get("semantic_validation_used"),
            semantic_validation_ms=result.get("semantic_validation_ms"),
            semantic_validation_status=result.get("semantic_validation_status"),
            correction_ms=result.get("correction_ms"),
            correction_status=result.get("correction_status"),
            answer_verified=result.get("answer_verified"),
            repetition_detected=result.get("repetition_detected"),
            repetition_count=result.get("repetition_count"),
            variation_enabled=result.get("variation_enabled"),
            variation_profile=result.get("variation_profile"),
            variation_applied=result.get("variation_applied"),
            variation_rewrite_used=result.get("variation_rewrite_used"),
            variation_status=result.get("variation_status"),
            similarity_score=result.get("similarity_score"),
            previous_answer_count=result.get("previous_answer_count"),
            variation_ms=result.get("variation_ms"),
            generate_source=source or None,
            generate_question_type=screen_question_type or None,
            generate_category=result.get("answer_category") or routed_category,
            **_response_personal_kwargs(result),
            coding_answer_mode=coding_answer_mode,
            coding_prompt_used=result.get("coding_prompt_used"),
            refinement_coding_prompt_used=result.get("refinement_coding_prompt_used"),
            input_format_used=coding_prompt_flags["input_format_used"],
            output_format_used=coding_prompt_flags["output_format_used"],
            count_prefix_detected=coding_prompt_flags["count_prefix_detected"],
            submission_ready_code=result.get("submission_ready_code"),
            hardcoded_sample_detected=coding_prompt_flags["hardcoded_sample_detected"],
            coding_input_contract=result.get("coding_input_contract"),
            regex_contract=result.get("regex_contract"),
            llm_contract_used=result.get("llm_contract_used"),
            llm_contract=result.get("llm_contract"),
            merged_coding_contract=result.get("merged_coding_contract"),
            contract_conflicts=result.get("contract_conflicts"),
            platform_detected=result.get("platform_detected"),
            platform_adapter=result.get("platform_adapter"),
            hackerrank_contract_used=result.get("hackerrank_contract_used"),
            hackerrank_full_problem_used=result.get("hackerrank_full_problem_used"),
            problem_title=result.get("problem_title"),
            hackerrank_subdomain=result.get("hackerrank_subdomain"),
            problem_family=result.get("problem_family"),
            contract_sections_found=result.get("contract_sections_found"),
            hackerrank_context_ready=result.get("hackerrank_context_ready"),
            missing_context_sections=result.get("missing_context_sections"),
            full_problem_text_is_summary_only=result.get("full_problem_text_is_summary_only"),
            full_problem_text_contains_json_noise=result.get("full_problem_text_contains_json_noise"),
            clean_full_problem_text_len=result.get("clean_full_problem_text_len"),
            context_readiness_hard_block_applied=result.get("context_readiness_hard_block_applied"),
            submission_ready_block_reason=result.get("submission_ready_block_reason"),
            code_generation_mode=result.get("code_generation_mode"),
            editor_stub_used=result.get("editor_stub_used"),
            editor_stub_mode=result.get("editor_stub_mode"),
            editor_required_symbols=result.get("editor_required_symbols"),
            editor_required_functions=result.get("editor_required_functions"),
            editor_required_lambdas=result.get("editor_required_lambdas"),
            editor_required_classes=result.get("editor_required_classes"),
            editor_runner_detected=result.get("editor_runner_detected"),
            editor_placeholder_lines=result.get("editor_placeholder_lines"),
            editor_stub_validation_used=result.get("editor_stub_validation_used"),
            editor_stub_validation_passed=result.get("editor_stub_validation_passed"),
            editor_stub_validation_errors=result.get("editor_stub_validation_errors"),
            function_stub_detected=result.get("function_stub_detected"),
            function_name=result.get("function_name"),
            coding_quality_gate_used=result.get("coding_quality_gate_used"),
            code_validation_used=result.get("code_validation_used"),
            code_validation_passed=result.get("code_validation_passed"),
            code_validation_errors=result.get("code_validation_errors"),
            python_syntax_validation_used=result.get("python_syntax_validation_used"),
            python_syntax_valid=result.get("python_syntax_valid"),
            incomplete_code_detected=result.get("incomplete_code_detected"),
            incomplete_code_errors=result.get("incomplete_code_errors"),
            required_stub_preserved=result.get("required_stub_preserved"),
            standalone_solution_rejected=result.get("standalone_solution_rejected"),
            function_stub_completeness_validation_used=result.get("function_stub_completeness_validation_used"),
            function_stub_completeness_passed=result.get("function_stub_completeness_passed"),
            function_stub_completeness_errors=result.get("function_stub_completeness_errors"),
            duplicate_function_definition_detected=result.get("duplicate_function_definition_detected"),
            partial_function_snippet_detected=result.get("partial_function_snippet_detected"),
            class_stub_detected=result.get("class_stub_detected"),
            class_name=result.get("class_name"),
            required_methods=result.get("required_methods"),
            missing_required_methods=result.get("missing_required_methods"),
            custom_class_validation_used=result.get("custom_class_validation_used"),
            custom_class_validation_passed=result.get("custom_class_validation_passed"),
            custom_class_validation_errors=result.get("custom_class_validation_errors"),
            builtin_complex_only_rejected=result.get("builtin_complex_only_rejected"),
            output_format_requires_custom_complex=result.get("output_format_requires_custom_complex"),
            output_decimal_places=result.get("output_decimal_places"),
            output_order_validation_used=result.get("output_order_validation_used"),
            output_order_validation_passed=result.get("output_order_validation_passed"),
            output_order_validation_errors=result.get("output_order_validation_errors"),
            sample_tests_found=result.get("sample_tests_found"),
            sample_tests_source=result.get("sample_tests_source"),
            sample_tests_ran=result.get("sample_tests_ran"),
            sample_tests_skipped_reason=result.get("sample_tests_skipped_reason"),
            sample_tests_passed=result.get("sample_tests_passed"),
            sample_test_errors=result.get("sample_test_errors"),
            sample_actual_output=result.get("sample_actual_output"),
            sample_expected_output=result.get("sample_expected_output"),
            function_test_harness_used=result.get("function_test_harness_used"),
            function_test_harness_name=result.get("function_test_harness_name"),
            class_test_harness_used=result.get("class_test_harness_used"),
            class_test_harness_name=result.get("class_test_harness_name"),
            correction_pass_needed=result.get("correction_pass_needed"),
            correction_pass_used=result.get("correction_pass_used"),
            correction_attempts=result.get("correction_attempts"),
            correction_reason=result.get("correction_reason"),
            correction_skip_reason=result.get("correction_skip_reason"),
            correction_failure_reason=result.get("correction_failure_reason"),
            correction_pass_failed=result.get("correction_pass_failed"),
            correction_prompt_len=result.get("correction_prompt_len"),
            correction_model=result.get("correction_model"),
            correction_retry_used=result.get("correction_retry_used"),
            coding_prompt_len=result.get("coding_prompt_len"),
            compact_contract_used=result.get("compact_contract_used"),
            raw_context_trimmed=result.get("raw_context_trimmed"),
            coding_max_tokens=result.get("coding_max_tokens"),
            prompt_token_estimate=result.get("prompt_token_estimate"),
            requested_completion_tokens=result.get("requested_completion_tokens"),
            primary_generation_rate_limited=result.get("primary_generation_rate_limited"),
            retry_after_seconds=result.get("retry_after_seconds"),
            primary_retry_used=result.get("primary_retry_used"),
            primary_retry_skipped_reason=result.get("primary_retry_skipped_reason"),
            unverified_code_warning=result.get("unverified_code_warning"),
            fallback_enabled=result.get("fallback_enabled"),
            fallback_reason=result.get("fallback_reason"),
            fallback_unavailable_reason=result.get("fallback_unavailable_reason"),
            coding_runtime_audit=coding_runtime_audit,
            structured_coding_answer_used=bool(result.get("coding_answer")),
            coding_validation_status=result.get("coding_validation_status"),
            coding_answer=result.get("coding_answer"),
            **followup_resolution.to_metadata(),
            **_followup_intent_metadata(followup_intent, req.followup_context),
        )
    except ResumeIndexError as exc:
        logger.warning("Resume retrieval failed for question_len=%s error=%s", len(req.question.strip()), exc)
        saved_job_context = job_context_service.get_context()
        result = generator.generate_answer(
            question=generation_question,
            question_type=effective_category,
            profile=(req.profile or {}) if use_profile_context else {},
            retrieved_snippets=[],
            job_context=saved_job_context if use_profile_context and saved_job_context.get("saved") else None,
            source=source,
            question_context_type=screen_question_type,
            screen_question_type=screen_question_type,
            coding_answer_mode=coding_answer_mode,
            profile_context_enabled=use_profile_context,
            editor_text=generation_editor_text,
            answer_plan=answer_plan,
        )
        context_status = _evaluate_hackerrank_context_readiness(
            platform=str(req.screen_platform_detected or result.get("platform_detected") or ""),
            coding_answer_mode=coding_answer_mode,
            problem_text=generation_problem_text,
            input_format=str(req.input_format or ""),
            output_format=str(req.output_format or ""),
            sample_input=str(req.sample_input or ""),
            sample_output=str(req.sample_output or ""),
            sample_tests_found=int(result.get("sample_tests_found") or 0),
        )
        original_json_noise_detected = _contains_json_noise(str(req.full_problem_text or req.question or ""))
        context_status = _force_context_not_ready_for_json_noise(context_status, original_json_noise_detected)
        result = _apply_hackerrank_context_gate(result, context_status)
        _apply_personal_validation(result)
        coding_runtime_audit.update(
            {
                "code_generation_mode": result.get("code_generation_mode"),
                "function_stub_detected": result.get("function_stub_detected"),
                "function_name": result.get("function_name"),
                "required_stub_preserved": result.get("required_stub_preserved"),
                "standalone_solution_rejected": result.get("standalone_solution_rejected"),
                "code_validation_passed": result.get("code_validation_passed"),
                "sample_tests_found": result.get("sample_tests_found"),
                "hackerrank_context_ready": result.get("hackerrank_context_ready"),
                "missing_context_sections": result.get("missing_context_sections"),
                "full_problem_text_is_summary_only": result.get("full_problem_text_is_summary_only"),
                "full_problem_text_contains_json_noise": result.get("full_problem_text_contains_json_noise"),
                "clean_full_problem_text_len": result.get("clean_full_problem_text_len"),
                "context_readiness_hard_block_applied": result.get("context_readiness_hard_block_applied"),
                "submission_ready_block_reason": result.get("submission_ready_block_reason"),
                "correction_pass_used": result.get("correction_pass_used"),
                "output_order_validation_used": result.get("output_order_validation_used"),
                "output_order_validation_passed": result.get("output_order_validation_passed"),
            }
        )
        coding_prompt_flags = _analyze_coding_prompt_flags(generation_question, result["answer"])
        if coding_answer_mode:
            logger.info("Coding runtime audit %s", coding_runtime_audit)
        refinement_job_id = _queue_parallel_refinement(
            req=req,
            saved_job_context=saved_job_context,
            retrieval={"retrieved_chunks": []},
            result=result,
        )
        total_pipeline_ms = req.total_pipeline_ms
        if total_pipeline_ms is None:
            total_pipeline_ms = round(
                (
                    (req.transcription_ms or 0)
                    + (req.recording_ms or 0)
                    + (req.upload_ms or 0)
                    + (req.classification_ms or 0)
                    + (req.profile_fetch_ms or 0)
                    + result["generation_ms"]
                ),
                2,
            )
        return GenerateResponse(
            answer=result["answer"],
            provider=result["provider"],
            model=result["model"],
            fallback_used=result["fallback_used"],
            primary_provider=result.get("primary_provider"),
            primary_model=result.get("primary_model"),
            refinement_provider=result.get("refinement_provider"),
            refinement_model=result.get("refinement_model"),
            refinement_used=result.get("refinement_used"),
            refinement_status=result.get("refinement_status"),
            refinement_job_id=refinement_job_id,
            error=result["error"],
            generation_ms=result["generation_ms"],
            generation_time_ms=result.get("generation_time_ms", result["generation_ms"]),
            primary_generation_ms=result.get("primary_generation_ms"),
            refinement_generation_ms=result.get("refinement_generation_ms"),
            recording_ms=req.recording_ms,
            upload_ms=req.upload_ms,
            transcription_ms=req.transcription_ms,
            classification_ms=req.classification_ms,
            profile_fetch_ms=req.profile_fetch_ms,
            rag_ms=None,
            prompt_build_ms=result.get("prompt_build_ms"),
            groq_generation_ms=result.get("groq_generation_ms"),
            performance_mode=settings.PERFORMANCE_MODE,
            total_pipeline_ms=total_pipeline_ms,
            retrieval_used=False,
            retrieved_chunk_count=0,
            profile_context_used=use_profile_context,
            answer_type=result.get("answer_type"),
            plan_confidence=result.get("plan_confidence"),
            profile_context_policy=result.get("profile_context_policy"),
            job_context_policy=result.get("job_context_policy"),
            general_knowledge_policy=result.get("general_knowledge_policy"),
            job_context_used=False,
            validation_status=result.get("validation_status"),
            validation_issues_count=result.get("validation_issues_count"),
            reasoning_effort=result.get("reasoning_effort"),
            deterministic_validation_ms=result.get("deterministic_validation_ms"),
            semantic_validation_used=result.get("semantic_validation_used"),
            semantic_validation_ms=result.get("semantic_validation_ms"),
            semantic_validation_status=result.get("semantic_validation_status"),
            correction_ms=result.get("correction_ms"),
            correction_status=result.get("correction_status"),
            answer_verified=result.get("answer_verified"),
            repetition_detected=result.get("repetition_detected"),
            repetition_count=result.get("repetition_count"),
            variation_enabled=result.get("variation_enabled"),
            variation_profile=result.get("variation_profile"),
            variation_applied=result.get("variation_applied"),
            variation_rewrite_used=result.get("variation_rewrite_used"),
            variation_status=result.get("variation_status"),
            similarity_score=result.get("similarity_score"),
            previous_answer_count=result.get("previous_answer_count"),
            variation_ms=result.get("variation_ms"),
            generate_source=source or None,
            generate_question_type=screen_question_type or None,
            generate_category=result.get("answer_category") or routed_category,
            **_response_personal_kwargs(result),
            coding_answer_mode=coding_answer_mode,
            coding_prompt_used=result.get("coding_prompt_used"),
            refinement_coding_prompt_used=result.get("refinement_coding_prompt_used"),
            input_format_used=coding_prompt_flags["input_format_used"],
            output_format_used=coding_prompt_flags["output_format_used"],
            count_prefix_detected=coding_prompt_flags["count_prefix_detected"],
            submission_ready_code=result.get("submission_ready_code"),
            hardcoded_sample_detected=coding_prompt_flags["hardcoded_sample_detected"],
            coding_input_contract=result.get("coding_input_contract"),
            regex_contract=result.get("regex_contract"),
            llm_contract_used=result.get("llm_contract_used"),
            llm_contract=result.get("llm_contract"),
            merged_coding_contract=result.get("merged_coding_contract"),
            contract_conflicts=result.get("contract_conflicts"),
            platform_detected=result.get("platform_detected"),
            platform_adapter=result.get("platform_adapter"),
            hackerrank_contract_used=result.get("hackerrank_contract_used"),
            hackerrank_full_problem_used=result.get("hackerrank_full_problem_used"),
            problem_title=result.get("problem_title"),
            hackerrank_subdomain=result.get("hackerrank_subdomain"),
            problem_family=result.get("problem_family"),
            contract_sections_found=result.get("contract_sections_found"),
            hackerrank_context_ready=result.get("hackerrank_context_ready"),
            missing_context_sections=result.get("missing_context_sections"),
            full_problem_text_is_summary_only=result.get("full_problem_text_is_summary_only"),
            full_problem_text_contains_json_noise=result.get("full_problem_text_contains_json_noise"),
            clean_full_problem_text_len=result.get("clean_full_problem_text_len"),
            context_readiness_hard_block_applied=result.get("context_readiness_hard_block_applied"),
            submission_ready_block_reason=result.get("submission_ready_block_reason"),
            code_generation_mode=result.get("code_generation_mode"),
            editor_stub_used=result.get("editor_stub_used"),
            editor_stub_mode=result.get("editor_stub_mode"),
            editor_required_symbols=result.get("editor_required_symbols"),
            editor_required_functions=result.get("editor_required_functions"),
            editor_required_lambdas=result.get("editor_required_lambdas"),
            editor_required_classes=result.get("editor_required_classes"),
            editor_runner_detected=result.get("editor_runner_detected"),
            editor_placeholder_lines=result.get("editor_placeholder_lines"),
            editor_stub_validation_used=result.get("editor_stub_validation_used"),
            editor_stub_validation_passed=result.get("editor_stub_validation_passed"),
            editor_stub_validation_errors=result.get("editor_stub_validation_errors"),
            function_stub_detected=result.get("function_stub_detected"),
            function_name=result.get("function_name"),
            coding_quality_gate_used=result.get("coding_quality_gate_used"),
            code_validation_used=result.get("code_validation_used"),
            code_validation_passed=result.get("code_validation_passed"),
            code_validation_errors=result.get("code_validation_errors"),
            python_syntax_validation_used=result.get("python_syntax_validation_used"),
            python_syntax_valid=result.get("python_syntax_valid"),
            incomplete_code_detected=result.get("incomplete_code_detected"),
            incomplete_code_errors=result.get("incomplete_code_errors"),
            required_stub_preserved=result.get("required_stub_preserved"),
            standalone_solution_rejected=result.get("standalone_solution_rejected"),
            function_stub_completeness_validation_used=result.get("function_stub_completeness_validation_used"),
            function_stub_completeness_passed=result.get("function_stub_completeness_passed"),
            function_stub_completeness_errors=result.get("function_stub_completeness_errors"),
            duplicate_function_definition_detected=result.get("duplicate_function_definition_detected"),
            partial_function_snippet_detected=result.get("partial_function_snippet_detected"),
            class_stub_detected=result.get("class_stub_detected"),
            class_name=result.get("class_name"),
            required_methods=result.get("required_methods"),
            missing_required_methods=result.get("missing_required_methods"),
            custom_class_validation_used=result.get("custom_class_validation_used"),
            custom_class_validation_passed=result.get("custom_class_validation_passed"),
            custom_class_validation_errors=result.get("custom_class_validation_errors"),
            builtin_complex_only_rejected=result.get("builtin_complex_only_rejected"),
            output_format_requires_custom_complex=result.get("output_format_requires_custom_complex"),
            output_decimal_places=result.get("output_decimal_places"),
            output_order_validation_used=result.get("output_order_validation_used"),
            output_order_validation_passed=result.get("output_order_validation_passed"),
            output_order_validation_errors=result.get("output_order_validation_errors"),
            sample_tests_found=result.get("sample_tests_found"),
            sample_tests_source=result.get("sample_tests_source"),
            sample_tests_ran=result.get("sample_tests_ran"),
            sample_tests_skipped_reason=result.get("sample_tests_skipped_reason"),
            sample_tests_passed=result.get("sample_tests_passed"),
            sample_test_errors=result.get("sample_test_errors"),
            sample_actual_output=result.get("sample_actual_output"),
            sample_expected_output=result.get("sample_expected_output"),
            function_test_harness_used=result.get("function_test_harness_used"),
            function_test_harness_name=result.get("function_test_harness_name"),
            class_test_harness_used=result.get("class_test_harness_used"),
            class_test_harness_name=result.get("class_test_harness_name"),
            correction_pass_needed=result.get("correction_pass_needed"),
            correction_pass_used=result.get("correction_pass_used"),
            correction_attempts=result.get("correction_attempts"),
            correction_reason=result.get("correction_reason"),
            correction_skip_reason=result.get("correction_skip_reason"),
            correction_failure_reason=result.get("correction_failure_reason"),
            correction_pass_failed=result.get("correction_pass_failed"),
            correction_prompt_len=result.get("correction_prompt_len"),
            correction_model=result.get("correction_model"),
            correction_retry_used=result.get("correction_retry_used"),
            coding_prompt_len=result.get("coding_prompt_len"),
            compact_contract_used=result.get("compact_contract_used"),
            raw_context_trimmed=result.get("raw_context_trimmed"),
            coding_max_tokens=result.get("coding_max_tokens"),
            prompt_token_estimate=result.get("prompt_token_estimate"),
            requested_completion_tokens=result.get("requested_completion_tokens"),
            primary_generation_rate_limited=result.get("primary_generation_rate_limited"),
            retry_after_seconds=result.get("retry_after_seconds"),
            primary_retry_used=result.get("primary_retry_used"),
            primary_retry_skipped_reason=result.get("primary_retry_skipped_reason"),
            unverified_code_warning=result.get("unverified_code_warning"),
            fallback_enabled=result.get("fallback_enabled"),
            fallback_reason=result.get("fallback_reason"),
            fallback_unavailable_reason=result.get("fallback_unavailable_reason"),
            coding_runtime_audit=coding_runtime_audit,
            structured_coding_answer_used=bool(result.get("coding_answer")),
            coding_validation_status=result.get("coding_validation_status"),
            coding_answer=result.get("coding_answer"),
            **followup_resolution.to_metadata(),
            **_followup_intent_metadata(followup_intent, req.followup_context),
        )
    except JobContextError as exc:
        logger.warning("Job context load failed for question_len=%s error=%s", len(req.question.strip()), exc)
        retrieval = (
            resume_index_service.retrieve(
                question=generation_question,
                category=effective_category,
                limit=settings.RAG_RETRIEVAL_LIMIT,
            )
            if use_profile_context
            else {"retrieval_used": False, "retrieved_chunks": [], "retrieval_ms": 0.0}
        )
        retrieval_used = retrieval["retrieval_used"]
        retrieved_chunks = retrieval["retrieved_chunks"]
        if retrieval["retrieval_ms"] > settings.RAG_TIMEOUT_MS:
            retrieval_used = False
            retrieved_chunks = []
        result = generator.generate_answer(
            question=generation_question,
            question_type=effective_category,
            profile=(req.profile or {}) if use_profile_context else {},
            retrieved_snippets=retrieved_chunks,
            job_context=None,
            source=source,
            question_context_type=screen_question_type,
            screen_question_type=screen_question_type,
            coding_answer_mode=coding_answer_mode,
            profile_context_enabled=use_profile_context,
            editor_text=generation_editor_text,
            answer_plan=answer_plan,
        )
        context_status = _evaluate_hackerrank_context_readiness(
            platform=str(req.screen_platform_detected or result.get("platform_detected") or ""),
            coding_answer_mode=coding_answer_mode,
            problem_text=generation_problem_text,
            input_format=str(req.input_format or ""),
            output_format=str(req.output_format or ""),
            sample_input=str(req.sample_input or ""),
            sample_output=str(req.sample_output or ""),
            sample_tests_found=int(result.get("sample_tests_found") or 0),
        )
        original_json_noise_detected = _contains_json_noise(str(req.full_problem_text or req.question or ""))
        context_status = _force_context_not_ready_for_json_noise(context_status, original_json_noise_detected)
        result = _apply_hackerrank_context_gate(result, context_status)
        _apply_personal_validation(result)
        coding_runtime_audit.update(
            {
                "code_generation_mode": result.get("code_generation_mode"),
                "function_stub_detected": result.get("function_stub_detected"),
                "function_name": result.get("function_name"),
                "required_stub_preserved": result.get("required_stub_preserved"),
                "standalone_solution_rejected": result.get("standalone_solution_rejected"),
                "code_validation_passed": result.get("code_validation_passed"),
                "sample_tests_found": result.get("sample_tests_found"),
                "hackerrank_context_ready": result.get("hackerrank_context_ready"),
                "missing_context_sections": result.get("missing_context_sections"),
                "full_problem_text_is_summary_only": result.get("full_problem_text_is_summary_only"),
                "full_problem_text_contains_json_noise": result.get("full_problem_text_contains_json_noise"),
                "clean_full_problem_text_len": result.get("clean_full_problem_text_len"),
                "context_readiness_hard_block_applied": result.get("context_readiness_hard_block_applied"),
                "submission_ready_block_reason": result.get("submission_ready_block_reason"),
                "correction_pass_used": result.get("correction_pass_used"),
                "output_order_validation_used": result.get("output_order_validation_used"),
                "output_order_validation_passed": result.get("output_order_validation_passed"),
            }
        )
        coding_prompt_flags = _analyze_coding_prompt_flags(generation_question, result["answer"])
        if coding_answer_mode:
            logger.info("Coding runtime audit %s", coding_runtime_audit)
        refinement_job_id = _queue_parallel_refinement(
            req=req,
            saved_job_context=None,
            retrieval={**retrieval, "retrieved_chunks": retrieved_chunks},
            result=result,
        )
        total_pipeline_ms = req.total_pipeline_ms
        if total_pipeline_ms is None:
            total_pipeline_ms = round(
                (
                    (req.recording_ms or 0)
                    + (req.upload_ms or 0)
                    + (req.transcription_ms or 0)
                    + (req.classification_ms or 0)
                    + (req.profile_fetch_ms or 0)
                    + retrieval["retrieval_ms"]
                    + result["generation_ms"]
                ),
                2,
            )
        return GenerateResponse(
            answer=result["answer"],
            provider=result["provider"],
            model=result["model"],
            fallback_used=result["fallback_used"],
            primary_provider=result.get("primary_provider"),
            primary_model=result.get("primary_model"),
            refinement_provider=result.get("refinement_provider"),
            refinement_model=result.get("refinement_model"),
            refinement_used=result.get("refinement_used"),
            refinement_status=result.get("refinement_status"),
            refinement_job_id=refinement_job_id,
            error=result["error"],
            generation_ms=result["generation_ms"],
            generation_time_ms=result.get("generation_time_ms", result["generation_ms"]),
            primary_generation_ms=result.get("primary_generation_ms"),
            refinement_generation_ms=result.get("refinement_generation_ms"),
            recording_ms=req.recording_ms,
            upload_ms=req.upload_ms,
            transcription_ms=req.transcription_ms,
            classification_ms=req.classification_ms,
            profile_fetch_ms=req.profile_fetch_ms,
            rag_ms=retrieval["retrieval_ms"],
            prompt_build_ms=result.get("prompt_build_ms"),
            groq_generation_ms=result.get("groq_generation_ms"),
            performance_mode=settings.PERFORMANCE_MODE,
            total_pipeline_ms=total_pipeline_ms,
            retrieval_used=retrieval_used,
            retrieved_chunk_count=len(retrieved_chunks),
            profile_context_used=use_profile_context,
            answer_type=result.get("answer_type"),
            plan_confidence=result.get("plan_confidence"),
            profile_context_policy=result.get("profile_context_policy"),
            job_context_policy=result.get("job_context_policy"),
            general_knowledge_policy=result.get("general_knowledge_policy"),
            job_context_used=False,
            validation_status=result.get("validation_status"),
            validation_issues_count=result.get("validation_issues_count"),
            reasoning_effort=result.get("reasoning_effort"),
            deterministic_validation_ms=result.get("deterministic_validation_ms"),
            semantic_validation_used=result.get("semantic_validation_used"),
            semantic_validation_ms=result.get("semantic_validation_ms"),
            semantic_validation_status=result.get("semantic_validation_status"),
            correction_ms=result.get("correction_ms"),
            correction_status=result.get("correction_status"),
            answer_verified=result.get("answer_verified"),
            repetition_detected=result.get("repetition_detected"),
            repetition_count=result.get("repetition_count"),
            variation_enabled=result.get("variation_enabled"),
            variation_profile=result.get("variation_profile"),
            variation_applied=result.get("variation_applied"),
            variation_rewrite_used=result.get("variation_rewrite_used"),
            variation_status=result.get("variation_status"),
            similarity_score=result.get("similarity_score"),
            previous_answer_count=result.get("previous_answer_count"),
            variation_ms=result.get("variation_ms"),
            generate_source=source or None,
            generate_question_type=screen_question_type or None,
            generate_category=result.get("answer_category") or routed_category,
            **_response_personal_kwargs(result),
            coding_answer_mode=coding_answer_mode,
            coding_prompt_used=result.get("coding_prompt_used"),
            refinement_coding_prompt_used=result.get("refinement_coding_prompt_used"),
            input_format_used=coding_prompt_flags["input_format_used"],
            output_format_used=coding_prompt_flags["output_format_used"],
            count_prefix_detected=coding_prompt_flags["count_prefix_detected"],
            submission_ready_code=result.get("submission_ready_code"),
            hardcoded_sample_detected=coding_prompt_flags["hardcoded_sample_detected"],
            coding_input_contract=result.get("coding_input_contract"),
            regex_contract=result.get("regex_contract"),
            llm_contract_used=result.get("llm_contract_used"),
            llm_contract=result.get("llm_contract"),
            merged_coding_contract=result.get("merged_coding_contract"),
            contract_conflicts=result.get("contract_conflicts"),
            platform_detected=result.get("platform_detected"),
            platform_adapter=result.get("platform_adapter"),
            hackerrank_contract_used=result.get("hackerrank_contract_used"),
            hackerrank_full_problem_used=result.get("hackerrank_full_problem_used"),
            problem_title=result.get("problem_title"),
            hackerrank_subdomain=result.get("hackerrank_subdomain"),
            problem_family=result.get("problem_family"),
            contract_sections_found=result.get("contract_sections_found"),
            hackerrank_context_ready=result.get("hackerrank_context_ready"),
            missing_context_sections=result.get("missing_context_sections"),
            full_problem_text_is_summary_only=result.get("full_problem_text_is_summary_only"),
            full_problem_text_contains_json_noise=result.get("full_problem_text_contains_json_noise"),
            clean_full_problem_text_len=result.get("clean_full_problem_text_len"),
            context_readiness_hard_block_applied=result.get("context_readiness_hard_block_applied"),
            submission_ready_block_reason=result.get("submission_ready_block_reason"),
            code_generation_mode=result.get("code_generation_mode"),
            editor_stub_used=result.get("editor_stub_used"),
            editor_stub_mode=result.get("editor_stub_mode"),
            editor_required_symbols=result.get("editor_required_symbols"),
            editor_required_functions=result.get("editor_required_functions"),
            editor_required_lambdas=result.get("editor_required_lambdas"),
            editor_required_classes=result.get("editor_required_classes"),
            editor_runner_detected=result.get("editor_runner_detected"),
            editor_placeholder_lines=result.get("editor_placeholder_lines"),
            editor_stub_validation_used=result.get("editor_stub_validation_used"),
            editor_stub_validation_passed=result.get("editor_stub_validation_passed"),
            editor_stub_validation_errors=result.get("editor_stub_validation_errors"),
            function_stub_detected=result.get("function_stub_detected"),
            function_name=result.get("function_name"),
            coding_quality_gate_used=result.get("coding_quality_gate_used"),
            code_validation_used=result.get("code_validation_used"),
            code_validation_passed=result.get("code_validation_passed"),
            code_validation_errors=result.get("code_validation_errors"),
            python_syntax_validation_used=result.get("python_syntax_validation_used"),
            python_syntax_valid=result.get("python_syntax_valid"),
            incomplete_code_detected=result.get("incomplete_code_detected"),
            incomplete_code_errors=result.get("incomplete_code_errors"),
            required_stub_preserved=result.get("required_stub_preserved"),
            standalone_solution_rejected=result.get("standalone_solution_rejected"),
            function_stub_completeness_validation_used=result.get("function_stub_completeness_validation_used"),
            function_stub_completeness_passed=result.get("function_stub_completeness_passed"),
            function_stub_completeness_errors=result.get("function_stub_completeness_errors"),
            duplicate_function_definition_detected=result.get("duplicate_function_definition_detected"),
            partial_function_snippet_detected=result.get("partial_function_snippet_detected"),
            class_stub_detected=result.get("class_stub_detected"),
            class_name=result.get("class_name"),
            required_methods=result.get("required_methods"),
            missing_required_methods=result.get("missing_required_methods"),
            custom_class_validation_used=result.get("custom_class_validation_used"),
            custom_class_validation_passed=result.get("custom_class_validation_passed"),
            custom_class_validation_errors=result.get("custom_class_validation_errors"),
            builtin_complex_only_rejected=result.get("builtin_complex_only_rejected"),
            output_format_requires_custom_complex=result.get("output_format_requires_custom_complex"),
            output_decimal_places=result.get("output_decimal_places"),
            output_order_validation_used=result.get("output_order_validation_used"),
            output_order_validation_passed=result.get("output_order_validation_passed"),
            output_order_validation_errors=result.get("output_order_validation_errors"),
            sample_tests_found=result.get("sample_tests_found"),
            sample_tests_source=result.get("sample_tests_source"),
            sample_tests_ran=result.get("sample_tests_ran"),
            sample_tests_skipped_reason=result.get("sample_tests_skipped_reason"),
            sample_tests_passed=result.get("sample_tests_passed"),
            sample_test_errors=result.get("sample_test_errors"),
            sample_actual_output=result.get("sample_actual_output"),
            sample_expected_output=result.get("sample_expected_output"),
            function_test_harness_used=result.get("function_test_harness_used"),
            function_test_harness_name=result.get("function_test_harness_name"),
            class_test_harness_used=result.get("class_test_harness_used"),
            class_test_harness_name=result.get("class_test_harness_name"),
            correction_pass_needed=result.get("correction_pass_needed"),
            correction_pass_used=result.get("correction_pass_used"),
            correction_attempts=result.get("correction_attempts"),
            correction_reason=result.get("correction_reason"),
            correction_skip_reason=result.get("correction_skip_reason"),
            correction_failure_reason=result.get("correction_failure_reason"),
            correction_pass_failed=result.get("correction_pass_failed"),
            correction_prompt_len=result.get("correction_prompt_len"),
            correction_model=result.get("correction_model"),
            correction_retry_used=result.get("correction_retry_used"),
            coding_prompt_len=result.get("coding_prompt_len"),
            compact_contract_used=result.get("compact_contract_used"),
            raw_context_trimmed=result.get("raw_context_trimmed"),
            coding_max_tokens=result.get("coding_max_tokens"),
            prompt_token_estimate=result.get("prompt_token_estimate"),
            requested_completion_tokens=result.get("requested_completion_tokens"),
            primary_generation_rate_limited=result.get("primary_generation_rate_limited"),
            retry_after_seconds=result.get("retry_after_seconds"),
            primary_retry_used=result.get("primary_retry_used"),
            primary_retry_skipped_reason=result.get("primary_retry_skipped_reason"),
            unverified_code_warning=result.get("unverified_code_warning"),
            fallback_enabled=result.get("fallback_enabled"),
            fallback_reason=result.get("fallback_reason"),
            fallback_unavailable_reason=result.get("fallback_unavailable_reason"),
            coding_runtime_audit=coding_runtime_audit,
            structured_coding_answer_used=bool(result.get("coding_answer")),
            coding_validation_status=result.get("coding_validation_status"),
            coding_answer=result.get("coding_answer"),
            **followup_resolution.to_metadata(),
            **_followup_intent_metadata(followup_intent, req.followup_context),
        )
    except ProviderError as exc:
        generation_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.warning(
            "Answer generation failed generation_ms=%s recording_ms=%s upload_ms=%s transcription_ms=%s classification_ms=%s profile_fetch_ms=%s question_len=%s error=%s provider=%s model=%s status_code=%s error_type=%s error_message=%s retry_after=%s phase=%s",
            generation_ms,
            req.recording_ms,
            req.upload_ms,
            req.transcription_ms,
            req.classification_ms,
            req.profile_fetch_ms,
            len(req.question.strip()),
            exc,
            exc.provider,
            exc.model,
            exc.status_code,
            exc.error_type,
            exc.error_message,
            exc.retry_after,
            exc.phase,
        )
        if exc.phase == "primary_generation" and exc.status_code in {429, 503}:
            retry_after_seconds = exc.retry_after
            if exc.error_type == "cooldown_active":
                safe_message = (
                    f"Coding model is cooling down after rate limit. Retry in about {max(1, int(round(retry_after_seconds or 1)))} seconds."
                )
                raise HTTPException(status_code=503, detail=safe_message) from exc
            safe_message = "Groq rate limit hit. Please retry"
            if retry_after_seconds:
                safe_message += f" after about {max(1, int(round(retry_after_seconds)))} seconds."
            else:
                safe_message += " shortly."
            raise HTTPException(status_code=429, detail=safe_message) from exc
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error generating answer: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Internal error during answer generation.",
        ) from exc


@router.get("/refinement/{job_id}", response_model=RefinementStatusResponse)
async def get_refinement_status(job_id: str):
    job = refinement_service.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Refinement job not found.")

    return RefinementStatusResponse(
        job_id=job["job_id"],
        refinement_provider=job["refinement_provider"],
        model=job["model"],
        refinement_status=job["status"],
        refined_answer=job.get("refined_answer"),
        error=job.get("error"),
    )
