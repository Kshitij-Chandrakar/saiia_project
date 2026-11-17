"""Actual native RPC regressions. Fixture writes use owner; assertions use restricted LOGINs."""

import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from app.privacy_registry import VERSION


def verify_review_fixes(r, actor, results):
    subject = r.user()["id"]
    now = datetime.now(timezone.utc)

    def rpc(role, function, args):
        with r.connect(role) as c:
            return c.execute(
                "select public." + function + "(" + ",".join(["%s"] * len(args)) + ")",
                args,
            ).fetchone()[0]

    def command(action, doc):
        return rpc(
            "admin_dispatch_executor",
            "administration_command",
            (action, json.dumps(doc)),
        )

    def work(action, doc):
        return rpc(
            "admin_dispatch_executor",
            "administration_campaign_work",
            (action, json.dumps(doc)),
        )

    def lifecycle():
        return rpc("admin_retention_executor", "administration_lifecycle", (100,))

    with r.connect() as c:
        revision = c.execute(
            "select revision from administration.memberships where subject=%s", (actor,)
        ).fetchone()[0]
        # Existing receipt of another action cannot authorize a new membership request.
        operation, review = uuid4(), uuid4()
        c.execute(
            "insert into administration.receipts(id,actor,review_id,action,target,revision,state) values(%s,%s,%s,'access.restrict',%s,1,'confirmed')",
            (operation, actor, review, subject),
        )
    value = rpc(
        "admin_executor",
        "administration_call",
        (
            actor,
            uuid4(),
            now,
            "membership.review",
            json.dumps(
                {
                    "target": subject,
                    "role": "admin",
                    "status": "active",
                    "reason": "membership",
                    "operation_id": str(operation),
                }
            ),
        ),
    )
    assert value["error"] == "conflict", value
    operation2 = uuid4()
    session = uuid4()
    reviewed = rpc(
        "admin_executor",
        "administration_call",
        (
            actor,
            session,
            now,
            "membership.review",
            json.dumps(
                {
                    "target": subject,
                    "role": "admin",
                    "status": "active",
                    "reason": "membership",
                    "operation_id": str(operation2),
                }
            ),
        ),
    )
    assert "review_id" in reviewed, reviewed
    with r.connect() as c:
        c.execute(
            "insert into administration.receipts(id,actor,review_id,action,target,revision,state) values(%s,%s,%s,'access.restrict',%s,1,'confirmed')",
            (operation2, actor, uuid4(), subject),
        )
    collided = rpc(
        "admin_executor",
        "administration_call",
        (
            actor,
            session,
            now,
            "membership.confirm",
            json.dumps({"review_id": reviewed["review_id"], "confirm": True}),
        ),
    )
    assert collided["error"] == "conflict", collided
    # Session cleanup has no account-deletion row; it must still be discoverable.
    with r.connect() as c:
        job = uuid4()
        c.execute(
            "insert into public.privacy_content_jobs(id,account_id,kind,state,blockers,registry_version) values(%s,%s,'history','blocked','[\"storage_unavailable\"]',%s)",
            (job, subject, VERSION),
        )
    value = rpc(
        "admin_executor", "administration_read", (actor, "privacy", subject, None, "")
    )
    assert value["requests"] == [] and any(
        row["task_id"] == str(job) and row["retry_available"] for row in value["tasks"]
    ), value
    # A result already dispatched survives loss of staff authority.
    with r.connect() as c:
        command_id, lease = uuid4(), uuid4()
        c.execute(
            "insert into administration.commands(id,actor,actor_revision,target,billing_id,reason,state,lease,lease_until,attempts,dispatched) values(%s,%s,%s,%s,%s,'support','running',%s,clock_timestamp()+interval '1 minute',1,true)",
            (command_id, actor, revision - 1, subject, uuid4(), lease),
        )
    assert (
        command(
            "finish",
            {"id": str(command_id), "lease": str(lease), "outcome": "confirmed"},
        )["state"]
        == "confirmed"
    )
    # The last crashed lease becomes explicit unknown; it cannot stay running forever.
    with r.connect() as c:
        exhausted = uuid4()
        c.execute(
            "insert into administration.commands(id,actor,actor_revision,target,billing_id,reason,state,lease,lease_until,attempts,dispatched) values(%s,%s,%s,%s,%s,'support','running',%s,clock_timestamp()-interval '1 minute',5,true)",
            (exhausted, actor, revision, subject, uuid4(), uuid4()),
        )
    command("claim", {})
    with r.connect() as c:
        assert c.execute(
            "select state,lease from administration.commands where id=%s", (exhausted,)
        ).fetchone() == ("unknown", None)
    # Provider acknowledgement records fact despite dispatch-time eligibility changes.
    campaign, audience, delivery, lease, event = [uuid4() for _ in range(5)]
    with r.connect() as c:
        c.execute(
            "insert into administration.campaigns(id,name,subject,body,state,author) values(%s,'Review regression','Synthetic','Synthetic','queued',%s)",
            (campaign, actor),
        )
        c.execute(
            "insert into administration.audience_reviews(id,campaign_id,revision,actor,actor_revision,session_id,recipient_count,references_until) values(%s,%s,1,%s,%s,%s,1,clock_timestamp()-interval '1 second')",
            (audience, campaign, actor, revision, uuid4()),
        )
        c.execute(
            "insert into administration.campaign_deliveries(id,campaign_id,review_id,account_id,state,lease,lease_until,event_id) values(%s,%s,%s,%s,'sending',%s,clock_timestamp()+interval '1 minute',%s)",
            (delivery, campaign, audience, subject, lease, event),
        )
    assert (
        work(
            "finish",
            {
                "id": str(delivery),
                "lease": str(lease),
                "state": "accepted",
                "event_id": None,
                "message_id": None,
            },
        )["state"]
        == "accepted"
    )
    with r.connect() as c:
        assert c.execute(
            "select state,event_id from administration.campaign_deliveries where id=%s",
            (delivery,),
        ).fetchone() == ("accepted", event)
        obsolete, obsolete_review = uuid4(), uuid4()
        c.execute(
            "insert into administration.campaigns(id,name,subject,body,revision,author) values(%s,'Edited draft','Synthetic','Synthetic',2,%s)",
            (obsolete, actor),
        )
        c.execute(
            "insert into administration.audience_reviews(id,campaign_id,revision,actor,actor_revision,session_id,recipient_count,references_until) values(%s,%s,1,%s,%s,%s,1,clock_timestamp()-interval '1 second')",
            (obsolete_review, obsolete, actor, revision, uuid4()),
        )
        c.execute(
            "update administration.commands set created_at=clock_timestamp()-interval '181 days' where id=%s",
            (command_id,),
        )
    lifecycle()
    with r.connect() as c:
        assert c.execute(
            "select state from administration.campaigns where id=%s", (obsolete,)
        ).fetchone() == ("draft",)
        assert not c.execute(
            "select exists(select 1 from administration.campaign_fences where id=%s)",
            (obsolete,),
        ).fetchone()[0]
        assert c.execute(
            "select state from administration.commands where id=%s", (command_id,)
        ).fetchone() == ("confirmed",)
        coupon = uuid4()
        c.execute(
            "insert into administration.coupon_requests(id,actor,coupon_id,expected,code,resulting_revision,recorded_at) values(%s,%s,%s,0,'INERT',1,clock_timestamp()-interval '181 days')",
            (coupon, actor, uuid4()),
        )
    retired = rpc("admin_retention_executor", "administration_retention", (100,))
    assert retired["coupons"] == 1, retired
    # Expired delivery leases finish their campaign even with no next claim.
    campaign2, review2 = uuid4(), uuid4()
    with r.connect() as c:
        c.execute(
            "insert into administration.campaigns(id,name,subject,body,state,author) values(%s,'Lease recovery','Synthetic','Synthetic','queued',%s)",
            (campaign2, actor),
        )
        for state, attempts in [("sending", 1), ("running", 5)]:
            c.execute(
                "insert into administration.campaign_deliveries(campaign_id,review_id,account_id,state,lease,lease_until,attempts) values(%s,%s,%s,%s,%s,clock_timestamp()-interval '1 minute',%s)",
                (campaign2, review2, uuid4(), state, uuid4(), attempts),
            )
    work("claim", {})
    with r.connect() as c:
        assert c.execute(
            "select state from administration.campaigns where id=%s", (campaign2,)
        ).fetchone() == ("complete",)
        assert set(
            row[0]
            for row in c.execute(
                "select state from administration.campaign_deliveries where campaign_id=%s",
                (campaign2,),
            ).fetchall()
        ) == {"failed", "unknown"}
    # Retention cannot claim old erased population history is complete.
    value = rpc(
        "admin_executor",
        "administration_metrics",
        (actor, now - timedelta(days=180), now - timedelta(days=170), "UTC"),
    )
    assert (
        value["total_users"] is None
        and value["new_users"] is None
        and value["growth_percent"] is None
        and value["daily_registrations"] == []
    ), value
    # Acceptance must still hold the exact transferred role/revision at verification.
    from c15_admin_acceptance import verify_totp

    successor = r.user()
    verify_totp(r, successor)

    def transfer(who, action, document):
        return rpc(
            "admin_executor",
            "administration_successor",
            (who, uuid4(), datetime.now(timezone.utc), action, json.dumps(document)),
        )

    offered = transfer(actor, "offer", {"target": successor["id"], "confirm": True})
    assert (
        transfer(
            successor["id"],
            "accept",
            {"transfer_id": offered["transfer_id"], "confirm": True},
        )["state"]
        == "accepted"
    )
    with r.connect() as c:
        c.execute(
            "update administration.memberships set role='admin',revision=revision+1 where subject=%s",
            (successor["id"],),
        )
    assert (
        rpc(
            "admin_executor",
            "administration_call",
            (successor["id"], None, None, "me", "{}"),
        )["role"]
        == "admin"
    )
    assert not transfer(actor, "status", {"transfer_id": offered["transfer_id"]})[
        "successor_access_verified"
    ]
    with r.connect() as c:
        c.execute(
            "update administration.memberships set role='super_admin',revision=revision+1 where subject=%s",
            (successor["id"],),
        )
    assert (
        rpc(
            "admin_executor",
            "administration_call",
            (successor["id"], None, None, "me", "{}"),
        )["role"]
        == "super_admin"
    )
    assert not transfer(actor, "status", {"transfer_id": offered["transfer_id"]})[
        "successor_access_verified"
    ]
    # Restore replay preserves an already active restriction.
    with r.connect() as c:
        c.execute(
            "insert into administration.customer_access(subject,restricted,revision) values(%s,true,3)",
            (subject,),
        )
    with r.connect("admin_restore_executor") as c:
        state = c.execute(
            "select public.administration_restore('capture','{}')"
        ).fetchone()[0]
        for row in state["restrictions"]:
            if row["subject"] == subject:
                row["restricted"], row["revision"] = False, 1
        c.execute(
            "select public.administration_restore('replay',%s::jsonb)",
            (json.dumps(state),),
        )
    with r.connect() as c:
        assert c.execute(
            "select restricted,revision from administration.customer_access where subject=%s",
            (subject,),
        ).fetchone() == (True, 3)
    results.append(
        {
            "scenario": "review_request_bindings_jobs_worker_recovery_retention_and_restore",
            "passed": True,
        }
    )
