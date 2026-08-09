import json
import logging
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.api import auth, auto_stt, classify, generate, job_context, job_contexts, question_detect, resume, resumes, system_audio, transcribe
from app.api.debug import router as debug_router
from app.api.screen_ocr import router as screen_ocr_router
from app.config import settings
from app.services.resume_index_service import ResumeIndexError, ResumeIndexService

app = FastAPI(title="SAIIA Backend")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
PROFILE_PATH = Path(__file__).parent.parent / "candidate_profile.json"
logger = logging.getLogger("profile_api")
_PROFILE_CACHE: dict | None = None
_PROFILE_CACHE_MTIME_NS: int | None = None
resume_index_service = ResumeIndexService()

origins = [
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transcribe.router, prefix="/transcribe", tags=["Transcribe"])
app.include_router(auto_stt.router, tags=["Auto STT"])
app.include_router(classify.router, prefix="/classify", tags=["Classify"])
app.include_router(generate.router, prefix="/generate", tags=["Generate"])
app.include_router(resume.router, prefix="/api/resume", tags=["Resume"])
app.include_router(resumes.router, prefix="/api/resumes", tags=["Cloud Resumes"])
app.include_router(job_contexts.router, prefix="/api/job-contexts", tags=["Cloud Job Contexts"])
app.include_router(system_audio.router, prefix="/api/audio/system", tags=["System Audio"])
app.include_router(job_context.router, prefix="/api/job-context", tags=["Job Context"])
app.include_router(question_detect.router, prefix="/api/question-detect", tags=["Question Detect"])
app.include_router(screen_ocr_router)
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
if settings.DEBUG:
    app.include_router(debug_router, prefix="/api/debug", tags=["Debug"])


PROFILE_ENCODING_FALLBACKS = ("utf-8", "cp1252", "latin-1")
CHARACTER_NORMALIZATION_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2022": "-",
        "\u25cf": "-",
        "\u25aa": "-",
        "\u00a0": " ",
    }
)


def _normalize_profile_text(value: str) -> str:
    normalized = value.translate(CHARACTER_NORMALIZATION_MAP)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized


