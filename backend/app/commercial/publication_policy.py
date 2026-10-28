"""Deployment-owned explicit policy, locked through the lifecycle transaction.
No approved values or durations are supplied by this module.
"""
import hashlib
from app.commercial import catalog_contract as c
from app.commercial.review_contract import ReviewAuthority


def resolve_policy(query, subject, draft):
    row = query("SELECT public.catalog_policy_resolve(%s,%s,%s)",
                (subject, draft.terms.subscription_policy_ref, draft.terms.migration_policy_ref))
    data = row["document"]
    if set(data) != {"version", "reviewer_rule_ref", "model_registry_version", "valid_from", "valid_until", "allowed_refs"}:
        raise ValueError("Policy unavailable")
    # A permission-authorized actor may review their own content only when the
    # deployment explicitly approves that rule; no second-reviewer invention.
    if data["reviewer_rule_ref"] != "current_subscription_admin" or data["version"] != "1":
        raise ValueError("Unsupported policy")
    refs = data["allowed_refs"]
    if not isinstance(refs, list) or any(not isinstance(r, str) for r in refs):
        raise ValueError("Invalid references")
    required = [l.policy_ref for l in draft.terms.limits]
    required += [l.reset.policy_ref for l in draft.terms.limits if l.reset is not None]
    required += [r for p in draft.terms.prices for r in (p.tax_policy_ref, p.rounding_policy_ref)]
    required += [r for d in draft.terms.discounts for r in (d.eligibility_policy_ref, d.redemption_policy_ref, d.application_policy_ref)]
    if any(r is None or r not in refs for r in required):
        raise ValueError("Unapproved policy reference")
    from app.answer_models import MODEL_CATALOG
    return ReviewAuthority(policy_id=row["policy_id"],policy_version=1,
        policy_fingerprint=hashlib.sha256(c.canonical_json(data).encode()).hexdigest(),
        approval_revision=row["approval_revision"],reviewer_rule_ref=data["reviewer_rule_ref"],
        model_registry_version=data["model_registry_version"],model_keys=tuple(sorted(MODEL_CATALOG)),
        valid_from=data["valid_from"],valid_until=data["valid_until"])
