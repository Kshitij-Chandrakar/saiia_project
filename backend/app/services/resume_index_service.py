import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any


class ResumeIndexError(Exception):
    """Raised when resume indexing or retrieval fails."""


class ResumeIndexService:
    def __init__(self) -> None:
        self.index_path = Path(__file__).resolve().parents[3] / "tmp" / "resume_index.json"
        self.stop_words = {
            "a",
            "about",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "by",
            "for",
            "from",
            "have",
            "i",
            "in",
            "is",
            "it",
            "me",
            "my",
            "of",
            "on",
            "or",
            "our",
            "that",
            "the",
            "their",
            "them",
            "to",
            "we",
            "with",
            "you",
            "your",
        }

    def build_index(self, profile: dict[str, Any]) -> dict[str, Any]:
        chunks = self.build_chunks(profile)
        if not chunks:
            raise ResumeIndexError(
                "Could not build a resume index because there is no usable resume/profile text yet."
            )

        payload = {
            "indexed": True,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "chunk_count": len(chunks),
            "chunks": chunks,
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def get_status(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {
                "indexed": False,
                "chunk_count": 0,
                "updated_at": None,
                "needs_rebuild": False,
            }

        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ResumeIndexError("Resume index is unreadable. Please rebuild the index.") from exc

        return {
            "indexed": bool(payload.get("chunks")),
            "chunk_count": len(payload.get("chunks", [])),
            "updated_at": payload.get("updated_at"),
            "needs_rebuild": False,
        }

    def delete_index(self) -> dict[str, Any]:
        if self.index_path.exists():
            self.index_path.unlink()
        return {
            "indexed": False,
            "chunk_count": 0,
            "updated_at": None,
            "needs_rebuild": False,
        }

    def retrieve(self, *, question: str, category: str, limit: int = 3) -> dict[str, Any]:
        started = time.perf_counter()
        if not self.index_path.exists():
            return {
                "retrieval_used": False,
                "retrieved_chunk_count": 0,
                "retrieved_chunks": [],
                "retrieval_ms": round((time.perf_counter() - started) * 1000, 2),
            }

        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ResumeIndexError("Resume index is unreadable. Please rebuild the index.") from exc

        chunks = payload.get("chunks", [])
        if not chunks:
            return {
                "retrieval_used": False,
                "retrieved_chunk_count": 0,
                "retrieved_chunks": [],
                "retrieval_ms": round((time.perf_counter() - started) * 1000, 2),
            }

        return self.retrieve_from_chunks(chunks, question=question, category=category, limit=limit, started=started)

    def build_chunks(self, profile: dict[str, Any], *, include_raw_resume_text: bool = True) -> list[dict[str, Any]]:
        documents = self._profile_documents(profile, include_raw_resume_text=include_raw_resume_text)
        if not documents:
            return []
        return self._chunk_documents(documents)

    def build_chunks_from_documents(self, documents: list[dict[str, str]]) -> list[dict[str, Any]]:
        return self._chunk_documents(documents)

    def retrieve_from_chunks(
        self,
        chunks: list[dict[str, Any]],
        *,
        question: str,
        category: str,
        limit: int = 3,
        started: float | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter() if started is None else started
        if not chunks:
            return {
                "retrieval_used": False,
                "retrieved_chunk_count": 0,
                "retrieved_chunks": [],
                "retrieval_ms": round((time.perf_counter() - started) * 1000, 2),
            }

        query_tokens = self._tokenize(question)
        category_tokens = self._tokenize(category)

        scored_chunks = []
        for chunk in chunks:
            chunk_tokens = chunk.get("tokens", [])
            score = self._score_chunk(
                query_tokens=query_tokens,
                category_tokens=category_tokens,
                chunk_tokens=chunk_tokens,
                section=chunk.get("section", ""),
            )
            if score <= 0:
                continue
            scored_chunks.append((score, chunk))

        scored_chunks.sort(key=lambda item: item[0], reverse=True)
        top_chunks = [chunk for _, chunk in scored_chunks[:limit]]

        return {
            "retrieval_used": bool(top_chunks),
            "retrieved_chunk_count": len(top_chunks),
            "retrieved_chunks": [
                {
                    "chunk_id": chunk["chunk_id"],
                    "source": chunk["source"],
                    "section": chunk["section"],
                    "text": chunk["text"],
                    "preview": chunk["preview"],
                }
                for chunk in top_chunks
            ],
            "retrieval_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def _profile_documents(self, profile: dict[str, Any], *, include_raw_resume_text: bool = True) -> list[dict[str, str]]:
        documents = []
        profile_fields = [
            ("full_name", profile.get("full_name", "")),
            ("professional_summary", profile.get("professional_summary", "")),
            ("resume", profile.get("resume", "")),
            ("top_skills", profile.get("top_skills", "")),
            ("technical_skills", profile.get("technical_skills", "")),
            ("soft_skills", profile.get("soft_skills", "")),
            ("tools_frameworks", profile.get("tools_frameworks", "")),
            ("skills", profile.get("skills", "")),
            ("projects", profile.get("projects", "")),
            ("experience", profile.get("experience", "")),
            ("education", profile.get("education", "")),
            ("degree", profile.get("degree", "")),
            ("branch", profile.get("branch", "")),
            ("branch_specialization", profile.get("branch_specialization", "")),
            ("college", profile.get("college", "")),
            ("college_university", profile.get("college_university", "")),
            ("university", profile.get("university", "")),
            ("graduation_year", profile.get("graduation_year", "")),
            ("work_experience", profile.get("work_experience", "")),
            ("achievements", profile.get("achievements", "")),
            ("certifications", profile.get("certifications", "")),
        ]
        if include_raw_resume_text:
            profile_fields.append(("raw_resume_text", profile.get("raw_resume_text", "")))
        for section, value in profile_fields:
            cleaned = self._clean_text(str(value or ""))
            if cleaned:
                documents.append({"section": section, "text": cleaned})
        return documents

    def _chunk_documents(self, documents: list[dict[str, str]]) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        chunk_index = 1

        for document in documents:
            section = document["section"]
            paragraphs = [segment.strip() for segment in document["text"].splitlines() if segment.strip()]
            if not paragraphs:
                paragraphs = [document["text"]]

            for paragraph in paragraphs:
                units = self._split_to_units(paragraph)
                current = ""
                for unit in units:
                    proposed = f"{current} {unit}".strip() if current else unit
                    if len(proposed) <= 320:
                        current = proposed
                        continue

                    if current:
                        chunks.append(self._make_chunk(chunk_index, section, current))
                        chunk_index += 1
                    current = unit

                if current:
                    chunks.append(self._make_chunk(chunk_index, section, current))
                    chunk_index += 1

        return chunks

    def _make_chunk(self, chunk_index: int, section: str, text: str) -> dict[str, Any]:
        cleaned = self._clean_text(text)
        preview = cleaned[:120] + ("..." if len(cleaned) > 120 else "")
        return {
            "chunk_id": f"resume-{chunk_index}",
            "source": "resume",
            "section": section,
            "text": cleaned,
            "preview": preview,
            "tokens": self._tokenize(cleaned),
        }

    def _split_to_units(self, text: str) -> list[str]:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        return sentences or [text.strip()]

    def _score_chunk(
        self,
        *,
        query_tokens: list[str],
        category_tokens: list[str],
        chunk_tokens: list[str],
        section: str,
    ) -> float:
        if not chunk_tokens:
            return 0.0

        query_counter = Counter(query_tokens)
        chunk_counter = Counter(chunk_tokens)
        overlap = sum(min(query_counter[token], chunk_counter[token]) for token in query_counter)
        norm = math.sqrt(len(query_tokens) * len(chunk_tokens)) if query_tokens else 1.0
        score = (overlap / norm) if overlap > 0 else 0.0

        section_weights = {
            "technical": {
                "projects": 0.45,
                "technical_skills": 0.4,
                "tools_frameworks": 0.35,
                "skills": 0.3,
                "experience": 0.3,
                "work_experience": 0.25,
            },
            "behavioral": {
                "experience": 0.45,
                "work_experience": 0.35,
                "projects": 0.25,
                "achievements": 0.25,
            },
            "resume-based": {
                "professional_summary": 0.4,
                "resume": 0.3,
                "projects": 0.25,
                "experience": 0.25,
                "work_experience": 0.25,
            },
            "hr": {
                "professional_summary": 0.35,
                "resume": 0.25,
                "projects": 0.2,
                "education": 0.2,
                "degree": 0.15,
                "achievements": 0.15,
            },
        }

        category_key = " ".join(category_tokens)
        for known_category, weights in section_weights.items():
            if known_category in category_key:
                score += weights.get(section, 0)
                break

        if section in {"skills", "top_skills", "technical_skills", "tools_frameworks"} and any(
            token in {"fastapi", "python", "react", "mongo", "mongodb", "tensorflow", "pytorch"}
            for token in query_tokens
        ):
            score += 0.25
        if section in {"experience", "work_experience", "projects"} and any(
            token in {"bug", "debug", "challenge", "difficult"}
            for token in query_tokens
        ):
            score += 0.25
        if "yourself" in query_tokens and section in {
            "professional_summary",
            "resume",
            "projects",
            "experience",
            "education",
            "degree",
        }:
            score += 0.35
        if section in {"experience", "work_experience", "projects", "achievements"} and any(
            token in {"bug", "difficult", "challenge", "problem", "debug"}
            for token in query_tokens
        ):
            score += 0.2
        if section in {"experience", "work_experience", "projects"} and any(
            token.startswith("debug") or token in {"issue", "problem", "troubleshooting", "workflow"}
            for token in chunk_tokens
        ) and any(token in {"bug", "difficult", "challenge", "problem"} for token in query_tokens):
            score += 0.25
        if any(token in {"project", "projects"} for token in query_tokens) and section == "projects":
            score += 0.35
        if any(token in {"education", "degree", "college", "qualification"} for token in query_tokens) and section in {
            "education",
            "degree",
            "branch_specialization",
            "college_university",
            "graduation_year",
        }:
            score += 0.3

        if score <= 0:
            return 0.0

        return round(score, 4)

    def _tokenize(self, text: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9+#]+", text.lower())
        return [token for token in tokens if token not in self.stop_words and len(token) > 1]

    def _clean_text(self, text: str) -> str:
        lines = [line.strip() for line in str(text or "").splitlines()]
        return "\n".join(line for line in lines if line).strip()
