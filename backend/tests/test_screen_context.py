"""Synthetic images and mocked SDK transport; no paid provider calls."""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import httpx
import anyio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import screen_context as api
from app.api.screen_ocr import router
from app.auth.supabase_auth import CurrentUser
from app.config import settings
from app.models.screen_context import ScreenContextRequest, ScreenContextProviderOutput, OUTCOME_RULES, MAX_IMAGE_BYTES, MAX_BODY_BYTES
from app.services import screen_context_service as service
from app.services.screen_vision_service import ScreenVisionService


def png(number=0, size=(60, 40)):
    with Image.new("RGB", size, (number, 20, 30)) as image, io.BytesIO() as output:
        image.save(output, format="PNG")
        return output.getvalue()


def context(count=1):
    raw = [png(n) for n in range(count)]
    hashes = [hashlib.sha256(item).hexdigest() for item in raw]
    body = {
        "contractVersion": "1", "sourceType": "screen_capture", "action": "new" if count == 1 else "continue",
        "identity": {"runtimeSessionId": "runtime", "generation": 2, "accountGeneration": None,
                     "cloudSessionId": None, "threadId": "thread", "turnId": "current-turn",
                     "operationId": "operation", "requestId": "attempt", "baseRevision": count - 1},
        "input": {"images": [{"imageHash": h, "role": "current" if n == count - 1 else "prior", "part": f"image_{n}"}
                             for n, h in enumerate(hashes)], "currentImageHash": hashes[-1],
                  "evidence": [{"text": f"source {n}: def solve(x):\n    return x", "complete": False,
                                "imageHash": h, "turnId": f"old-{n}"} for n, h in enumerate(hashes[:-1])], "answers": []},
    }
    return body, {f"image_{n}": item for n, item in enumerate(raw)}


def output(body, outcome="answered", **overrides):
    data = {
        "outcome": outcome,
        "evidenceDelta": {"text": "Observed constraints: n <= 1000\n    exact code whitespace", "complete": outcome == "answered",
                          "imageHashes": [item["imageHash"] for item in body["input"]["images"]],
                          "replacesTurnIds": body.get("replacesTurnIds", [])},
        "items": [{"index": 1, "display_number": "", "question": "Explain the diagram", "question_type": "visual",
                   "answer": "A grounded answer", "language": "", "code": ""}] if outcome == "answered" else [],
        "missingDetails": ["Capture the remaining input constraints"] if outcome == "needs_more_content" else [],
        "conflicts": [], "clarification": None,
    }
    if outcome in {"needs_clarification", "failed"}:
        data["evidenceDelta"] = None
    if outcome == "needs_clarification":
        data["clarification"] = "Does the new code replace the old implementation?"
        data["conflicts"] = ["Two different implementations are visible"]
    return {**data, **overrides}


@pytest.fixture
def provider(monkeypatch):
    calls, closed = [], []
    state = {"value": None, "status": "completed", "refusal": False, "error": None, "text": None}

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.responses = self
            assert kwargs["max_retries"] == 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            closed.append(True)

        async def create(self, **kwargs):
            calls.append(kwargs)
            action = json.loads(kwargs["input"][0]["content"][0]["text"].split("\n", 1)[1])["action"]
            assert kwargs["text"]["format"]["type"] == "json_schema" and kwargs["text"]["format"]["strict"] is True
            assert kwargs["text"]["format"]["schema"] == ScreenContextProviderOutput.schema_for_action(action)
            for hook in self.kwargs["http_client"].event_hooks["request"]:
                await hook(None)
            if state["error"]:
                raise state["error"]
            value = state["value"]
            if callable(value):
                value = value(kwargs)
            text = value if isinstance(value, str) else json.dumps({"result": value}, ensure_ascii=False)
            return SimpleNamespace(status=state["status"], output_text=state["text"] or text,
                                   incomplete_details=SimpleNamespace(reason=state.get("incomplete_reason")),
                                   output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])] if state["refusal"] else [])

    monkeypatch.setattr(service, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "mock-only")
    monkeypatch.setattr(settings, "SCREEN_VISION_PROVIDER", "openai")
    monkeypatch.setattr(settings, "SCREEN_VISION_MODEL", "gpt-5-nano-2025-08-07")
    monkeypatch.setattr(settings, "SCREEN_VISION_MAX_OUTPUT_TOKENS", 1800)
    return state, calls, closed


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        yield client


def post(client, body, files, headers=None):
    return client.post("/api/screen/analyze-context", data={"context": json.dumps(body)},
                       files=[(name, ("ignored.png", data, "image/png")) for name, data in files.items()], headers=headers)


def test_three_images_diagram_and_fallible_answers_separated_in_one_call(client, provider):
    body, files = context(3)
    body["input"]["answers"] = [{"turnId": "old-0", "text": "FALLIBLE_PREVIOUS_ANSWER"}]
    provider[0]["value"] = output(body)
    response = post(client, body, files)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["identity"] == body["identity"]
    assert result["controllerResult"]["validated"] is True
    assert result["metrics"] == {"logicalScreenCalls": 1, "httpAttempts": 1, "sdkMaxRetries": 0,
                                  "imagesSupplied": 3, "newCaptureCount": 1}
    assert len(provider[1]) == 1 and provider[2]
    call = provider[1][0]
    assert call["store"] is False and call["model"] == settings.SCREEN_VISION_MODEL
    content = call["input"][0]["content"]
    actual_hashes = [part["text"].split()[2].rstrip(";") for part in content if part.get("text", "").startswith("Source image")]
    assert actual_hashes == [item["imageHash"] for item in body["input"]["images"]]
    assert sum(part["type"] == "input_image" for part in content) == 3
    assert "FALLIBLE_PREVIOUS_ANSWER" not in content[0]["text"]
    assert "fallible; not observed evidence" in content[-1]["text"]
    assert "FALLIBLE_PREVIOUS_ANSWER" in content[-1]["text"]
    assert "    return x" in json.loads(content[0]["text"].split("\n", 1)[1])["sourceEvidence"][0]["text"]
    assert "not source facts" in call["instructions"] and "diagram" in call["instructions"]


def test_bound_user_clarification_is_separate_from_source_and_still_cannot_commit(client, provider):
    body, files = context()
    body["clarificationResponse"] = {"requestId": "previous-attempt", "threadId": "thread", "turnId": "current-turn",
                                     "text": "PRIVATE_CLARIFICATION use the corrected implementation"}
    provider[0]["value"] = output(body, "needs_clarification")
    response = post(client, body, files)
    assert response.status_code == 200
    assert response.json()["committable"] is False
    assert response.json()["controllerResult"] is None
    content = provider[1][0]["input"][0]["content"]
    assert "PRIVATE_CLARIFICATION" not in content[0]["text"]
    clarification = [part["text"] for part in content if part.get("text", "").startswith("USER CLARIFICATION")]
    assert len(clarification) == 1 and "PRIVATE_CLARIFICATION" in clarification[0]
    assert "PRIVATE_CLARIFICATION" not in content[-1]["text"]


@pytest.mark.parametrize("field,value", [("threadId", "other"), ("turnId", "other"), ("requestId", "attempt"),
                                         ("requestId", "../unsafe"), ("text", ""), ("text", "   "), ("text", "x" * 2001)],
                         ids=["thread", "turn", "same-attempt", "unsafe-id", "empty", "blank", "over-limit"])
