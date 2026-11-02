"""Deterministic adapters for the isolated acceptance worker, never production."""

from pathlib import Path
from types import SimpleNamespace


def configure(app, config, staging):
    from app.api import generate, interview_sessions, resumes, screen_context
    from app.cloud.cloud_resume import CloudResumeError, CloudResumeService
    from app.models.screen_context import ScreenContextOutput
    from app.services.resume_index_service import ResumeIndexError, ResumeIndexService
    from app.services.screen_context_service import response_for
    from test_screen_context import output

    original = screen_context.get_screen_service()

    async def provider(request, _files):
        outcome = "reference_accepted" if request.action == "reference" else "answered"
        if request.identity.operationId == config["screen_failure_id"]:
            outcome = "failed"
        result = ScreenContextOutput.model_validate(
            output(request.model_dump(), outcome)
        )
        return response_for(request, result, original, logical_calls=1, http_attempts=1)

    screen_context.get_screen_service = lambda: SimpleNamespace(answer_context=provider)
    app.include_router(screen_context.router, prefix="/api/screen")

    class Parser:
        def extract_profile(self, **_):
            return {
                "profile": {
                    "full_name": "Synthetic candidate",
                    "professional_summary": "Builds synthetic software",
                },
                "parser_provider": "synthetic",
                "extracted_text_length": 25,
            }

    class Indexer(ResumeIndexService):
        def build_chunks_from_documents(self, documents):
            if "FAIL_INDEX" in str(documents):
                raise ResumeIndexError("synthetic index failure")
            return super().build_chunks_from_documents(documents)

    if staging:
        service = CloudResumeService(parser=Parser(), indexer=Indexer())
    else:
        import json

        import psycopg

        root = Path(config["local_blob_root"]).resolve()
        root.mkdir(parents=True, exist_ok=True)

        class Storage:
            def path(self, name):
                path = (root / name).resolve()
                if root not in path.parents:
                    raise CloudResumeError("local fixture path rejected")
                return path

            def upload_resume_object(self, name, data, _mime):
                path = self.path(name)
                if path.exists():
                    raise CloudResumeError("synthetic object already exists")
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as file:
                    file.write(data)

            def download_resume_object(self, name):
                return self.path(name).read_bytes()

            def delete_resume_object(self, name):
                self.path(name).unlink(missing_ok=True)

            def query(self, sql, parameters):
                # Disposable storage boundary only. Metadata/usage handlers still
                # use the restricted executor and existing ownership checks.
                with psycopg.connect(
                    host="127.0.0.1",
                    port=config["pg_port"],
                    dbname="postgres",
                    user="catalog_test_owner",
                ) as conn:
                    cursor = conn.execute(sql, parameters)
                    return cursor.fetchall() if cursor.description else None

            def insert_resume_chunks(self, chunks):
                for chunk in chunks:
                    self.query(
                        "INSERT INTO resume_chunks(user_id,resume_id,section,chunk_text,generation_id,metadata) SELECT x.user_id,x.resume_id,x.section,x.chunk_text,x.generation_id,x.metadata FROM jsonb_populate_record(null::resume_chunks,%s::jsonb) x",
                        (json.dumps(chunk),),
                    )

            def delete_resume_chunks(self, *, user_id, resume_id, generation_id=None):
                self.query(
                    "DELETE FROM resume_chunks WHERE user_id=%s AND resume_id=%s AND (%s::uuid IS NULL OR generation_id=%s::uuid)",
                    (user_id, resume_id, generation_id, generation_id),
                )

            def delete_inactive_resume_chunks(
                self, *, user_id, resume_id, active_generation_id
            ):
                self.query(
                    "DELETE FROM resume_chunks WHERE user_id=%s AND resume_id=%s AND generation_id<>%s",
                    (user_id, resume_id, active_generation_id),
                )

            def get_active_resume_chunk_counts(self, *, user_id, records):
                return {
                    (r.id, str(r.active_chunk_generation)): self.query(
                        "SELECT count(*) FROM resume_chunks WHERE user_id=%s AND resume_id=%s AND generation_id=%s",
                        (user_id, r.id, r.active_chunk_generation),
                    )[0][0]
                    for r in records
                }

        service = CloudResumeService(
            client=Storage(), parser=Parser(), indexer=Indexer()
        )
    resumes._cached_cloud_resume_service = lambda: service
    app.include_router(resumes.router, prefix="/api/resumes")

    class Notes:
        def generate(self, **_):
            return {
                "notes_markdown": "Synthetic acceptance notes",
                "provider": "synthetic",
                "model": "synthetic",
            }

    class Ask:
        def generate(self, **_):
            return {
                "answer_text": "Synthetic acceptance coaching",
                "provider": "synthetic",
                "model": "synthetic",
            }

    interview_sessions._cached_cloud_interview_notes_service = lambda: SimpleNamespace(
        _generator=Notes()
    )
    interview_sessions._cached_cloud_interview_ask_ai_service = lambda: SimpleNamespace(
        _generator=Ask()
    )
    interview_sessions._trigger_feature_email = lambda **_: None
    app.include_router(generate.router, prefix="/generate")

    from app.commercial.subscription_execution import SubscriptionTurns
    from app.session_generation import TurnStateError

    original_operation = SubscriptionTurns.operation
    failed = False

    async def checkpoint_fault(self, action, identity, *args, **kwargs):
        nonlocal failed
        if (
            config["http_port"] == 18765
            and action == "complete"
            and identity["p_request_id"] == config["manual_recovery_id"]
            and not failed
        ):
            failed = True
            raise TurnStateError("persistence_unavailable")
        return await original_operation(self, action, identity, *args, **kwargs)

    SubscriptionTurns.operation = checkpoint_fault
