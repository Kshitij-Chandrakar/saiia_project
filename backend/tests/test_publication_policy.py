"""Explicit policy approval must include the top-level lifecycle references."""
from datetime import timedelta
from uuid import uuid4

import pytest
from app.commercial import catalog_contract as c
from app.commercial.publication_policy import resolve_policy
from test_catalog_contract import document, AT


@pytest.mark.parametrize("missing", [None, "subscription_policy_ref", "migration_policy_ref"])
def test_top_level_policy_references_require_explicit_approval(missing):
    draft = c.CatalogDraft.model_validate(document())
    refs = [draft.terms.subscription_policy_ref, draft.terms.migration_policy_ref]
    refs += [limit.policy_ref for limit in draft.terms.limits]
    refs += [limit.reset.policy_ref for limit in draft.terms.limits if limit.reset]
    refs += [ref for price in draft.terms.prices for ref in (price.tax_policy_ref, price.rounding_policy_ref)]
    refs += [ref for discount in draft.terms.discounts for ref in (
        discount.eligibility_policy_ref, discount.redemption_policy_ref, discount.application_policy_ref)]
    refs = [ref for ref in refs if ref is not None]
    if missing:
        refs.remove(getattr(draft.terms, missing))
    calls = []

    def query(sql, params):
        calls.append(params)
        return dict(policy_id=str(uuid4()), approval_revision="1", document=dict(
            version="1", reviewer_rule_ref="current_subscription_admin",
            model_registry_version="synthetic.models.v1", valid_from=AT.isoformat(),
            valid_until=(AT + timedelta(days=1)).isoformat(), allowed_refs=refs))

    if missing:
        with pytest.raises(ValueError, match="Unapproved policy reference"):
            resolve_policy(query, "synthetic-actor", draft)
    else:
        assert resolve_policy(query, "synthetic-actor", draft).policy_version == 1
    assert calls == [("synthetic-actor", draft.terms.subscription_policy_ref, draft.terms.migration_policy_ref)]