def test_clarification_binding_and_length_reject_before_model(client, provider, field, value):
    body, files = context()
    body["clarificationResponse"] = {"requestId": "previous-attempt", "threadId": "thread", "turnId": "current-turn", "text": "Use corrected code"}
    body["clarificationResponse"][field] = value
    assert post(client, body, files).status_code == 422
    assert not provider[1]


@pytest.mark.parametrize("outcome", ["needs_more_content", "needs_clarification", "failed"])
def test_structured_non_answer_outcomes(client, provider, outcome):
    body, files = context()
    provider[0]["value"] = output(body, outcome)
    result = post(client, body, files).json()
    assert result["outcome"] == outcome
    assert result["answer"] == "" and not result["items"]
    assert result["committable"] is (outcome == "needs_more_content")
    if outcome == "needs_more_content":
        assert "answer" not in result["controllerResult"]
        assert result["controllerResult"]["evidence"]["complete"] is False
        assert result["missingDetails"]
    else:
        assert result["controllerResult"] is None and result["evidenceDelta"] is None


def test_repeated_capture_uses_one_uploaded_image_and_new_logical_turn(client, provider):
    body, files = context(2)
    body["input"]["images"] = [{**body["input"]["images"][0], "role": "prior_current"}]
    body["input"]["currentImageHash"] = body["input"]["images"][0]["imageHash"]
    files.pop("image_1")
    provider[0]["value"] = output(body)
    result = post(client, body, files)
    assert result.status_code == 200
    assert result.json()["metrics"]["imagesSupplied"] == 1


def test_ambiguous_batch_clarifies_without_provider_and_selected_item_is_owned_by_app(client, provider):
    body, files = context(2)
    body["input"]["answers"] = [{"turnId": "old-0", "text": "Two independent answers"}]
    body["priorItems"] = [{"turnId": "old-0", "index": n, "questionId": f"old-0:{n}"} for n in [1, 2]]
    response = post(client, body, files).json()
    assert response["outcome"] == "needs_clarification" and not response["committable"]
    assert response["metrics"]["logicalScreenCalls"] == 0 and not provider[1]
    body["targetQuestionId"] = "old-0:2"
    provider[0]["value"] = output(body)
    response = post(client, body, files).json()
    assert response["items"][0]["question_id"] == "old-0:2"


def test_batch_stays_separate_and_ordered(client, provider):
    body, files = context()
    value = output(body)
    value["items"] = [{**value["items"][0], "index": n, "question_type": "mcq", "display_number": str(n + 6),
                       "answer": f"b. option {n}"} for n in [1, 2]]
    provider[0]["value"] = value
    result = post(client, body, files).json()
    assert [item["question_id"] for item in result["items"]] == ["current-turn:1", "current-turn:2"]
    assert result["answer"] == "7. b. option 1\n8. b. option 2"


def test_explicit_replacement_and_unresolved_conflict(client, provider):
    body, files = context(2)
    body["replacesTurnIds"] = ["old-0"]
    provider[0]["value"] = output(body)
    assert post(client, body, files).json()["evidenceDelta"]["replacesTurnIds"] == ["old-0"]
    body["replacesTurnIds"] = []
    provider[0]["value"] = output(body, "needs_clarification")
    result = post(client, body, files).json()
    assert result["conflicts"] and not result["committable"]
    assert "do not silently choose latest wins" in provider[1][-1]["instructions"]


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(action="new"),
    lambda b: b["identity"].update(baseRevision=99),
    lambda b: b["identity"].update(generation=-1),
    lambda b: b["identity"].update(user_id="untrusted-user"),
    lambda b: b["input"]["images"][0].update(role="current"),
    lambda b: b["input"]["images"][0].update(part="/server/path"),
    lambda b: b["input"]["images"][0].update(url="https://private.example/image"),
    lambda b: b.update(targetQuestionId="unknown-item"),
    lambda b: b.update(replacesTurnIds=["unknown-turn"]),
    lambda b: b["input"]["evidence"][0].update(text="x" * 24001),
    lambda b: b["input"]["evidence"][0].update(text="   "),
    lambda b: b["input"]["images"].reverse(),
    lambda b: b["input"]["images"].append(b["input"]["images"][0]),
])
def test_invalid_context_is_private_and_rejected_before_provider(client, provider, mutation):
    body, files = context(2)
    mutation(body)
    response = post(client, body, files)
    assert response.status_code == 422
    expected = "context_field_limit" if len(body["input"]["evidence"][0]["text"]) > 24000 else "invalid_context"
    assert response.json()["detail"]["code"] == expected
    assert "source 0" not in response.text
    assert not provider[1]


@pytest.mark.parametrize("case,expected", [("malformed", "invalid_output"), ("truncated", "incomplete_output"),
    ("refused", "provider_refused"), ("overflow", "output_limit"), ("exception", "provider_error"),
    ("wrong_ref", "invalid_output"), ("wrong_order", "invalid_output"), ("bad_outcome", "invalid_output")])
def test_provider_failures_never_commit_or_expose_payload(client, provider, case, expected):
    body, files = context()
    state = provider[0]
    state["value"] = output(body)
    if case == "malformed": state["value"] = '{"PRIVATE"'
    if case == "truncated": state["status"] = "incomplete"
    if case == "refused": state["refusal"] = True
    if case == "overflow": state["text"] = "PRIVATE" * 12000
    if case == "exception": state["error"] = RuntimeError("PRIVATE provider details")
    if case == "wrong_ref": state["value"]["evidenceDelta"]["imageHashes"] = ["0" * 64]
    if case == "wrong_order": state["value"]["items"][0]["index"] = 2
    if case == "bad_outcome": state["value"]["outcome"] = "needs_more_content"
    result = post(client, body, files).json()
    assert result["outcome"] == "failed" and result["committable"] is False
    assert result["errorCode"] == expected and result["controllerResult"] is None
    assert "PRIVATE" not in json.dumps(result)
    assert len(provider[1]) == 1 and provider[2]


@pytest.mark.parametrize("raw,code", [(b"corrupt", "invalid_image"), (png(size=(2201, 1)), "image_pixel_limit"),
    (b"x" * (MAX_IMAGE_BYTES + 1), "multipart_limit")], ids=["corrupt", "pixels", "bytes"])
def test_image_validation_precedes_provider(client, provider, raw, code):
    body, files = context()
    body["input"]["images"][0]["imageHash"] = hashlib.sha256(raw).hexdigest()
    body["input"]["currentImageHash"] = body["input"]["images"][0]["imageHash"]
    response = post(client, body, {"image_0": raw})
    assert response.status_code in {413, 422}
    assert response.json()["detail"]["code"] == code
    assert not provider[1]


def test_hash_missing_part_unsupported_type_and_body_limit(client, provider):
    body, files = context()
    assert post(client, body, {"image_0": png(9)}).json()["detail"]["code"] == "image_hash_mismatch"
    assert post(client, body, {"image_1": files["image_0"]}).json()["detail"]["code"] == "image_parts_mismatch"
    response = client.post("/api/screen/analyze-context", data={"context": json.dumps(body)},
                           files={"image_0": ("image.gif", b"not image", "image/gif")})
    assert response.status_code == 415
    assert post(client, body, files, {"Content-Length": str(MAX_BODY_BYTES + 1)}).status_code == 413
    assert not provider[1]


