from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from requests import RequestException, Response, Timeout

from app.config import settings
from app.services.resume_service import ResumeService


class AffindaResumeParserError(Exception):
    """Raised when Affinda parsing fails."""


def get_path(obj: Any, path: list[str], default: Any = None) -> Any:
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def normalize_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        items: list[Any] = []
        for item in value:
            items.extend(normalize_list(item))
        return items
    return [value]


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


class AffindaResumeParser:
    def __init__(self, resume_service: ResumeService) -> None:
        self.resume_service = resume_service
        self.base_url = settings.AFFINDA_API_BASE_URL or "https://api.affinda.com"
        self.timeout_seconds = settings.AFFINDA_TIMEOUT_SECONDS

    def is_enabled(self) -> bool:
        return bool(settings.AFFINDA_API_KEY)

    def document_type(self) -> str:
        return settings.AFFINDA_DOCUMENT_TYPE.strip()

    def validate_affinda_config(self) -> list[str]:
        errors: list[str] = []
        if not settings.AFFINDA_API_BASE_URL:
            errors.append("Missing AFFINDA_API_BASE_URL")
        if not settings.AFFINDA_API_KEY:
            errors.append("Missing AFFINDA_API_KEY")
        if not settings.AFFINDA_WORKSPACE:
            errors.append("Missing AFFINDA_WORKSPACE")
        if not settings.AFFINDA_DOCUMENT_TYPE:
            errors.append("Missing AFFINDA_DOCUMENT_TYPE")
        return errors

    def parse(self, *, filename: str, content: bytes, resume_text: str) -> dict[str, Any]:
        errors = self.validate_affinda_config()
        if errors:
            raise AffindaResumeParserError("; ".join(errors))

        payload, _ = self.upload_document_only(
            filename=filename,
            content=content,
            content_type=self._guess_content_type(filename),
            compact=False,
            timeout_seconds=self.timeout_seconds,
        )
        data = self._extract_data(payload)
        if not isinstance(data, dict) or not data:
            raise AffindaResumeParserError("Affinda returned no data.")

        mapped = self._map_affinda_payload(data)
        normalized = self.resume_service.normalize_profile_fields(
            mapped,
            mapped.get("raw_resume_text") or resume_text,
        )
        normalized["raw_resume_text"] = str(mapped.get("raw_resume_text") or resume_text).strip()
        return normalized

    def list_document_types(self) -> dict[str, Any]:
        errors = self.validate_affinda_config()
        filtered_errors = [error for error in errors if error != "Missing AFFINDA_DOCUMENT_TYPE"]
        if filtered_errors:
            raise AffindaResumeParserError("; ".join(filtered_errors))

        response = self._request(
            "GET",
            "/v3/document-types",
            params={"workspace": settings.AFFINDA_WORKSPACE},
            timeout_seconds=min(self.timeout_seconds, 60),
        )
        payload = self._safe_json(response)

        raw_items = []
        if isinstance(payload, list):
            raw_items = payload
        elif isinstance(payload.get("results"), list):
            raw_items = payload["results"]
        elif isinstance(payload.get("data"), list):
            raw_items = payload["data"]
        elif isinstance(payload.get("documentTypes"), list):
            raw_items = payload["documentTypes"]

        document_types = []
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
            description = str(item.get("description") or "").strip()
            if not identifier:
                continue
            document_types.append(
                {
                    "identifier": identifier,
                    "name": name,
                    "description": description,
                }
            )

        configured_document_type = settings.AFFINDA_DOCUMENT_TYPE.strip()
        configured_document_type_found = any(
            item["identifier"] == configured_document_type for item in document_types
        )

        return {
            "workspace": settings.AFFINDA_WORKSPACE,
            "configured_document_type": configured_document_type,
            "document_types": document_types,
            "configured_document_type_found": configured_document_type_found,
        }

    def upload_document_only(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        compact: bool,
        timeout_seconds: float,
    ) -> tuple[dict[str, Any], int]:
        errors = self.validate_affinda_config()
        if errors:
            raise AffindaResumeParserError("; ".join(errors))

        response = self._request(
            "POST",
            "/v3/documents",
            data={
                "workspace": settings.AFFINDA_WORKSPACE,
                "documentType": settings.AFFINDA_DOCUMENT_TYPE,
                "wait": "true",
                "compact": "false" if not compact else "true",
            },
            files={"file": (Path(filename).name or "resume", content, content_type or "application/octet-stream")},
            timeout_seconds=timeout_seconds,
        )
        return self._safe_json(response), response.status_code

    def build_debug_upload_payload(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        warnings: list[str] = []

        document_types_payload = self.list_document_types()
        if not document_types_payload["configured_document_type_found"]:
            return {
                "ok": False,
                "status_code": 400,
                "affinda_document_identifier": None,
                "top_level_keys": [],
                "data_keys": [],
                "meta_keys": [],
                "error": "Configured AFFINDA_DOCUMENT_TYPE was not found in Affinda document types for the configured workspace.",
                "warnings": warnings,
                "raw_shape_sample": {},
                "mapped_profile_preview": {},
            }

        payload, status_code = self.upload_document_only(
            filename=filename,
            content=content,
            content_type=content_type or self._guess_content_type(filename),
            compact=False,
            timeout_seconds=60,
        )
        data = self._extract_data(payload)
        meta = self._extract_meta(payload)

        if not isinstance(data, dict) or not data:
            return {
                "ok": False,
                "status_code": status_code,
                "affinda_document_identifier": self._extract_document_identifier(payload),
                "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
                "data_keys": [],
                "meta_keys": sorted(meta.keys()) if isinstance(meta, dict) else [],
                "error": "No data returned",
                "warnings": warnings,
                "raw_shape_sample": self._shape_sample(payload),
                "mapped_profile_preview": {},
            }

        mapped_profile_preview = self._map_affinda_payload(data)
        if not any(str(value).strip() for value in mapped_profile_preview.values()):
            warnings.append("Affinda response was received, but mapped_profile_preview is empty.")

        return {
            "ok": True,
            "status_code": status_code,
            "affinda_document_identifier": self._extract_document_identifier(payload),
            "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
            "data_keys": sorted(data.keys()) if isinstance(data, dict) else [],
            "meta_keys": sorted(meta.keys()) if isinstance(meta, dict) else [],
            "error": None,
            "warnings": warnings,
            "raw_shape_sample": self._shape_sample(payload),
            "mapped_profile_preview": mapped_profile_preview,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        timeout_seconds: float,
    ) -> Response:
        headers = {"Authorization": f"Bearer {settings.AFFINDA_API_KEY}"}
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                params=params,
                data=data,
                files=files,
                timeout=timeout_seconds,
            )
        except Timeout as exc:
            raise AffindaResumeParserError("request timeout") from exc
        except RequestException as exc:
            raise AffindaResumeParserError(f"request failed: {exc.__class__.__name__}") from exc

        if response.status_code == 401:
            raise AffindaResumeParserError("invalid API key")
        if response.status_code == 403:
            raise AffindaResumeParserError("invalid workspace or invalid document type")
        if response.status_code == 404:
            raise AffindaResumeParserError("invalid workspace")
        if response.status_code == 408:
            raise AffindaResumeParserError("request timeout")
        if response.status_code == 422:
            raise AffindaResumeParserError("document processing failed")
        if response.status_code >= 400:
            detail = self._extract_error_detail(response)
            raise AffindaResumeParserError(detail or f"Affinda returned status {response.status_code}")

        return response

    def _safe_json(self, response: Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise AffindaResumeParserError("invalid response shape") from exc
        if not isinstance(payload, dict):
            raise AffindaResumeParserError("invalid response shape")
        return payload

    def _extract_error_detail(self, response: Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""
        if not isinstance(payload, dict):
            return ""
        return str(
            payload.get("detail")
            or payload.get("message")
            or payload.get("error")
            or ""
        ).strip()

    def _extract_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("data"), dict):
            return payload["data"]
        if isinstance(get_path(payload, ["document", "data"]), dict):
            return get_path(payload, ["document", "data"], {})
        if isinstance(payload.get("result"), dict):
            return payload["result"]
        if isinstance(payload.get("document"), dict):
            return payload["document"]
        return payload if isinstance(payload, dict) else {}

    def _extract_meta(self, payload: dict[str, Any]) -> dict[str, Any]:
        for key in ("meta", "metadata"):
            if isinstance(payload.get(key), dict):
                return payload[key]
        if isinstance(get_path(payload, ["document", "meta"]), dict):
            return get_path(payload, ["document", "meta"], {})
        return {}

    def _extract_document_identifier(self, payload: dict[str, Any]) -> str:
        return str(
            payload.get("identifier")
            or payload.get("id")
            or get_path(payload, ["document", "identifier"], "")
            or get_path(payload, ["document", "id"], "")
            or ""
        ).strip()

    def _shape_sample(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"type": type(payload).__name__}

        sample: dict[str, Any] = {}
        for key, value in list(payload.items())[:12]:
            if isinstance(value, dict):
                sample[key] = {"type": "dict", "keys": list(value.keys())[:12]}
            elif isinstance(value, list):
                first = value[0] if value else None
                if isinstance(first, dict):
                    sample[key] = {
                        "type": "list",
                        "length": len(value),
                        "first_item_keys": list(first.keys())[:12],
                    }
                else:
                    sample[key] = {"type": "list", "length": len(value)}
            else:
                sample[key] = {"type": type(value).__name__}
        return sample

    def _map_affinda_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        education_entries = normalize_list(data.get("education"))
        selected_education_entries = self._select_education_entries(education_entries)
        primary_education = selected_education_entries[0] if selected_education_entries else {}
        work_entries = normalize_list(data.get("workExperience"))
        project_entries = normalize_list(data.get("project"))
        achievement_entries = normalize_list(data.get("achievement"))
        certification_entries = normalize_list(data.get("certification") or data.get("certifications"))
        top_skills = self._collect_skills(data.get("skill"), limit=8)
        technical_skills = self._collect_skills(data.get("skill"), limit=20)

        preview = {
            "full_name": self._extract_candidate_name(data.get("candidateName")),
            "email": self._extract_email(data.get("email")),
            "phone": self._extract_phone_value(data.get("phoneNumber")),
            "location": self._extract_location(data.get("location")),
            "professional_summary": self._extract_summary(data),
            "education": self._build_education_summary(selected_education_entries),
            "degree": self._extract_degree(primary_education),
            "branch": self._extract_branch(primary_education),
            "college": self._extract_college(primary_education),
            "university": self._extract_university(primary_education) or self._extract_college(primary_education),
            "graduation_year": self._extract_graduation_year(primary_education),
            "top_skills": top_skills,
            "technical_skills": technical_skills,
            "work_experience": self._build_work_entries(work_entries),
            "projects": self._build_project_entries(project_entries),
            "achievements": self._build_simple_entries(achievement_entries),
            "certifications": self._build_simple_entries(certification_entries),
            "raw_resume_text": self._extract_raw_text(data.get("rawText")),
        }
        return {key: value for key, value in preview.items() if str(value or "").strip()}

    def _extract_candidate_name(self, value: Any) -> str:
        if isinstance(value, list):
            for item in value:
                name = self._extract_candidate_name(item)
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

    def _extract_email(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            for item in value:
                email = self._extract_email(item)
                if email:
                    return email
            return ""
        if isinstance(value, dict):
            return self._first_non_empty(
                value.get("raw"),
                value.get("parsed"),
                value.get("value"),
                value.get("text"),
                value.get("email"),
                value.get("emailAddress"),
            )
        return ""

    def _extract_phone_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            for item in value:
                phone = self._extract_phone_value(item)
                if phone:
                    return phone
            return ""
        if isinstance(value, dict):
            return self._first_non_empty(
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

    def _extract_summary(self, data: dict[str, Any]) -> str:
        return self._first_non_empty(data.get("summary"), data.get("objective"))

    def _extract_location(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if not isinstance(value, dict):
            return ""
        return self._first_non_empty(
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

    def _extract_degree(self, education: Any) -> str:
        if not isinstance(education, dict):
            return ""
        parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
        accreditation = education.get("accreditation") or parsed.get("educationAccreditation")
        if isinstance(accreditation, dict):
            return self._first_non_empty(
                accreditation.get("education"),
                accreditation.get("inputStr"),
                accreditation.get("matchStr"),
                accreditation.get("raw"),
                accreditation.get("parsed"),
            )
        degree = self._first_non_empty(
            education.get("degree"),
            education.get("qualification"),
            parsed.get("educationAccreditation"),
        )
        return self._clean_education_text(degree)

    def _extract_branch(self, education: Any) -> str:
        if not isinstance(education, dict):
            return ""
        parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
        major = parsed.get("educationMajor")
        if isinstance(major, list):
            major_parts = [self._extract_text_node(item) for item in major]
            major_parts = [part for part in major_parts if part]
            major_text = " and ".join(major_parts) if len(major_parts) == 2 else ", ".join(major_parts)
            if major_text:
                return self._clean_education_text(major_text)
        majors = self._list_value(education.get("majors") or education.get("specializations"))
        if majors:
            return self._clean_education_text(majors[0])
        if isinstance(major, dict):
            return self._clean_education_text(self._first_non_empty(major.get("raw"), major.get("parsed")))
        if isinstance(major, str):
            return self._clean_education_text(major.strip())
        return self._clean_education_text(
            self._first_non_empty(
                education.get("fieldOfStudy"),
                education.get("specialization"),
            )
        )

    def _extract_college(self, education: Any) -> str:
        if not isinstance(education, dict):
            return ""
        parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
        organization = parsed.get("educationOrganization")
        if isinstance(organization, dict):
            return self._normalize_university_name(
                self._first_non_empty(organization.get("raw"), organization.get("parsed"))
            )
        return self._normalize_university_name(self._first_non_empty(
            education.get("organization"),
            education.get("institution"),
            organization,
        ))

    def _extract_university(self, education: Any) -> str:
        if not isinstance(education, dict):
            return ""
        return self._normalize_university_name(self._first_non_empty(
            education.get("organization"),
            education.get("institution"),
            education.get("school"),
        ))

    def _extract_graduation_year(self, education: Any) -> str:
        if not isinstance(education, dict):
            return ""
        parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
        dates = education.get("dates") or parsed.get("educationDates")
        values = []
        if isinstance(dates, dict):
            values.extend(
                [
                    dates.get("completionDate"),
                    dates.get("endDate"),
                    dates.get("rawText"),
                    dates.get("raw"),
                    dates.get("parsed"),
                ]
            )
        values.extend([education.get("graduationDate"), education.get("endDate"), education.get("date")])
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            if "present" in text.lower():
                return "Present"
            year = self.resume_service._normalize_year(value)  # noqa: SLF001
            if year:
                return year
        return ""

    def _build_education_summary(self, education_entries: list[Any]) -> str:
        entries = []
        seen: set[str] = set()
        for education in education_entries[:3]:
            if not isinstance(education, dict):
                continue
            degree = self._extract_degree(education)
            branch = self._extract_branch(education)
            university = self._extract_college(education) or self._extract_university(education)
            graduation_year = self._extract_graduation_year(education)
            line = ""
            if degree and branch and university:
                line = f"{degree} in {branch}, {university}"
            elif degree and university:
                line = f"{degree}, {university}"
            else:
                parts = [degree, branch, university, graduation_year]
                line = ", ".join(part for part in parts if part)
            line = self._clean_education_text(line)
            key = line.lower()
            if line and key not in seen:
                seen.add(key)
                entries.append(line)
        return "\n".join(entries)

    def _select_education_entries(self, education_entries: list[Any]) -> list[Any]:
        preferred: list[Any] = []
        fallback: list[Any] = []
        for education in education_entries:
            if not isinstance(education, dict):
                continue
            raw = str(education.get("raw", "")).strip().lower()
            parsed = education.get("parsed") if isinstance(education.get("parsed"), dict) else {}
            level = str(get_path(parsed, ["educationLevel", "raw"], "")).strip().lower()
            organization = self._extract_college(education)
            degree = self._extract_degree(education)
            branch = self._extract_branch(education)
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

    def _clean_education_text(self, value: str) -> str:
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

    def _normalize_university_name(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        normalized = text.title() if text.isupper() else text
        normalized = normalized.replace("O.P Jindal University", "O.P. Jindal University")
        normalized = normalized.replace("O.P JINDAL UNIVERSITY", "O.P. Jindal University")
        return normalized

    def _build_work_entries(self, work_entries: list[Any]) -> str:
        lines: list[str] = []
        for item in work_entries:
            if not self._is_real_work_experience(item):
                continue
            line = self._build_work_entry(item)
            if line:
                lines.append(line)
        return "\n".join(lines[:5])

    def _is_real_work_experience(self, item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
        organization = self._extract_text_node(parsed.get("workExperienceOrganization"))
        title = self._extract_text_node(parsed.get("workExperienceJobTitle"))
        raw = str(item.get("raw", "")).strip().lower()
        if "github" in raw:
            return False
        if organization and title:
            return True
        return any(token in title.lower() for token in ("intern", "engineer", "developer", "analyst"))

    def _build_simple_entries(self, entries: list[str]) -> str:
        rendered: list[str] = []
        for entry in entries:
            if isinstance(entry, dict):
                text = self._render_mapping(entry)
            else:
                text = str(entry or "").strip()
            if text:
                rendered.append(text)
        return "\n".join(rendered[:5])

    def _build_work_entry(self, item: Any) -> str:
        if isinstance(item, str):
            return item.strip()
        if not isinstance(item, dict):
            return ""
        parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
        parts = [
            self._extract_job_title(item),
            self._first_non_empty(
                self._extract_text_node(parsed.get("workExperienceOrganization")),
                item.get("organization"),
                item.get("company"),
                item.get("employer"),
            ),
            self._extract_date_range(item),
            self._first_non_empty(
                self._extract_text_node(parsed.get("workExperienceDescription")),
                item.get("summary"),
                item.get("jobDescription"),
                item.get("description"),
            ),
        ]
        return " - ".join(part for part in parts if part)

    def _extract_job_title(self, item: Any) -> str:
        if not isinstance(item, dict):
            return ""
        parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
        return self._first_non_empty(
            self._extract_text_node(parsed.get("workExperienceJobTitle")),
            item.get("jobTitle"),
            item.get("title"),
            item.get("occupation"),
        )

    def _extract_date_range(self, item: Any) -> str:
        if not isinstance(item, dict):
            return ""
        parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
        dates = item.get("dates") or parsed.get("workExperienceDates")
        if isinstance(dates, dict):
            start = self._first_non_empty(
                dates.get("startDate"),
                self._extract_nested_date(dates.get("start")),
                dates.get("rawText"),
                dates.get("raw"),
            )
            end = self._first_non_empty(
                dates.get("endDate"),
                self._extract_nested_date(dates.get("end")),
            )
            if start and end:
                return f"{start} to {end}"
            return start or end
        start = self._first_non_empty(item.get("startDate"), item.get("start"))
        end = self._first_non_empty(item.get("endDate"), item.get("end"))
        if start and end:
            return f"{start} to {end}"
        return start or end

    def _collect_skills(self, value: Any, *, limit: int) -> list[str]:
        skills: list[str] = []
        seen: set[str] = set()
        for item in normalize_list(value):
            text = self._extract_skill_text(item)
            if not text:
                continue
            for fragment in [part.strip() for part in text.replace("|", ",").split(",") if part.strip()]:
                key = fragment.lower()
                if key in seen or key in NON_SKILL_LABELS:
                    continue
                seen.add(key)
                skills.append(fragment)
        ranked = sorted(
            skills,
            key=lambda skill: (
                PREFERRED_TOP_SKILLS.index(skill.lower())
                if skill.lower() in PREFERRED_TOP_SKILLS
                else len(PREFERRED_TOP_SKILLS),
                skills.index(skill),
            ),
        )
        return ranked[:limit]

    def _extract_skill_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return self._first_non_empty(
                value.get("name"),
                value.get("raw"),
                value.get("parsed"),
                value.get("value"),
                value.get("text"),
                value.get("skill"),
            )
        return ""

    def _build_project_entries(self, entries: list[Any]) -> str:
        lines: list[str] = []
        for item in entries:
            line = self._build_project_entry(item)
            if line:
                lines.append(line)
        return "\n".join(lines[:8])

    def _build_project_entry(self, item: Any) -> str:
        if isinstance(item, str):
            return item.strip()
        if not isinstance(item, dict):
            return ""
        parsed = item.get("parsed") if isinstance(item.get("parsed"), dict) else {}
        parts = [
            self._first_non_empty(
                self._extract_text_node(parsed.get("projectTitle")),
                item.get("name"),
                item.get("title"),
                item.get("project"),
            ),
            self._first_non_empty(
                self._extract_text_node(parsed.get("projectDescription")),
                item.get("description"),
                item.get("summary"),
                item.get("details"),
            ),
            self._stringify_technologies(item.get("technologies")),
        ]
        return " - ".join(part for part in parts if part)

    def _stringify_technologies(self, value: Any) -> str:
        parts: list[str] = []
        for item in normalize_list(value):
            if isinstance(item, dict):
                text = self._first_non_empty(item.get("name"), item.get("raw"), item.get("text"))
            else:
                text = str(item or "").strip()
            if text:
                parts.append(text)
        return ", ".join(parts)

    def _extract_raw_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return "\n".join(str(item).strip() for item in value if str(item or "").strip())
        return ""

    def _extract_text_node(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return self._first_non_empty(value.get("raw"), value.get("parsed"), value.get("text"))
        return ""

    def _extract_nested_date(self, value: Any) -> str:
        if isinstance(value, dict):
            return self._first_non_empty(value.get("date"), value.get("rawText"), value.get("raw"))
        return str(value or "").strip()

    def _list_value(self, value: Any) -> list[Any]:
        items = normalize_list(value)
        rendered: list[Any] = []
        for item in items:
            if isinstance(item, dict):
                text = self._render_mapping(item)
                if text:
                    rendered.append(text)
            elif str(item or "").strip():
                rendered.append(str(item).strip())
        return rendered

    def _render_mapping(self, value: dict[str, Any]) -> str:
        if self._extract_job_title(value):
            return self._build_work_entry(value)
        parts = [
            self._first_non_empty(value.get("name"), value.get("title"), value.get("organization"), value.get("issuer")),
            self._first_non_empty(value.get("description"), value.get("summary"), value.get("details")),
        ]
        return " - ".join(part for part in parts if part)

    def _first_non_empty(self, *values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _guess_content_type(self, filename: str) -> str:
        suffix = Path(filename or "").suffix.lower()
        return {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
        }.get(suffix, "application/octet-stream")
