from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests import RequestException, Timeout

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH, override=True)

AFFINDA_API_BASE_URL = os.getenv("AFFINDA_API_BASE_URL", "https://api.affinda.com").rstrip("/")
AFFINDA_API_KEY = os.getenv("AFFINDA_API_KEY", "").strip()
AFFINDA_WORKSPACE = os.getenv("AFFINDA_WORKSPACE", "").strip()
AFFINDA_DOCUMENT_TYPE = os.getenv("AFFINDA_DOCUMENT_TYPE", "").strip()
AFFINDA_COLLECTION = os.getenv("AFFINDA_COLLECTION", "").strip()

if not AFFINDA_DOCUMENT_TYPE and AFFINDA_COLLECTION:
    AFFINDA_DOCUMENT_TYPE = AFFINDA_COLLECTION


def guess_content_type(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
    }.get(suffix, "application/octet-stream")


def normalize_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        items: list[Any] = []
        for item in value:
            items.extend(normalize_list(item))
        return items
    return [value]


def get_path(obj: Any, path: list[str], default: Any = None) -> Any:
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def find_key_recursive(obj: Any, possible_names: set[str]) -> Any:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in possible_names:
                return value
        for value in obj.values():
            found = find_key_recursive(value, possible_names)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_key_recursive(item, possible_names)
            if found not in (None, "", [], {}):
                return found
    return None


NON_SKILL_LABELS = {
    "github",
    "linkedin",
    "leetcode",
    "portfolio",
    "website",
}

PREFERRED_TOP_SKILLS = (
    "python",
    "machine learning",
    "deep learning",
    "generative ai",
    "nlp",
    "fastapi",
    "streamlit",
    "langchain",
)


def validate_affinda_config() -> list[str]:
    errors: list[str] = []
    if not AFFINDA_API_BASE_URL:
        errors.append("Missing AFFINDA_API_BASE_URL")
    if not AFFINDA_API_KEY:
        errors.append("Missing AFFINDA_API_KEY")
    if not AFFINDA_WORKSPACE:
        errors.append("Missing AFFINDA_WORKSPACE")
    if not AFFINDA_DOCUMENT_TYPE:
        errors.append("Missing AFFINDA_DOCUMENT_TYPE")
    return errors


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {AFFINDA_API_KEY}"}


def safe_json(response: requests.Response) -> dict[str, Any]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Response is not a JSON object")
    return payload


def safe_json_any(response: requests.Response) -> Any:
    return response.json()


def fetch_document_types() -> Any:
    url = f"{AFFINDA_API_BASE_URL}/v3/document_types"
    params = {"workspace": AFFINDA_WORKSPACE}
    print(f"DOCUMENT_TYPES_URL={url}")
    response = requests.get(
        url,
        headers=auth_headers(),
        params=params,
        timeout=60,
    )
    response.raise_for_status()
    print(f"DOCUMENT_TYPES_STATUS_CODE={response.status_code}")
    return safe_json_any(response)


def fetch_document_type_detail() -> dict[str, Any]:
    url = f"{AFFINDA_API_BASE_URL}/v3/document_types/{AFFINDA_DOCUMENT_TYPE}"
    print(f"DOCUMENT_TYPE_DETAIL_URL={url}")
    response = requests.get(
        url,
        headers=auth_headers(),
        timeout=60,
    )
    response.raise_for_status()
    print(f"DOCUMENT_TYPE_DETAIL_STATUS_CODE={response.status_code}")
    return safe_json(response)