def test_cloud_ownership_active_status_and_invalid_auth_never_downgrade(client, provider, monkeypatch):
    body, files = context()
    body["identity"].update(cloudSessionId="30000000-0000-4000-8000-000000000001", accountGeneration=1)
    assert post(client, body, files).status_code == 401
    monkeypatch.setattr(api, "get_current_user", lambda _request: CurrentUser(user_id="verified-owner"))
    calls = []
    record = SimpleNamespace(status="active", ended_at=None)

    class Sessions:
        def get_session(self, **kwargs):
            calls.append(kwargs)
            if record.status == "missing": raise api.CloudInterviewSessionNotFoundError("private")
            return record

    monkeypatch.setattr(api, "CloudInterviewSessionService", Sessions)
    provider[0]["value"] = output(body)
    assert post(client, body, files, {"Authorization": "Bearer fake"}).status_code == 200
    assert calls[0] == {"user_id": "verified-owner", "session_id": body["identity"]["cloudSessionId"], "allow_model_bound": True}
    for status in ["ended", "abandoned", "missing"]:
        record.status = status
        assert post(client, body, files, {"Authorization": "Bearer fake"}).status_code == (404 if status == "missing" else 409)
    monkeypatch.setattr(api, "get_current_user", lambda _request: (_ for _ in ()).throw(HTTPException(401, "Invalid authentication credentials.")))
    body["identity"]["cloudSessionId"] = None
    assert post(client, body, files, {"Authorization": "Bearer invalid"}).status_code == 401
    assert len(provider[1]) == 1


def test_remote_local_request_denied_and_openapi_documents_additive_route(client, provider):
    body, files = context()
    with TestClient(client.app, client=("203.0.113.8", 1234)) as remote:
        assert post(remote, body, files).status_code == 403
    schema = client.get("/openapi.json").json()
    assert "/api/screen/analyze-active-window-answer" in schema["paths"]
    assert "multipart/form-data" in schema["paths"]["/api/screen/analyze-context"]["post"]["requestBody"]["content"]
    assert not provider[1]


@pytest.mark.asyncio
async def test_disconnection_cancels_provider_and_finally_runs():
    closed = []

    async def blocked():
        try:
            await asyncio.sleep(60)
        finally:
            closed.append(True)

    async def is_disconnected(): return True
    with pytest.raises(HTTPException) as error:
        await api.run_until_disconnect(SimpleNamespace(is_disconnected=is_disconnected), blocked())
    assert error.value.status_code == 499 and closed


@pytest.mark.parametrize("outcome", ["needs_more_content", "answered", "reference_accepted"])
def test_phase1_snapshot_to_request_and_result_back_to_real_controller(client, provider, outcome):
    module = Path(__file__).resolve().parents[2] / "frontend/electron/screen_context_controller.cjs"
    script = """
let nextId=0; require('node:crypto').randomUUID=()=>`test-id-${++nextId}`;
const {createScreenContextController}=require(process.argv[1]);
const c=createScreenContextController({inspectImage:()=>({width:60,height:40})});
c.adoptSession({runtimeSessionId:'runtime'});
const t=c.begin({action:'new'});
c.registerImage(t,Buffer.from(process.argv[2],'base64'));
console.log(JSON.stringify(c.prepareRequest(t)));
"""
    if outcome == "reference_accepted":
        script = script.replace("action:'new'", "action:'reference'")
    import base64
    snapshot = json.loads(subprocess.check_output(["node", "-e", script, str(module), base64.b64encode(png()).decode()], text=True))
    body, files = context()
    body["identity"] = snapshot["identity"]
    assert snapshot["input"]["currentImageHash"] == body["input"]["currentImageHash"]
    if outcome == "reference_accepted":
        body.update(action="reference", contextKind="reference")
    provider[0]["value"] = output(body, outcome)
    response = post(client, body, files).json()
    commit = "commitAnswer" if outcome == "answered" else "commitEvidence"
    executor = module.with_name("screen_context_execution.cjs")
    script += f"const r=JSON.parse(process.argv[3]); require({json.dumps(str(executor))}).validateResponse(r,c.prepareRequest(t)); c.{commit}(t,r.controllerResult); console.log(JSON.stringify(c.metadata()));"
    lines = subprocess.check_output(["node", "-e", script, str(module), base64.b64encode(png()).decode(),
                                     json.dumps(response)], text=True).splitlines()
    metadata = json.loads(lines[-1])
    assert metadata["evidenceCount"] == metadata["acceptedImageCount"] == metadata["revision"] == 1
    assert metadata["status"] == ("answered" if outcome == "answered" else "collecting")


def test_no_unrelated_retrieval_or_persistence_calls():
    source = Path(service.__file__).read_text()
    for forbidden in ["save_debug", "interview_ask_ai", "interview_transcripts", "resume_index", "job_context", "previous_response_id", "conversation="]:
        assert forbidden not in source


def test_safe_validation_diagnostics_never_include_private_values_or_unknown_keys(client, provider, caplog, monkeypatch):
    monkeypatch.setenv("SAIIA_DEV_SCREEN_CONTEXT_DIAGNOSTICS", "1")
    body, files = context()
    value = output(body)
    value["items"][0]["PRIVATE_FIELD_NAME"] = "PRIVATE_ANSWER_OR_SOURCE"
    provider[0]["value"] = value
    with caplog.at_level("INFO", logger=service.__name__):
        response = post(client, body, files)
    assert response.status_code == 200
    assert response.json()["outcome"] == "failed"
    assert response.json()["errorCode"] == "invalid_output"
    assert "extra_forbidden" in caplog.text and "items.[].<unknown>" in caplog.text
    assert "status=completed" in caplog.text and "outcome=failed" in caplog.text
    assert "PRIVATE_FIELD_NAME" not in caplog.text and "PRIVATE_ANSWER_OR_SOURCE" not in caplog.text


@pytest.mark.parametrize("case,path", [
    ("evidence_presence", "evidenceDelta"), ("evidence_complete", "evidenceDelta.complete"),
    ("evidence_blank", "evidenceDelta.text"), ("items_presence", "items"),
    ("missing_details_presence", "missingDetails"), ("conflicts_forbidden", "conflicts"),
    ("clarification_presence", "clarification"), ("question_blank", "items.[].question"),
    ("answer_blank", "items.[].answer"), ("item_order", "items.[].index"),
    ("coding_code_missing", "items.[].code"), ("coding_language_missing", "items.[].language"),
])
def test_cross_field_provider_failure_identifies_exact_safe_rule(client, provider, caplog, monkeypatch, case, path):
    monkeypatch.delenv("SAIIA_DEV_SCREEN_CONTEXT_DIAGNOSTICS", raising=False)
    body, files = context()
    value = output(body)
    value["items"][0]["question"] = "PRIVATE_SOURCE"
    value["items"][0]["answer"] = "PRIVATE_ANSWER"
    if case == "evidence_presence": value["evidenceDelta"] = None
    elif case == "evidence_complete": value["evidenceDelta"]["complete"] = False
    elif case == "evidence_blank": value["evidenceDelta"]["text"] = " "
    elif case == "items_presence": value["items"] = []
    elif case == "missing_details_presence": value["missingDetails"] = ["PRIVATE_DETAIL"]
    elif case == "conflicts_forbidden": value["conflicts"] = ["PRIVATE_CONFLICT"]
    elif case == "clarification_presence": value["clarification"] = "PRIVATE_CLARIFICATION"
    elif case == "question_blank": value["items"][0]["question"] = " "
    elif case == "answer_blank": value["items"][0]["answer"] = " "
    elif case == "item_order": value["items"][0]["index"] = 2
    else:
        value["items"][0].update(question_type="coding", code="" if case == "coding_code_missing" else "PRIVATE_CODE",
                                 language="python" if case == "coding_code_missing" else "")
    provider[0]["value"] = value
    with caplog.at_level("WARNING", logger=service.__name__):
        result = post(client, body, files, {"X-SAIIA-Screen-Diagnostics": "1"}).json()
    assert result["errorCode"] == "invalid_output" and result["committable"] is False
    assert result["controllerResult"] is None
    assert f"screen_output_{case}" in caplog.text and f"'path': '{path}'" in caplog.text
    assert "PRIVATE_" not in caplog.text


