from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class SourceType(str, Enum):
    SCREEN_CAPTURE = "screen_capture"
    BROWSER_EXTENSION = "browser_extension"


class EnvelopeStatus(str, Enum):
    READY = "ready"
    SELECTION_REQUIRED = "selection_required"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExtractionMethod(str, Enum):
    SCREEN_VISION = "screen_vision"
    LOCAL_OCR = "local_ocr"
    COMBINED = "combined"
    GENERIC_DOM = "generic_dom"


class NormalizedQuestionType(str, Enum):
    CODING = "coding"
    DEBUGGING = "debugging"
    OUTPUT_PREDICTION = "output_prediction"
    MCQ = "mcq"
    DIAGRAM = "diagram"
    CHART = "chart"
    ARCHITECTURE = "architecture"
    SYSTEM_DESIGN = "system_design"
    TECHNICAL = "technical"
    APTITUDE = "aptitude"
    GENERAL = "general"
    UNKNOWN = "unknown"


class SubmissionMode(str, Enum):
    STANDALONE_PROGRAM = "standalone_program"
    STDIN_FULL_SOLUTION = "stdin_full_solution"
    FUNCTION_STUB = "function_stub"
    CLASS_STUB = "class_stub"
    EDITOR_TEMPLATE = "editor_template"
    EXPLANATION_ONLY = "explanation_only"
    DEBUG_FIX = "debug_fix"
    OUTPUT_PREDICTION = "output_prediction"


class LanguageSource(str, Enum):
    EXPLICIT_QUESTION = "explicit_question"
    MANUAL_OVERRIDE = "manual_override"
    WEBSITE_SELECTOR = "website_selector"
    STARTER_CODE = "starter_code"
    PREVIOUS_CONTEXT = "previous_context"
    SAVED_PREFERENCE = "saved_preference"
    CONFIGURED_FALLBACK = "configured_fallback"
    UNKNOWN = "unknown"


class SafeErrorCode(str, Enum):
    EXTENSION_NOT_CONNECTED = "extension_not_connected"
    NO_COMPLETE_QUESTIONS = "no_complete_questions"
    UNREADABLE_SCREEN = "unreadable_screen"
    INVALID_MODEL_RESPONSE = "invalid_model_response"
    RESPONSE_PARSE_FAILED = "response_parse_failed"
    CAPTURE_FAILED = "capture_failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    OPERATION_CANCELLED = "operation_cancelled"
    STALE_RESULT = "stale_result"
    UNSUPPORTED_CONTENT = "unsupported_content"
    UNKNOWN_ERROR = "unknown_error"


class QuestionOption(StrictBaseModel):
    label: str = ""
    text: str = ""


class NormalizedAnswer(StrictBaseModel):
    text: str = ""
    code: str | None = None
    explanation: str | None = None


class VisualContext(StrictBaseModel):
    diagram_present: bool = False
    chart_present: bool = False
    image_context_required: bool = False
    visual_description: str | None = None


class CodeContext(StrictBaseModel):
    selected_language: str | None = None
    language_source: LanguageSource | None = None
    starter_code: str | None = None
    function_signature: str | None = None
    class_name: str | None = None
    editor_type: str | None = None
    platform_mode: str | None = None
    submission_mode: SubmissionMode | None = None


class NormalizedQuestion(StrictBaseModel):
    question_type: NormalizedQuestionType = NormalizedQuestionType.UNKNOWN
    title: str = ""
    statement: str = ""
    function_description: str = ""
    input_format: str = ""
    output_format: str = ""
    constraints: list[str] = Field(default_factory=list)
    examples: list[dict[str, str]] = Field(default_factory=list)
    options: list[QuestionOption] = Field(default_factory=list)
    answer: NormalizedAnswer = Field(default_factory=NormalizedAnswer)
    visual_context: VisualContext = Field(default_factory=VisualContext)
    code_context: CodeContext = Field(default_factory=CodeContext)


class QuestionRegion(StrictBaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class ExtractionQuestionItem(StrictBaseModel):
    question_id: str
    display_number: str = ""
    question: NormalizedQuestion
    region: QuestionRegion | None = None

    @field_validator("question_id")
    @classmethod
    def _require_question_id(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("question_id is required")
        return normalized


class BrowserMetadata(StrictBaseModel):
    name: str | None = None
    extension_id: str | None = None
    tab_id: str | int | None = None
    window_id: str | int | None = None
    url_origin: str | None = None
    page_title: str | None = None


class ExtractionMetadata(StrictBaseModel):
    complete: bool
    confidence: float = Field(ge=0.0, le=1.0)
    missing_sections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    method: ExtractionMethod


class ExtractionTiming(StrictBaseModel):
    capture_ms: float = Field(default=0.0, ge=0)
    image_prepare_ms: float = Field(default=0.0, ge=0)
    screen_model_ms: float = Field(default=0.0, ge=0)
    response_parse_ms: float = Field(default=0.0, ge=0)
    overlay_render_ms: float | None = Field(default=None, ge=0)
    total_ms: float = Field(default=0.0, ge=0)


class ExtractionMetrics(StrictBaseModel):
    screenshot_count: int = Field(default=1, ge=0)
    screen_model_request_count: int = Field(default=1, ge=0)
    automatic_fallback_count: int = Field(default=0, ge=0)
    correction_request_count: int = Field(default=0, ge=0)
    generation_request_count: int = Field(default=0, ge=0)


class SafeExtractionError(StrictBaseModel):
    code: SafeErrorCode
    message: str
    retryable: bool = True
    details: str | None = None


class ExtractionResultEnvelope(StrictBaseModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str
    operation_id: str
    mode: Literal["screen"] = "screen"
    source_type: SourceType
    status: EnvelopeStatus
    browser: BrowserMetadata | None = None
    questions: list[ExtractionQuestionItem] = Field(default_factory=list)
    selected_question_id: str | None = None
    extraction: ExtractionMetadata
    timing: ExtractionTiming | None = None
    metrics: ExtractionMetrics | None = None
    error: SafeExtractionError | None = None

    @field_validator("request_id", "operation_id")
    @classmethod
    def _require_operation_ids(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("operation identifiers are required")
        return normalized

    @model_validator(mode="after")
    def _validate_invariants(self) -> "ExtractionResultEnvelope":
        ids = [item.question_id for item in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question_id values must be unique")
        if self.selected_question_id is not None and self.selected_question_id not in set(ids):
            raise ValueError("selected_question_id must reference a question")
        if self.status == EnvelopeStatus.READY and not self.questions:
            raise ValueError("ready envelopes require at least one question")
        if self.status == EnvelopeStatus.FAILED and self.error is None:
            raise ValueError("failed envelopes require a safe error")
        if self.status == EnvelopeStatus.CANCELLED and self.error is None:
            raise ValueError("cancelled envelopes require a safe error")
        return self
