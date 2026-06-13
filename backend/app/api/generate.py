import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.nlp.answer_generator import AnswerGenerator, ProviderError

router = APIRouter()
logger = logging.getLogger("generate_api")
logging.basicConfig(level=logging.INFO)

generator = AnswerGenerator(include_context=True)


class GenerateRequest(BaseModel):
    question: str
    category: str
    profile: Optional[Dict[str, Any]] = None
    transcription_ms: Optional[float] = None
    classification_ms: Optional[float] = None
    profile_fetch_ms: Optional[float] = None
    total_pipeline_ms: Optional[float] = None


class GenerateResponse(BaseModel):
    answer: str
    provider: str
    model: str
    fallback_used: bool
    error: Optional[str] = None
    generation_ms: float
    transcription_ms: Optional[float] = None
    classification_ms: Optional[float] = None
    profile_fetch_ms: Optional[float] = None
    total_pipeline_ms: Optional[float] = None


@router.post("/", response_model=GenerateResponse)
async def generate_answer(req: GenerateRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="`question` field cannot be empty.")
    if not req.category or not req.category.strip():
        raise HTTPException(status_code=400, detail="`category` field cannot be empty.")

    started = time.perf_counter()

    try:
        result = generator.generate_answer(
            question=req.question,
            question_type=req.category,
            profile=req.profile or {},
        )

        total_pipeline_ms = req.total_pipeline_ms
        if total_pipeline_ms is None:
            total_pipeline_ms = round(
                (
                    (req.transcription_ms or 0)
                    + (req.classification_ms or 0)
                    + (req.profile_fetch_ms or 0)
                    + result["generation_ms"]
                ),
                2,
            )

        logger.info(
            "Answer generation completed provider=%s model=%s fallback_used=%s generation_ms=%s transcription_ms=%s classification_ms=%s profile_fetch_ms=%s total_pipeline_ms=%s question_len=%s profile_keys=%s",
            result["provider"],
            result["model"],
            result["fallback_used"],
            result["generation_ms"],
            req.transcription_ms,
            req.classification_ms,
            req.profile_fetch_ms,
            total_pipeline_ms,
            len(req.question.strip()),
            sorted((req.profile or {}).keys()),
        )

        return GenerateResponse(
            answer=result["answer"],
            provider=result["provider"],
            model=result["model"],
            fallback_used=result["fallback_used"],
            error=result["error"],
            generation_ms=result["generation_ms"],
            transcription_ms=req.transcription_ms,
            classification_ms=req.classification_ms,
            profile_fetch_ms=req.profile_fetch_ms,
            total_pipeline_ms=total_pipeline_ms,
        )
    except ProviderError as exc:
        generation_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.warning(
            "Answer generation failed generation_ms=%s transcription_ms=%s classification_ms=%s profile_fetch_ms=%s question_len=%s error=%s",
            generation_ms,
            req.transcription_ms,
            req.classification_ms,
            req.profile_fetch_ms,
            len(req.question.strip()),
            exc,
        )
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
