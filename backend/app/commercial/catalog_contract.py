"""Pure catalog.v1 documents. No storage, pricing engine or access authority.

Policy references are declarations, not verified approvals. A snapshot fingerprint
identifies content; it is not a signature, database publication or entitlement.
Only the explicit currency subset below is supported; it implies no provider
support or commercial currency choice. No application configuration is imported.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Annotated, Final, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

CONTRACT_VERSION: Final = "catalog.v1"
REGISTRY_VERSION: Final = "catalog.features.v1"
CURRENCY_VERSION: Final = "catalog.currency.v1"
MAX_INTEGER = 2**63 - 1  # Representation bound, not a commercial allowance.
CURRENCIES = MappingProxyType({"INR": 2, "USD": 2, "JPY": 0, "KWD": 3})


def _integer(value: object) -> int:
    if type(value) is int:
        return value
    # Decimal strings are the lossless JSON wire representation, not coercion
    # from floats, booleans, exponent notation, whitespace or leading zeros.
    if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]{0,18}", value):
        return int(value)
    raise PydanticCustomError("invalid_integer", "Expected an exact integer")


def _identifier(value: object) -> str:
    if not isinstance(value, str):
        raise PydanticCustomError("invalid_identifier", "Expected a UUID string")
    try:
        parsed = UUID(value)
    except ValueError:
        raise PydanticCustomError(
            "invalid_identifier", "Expected a UUID string"
        ) from None
    if str(parsed) != value.lower():
        raise PydanticCustomError("invalid_identifier", "Expected a hyphenated UUID")
    return str(parsed)


def _instant(value: object) -> datetime:
    if isinstance(value, str):
        try:
            # Python 3.10 accepts 3/6 fractional digits; PostgreSQL trims zeros.
            value = re.sub(
                r"\.(\d{1,6})(?=Z|[+-]\d{2}:\d{2}$)",
                lambda match: "." + match[1].ljust(6, "0"),
                value,
            )
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise PydanticCustomError(
                "invalid_instant", "Expected an aware instant"
            ) from None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise PydanticCustomError("invalid_instant", "Expected an aware instant")
    return value.astimezone(timezone.utc)


Quantity = Annotated[
    int,
    BeforeValidator(_integer),
    Field(ge=0, le=MAX_INTEGER),
    PlainSerializer(str, when_used="json"),
]
Positive = Annotated[Quantity, Field(ge=1)]
Identifier = Annotated[str, BeforeValidator(_identifier)]
Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9._:-]{0,119}$")]
Text = Annotated[
    str,
    Field(
        min_length=1,
        max_length=2000,
        pattern=r"^[^<>\x00-\x1f]*[^\s<>\x00-\x1f][^<>\x00-\x1f]*$",
    ),
]
Instant = Annotated[datetime, BeforeValidator(_instant)]


class FrozenDocument(BaseModel):
    """Strict deeply typed documents; nested collections are tuples, not dicts."""

    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always"
    )

    @field_validator("*", mode="before")
    @classmethod
    def json_arrays(cls, value: object) -> object:
        # JSON lists explicitly become tuples; sets/generators remain invalid.
        return tuple(value) if isinstance(value, list) else value


@dataclass(frozen=True)
class MeterSpec:
    """Registered compatibility only; no runtime quota or measurement."""

    feature: str
    kind: str
    unit: str


@dataclass(frozen=True)
class Capability:
    """Local implementation is independent of hosted/commercial readiness."""

    meters: tuple[str, ...]
    required_limit: str | None = None
    implemented: bool = True
    hosted_readiness: str = "not_verified"
    grants_runtime_access: bool = False


METERS = MappingProxyType(
    {
        "answers.completed": MeterSpec("answers.generate", "quota", "turn"),
        "answers.concurrent": MeterSpec("answers.generate", "concurrency", "operation"),
        "audio.transcribed": MeterSpec("audio.transcribe", "quota", "second"),
        "audio.concurrent": MeterSpec("audio.transcribe", "concurrency", "stream"),
        "auto.authorized_running": MeterSpec("assistant.auto", "quota", "second"),
        "auto.concurrent_runs": MeterSpec("assistant.auto", "concurrency", "run"),
        "resume.stored_files": MeterSpec("resume.upload", "storage", "file"),
        "resume.stored_bytes": MeterSpec("resume.upload", "storage", "byte"),
        "resume.extractions": MeterSpec("resume.extract", "quota", "extraction"),
        "job_context.stored": MeterSpec("job_context.manage", "storage", "record"),
        "job_context.extractions": MeterSpec(
            "job_context.extract", "quota", "extraction"
        ),
        "screen.analyses": MeterSpec("screen.analyze", "quota", "analysis"),
        "screen.concurrent": MeterSpec("screen.analyze", "concurrency", "operation"),
        "notes.generations": MeterSpec("notes.generate", "quota", "generation"),
        "ask_ai.completed": MeterSpec("session.ask_ai", "quota", "turn"),
    }
)
FEATURES = MappingProxyType(
    {
        feature: Capability(
            tuple(k for k, m in METERS.items() if m.feature == feature), required
        )
        for feature, required in (
            ("answers.generate", "answers.completed"),
            ("audio.transcribe", "audio.transcribed"),
            ("assistant.auto", "auto.authorized_running"),
            ("resume.upload", "resume.stored_files"),
            ("resume.extract", "resume.extractions"),
            ("resume.grounding", None),
            ("job_context.manage", "job_context.stored"),
            ("job_context.extract", "job_context.extractions"),
            ("screen.analyze", "screen.analyses"),
            ("sessions.history", None),
            ("transcripts.export", None),
            ("notes.generate", "notes.generations"),
            ("session.ask_ai", "ask_ai.completed"),
        )
    }
)
AUTO_BASIS = "authorized_running_including_silence_both_once"


class PlanIdentity(FrozenDocument):
    plan_id: Identifier
    code: Key


class BillingInterval(FrozenDocument):
    unit: Literal["month", "year"]
    count: Positive


class ResetCadence(FrozenDocument):
    unit: Literal["month", "year"]
    count: Positive
    anchor: Literal["calendar", "subscription_anniversary"]
    timezone: str
    policy_ref: Key

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise PydanticCustomError("invalid_timezone", "Unknown timezone") from None
        return value


class Price(FrozenDocument):
    price_id: Identifier
    currency: Literal["INR", "USD", "JPY", "KWD"]
    exponent: Quantity
    currency_version: Literal["catalog.currency.v1"] = CURRENCY_VERSION
    amount_minor: Quantity | None = None
    billing: BillingInterval | None = None
    tax_policy_ref: Key | None = None
    rounding_policy_ref: Key | None = None


class Entitlement(FrozenDocument):
    feature: Key
    allowed: bool
    model_keys: tuple[str, ...] = ()
    audio_sources: tuple[Literal["microphone", "system", "both"], ...] = ()


class Limit(FrozenDocument):
    meter: Key
    feature: Key
    kind: Literal["quota", "storage", "concurrency"]
    unit: Key
    amount: Quantity | None = None
    grant_kind: Literal["one_time", "recurring"] | None = None
    reset: ResetCadence | None = None
    policy_ref: Key | None = None
    basis: Literal["authorized_running_including_silence_both_once"] | None = None


class Discount(FrozenDocument):
    discount_id: Identifier
    revision: Positive
    kind: Literal["percentage", "fixed"]
    basis_points: Quantity | None = None
    amount_minor: Quantity | None = None
    currency: Literal["INR", "USD", "JPY", "KWD"] | None = None
    exponent: Quantity | None = None
    scope: Literal["offer", "prices", "account_policy"] | None = None
    price_ids: tuple[Identifier, ...] = ()
    eligibility_policy_ref: Key | None = None
    valid_from: Instant | None = None
    valid_until: Instant | None = None
    total_redemptions: Positive | None = None
    per_account_redemptions: Positive | None = None
    redemption_policy_ref: Key | None = None
    duration: Literal["once", "repeating", "ongoing"] | None = None
    cycles: Positive | None = None
    stacking: bool | None = None
    application_policy_ref: Key | None = None
    public_label: Text | None = None


class OfferTerms(FrozenDocument):
    name: Text | None = None
    description: Text | None = None
    prices: tuple[Price, ...] = ()
    entitlements: tuple[Entitlement, ...] = ()
    limits: tuple[Limit, ...] = ()
    discounts: tuple[Discount, ...] = ()
    subscription_policy_ref: Key | None = None
    migration_policy_ref: Key | None = None


# v1 classes/defaults remain unchanged: v2 is an explicit, independently decoded
# terms shape. This is representation, never runtime quota authority.
V2_FEATURES = MappingProxyType({**FEATURES,
    "resume.extract": Capability(("resume.extractions",), None, hosted_readiness="requires_resume_operation_admission"),
    "clipboard.saved_answers": Capability(("clipboard.new_saves",), "clipboard.new_saves", implemented=True, hosted_readiness="session_scoped_create_read_only"),
    "sketch.generate": Capability((), implemented=False, hosted_readiness="diagram_path_requires_verification"),
    "screen.followups": Capability((), implemented=False, hosted_readiness="continue_context_is_not_verified_followup_product")})
V2_METERS = MappingProxyType({**METERS,
    "resume.replacements": MeterSpec("resume.upload", "quota", "replacement"),
    "clipboard.new_saves": MeterSpec("clipboard.saved_answers", "quota", "save")})


class AllowancePeriod(FrozenDocument):
    unit: Literal["day", "month"]
    anchor: Literal["calendar", "account_signup_day"]
    timezone: Literal["Asia/Kolkata"]

    @model_validator(mode="after")
    def compatible(self):
        if (self.unit == "day") != (self.anchor == "calendar"):
            raise ValueError("Incompatible period anchor")
        return self


class UsageAllowance(FrozenDocument):
    meter: Key
    feature: Key
    mode: Literal["unlimited", "limited"]
    unit: Key
    amount: Quantity | None = None
    period: AllowancePeriod | None = None
    basis: Literal["authorized_running_including_silence_both_once"] | None = None

    @model_validator(mode="after")
    def compatible(self):
        spec = V2_METERS.get(self.meter)
        if spec is None or spec.feature != self.feature or spec.unit != self.unit or spec.kind != "quota":
            raise ValueError("Incompatible registered usage meter")
        if self.mode == "unlimited" and (self.amount is not None or self.period is not None):
            raise ValueError("Unlimited has no numeric quota or reset")
        if self.mode == "limited" and (self.amount is None or self.period is None):
            raise ValueError("Limited requires amount and period")
        if (self.meter == "auto.authorized_running") != (self.basis is not None):
            raise ValueError("Incompatible measurement basis")
        return self


class FeaturePresentation(FrozenDocument):
    feature: Key
    label: Text
    information: Text
    preview: Literal["unavailable"] = "unavailable"


class OfferTermsV2(OfferTerms):
    resume_extraction_basis: Literal["initial_upload_or_replacement_operation"] = "initial_upload_or_replacement_operation"
    pricing_mode: Literal["unconfigured", "free", "priced"] = "unconfigured"
    unmetered_features: tuple[Key, ...] = ()
    saved_answer_policy: Literal["immutable_user_entries_retain_across_resets"] = "immutable_user_entries_retain_across_resets"
    allowances: tuple[UsageAllowance, ...] = ()
    presentation: tuple[FeaturePresentation, ...] = ()
    model_selection: Literal["configured_supported_available"] = "configured_supported_available"
    validation_policy_version: Literal["catalog.validation.v2"] = "catalog.validation.v2"


# V3 adds explicit storage capacity and non-operational service benefits.
# V1/V2 shapes, normalization and canonical bytes remain unchanged.
V3_FEATURES = MappingProxyType({**V2_FEATURES,
    "sketch.generate": Capability((), hosted_readiness="answer_diagrams_requires_hosted_admission"),
    "screen.followups": Capability((), hosted_readiness="screen_context_continue_requires_metering")})

class StorageAllowance(FrozenDocument):
    meter: Literal["resume.stored_files"] = "resume.stored_files"
    mode: Literal["unlimited", "limited"]
    amount: Quantity | None = None

    @model_validator(mode="after")
    def compatible(self):
        if (self.mode == "unlimited") != (self.amount is None):
            raise ValueError("Explicit storage capacity required")
        return self

class ServiceBenefit(FrozenDocument):
    key: Literal["support.email", "support.ai_human", "access.early"]
    label: Text
    # No support workflow/release authority exists yet. Never imply operational.
    availability: Literal["coming_soon"] = "coming_soon"

class OfferTermsV3(OfferTermsV2):
    validation_policy_version: Literal["catalog.validation.v3"] = "catalog.validation.v3"
    storage_allowances: tuple[StorageAllowance, ...] = ()
    service_benefits: tuple[ServiceBenefit, ...] = ()


def _versioned_terms(value, info):
    if isinstance(value, dict):
        model = {
            "catalog.v1": OfferTerms,
            "catalog.v2": OfferTermsV2,
            "catalog.v3": OfferTermsV3,
        }.get(info.data.get("contract_version", CONTRACT_VERSION))
        if model is not None:
            return model.model_validate(value)
    return value


DraftState = Literal["draft", "previewed", "published", "abandoned"]


class CatalogDraft(FrozenDocument):
    """Editable head; assignment validates shape, cross-field checks are explicit."""

    model_config = ConfigDict(frozen=False, validate_assignment=True)
    draft_id: Identifier
    plan: PlanIdentity
    revision: Positive
    state: DraftState = "draft"
    contract_version: Literal["catalog.v1", "catalog.v2", "catalog.v3"] = CONTRACT_VERSION
    registry_version: Literal["catalog.features.v1", "catalog.features.v2", "catalog.features.v3"] = REGISTRY_VERSION
    terms: OfferTerms | OfferTermsV2 | OfferTermsV3 = OfferTerms()
    internal_notes: str = ""

    _terms_for_version = field_validator("terms", mode="before")(_versioned_terms)

    @model_validator(mode="after")
    def version_shape(self):
        check_version(self.contract_version, self.registry_version, self.terms)
        return self



def check_version(contract, registry, terms):
    expected = {OfferTerms: "1", OfferTermsV2: "2", OfferTermsV3: "3"}.get(type(terms))
    if expected is None or contract != "catalog.v" + expected or registry != "catalog.features.v" + expected:
        raise ValueError("Incompatible catalog versions")


@dataclass(frozen=True)
class ContractIssue:
    path: tuple[str | int, ...]
    code: str


@dataclass(frozen=True)
class ValidationReport:
    draft: CatalogDraft | None
    errors: tuple[ContractIssue, ...]
    pending: tuple[ContractIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def publishable(self) -> bool:
        return self.valid and not self.pending


def transition_errors(
    current: DraftState, target: DraftState
) -> tuple[ContractIssue, ...]:
    """Validate an edge only; no state mutation, preview, CAS or publication."""
    edges = {
        "draft": ("previewed", "abandoned"),
        "previewed": ("draft", "published", "abandoned"),
    }
    return (
        ()
        if target in edges.get(current, ())
        else (ContractIssue(("state",), "invalid_transition"),)
    )


def _terms_issues(
    terms: OfferTerms, model_keys: frozenset[str]
) -> tuple[tuple[ContractIssue, ...], tuple[ContractIssue, ...]]:
    errors: list[ContractIssue] = []
    pending: list[ContractIssue] = []

    def error(path: tuple[str | int, ...], code: str) -> None:
        errors.append(ContractIssue(("terms",) + path, code))

    def required(path: tuple[str | int, ...], value: object) -> None:
        if value is None or value == ():
            pending.append(ContractIssue(("terms",) + path, "policy_unresolved"))

    for field in (
        "name",
        "description",
        "subscription_policy_ref",
        "migration_policy_ref",
    ):
        required((field,), getattr(terms, field))
    required(("prices",), terms.prices)
    registered = V3_FEATURES if isinstance(terms, OfferTermsV3) else V2_FEATURES if isinstance(terms, OfferTermsV2) else FEATURES
    features: dict[str, Entitlement] = {}
    for i, item in enumerate(terms.entitlements):
        path = ("entitlements", i)
        if item.feature not in registered:
            error(path + ("feature",), "unknown_feature")
        if isinstance(terms, OfferTermsV2) and item.allowed and item.feature in registered and not registered[item.feature].implemented:
            pending.append(ContractIssue(("terms",) + path + ("feature",), "capability_unverified"))
        if item.feature in features:
            error(path + ("feature",), "duplicate_feature")
        features[item.feature] = item
        if len(set(item.model_keys)) != len(item.model_keys) or len(
            set(item.audio_sources)
        ) != len(item.audio_sources):
            error(path, "duplicate_dimension")
        if item.model_keys and (
            item.feature != "answers.generate"
            or not item.allowed
            or not set(item.model_keys) <= model_keys
        ):
            error(path + ("model_keys",), "invalid_model_eligibility")
        if item.audio_sources and (
            item.feature != "assistant.auto" or not item.allowed
        ):
            error(path + ("audio_sources",), "incompatible_dimension")
        if item.feature == "assistant.auto" and item.allowed:
            required(path + ("audio_sources",), item.audio_sources)
    meters: set[str] = set()
    for i, limit in enumerate(terms.limits):
        path = ("limits", i)
        spec = METERS.get(limit.meter)
        if limit.meter in meters:
            error(path + ("meter",), "duplicate_limit")
        meters.add(limit.meter)
        if spec is None:
            error(path + ("meter",), "unknown_meter")
        elif (limit.feature, limit.kind, limit.unit) != (
            spec.feature,
            spec.kind,
            spec.unit,
        ):
            error(path, "incompatible_unit")
        if limit.feature not in features or not features[limit.feature].allowed:
            error(path + ("feature",), "feature_denied")
        required(path + ("amount",), limit.amount)
        required(path + ("policy_ref",), limit.policy_ref)
        if limit.kind == "quota":
            required(path + ("grant_kind",), limit.grant_kind)
            if limit.grant_kind == "recurring":
                required(path + ("reset",), limit.reset)
            elif limit.reset is not None:
                error(path + ("reset",), "incompatible_reset")
        elif limit.grant_kind is not None or limit.reset is not None:
            error(path, "incompatible_reset")
        if limit.meter == "auto.authorized_running":
            required(path + ("basis",), limit.basis)
        elif limit.basis is not None:
            error(path + ("basis",), "incompatible_basis")
    for key, item in features.items():
        spec_feature = registered.get(key)
        if (
            item.allowed
            and spec_feature
            and spec_feature.required_limit
            and spec_feature.required_limit not in meters
        ):
            pending.append(ContractIssue(("terms", "limits", key), "limit_unresolved"))
    price_ids: set[str] = set()
    prices: set[tuple[str, str, int]] = set()
    for i, price in enumerate(terms.prices):
        path = ("prices", i)
        if price.price_id in price_ids:
            error(path + ("price_id",), "duplicate_price")
        price_ids.add(price.price_id)
        if price.exponent != CURRENCIES[price.currency]:
            error(path + ("exponent",), "incompatible_currency")
        for field in (
            "amount_minor",
            "billing",
            "tax_policy_ref",
            "rounding_policy_ref",
        ):
            required(path + (field,), getattr(price, field))
        if price.billing:
            identity = (price.currency, price.billing.unit, price.billing.count)
            if identity in prices:
                error(path, "duplicate_price")
            prices.add(identity)
    discounts: set[str] = set()
    for i, discount in enumerate(terms.discounts):
        path = ("discounts", i)
        if discount.discount_id in discounts:
            error(path, "duplicate_discount")
        discounts.add(discount.discount_id)
        if discount.kind == "percentage":
            required(path + ("basis_points",), discount.basis_points)
            if (
                discount.basis_points is not None
                and not 1 <= discount.basis_points <= 10000
            ):
                error(path + ("basis_points",), "invalid_discount")
            if any(
                v is not None
                for v in (discount.amount_minor, discount.currency, discount.exponent)
            ):
                error(path, "invalid_discount")
        else:
            for field in ("amount_minor", "currency", "exponent"):
                required(path + (field,), getattr(discount, field))
            if discount.basis_points is not None or discount.amount_minor == 0:
                error(path, "invalid_discount")
        if discount.scope == "prices":
            required(path + ("price_ids",), discount.price_ids)
            if (
                len(set(discount.price_ids)) != len(discount.price_ids)
                or not set(discount.price_ids) <= price_ids
            ):
                error(path + ("price_ids",), "invalid_discount_scope")
        elif discount.price_ids:
            error(path + ("price_ids",), "invalid_discount_scope")
        for field in (
            "scope",
            "eligibility_policy_ref",
            "valid_from",
            "valid_until",
            "total_redemptions",
            "per_account_redemptions",
            "redemption_policy_ref",
            "duration",
            "stacking",
            "application_policy_ref",
        ):
            required(path + (field,), getattr(discount, field))
        if (
            discount.valid_from
            and discount.valid_until
            and discount.valid_from >= discount.valid_until
        ):
            error(path, "invalid_discount_window")
        if (
            discount.total_redemptions is not None
            and discount.per_account_redemptions is not None
            and discount.per_account_redemptions > discount.total_redemptions
        ):
            error(path, "invalid_redemption_limit")
        if discount.duration == "repeating":
            required(path + ("cycles",), discount.cycles)
        elif discount.cycles is not None:
            error(path + ("cycles",), "invalid_discount_duration")
        if discount.stacking is True:
            error(path + ("stacking",), "unsupported_stacking")
        eligible = [
            p
            for p in terms.prices
            if discount.scope != "prices" or p.price_id in discount.price_ids
        ]
        if discount.kind == "fixed":
            for price in eligible:
                if (
                    discount.currency is not None
                    and discount.exponent is not None
                    and (
                        discount.currency != price.currency
                        or discount.exponent != price.exponent
                    )
                ):
                    error(path, "incompatible_currency")
                if (
                    discount.amount_minor is not None
                    and price.amount_minor is not None
                    and discount.amount_minor > price.amount_minor
                ):
                    error(path, "discount_exceeds_price")
    if isinstance(terms, OfferTermsV2):
        if terms.pricing_mode == "free":
            if terms.prices or terms.discounts:
                error(("pricing_mode",), "free_has_paid_terms")
            pending = [issue for issue in pending if issue.path != ("terms", "prices")]
        if any(item.model_keys for item in terms.entitlements):
            error(("model_selection",), "contradictory_model_selection")
        if any(key not in ("sessions.history", "transcripts.export") or not features.get(key) or not features[key].allowed for key in terms.unmetered_features) or len(set(terms.unmetered_features)) != len(terms.unmetered_features):
            error(("unmetered_features",), "contradictory_allowance")
        for key in ("sessions.history", "transcripts.export"):
            if features.get(key) and features[key].allowed and key not in terms.unmetered_features:
                pending.append(ContractIssue(("terms", "unmetered_features", key), "limit_unresolved"))
        seen = set()
        for i, allowance in enumerate(terms.allowances):
            if allowance.meter in seen or allowance.meter in meters or not features.get(allowance.feature) or not features[allowance.feature].allowed:
                error(("allowances", i), "contradictory_allowance")
            seen.add(allowance.meter)
        if features.get("resume.upload") and features["resume.upload"].allowed and "resume.replacements" not in seen:
            pending.append(ContractIssue(("terms", "allowances", "resume.replacements"), "limit_unresolved"))
        pending = [issue for issue in pending if not (issue.code == "limit_unresolved" and registered.get(str(issue.path[-1])) and registered[str(issue.path[-1])].required_limit in seen)]
        displays = set()
        for i, display in enumerate(terms.presentation):
            if display.feature not in registered or display.feature in displays or display.feature not in features:
                error(("presentation", i), "invalid_presentation")
            displays.add(display.feature)
    if isinstance(terms, OfferTermsV3):
        if len({a.meter for a in terms.storage_allowances}) != len(terms.storage_allowances) or len({b.key for b in terms.service_benefits}) != len(terms.service_benefits):
            error(("storage_allowances",), "duplicate_definition")
        for a in terms.storage_allowances:
            if a.meter in meters or not features.get("resume.upload") or not features["resume.upload"].allowed:
                error(("storage_allowances",), "contradictory_allowance")
        if terms.storage_allowances:
            pending = [p for p in pending if p.path != ("terms", "limits", "resume.upload")]
        if terms.pricing_mode == "unconfigured":
            pending.append(ContractIssue(("terms", "pricing_mode"), "policy_unresolved"))
    return tuple(errors), tuple(pending)


def validate_draft(
    value: object, *, model_keys: frozenset[str] = frozenset()
) -> ValidationReport:
    """Return safe field/reason issues, never input values or provider errors.

    Model keys must be supplied by a later trusted caller from its backend model
    catalog. This proves compatibility only, never account access/entitlement.
    """
    if isinstance(value, CatalogDraft):
        value = value.model_dump(mode="python")
    try:
        draft = CatalogDraft.model_validate(value)
    except ValidationError as exc:
        return ValidationReport(
            None,
            tuple(
                ContractIssue(tuple(e["loc"]), str(e["type"]))
                for e in exc.errors(include_input=False)
            ),
            (),
        )
    errors, pending = _terms_issues(draft.terms, model_keys)
    if draft.state in ("published", "abandoned"):
        errors += (ContractIssue(("state",), "invalid_transition"),)
    return ValidationReport(draft, errors, pending)


class CatalogValidationError(ValueError):
    """Safe structured failure to build a snapshot."""

    def __init__(self, issues: tuple[ContractIssue, ...]) -> None:
        self.issues = issues
        super().__init__("Catalog terms are not structurally publishable")


def _normalized(terms: OfferTerms) -> OfferTerms:
    # All these collections are sets by contract; no ordered commercial rules.
    data = terms.model_dump(mode="python")
    normalized_features = {f.feature: f for f in terms.entitlements}
    data["entitlements"] = tuple(
        (
            Entitlement(feature=key, allowed=False)
            if key not in normalized_features
            else Entitlement(
                **dict(
                    normalized_features[key].model_dump(mode="python"),
                    model_keys=tuple(sorted(normalized_features[key].model_keys)),
                    audio_sources=tuple(sorted(normalized_features[key].audio_sources)),
                )
            )
        )
        for key in sorted(V3_FEATURES if isinstance(terms, OfferTermsV3) else V2_FEATURES if isinstance(terms, OfferTermsV2) else FEATURES)
    )
    data["prices"] = tuple(sorted(terms.prices, key=lambda p: p.price_id))
    data["limits"] = tuple(sorted(terms.limits, key=lambda item: item.meter))
    data["discounts"] = tuple(
        Discount(
            **dict(d.model_dump(mode="python"), price_ids=tuple(sorted(d.price_ids)))
        )
        for d in sorted(terms.discounts, key=lambda d: d.discount_id)
    )
    return type(terms).model_validate(data)


def canonical_json(value: object) -> str:
    """Shared exact JSON encoding; protocol documents still define their contents."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def terms_fingerprint(terms: OfferTerms) -> str:
    """Content identity only; callers must separately establish readiness/authority."""
    normalized = _normalized(type(terms).model_validate(terms.model_dump(mode="python")))
    return hashlib.sha256(
        canonical_json(normalized.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()


class OfferSnapshot(FrozenDocument):
    """Immutable content document, not proof of durable publication."""

    contract_version: Literal["catalog.v1", "catalog.v2", "catalog.v3"] = CONTRACT_VERSION
    registry_version: Literal["catalog.features.v1", "catalog.features.v2", "catalog.features.v3"] = REGISTRY_VERSION
    plan: PlanIdentity
    offer_version_id: Identifier
    version: Positive
    terms: OfferTerms | OfferTermsV2 | OfferTermsV3
    eligible_model_keys: tuple[str, ...] = Field(default=(), exclude=True, repr=False)

    _terms_for_version = field_validator("terms", mode="before")(_versioned_terms)

    @model_validator(mode="after")
    def checked_terms(self) -> OfferSnapshot:
        check_version(self.contract_version, self.registry_version, self.terms)
        errors, pending = _terms_issues(self.terms, frozenset(self.eligible_model_keys))
        if errors or pending:
            raise ValueError("Snapshot requires complete valid catalog terms")
        object.__setattr__(self, "terms", _normalized(self.terms))
        return self

    def canonical_json(self) -> str:
        """Exact wire content; includes IDs, versions and all contractual terms."""
        return canonical_json(self.model_dump(mode="json"))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def create_snapshot(
    value: object,
    *,
    offer_version_id: str,
    version: int,
    model_keys: frozenset[str] = frozenset(),
) -> OfferSnapshot:
    """Validate afresh; do not trust model_copy/model_construct or preview hashes."""
    report = validate_draft(value, model_keys=model_keys)
    if not report.publishable or report.draft is None:
        raise CatalogValidationError(report.errors + report.pending)
    draft = report.draft
    if transition_errors(draft.state, "published"):
        raise CatalogValidationError((ContractIssue(("state",), "invalid_transition"),))
    return OfferSnapshot(
        contract_version=draft.contract_version, registry_version=draft.registry_version,
        plan=draft.plan,
        offer_version_id=offer_version_id,
        version=version,
        terms=draft.terms,
        eligible_model_keys=tuple(sorted(model_keys)),
    )


class Visibility(FrozenDocument):
    offer_version_id: Identifier
    state: Literal["visible", "retired"]
    revision: Positive
    valid_from: Instant
    valid_until: Instant | None = None
    retired_at: Instant | None = None

    @model_validator(mode="after")
    def valid_window(self) -> Visibility:
        if (
            self.valid_until is not None
            and self.valid_until <= self.valid_from
            or (self.state == "retired") != (self.retired_at is not None)
            or self.retired_at is not None
            and self.retired_at < self.valid_from
        ):
            raise ValueError("Invalid visibility lifecycle/window")
        return self


class PublicPrice(FrozenDocument):
    price_id: Identifier
    currency: str
    exponent: Quantity
    amount_minor: Quantity
    billing: BillingInterval


class PublicDiscount(FrozenDocument):
    discount_id: Identifier
    revision: Positive
    label: Text
    kind: Literal["percentage", "fixed"]
    basis_points: Quantity | None
    amount_minor: Quantity | None
    currency: str | None
    exponent: Quantity | None
    duration: str
    cycles: Positive | None
    price_ids: tuple[Identifier, ...]
    valid_from: Instant
    valid_until: Instant


class PublicLimit(FrozenDocument):
    meter: str
    feature: str
    kind: str
    unit: str
    amount: Quantity
    grant_kind: str | None
    reset_unit: str | None
    reset_count: Positive | None
    reset_anchor: str | None
    reset_timezone: str | None
    basis: str | None


class PublicOffer(FrozenDocument):
    contract_version: Literal["catalog.v1", "catalog.v2", "catalog.v3"] = CONTRACT_VERSION
    registry_version: Literal["catalog.features.v1", "catalog.features.v2", "catalog.features.v3"] = REGISTRY_VERSION
    plan: PlanIdentity
    offer_version_id: Identifier
    version: Positive
    fingerprint: str
    visibility_revision: Positive
    name: str
    description: str
    prices: tuple[PublicPrice, ...]
    entitlements: tuple[Entitlement, ...]
    limits: tuple[PublicLimit, ...]
    discounts: tuple[PublicDiscount, ...]
    purchasable: Literal[False] = False
    checkout_state: Literal["unavailable"] = "unavailable"


class PublicOfferV2(PublicOffer):
    resume_extraction_basis: Literal["initial_upload_or_replacement_operation"]
    pricing_mode: Literal["unconfigured", "free", "priced"]
    allowances: tuple[UsageAllowance, ...]
    presentation: tuple[FeaturePresentation, ...]
    model_selection: Literal["configured_supported_available"]
    unmetered_features: tuple[Key, ...]
    saved_answer_policy: Literal["immutable_user_entries_retain_across_resets"]


class PublicOfferV3(PublicOfferV2):
    storage_allowances: tuple[StorageAllowance, ...]
    service_benefits: tuple[ServiceBenefit, ...]


def public_projection(
    snapshot: OfferSnapshot, visibility: Visibility, *, at: datetime
) -> PublicOffer | None:
    """Project only explicit fields at a supplied time; never consult DB/clock.

    A caller's visibility document is not proof of publication. Later services
    must load trusted availability and revalidate checkout independently.
    """
    now = _instant(at)
    visibility = Visibility.model_validate(visibility.model_dump(mode="python"))
    if visibility.offer_version_id != snapshot.offer_version_id:
        raise CatalogValidationError(
            (ContractIssue(("visibility",), "offer_version_mismatch"),)
        )
    if (
        visibility.state != "visible"
        or now < visibility.valid_from
        or visibility.valid_until is not None
        and now >= visibility.valid_until
    ):
        return None
    # Revalidate even if a caller used Pydantic's unchecked copy/construct APIs.
    snapshot = OfferSnapshot.model_validate(
        dict(
            snapshot.model_dump(mode="python"),
            eligible_model_keys=snapshot.eligible_model_keys,
        )
    )
    terms = snapshot.terms
    projection = PublicOfferV3 if isinstance(terms, OfferTermsV3) else PublicOfferV2 if isinstance(terms, OfferTermsV2) else PublicOffer
    extra = {k: getattr(terms, k) for k in ("allowances", "presentation", "model_selection", "unmetered_features", "saved_answer_policy", "pricing_mode", "resume_extraction_basis")} if isinstance(terms, OfferTermsV2) else {}
    if isinstance(terms, OfferTermsV3):
        extra.update(storage_allowances=terms.storage_allowances, service_benefits=terms.service_benefits)
    return projection.model_validate(
        dict(
            **extra, contract_version=snapshot.contract_version, registry_version=snapshot.registry_version,
            plan=snapshot.plan,
            offer_version_id=snapshot.offer_version_id,
            version=snapshot.version,
            fingerprint=snapshot.fingerprint,
            visibility_revision=visibility.revision,
            name=terms.name,
            description=terms.description,
            prices=tuple(
                PublicPrice.model_validate(
                    dict(
                        price_id=p.price_id,
                        currency=p.currency,
                        exponent=p.exponent,
                        amount_minor=p.amount_minor,
                        billing=p.billing,
                    )
                )
                for p in terms.prices
            ),
            entitlements=terms.entitlements,
            limits=tuple(
                PublicLimit.model_validate(
                    dict(
                        meter=limit.meter,
                        feature=limit.feature,
                        kind=limit.kind,
                        unit=limit.unit,
                        amount=limit.amount,
                        grant_kind=limit.grant_kind,
                        reset_unit=limit.reset.unit if limit.reset else None,
                        reset_count=limit.reset.count if limit.reset else None,
                        reset_anchor=limit.reset.anchor if limit.reset else None,
                        reset_timezone=limit.reset.timezone if limit.reset else None,
                        basis=limit.basis,
                    )
                )
                for limit in terms.limits
            ),
            discounts=tuple(
                PublicDiscount.model_validate(
                    dict(
                        discount_id=d.discount_id,
                        revision=d.revision,
                        label=d.public_label,
                        kind=d.kind,
                        basis_points=d.basis_points,
                        amount_minor=d.amount_minor,
                        currency=d.currency,
                        exponent=d.exponent,
                        duration=d.duration,
                        cycles=d.cycles,
                        price_ids=d.price_ids,
                        valid_from=d.valid_from,
                        valid_until=d.valid_until,
                    )
                )
                for d in terms.discounts
                if d.public_label is not None
            ),
        )
    )