def parse_document_types(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_items: list[Any] = []
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload.get("results"), list):
        raw_items = payload["results"]
    elif isinstance(payload.get("data"), list):
        raw_items = payload["data"]
    elif isinstance(payload.get("documentTypes"), list):
        raw_items = payload["documentTypes"]

    document_types: list[dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        identifier = str(
            item.get("identifier")
            or item.get("slug")
            or item.get("id")
            or item.get("name")
            or ""
        ).strip()
        name = str(item.get("name") or item.get("displayName") or identifier).strip()
        if not identifier:
            continue
        document_types.append({"identifier": identifier, "name": name})
    return document_types


def extract_data(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(get_path(payload, ["document", "data"]), dict):
        return get_path(payload, ["document", "data"], {})
    if isinstance(payload.get("result"), dict):
        return payload["result"]
    if isinstance(payload.get("document"), dict):
        return payload["document"]
    return payload if isinstance(payload, dict) else {}


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def list_value(value: Any) -> list[str]:
    rendered: list[str] = []
    for item in normalize_list(value):
        if isinstance(item, dict):
            text = " - ".join(
                part
                for part in [
                    first_non_empty(
                        item.get("name"),
                        item.get("title"),
                        item.get("organization"),
                        item.get("issuer"),
                        item.get("jobTitle"),
                    ),
                    first_non_empty(
                        item.get("description"),
                        item.get("summary"),
                        item.get("details"),
                    ),
                ]
                if part
            )
        else:
            text = str(item or "").strip()
        if text:
            rendered.append(text)
    return rendered


def extract_candidate_name(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            name = extract_candidate_name(item)
            if name:
                return name
        return ""
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in NON_SKILL_LABELS:
            return ""
        return text.title() if text.isupper() else text
    if not isinstance(value, dict):
        return ""
    for key in ("raw", "parsed", "value", "text"):
        text = str(value.get(key, "")).strip()
        if text and text.lower() not in NON_SKILL_LABELS:
            return text.title() if text.isupper() else text
    parts = [
        value.get("candidateNameFirst"),
        value.get("candidateNameMiddle"),
        value.get("candidateNameFamily"),
        value.get("firstName"),
        value.get("middleName"),
        value.get("lastName"),
        value.get("familyName"),
    ]
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def extract_email(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            email = extract_email(item)
            if email:
                return email
        return ""
    if isinstance(value, dict):
        return first_non_empty(
            value.get("raw"),
            value.get("parsed"),
            value.get("value"),
            value.get("text"),
            value.get("email"),
            value.get("emailAddress"),
        )
    return ""


def extract_phone(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            phone = extract_phone(item)
            if phone:
                return phone
        return ""
    if isinstance(value, dict):
        return first_non_empty(
            value.get("formattedNumber"),
            value.get("phoneNumber"),
            value.get("number"),
            value.get("raw"),
            value.get("parsed"),
            value.get("value"),
            value.get("text"),
            value.get("rawText"),
        )
    return ""


def extract_location(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    return first_non_empty(
        value.get("formatted"),
        value.get("rawInput"),
        ", ".join(
            part
            for part in [
                str(value.get("city", "")).strip(),
                str(value.get("state", "")).strip(),
                str(value.get("country", "")).strip(),
            ]
            if part
        ),
    )


def extract_degree(education: Any) -> str:
    if not isinstance(education, dict):
        return ""
    parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
    accreditation = education.get("accreditation") or parsed.get("educationAccreditation")
    if isinstance(accreditation, dict):
        return first_non_empty(
            accreditation.get("education"),
            accreditation.get("inputStr"),
            accreditation.get("matchStr"),
            accreditation.get("raw"),
            accreditation.get("parsed"),
        )
    degree = first_non_empty(education.get("degree"), education.get("qualification"), parsed.get("educationAccreditation"))
    return clean_education_text(degree)


def extract_branch(education: Any) -> str:
    if not isinstance(education, dict):
        return ""
    parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
    major = parsed.get("educationMajor")
    if isinstance(major, list):
        major_parts = [extract_text_node(item) for item in major]
        major_parts = [part for part in major_parts if part]
        major_text = " and ".join(major_parts) if len(major_parts) == 2 else ", ".join(major_parts)
        if major_text:
            return clean_education_text(major_text)
    majors = list_value(education.get("majors") or education.get("specializations"))
    if majors:
        return clean_education_text(majors[0])
    if isinstance(major, dict):
        return clean_education_text(first_non_empty(major.get("raw"), major.get("parsed")))
    if isinstance(major, str):
        return clean_education_text(major.strip())
    return clean_education_text(first_non_empty(education.get("fieldOfStudy"), education.get("specialization")))


def extract_college(education: Any) -> str:
    if not isinstance(education, dict):
        return ""
    parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
    organization = parsed.get("educationOrganization")
    if isinstance(organization, dict):
        return normalize_university_name(first_non_empty(organization.get("raw"), organization.get("parsed")))
    return normalize_university_name(first_non_empty(education.get("organization"), education.get("institution"), organization))


def extract_university(education: Any) -> str:
    if not isinstance(education, dict):
        return ""
    return normalize_university_name(first_non_empty(education.get("organization"), education.get("institution"), education.get("school")))


def extract_graduation_year(education: Any) -> str:
    if not isinstance(education, dict):
        return ""
    parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
    dates = education.get("dates") or parsed.get("educationDates")
    values: list[Any] = []
    if isinstance(dates, dict):
        values.extend([
            dates.get("completionDate"),
            dates.get("endDate"),
            dates.get("rawText"),
            dates.get("raw"),
            dates.get("parsed"),
        ])
    values.extend([education.get("graduationDate"), education.get("endDate"), education.get("date")])
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        if "present" in text.lower():
            return "Present"
        for token in text.split():
            if token.isdigit() and len(token) == 4 and token.startswith(("19", "20")):
                return token
    return ""


def extract_summary(data: dict[str, Any]) -> str:
    return first_non_empty(data.get("summary"), data.get("objective"))


def build_education_summary(entries: list[Any]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for education in entries[:3]:
        if not isinstance(education, dict):
            continue
        degree = extract_degree(education)
        branch = extract_branch(education)
        university = extract_college(education) or extract_university(education)
        graduation_year = extract_graduation_year(education)
        if degree and branch and university:
            line = f"{degree} in {branch}, {university}"
        elif degree and university:
            line = f"{degree}, {university}"
        else:
            line = ", ".join(part for part in [degree, branch, university, graduation_year] if part)
        line = clean_education_text(line)
        if line and line.lower() not in seen:
            seen.add(line.lower())
            lines.append(line)
    return "\n".join(lines)


def select_education_entries(entries: list[Any]) -> list[Any]:
    preferred: list[Any] = []
    fallback: list[Any] = []
    for education in entries:
        if not isinstance(education, dict):
            continue
        raw = str(education.get("raw", "")).strip().lower()
        parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
        level = str(get_path(parsed, ["educationLevel", "raw"], "")).strip().lower()
        organization = extract_college(education)
        degree = extract_degree(education)
        branch = extract_branch(education)
        if any(token in raw for token in ("certificate", "finalist", "hackathon")) or "course/certificate" in level:
            fallback.append(education)
            continue
        if any(token in raw for token in ("bachelor", "master", "university", "college")) or organization or ("major" in raw):
            preferred.append(education)
        elif degree or branch:
            preferred.append(education)
        else:
            fallback.append(education)
    return preferred or fallback


def clean_education_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = [part.strip() for part in text.replace("•", " ").split(" - ") if part.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(part)
    return " - ".join(deduped).strip(" ,;-")


def normalize_university_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.title() if text.isupper() else text
    normalized = normalized.replace("O.P Jindal University", "O.P. Jindal University")
    normalized = normalized.replace("O.P JINDAL UNIVERSITY", "O.P. Jindal University")
    return normalized


def build_work_entry(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
    parts = [
        first_non_empty(
            extract_text_node(parsed.get("workExperienceJobTitle")),
            item.get("jobTitle"),
            item.get("title"),
            item.get("occupation"),
        ),
        first_non_empty(
            extract_text_node(parsed.get("workExperienceOrganization")),
            item.get("organization"),
            item.get("company"),
            item.get("employer"),
        ),
        extract_date_range(item),
        first_non_empty(
            extract_text_node(parsed.get("workExperienceDescription")),
            item.get("summary"),
            item.get("jobDescription"),
            item.get("description"),
        ),
    ]
    return " - ".join(part for part in parts if part)


def build_work_entries(entries: list[Any]) -> str:
    lines: list[str] = []
    for item in entries:
        if not is_real_work_experience(item):
            continue
        line = build_work_entry(item)
        if line:
            lines.append(line)
    return "\n".join(lines[:5])


def is_real_work_experience(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
    organization = extract_text_node(parsed.get("workExperienceOrganization"))
    title = extract_text_node(parsed.get("workExperienceJobTitle"))
    raw = str(item.get("raw", "")).strip().lower()
    if "github" in raw:
        return False
    if organization and title:
        return True
    return any(token in title.lower() for token in ("intern", "engineer", "developer", "analyst"))


def extract_date_range(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
    dates = item.get("dates") or parsed.get("workExperienceDates")
    if isinstance(dates, dict):
        start = first_non_empty(
            dates.get("startDate"),
            extract_nested_date(dates.get("start")),
            dates.get("rawText"),
            dates.get("raw"),
        )
        end = first_non_empty(dates.get("endDate"), extract_nested_date(dates.get("end")))
        if start and end:
            return f"{start} to {end}"
        return start or end
    return first_non_empty(item.get("startDate"), item.get("endDate"))


def build_project_entry(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
    parts = [
        first_non_empty(
            extract_text_node(parsed.get("projectTitle")),
            item.get("name"),
            item.get("title"),
            item.get("project"),
        ),
        first_non_empty(
            extract_text_node(parsed.get("projectDescription")),
            item.get("description"),
            item.get("summary"),
            item.get("details"),
        ),
        stringify_technologies(item.get("technologies")),
    ]
    return " - ".join(part for part in parts if part)


def build_project_entries(entries: list[Any]) -> str:
    lines: list[str] = []
    for item in entries:
        line = build_project_entry(item)
        if line:
            lines.append(line)
    return "\n".join(lines[:8])


def stringify_technologies(value: Any) -> str:
    parts: list[str] = []
    for item in normalize_list(value):
        if isinstance(item, dict):
            text = first_non_empty(item.get("name"), item.get("raw"), item.get("text"))
        else:
            text = str(item or "").strip()
        if text:
            parts.append(text)
    return ", ".join(parts)


def build_simple_entries(value: Any) -> str:
    lines: list[str] = []
    for item in normalize_list(value):
        if isinstance(item, dict):
            text = " - ".join(
                part
                for part in [
                    first_non_empty(item.get("name"), item.get("title"), item.get("organization"), item.get("issuer")),
                    first_non_empty(item.get("description"), item.get("summary"), item.get("details")),
                ]
                if part
            )
        else:
            text = str(item or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines[:5])


def extract_skill_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return first_non_empty(
            value.get("name"),
            value.get("raw"),
            value.get("parsed"),
            value.get("value"),
            value.get("text"),
            value.get("skill"),
        )
    return ""


def collect_skills(value: Any, *, limit: int) -> list[str]:
    skills: list[str] = []
    seen: set[str] = set()
    for item in normalize_list(value):
        text = extract_skill_text(item)
        if not text:
            continue
        for fragment in [part.strip() for part in text.replace("|", ",").split(",") if part.strip()]:
            key = fragment.lower()
            normalized_key = key.lstrip("🔗")
            if key in seen or normalized_key in NON_SKILL_LABELS:
                continue
            seen.add(key)
            skills.append(fragment)
    ranked = sorted(
        skills,
        key=lambda skill: (
            PREFERRED_TOP_SKILLS.index(skill.lower().lstrip("🔗"))
            if skill.lower().lstrip("🔗") in PREFERRED_TOP_SKILLS
            else len(PREFERRED_TOP_SKILLS),
            skills.index(skill),
        ),
    )
    return ranked[:limit]


def extract_text_node(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return first_non_empty(value.get("raw"), value.get("parsed"), value.get("text"))
    return ""


def extract_nested_date(value: Any) -> str:
    if isinstance(value, dict):
        return first_non_empty(value.get("date"), value.get("rawText"), value.get("raw"))
    return str(value or "").strip()


def map_profile_preview(data: dict[str, Any]) -> dict[str, Any]:
    education_entries = normalize_list(data.get("education"))
    selected_education_entries = select_education_entries(education_entries)
    education_entry = selected_education_entries[0] if selected_education_entries else {}
    work_entries = normalize_list(data.get("workExperience"))
    project_entries = normalize_list(data.get("project"))
    top_skills = collect_skills(data.get("skill"), limit=8)

    preview = {
        "full_name": extract_candidate_name(data.get("candidateName")),
        "email": extract_email(data.get("email")),
        "phone": extract_phone(data.get("phoneNumber")),
        "location": extract_location(data.get("location")),
        "summary": extract_summary(data),
        "education": build_education_summary(selected_education_entries),
        "degree": extract_degree(education_entry),
        "branch": extract_branch(education_entry),
        "college": extract_college(education_entry),
        "university": extract_university(education_entry) or extract_college(education_entry),
        "graduation_year": extract_graduation_year(education_entry),
        "top_skills": top_skills,
        "technical_skills": collect_skills(data.get("skill"), limit=20),
        "work_experience": build_work_entries(work_entries),
        "projects": build_project_entries(project_entries),
        "achievements": build_simple_entries(data.get("achievement")),
        "certifications": build_simple_entries(data.get("certification") or data.get("certifications")),
        "raw_resume_text": first_non_empty(data.get("rawText")),
    }
    return {key: value for key, value in preview.items() if str(value or "").strip()}


def main() -> int:
    print(f"LOADED_ENV_PATH={ENV_PATH}")
    print(f"AFFINDA_API_BASE_URL={AFFINDA_API_BASE_URL}")
    print(f"AFFINDA_API_KEY_PRESENT={'yes' if AFFINDA_API_KEY else 'no'}")
    print(f"LOADED_AFFINDA_WORKSPACE={AFFINDA_WORKSPACE}")
    print(f"LOADED_AFFINDA_DOCUMENT_TYPE={AFFINDA_DOCUMENT_TYPE}")
    print(f"LOADED_AFFINDA_COLLECTION={AFFINDA_COLLECTION}")

    if len(sys.argv) < 2:
        print('Usage: python backend\\scripts\\test_affinda_upload.py "resume.pdf"')
        return 1

    errors = validate_affinda_config()
    if errors:
        print("Affinda config errors:")
        for error in errors:
            print(f"- {error}")
        return 1

    resume_path = Path(sys.argv[1])
    if not resume_path.exists():
        print(f"Resume file not found: {resume_path}")
        return 1

    try:
        document_types_payload = fetch_document_types()
        document_types = parse_document_types(document_types_payload)
    except Timeout:
        print("Document type lookup failed: request timeout")
        return 1
    except RequestException as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        response_text = response.text if response is not None else ""
        print(f"Document type lookup failed: status_code={status_code} error={exc.__class__.__name__}")
        print(f"REQUEST_URL={AFFINDA_API_BASE_URL}/v3/document_types")
        print(f"REQUEST_PARAMS={{'workspace': '{AFFINDA_WORKSPACE}'}}")
        print(f"RESPONSE_BODY={response_text}")
        return 1
    except Exception as exc:
        print(f"Document type lookup failed: {exc}")
        return 1

    try:
        detail_payload = fetch_document_type_detail()
        detail_status_code = 200
    except Timeout:
        print("Document type detail lookup failed: request timeout")
        return 1
    except RequestException as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        response_text = response.text if response is not None else ""
        print(f"Document type detail lookup failed: status_code={status_code} error={exc.__class__.__name__}")
        print(f"REQUEST_URL={AFFINDA_API_BASE_URL}/v3/document_types/{AFFINDA_DOCUMENT_TYPE}")
        print("REQUEST_PARAMS={}")
        print(f"RESPONSE_BODY={response_text}")
        return 1
    except Exception as exc:
        print(f"Document type detail lookup failed: {exc}")
        return 1

    print("Available document types:")
    for item in document_types:
        print(f"- {item['identifier']} :: {item['name']}")

    configured_document_type_found = any(
        item["identifier"] == AFFINDA_DOCUMENT_TYPE for item in document_types
    )
    print("Document type detail status_code: 200")
    print(f"Document type detail keys: {sorted(detail_payload.keys()) if isinstance(detail_payload, dict) else []}")
    print(f"Configured document type exists: {configured_document_type_found}")
    if not configured_document_type_found:
        print("Configured document type was not found in Affinda. Stop here and fix the env value.")
        return 1

    content = resume_path.read_bytes()
    try:
        upload_url = f"{AFFINDA_API_BASE_URL}/v3/documents"
        upload_form = {
            "workspace": AFFINDA_WORKSPACE,
            "documentType": AFFINDA_DOCUMENT_TYPE,
            "wait": "true",
            "compact": "false",
        }
        print(f"UPLOAD_URL={upload_url}")
        response = requests.post(
            upload_url,
            headers=auth_headers(),
            data=upload_form,
            files={
                "file": (
                    resume_path.name,
                    content,
                    guess_content_type(resume_path.name),
                )
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = safe_json(response)
    except Timeout:
        print("Affinda upload failed: request timeout")
        return 1
    except RequestException as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        response_text = response.text if response is not None else ""
        print(f"Affinda upload failed: status_code={status_code} error={exc.__class__.__name__}")
        print(f"UPLOAD_URL={upload_url}")
        print(f"UPLOAD_FORM_FIELDS={upload_form}")
        print(f"RESPONSE_BODY={response_text}")
        return 1
    except Exception as exc:
        print(f"Affinda upload failed: {exc}")
        return 1

    data = extract_data(payload)
    mapped_profile_preview = map_profile_preview(data if isinstance(data, dict) else {})
    education_entries = normalize_list(data.get("education")) if isinstance(data, dict) else []
    first_education_item = education_entries[0] if education_entries else {}
    sanitized_payload = {
        "ok": True,
        "status_code": response.status_code,
        "affinda_document_identifier": str(
            payload.get("identifier")
            or payload.get("id")
            or get_path(payload, ["document", "identifier"], "")
            or get_path(payload, ["document", "id"], "")
            or ""
        ).strip(),
        "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "data_keys": sorted(data.keys()) if isinstance(data, dict) else [],
        "mapped_profile_preview": mapped_profile_preview,
    }

    print(f"Upload ok: {sanitized_payload['ok']}")
    print(f"Upload status_code: {sanitized_payload['status_code']}")
    print(f"Affinda document identifier: {sanitized_payload['affinda_document_identifier']}")
    print(f"Top-level response keys: {sanitized_payload['top_level_keys']}")
    print(f"Data keys: {sanitized_payload['data_keys']}")
    print(f"education_raw_sample_keys={list(first_education_item.keys()) if isinstance(first_education_item, dict) else []}")
    if isinstance(first_education_item, dict):
        sample = {
            "raw": first_education_item.get("raw"),
            "parsed_keys": list((first_education_item.get("parsed") or {}).keys()) if isinstance(first_education_item.get("parsed"), dict) else [],
            "parsed_sample": {
                key: (first_education_item["parsed"].get(key) if isinstance(first_education_item.get("parsed"), dict) else None)
                for key in list((first_education_item.get("parsed") or {}).keys())[:8]
            },
        }
        print(f"first_education_item_sample={json.dumps(sample, ensure_ascii=False)[:3000]}")
    print("Mapped profile preview:")
    print(json.dumps(sanitized_payload["mapped_profile_preview"], indent=2, ensure_ascii=False))
    print("Mapped preview summary:")
    print(f"full_name={mapped_profile_preview.get('full_name', '')}")
    print(f"email={mapped_profile_preview.get('email', '')}")
    print(f"phone={mapped_profile_preview.get('phone', '')}")
    print(f"top_skills={mapped_profile_preview.get('top_skills', [])}")
    print(f"work_experience_count={len([line for line in str(mapped_profile_preview.get('work_experience', '')).splitlines() if line.strip()])}")
    print(f"projects_count={len([line for line in str(mapped_profile_preview.get('projects', '')).splitlines() if line.strip()])}")
    print(f"education={mapped_profile_preview.get('education', '')}")
    print(f"degree={mapped_profile_preview.get('degree', '')}")
    print(f"branch={mapped_profile_preview.get('branch', '')}")
    print(f"college={mapped_profile_preview.get('college', '')}")
    print(f"university={mapped_profile_preview.get('university', '')}")
    print(f"graduation_year={mapped_profile_preview.get('graduation_year', '')}")

    output_path = PROJECT_ROOT / "backend" / "debug_affinda_response_shape.json"
    output_path.write_text(json.dumps(sanitized_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved sanitized response shape to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
