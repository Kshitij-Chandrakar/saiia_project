import io
import json
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

scipy_module = types.ModuleType("scipy")
scipy_signal_module = types.ModuleType("scipy.signal")
scipy_signal_module.resample_poly = lambda data, up, down: data
sys.modules.setdefault("scipy", scipy_module)
sys.modules.setdefault("scipy.signal", scipy_signal_module)

from app.api import screen_ocr as screen_ocr_api
from app.config import settings
from app.services.screen_vision_service import ScreenVisionService


def _image_bytes() -> tuple[bytes, str, str]:
    image = Image.new("RGB", (420, 240), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), "screen.png", "image/png"


def _json_payload(**overrides: Any) -> str:
    payload = {
        "is_question": True,
        "question_type": "interview",
        "question": "What is a context window in language models?",
        "full_problem_text": "What is a context window in language models?",
        "editor_text": "",
        "input_format": "",
        "output_format": "",
        "sample_input": "",
        "sample_output": "",
        "options": [],
        "visible_error": "",
        "confidence": 0.92,
        "reason": "Detected central interview question.",
        "source_region": "main_content",
    }
    payload.update(overrides)
    return json.dumps(payload)


def _direct_answer_payload(**overrides: Any) -> str:
    payload = {
        "ok": True,
        "result_mode": "single",
        "question_type": "general",
        "question": "What is an array?",
        "answer": "An array stores multiple values under one name.\n\nReal-life example:\nA list of scores can be stored together and read by position.",
        "language": "",
        "code": "",
        "items": [],
        "question_count": 1,
        "incomplete_question_count": 0,
        "confidence": 0.9,
        "incomplete": False,
        "reason": "Visible central question.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def _direct_batch_payload() -> str:
    return _direct_answer_payload(
        result_mode="batch",
        question_type="mcq",
        question="Question 7: The chief ore of Aluminium is?\nQuestion 8: The first train in India ran from Bombay to ...?\nQuestion 9: Deficiency of iron causes?",
        answer="7. c. Bauxite\n8. d. Thane\n9. d. Anaemia",
        items=[
            {
                "question_id": "screen_question_1",
                "display_number": "7",
                "question": "The chief ore of Aluminium is?",
                "question_type": "mcq",
                "answer": "c. Bauxite",
                "language": "",
                "code": "",
                "confidence": 0.96,
            },
            {
                "question_id": "screen_question_2",
                "display_number": "8",
                "question": "The first train in India ran from Bombay to ...?",
                "question_type": "mcq",
                "answer": "d. Thane",
                "language": "",
                "code": "",
                "confidence": 0.93,
            },
            {
                "question_id": "screen_question_3",
                "display_number": "9",
                "question": "Deficiency of iron causes?",
                "question_type": "mcq",
                "answer": "d. Anaemia",
                "language": "",
                "code": "",
                "confidence": 0.94,
            },
        ],
        question_count=3,
        incomplete_question_count=1,
        confidence=0.94,
    )


class FakeResponses:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if not self.outputs:
            raise AssertionError("unexpected OpenAI call")
        return SimpleNamespace(output_text=self.outputs.pop(0))


class FakeOpenAIClient:
    def __init__(self, outputs: list[str]) -> None:
        self.responses = FakeResponses(outputs)


@pytest.fixture()
def openai_screen_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SCREEN_VISION_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(settings, "SCREEN_VISION_MODEL", "gpt-5-nano-2025-08-07")
    monkeypatch.setattr(settings, "SCREEN_VISION_FALLBACK_MODEL", "gpt-5.4-nano-2026-03-17")
    monkeypatch.setattr(settings, "ENABLE_SCREEN_VISION_FALLBACK", True)
    monkeypatch.setattr(settings, "SCREEN_VISION_TIMEOUT_SECONDS", 15.0)
    monkeypatch.setattr(settings, "SCREEN_VISION_FALLBACK_TIMEOUT_SECONDS", 20.0)
    monkeypatch.setattr(settings, "SCREEN_VISION_MAX_OUTPUT_TOKENS", 1800)
    monkeypatch.setattr(settings, "SCREEN_VISION_DETAIL", "high")
    monkeypatch.setattr(settings, "SCREEN_VISION_CONFIDENCE_THRESHOLD", 0.72)
    monkeypatch.setattr(settings, "SCREEN_VISION_FALLBACK_OCR", True)
    monkeypatch.setattr(settings, "ENABLE_LOCAL_OCR_PREPASS", False)
    monkeypatch.setattr(settings, "ENABLE_LOCAL_OCR_SHORT_CIRCUIT", False)
    monkeypatch.setattr(settings, "SCREEN_ANALYZE_DEBUG_SAVE", False)


def _run_service(service: ScreenVisionService) -> dict[str, Any]:
    image, filename, content_type = _image_bytes()
    return service.analyze_image(filename=filename, content=image, content_type=content_type)


def test_openai_primary_success_uses_exact_nano_model(openai_screen_settings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    service = ScreenVisionService()
    client = FakeOpenAIClient([_json_payload()])
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)

    result = _run_service(service)

    assert result["ok"] is True
    assert result["vision_provider"] == "openai"
    assert result["vision_model"] == "gpt-5-nano-2025-08-07"
    assert result["vision_fallback_used"] is False
    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["model"] == "gpt-5-nano-2025-08-07"
    assert call["model"] != "gpt-5-nano"
    assert call["input"][0]["content"][0]["type"] == "input_text"
    assert call["input"][0]["content"][1]["type"] == "input_image"
    assert call["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert call["text"]["format"]["type"] == "json_schema"
    assert "test-openai-key" not in json.dumps(call)


def test_direct_screen_answer_uses_one_openai_call_without_extraction_fallback(
    openai_screen_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScreenVisionService()
    client = FakeOpenAIClient([_direct_answer_payload()])
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)
    image, filename, content_type = _image_bytes()

    result = service.answer_image(filename=filename, content=image, content_type=content_type)

    assert result["ok"] is True
    assert result["answer"]
    assert result["screenshot_count"] == 1
    assert result["screen_model_request_count"] == 1
    assert result["extraction_request_count"] == 1
    assert result["generation_request_count"] == 0
    assert result["automatic_fallback_count"] == 0
    assert result["correction_request_count"] == 0
    assert result["fallback_used"] is False
    assert result["image_prepare_ms"] >= 0
    assert result["screen_model_ms"] >= 0
    assert result["response_parse_ms"] >= 0
    assert result["original_image_width"] == 420
    assert result["original_image_height"] == 240
    assert result["image_width"] > 0
    assert result["image_height"] > 0
    assert result["encoded_image_bytes"] > 0
    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["model"] == "gpt-5-nano-2025-08-07"
    assert call["text"]["format"]["name"] == "screen_direct_answer"
    assert call["reasoning"] == {"effort": "low"}
    prompt = call["input"][0]["content"][0]["text"]
    assert "Do not answer during this extraction step" not in prompt
    assert "ignore checked radio buttons" in prompt.lower()
    assert "detect every fully visible question" in prompt.lower()
    assert "preserve top-to-bottom screen order" in prompt.lower()
    assert "do not merge independent questions" in prompt.lower()
    assert "separate model calls" in prompt.lower()
    assert "for mcq batch results" in prompt.lower()
    assert "do not include explanations" in prompt.lower()
    assert "including single mcqs" in prompt.lower()
    assert "do not include a reason" in prompt.lower()


def test_direct_screen_answer_returns_all_visible_mcqs_in_one_request(
    openai_screen_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScreenVisionService()
    client = FakeOpenAIClient([_direct_batch_payload()])
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)
    image, filename, content_type = _image_bytes()

    result = service.answer_image(filename=filename, content=image, content_type=content_type)

    assert result["ok"] is True
    assert result["result_mode"] == "batch"
    assert result["question_type"] == "mcq"
    assert result["question_count"] == 3
    assert result["incomplete_question_count"] == 1
    assert [item["display_number"] for item in result["items"]] == ["7", "8", "9"]
    assert [item["answer"] for item in result["items"]] == ["c. Bauxite", "d. Thane", "d. Anaemia"]
    assert "10." not in result["answer"]
    assert result["answer"] == "7. c. Bauxite\n8. d. Thane\n9. d. Anaemia"
    assert result["screenshot_count"] == 1
    assert result["screen_model_request_count"] == 1
    assert result["generation_request_count"] == 0
    assert result["automatic_fallback_count"] == 0
    assert result["correction_request_count"] == 0
    assert len(client.responses.calls) == 1


def test_direct_screen_answer_single_mcq_is_option_only(
    openai_screen_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScreenVisionService()
    client = FakeOpenAIClient([
        _direct_answer_payload(
            question_type="mcq",
            question="Aam Admi Bima Yojana was launched on:",
            answer="D. October 2, 2007 - It was launched in October 2007 as part of the social security initiatives.",
            items=[
                {
                    "question_id": "screen_question_1",
                    "display_number": "",
                    "question": "Aam Admi Bima Yojana was launched on:",
                    "question_type": "mcq",
                    "answer": "D. October 2, 2007 - It was launched in October 2007 as part of the social security initiatives.",
                    "language": "",
                    "code": "",
                    "confidence": 0.91,
                }
            ],
            question_count=1,
        )
    ])
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)
    image, filename, content_type = _image_bytes()

    result = service.answer_image(filename=filename, content=image, content_type=content_type)

    assert result["answer"] == "D. October 2, 2007"
    assert result["items"][0]["answer"] == "D. October 2, 2007"


def test_direct_screen_answer_prompt_ignores_incorrect_selected_options(
    openai_screen_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScreenVisionService()
    client = FakeOpenAIClient([_direct_batch_payload()])
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)
    image, filename, content_type = _image_bytes()

    service.answer_image(filename=filename, content=image, content_type=content_type)

    prompt = client.responses.calls[0]["input"][0]["content"][0]["text"].lower()
    assert "ignore checked radio buttons" in prompt
    assert "selected checkboxes" in prompt
    assert "green/red correctness markers" in prompt
    assert "solve independently" in prompt


def test_direct_screen_answer_unreadable_returns_no_answer(
    openai_screen_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScreenVisionService()
    client = FakeOpenAIClient([
        _direct_answer_payload(
            ok=False,
            question_type="none",
            question="",
            answer="",
            language="",
            code="",
            confidence=0,
            incomplete=True,
            reason="No readable question.",
        )
    ])
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)
    image, filename, content_type = _image_bytes()

    result = service.answer_image(filename=filename, content=image, content_type=content_type)

    assert result["ok"] is False
    assert result["answer"] == ""
    assert result["question_type"] == "none"
    assert result["incomplete"] is True
    assert len(client.responses.calls) == 1


def test_direct_screen_answer_accepts_coding_language_and_code(
    openai_screen_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ScreenVisionService()
    client = FakeOpenAIClient([
        _direct_answer_payload(
            question_type="coding",
            question="Write binary search in Python.",
            answer="### Approach\nUse two pointers.\n\n### Code\n```python\ndef binary_search(nums, target):\n    return -1\n```\n\nTime Complexity: O(log n)\nSpace Complexity: O(1)",
            language="python",
            code="def binary_search(nums, target):\n    return -1",
        )
    ])
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)
    image, filename, content_type = _image_bytes()

    result = service.answer_image(filename=filename, content=image, content_type=content_type)

    assert result["ok"] is True
    assert result["result_mode"] == "single"
    assert result["question_count"] == 1
    assert result["question_type"] == "coding"
    assert result["language"] == "python"
    assert "binary_search" in result["code"]
    prompt = client.responses.calls[0]["input"][0]["content"][0]["text"].lower()
    assert "do not treat examples, sample cases, editor content" in prompt


def test_openai_low_confidence_uses_gpt54_nano_fallback(openai_screen_settings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    service = ScreenVisionService()
    client = FakeOpenAIClient(
        [
            _json_payload(confidence=0.4, reason="Low confidence extraction."),
            _json_payload(question="Explain REST APIs.", full_problem_text="Explain REST APIs.", confidence=0.91),
        ]
    )
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)

    result = _run_service(service)

    assert result["ok"] is True
    assert result["vision_model"] == "gpt-5.4-nano-2026-03-17"
    assert result["vision_fallback_used"] is True
    assert result["screen_vision_fallback_model"] == "gpt-5.4-nano-2026-03-17"
    assert [call["model"] for call in client.responses.calls] == [
        "gpt-5-nano-2025-08-07",
        "gpt-5.4-nano-2026-03-17",
    ]


def test_openai_failure_uses_rapidocr_final_fallback(openai_screen_settings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    service = ScreenVisionService()
    client = FakeOpenAIClient(["not json", ""])
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)
    monkeypatch.setattr(
        service._ocr_service,
        "extract_text",
        lambda **kwargs: {
            "extracted_text": "Explain supervised machine learning.",
            "confidence": 0.9,
            "ocr_ms": 1.0,
            "text_length": 36,
        },
    )

    result = _run_service(service)

    assert result["fallback_ocr_used"] is True
    assert result["vision_fallback_used"] is True
    assert result["vision_provider"] == "rapidocr_fallback"
    assert result["ok"] is True


def test_local_ocr_short_circuit_avoids_openai_call(openai_screen_settings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_LOCAL_OCR_PREPASS", True)
    monkeypatch.setattr(settings, "ENABLE_LOCAL_OCR_SHORT_CIRCUIT", True)
    service = ScreenVisionService()
    client = FakeOpenAIClient([_json_payload()])
    monkeypatch.setattr(service, "_get_openai_client", lambda: client)
    monkeypatch.setattr(
        service,
        "_analyze_with_ocr_fallback",
        lambda **kwargs: {
            "raw_text": "Explain API rate limits?",
            "raw_vision_json": "",
            "cleaned_text": "Explain API rate limits?",
            "question": "Explain API rate limits?",
            "question_type": "interview",
            "is_question": True,
            "confidence": 0.91,
            "reason": "high_confidence_simple_text",
            "vision_ms": 1.0,
            "rejected_ui_noise": False,
            "rejected_code_boilerplate": False,
            "ui_noise_ratio": 0.0,
            "source_region": "main_content",
        },
    )

    result = _run_service(service)

    assert result["vision_provider"] == "rapidocr_short_circuit"
    assert result["local_ocr_short_circuit_used"] is True
    assert client.responses.calls == []


def test_missing_openai_key_uses_rapidocr_without_cloud_fallback(openai_screen_settings: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    service = ScreenVisionService()
    monkeypatch.setattr(
        service._ocr_service,
        "extract_text",
        lambda **kwargs: {
            "extracted_text": "What is authentication?",
            "confidence": 0.9,
            "ocr_ms": 1.0,
            "text_length": 23,
        },
    )

    result = _run_service(service)

    assert result["fallback_ocr_used"] is True
    assert result["vision_error"] == "missing_api_key"
    assert result["ok"] is True


def test_openai_provider_metadata_preserves_frontend_response_fields(
    openai_screen_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_analyze_image(**kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "capture_target": "active_external_window",
            "window_title": "Window",
            "process_name": "chrome",
            "image_width": 1,
            "image_height": 1,
            "vision_provider": "openai",
            "vision_model": "gpt-5-nano-2025-08-07",
            "screen_vision_fallback_model": "gpt-5.4-nano-2026-03-17",
            "screen_vision_detail": "high",
            "local_ocr_used": True,
            "local_ocr_short_circuit_used": False,
            "primary_vision_ms": 2.0,
            "fallback_vision_ms": 0.0,
            "raw_vision_text": "{}",
            "raw_vision_json": "{}",
            "cleaned_text": "Question?",
            "extracted_question": "Question?",
            "question_type": "interview",
            "is_question": True,
            "confidence": 0.8,
            "capture_ms": 1.0,
            "vision_ms": 2.0,
            "fallback_ocr_used": False,
            "screenshot_hid_saiia_windows": False,
            "final_extracted_question": "Question?",
            "valid_problem_found": True,
        }

    monkeypatch.setattr(screen_ocr_api.screen_vision_service, "analyze_image", fake_analyze_image)
    test_app = FastAPI()
    test_app.include_router(screen_ocr_api.router)
    image, filename, content_type = _image_bytes()

    response = TestClient(test_app).post(
        "/api/screen/analyze-active-window",
        files={"file": (filename, image, content_type)},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["vision_provider"] == "openai"
    assert payload["screen_vision_fallback_model"] == "gpt-5.4-nano-2026-03-17"
    assert payload["local_ocr_used"] is True
    assert payload["groq_vision_attempted"] is False


def test_active_window_answer_endpoint_preserves_batch_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = json.loads(_direct_batch_payload())["items"]

    def fake_answer_image(**kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "capture_target": "active_external_window",
            "window_title": "Quiz",
            "process_name": "chrome",
            "original_image_width": 420,
            "original_image_height": 240,
            "image_width": 420,
            "image_height": 240,
            "encoded_image_bytes": 1000,
            "vision_provider": "openai",
            "vision_model": "gpt-5-nano-2025-08-07",
            "result_mode": "batch",
            "question": "Q7\nQ8\nQ9",
            "answer": "7. c. Bauxite\n8. d. Thane\n9. d. Anaemia",
            "language": "",
            "code": "",
            "items": items,
            "question_count": 3,
            "incomplete_question_count": 1,
            "question_type": "mcq",
            "confidence": 0.94,
            "incomplete": False,
            "capture_ms": 0.0,
            "image_prepare_ms": 1.0,
            "upload_ms": 0.0,
            "screen_model_ms": 2.0,
            "response_parse_ms": 1.0,
            "overlay_render_ms": 0.0,
            "total_screen_pipeline_ms": 3.0,
            "vision_ms": 2.0,
            "vision_latency_ms": 2.0,
            "screenshot_count": 1,
            "screen_model_request_count": 1,
            "extraction_request_count": 1,
            "generation_request_count": 0,
            "automatic_fallback_count": 0,
            "correction_request_count": 0,
        }

    monkeypatch.setattr(screen_ocr_api.screen_vision_service, "answer_image", fake_answer_image)
    test_app = FastAPI()
    test_app.include_router(screen_ocr_api.router)
    image, filename, content_type = _image_bytes()

    response = TestClient(test_app).post(
        "/api/screen/analyze-active-window-answer",
        files={"file": (filename, image, content_type)},
        data={
            "operation_id": "op_batch_1",
            "request_id": "req_batch_1",
            "source_type": "screen_capture",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["operation_id"] == "op_batch_1"
    assert payload["request_id"] == "req_batch_1"
    assert payload["source_type"] == "screen_capture"
    assert payload["result_mode"] == "batch"
    assert payload["question_count"] == 3
    assert payload["incomplete_question_count"] == 1
    assert [item["display_number"] for item in payload["items"]] == ["7", "8", "9"]
    assert payload["envelope"]["schema_version"] == "1.0"
    assert payload["envelope"]["operation_id"] == "op_batch_1"
    assert payload["envelope"]["request_id"] == "req_batch_1"
    assert payload["envelope"]["source_type"] == "screen_capture"
    assert payload["envelope"]["browser"] is None
    assert payload["envelope"]["status"] == "ready"
    assert payload["envelope"]["selected_question_id"] is None
    assert payload["envelope"]["questions"][0]["display_number"] == "7"
    assert payload["envelope"]["questions"][0]["question"]["answer"]["text"] == "c. Bauxite"
    assert payload["envelope"]["questions"][0]["question"]["question_type"] == "mcq"
    assert payload["envelope"]["metrics"]["screenshot_count"] == payload["screenshot_count"]
    assert payload["envelope"]["metrics"]["screen_model_request_count"] == payload["screen_model_request_count"]
    assert payload["envelope"]["metrics"]["generation_request_count"] == payload["generation_request_count"]
    assert payload["answer"] == "7. c. Bauxite\n8. d. Thane\n9. d. Anaemia"


def test_extension_unavailable_endpoint_returns_failed_browser_extension_operation() -> None:
    test_app = FastAPI()
    test_app.include_router(screen_ocr_api.router)

    response = TestClient(test_app).post(
        "/api/screen/extension-unavailable",
        data={
            "operation_id": "op_extension_1",
            "request_id": "req_extension_1",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["ok"] is False
    assert payload["operation_id"] == "op_extension_1"
    assert payload["request_id"] == "req_extension_1"
    assert payload["source_type"] == "browser_extension"
    assert payload["question"] == ""
    assert payload["answer"] == ""
    assert payload["question_count"] == 0
    assert payload["screenshot_count"] == 0
    assert payload["screen_model_request_count"] == 0
    assert payload["generation_request_count"] == 0
    assert payload["envelope"]["status"] == "failed"
    assert payload["envelope"]["source_type"] == "browser_extension"
    assert payload["envelope"]["error"]["code"] == "extension_not_connected"
