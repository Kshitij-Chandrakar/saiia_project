import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from fastapi import APIRouter, File, UploadFile

from app.config import settings
from app.nlp.answer_generator import NvidiaProvider
from app.services.affinda_resume_parser import AffindaResumeParser, AffindaResumeParserError
from app.services.resume_service import ResumeService

router = APIRouter()
logger = logging.getLogger("debug_api")
affinda_parser = AffindaResumeParser(ResumeService())


@router.get("/nvidia-test")
async def nvidia_test():
    provider = NvidiaProvider()
    timeout_seconds = min(settings.NVIDIA_TIMEOUT_SECONDS, 20)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(provider.connectivity_test, timeout=timeout_seconds)
        try:
            result = future.result(timeout=timeout_seconds + 2)
        except FutureTimeoutError:
            result = {
                "success": False,
                "status_code": None,
                "response_preview": None,
                "error": "NVIDIA connectivity test timed out",
            }

    payload = {
        "temporary": True,
        "success": result["success"],
        "key_loaded": bool(settings.NVIDIA_API_KEY),
        "key_prefix": settings.NVIDIA_API_KEY[:6] if settings.NVIDIA_API_KEY else "",
        "key_length": len(settings.NVIDIA_API_KEY),
        "base_url": settings.NVIDIA_BASE_URL,
        "model": settings.NVIDIA_MODEL,
        "status_code": result["status_code"],
        "error": result["error"],
        "response_preview": result["response_preview"],
    }

    logger.info(
        "nvidia_test success=%s key_loaded=%s key_prefix=%s key_length=%s base_url=%s model=%s status_code=%s error=%s",
        payload["success"],
        payload["key_loaded"],
        payload["key_prefix"],
        payload["key_length"],
        payload["base_url"],
        payload["model"],
        payload["status_code"],
        payload["error"],
    )
    return payload


@router.get("/affinda/document-types")
async def affinda_document_types():
    try:
        payload = affinda_parser.list_document_types()
        logger.info(
            "affinda_document_types workspace=%s configured_document_type=%s found=%s count=%s",
            payload["workspace"],
            payload["configured_document_type"],
            payload["configured_document_type_found"],
            len(payload["document_types"]),
        )
        return payload
    except AffindaResumeParserError as exc:
        logger.warning("affinda_document_types failed error=%s", exc)
        return {
            "workspace": settings.AFFINDA_WORKSPACE,
            "configured_document_type": settings.AFFINDA_DOCUMENT_TYPE,
            "document_types": [],
            "configured_document_type_found": False,
            "error": str(exc),
        }


@router.post("/affinda/upload")
async def affinda_upload(file: UploadFile = File(...)):
    content = await file.read()
    try:
        payload = affinda_parser.build_debug_upload_payload(
            filename=file.filename or "resume",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
        logger.info(
            "affinda_upload_debug filename=%s ok=%s status_code=%s doc_id=%s top_level_keys=%s data_keys=%s",
            file.filename,
            payload["ok"],
            payload["status_code"],
            payload["affinda_document_identifier"],
            payload["top_level_keys"],
            payload["data_keys"],
        )
        return payload
    except AffindaResumeParserError as exc:
        logger.warning("affinda_upload_debug failed filename=%s error=%s", file.filename, exc)
        return {
            "ok": False,
            "status_code": 500,
            "affinda_document_identifier": None,
            "top_level_keys": [],
            "data_keys": [],
            "meta_keys": [],
            "error": str(exc),
            "warnings": [],
            "raw_shape_sample": {},
            "mapped_profile_preview": {},
        }