def test_cross_field_diagnostics_preserve_all_previous_outcome_rules():
    from itertools import product
    from pydantic import ValidationError
    from app.models.screen_context import ScreenContextOutput

    body, _ = context()
    for outcome, delta_state, items, missing, conflicts, clarify in product(
            ["answered", "reference_accepted", "needs_more_content", "needs_clarification", "failed"],
            [None, False, True], [False, True], [False, True], [False, True], [False, True]):
        value = output(body, outcome)
        value.update(evidenceDelta=None if delta_state is None else {**output(body)["evidenceDelta"], "complete": delta_state},
                     items=output(body)["items"] if items else [], missingDetails=["missing"] if missing else [],
                     conflicts=["conflict"] if conflicts else [], clarification="clarify" if clarify else None)
        if outcome == "answered":
            expected = delta_state is True and items and not missing and not conflicts and not clarify
        elif outcome == "reference_accepted":
            expected = delta_state is False and not items and not missing and not conflicts and not clarify
        elif outcome == "needs_more_content":
            expected = delta_state is False and not items and missing and not conflicts and not clarify
        elif outcome == "needs_clarification":
            expected = delta_state is None and not items and not missing and clarify
        else:
            expected = delta_state is None and not items and not missing and not conflicts and not clarify
        try:
            ScreenContextOutput.model_validate(value)
            accepted = True
        except ValidationError:
            accepted = False
        assert accepted == bool(expected), (outcome, delta_state, items, missing, conflicts, clarify)


def test_debug_diagnostics_are_off_without_development_opt_in(client, provider, caplog, monkeypatch):
    monkeypatch.delenv("SAIIA_DEV_SCREEN_CONTEXT_DIAGNOSTICS", raising=False)
    body, files = context()
    provider[0]["status"] = "incomplete"
    with caplog.at_level("INFO", logger=service.__name__):
        result = post(client, body, files).json()
    assert result["outcome"] == "failed" and result["errorCode"] == "incomplete_output"
    assert not [record for record in caplog.records if record.name == service.__name__]


def test_development_electron_header_enables_safe_terminal_diagnostics_per_request(client, provider, caplog, monkeypatch):
    monkeypatch.delenv("SAIIA_DEV_SCREEN_CONTEXT_DIAGNOSTICS", raising=False)
    body, files = context()
    provider[0]["value"] = output(body)
    with caplog.at_level("WARNING", logger=service.__name__):
        assert post(client, body, files, {"X-SAIIA-Screen-Diagnostics": "1"}).json()["outcome"] == "answered"
        assert "stage=prepare intent=new" in caplog.text and "images=1 evidence=0 answers=0" in caplog.text
        assert "status=completed" in caplog.text
        caplog.clear()
        body["input"]["evidence"] = [{"text": "PRIVATE_SOURCE"}]
        assert post(client, body, files, {"X-SAIIA-Screen-Diagnostics": "1"}).status_code == 422
        assert "input.evidence.[].imageHash" in caplog.text and "missing" in caplog.text
        assert "PRIVATE_SOURCE" not in caplog.text
        caplog.clear()
        body, files = context()
        post(client, body, files)
        assert not caplog.records


def test_remote_diagnostic_header_cannot_enable_terminal_logging(provider, caplog, monkeypatch):
    monkeypatch.delenv("SAIIA_DEV_SCREEN_CONTEXT_DIAGNOSTICS", raising=False)
    app = FastAPI(); app.include_router(router)
    body, files = context()
    with TestClient(app, client=("203.0.113.4", 50000)) as remote, caplog.at_level("WARNING", logger=service.__name__):
        assert post(remote, body, files, {"X-SAIIA-Screen-Diagnostics": "1"}).status_code == 403
    assert not caplog.records


def test_truncation_reason_is_visible_without_exposing_or_committing_partial_output(client, provider, caplog, monkeypatch):
    monkeypatch.delenv("SAIIA_DEV_SCREEN_CONTEXT_DIAGNOSTICS", raising=False)
    body, files = context()
    provider[0].update(status="incomplete", incomplete_reason="max_output_tokens", text="PRIVATE_PARTIAL_OUTPUT")
    with caplog.at_level("WARNING", logger=service.__name__):
        result = post(client, body, files, {"X-SAIIA-Screen-Diagnostics": "1"}).json()
    assert result["errorCode"] == "incomplete_output" and result["committable"] is False
    assert result["controllerResult"] is None and result["evidenceDelta"] is None
    assert "status=incomplete" in caplog.text and "incomplete_reason=max_output_tokens" in caplog.text
    assert "PRIVATE_PARTIAL_OUTPUT" not in caplog.text


@pytest.mark.parametrize("scenario", ["new", "reference", "reference_continue", "reference_incomplete", "retry", "retry_contract",
                                      "new_continue", "targeted", "batch", "replacement", "clarification", "unicode"])
