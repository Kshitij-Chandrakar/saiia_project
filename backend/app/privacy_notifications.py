"""Privacy templates on the existing durable transactional-email contract."""

from app.privacy_content import ContentBlocked

TEMPLATES = {
    "accepted": (
        "privacy_request_accepted",
        "Your deletion request was accepted",
        "Your request was accepted and product access restricted. This notice does not verify cleanup completion.",
    ),
    "primary_verified": (
        "privacy_primary_verified",
        "Your personal-content cleanup status",
        "Removal from controlled primary stores is verified. Retained obligations remain pending.",
    ),
    "attention_required": (
        "privacy_attention_required",
        "Your privacy request needs follow-up",
        "Your request requires follow-up. Completion has not been verified.",
    ),
}
EXCEPTIONS = (
    " This is not confirmation of erasure from backups, processors or offline devices. "
    "Minimum billing and approved retained metadata may remain. Subscription cancellation is not confirmed by this notice; "
    "further charges may remain possible. Already downloaded files cannot be recalled."
)


class PrivacyNotifier:
    def __init__(self, engine, email_service):
        self.engine, self.email_service = engine, email_service

    def notify(self, account, stage):
        if stage not in TEMPLATES:
            raise ContentBlocked("notification_state_unverified")
        with self.engine.transaction() as c:
            c.execute(
                "select r.request_id,u.email,coalesce(j.state,'pending'),coalesce(j.revision,0) from privacy_deletion_requests r join auth.users u on u.id=r.account_id left join privacy_content_jobs j on j.id=r.request_id where r.account_id=%s and r.state='accepted_restricted' and to_jsonb(u)->>'deleted_at' is null",
                (account,),
            )
            row = c.fetchone()
            if not row or stage == "primary_verified" and row[2] != "primary_verified":
                raise ContentBlocked("notification_state_unverified")
            if stage == "attention_required" and row[2] not in ("blocked", "failed"):
                c.execute(
                    "select 1 from privacy_followup_tasks where request_id=%s and (state='blocked' or kind='billing_review' and due_at<=clock_timestamp()) limit 1",
                    (row[0],),
                )
                if not c.fetchone():
                    raise ContentBlocked("notification_state_unverified")
            request, email, _, _revision = row
        kind, subject, body = TEMPLATES[stage]
        # No provider is composed here. Tests inject the existing dry-run provider
        # and event-store contract; production activation stays disabled.
        return self.email_service.send_transactional_email(
            recipient_email=email,
            subject=subject,
            email_type=kind,
            text_body=body + EXCEPTIONS,
            user_id=account,
            idempotency_key=f"privacy.{request}.{stage}",
            safe_metadata={"privacy_request": str(request), "privacy_state": stage},
        )
