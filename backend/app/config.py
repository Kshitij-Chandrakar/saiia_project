import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny.en")
    FFMPEG_PATH = os.getenv("FFMPEG_PATH", "")

    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
    GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))

    ENABLE_OLLAMA_FALLBACK = os.getenv("ENABLE_OLLAMA_FALLBACK", "true").strip().lower() == "true"
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b").strip()
    OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))

    USE_ZERO_SHOT_CLASSIFIER = os.getenv("USE_ZERO_SHOT_CLASSIFIER", "false").strip().lower() == "true"

    DB_PATH = os.getenv("DB_PATH", "data/user_profiles.db")
    PROFILE_PATH = Path(__file__).parent.parent / "candidate_profile.json"


settings = Settings()
