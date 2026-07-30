import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError
from rapidocr_onnxruntime import RapidOCR

MAX_SCREEN_IMAGE_BYTES = 10 * 1024 * 1024
MAX_OCR_DIMENSION = 2200
SUPPORTED_SCREEN_IMAGE_TYPES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
}
SUPPORTED_SCREEN_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/bmp",
}


class ScreenOcrError(Exception):
    """Raised when OCR extraction fails with a user-facing error."""


class ScreenOcrService:
    def __init__(self) -> None:
        self._engine: RapidOCR | None = None

    @property
    def engine(self) -> RapidOCR:
        if self._engine is None:
            self._engine = RapidOCR()
        return self._engine

    def extract_text(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        self._validate_upload(filename=filename, content=content, content_type=content_type)
        image = self._load_image(content)
        image = self._prepare_image(image)

        result, elapsed = self.engine(np.array(image))
        extracted_lines: list[str] = []
        confidence_values: list[float] = []

        for entry in result or []:
            if len(entry) < 3:
                continue
            text = str(entry[1] or "").strip()
            if not text:
                continue
            extracted_lines.append(text)
            try:
                confidence_values.append(float(entry[2]))
            except (TypeError, ValueError):
                continue

        extracted_text = self._normalize_text(extracted_lines)
        if not extracted_text:
            raise ScreenOcrError("Could not extract readable text.")

        average_confidence = (
            round(sum(confidence_values) / len(confidence_values), 4)
            if confidence_values
            else None
        )
        ocr_ms = round(sum(float(value) for value in (elapsed or [])) * 1000, 2)

        return {
            "status": "ok",
            "extracted_text": extracted_text,
            "confidence": average_confidence,
            "ocr_ms": ocr_ms,
            "text_length": len(extracted_text),
        }

    def _validate_upload(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> None:
        suffix = Path(filename or "").suffix.lower()
        normalized_content_type = (content_type or "").split(";")[0].strip().lower()

        if not content:
            raise ScreenOcrError("Could not capture screen.")
        if len(content) > MAX_SCREEN_IMAGE_BYTES:
            raise ScreenOcrError("Captured image is too large. Please try a smaller capture.")
        if suffix and suffix not in SUPPORTED_SCREEN_IMAGE_TYPES:
            raise ScreenOcrError("Unsupported image format.")
        if normalized_content_type and normalized_content_type not in SUPPORTED_SCREEN_CONTENT_TYPES:
            raise ScreenOcrError("Unsupported image format.")

    def _load_image(self, content: bytes) -> Image.Image:
        try:
            image = Image.open(io.BytesIO(content))
            image.load()
            return image
        except (UnidentifiedImageError, OSError) as exc:
            raise ScreenOcrError("Unsupported image format.") from exc

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        prepared = image.convert("RGB")
        prepared.thumbnail((MAX_OCR_DIMENSION, MAX_OCR_DIMENSION))
        return prepared

    def _normalize_text(self, lines: list[str]) -> str:
        normalized_lines = [self._clean_line(line) for line in lines]
        filtered_lines = [line for line in normalized_lines if line]
        return "\n".join(filtered_lines).strip()

    def _clean_line(self, value: Any) -> str:
        text = str(value or "").strip()
        return " ".join(text.split())