def test_real_executor_multipart_backend_provider_response_and_commit_roundtrip(client, provider, scenario):
    """Keep one real JS controller alive across actual multipart/JSON boundaries."""
    import base64
    module = Path(__file__).resolve().parents[2] / "frontend/electron"
    script = r"""
const assert=require('node:assert/strict');
const {createScreenContextController}=require(process.argv[1]+'/screen_context_controller.cjs');
const {createScreenContextExecution}=require(process.argv[1]+'/screen_context_execution.cjs');
const lines=require('node:readline').createInterface({input:process.stdin})[Symbol.asyncIterator]();
const images=JSON.parse(process.argv[2]), scenario=process.argv[3];
let captures=0, results=0, requests=[], complete;
const c=createScreenContextController({inspectImage:()=>({width:60,height:40})});
c.adoptSession({runtimeSessionId:'runtime'});
const x=createScreenContextExecution({controller:c,backendUrl:'http://127.0.0.1:8000',developmentDiagnostics:true,
 capture:async()=>({imageDataUrl:'data:image/png;base64,'+images[captures++]}),
 authorize:async()=>({isCurrent:()=>true}),
 publish:s=>{if(s.result)results++; if(['answered','reference_accepted','needs_more_content','needs_clarification','failed'].includes(s.phase))complete?.(s)},
 fetchImpl:async(_url, options)=>{
   const raw=options.body.toString();
   requests.push(JSON.parse(raw.split('\r\n\r\n')[1].split('\r\n')[0]));
   console.log(JSON.stringify({body:options.body.toString('base64'),headers:options.headers}));
   const reply=JSON.parse((await lines.next()).value);
   return new Response(JSON.stringify(reply.body),{status:reply.status});
 }});
async function run(action,retry=false,selection={}){const done=new Promise(resolve=>complete=resolve);retry?x.retry():x.execute({action,...selection});return done;}
(async()=>{
 if(scenario.startsWith('retry')){
   assert.equal((await run('new')).phase,'failed');
   assert.equal((await run(null,true)).phase,'answered');
   const [a,b]=requests;assert.notEqual(a.identity.requestId,b.identity.requestId);
   b.identity.requestId=a.identity.requestId;assert.deepEqual(a,b);
   assert.equal(captures,1);assert.equal(results,1);assert.equal(c.metadata().revision,1);
   assert.throws(()=>x.retry());
 }else if(['new_continue','targeted','batch','replacement','clarification','unicode'].includes(scenario)){
   assert.equal((await run('new')).phase,'answered');
   const origin=requests[0].identity.turnId, target=origin+(scenario==='batch'?':2':':1');
   const selection={targetQuestionId:target,...(scenario==='replacement'?{replacesTurnIds:[origin]}:{})};
   const next=await run('continue',false,selection);
   if(scenario==='clarification'){
     assert.equal(next.phase,'needs_clarification');assert.equal(c.metadata().revision,1);
     const requestId=x.status().clarificationRequestId;
     assert.throws(()=>x.resolve({requestId:'wrong',text:'never accepted'}));
     const done=new Promise(resolve=>complete=resolve);
     x.resolve({requestId,text:'USE_UPDATED_IMPLEMENTATION',targetQuestionId:target,replacesTurnIds:[origin]});
     assert.equal((await done).phase,'answered');assert.equal(captures,2);
   }else assert.equal(next.phase,'answered');
   assert.equal(c.metadata().revision,2);assert.equal(c.metadata().evidenceCount,2);
   assert.equal(c.metadata().priorItems.find(i=>i.questionId===target).turnId,origin);
   if(['targeted','batch','replacement','clarification'].includes(scenario)){
     assert.equal((await run('continue',false,{targetQuestionId:target})).phase,'answered');
     const r=requests.at(-1), second=r.input.evidence[1];
     assert.equal(r.identity.baseRevision,2);assert.equal(r.input.evidence.length,2);
     assert.equal(r.priorItems.find(i=>i.questionId===target).turnId,origin);
     assert.equal(second.imageHashes.length,2);assert.deepEqual(r.replacesTurnIds,[]);
     if(['replacement','clarification'].includes(scenario))assert.deepEqual(second.replacesTurnIds,[origin]);
     if(scenario==='clarification')assert.equal(r.input.clarifications[0].text,'USE_UPDATED_IMPLEMENTATION');
   }
 }else if(scenario==='reference_incomplete'){
   assert.equal((await run('reference')).phase,'reference_accepted');
   assert.equal((await run('continue')).phase,'needs_more_content');
   assert.equal(c.metadata().acceptedImageCount,2);assert.equal(c.metadata().revision,2);
   assert.equal(c.metadata().answerCount,0);assert.equal(results,0);
 }else if(scenario==='reference_continue'){
   assert.equal((await run('reference')).phase,'reference_accepted');assert.equal(results,0);
   for(let i=1;i<=2;i++){
     assert.equal((await run('continue')).phase,'answered');
     const r=requests[i];assert.equal(r.action,'continue');assert.equal(r.contextKind,'reference');
     assert.equal(r.identity.baseRevision,i);assert.equal(r.input.evidence.length,i);
     assert.equal(r.input.answers.length,i-1);assert.equal(r.input.images.length,i+1);
     assert.equal(r.input.images.filter(v=>v.role==='current').length,1);
     assert.equal(r.input.evidence[0].turnId,requests[0].identity.turnId);
     assert.equal(r.targetQuestionId,null);assert.deepEqual(r.replacesTurnIds,[]);
   }
   assert.equal(results,2);assert.equal(c.metadata().acceptedImageCount,3);
 }else{
   const s=await run(scenario);assert.equal(s.phase,scenario==='reference'?'reference_accepted':'answered');
   assert.equal(c.metadata().acceptedImageCount,1);assert.equal(c.metadata().revision,1);
 }
 console.log(JSON.stringify({done:true}));process.exit(0);
})().catch(e=>{console.error(e);process.exit(1)});
"""
    def mock_output(call):
        source = json.loads(call["input"][0]["content"][0]["text"].split("\n", 1)[1])
        hashes = [part["text"].split()[2].rstrip(";") for part in call["input"][0]["content"] if part.get("text", "").startswith("Source image ")]
        body = {"input": {"images": [{"imageHash": h} for h in hashes]}, "replacesTurnIds": source["replacesTurnIds"]}
        value = output(body, "reference_accepted" if source["action"] == "reference" else
                       "needs_more_content" if scenario == "reference_incomplete" else "answered")
        if scenario == "retry_contract" and len(provider[1]) == 1:
            value["evidenceDelta"]["complete"] = False
        if scenario == "batch" and len(provider[1]) == 1:
            value["items"].append({**value["items"][0], "index": 2, "question": "Second question"})
        if scenario == "clarification" and len(provider[1]) == 2:
            value = output(body, "needs_clarification")
        if scenario == "unicode" and len(provider[1]) == 1:
            value["evidenceDelta"]["text"] = "😀" * 12001
        if len(provider[1]) >= 3 and scenario in {"replacement", "clarification"}:
            assert source["sourceEvidence"][0]["turnId"] in source["supersededSourceTurnIds"]
            assert source["sourceEvidence"][0]["turnId"] not in source["activeSourceTurnIds"]
        if scenario == "clarification" and len(provider[1]) == 4:
            accepted = [part["text"] for part in call["input"][0]["content"] if part.get("text", "").startswith("ACCEPTED USER CLARIFICATIONS")][0]
            assert "USE_UPDATED_IMPLEMENTATION" in accepted and "USE_UPDATED_IMPLEMENTATION" not in call["input"][0]["content"][0]["text"]
        return value

    provider[0]["value"] = mock_output
    images = [base64.b64encode(png(i)).decode() for i in range(3)]
    process = subprocess.Popen(["node", "-e", script, str(module), json.dumps(images), scenario],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        attempts = 0
        while True:
            line = process.stdout.readline()
            assert line, process.stderr.read()
            message = json.loads(line)
            if message.get("done"):
                break
            provider[0]["status"] = "incomplete" if scenario == "retry" and attempts == 0 else "completed"
            response = client.post("/api/screen/analyze-context", content=base64.b64decode(message["body"]), headers=message["headers"])
            process.stdin.write(json.dumps({"status": response.status_code, "body": response.json()}) + "\n")
            process.stdin.flush()
            attempts += 1
        assert process.wait(timeout=10) == 0, process.stderr.read()
        expected_attempts = {"reference_continue": 3, "retry": 2, "retry_contract": 2, "reference_incomplete": 2,
                             "new_continue": 2, "targeted": 3, "batch": 3, "replacement": 3, "clarification": 4, "unicode": 2}
        assert attempts == expected_attempts.get(scenario, 1)
        if scenario.startswith("retry"):
            assert provider[1][0] == provider[1][1]  # Identical model input, schema, task and budget.
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_reference_intent_extracts_without_solving_and_reference_continuation_does_not_force_old_question(client, provider):
    body, files = context()
    body.update(action="reference", contextKind="reference")
    provider[0]["value"] = output(body, "reference_accepted")
    result = post(client, body, files).json()
    assert result["outcome"] == "reference_accepted" and result["committable"] is True
    assert result["answer"] == "" and result["items"] == [] and result["missingDetails"] == []
    assert "answer" not in result["controllerResult"]
    assert result["controllerResult"]["evidence"]["complete"] is False
    assert "never solve, invent a question" in provider[1][-1]["instructions"]
    reference_instructions = provider[1][-1]["instructions"]
    assert "Application-selected action=reference; contextKind=reference" in reference_instructions
    assert "ACTIVE TASK: save the readable capture as reference material" in reference_instructions
    assert "Do not ask what to do with the passage" in reference_instructions
    assert "Only ask clarification when a concrete ambiguity in the source" in reference_instructions
    assert "uncertain intent clarifies" not in reference_instructions
    body, files = context(3)
    body["contextKind"] = "reference"
    body["input"]["evidence"][0]["kind"] = "reference"
    body["input"]["answers"] = [{"turnId": "old-1", "text": "FALLIBLE_QUESTION_ONE_ANSWER"}]
    body["priorItems"] = [{"questionId": "old-1:1", "turnId": "old-1", "index": 1}]
    provider[0]["value"] = output(body)
    result = post(client, body, files).json()
    assert result["outcome"] == "answered"
    assert result["items"][0]["question_id"] == "current-turn:1"
    assert "Application-selected action=continue; contextKind=reference" in provider[1][-1]["instructions"]
    assert "ACTIVE TASK: save the readable capture" not in provider[1][-1]["instructions"]
    source = provider[1][-1]["input"][0]["content"][0]["text"]
    assert json.loads(source.split("\n", 1)[1])["referenceTurnIds"] == ["old-0"]
    assert "FALLIBLE_QUESTION_ONE_ANSWER" not in source
    assert "fallible; not observed evidence" in provider[1][-1]["input"][0]["content"][-1]["text"]


@pytest.mark.parametrize("outcome", ["answered", "needs_more_content"])
def test_reference_cannot_solve_or_disguise_missing_question_as_reference_acceptance(client, provider, outcome):
    body, files = context(); body.update(action="reference", contextKind="reference")
    provider[0]["value"] = output(body, outcome)
    result = post(client, body, files).json()
    assert result["outcome"] == "failed" and result["errorCode"] == "invalid_output"
    assert result["controllerResult"] is None


def test_question_capture_cannot_be_implicitly_converted_to_reference(client, provider):
    body, files = context()
    provider[0]["value"] = output(body, "reference_accepted")
    result = post(client, body, files).json()
    assert result["outcome"] == "failed" and result["errorCode"] == "invalid_output"
    assert not result["committable"] and result["controllerResult"] is None


@pytest.mark.parametrize("bad", ["missing_evidence", "complete", "missing_details", "invented_question", "bad_hash"])
def test_reference_acceptance_stays_strict(client, provider, bad):
    body, files = context(); body.update(action="reference", contextKind="reference")
    value = output(body, "reference_accepted")
    if bad == "missing_evidence": value["evidenceDelta"] = None
    if bad == "complete": value["evidenceDelta"]["complete"] = True
    if bad == "missing_details": value["missingDetails"] = ["No question"]
    if bad == "invented_question": value["items"] = output(body)["items"]
    if bad == "bad_hash": value["evidenceDelta"]["imageHashes"] = ["f" * 64]
    provider[0]["value"] = value
    result = post(client, body, files).json()
    assert result["outcome"] == "failed" and result["errorCode"] == "invalid_output"
    assert not result["committable"] and result["controllerResult"] is None


@pytest.mark.parametrize("action", ["new", "reference", "continue"])
def test_provider_enforces_action_and_outcome_combinations_in_nested_schema(action):
    from app.models.screen_context import ScreenContextProviderOutput
    schema = ScreenContextProviderOutput.schema_for_action(action)
    assert schema["type"] == "object" and "anyOf" not in schema
    assert schema["required"] == ["result"] and schema["additionalProperties"] is False
    branches = {branch["properties"]["outcome"]["enum"][0]: branch
                for branch in schema["properties"]["result"]["anyOf"]}
    assert set(branches) == ({"reference_accepted", "needs_clarification", "failed"} if action == "reference" else
                             {"answered", "needs_more_content", "needs_clarification", "failed"})
    for outcome, branch in branches.items():
        rule = OUTCOME_RULES[outcome]
        props = branch["properties"]
        assert branch["additionalProperties"] is False and set(branch["required"]) == set(props)
        if outcome in {"answered", "needs_more_content", "reference_accepted"}:
            evidence = props["evidenceDelta"]
            assert evidence["type"] == "object" and evidence["additionalProperties"] is False
            assert set(evidence["required"]) == set(evidence["properties"])
            assert evidence["properties"]["complete"] == {"type": "boolean", "enum": [rule["complete"]]}
            assert props["conflicts"]["maxItems"] == 0 and props["clarification"] == {"type": "null"}
        else:
            assert props["evidenceDelta"] == {"type": "null"}
        assert props["items"]["minItems" if outcome == "answered" else "maxItems"] == (1 if outcome == "answered" else 0)
        assert props["missingDetails"]["minItems" if outcome == "needs_more_content" else "maxItems"] == (1 if outcome == "needs_more_content" else 0)


@pytest.mark.parametrize("outcome,violation", [(outcome, "presence") for outcome in
    ["answered", "reference_accepted", "needs_more_content", "needs_clarification", "failed"]] +
    [(outcome, "complete") for outcome in ["answered", "reference_accepted", "needs_more_content"]])
def test_observed_evidence_failures_through_provider_parser(client, provider, caplog, outcome, violation):
    body, files = context()
    if outcome == "reference_accepted": body.update(action="reference", contextKind="reference")
    value = output(body, outcome)
    if violation == "presence":
        value["evidenceDelta"] = None if value["evidenceDelta"] is not None else output(body)["evidenceDelta"]
    elif value["evidenceDelta"] is not None:
        value["evidenceDelta"]["complete"] = not value["evidenceDelta"]["complete"]
    provider[0]["value"] = value
    with caplog.at_level("WARNING", logger=service.__name__):
        result = post(client, body, files, {"X-SAIIA-Screen-Diagnostics": "1"}).json()
    assert result["errorCode"] == "invalid_output" and result["committable"] is False
    assert f"screen_output_evidence_{violation}" in caplog.text
    assert "stage=provider_output" in caplog.text and f"'outcome': '{outcome}'" in caplog.text
    assert "evidence_type" in caplog.text and "complete_type" in caplog.text


@pytest.mark.parametrize("action,outcome", [("reference", "answered"), ("reference", "needs_more_content"),
                                           ("new", "reference_accepted"), ("continue", "reference_accepted")])
def test_observed_outcome_conflict_through_response_adapter(client, provider, caplog, action, outcome):
    body, files = context(2 if action == "continue" else 1)
    body.update(action=action, contextKind="question" if action == "new" else "reference")
    provider[0]["value"] = output(body, outcome)
    with caplog.at_level("WARNING", logger=service.__name__):
        result = post(client, body, files, {"X-SAIIA-Screen-Diagnostics": "1"}).json()
    assert result["outcome"] == "failed" and result["controllerResult"] is None
    assert "stage=response_contract" in caplog.text and "path=outcome" in caplog.text
    assert f"'outcome': '{outcome}'" in caplog.text


def test_shape_diagnostics_never_include_values_or_crash_on_malformed_outcome():
    for raw in ["not JSON", "null", "[]", json.dumps({"result": {"outcome": ["PRIVATE"], "evidenceDelta": "PRIVATE"}}),
                json.dumps({"result": {"outcome": "PRIVATE", "evidenceDelta": {"complete": "PRIVATE", "text": "PRIVATE"}}})]:
        assert "PRIVATE" not in json.dumps(service.output_shape(raw))


@pytest.mark.parametrize("mutation", ["no_controller_result", "answer_mismatch", "not_committable", "evidence_mismatch"])
def test_backend_response_revalidates_commit_contract(client, provider, mutation):
    from pydantic import ValidationError
    from app.models.screen_context import ScreenContextResponse
    body, files = context(); provider[0]["value"] = output(body)
    result = post(client, body, files).json()
    if mutation == "no_controller_result": result["controllerResult"] = None
    elif mutation == "answer_mismatch": result["controllerResult"]["answer"] = "PRIVATE"
    elif mutation == "not_committable": result["committable"] = False
    else: result["controllerResult"]["evidence"]["text"] = "PRIVATE"
    with pytest.raises(ValidationError) as exc:
        ScreenContextResponse.model_validate(result)
    assert exc.value.errors(include_input=False)[0]["type"] == "screen_response_commit_contract"


def test_upload_stays_in_memory_above_normal_spool_threshold_and_closes(client, provider, monkeypatch):
    import starlette.formparsers
    opened = []

    def spool(**kwargs):
        file = tempfile.SpooledTemporaryFile(**kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", spool)
    body, _ = context()
    raw = png() + b"\0" * (2 * 1024 * 1024)
    image_hash = hashlib.sha256(raw).hexdigest()
    body["input"]["images"][0]["imageHash"] = image_hash
    body["input"]["currentImageHash"] = image_hash
    provider[0]["value"] = output(body)
    assert post(client, body, {"image_0": raw}).status_code == 200
    assert opened and all(file.closed and not file._rolled for file in opened)


@pytest.mark.asyncio
async def test_aggregate_and_prepared_limits(monkeypatch):
    body, files = context(3)
    request = ScreenContextRequest.model_validate(body)
    screen = ScreenVisionService()
    monkeypatch.setattr(service, "MAX_IMAGES_BYTES", 1)
    with pytest.raises(service.ScreenContextError) as error:
        await service.encode_images(screen, request, files)
    assert error.value.code == "aggregate_image_limit"
    monkeypatch.setattr(service, "MAX_IMAGES_BYTES", 24 * 1024 * 1024)
    monkeypatch.setattr(service, "MAX_PREPARED_BYTES", 1)
    with pytest.raises(service.ScreenContextError) as error:
        await service.encode_images(screen, request, files)
    assert error.value.code == "prepared_image_limit"


def test_collections_metadata_and_multipart_boundaries(client, provider):
    body, files = context()
    body["input"]["images"] *= 7
    assert post(client, body, files).status_code == 422
    body, files = context(2)
    body["input"]["evidence"] *= 33
    assert post(client, body, files).status_code == 422
    body, files = context()
    body["untrusted_metadata"] = "x" * (256 * 1024)
    assert post(client, body, files).status_code == 413
    response = client.post("/api/screen/analyze-context", content=b"--broken\r\n",
                           headers={"Content-Type": "multipart/form-data; boundary=broken"})
    assert response.status_code == 400
    assert not provider[1]


@pytest.mark.asyncio
async def test_concurrency_admission_and_external_cancellation_release_gate(monkeypatch):
    gate = asyncio.Semaphore(1)
    monkeypatch.setattr(api, "_slots", gate)
    await gate.acquire()
    local_request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    with pytest.raises(HTTPException) as error:
        await api.analyze_context(local_request)
    assert error.value.status_code == 429
    gate.release()
    entered = asyncio.Event()

    async def blocked_parse(_request):
        entered.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(api, "parse_context", blocked_parse)
    task = asyncio.create_task(api.analyze_context(local_request))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not gate.locked()


@pytest.mark.asyncio
async def test_async_provider_cancel_closes_client(monkeypatch):
    entered, closed = asyncio.Event(), []

    class BlockedClient:
        def __init__(self, **_kwargs): self.responses = self
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): closed.append(True)
        async def create(self, **_kwargs):
            entered.set()
            await asyncio.sleep(60)

    monkeypatch.setattr(service, "AsyncOpenAI", BlockedClient)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "mock-only")
    monkeypatch.setattr(settings, "SCREEN_VISION_PROVIDER", "openai")
    body, files = context()
    task = asyncio.create_task(ScreenVisionService().answer_context(ScreenContextRequest.model_validate(body), files))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert closed


