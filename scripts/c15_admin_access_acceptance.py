"""Native fixed-operation access-axis acceptance; owner is fixture/observer only."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import psycopg


def verify_access(r, super_admin, admin, customer, other, results, source_restore):
    now = datetime.now(timezone.utc)
    session = uuid4()

    def call(actor, action, doc, own_session=session):
        with r.connect("admin_executor") as c:
            return c.execute(
                "select public.administration_access(%s,%s,%s,%s,%s::jsonb)",
                (actor, own_session, now, action, json.dumps(doc)),
            ).fetchone()[0]

    def review(actor, target, restricted=True):
        return call(
            actor,
            "review",
            {
                "target": target,
                "restricted": restricted,
                "reason": "support",
                "operation_id": str(uuid4()),
            },
        )

    def confirm(actor, v):
        return call(
            actor, "confirm", {"review_id": str(v["review_id"]), "confirm": True}
        )

    from c15_admin_acceptance import verify_totp

    staff = r.user()
    staff_proof = verify_totp(r, staff)
    admin = staff["id"]
    customer_identity, other_identity = r.user(), r.user()
    customer, other = customer_identity["id"], other_identity["id"]
    from c15_actual_engines import ActualStorage

    store = ActualStorage(r)
    key = customer + "/" + str(uuid4()) + "/synthetic.txt"
    assert (
        store.request("POST", "/object/resumes/" + key, data=b"SYNTHETIC").status_code
        == 200
    )
    with r.connect() as c:
        c.execute(
            "insert into administration.memberships(subject,role,status,revision) values(%s,'admin','active',1)",
            (admin,),
        )
        before = c.execute("select count(*) from public.billing_operations").fetchone()
    for role in ("admin_executor", "admin_bootstrap_executor"):
        for statement in (
            "select * from administration.customer_access",
            "delete from administration.access_reviews",
            "truncate administration.customer_access",
        ):
            try:
                with r.connect(role) as c:
                    c.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                raise AssertionError("direct access permitted")
    assert review(admin, super_admin)["error"] == "not_found"
    assert review(admin, customer, False)["error"] == "not_found"
    v = review(admin, customer)
    assert "review_id" in v, v
    assert (
        call(admin, "confirm", {"review_id": v["review_id"], "confirm": True}, uuid4())[
            "error"
        ]
        == "conflict"
    )
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _: confirm(admin, v), range(2)))
    assert all(x["state"] == "confirmed" for x in outcomes), outcomes
    assert outcomes[0]["revision"] == outcomes[1]["revision"] == "1"
    assert outcomes[0] == outcomes[1]
    assert (
        store.request(
            "GET", "/object/resumes/" + key, customer_identity["access_token"]
        ).status_code
        != 200
    )
    assert (
        store.request(
            "POST",
            "/object/resumes/" + customer + "/" + str(uuid4()) + "/late.txt",
            data=b"LATE",
        ).status_code
        != 200
    )
    from app.administration import configured, router
    from app.config import settings
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    source_restore.publish()
    app = FastAPI()
    app.include_router(router)
    app.state.administration = configured(settings)
    with TestClient(app) as client:
        assert (
            client.get(
                "/api/admin/me",
                headers={
                    "Authorization": "Bearer " + customer_identity["access_token"]
                },
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/admin/me",
                headers={"Authorization": "Bearer " + other_identity["access_token"]},
            ).status_code
            == 404
        )
    with r.connect() as c:
        try:
            c.execute(
                "insert into public.profiles(user_id,full_name) values(%s,'Synthetic blocked profile')",
                (customer,),
            )
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise AssertionError("late profile bootstrap permitted")
    with r.connect("admin_executor") as c:
        assert c.execute(
            "select public.administration_product_access(%s)", (customer,)
        ).fetchone() == (False,)
        assert c.execute(
            "select public.administration_product_access(%s)", (other,)
        ).fetchone() == (True,)
    with r.connect("usage_executor") as c:
        try:
            c.execute("select public.subscription_access_check(%s)", (customer,))
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise AssertionError("restricted usage admitted")
    # Promotion reviews cannot activate an already staff-restricted customer.
    with r.connect("admin_executor") as c:
        refused = c.execute(
            "select public.administration_call(%s,%s,%s,'membership.review',%s::jsonb)",
            (
                super_admin,
                session,
                now,
                json.dumps(
                    {
                        "target": customer,
                        "role": "admin",
                        "status": "active",
                        "reason": "membership",
                        "operation_id": str(uuid4()),
                    }
                ),
            ),
        ).fetchone()[0]
        assert refused["error"] == "invalid", refused
    restored = confirm(super_admin, review(super_admin, customer, False))
    assert restored["state"] == "confirmed"
    assert (
        store.request(
            "GET", "/object/resumes/" + key, customer_identity["access_token"]
        ).status_code
        == 200
    )
    with r.connect("admin_executor") as c:
        assert c.execute(
            "select public.administration_product_access(%s)", (customer,)
        ).fetchone() == (True,)
    with r.connect() as c:
        assert (
            c.execute("select count(*) from public.billing_operations").fetchone()
            == before
        )
        assert c.execute(
            "select revision from administration.customer_access where subject=%s",
            (customer,),
        ).fetchone() == (2,)
        c.execute(
            "insert into public.subscription_deletion_jobs(account_id,request_id) values(%s,%s)",
            (customer, uuid4()),
        )
    # Clearing the staff axis never clears a separately accepted C15 barrier.
    assert (
        confirm(super_admin, review(super_admin, customer, False))["state"]
        == "confirmed"
    )
    with r.connect("admin_executor") as c:
        assert c.execute(
            "select public.administration_product_access(%s)", (customer,)
        ).fetchone() == (False,)
    race_target = r.user()["id"]
    restricted = review(admin, race_target)
    with r.connect("admin_executor") as c:
        promotion = c.execute(
            "select public.administration_call(%s,%s,%s,'membership.review',%s::jsonb)",
            (
                super_admin,
                session,
                now,
                json.dumps(
                    {
                        "target": race_target,
                        "role": "admin",
                        "status": "active",
                        "reason": "membership",
                        "operation_id": str(uuid4()),
                    }
                ),
            ),
        ).fetchone()[0]

    def promote():
        with r.connect("admin_executor") as c:
            return c.execute(
                "select public.administration_call(%s,%s,%s,'membership.confirm',%s::jsonb)",
                (
                    super_admin,
                    session,
                    now,
                    json.dumps({"review_id": promotion["review_id"], "confirm": True}),
                ),
            ).fetchone()[0]

    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(confirm, admin, restricted)
        b = pool.submit(promote)
        race = [a.result(), b.result()]
    assert sum(x.get("state") == "confirmed" for x in race) == 1, race
    with r.connect() as c:
        assert not c.execute(
            "select exists(select 1 from administration.customer_access a join administration.memberships m on m.subject=a.subject where a.subject=%s and a.restricted and m.status='active')",
            (race_target,),
        ).fetchone()[0]
    verify_retry(r, admin, staff_proof, results, source_restore)
    verify_retention(r, admin, customer, v, confirm, results)
    results.append(
        {
            "scenario": "staff_access_restrict_restore_roles_target_binding_concurrent_replay_direct_permissions_billing_unchanged",
            "passed": True,
        }
    )


def verify_retry(r, admin, proof, results, source_restore):
    from app.administration import configured, router
    from app.config import settings
    from app.privacy_content import ContentEngine
    from app.privacy_runtime_db import RuntimeConnection
    from c15_actual_engines import ActualStorage
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from psycopg import sql

    owner = r.user()["id"]
    with r.connect() as c:
        c.execute(
            sql.SQL("alter role privacy_content_executor login password {}").format(
                sql.Literal(r.password)
            )
        )
    engine = ContentEngine(
        lambda: RuntimeConnection(
            r.connect("privacy_content_executor"), "privacy_content_executor"
        ),
        ActualStorage(r),
        local_rehearsal=True,
    )
    task = str(uuid4())
    engine.request(owner, task, "history")
    with r.connect() as c:
        c.execute(
            "update privacy_content_jobs set state='blocked',attempts=1,blockers='[\"storage_forbidden_not_absence\"]'::jsonb where id=%s",
            (task,),
        )
        revision = c.execute(
            "select revision from privacy_content_jobs where id=%s", (task,)
        ).fetchone()[0]
    source_restore.publish()
    app = FastAPI()
    app.include_router(router)
    app.state.administration = configured(settings)
    headers = {"Authorization": "Bearer " + proof["access_token"]}
    with TestClient(app) as client:
        doc = {
            "task_id": task,
            "revision": str(revision),
            "reason": "support",
            "operation_id": str(uuid4()),
        }
        with r.connect() as c:
            c.execute(
                "update privacy_content_jobs set lease_id=%s,lease_until=clock_timestamp()+interval '1 minute' where id=%s",
                (uuid4(), task),
            )
        assert (
            client.post(
                "/api/admin/privacy-retries/review", json=doc, headers=headers
            ).status_code
            == 409
        )
        with r.connect() as c:
            c.execute(
                "update privacy_content_jobs set lease_id=null,lease_until=null where id=%s",
                (task,),
            )
            unit = c.execute(
                "insert into privacy_retirement_units(account_id,category) values(%s,'unclassified') returning unit_id",
                (owner,),
            ).fetchone()[0]
            c.execute(
                "insert into privacy_retirement_holds(unit_id,reason,review_at,active,revision) values(%s,'operational',clock_timestamp()+interval '7 days',true,1)",
                (unit,),
            )
        assert (
            client.post(
                "/api/admin/privacy-retries/review", json=doc, headers=headers
            ).status_code
            == 409
        )
        with r.connect() as c:
            c.execute(
                "update privacy_retirement_holds set active=false,revision=revision+1 where unit_id=%s",
                (unit,),
            )
        assert (
            client.post(
                "/api/admin/privacy-retries/review",
                json={**doc, "revision": str(revision + 1)},
                headers=headers,
            ).status_code
            == 409
        )
        denied = client.post(
            "/api/admin/privacy-retries/review",
            json={**doc, "scope": "account"},
            headers=headers,
        )
        assert denied.status_code == 400, denied.text
        reviewed = client.post(
            "/api/admin/privacy-retries/review", json=doc, headers=headers
        )
        assert reviewed.status_code == 200, reviewed.text
        confirmation = {"review_id": reviewed.json()["review_id"], "confirm": True}
        accepted = client.post(
            "/api/admin/privacy-retries/confirm", json=confirmation, headers=headers
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["state"] == "queued"
        assert (
            client.post(
                "/api/admin/privacy-retries/confirm", json=confirmation, headers=headers
            ).json()
            == accepted.json()
        )
    assert engine.run_one()
    with r.connect() as c:
        state = c.execute(
            "select state from privacy_content_jobs where id=%s", (task,)
        ).fetchone()[0]
        assert state == "primary_verified", state
        before = c.execute("select count(*) from privacy_content_jobs").fetchone()[0]
    with TestClient(app) as client:
        unavailable = client.post(
            "/api/admin/privacy-retries/review",
            json={**doc, "operation_id": str(uuid4())},
            headers=headers,
        )
        assert unavailable.status_code == 409, unavailable.text
    with r.connect() as c:
        assert (
            c.execute("select count(*) from privacy_content_jobs").fetchone()[0]
            == before
        )
    results.append(
        {
            "scenario": "exact_task_retry_actual_http_replay_scope_denial_restricted_worker_primary_verification",
            "passed": True,
        }
    )


def verify_retention(r, actor, target, consumed_review, confirm, results):
    expired, held, live = uuid4(), uuid4(), uuid4()
    with r.connect() as c:
        for event, days in ((expired, 181), (held, 181), (live, 179)):
            c.execute(
                "insert into administration.audit(id,action,role_at_action,outcome,correlation,recorded_at,expires_at) values(%s,'synthetic.retention','admin','confirmed',%s,clock_timestamp()-%s*interval '1 day',clock_timestamp()+(180-%s)*interval '1 day')",
                (event, uuid4(), days, days),
            )
            c.execute(
                "insert into administration.audit_references(event,actor,target) values(%s,%s,%s)",
                (event, actor, target),
            )
        c.execute(
            "insert into administration.retention_holds values('audit',%s,'security',true,clock_timestamp()+interval '7 days')",
            (held,),
        )
    for role in ("admin_executor", "admin_bootstrap_executor"):
        try:
            with r.connect(role) as c:
                c.execute("select public.administration_retention(100)")
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise AssertionError("ordinary role performed maintenance")
    with r.connect("admin_retention_executor") as c:
        retained = c.execute("select public.administration_retention(100)").fetchone()[
            0
        ]
        assert retained["audit"] >= 1
    with r.connect() as c:
        assert c.execute(
            "select count(*) from administration.audit where id=%s", (expired,)
        ).fetchone() == (0,)
        assert c.execute(
            "select count(*) from administration.audit_references where event=%s",
            (expired,),
        ).fetchone() == (0,)
        assert c.execute(
            "select count(*) from administration.audit where id=any(%s)",
            ([held, live],),
        ).fetchone() == (2,)
        assert c.execute(
            "select count(*) from administration.access_reviews where id=%s",
            (consumed_review["review_id"],),
        ).fetchone() == (0,)
    # Removed confirmation references cannot reapply a stale restriction, but own
    # accepted receipts still recover the outcome without disclosing staff history.
    recovered = confirm(actor, consumed_review)
    assert recovered["state"] == "confirmed"
    with r.connect() as c:
        assert c.execute(
            "select restricted from administration.customer_access where subject=%s",
            (target,),
        ).fetchone() == (False,)

    def run():
        with r.connect("admin_retention_executor") as c:
            return c.execute("select public.administration_retention(100)").fetchone()[
                0
            ]

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(lambda _: run(), range(2)))
    assert all(x["audit"] == 0 for x in outcomes)
    try:
        with r.connect("admin_retention_executor") as c:
            c.execute("select public.administration_retention(null)")
    except psycopg.errors.InvalidParameterValue:
        pass
    else:
        raise AssertionError("unbounded retention accepted")
    results.append(
        {
            "scenario": "restricted_admin_retention_180_day_clock_hold_dependencies_confirmation_removal_receipt_recovery_concurrent_workers",
            "passed": True,
        }
    )
