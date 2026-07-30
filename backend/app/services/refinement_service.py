import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from app.config import settings


class RefinementService:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="saiia-refine")
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._logger = logging.getLogger(self.__class__.__name__)
        self._timeout_seconds = settings.REFINEMENT_JOB_TIMEOUT_SECONDS

    def submit(
        self,
        *,
        run_refinement: Callable[[], str],
        refinement_provider: str,
        model: str,
    ) -> str:
        job_id = uuid.uuid4().hex
        created_at = time.time()

        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "pending",
                "refinement_provider": refinement_provider,
                "model": model,
                "created_at": created_at,
                "updated_at": created_at,
                "refined_answer": None,
                "error": None,
            }

        self._logger.info(
            "refinement_job job_id=%s provider=%s model=%s status=pending elapsed_ms=0 error=null",
            job_id,
            refinement_provider,
            model,
        )
        self._executor.submit(self._run_job, job_id, run_refinement)
        return job_id

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _run_job(self, job_id: str, run_refinement: Callable[[], str]) -> None:
        started = time.perf_counter()
        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, Exception] = {}
        finished = threading.Event()

        def worker() -> None:
            try:
                result_holder["answer"] = run_refinement()
            except Exception as exc:
                error_holder["error"] = exc
            finally:
                finished.set()

        threading.Thread(target=worker, name=f"refinement-worker-{job_id[:8]}", daemon=True).start()

        if not finished.wait(timeout=self._timeout_seconds):
            self._mark_failed(
                job_id=job_id,
                error_message="Groq refinement timed out",
                elapsed_ms=self._elapsed_ms(started),
            )
            return

        error = error_holder.get("error")
        if error is not None:
            self._mark_failed(
                job_id=job_id,
                error_message=self._safe_error_message(error),
                elapsed_ms=self._elapsed_ms(started),
            )
            return

        refined_answer = str(result_holder.get("answer", "")).strip()
        if not refined_answer:
            self._mark_failed(
                job_id=job_id,
                error_message="Groq refinement failed",
                elapsed_ms=self._elapsed_ms(started),
            )
            return

        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = "completed"
            job["refined_answer"] = refined_answer
            job["error"] = None
            job["updated_at"] = time.time()

        self._logger.info(
            "refinement_job job_id=%s provider=%s model=%s status=completed elapsed_ms=%s error=null",
            job_id,
            job["refinement_provider"],
            job["model"],
            self._elapsed_ms(started),
        )

    def _mark_failed(self, *, job_id: str, error_message: str, elapsed_ms: float) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = "failed"
            job["error"] = error_message
            job["updated_at"] = time.time()

        self._logger.warning(
            "refinement_job job_id=%s provider=%s model=%s status=failed elapsed_ms=%s error=%s",
            job_id,
            job["refinement_provider"],
            job["model"],
            elapsed_ms,
            error_message,
        )

    def _safe_error_message(self, error: Exception) -> str:
        message = str(error).lower()
        if "timed out" in message or "timeout" in message:
            return "Groq refinement timed out"
        if "401" in message or "403" in message or "invalid or missing" in message or "authentication" in message:
            return "Groq authentication failed"
        return "Groq refinement failed"

    def _elapsed_ms(self, started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 2)