@pytest.mark.asyncio
async def test_deadline_cancellation_waits_for_owned_cleanup():
    closed = []

    async def blocked():
        try:
            await asyncio.sleep(60)
        finally:
            await asyncio.sleep(0)
            closed.append(True)

    async def connected(): return False
    with pytest.raises(TimeoutError):
        with anyio.fail_after(0.01):
            await api.run_until_disconnect(SimpleNamespace(is_disconnected=connected), blocked())
    assert closed


@pytest.mark.parametrize("kind,expected", [("timeout", "provider_timeout"), ("rate", "provider_rate_limited"),
                                        ("configuration", "provider_configuration"), ("connection", "provider_unavailable")])
def test_provider_errors_are_safe_actionable_and_noncommittable(client, provider, kind, expected):
    request = httpx.Request("POST", "https://example.invalid/responses")
    if kind == "timeout": error = service.APITimeoutError(request=request)
    elif kind == "connection": error = service.APIConnectionError(request=request, message="PRIVATE")
    else:
        response = httpx.Response(429 if kind == "rate" else 400, request=request)
        error = (service.RateLimitError if kind == "rate" else service.BadRequestError)("PRIVATE", response=response, body={"PRIVATE": "PRIVATE"})
    provider[0]["error"] = error
    body, files = context()
    result = post(client, body, files).json()
    assert result["errorCode"] == expected and result["committable"] is False
    assert result["controllerResult"] is None and "PRIVATE" not in json.dumps(result)


