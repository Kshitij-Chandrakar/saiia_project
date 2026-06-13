# from fastapi import FastAPI
from fastapi import FastAPI, Request, Form, HTTPException

from fastapi.middleware.cors import CORSMiddleware

from app.api import transcribe, classify, generate


from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import json
from pathlib import Path

app = FastAPI(title="SAIIA Backend")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
PROFILE_PATH = Path(__file__).parent.parent / "candidate_profile.json"

app = FastAPI(title="SAIIA Backend")

# ─── CORS CONFIG ───────────────────────────────────────────────────────────────
origins = [
    "http://localhost:5173",  # your Vite dev server
    # add other origins here (e.g. production URLs) as needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ────────────────────────────────────────────────────────────────────────────────

# Mount the three API routers
app.include_router(transcribe.router, prefix="/transcribe", tags=["Transcribe"])
app.include_router(classify.router,   prefix="/classify",   tags=["Classify"])
app.include_router(generate.router,   prefix="/generate",   tags=["Generate"])

# ─── Candidate Profile Setup ─────────────────────────────────────────────
@app.get("/profile-setup", response_class=HTMLResponse)
async def profile_form(request: Request):
    return templates.TemplateResponse("profile_setup.html", {"request": request})

@app.post("/api/profile", response_class=HTMLResponse)
async def save_profile(
    resume: str = Form(...),
    role:   str = Form(...),
    company:str = Form(...),
    skills: str = Form(...),
    experience: str = Form(...),
):
    fields = {
        "resume": resume.strip(),
        "role": role.strip(),
        "company": company.strip(),
        "skills": skills.strip(),
        "experience": experience.strip(),
    }
    if not all(fields.values()):
        raise HTTPException(
            status_code=400,
            detail="Please complete your profile before generating interview answers.",
        )

    data = fields
    PROFILE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    # Auto-close browser window after saving
    return HTMLResponse(
        "<!DOCTYPE html><html><body>"
        "<p>Saved! This window will close…</p>"
        "<script>setTimeout(()=>window.close(),800);</script>"
        "</body></html>"
    )

@app.get("/api/profile", response_class=JSONResponse)
async def get_profile():
    if PROFILE_PATH.exists():
        return JSONResponse(content=json.loads(PROFILE_PATH.read_text()))
    return JSONResponse(content={})
# ───────────────────────────────────────────────────────────────────────────────
