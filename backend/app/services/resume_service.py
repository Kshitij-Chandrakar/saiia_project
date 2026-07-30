import io
import json
import re
from pathlib import Path
from typing import Any

import fitz
import requests
from docx import Document
from requests import RequestException, Timeout

from app.config import settings
from app.nlp.answer_generator import ProviderError

MAX_RESUME_FILE_BYTES = 5 * 1024 * 1024
LOW_TEXT_PDF_MESSAGE = (
    "Could not extract readable text from this resume. Please upload a text-based PDF, DOCX, or TXT file."
)

SUPPORTED_RESUME_TYPES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
}

PROFILE_FIELD_ORDER = (
    "full_name",
    "email",
    "phone",
    "location",
    "current_title",
    "target_role",
    "professional_summary",
    "education",
    "degree",
    "branch",
    "branch_specialization",
    "college",
    "college_university",
    "university",
    "graduation_year",
    "top_skills",
    "technical_skills",
    "soft_skills",
    "tools_frameworks",
    "projects",
    "experience",
    "work_experience",
    "leadership_activities",
    "achievements",
    "certifications",
    "live_profile_summary",
    "raw_resume_text",
)

PROFILE_COMPATIBILITY_FIELDS = (
    "resume",
    "role",
    "company",
    "skills",
    "manual_review_required",
    "manual_review_message",
    "extraction_confidence",
)

PROFILE_REVIEW_FIELDS = (
    "full_name",
    "email",
    "phone",
    "location",
    "current_title",
    "target_role",
    "professional_summary",
    "education",
    "degree",
    "branch",
    "college",
    "university",
    "graduation_year",
    "top_skills",
    "projects_or_experience",
    "projects",
    "experience",
)

PREFERRED_TOP_SKILL_ORDER = (
    "python",
    "machine learning",
    "deep learning",
    "tensorflow",
    "pytorch",
    "fastapi",
    "opencv",
    "streamlit",
)


class ResumeExtractionError(Exception):
    """Raised when resume extraction fails with a user-facing error."""


