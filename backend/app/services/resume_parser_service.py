import logging
from typing import Any

from app.config import settings
from app.nlp.answer_generator import ProviderError
from app.services.affinda_resume_parser import AffindaResumeParser, AffindaResumeParserError
from app.services.resume_service import ResumeService

logger = logging.getLogger("resume_parser_service")


class ResumeParserService:
    def __init__(self) -> None:
        self.resume_service = ResumeService()
        self.affinda_parser = AffindaResumeParser(self.resume_service)

    def extract_profile(self, *, filename: str, content: bytes) -> dict[str, Any]:
        resume_text = self.resume_service.extract_text(filename=filename, content=content)
        requested_provider = settings.RESUME_PARSER_PROVIDER or "local"
        fallback_provider = settings.RESUME_PARSER_FALLBACK or "local"

        if requested_provider == "affinda":
            return self._extract_with_affinda(
                filename=filename,
                content=content,
                resume_text=resume_text,
                fallback_provider=fallback_provider,
            )

        local_profile = self.resume_service.build_profile_fields(resume_text)
        return self._build_result(
            profile=local_profile,
            parser_provider="local",
            fallback_used=False,
            fallback_message="",
            extracted_text_length=len(resume_text),
        )

    def _extract_with_affinda(
        self,
        *,
        filename: str,
        content: bytes,
        resume_text: str,
        fallback_provider: str,
    ) -> dict[str, Any]:
        try:
            affinda_profile = self.affinda_parser.parse(
                filename=filename,
                content=content,
                resume_text=resume_text,
            )
        except AffindaResumeParserError as exc:
            logger.warning("Affinda parsing unavailable, using local extraction instead: %s", exc)
            if fallback_provider == "local":
                local_profile = self.resume_service.build_profile_fields(resume_text)
                return self._build_result(
                    profile=local_profile,
                    parser_provider="local",
                    fallback_used=True,
                    fallback_message="Affinda parsing unavailable, local extraction used.",
                    extracted_text_length=len(resume_text),
                )
            raise ProviderError(str(exc)) from exc

        missing_fields = self.resume_service.get_missing_fields(affinda_profile)
        if self._needs_local_completion(affinda_profile, missing_fields) and fallback_provider == "local":
            try:
                local_profile = self.resume_service.build_profile_fields(resume_text)
                return self._build_result(
                    profile=local_profile,
                    parser_provider="local",
                    fallback_used=True,
                    fallback_message="Affinda parsing unavailable, local extraction used.",
                    extracted_text_length=len(resume_text),
                )
            except ProviderError as exc:
                logger.warning(
                    "Affinda parse was incomplete and local fallback was unavailable. Returning Affinda result only: %s",
                    exc,
                )

        return self._build_result(
            profile=affinda_profile,
            parser_provider="affinda",
            fallback_used=False,
            fallback_message="",
            extracted_text_length=len(resume_text),
        )

    def _needs_local_completion(self, profile: dict[str, Any], missing_fields: list[str]) -> bool:
        if not missing_fields:
            return False

        high_value_fields = {
            "full_name",
            "education",
            "degree",
            "top_skills",
            "projects_or_experience",
        }
        if any(field in high_value_fields for field in missing_fields):
            return True

        return bool(profile.get("manual_review_required"))

    def _build_result(
        self,
        *,
        profile: dict[str, Any],
        parser_provider: str,
        fallback_used: bool,
        fallback_message: str,
        extracted_text_length: int,
    ) -> dict[str, Any]:
        missing_fields = self.resume_service.get_missing_fields(profile)
        review_required = bool(profile.get("manual_review_required")) or bool(missing_fields)

        result = {
            "parser_provider": parser_provider,
            "fallback_used": fallback_used,
            "fallback_message": fallback_message,
            "warning": fallback_message or (
                "Some resume fields may need manual review." if review_required else None
            ),
            "missing_fields": missing_fields,
            "review_required": review_required,
            "profile": profile,
            "manual_review_required": review_required,
            "manual_review_message": (
                profile.get("manual_review_message")
                or ("Some resume fields may need manual review." if review_required else "")
            ),
            "extraction_confidence": profile.get("extraction_confidence", ""),
            "extracted_text_length": extracted_text_length,
        }
        result.update(profile)
        return result
