"""Backend-only product catalog. Availability is not account entitlement."""
import json
import re
from dataclasses import dataclass, replace
from types import MappingProxyType


@dataclass(frozen=True)
class AnswerModel:
    key: str
    display_name: str
    provider: str
    api_model: str
    description: str
    effort: str
    supported_efforts: tuple[str, ...]
    output_limit: int
    api_profile: str = ""


_OPENAI_EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")
_GEMINI_EFFORTS = ("minimal", "low", "medium", "high")
MODELS = (
    AnswerModel("gpt-5.6-luna", "GPT-5.6 Luna", "openai", "gpt-5.6-luna",
                "Cost-conscious text generation", "low", _OPENAI_EFFORTS, 128000),
    AnswerModel("gpt-5.6-terra", "GPT-5.6 Terra", "openai", "gpt-5.6-terra",
                "Balances capability and cost", "low", _OPENAI_EFFORTS, 128000),
    AnswerModel("gpt-oss-120b", "GPT-OSS 120B", "groq", "openai/gpt-oss-120b",
                "Open-weight model via Groq", "low", ("low", "medium", "high"), 65536),
    AnswerModel("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", "gemini", "gemini-3.5-flash-lite",
                "High-throughput, cost-efficient", "minimal", _GEMINI_EFFORTS, 65536),
    AnswerModel("gemini-3.6-flash", "Gemini 3.6 Flash", "gemini", "gemini-3.6-flash",
                "Coding and reasoning", "medium", _GEMINI_EFFORTS, 65536),
)
# Frozen compatibility facts for Phase 2/3 rows that predate binding snapshots.
# These are profiles, never an admission allowlist for new model IDs.
MODELS = tuple(replace(m, api_profile={"openai": "openai-reasoning", "groq": "groq-oss",
                                     "gemini": "gemini-thinking"}[m.provider]) for m in MODELS)
LEGACY_MODELS = MappingProxyType({m.key: m for m in MODELS})
KNOWN_MODELS = {f"{m.provider}:{m.api_model}": m for m in MODELS}
DEFAULT_MODEL_KEY = "gemini-3.5-flash-lite"
FALLBACK_MODEL_KEY = "gpt-oss-120b"


class ModelConfigurationError(ValueError):
    """Never include configuration values, credentials or remote error text."""


PROFILES = MappingProxyType({
    "openai-responses": ("openai", ()),
    "openai-reasoning": ("openai", _OPENAI_EFFORTS),
    "groq-chat": ("groq", ()),
    "groq-oss": ("groq", ("low", "medium", "high")),
    "gemini-content": ("gemini", ()),
    "gemini-thinking": ("gemini", _GEMINI_EFFORTS),
})
DEFAULT_PROFILES = {"openai": "openai-responses", "groq": "groq-chat", "gemini": "gemini-content"}
DEFAULT_ENTRIES = ",".join(KNOWN_MODELS)


def qualified_entry(value):
    if not isinstance(value, str) or value.count(":") != 1:
        raise ModelConfigurationError("Answer model entries require provider:model-id.")
    provider, model_id = value.split(":")
    if provider not in DEFAULT_PROFILES:
        raise ModelConfigurationError("Answer model provider is unsupported.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", model_id) or ".." in model_id or (provider == "gemini" and "/" in model_id):
        raise ModelConfigurationError("Answer model API identifier is invalid.")
    return provider, model_id


