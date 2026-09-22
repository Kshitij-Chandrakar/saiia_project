"""Opt-in, isolated generator audit. No application imports this script.

Run from repository root with .venv/Scripts/python.exe and --live to make
four ordinary generation requests. Without --live, only synthetic prompt
metadata is inspected. Output contains no prompt, answer, credentials or resume.
This deliberately does NOT represent an end-to-end authenticated Chat trace.
"""
import argparse
import json
import logging
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Existing generator log messages are not part of this safe audit artifact.
    logging.disable(logging.CRITICAL)
    from app.config import settings
    from app.nlp.answer_generator import AnswerGenerator
    from app.nlp.answer_planner import build_answer_plan
    from app.nlp.classifier import classify_question_by_rules
    import openai

    init = time.perf_counter()
    generator = AnswerGenerator(include_context=True)
    init_ms = (time.perf_counter() - init) * 1000
    chunks = [
        {"section": "skills", "text": "SYNTHETIC_SKILL_SENTINEL: Python and SQL."},
        {"section": "projects", "text": "SYNTHETIC_PROJECT_SENTINEL: Built a library catalog."},
    ]
    profile = {
        "selected_resume_authoritative": True,
        "resume": chunks[0]["text"],
        "professional_summary": chunks[0]["text"],
        "projects": chunks[1]["text"],
    }
    report = {
        "scope": "isolated generator; synthetic selected resume; no HTTP endpoint, auth, persistence or UI",
        "sdk": openai.__version__, "client_initialization_ms": round(init_ms, 2),
        "model": settings.OPENAI_MODEL,
        "refinement_enabled": settings.REFINEMENT_ENABLED,
        "semantic_validation_enabled": settings.ENABLE_SEMANTIC_VALIDATION,
        "conditional_correction_enabled": settings.ENABLE_CONDITIONAL_CORRECTION,
        "samples": [],
    }
    client = generator.openai_provider.client
    if args.live and client is None:
        parser.error("Configured OpenAI credential is unavailable")
    questions = ["what is clustering"] * (3 if args.live else 1) + ["what is normalization"]
    for index, question in enumerate(questions):
        start = time.perf_counter()
        sample = {"request_id": "audit-" + uuid.uuid4().hex, "question": question,
                  "run": index + 1, "events": [], "provider_calls": 0, "http_attempts": 0}

        def event(stage, **safe):
            sample["events"].append({"stage": stage, "at_ms": round((time.perf_counter()-start)*1000, 3), **safe})

        event("generator_sample_start")
        category = classify_question_by_rules(question) or "general"
        event("classification_complete", category=category)
        plan = build_answer_plan(question=question, category=category, source="chat", screen_question_type="none")
        kwargs = dict(question=question, question_type=category, profile=profile,
                      retrieved_snippets=chunks, source="chat", profile_context_enabled=True,
                      screen_question_type="none", answer_plan=plan)
        prompt = generator._build_prompt(**kwargs)
        sample["prompt_fixture"] = {
            "answer_type": plan.answer_type, "policy": plan.profile_context_policy,
            "characters": len(prompt),
            "synthetic_resume_text_present": any(c["text"] in prompt for c in chunks),
            "strict_selected_resume_instruction_present": "STRICT SELECTED-RESUME MODE" in prompt,
        }
        # Fixture inspection is outside the measured generation interval.
        if args.live:
            original_create = client.responses.create
            original_generate = generator.openai_provider.generate
            active = {"call": 0, "attempt": 0}

            def on_request(request):
                active["attempt"] += 1
                sample["http_attempts"] += 1
                event("provider_http_dispatch", call_id=active["call"], attempt=active["attempt"])

            def on_response(response):
                event("provider_response_headers", call_id=active["call"], attempt=active["attempt"], status=response.status_code)

            def create(**kw):
                response = original_create(**kw)
                usage = getattr(response, "usage", None)
                event("sdk_parsed_response", call_id=active["call"],
                      input_tokens=getattr(usage, "input_tokens", None),
                      output_tokens=getattr(usage, "output_tokens", None),
                      reasoning_tokens=getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", None),
                      returned_model=getattr(response, "model", None))
                return response

            def generate(**kw):
                sample["provider_calls"] += 1
                active.update(call=sample["provider_calls"], attempt=0)
                event("provider_call_start", call_id=active["call"], phase=kw.get("phase"),
                      max_output_tokens=kw.get("max_output_tokens"), reasoning_effort=kw.get("reasoning_effort"),
                      timeout=kw.get("timeout"), stream=False,
                      input_characters=len(kw.get("input_text", "")))
                try:
                    return original_generate(**kw)
                finally:
                    event("provider_call_end", call_id=active["call"])

            client.responses.create = create
            generator.openai_provider.generate = generate
            # Observe the existing SDK transport; do not replace its retry or pool settings.
            client._client.event_hooks["request"].append(on_request)
            client._client.event_hooks["response"].append(on_response)
            sample["sdk_max_retries"] = client.max_retries
            event("generation_start")
            gen_start = time.perf_counter()
            try:
                result = generator.generate_answer(**kwargs)
                sample["generator_wall_ms"] = round((time.perf_counter()-gen_start)*1000, 2)
                sample["result"] = {key: result.get(key) for key in (
                    "primary_generation_ms", "generation_ms", "prompt_build_ms",
                    "deterministic_validation_ms", "semantic_validation_used", "semantic_validation_ms",
                    "correction_ms", "correction_pass_used", "variation_ms", "refinement_used",
                    "validation_status", "validation_issues_count", "fallback_used")}
                sample["answer_characters"] = len(result.get("answer", ""))
                event("generation_complete")
            except Exception as exc:
                sample["error_type"] = type(exc).__name__
                event("generation_failed")
            finally:
                client.responses.create = original_create
                generator.openai_provider.generate = original_generate
                client._client.event_hooks["request"].remove(on_request)
                client._client.event_hooks["response"].remove(on_response)
        report["samples"].append(sample)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"run": index+1, "provider_calls": sample["provider_calls"],
                          "http_attempts": sample["http_attempts"], "generator_wall_ms": sample.get("generator_wall_ms"),
                          "error_type": sample.get("error_type")} ), flush=True)
        if sample.get("error_type"):
            break
    if client:
        client.close()


if __name__ == "__main__":
    main()