def test_missing_provider_key_is_configuration_failure_without_a_model_call(client, provider, monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    body, files = context()
    result = post(client, body, files).json()
    assert result["errorCode"] == "provider_configuration" and result["committable"] is False
    assert result["metrics"]["logicalScreenCalls"] == 0 and not provider[1]


def test_preparation_exception_is_controlled_by_endpoint_before_provider(client, provider, monkeypatch):
    screen = ScreenVisionService()
    def broken(_image): raise RuntimeError("PRIVATE preparation details")
    monkeypatch.setattr(screen, "_prepare_image", broken)
    monkeypatch.setattr(api, "get_screen_service", lambda: screen)
    body, files = context()
    response = post(client, body, files)
    assert response.status_code == 500 and response.json() == {"detail": {"code": "image_preparation_failed"}}
    assert not provider[1]


@pytest.mark.asyncio
async def test_cancelled_decode_keeps_endpoint_slot_until_worker_finishes(monkeypatch, provider):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    screen = ScreenVisionService()
    original = screen._prepare_image
    calls = []
    def blocked(image):
        calls.append(True); entered.set()
        assert release.wait(3)
        try: return original(image)
        finally: finished.set()
    monkeypatch.setattr(screen, "_prepare_image", blocked)
    gate = asyncio.Semaphore(1)
    monkeypatch.setattr(api, "_slots", gate)
    body, files = context(2)
    async def parsed(_request): return ScreenContextRequest.model_validate(body), files
    monkeypatch.setattr(api, "parse_context", parsed)
    monkeypatch.setattr(api, "get_screen_service", lambda: screen)
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"), is_disconnected=lambda: asyncio.sleep(0, result=False))
    task = asyncio.create_task(api.analyze_context(request))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0.01)  # Worker is blocked by a test event, not a timing assumption.
        assert gate.locked() and not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError): await task
    assert finished.is_set() and len(calls) == 1 and not gate.locked()


