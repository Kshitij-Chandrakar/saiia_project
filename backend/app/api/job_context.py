import logging
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.nlp.answer_generator import ProviderError
from app.services.job_context_service import JobContextError, JobContextService

router = APIRouter()
logger = logging.getLogger("job_context_api")
logging.basicConfig(level=logging.INFO)

job_context_service = JobContextService()


class JobContextPayload(BaseModel):
    target_role: str = ""
    company_name: str = ""
    job_description: str = ""
    required_skills: str = ""
    responsibilities: str = ""
    preferred_qualifications: str = ""
    company_notes: str = ""


class JobContextResponse(JobContextPayload):
    updated_at: Optional[str] = None
    saved: bool = False


class JobContextExtractResponse(JobContextPayload):
    extracted_text_length: int


@router.get("", response_model=JobContextResponse)
async def get_job_context():
    try:
        return JobContextResponse(**job_context_service.get_context())
    except JobContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=JobContextResponse)
async def save_job_context(payload: JobContextPayload):
    try:
        saved = job_context_service.save_context(payload.model_dump())
        logger.info(
            "Job context saved fields=%s",
            sorted(key for key, value in saved.items() if key not in {"saved", "updated_at"} and value),
        )
        return JobContextResponse(**saved)
    except JobContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected job context save error")
        raise HTTPException(
            status_code=500,
            detail="Job context save failed unexpectedly. Please try again.",
        ) from exc


@router.delete("", response_model=JobContextResponse)
async def delete_job_context():
    try:
        return JobContextResponse(**job_context_service.delete_context())
    except JobContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/extract", response_model=JobContextExtractResponse)
async def extract_job_context(file: UploadFile = File(...)):
    try:
        content = await file.read()
        raw_text = job_context_service.extract_text(filename=file.filename or "", content=content)
        structured = job_context_service.build_context_fields(raw_text)
        logger.info(
            "Job context extracted filename=%s text_length=%s fields=%s",
            file.filename,
            len(raw_text),
            sorted(key for key, value in structured.items() if value),
        )
        return JobContextExtractResponse(
            **structured,
            extracted_text_length=len(raw_text),
        )
    except JobContextError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected job context extraction error for filename=%s", file.filename)
        raise HTTPException(
            status_code=500,
            detail="Job context extraction failed unexpectedly. Please try again.",
        ) from exc