def _write_profile_json(payload: dict) -> None:
    global _PROFILE_CACHE, _PROFILE_CACHE_MTIME_NS
    normalized_payload = _normalize_profile_payload(payload)
    PROFILE_PATH.write_text(
        json.dumps(normalized_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        _PROFILE_CACHE_MTIME_NS = PROFILE_PATH.stat().st_mtime_ns
    except OSError:
        _PROFILE_CACHE_MTIME_NS = None
    _PROFILE_CACHE = normalized_payload


def _normalize_profile_payload(value):
    if isinstance(value, dict):
        return {key: _normalize_profile_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_profile_payload(item) for item in value]
    if isinstance(value, str):
        return _normalize_profile_text(value)
    return value


def _build_live_profile_summary(payload: dict) -> str:
    projects = [line.strip() for line in str(payload.get("projects", "")).splitlines() if line.strip()]
    education = str(payload.get("education", "")).strip() or ", ".join(
        part
        for part in [
            str(payload.get("degree", "")).strip(),
            str(payload.get("branch", "") or payload.get("branch_specialization", "")).strip(),
            str(payload.get("college", "") or payload.get("college_university", "") or payload.get("university", "")).strip(),
            str(payload.get("graduation_year", "")).strip(),
        ]
        if part
    )
    summary = {
        "full_name": str(payload.get("full_name", "")).strip(),
        "target_role": str(payload.get("target_role", "") or payload.get("current_title", "") or payload.get("role", "")).strip(),
        "education": education,
        "top_skills": str(payload.get("top_skills", "")).strip(),
        "projects": "\n".join(projects[:2]),
        "company": str(payload.get("company", "")).strip(),
    }
    return json.dumps(summary, ensure_ascii=False)


def _load_profile_json() -> dict:
    global _PROFILE_CACHE, _PROFILE_CACHE_MTIME_NS
    if not PROFILE_PATH.exists():
        _PROFILE_CACHE = {}
        _PROFILE_CACHE_MTIME_NS = None
        return {}

    try:
        current_mtime_ns = PROFILE_PATH.stat().st_mtime_ns
        if _PROFILE_CACHE is not None and _PROFILE_CACHE_MTIME_NS == current_mtime_ns:
            return _PROFILE_CACHE
    except OSError:
        current_mtime_ns = None

    try:
        raw_bytes = PROFILE_PATH.read_bytes()
    except OSError:
        logger.exception("Could not read candidate profile file: %s", PROFILE_PATH)
        return {}

    decoded_text = None
    used_encoding = None

    for encoding in PROFILE_ENCODING_FALLBACKS:
        try:
            decoded_text = raw_bytes.decode(encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue

    if decoded_text is None:
        logger.error("Could not decode candidate profile file with supported encodings: %s", PROFILE_PATH)
        return {}

    try:
        payload = json.loads(decoded_text)
    except json.JSONDecodeError:
        logger.exception(
            "Candidate profile JSON is invalid after decoding with %s. Returning empty profile.",
            used_encoding,
        )
        try:
            _write_profile_json({})
        except OSError:
            logger.exception("Failed to reset invalid candidate profile file as UTF-8 JSON.")
        return {}

    if not isinstance(payload, dict):
        logger.error(
            "Candidate profile JSON root is not an object after decoding with %s. Returning empty profile.",
            used_encoding,
        )
        try:
            _write_profile_json({})
        except OSError:
            logger.exception("Failed to reset non-object candidate profile file as UTF-8 JSON.")
        return {}

    normalized_payload = _normalize_profile_payload(payload)
    if isinstance(normalized_payload, dict):
        branch_value = str(
            normalized_payload.get("branch", "") or normalized_payload.get("branch_specialization", "")
        ).strip()
        college_value = str(
            normalized_payload.get("college", "")
            or normalized_payload.get("college_university", "")
            or normalized_payload.get("university", "")
        ).strip()
        if branch_value:
            normalized_payload["branch"] = branch_value
            if not str(normalized_payload.get("branch_specialization", "")).strip():
                normalized_payload["branch_specialization"] = branch_value
        if college_value:
            normalized_payload["college"] = college_value
            if not str(normalized_payload.get("college_university", "")).strip():
                normalized_payload["college_university"] = college_value
            if not str(normalized_payload.get("university", "")).strip():
                normalized_payload["university"] = college_value
        if "soft_skills" not in normalized_payload:
            normalized_payload["soft_skills"] = ""
        if "leadership_activities" not in normalized_payload:
            normalized_payload["leadership_activities"] = ""
        normalized_payload["live_profile_summary"] = _build_live_profile_summary(normalized_payload)

    needs_rewrite = used_encoding != "utf-8" or normalized_payload != payload
    if needs_rewrite:
        logger.warning(
            "Recovered candidate profile using %s decode fallback or character normalization. Rewriting as UTF-8.",
            used_encoding,
        )
        try:
            _write_profile_json(normalized_payload)
        except OSError:
            logger.exception("Failed to rewrite recovered candidate profile as UTF-8.")

    _PROFILE_CACHE = normalized_payload
    _PROFILE_CACHE_MTIME_NS = current_mtime_ns
    return normalized_payload


@app.get("/profile-setup", response_class=HTMLResponse)
async def profile_form(request: Request):
    return templates.TemplateResponse("profile_setup.html", {"request": request})


@app.post("/api/profile", response_class=HTMLResponse)
async def save_profile(
    resume: str = Form(...),
    raw_resume_text: str = Form(""),
    full_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    location: str = Form(""),
    current_title: str = Form(""),
    target_role: str = Form(""),
    professional_summary: str = Form(""),
    role: str = Form(...),
    company: str = Form(...),
    top_skills: str = Form(""),
    technical_skills: str = Form(""),
    soft_skills: str = Form(""),
    tools_frameworks: str = Form(""),
    skills: str = Form(...),
    projects: str = Form(""),
    experience: str = Form(...),
    education: str = Form(""),
    degree: str = Form(""),
    branch_specialization: str = Form(""),
    college_university: str = Form(""),
    university: str = Form(""),
    graduation_year: str = Form(""),
    work_experience: str = Form(""),
    leadership_activities: str = Form(""),
    achievements: str = Form(""),
    certifications: str = Form(""),
):
    normalized_role = current_title.strip() or target_role.strip() or role.strip()
    normalized_summary = professional_summary.strip() or resume.strip()
    normalized_top_skills = top_skills.strip() or skills.strip()
    normalized_work_experience = work_experience.strip()

    fields = {
        "resume": normalized_summary,
        "raw_resume_text": raw_resume_text.strip(),
        "full_name": full_name.strip(),
        "email": email.strip(),
        "phone": phone.strip(),
        "location": location.strip(),
        "current_title": current_title.strip() or normalized_role,
        "target_role": target_role.strip() or normalized_role,
        "professional_summary": normalized_summary,
        "role": normalized_role,
        "company": company.strip(),
        "top_skills": normalized_top_skills,
        "technical_skills": technical_skills.strip(),
        "soft_skills": soft_skills.strip(),
        "tools_frameworks": tools_frameworks.strip(),
        "skills": normalized_top_skills,
        "projects": projects.strip(),
        "experience": experience.strip(),
        "education": education.strip(),
        "degree": degree.strip(),
        "branch": branch_specialization.strip(),
        "branch_specialization": branch_specialization.strip(),
        "college": college_university.strip() or university.strip(),
        "college_university": college_university.strip() or university.strip(),
        "university": university.strip() or college_university.strip(),
        "graduation_year": graduation_year.strip(),
        "work_experience": normalized_work_experience,
        "leadership_activities": leadership_activities.strip(),
        "achievements": achievements.strip(),
        "certifications": certifications.strip(),
    }
    fields["live_profile_summary"] = _build_live_profile_summary(fields)

    required_fields = {
        "resume": fields["resume"],
        "role": fields["role"],
        "company": fields["company"],
        "skills": fields["skills"],
        "experience": fields["experience"],
    }
    if not all(required_fields.values()):
        raise HTTPException(
            status_code=400,
            detail="Please complete your profile before generating interview answers.",
        )

    _write_profile_json(fields)
    try:
        resume_index_service.build_index(fields)
    except ResumeIndexError:
        logger.exception("Profile saved but resume index could not be activated.")
    except Exception:
        logger.exception("Unexpected error while activating resume index after profile save.")
    return HTMLResponse(
        "<!DOCTYPE html><html><body>"
        "<p>Saved! This window will close...</p>"
        "<script>"
        "try { localStorage.setItem('saiiaProfileUpdatedAt', String(Date.now())); } catch (error) {}"
        "setTimeout(()=>window.close(),800);"
        "</script>"
        "</body></html>"
    )


@app.get("/api/profile", response_class=JSONResponse)
async def get_profile():
    return JSONResponse(content=_load_profile_json())