def test_schema_fingerprint_is_stable_and_contains_no_private_input(client, provider, caplog):
    body, files = context(); provider[0]["value"] = output(body)
    fingerprints = []
    for _ in range(2):
        with caplog.at_level("WARNING", logger=service.__name__):
            post(client, body, files, {"X-SAIIA-Screen-Diagnostics": "1"})
        lines = [record.getMessage() for record in caplog.records if " schema=" in record.getMessage()]
        fingerprints.append(lines[-1].split("schema=", 1)[1].split()[0]); caplog.clear()
    assert fingerprints[0] == fingerprints[1] and len(fingerprints[0]) == 16


@pytest.mark.parametrize("bad", ["future_hash", "future_replacement", "duplicate_support", "reference_in_question", "wrong_clarification_thread"])
def test_typed_provenance_rejects_invalid_relationships_before_provider(client, provider, bad):
    body, files = context(2)
    source = body["input"]["evidence"][0]
    if bad == "future_hash": source["imageHashes"] = [source["imageHash"], body["input"]["currentImageHash"]]
    elif bad == "future_replacement": source["replacesTurnIds"] = [body["identity"]["turnId"]]
    elif bad == "duplicate_support": source["imageHashes"] = [source["imageHash"], source["imageHash"]]
    elif bad == "reference_in_question": source["kind"] = "reference"
    else: body["input"]["clarifications"] = [{"threadId": "other", "turnId": source["turnId"], "requestId": "old-request", "text": "PRIVATE"}]
    assert post(client, body, files).status_code == 422
    assert not provider[1]

@pytest.mark.asyncio
@pytest.mark.parametrize("peer,headers", [
    ("203.0.113.9", {}),
    ("203.0.113.9", {"x-forwarded-for": "127.0.0.1", "forwarded": "for=127.0.0.1"}),
    ("not-an-address", {}),
])
async def test_unauthenticated_remote_rejected_before_body_or_slot(monkeypatch, peer, headers):
    from starlette.requests import Request
    calls = []

    class Slots:
        def locked(self): calls.append("slot"); raise AssertionError("No admission inspection expected")
        async def acquire(self): calls.append("acquire"); raise AssertionError("No slot expected")

    async def receive():
        calls.append("body")
        raise AssertionError("Rejected request body must not be read")

    monkeypatch.setattr(api, "_slots", Slots())
    request = Request({"type": "http", "method": "POST", "path": "/", "client": (peer, 1234),
                       "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}, receive)
    with pytest.raises(HTTPException) as error:
        await api.analyze_context(request)
    assert error.value.status_code == 403
    assert calls == []


@pytest.mark.parametrize("peer,forwarded,expected", [
    ("203.0.113.9", "127.0.0.1", 403),  # Untrusted peer cannot forge local access.
    ("127.0.0.1", "203.0.113.9", 403),  # Trusted proxy supplies a remote client.
    ("127.0.0.1", "127.0.0.2", 200),
])
def test_server_trusted_proxy_boundary_controls_peer(client, provider, peer, forwarded, expected):
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    body, files = context()
    provider[0]["value"] = output(body)
    app = ProxyHeadersMiddleware(client.app, trusted_hosts=["127.0.0.1"])
    with TestClient(app, client=(peer, 1234)) as proxied:
        response = post(proxied, body, files, {"x-forwarded-for": forwarded})
    assert response.status_code == expected, response.text
    assert len(provider[1]) == (1 if expected == 200 else 0)


def test_authenticated_remote_requires_owned_active_cloud_session(client, provider, monkeypatch):
    body, files = context()
    monkeypatch.setattr(api, "get_current_user", lambda _request: CurrentUser(user_id="verified-owner"))
    owners = []
    monkeypatch.setattr(api, "check_cloud_session", lambda context, user: owners.append((context.identity.cloudSessionId, user.user_id)))
    with TestClient(client.app, client=("203.0.113.9", 1234)) as remote:
        assert post(remote, body, files, {"Authorization": "Bearer synthetic"}).status_code == 403
        body["identity"].update(cloudSessionId="30000000-0000-4000-8000-000000000001", accountGeneration=1)
        provider[0]["value"] = output(body)
        assert post(remote, body, files, {"Authorization": "Bearer synthetic"}).status_code == 200
        assert owners == [(body["identity"]["cloudSessionId"], "verified-owner")]
        monkeypatch.setattr(api, "get_current_user", lambda _: (_ for _ in ()).throw(HTTPException(401, "invalid")))
        assert post(remote, body, files, {"Authorization": "Bearer invalid"}).status_code == 401
    assert len(provider[1]) == 1


@pytest.mark.parametrize("reason", ["provider", "key", "batch"])
def test_early_service_outcomes_skip_image_preparation_and_provider(client, provider, monkeypatch, reason):
    body, files = context()
    if reason == "provider":
        monkeypatch.setattr(settings, "SCREEN_VISION_PROVIDER", "openrouter")
    elif reason == "key":
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    else:
        body, files = context(2)
        body["input"]["answers"] = [{"turnId": "old-0", "text": "Previous answers"}]
        body["priorItems"] = [{"questionId": f"old-0:{i}", "turnId": "old-0", "index": i} for i in (1, 2)]

    async def no_decode(*args):
        raise AssertionError("Early outcome must not decode or prepare images")

    monkeypatch.setattr(service, "encode_images", no_decode)
    response = post(client, body, files)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["committable"] is False and result["controllerResult"] is None
    assert result["outcome"] == ("needs_clarification" if reason == "batch" else "failed")
    if reason != "batch":
        assert result["errorCode"] == ("provider_unavailable" if reason == "provider" else "provider_configuration")
    assert provider[1] == []


@pytest.mark.asyncio
async def test_early_exit_still_rejects_manifest_and_byte_limits(provider, monkeypatch):
    body, files = context()
    request = ScreenContextRequest.model_validate(body)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    for invalid, code in [({}, "image_parts_mismatch"), ({"image_0": b""}, "image_byte_limit"),
                          ({"image_0": b"x" * (MAX_IMAGE_BYTES + 1)}, "image_byte_limit")]:
        with pytest.raises(service.ScreenContextError) as error:
            await service.answer_context(ScreenVisionService(), request, invalid)
        assert error.value.code == code
    assert provider[1] == []

@pytest.mark.asyncio
async def test_immediate_outcome_joins_disconnect_probe_even_if_probe_consumes_cancel():
    started = asyncio.Event()
    probes = []

    async def is_disconnected():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            probes.append("cancel_consumed")
            return False

    async def outcome():
        await started.wait()
        return "early_outcome"

    result = await asyncio.wait_for(api.run_until_disconnect(SimpleNamespace(is_disconnected=is_disconnected), outcome()), 1)
    assert result == "early_outcome" and probes == ["cancel_consumed"]
