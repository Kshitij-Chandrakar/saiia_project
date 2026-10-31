"""Internal review evidence, not approval policy, publication or access authority."""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.commercial import catalog_contract as c

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class AuthorityBinding(c.FrozenDocument):
    policy_id: c.Identifier
    policy_version: c.Positive
    policy_fingerprint: Digest
    approval_revision: c.Positive
    reviewer_rule_ref: c.Key
    model_registry_version: c.Key
    model_fingerprint: Digest
    valid_from: c.Instant
    valid_until: c.Instant

    @model_validator(mode="after")
    def window(self) -> AuthorityBinding:
        if self.valid_until <= self.valid_from:
            raise ValueError("Invalid review authority window")
        return self


class ReviewAuthority(c.FrozenDocument):
    """ONLY supplied by an injected trusted resolver, never request authority.

    The resolver must verify all draft policy references/reviewer rules, supply
    explicit validity bounds and hold authoritative policy locks until commit.
    No production resolver/default approval/duration exists in F1.
    """

    policy_id: c.Identifier
    policy_version: c.Positive
    policy_fingerprint: Digest
    approval_revision: c.Positive
    reviewer_rule_ref: c.Key
    model_registry_version: c.Key
    model_keys: tuple[str, ...]
    valid_from: c.Instant
    valid_until: c.Instant

    def binding(self) -> AuthorityBinding:
        data = self.model_dump(mode="python", exclude={"model_keys"})
        data["model_fingerprint"] = hashlib.sha256(
            c.canonical_json(sorted(set(self.model_keys))).encode("utf-8")
        ).hexdigest()
        return AuthorityBinding.model_validate(data)


class ReviewIntent(c.FrozenDocument):
    action: Literal["publish", "replace"]
    valid_from: c.Instant
    valid_until: c.Instant | None = None

    @model_validator(mode="after")
    def window(self) -> ReviewIntent:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("Invalid proposed visibility window")
        return self


class OfferReference(c.FrozenDocument):
    offer_version_id: c.Identifier
    visibility_revision: c.Positive
    fingerprint: Digest


class ReviewBasis(c.FrozenDocument):
    protocol: Literal["catalog.review.v1"] = "catalog.review.v1"
    contract_version: Literal["catalog.v1", "catalog.v2", "catalog.v3"] = "catalog.v1"
    registry_version: Literal["catalog.features.v1", "catalog.features.v2", "catalog.features.v3"] = "catalog.features.v1"
    validation_policy_version: Literal["catalog.validation.v1", "catalog.validation.v2", "catalog.validation.v3"] = (
        "catalog.validation.v1"
    )
    draft_id: c.Identifier
    plan_id: c.Identifier
    revision: c.Positive
    source_hash: Digest
    terms_fingerprint: Digest
    authority: AuthorityBinding
    intent: ReviewIntent
    current_offer: OfferReference | None
    archived_offer: OfferReference | None

    @model_validator(mode="after")
    def versions_match(self):
        version = self.contract_version.rsplit("v", 1)[-1]
        if self.registry_version != "catalog.features.v" + version or self.validation_policy_version != "catalog.validation.v" + version:
            raise ValueError("Incompatible review versions")
        return self


class ReviewReceipt(c.FrozenDocument):
    storage_version: Literal["catalog.review.store.v1"] = "catalog.review.store.v1"
    review_id: c.Identifier
    reviewer_subject: c.Identifier
    permission_revision: c.Positive
    recorded_at: c.Instant
    basis: ReviewBasis


ReviewState = Literal[
    "current",
    "draft_changed",
    "draft_terminal",
    "expired",
    "authority_changed",
    "authority_unavailable",
    "head_changed",
]


class ReviewEvidence(c.FrozenDocument):
    """Fresh assessment plus immutable evidence; NEVER a publication permit.

    F2 must recheck actor, source/authority/head/expiry and consumption in the
    SAME publication transaction, recompute snapshot, then atomically write
    publication/provenance/audit/receipt. A completed F1 read cannot authorize it.
    """

    receipt: ReviewReceipt
    state: ReviewState
    publication_enabled: Literal[False] = False
    # F1 observation is not an F2 consumption lookup or publication permit.
    consumption_state: Literal["not_checked"] = "not_checked"