def _label(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ModelConfigurationError("Answer model presentation override is invalid.")
    return value.strip()


def parse_catalog(entries, default, fallback, overrides="{}"):
    try:
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise ValueError()
                result[key] = value
            return result
        options = json.loads(overrides, object_pairs_hook=unique_object)
        if not isinstance(options, dict): raise ValueError()
    except (ValueError, TypeError):
        raise ModelConfigurationError("ANSWER_MODEL_OVERRIDES must be a JSON object with unique keys.") from None
    models, seen = [], set()
    for raw in entries.split(","):
        entry = raw.strip()
        provider, model_id = qualified_entry(entry)
        if entry in seen: raise ModelConfigurationError("ANSWER_MODELS contains a duplicate entry.")
        seen.add(entry)
        known = KNOWN_MODELS.get(entry)
        neutral = f"Text generation via {dict(openai='OpenAI', groq='Groq', gemini='Gemini')[provider]}"
        model = known or AnswerModel(entry, model_id.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").title(),
                                    provider, model_id, neutral, "", (), 65536, DEFAULT_PROFILES[provider])
        option = options.get(entry, {})
        if not isinstance(option, dict) or option.keys() - {"display_name", "description", "profile", "effort", "output_limit"}:
            raise ModelConfigurationError("Answer model override fields are unsupported.")
        profile = option.get("profile", model.api_profile)
        if not isinstance(profile, str) or profile not in PROFILES or PROFILES[profile][0] != provider:
            raise ModelConfigurationError("Answer model parameter profile is incompatible with its provider.")
        efforts = PROFILES[profile][1]
        effort = option.get("effort", model.effort if profile == model.api_profile else (efforts[0] if efforts else ""))
        limit = option.get("output_limit", model.output_limit)
        if (not isinstance(effort, str) or (effort not in efforts if efforts else effort != "") or
            type(limit) is not int or not 1 <= limit <= 128000):
            raise ModelConfigurationError("Answer model parameter override is invalid.")
        models.append(replace(model, api_profile=profile, effort=effort, supported_efforts=efforts, output_limit=limit,
            display_name=_label(option.get("display_name", model.display_name), 100),
            description=_label(option.get("description", model.description), 240)))
    if options.keys() - seen:
        raise ModelConfigurationError("Answer model overrides must reference selectable models.")
    if default not in seen or fallback not in seen:
        raise ModelConfigurationError("Answer default and fallback must reference ANSWER_MODELS entries.")
    return tuple(models), next(m.key for m in models if f"{m.provider}:{m.api_model}" == default), next(m.key for m in models if f"{m.provider}:{m.api_model}" == fallback)


def model_binding(model):
    return dict(version=1, provider=model.provider, api_model=model.api_model, profile=model.api_profile,
                effort=model.effort, output_limit=model.output_limit)


def resolve_binding(key, binding=None):
    """Removal changes admission only; execution uses immutable stored facts."""
    if binding is None:
        if key in LEGACY_MODELS: return LEGACY_MODELS[key]
        raise ModelConfigurationError("Stored answer model binding is missing.")
    if not isinstance(binding, dict) or set(binding) != {"version", "provider", "api_model", "profile", "effort", "output_limit"} or type(binding["version"]) is not int or binding["version"] != 1:
        raise ModelConfigurationError("Stored answer model binding is invalid.")
    provider, model_id = qualified_entry(f"{binding['provider']}:{binding['api_model']}")
    known = KNOWN_MODELS.get(f"{provider}:{model_id}")
    if key != (known.key if known else f"{provider}:{model_id}"):
        raise ModelConfigurationError("Stored answer model identity does not match its binding.")
    profile, effort, limit = binding['profile'], binding['effort'], binding['output_limit']
    if not isinstance(profile, str) or profile not in PROFILES or PROFILES[profile][0] != provider:
        raise ModelConfigurationError("Stored answer model profile is unsupported.")
    efforts = PROFILES[profile][1]
    if (not isinstance(effort, str) or (effort not in efforts if efforts else effort != "") or
        type(limit) is not int or not 1 <= limit <= 128000):
        raise ModelConfigurationError("Stored answer model parameters are invalid.")
    return AnswerModel(key, known.display_name if known else model_id, provider, model_id,
                       known.description if known else "Text generation", effort, efforts, limit, profile)


# Config is loaded before this immutable startup snapshot; no provider or DB calls.
from app.config import settings
MODELS, DEFAULT_MODEL_KEY, FALLBACK_MODEL_KEY = parse_catalog(
    settings.ANSWER_MODELS, settings.ANSWER_DEFAULT_MODEL, settings.ANSWER_FALLBACK_MODEL,
    settings.ANSWER_MODEL_OVERRIDES)
MODEL_CATALOG = MappingProxyType({m.key: m for m in MODELS})
_disabled_entries = tuple(e.strip() for e in settings.ANSWER_DISABLED_MODELS.split(",")) if settings.ANSWER_DISABLED_MODELS else ()
for _entry in _disabled_entries:
    qualified_entry(_entry)
if len(set(_disabled_entries)) != len(_disabled_entries):
    raise ModelConfigurationError("ANSWER_DISABLED_MODELS contains duplicates.")
DISABLED_MODELS = frozenset(_disabled_entries)


def model_catalog(config) -> list[dict]:
    """Presentation only; execution profiles, credentials and URLs never cross this API."""
    return [dict(key=m.key, display_name=m.display_name, provider=m.provider, logo_key=m.provider,
                 description=m.description, default=m.key == DEFAULT_MODEL_KEY,
                 selectable=f"{m.provider}:{m.api_model}" not in DISABLED_MODELS, credentials_configured=bool(getattr(config, m.provider.upper()+"_API_KEY", "")),
                 live_access="not_verified") for m in MODELS]
