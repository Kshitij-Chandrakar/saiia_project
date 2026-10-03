from pathlib import Path
import os
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import debug
from app.nlp import answer_generator as agmod
from app.nlp.answer_generator import AnswerGenerator, ProviderError


@pytest.mark.parametrize("provider", ["openai", "groq", "ollama"])
def test_supported_provider_selection_and_dispatch(monkeypatch, provider):
    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", provider)
    monkeypatch.setattr(agmod.settings, "PRIMARY_LLM_PROVIDER", "openai")
    generator = AnswerGenerator.__new__(AnswerGenerator)
    methods = {
        "openai": "_generate_with_openai_then_optional_groq",
        "groq": "_generate_with_groq_then_optional_ollama",
        "ollama": "_generate_with_ollama",
    }

    def unexpected(*args, **kwargs):
        pytest.fail("Dispatch called a different provider")

    for method in methods.values():
        monkeypatch.setattr(generator, method, unexpected)
    monkeypatch.setattr(generator, methods[provider], lambda *args, **kwargs: {"provider": provider})

    selected = generator._select_primary_provider("Design a distributed system", "technical")
    assert selected == provider
    assert generator._generate_with_primary_provider(
        primary_provider=selected,
        prompt="test",
        answer_plan=None,
        context_qt="",
        question="test",
        question_type="technical",
        profile=None,
        retrieved_snippets=None,
        job_context=None,
    ) == {"provider": provider}


@pytest.mark.parametrize("configured", ["nvidia", "unknown-provider"])
@pytest.mark.parametrize("legacy, expected", [("groq", "openai"), ("ollama", "ollama")])
def test_unsupported_config_uses_existing_fallback(monkeypatch, configured, legacy, expected):
    monkeypatch.setattr(agmod.settings, "ANSWER_PROVIDER", configured)
    monkeypatch.setattr(agmod.settings, "PRIMARY_LLM_PROVIDER", legacy)
    generator = AnswerGenerator.__new__(AnswerGenerator)
    assert generator._select_primary_provider("test", "technical") == expected


def test_unsupported_direct_dispatch_fails():
    generator = AnswerGenerator.__new__(AnswerGenerator)
    with pytest.raises(ProviderError, match="Use ANSWER_PROVIDER=openai, groq, or ollama"):
        generator._generate_with_primary_provider(
            primary_provider="nvidia",
            prompt="test",
            answer_plan=None,
            context_qt="",
            question="test",
            question_type="technical",
            profile=None,
            retrieved_snippets=None,
            job_context=None,
        )


def test_debug_router_has_no_nvidia_endpoint():
    app = FastAPI()
    app.include_router(debug.router, prefix="/api/debug")
    with TestClient(app) as client:
        assert client.get("/api/debug/nvidia-test").status_code == 404
    assert "/api/debug/affinda/document-types" in {route.path for route in app.routes}


@pytest.mark.parametrize("override, expected", [(None, 50.0), ("12.5", 12.5)])
def test_refinement_timeout_is_independent_of_retired_nvidia_setting(override, expected):
    env = dict(os.environ, NVIDIA_TIMEOUT_SECONDS="999")
    env.pop("REFINEMENT_JOB_TIMEOUT_SECONDS", None)
    if override is not None:
        env["REFINEMENT_JOB_TIMEOUT_SECONDS"] = override
    result = subprocess.run(
        [sys.executable, "-c", "import dotenv; dotenv.load_dotenv = lambda: None; from app.config import settings; print(settings.REFINEMENT_JOB_TIMEOUT_SECONDS)"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(result.stdout) == expected