class ResumeService:
    def __init__(self) -> None:
        self._groq_url = "https://api.groq.com/openai/v1/chat/completions"

    def validate_upload(self, *, filename: str, content: bytes) -> str:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in SUPPORTED_RESUME_TYPES:
            raise ResumeExtractionError(
                "Unsupported resume file type. Please upload a PDF, DOCX, or TXT resume."
            )
        if not content:
            raise ResumeExtractionError("The uploaded resume is empty. Please choose a valid file.")
        if len(content) > MAX_RESUME_FILE_BYTES:
            raise ResumeExtractionError("Resume file is too large. Please upload a file under 5 MB.")
        return SUPPORTED_RESUME_TYPES[suffix]

    def extract_text(self, *, filename: str, content: bytes) -> str:
        file_type = self.validate_upload(filename=filename, content=content)

        try:
            if file_type == "pdf":
                text = self._extract_pdf_text(content)
            elif file_type == "docx":
                text = self._extract_docx_text(content)
            else:
                text = self._extract_txt_text(content)
        except ResumeExtractionError:
            raise
        except Exception as exc:
            raise ResumeExtractionError(
                "Could not read this resume file. Please upload a valid PDF, DOCX, or TXT file."
            ) from exc

        cleaned = self._clean_text(text)
        if not cleaned:
            if file_type == "pdf":
                raise ResumeExtractionError(LOW_TEXT_PDF_MESSAGE)
            raise ResumeExtractionError(
                "Could not extract readable text from this resume. Please upload a file with readable text."
            )
        return cleaned

    def build_profile_fields(self, resume_text: str) -> dict[str, Any]:
        if not settings.GROQ_API_KEY:
            raise ProviderError("Groq API key is missing. Set GROQ_API_KEY to enable resume extraction.")

        prompt = (
            "Convert the resume text into clean SAIIA profile fields.\n"
            "Return valid JSON only with these keys:\n"
            "full_name, email, phone, location, current_title, target_role, professional_summary, "
            "education, degree, branch_specialization, college_university, graduation_year, top_skills, "
            "technical_skills, soft_skills, tools_frameworks, projects, experience, work_experience, leadership_activities, achievements, certifications\n"
            "Rules:\n"
            "- Use strings for single-value fields.\n"
            "- Multi-item fields may be arrays of short strings or a single clean string.\n"
            "- Extract the candidate name separately into `full_name`.\n"
            "- Keep education separate from skills, projects, and experience.\n"
            "- `education` should be a short education summary only.\n"
            "- `degree`, `branch_specialization`, `college_university`, and `graduation_year` must stay separate when available.\n"
            "- `professional_summary` must be a concise 2-3 sentence spoken-style summary.\n"
            "- `top_skills` must contain only 6 to 8 of the strongest candidate skills.\n"
            "- `technical_skills` should include the fuller technical stack without duplicates.\n"
            "- `tools_frameworks` should include major tools and frameworks only.\n"
            "- `projects` should preserve project names separately and keep each item short.\n"
            "- `work_experience` must include only actual jobs, internships, or professional experience.\n"
            "- Campus coordination, IEEE, SIH, event, volunteer, club, ambassador, or leadership roles must go into `leadership_activities` or `achievements`, not `work_experience`.\n"
            "- `experience`, `work_experience`, `leadership_activities`, `achievements`, and `certifications` must stay separate from each other.\n"
            "- Do not dump the whole resume into any one field.\n"
            "- Do not mix skills, education, projects, and experience together.\n"
            "- Remove noisy symbols and markdown-style bullets.\n"
            "- Infer `current_title` or `target_role` only if strongly supported by the resume.\n"
            "- If name or education is unclear, leave the field empty instead of guessing.\n"
            "- Do not invent any experience, projects, education, achievements, or certifications.\n"
            "- Use empty strings or empty arrays for missing information.\n\n"
            f"Resume text:\n{resume_text}"
        )

        try:
            response = requests.post(
                self._groq_url,
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.GROQ_MODEL,
                    "temperature": 0.2,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You extract structured candidate profile data from resumes. "
                                "Return only valid JSON, keep sections cleanly separated, and never invent missing facts."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=settings.GROQ_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except Timeout as exc:
            raise ProviderError(
                "Groq timed out while extracting resume fields. Please try again."
            ) from exc
        except RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 401:
                raise ProviderError(
                    "Groq API key is invalid or missing. Please update GROQ_API_KEY and try again."
                ) from exc
            raise ProviderError(
                "Groq could not extract resume fields right now. Please check your API key, internet connection, or Groq service status."
            ) from exc

        data = response.json()
        raw_content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ProviderError("Groq returned an unexpected resume extraction response.") from exc

        return self.normalize_profile_fields(parsed, resume_text)

    def empty_profile(self) -> dict[str, Any]:
        profile: dict[str, Any] = {key: "" for key in PROFILE_FIELD_ORDER}
        for field in PROFILE_COMPATIBILITY_FIELDS:
            profile[field] = ""
        profile["manual_review_required"] = False
        return profile

    def normalize_profile_fields(self, parsed: dict[str, Any], resume_text: str) -> dict[str, Any]:
        return self._normalize_profile(parsed, resume_text)

    def merge_profile_fields(
        self,
        primary: dict[str, Any],
        fallback: dict[str, Any],
        *,
        resume_text: str,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        csv_limits = {
            "top_skills": 8,
            "technical_skills": 20,
            "tools_frameworks": 20,
            "skills": 20,
        }
        multiline_limits = {
            "projects": 5,
            "experience": 5,
            "work_experience": 5,
            "leadership_activities": 5,
            "achievements": 5,
            "certifications": 5,
            "education": 3,
        }

        for field in (*PROFILE_FIELD_ORDER, *PROFILE_COMPATIBILITY_FIELDS):
            primary_value = primary.get(field, "")
            fallback_value = fallback.get(field, "")
            if field in csv_limits:
                merged[field] = ", ".join(
                    self._merge_skill_values(primary_value, fallback_value, limit=csv_limits[field])
                )
            elif field in multiline_limits:
                merged[field] = self._merge_multiline_values(
                    primary_value,
                    fallback_value,
                    limit=multiline_limits[field],
                )
            else:
                merged[field] = self._normalize_text_value(primary_value) or self._normalize_text_value(
                    fallback_value
                )

        merged["raw_resume_text"] = self._clean_text(
            primary.get("raw_resume_text") or fallback.get("raw_resume_text") or resume_text
        )
        return self._normalize_profile(merged, merged["raw_resume_text"])

    def get_missing_fields(self, profile: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        for field in PROFILE_REVIEW_FIELDS:
            if field == "education":
                if not self._has_education_details(profile):
                    missing.append(field)
                continue
            if field == "projects_or_experience":
                if not (
                    self._normalize_text_value(profile.get("projects", ""))
                    or self._normalize_text_value(profile.get("experience", ""))
                    or self._normalize_text_value(profile.get("work_experience", ""))
                ):
                    missing.append(field)
                continue
            if not self._normalize_text_value(profile.get(field, "")):
                missing.append(field)
        return missing

    def _extract_pdf_text(self, content: bytes) -> str:
        document = fitz.open(stream=content, filetype="pdf")
        try:
            text = "\n".join(page.get_text("text") for page in document)
        finally:
            document.close()

        cleaned = self._clean_text(text)
        alpha_chars = sum(char.isalpha() for char in cleaned)
        if len(cleaned) < 80 or alpha_chars < 50:
            raise ResumeExtractionError(LOW_TEXT_PDF_MESSAGE)
        return cleaned

    def _extract_docx_text(self, content: bytes) -> str:
        document = Document(io.BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    def _extract_txt_text(self, content: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ResumeExtractionError(
            "Could not read this resume file. Please upload a valid PDF, DOCX, or TXT file."
        )

    def _clean_text(self, value: Any) -> str:
        text = str(value or "")
        lines = [line.strip() for line in text.splitlines()]
        filtered = [line for line in lines if line]
        return "\n".join(filtered).strip()

    def _normalize_profile(self, parsed: dict[str, Any], resume_text: str) -> dict[str, Any]:
        normalized = self.empty_profile()

        normalized["full_name"] = self._normalize_name(parsed.get("full_name", ""))
        normalized["email"] = self._normalize_contact_value(parsed.get("email", ""), value_type="email")
        normalized["phone"] = self._normalize_contact_value(parsed.get("phone", ""), value_type="phone")
        normalized["location"] = self._normalize_text_value(parsed.get("location", ""))

        current_title = self._normalize_text_value(parsed.get("current_title", ""))
        target_role = self._normalize_text_value(parsed.get("target_role", ""))
        normalized["current_title"] = current_title or target_role
        normalized["target_role"] = target_role or current_title

        normalized["professional_summary"] = self._normalize_summary(
            parsed.get("professional_summary", ""),
            max_sentences=3,
        )
        normalized["education"] = self._normalize_summary(parsed.get("education", ""), max_sentences=2)
        normalized["degree"] = self._normalize_text_value(parsed.get("degree", ""))
        normalized["branch"] = self._normalize_text_value(
            parsed.get("branch", "") or parsed.get("branch_specialization", "")
        )
        normalized["branch_specialization"] = normalized["branch"]
        normalized["college"] = self._normalize_text_value(
            parsed.get("college", "") or parsed.get("college_university", "") or parsed.get("university", "")
        )
        normalized["college_university"] = normalized["college"]
        normalized["university"] = self._normalize_text_value(
            parsed.get("university", "") or parsed.get("college", "") or parsed.get("college_university", "")
        )
        normalized["graduation_year"] = self._normalize_year(parsed.get("graduation_year", ""))

        top_skills = self._prioritize_top_skills(
            self._normalize_skill_list(
            parsed.get("top_skills", "") or parsed.get("skills", ""),
            limit=8,
            )
        )[:8]
        technical_skill_candidates = self._normalize_skill_list(
            parsed.get("technical_skills", "") or parsed.get("skills", ""),
            limit=20,
        )
        technical_skills = [
            skill
            for skill in technical_skill_candidates
            if re.sub(r"[^a-z0-9+#]", "", skill.lower())
            not in {re.sub(r"[^a-z0-9+#]", "", item.lower()) for item in top_skills}
        ]
        soft_skills = self._normalize_skill_list(parsed.get("soft_skills", ""), limit=12)
        tools_frameworks = self._normalize_skill_list(parsed.get("tools_frameworks", ""), limit=20)

        normalized_projects = self._normalize_multiline_entries(parsed.get("projects", ""), limit=5)
        normalized_experience = self._normalize_multiline_entries(
            parsed.get("experience", "") or parsed.get("work_experience", ""),
            limit=6,
        )
        normalized_experience = self._remove_project_entries(normalized_experience, normalized_projects)
        normalized_work_experience, normalized_leadership = self._split_experience_buckets(normalized_experience)
        achievement_source = self._normalize_multiline_entries(parsed.get("achievements", ""), limit=5)
        normalized_achievements = self._merge_multiline_values(
            achievement_source,
            normalized_leadership,
            limit=5,
        )

        normalized["top_skills"] = ", ".join(top_skills)
        normalized["technical_skills"] = ", ".join(technical_skills)
        normalized["soft_skills"] = ", ".join(soft_skills)
        normalized["tools_frameworks"] = ", ".join(tools_frameworks)
        normalized["projects"] = normalized_projects
        normalized["experience"] = normalized_experience
        normalized["work_experience"] = normalized_work_experience
        normalized["leadership_activities"] = normalized_leadership
        normalized["achievements"] = normalized_achievements
        normalized["certifications"] = self._normalize_multiline_entries(
            parsed.get("certifications", ""),
            limit=5,
        )

        manual_review_reasons = []
        if not normalized["full_name"]:
            manual_review_reasons.append("full_name")
        if not self._has_education_details(normalized):
            manual_review_reasons.append("education")
        if not top_skills:
            manual_review_reasons.append("top_skills")
        if not (normalized["projects"] or normalized["experience"]):
            manual_review_reasons.append("projects_or_experience")

        confidence = "high"
        if manual_review_reasons or len(top_skills) < 2 or not normalized["professional_summary"]:
            confidence = "medium"
        if len(manual_review_reasons) >= 2 or (not normalized["professional_summary"] and len(top_skills) < 2):
            confidence = "low"

        normalized["resume"] = normalized["professional_summary"]
        normalized["role"] = normalized["current_title"] or normalized["target_role"]
        normalized["company"] = ""
        normalized["skills"] = normalized["top_skills"] or normalized["technical_skills"]
        normalized["live_profile_summary"] = self._build_live_profile_summary(normalized)
        normalized["raw_resume_text"] = self._clean_text(resume_text)
        normalized["manual_review_required"] = bool(manual_review_reasons or confidence == "low")
        normalized["manual_review_message"] = (
            "Some resume sections may need manual review." if normalized["manual_review_required"] else ""
        )
        normalized["extraction_confidence"] = confidence

        return normalized

    def _normalize_text_value(self, value: Any) -> str:
        text = self._stringify_value(value)
        if not text:
            return ""

        translation_map = str.maketrans(
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
        text = text.translate(translation_map)
        text = re.sub(r"[*_`#>\u2022\u25cf\u25aa]+", " ", text)
        text = re.sub(r"\s*[:|]\s*", " ", text)
        text = re.sub(r"\s*-\s*", " - ", text)
        text = re.sub(r"\s+", " ", text).strip(" ,;-")
        text = self._collapse_duplicate_segments(text)
        return text

    def _normalize_name(self, value: Any) -> str:
        text = self._normalize_text_value(value)
        if not text:
            return ""
        if text.isupper() or text == text.lower():
            tokens = []
            for token in text.split():
                if re.fullmatch(r"[A-Z]{2,}", token):
                    tokens.append(token.title())
                elif re.fullmatch(r"[A-Za-z]+(?:[-'][A-Za-z]+)?", token):
                    tokens.append(token.title())
                else:
                    tokens.append(token)
            return " ".join(tokens)
        return text

    def _normalize_summary(self, value: Any, *, max_sentences: int) -> str:
        text = self._normalize_text_value(value)
        if not text:
            return ""

        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", text) if segment.strip()]
        if sentences:
            text = " ".join(sentences[:max_sentences])
        return text[:420].strip()

    def _normalize_contact_value(self, value: Any, *, value_type: str) -> str:
        text = self._normalize_text_value(value)
        if not text:
            return ""

        if value_type == "email":
            match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
            return match.group(0) if match else ""

        digits = re.sub(r"[^\d+]", "", text)
        if len(re.sub(r"\D", "", digits)) < 10:
            return ""
        return text

    def _normalize_year(self, value: Any) -> str:
        text = self._normalize_text_value(value)
        if not text:
            return ""

        match = re.search(r"\b(19|20)\d{2}\b", text)
        return match.group(0) if match else ""

    def _normalize_skill_list(self, value: Any, *, limit: int) -> list[str]:
        items = self._listify_value(value)
        cleaned: list[str] = []
        seen: set[str] = set()

        for item in items:
            fragments = re.split(r",|/|\||;|\n", item)
            for fragment in fragments:
                skill = self._normalize_text_value(fragment)
                if not skill:
                    continue
                normalized_key = re.sub(r"[^a-z0-9+#]", "", skill.lower())
                if not normalized_key or normalized_key in seen:
                    continue
                seen.add(normalized_key)
                cleaned.append(skill)
                if len(cleaned) >= limit:
                    return cleaned

        return cleaned

    def _prioritize_top_skills(self, skills: list[str]) -> list[str]:
        normalized_order = {name: index for index, name in enumerate(PREFERRED_TOP_SKILL_ORDER)}
        return sorted(
            skills,
            key=lambda skill: (
                normalized_order.get(skill.lower(), len(normalized_order)),
                skills.index(skill),
            ),
        )

    def _normalize_multiline_entries(self, value: Any, *, limit: int) -> str:
        items = self._listify_value(value)
        cleaned: list[str] = []
        seen: set[str] = set()

        for item in items:
            entry = self._normalize_text_value(item)
            if not entry:
                continue
            key = re.sub(r"[^a-z0-9]", "", entry.lower())
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(entry)
            if len(cleaned) >= limit:
                break

        return "\n".join(cleaned)

    def _split_experience_buckets(self, value: str) -> tuple[str, str]:
        work_entries: list[str] = []
        leadership_entries: list[str] = []

        for raw_line in str(value or "").splitlines():
            line = self._normalize_text_value(raw_line)
            if not line:
                continue
            if self._is_leadership_entry(line):
                leadership_entries.append(line)
            elif self._is_professional_experience_entry(line):
                work_entries.append(line)
            else:
                leadership_entries.append(line)

        return "\n".join(work_entries[:5]), "\n".join(leadership_entries[:5])

    def _remove_project_entries(self, experience: str, projects: str) -> str:
        project_lines = [line.strip() for line in str(projects or "").splitlines() if line.strip()]
        if not project_lines:
            return experience

        project_keys = {re.sub(r"[^a-z0-9]", "", line.lower()) for line in project_lines}
        cleaned_lines: list[str] = []
        for raw_line in str(experience or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line_key = re.sub(r"[^a-z0-9]", "", line.lower())
            if any(project_key and project_key in line_key for project_key in project_keys):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines[:6])

    def _is_leadership_entry(self, line: str) -> bool:
        normalized = line.lower()
        leadership_tokens = (
            "ieee",
            "sih",
            "technoambition",
            "coordinator",
            "core team",
            "student",
            "club",
            "chapter",
            "ambassador",
            "organizer",
            "organiser",
            "leadership",
            "volunteer",
            "event",
            "hackathon",
        )
        return any(token in normalized for token in leadership_tokens)

    def _is_professional_experience_entry(self, line: str) -> bool:
        normalized = line.lower()
        professional_tokens = (
            "intern",
            "internship",
            "engineer",
            "developer",
            "analyst",
            "software",
            "company",
            "technologies",
            "private limited",
            "pvt ltd",
            "llp",
            "associate",
            "consultant",
        )
        return any(token in normalized for token in professional_tokens)

    def _collapse_duplicate_segments(self, text: str) -> str:
        parts = [part.strip() for part in text.split(" - ") if part.strip()]
        if len(parts) < 2:
            return text
        deduped: list[str] = []
        seen: set[str] = set()
        for part in parts:
            key = re.sub(r"[^a-z0-9]", "", part.lower())
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(part)
        return " - ".join(deduped) if deduped else text

    def _build_live_profile_summary(self, profile: dict[str, Any]) -> str:
        projects = [line.strip() for line in str(profile.get("projects", "")).splitlines() if line.strip()]
        leadership = [
            line.strip() for line in str(profile.get("leadership_activities", "")).splitlines() if line.strip()
        ]
        project_summary = "\n".join(projects[:2])
        education = self._normalize_text_value(
            profile.get("education")
            or ", ".join(
                part
                for part in [
                    str(profile.get("degree", "")).strip(),
                    str(profile.get("branch", "") or profile.get("branch_specialization", "")).strip(),
                    str(profile.get("college", "") or profile.get("college_university", "")).strip(),
                    str(profile.get("graduation_year", "")).strip(),
                ]
                if part
            )
        )
        summary = {
            "full_name": self._normalize_text_value(profile.get("full_name", "")),
            "target_role": self._normalize_text_value(
                profile.get("target_role", "") or profile.get("current_title", "") or profile.get("role", "")
            ),
            "education": education,
            "top_skills": self._normalize_text_value(profile.get("top_skills", "")),
            "projects": project_summary,
            "leadership_highlights": "\n".join(leadership[:2]),
            "company": self._normalize_text_value(profile.get("company", "")),
        }
        return json.dumps(summary, ensure_ascii=False)

    def _merge_skill_values(self, primary: Any, fallback: Any, *, limit: int) -> list[str]:
        merged = self._normalize_skill_list(primary, limit=limit)
        if len(merged) >= limit:
            return merged

        for skill in self._normalize_skill_list(fallback, limit=limit):
            key = re.sub(r"[^a-z0-9+#]", "", skill.lower())
            existing_keys = {re.sub(r"[^a-z0-9+#]", "", item.lower()) for item in merged}
            if not key or key in existing_keys:
                continue
            merged.append(skill)
            if len(merged) >= limit:
                break
        return merged

    def _merge_multiline_values(self, primary: Any, fallback: Any, *, limit: int) -> str:
        merged = self._normalize_multiline_entries(primary, limit=limit)
        merged_lines = [line.strip() for line in merged.splitlines() if line.strip()]
        seen = {re.sub(r"[^a-z0-9]", "", line.lower()) for line in merged_lines}

        for line in self._normalize_multiline_entries(fallback, limit=limit).splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue
            key = re.sub(r"[^a-z0-9]", "", cleaned.lower())
            if not key or key in seen:
                continue
            seen.add(key)
            merged_lines.append(cleaned)
            if len(merged_lines) >= limit:
                break

        return "\n".join(merged_lines)

    def _listify_value(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                items.extend(self._listify_value(item))
            return items
        if isinstance(value, dict):
            return [self._stringify_mapping(value)]

        text = str(value).strip()
        if not text:
            return []
        return [segment.strip() for segment in re.split(r"\n{2,}|\u2022", text) if segment.strip()]

    def _stringify_mapping(self, value: dict[str, Any]) -> str:
        prioritized_keys = (
            "name",
            "title",
            "project",
            "role",
            "degree",
            "organization",
            "college",
            "university",
            "summary",
            "description",
            "details",
        )
        parts = []
        seen = set()

        for key in prioritized_keys:
            item = self._normalize_text_value(value.get(key, ""))
            if item and item.lower() not in seen:
                seen.add(item.lower())
                parts.append(item)

        for key, raw_item in value.items():
            if key in prioritized_keys:
                continue
            item = self._normalize_text_value(raw_item)
            if item and item.lower() not in seen:
                seen.add(item.lower())
                parts.append(item)

        if not parts:
            return ""
        return " - ".join(parts[:2])

    def _stringify_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, dict):
            return self._stringify_mapping(value)
        if isinstance(value, list):
            parts = []
            for item in value:
                text = self._stringify_value(item)
                if text:
                    parts.append(text)
            return " ".join(parts)
        return self._clean_text(value)

    def _has_education_details(self, profile: dict[str, Any]) -> bool:
        return any(
            profile.get(field, "")
            for field in (
                "education",
                "degree",
                "branch_specialization",
                "branch",
                "college",
                "college_university",
                "university",
                "graduation_year",
            )
        )
