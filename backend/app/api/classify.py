import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.nlp.classifier import QuestionClassifier

router = APIRouter()
logger = logging.getLogger("classify_api")
logging.basicConfig(level=logging.INFO)

classifier = QuestionClassifier()


class ClassifyRequest(BaseModel):
    text: str


class ClassifyResponse(BaseModel):
    category: str
    classification_ms: float


@router.post("/", response_model=ClassifyResponse)
async def classify_text(req: ClassifyRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="`text` field cannot be empty.")

    started = time.perf_counter()

    try:
        category = classifier.classify_question(req.text)
        classification_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "Classification completed category=%s classification_ms=%s text_len=%s",
            category,
            classification_ms,
            len(req.text.strip()),
        )
        return ClassifyResponse(category=category, classification_ms=classification_ms)
    except Exception as exc:
        logger.exception("Classification error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Internal error during classification.",
        ) from exc
