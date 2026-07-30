import logging
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.nlp.answer_generator import ProviderError
from app.services.resume_index_service import ResumeIndexError, ResumeIndexService
from app.services.resume_parser_service import ResumeParserService
from app.services.resume_service import ResumeExtractionError

router = APIRouter()
logger = logging.getLogger("resume_api")
logging.basicConfig(level=logging.INFO)

resume_parser_service = ResumeParserService()
resume_index_service = ResumeIndexService()


class ResumeProfileResponse(BaseModel):
    full_name: str
    email: str
    phone: str
    location: str
    current_title: str
    target_role: str
    professional_summary: str
    education: str
    degree: str
    branch: str = ""
    branch_specialization: str
    college: str = ""
    college_university: str
    university: str = ""
    graduation_year: str
    top_skills: str
    technical_skills: str
    soft_skills: str = ""
    tools_frameworks: str
    projects: str
    experience: str
    work_experience: str
    leadership_activities: str = ""
    achievements: str
    certifications: str
    live_profile_summary: str = ""
    resume: str
    role: str
    company: str
    skills: str
    raw_resume_text: str
    manual_review_required: bool
    manual_review_message: str
    extraction_confidence: str


class ResumeExtractResponse(ResumeProfileResponse):
    parser_provider: str
    fallback_used: bool
    fallback_message: str = ""
    warning: str | None = None
    missing_fields: list[str]
    review_required: bool
    profile: ResumeProfileResponse
    extracted_text_length: int


class ResumeIndexRequest(BaseModel):
    profile: Optional[dict[str, Any]] = None


class ResumeIndexStatusResponse(BaseModel):
    indexed: bool
    chunk_count: int
    updated_at: Optional[str] = None
    needs_rebuild: bool = False


@router.post("/extract", response_model=ResumeExtractResponse)
async def extract_resume(file: UploadFile = File(...)):
    try:
        content = await file.read()
        structured = resume_parser_service.extract_profile(filename=file.filename or "", content=content)
        response_payload = dict(structured)
        profile_payload = response_payload.pop("profile", {}) or {}

        if response_payload.get("fallback_used"):
            logger.warning(
                "Resume extraction fallback_used=true filename=%s provider=%s warning=%s",
                file.filename,
                response_payload.get("parser_provider"),
                response_payload.get("warning") or response_payload.get("fallback_message") or "",
            )
        logger.info(
            "Resume extracted successfully filename=%s provider=%s fallback=%s fields=%s",
            file.filename,
            response_payload.get("parser_provider"),
            response_payload.get("fallback_used"),
            sorted(key for key, value in profile_payload.items() if value),
        )
        return ResumeExtractResponse(
            **response_payload,
            profile=ResumeProfileResponse(**profile_payload),
        )
    except ResumeExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected resume extraction error for filename=%s", file.filename)
        raise HTTPException(
            status_code=500,
            detail="Resume extraction failed unexpectedly. Please try again.",
        ) from exc


@router.post("/index", response_model=ResumeIndexStatusResponse)
async def index_resume(req: ResumeIndexRequest):
    try:
        payload = resume_index_service.build_index(req.profile or {})
        logger.info(
            "Resume index built chunk_count=%s sections=%s",
            payload["chunk_count"],
            sorted({chunk["section"] for chunk in payload["chunks"]}),
        )
        return ResumeIndexStatusResponse(
            indexed=True,
            chunk_count=payload["chunk_count"],
            updated_at=payload["updated_at"],
            needs_rebuild=False,
        )
    except ResumeIndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected resume index build error")
        raise HTTPException(
            status_code=500,
            detail="Resume indexing failed unexpectedly. Please try again.",
        ) from exc


@router.get("/index/status", response_model=ResumeIndexStatusResponse)
async def resume_index_status():
    try:
        return ResumeIndexStatusResponse(**resume_index_service.get_status())
    except ResumeIndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/index", response_model=ResumeIndexStatusResponse)
async def delete_resume_index():
    try:
        return ResumeIndexStatusResponse(**resume_index_service.delete_index())
    except ResumeIndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
