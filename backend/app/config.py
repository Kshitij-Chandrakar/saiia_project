import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    DEBUG = os.getenv("DEBUG", "false").strip().lower() == "true"
    PERFORMANCE_MODE = os.getenv("PERFORMANCE_MODE", "standard").strip().lower()
    ANSWER_MAX_WORDS = int(os.getenv("ANSWER_MAX_WORDS", "160"))
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny.en")
    FFMPEG_PATH = os.getenv("FFMPEG_PATH", "")
    STT_PROVIDER = os.getenv("STT_PROVIDER", "assemblyai").strip().lower()
    MANUAL_STT_PROVIDER = os.getenv("MANUAL_STT_PROVIDER", "groq").strip().lower()
    STT_FALLBACK_PROVIDER = os.getenv("STT_FALLBACK_PROVIDER", "whisper_local").strip().lower()
    AUTO_STT_PROVIDER = os.getenv("AUTO_STT_PROVIDER", "assemblyai_streaming").strip().lower()
    AUTO_STT_FALLBACK_PROVIDER = os.getenv("AUTO_STT_FALLBACK_PROVIDER", "whisper_local").strip().lower()
    ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
    ASSEMBLYAI_STT_MODEL = os.getenv("ASSEMBLYAI_STT_MODEL", "best").strip().lower()
    ASSEMBLYAI_STREAMING_URL = (
        os.getenv("ASSEMBLYAI_STREAMING_URL", "wss://streaming.assemblyai.com/v3/ws").strip().rstrip("/")
    )
    ASSEMBLYAI_STREAMING_SAMPLE_RATE = int(os.getenv("ASSEMBLYAI_STREAMING_SAMPLE_RATE", "16000"))
    ASSEMBLYAI_STREAMING_SPEECH_MODEL = os.getenv(
        "ASSEMBLYAI_STREAMING_SPEECH_MODEL",
        "universal-streaming-english",
    ).strip()
    SYSTEM_AUDIO_DEBUG_SAVE = os.getenv("SYSTEM_AUDIO_DEBUG_SAVE", "false").strip().lower() == "true"
    SYSTEM_AUDIO_GAIN = float(os.getenv("SYSTEM_AUDIO_GAIN", "2.0"))
    SYSTEM_AUDIO_MAX_GAIN = float(os.getenv("SYSTEM_AUDIO_MAX_GAIN", "4.0"))
    SCREEN_VISION_PROVIDER = os.getenv("SCREEN_VISION_PROVIDER", "openai").strip().lower()
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
    OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")
    OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "").strip()
    OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "SAIIA").strip()
    SCREEN_VISION_MODEL = os.getenv(
        "SCREEN_VISION_MODEL",
        "gpt-5-nano-2025-08-07",
    ).strip()
    SCREEN_VISION_FALLBACK_MODEL = os.getenv(
        "SCREEN_VISION_FALLBACK_MODEL",
        "gpt-5.4-nano-2026-03-17",
    ).strip()
    ENABLE_SCREEN_VISION_FALLBACK = (
        os.getenv("ENABLE_SCREEN_VISION_FALLBACK", "true").strip().lower() == "true"
    )
    ENABLE_LOCAL_OCR_PREPASS = os.getenv("ENABLE_LOCAL_OCR_PREPASS", "true").strip().lower() == "true"
    ENABLE_LOCAL_OCR_SHORT_CIRCUIT = (
        os.getenv("ENABLE_LOCAL_OCR_SHORT_CIRCUIT", "true").strip().lower() == "true"
    )
    SCREEN_VISION_DETAIL = os.getenv("SCREEN_VISION_DETAIL", "high").strip().lower()
    SCREEN_VISION_CONFIDENCE_THRESHOLD = float(os.getenv("SCREEN_VISION_CONFIDENCE_THRESHOLD", "0.72"))
    SCREEN_VISION_MAX_OUTPUT_TOKENS = int(os.getenv("SCREEN_VISION_MAX_OUTPUT_TOKENS", "1800"))
    SCREEN_VISION_TIMEOUT_SECONDS = float(
        os.getenv(
            "SCREEN_VISION_TIMEOUT_SECONDS",
            str(float(os.getenv("SCREEN_VISION_TIMEOUT_MS", "15000")) / 1000),
        )
    )
    SCREEN_VISION_FALLBACK_TIMEOUT_SECONDS = float(os.getenv("SCREEN_VISION_FALLBACK_TIMEOUT_SECONDS", "20"))
    SCREEN_VISION_TIMEOUT_MS = int(SCREEN_VISION_TIMEOUT_SECONDS * 1000)
    SCREEN_VISION_MAX_IMAGE_WIDTH = int(os.getenv("SCREEN_VISION_MAX_IMAGE_WIDTH", "1600"))
    SCREEN_VISION_FALLBACK_OCR = (
        os.getenv("ENABLE_RAPIDOCR_FALLBACK", os.getenv("SCREEN_VISION_FALLBACK_OCR", "true")).strip().lower()
        == "true"
    )
    SCREEN_ANALYZE_DEBUG_SAVE = os.getenv("SCREEN_ANALYZE_DEBUG_SAVE", "false").strip().lower() == "true"
    SCREEN_FULL_CAPTURE_ENABLED = os.getenv("SCREEN_FULL_CAPTURE_ENABLED", "true").strip().lower() == "true"
    SCREEN_FULL_CAPTURE_MAX_SCROLLS = int(os.getenv("SCREEN_FULL_CAPTURE_MAX_SCROLLS", "4"))
    SCREEN_FULL_CAPTURE_SCROLL_AMOUNT = float(os.getenv("SCREEN_FULL_CAPTURE_SCROLL_AMOUNT", "0.75"))
    SCREEN_FULL_CAPTURE_WAIT_MS = int(os.getenv("SCREEN_FULL_CAPTURE_WAIT_MS", "250"))
    SCREEN_FULL_CAPTURE_RESTORE_SCROLL = (
        os.getenv("SCREEN_FULL_CAPTURE_RESTORE_SCROLL", "true").strip().lower() == "true"
    )
    RESUME_PARSER_PROVIDER = os.getenv("RESUME_PARSER_PROVIDER", "gpt").strip().lower()
    RESUME_PARSER_FALLBACK = os.getenv("RESUME_PARSER_FALLBACK", "local").strip().lower()
    RESUME_GPT_PARSER_ENABLED = os.getenv("RESUME_GPT_PARSER_ENABLED", "true").strip().lower() == "true"
    RESUME_GPT_MODEL = os.getenv("RESUME_GPT_MODEL", "gpt-5-mini").strip()
    RESUME_GPT_TIMEOUT_SECONDS = float(os.getenv("RESUME_GPT_TIMEOUT_SECONDS", "20"))
    RESUME_GPT_MAX_INPUT_CHARS = int(os.getenv("RESUME_GPT_MAX_INPUT_CHARS", "30000"))
    RESUME_GPT_REASONING_EFFORT = os.getenv("RESUME_GPT_REASONING_EFFORT", "minimal").strip().lower()
    RESUME_GPT_MAX_OUTPUT_TOKENS = int(os.getenv("RESUME_GPT_MAX_OUTPUT_TOKENS", "2500"))
    RESUME_GPT_MAX_RETRIES = int(os.getenv("RESUME_GPT_MAX_RETRIES", "0"))
    AFFINDA_API_KEY = os.getenv("AFFINDA_API_KEY", "").strip()
    AFFINDA_WORKSPACE = os.getenv("AFFINDA_WORKSPACE", "").strip()
    AFFINDA_DOCUMENT_TYPE = os.getenv("AFFINDA_DOCUMENT_TYPE", "").strip()
    AFFINDA_COLLECTION = os.getenv("AFFINDA_COLLECTION", "").strip()
    AFFINDA_API_BASE_URL = (
        os.getenv("AFFINDA_API_BASE_URL", "").strip()
        or os.getenv("AFFINDA_BASE_URL", "https://api.affinda.com").strip()
    ).rstrip("/")
    AFFINDA_BASE_URL = AFFINDA_API_BASE_URL
    AFFINDA_TIMEOUT_SECONDS = float(os.getenv("AFFINDA_TIMEOUT_SECONDS", "45"))

    ANSWER_PROVIDER = os.getenv("ANSWER_PROVIDER", "openai").strip().lower()
    ANSWER_FALLBACK_PROVIDER = os.getenv("ANSWER_FALLBACK_PROVIDER", "groq").strip().lower()
    ENABLE_ANSWER_PROVIDER_FALLBACK = os.getenv("ENABLE_ANSWER_PROVIDER_FALLBACK", "true").strip().lower() == "true"

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini-2026-03-17").strip()
    AI_NOTES_MODEL = os.getenv("AI_NOTES_MODEL", OPENAI_MODEL).strip()
    AI_NOTES_TIMEOUT_SECONDS = float(os.getenv("AI_NOTES_TIMEOUT_SECONDS", "20"))
    AI_NOTES_MAX_INPUT_CHARS = int(os.getenv("AI_NOTES_MAX_INPUT_CHARS", "18000"))
    AI_NOTES_MAX_OUTPUT_TOKENS = int(os.getenv("AI_NOTES_MAX_OUTPUT_TOKENS", "2500"))
    AI_NOTES_REASONING_EFFORT = os.getenv("AI_NOTES_REASONING_EFFORT", "low").strip().lower()
    OPENAI_DEFAULT_REASONING_EFFORT = os.getenv("OPENAI_DEFAULT_REASONING_EFFORT", "low").strip().lower()
    OPENAI_COMPLEX_REASONING_EFFORT = os.getenv("OPENAI_COMPLEX_REASONING_EFFORT", "medium").strip().lower()
    OPENAI_VALIDATION_REASONING_EFFORT = os.getenv("OPENAI_VALIDATION_REASONING_EFFORT", "low").strip().lower()
    OPENAI_CORRECTION_REASONING_EFFORT = os.getenv("OPENAI_CORRECTION_REASONING_EFFORT", "low").strip().lower()
    OPENAI_PRIMARY_TIMEOUT_SECONDS = float(os.getenv("OPENAI_PRIMARY_TIMEOUT_SECONDS", "25"))
    OPENAI_VALIDATION_TIMEOUT_SECONDS = float(os.getenv("OPENAI_VALIDATION_TIMEOUT_SECONDS", "15"))
    OPENAI_CORRECTION_TIMEOUT_SECONDS = float(os.getenv("OPENAI_CORRECTION_TIMEOUT_SECONDS", "20"))
    OPENAI_STANDARD_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_STANDARD_MAX_OUTPUT_TOKENS", "2500"))
    OPENAI_PERSONAL_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_PERSONAL_MAX_OUTPUT_TOKENS", "2500"))
    OPENAI_CODING_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_CODING_MAX_OUTPUT_TOKENS", "6000"))
    OPENAI_SYSTEM_DESIGN_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_SYSTEM_DESIGN_MAX_OUTPUT_TOKENS", "5000"))
    ENABLE_SEMANTIC_VALIDATION = os.getenv("ENABLE_SEMANTIC_VALIDATION", "true").strip().lower() == "true"
    ENABLE_CONDITIONAL_CORRECTION = os.getenv("ENABLE_CONDITIONAL_CORRECTION", "true").strip().lower() == "true"
    ENABLE_ALWAYS_ON_REFINEMENT = os.getenv("ENABLE_ALWAYS_ON_REFINEMENT", "false").strip().lower() == "true"
    ENABLE_TRUE_ANSWER_STREAMING = os.getenv("ENABLE_TRUE_ANSWER_STREAMING", "true").strip().lower() == "true"
    ENABLE_CONTROLLED_ANSWER_VARIATION = (
        os.getenv("ENABLE_CONTROLLED_ANSWER_VARIATION", "true").strip().lower() == "true"
    )
    VARIATION_HISTORY_LIMIT = max(1, int(os.getenv("VARIATION_HISTORY_LIMIT", "3")))
    VARIATION_CACHE_TTL_SECONDS = max(60, int(os.getenv("VARIATION_CACHE_TTL_SECONDS", "7200")))
    ENABLE_VARIATION_REWRITE = os.getenv("ENABLE_VARIATION_REWRITE", "true").strip().lower() == "true"
    ENABLE_LIVE_FOLLOWUP_RESOLUTION = (
        os.getenv("ENABLE_LIVE_FOLLOWUP_RESOLUTION", "true").strip().lower() == "true"
    )
    FOLLOWUP_HISTORY_LIMIT = max(1, int(os.getenv("FOLLOWUP_HISTORY_LIMIT", "5")))
    FOLLOWUP_CONTEXT_TTL_SECONDS = max(60, int(os.getenv("FOLLOWUP_CONTEXT_TTL_SECONDS", "1800")))
    ENABLE_MODEL_ASSISTED_FOLLOWUP_RESOLUTION = (
        os.getenv("ENABLE_MODEL_ASSISTED_FOLLOWUP_RESOLUTION", "false").strip().lower() == "true"
    )
    ENABLE_FOLLOWUP_INTENT_COMPILER = (
        os.getenv("ENABLE_FOLLOWUP_INTENT_COMPILER", "true").strip().lower() == "true"
    )

    LLM_PROVIDER = os.getenv("LLM_PROVIDER", ANSWER_PROVIDER).strip().lower()
    PRIMARY_LLM_PROVIDER = (
        os.getenv("PRIMARY_LLM_PROVIDER", "").strip().lower()
        or LLM_PROVIDER
    )

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
    PRIMARY_GROQ_MODEL = (
        os.getenv("PRIMARY_GROQ_MODEL", "").strip()
        or GROQ_MODEL
    )
    GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))
    GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo").strip()

    REFINEMENT_ENABLED = (
        os.getenv("REFINEMENT_ENABLED", os.getenv("ENABLE_ALWAYS_ON_REFINEMENT", "false")).strip().lower()
        == "true"
    )
    REFINEMENT_PROVIDER = os.getenv("REFINEMENT_PROVIDER", "groq").strip().lower()
    CODING_GROQ_MODEL = os.getenv("CODING_GROQ_MODEL", "qwen/qwen3.6-27b").strip()
    CODING_MAX_TOKENS = min(int(os.getenv("CODING_MAX_TOKENS", "1600")), 2000)
    REFINEMENT_GROQ_MODEL = os.getenv("REFINEMENT_GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    REFINEMENT_TIMEOUT_MS = int(os.getenv("REFINEMENT_TIMEOUT_MS", "2500"))
    REFINEMENT_MAX_WORDS = int(os.getenv("REFINEMENT_MAX_WORDS", "120"))

    ENABLE_NVIDIA_REFINEMENT = os.getenv("ENABLE_NVIDIA_REFINEMENT", "false").strip().lower() == "true"
    ENABLE_PROVIDER_ROUTER = os.getenv("ENABLE_PROVIDER_ROUTER", "false").strip().lower() == "true"
    ENABLE_PARALLEL_REFINEMENT = os.getenv("ENABLE_PARALLEL_REFINEMENT", "false").strip().lower() == "true"
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
    NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip().rstrip("/")
    NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-pro").strip()
    NVIDIA_TIMEOUT_SECONDS = float(os.getenv("NVIDIA_TIMEOUT_SECONDS", "45"))
    REFINEMENT_JOB_TIMEOUT_SECONDS = float(
        os.getenv("REFINEMENT_JOB_TIMEOUT_SECONDS", str(max(NVIDIA_TIMEOUT_SECONDS + 5, 20)))
    )

    ENABLE_OLLAMA_FALLBACK = os.getenv("ENABLE_OLLAMA_FALLBACK", "true").strip().lower() == "true"
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b").strip()
    OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
    RAG_RETRIEVAL_LIMIT = int(os.getenv("RAG_RETRIEVAL_LIMIT", "2"))
    RAG_TIMEOUT_MS = float(os.getenv("RAG_TIMEOUT_MS", "120"))

    USE_ZERO_SHOT_CLASSIFIER = os.getenv("USE_ZERO_SHOT_CLASSIFIER", "false").strip().lower() == "true"

    DB_PATH = os.getenv("DB_PATH", "data/user_profiles.db")
    PROFILE_PATH = Path(__file__).parent.parent / "candidate_profile.json"


settings = Settings()
