"""Local-only disposable verification of the exact prepared staging SQL batch."""

import argparse
import hashlib
import json
from pathlib import Path

from app.commercial.catalog_store import RpcFailure
from test_catalog_store_native import Native, literal

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "C11_C13_STAGING_cfmvqbjmnwklxqlpelxe"


def check(pg_bin, owner_mode="superuser"):
    db = Native(pg_bin)
    try:
        # Supabase platform interfaces only, not hosted platform acceptance.
        db.run("""
        create role anon;create role authenticated;create role service_role bypassrls;
        create role authenticator login noinherit;
        create schema auth;create schema storage;create schema extensions;
        create table auth.users(id uuid primary key,created_at timestamptz default now(),email_confirmed_at timestamptz);
        create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
        create function auth.role() returns text language sql stable as $$select current_setting('request.jwt.claim.role',true)$$;
        create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
        create table storage.objects(id uuid primary key,bucket_id text,name text);
        alter table storage.objects enable row level security;
        create function storage.foldername(text) returns text[] language sql as $$select string_to_array($1,'/')$$;
        grant usage on schema auth,storage,public to anon,authenticated,service_role;
        alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
        alter default privileges in schema public grant execute on functions to anon,authenticated,service_role;
        """)
        if owner_mode != "superuser":
            bypass = "nobypassrls" if owner_mode == "missing-bypass" else "bypassrls"
            db.run(f"""
            create role migration_owner login nosuperuser nocreatedb createrole noreplication inherit {bypass};
            create role platform_storage_owner nologin;
            create extension if not exists pgcrypto with schema extensions;
            grant create on database postgres to migration_owner;
            alter schema public owner to migration_owner;
            grant usage on schema auth,extensions,storage to migration_owner;
            grant select,references on auth.users to migration_owner;
            alter table storage.buckets owner to platform_storage_owner;
            alter table storage.objects owner to platform_storage_owner;
            grant insert,update,select on storage.buckets to migration_owner;
            """)
            if owner_mode != "missing-storage":
                db.run(
                    "grant platform_storage_owner to migration_owner with inherit true,set false,admin false"
                )
            db.args[db.args.index("-U") + 1] = "migration_owner"
        owner = json.loads(
            db.run(
                (ROOT / "docs/sql" / (PREFIX + "_OWNER_PREFLIGHT.sql")).read_text(
                    encoding="utf-8"
                )
            )
        )
        if owner_mode != "superuser":
            assert (
                not owner["identity"]["rolsuper"] and owner["identity"]["rolcreaterole"]
            )
            assert owner["identity"]["rolbypassrls"] == (owner_mode != "missing-bypass")
            storage_owner = next(
                row
                for row in owner["platform_ownership"]
                if row["object_name"] == "storage.objects"
            )
            assert storage_owner["inherited_owner_authority"] == (
                owner_mode != "missing-storage"
            )
        storage_preflight = json.loads(
            db.run(
                (
                    ROOT / "docs/sql" / (PREFIX + "_STORAGE_POLICY_PREFLIGHT.sql")
                ).read_text(encoding="utf-8")
            )
        )
        assert (
            storage_preflight["read_only"] == "on"
            and not storage_preflight["behavior_verified"]
        )
        assert storage_preflight["supautils_settings"] == []
        assert storage_preflight["policy_ddl_route"] == (
            "UNVERIFIED_STOP_NO_WRITES"
            if owner_mode == "missing-storage"
            else "STANDARD_OWNER_AUTHORITY"
        )
        platform_query = "select relowner::text,relrowsecurity,relforcerowsecurity from pg_class where oid='storage.objects'::regclass"
        policy_query = "select polname,polpermissive,polcmd,polroles::text,pg_get_expr(polqual,polrelid) qual,pg_get_expr(polwithcheck,polrelid) check_expr from pg_policy where polrelid='storage.objects'::regclass order by polname"
        membership_query = "select roleid::text,member::text,admin_option,inherit_option,set_option from pg_auth_members order by roleid,member"
        before_policy_trial = [
            db.rows(q) for q in (platform_query, policy_query, membership_query)
        ]
        policy_trial = (
            ROOT
            / "docs/sql"
            / (PREFIX + "_STORAGE_POLICY_ROLLBACK_PROBE_PENDING_APPROVAL.sql")
        ).read_text(encoding="utf-8")
        if owner_mode == "missing-storage":
            try:
                db.run(policy_trial)
                raise AssertionError(
                    "plain PostgreSQL without owner/hook must reject policy DDL"
                )
            except RpcFailure as error:
                assert error.sqlstate == "42501"
        else:
            db.run(policy_trial)
        assert not db.rows(
            "select 1 from pg_policy where polrelid='storage.objects'::regclass and polname='c132_staging_policy_authority_probe'"
        )
        assert [
            db.rows(q) for q in (platform_query, policy_query, membership_query)
        ] == before_policy_trial
        print(
            f"PASS ({owner_mode}): policy DDL rollback probe/negative check; no probe policy retained"
        )
        batch = (
            ROOT / "docs/sql" / (PREFIX + "_APPLICATION_PENDING_APPROVAL.sql")
        ).read_text(encoding="utf-8")
        storage_guard = (
            ROOT / "docs/sql" / (PREFIX + "_STORAGE_AUTHORITY_GUARD.sql")
        ).read_text(encoding="utf-8")
        assert storage_guard.strip() in batch
        if owner_mode == "missing-storage":
            # Unknown custom GUC placeholders are not loaded extension metadata.
            fake = batch.replace(
                "DO $storage_policy_authority$",
                "SET LOCAL supautils.version='3.3.0'; SET LOCAL supautils.policy_grants='"
                + '{"migration_owner":["storage.objects"]}'
                + "';\nDO $storage_policy_authority$",
                1,
            )
            try:
                db.run(fake)
                raise AssertionError(
                    "unregistered hook placeholders cannot confer policy authority"
                )
            except RpcFailure as error:
                assert error.sqlstate == "P0001"
            assert not db.rows("select 1 from pg_roles where rolname='usage_executor'")
            print("PASS: fake hook settings cannot bypass policy authority guard")
        if owner_mode in ("missing-storage", "missing-bypass"):
            try:
                db.run(batch)
                raise AssertionError("insufficient owner authority must fail closed")
            except RpcFailure as error:
                assert error.sqlstate in {"42501", "P0001"}
            assert db.rows(
                "select to_regclass('public.usage_events') t,to_regclass('supabase_migrations.schema_migrations') h"
            ) == [{"t": None, "h": None}]
            assert not db.rows("select 1 from pg_roles where rolname='usage_executor'")
            print(
                f"PASS: {owner_mode} fails closed and rolls back without broadening privileges"
            )
            return
        if owner_mode == "superuser":
            # All mutations occur only in a task-owned transaction and must be
            # rejected by the real pre-COMMIT assertions, not postflight checks.
            corruptions = {
                "same-count wrong version": "update supabase_migrations.schema_migrations set version='20990101000000' where version='20261025010000';",
                "LOGIN role": "alter role usage_executor login;",
                "role membership": "grant authenticated to usage_executor;",
                "public bucket": "update storage.buckets set public=true where id='resumes';",
                "disabled RLS": "alter table public.usage_events disable row level security;",
                "unforced RLS": "alter table public.usage_events no force row level security;",
                "direct table access": "grant select on public.usage_events to usage_executor;",
                "wrong function executor": "grant execute on function public.subscription_relay_claim(uuid,uuid,uuid) to authenticated;",
                "missing function executor": "revoke execute on function public.subscription_relay_claim(uuid,uuid,uuid) from usage_executor;",
                "PUBLIC function": "grant execute on function public.subscription_relay_claim(uuid,uuid,uuid) to public;",
                "grantable function executor": "grant execute on function public.subscription_relay_claim(uuid,uuid,uuid) to usage_executor with grant option;",
                "unlisted function executor": "grant execute on function public.subscription_relay_claim(uuid,uuid,uuid) to authenticator;",
                "unsafe function search path": "alter function public.subscription_relay_claim(uuid,uuid,uuid) set search_path=public;",
                "legacy RLS disabled": "alter table public.resumes disable row level security;",
                "disabled immutability": "alter table public.usage_events disable trigger immutable_rows;",
                "missing privacy barrier": "drop policy subscription_deletion_barrier on storage.objects;",
            }
            for label, mutation in corruptions.items():
                corrupt = batch.replace("DO $verify$", mutation + "\nDO $verify$", 1)
                try:
                    db.run(corrupt)
                    raise AssertionError(f"precommit must reject {label}")
                except RpcFailure as error:
                    assert error.sqlstate == "P0001", (label, error.sqlstate)
                assert db.rows(
                    "select to_regclass('public.usage_events') t,to_regclass('supabase_migrations.schema_migrations') h"
                ) == [{"t": None, "h": None}]
                assert not db.rows(
                    "select 1 from pg_roles where rolname='usage_executor'"
                )
                assert db.rows("select count(*) n from storage.buckets") == [{"n": 0}]
                print(f"PASS: precommit rejects {label}; full rollback")
        assertions = (
            ROOT / "docs/sql" / (PREFIX + "_PRECOMMIT_ASSERTIONS.sql")
        ).read_text(encoding="utf-8")
        assert assertions.strip() in batch
        # A failure late in the one-transaction batch must leave no application/history/roles.
        broken = batch.replace(
            "NOTIFY pgrst, 'reload schema';",
            "DO $$ BEGIN RAISE EXCEPTION 'synthetic failure'; END $$;",
        )
        try:
            db.run(broken)
            raise AssertionError("injected failure must abort")
        except RpcFailure as error:
            assert error.sqlstate == "P0001"
        assert db.rows(
            "select to_regclass('public.usage_events') t,to_regclass('supabase_migrations.schema_migrations') h"
        ) == [{"t": None, "h": None}]
        assert not db.rows("select 1 from pg_roles where rolname='usage_executor'")
        db.run(batch)
        versions = db.rows(
            "select version from supabase_migrations.schema_migrations order by version"
        )
        manifest = json.loads(
            (ROOT / "docs/sql/C11_C13_STAGING_MANIFEST.json").read_text()
        )
        assert [x["version"] for x in versions] == [x["version"] for x in manifest]
        recorded = {
            row["version"]: row["statements"][0]
            for row in db.rows(
                "select version,statements from supabase_migrations.schema_migrations"
            )
        }
        for entry in manifest:
            raw = (ROOT / "supabase/migrations" / entry["file"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
            assert recorded[entry["version"]].replace("\r\n", "\n") == raw.decode(
                "utf-8"
            ).replace("\r\n", "\n")
        assert db.rows("select count(*) n from public.account_plan_bindings") == [
            {"n": 0}
        ]
        assert db.rows("select count(*) n from public.catalog_offer_versions") == [
            {"n": 0}
        ]
        roles = db.rows(
            "select rolname,rolcanlogin,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolinherit from pg_roles where rolname in ('catalog_draft_executor','catalog_public_reader','usage_executor','usage_binding_executor','usage_reconciler') order by rolname"
        )
        assert len(roles) == 5 and all(
            not any(v for k, v in row.items() if k != "rolname") for row in roles
        )
        assert db.rows(
            "select has_function_privilege('usage_executor','public.subscription_relay_claim(uuid,uuid,uuid)','execute') allowed,has_function_privilege('authenticated','public.subscription_relay_claim(uuid,uuid,uuid)','execute') denied"
        ) == [{"allowed": True, "denied": False}]
        postflight = json.loads(
            db.run((ROOT / "docs/sql" / (PREFIX + "_POSTFLIGHT.sql")).read_text())
        )
        assert postflight["history"] == {
            "history_count": 50,
            "all_expected": True,
            "no_extra": True,
        }
        assert postflight["roles"]["five_closed_roles"]
        assert all(
            postflight[key] == 0
            for key in (
                "permission_rows",
                "bindings",
                "offers",
                "policy_rows",
                "configuration_rows",
                "usage_events",
            )
        )
        assert (
            postflight["relay_execute_allowed"]
            and postflight["relay_authenticated_denied"]
            and postflight["relay_private"]
        )
        assert sorted(postflight["buckets"], key=lambda row: row["id"]) == [
            {"id": "exports", "public": False},
            {"id": "resumes", "public": False},
        ]
        snapshot = json.loads(
            db.run((ROOT / "docs/sql" / (PREFIX + "_PREFLIGHT.sql")).read_text())
        )
        assert all(x["object"] for x in snapshot["required_objects"])
        # Replay guard fails before any second migration or history mutation.
        try:
            db.run(batch)
            raise AssertionError("baseline guard must reject replay")
        except RpcFailure as error:
            assert error.sqlstate == "P0001"
        assert db.rows(
            "select count(*) n from supabase_migrations.schema_migrations"
        ) == [{"n": 50}]
        print(
            f"PASS ({owner_mode}): full 50-source batch, atomic rollback, history, five closed roles/relay ACL, read-only postflight, replay guard, zero bindings/offers"
        )
    finally:
        db.close()


def check_reviewed_guard_decisions(pg_bin):
    """Guard predicate tests with explicit local metadata, never a fake hook pass."""
    db = Native(pg_bin)
    try:
        db.run("""
        create role postgres login nosuperuser createrole bypassrls;
        create role other_actor login nosuperuser createrole bypassrls;
        create role supabase_storage_admin nologin;
        create schema storage;
        create table storage.objects(id uuid);
        alter table storage.objects enable row level security;
        alter table storage.objects owner to supabase_storage_admin;
        grant usage on schema storage to postgres,other_actor;
        """)
        guard = (
            ROOT / "docs/sql" / (PREFIX + "_STORAGE_AUTHORITY_GUARD.sql")
        ).read_text(encoding="utf-8")
        # The actual DO body is evaluated against temporary, explicitly synthetic
        # metadata. This tests decisions, not managed Supautils execution.
        evaluated = guard.replace("pg_catalog.pg_settings", "pg_temp.policy_settings")
        cases = [
            (
                "reviewed missing version",
                None,
                "sighup",
                "configuration file",
                False,
                "postgres",
                True,
                True,
            ),
            (
                "known supported version",
                "3.3.0",
                "sighup",
                "configuration file",
                False,
                "postgres",
                True,
                True,
            ),
            (
                "known old version",
                "3.2.3",
                "sighup",
                "configuration file",
                False,
                "postgres",
                True,
                False,
            ),
            (
                "malformed registered version",
                "unrecognized",
                "sighup",
                "configuration file",
                False,
                "postgres",
                True,
                False,
            ),
            (
                "missing registered grant",
                None,
                "sighup",
                "configuration file",
                False,
                "postgres",
                False,
                False,
            ),
            (
                "unregistered placeholder context",
                None,
                "user",
                "session",
                False,
                "postgres",
                True,
                False,
            ),
            (
                "changed config source",
                None,
                "sighup",
                "session",
                False,
                "postgres",
                True,
                False,
            ),
            (
                "restart pending",
                None,
                "sighup",
                "configuration file",
                True,
                "postgres",
                True,
                False,
            ),
            (
                "unreviewed actor",
                None,
                "sighup",
                "configuration file",
                False,
                "other_actor",
                True,
                False,
            ),
        ]
        for (
            label,
            version,
            context,
            source,
            pending,
            actor,
            permitted,
            allowed,
        ) in cases:
            db.args[db.args.index("-U") + 1] = actor
            metadata = json.dumps({actor: ["storage.objects"] if permitted else []})
            script = "create temp table policy_settings(name text,setting text,context text,source text,pending_restart boolean);"
            script += (
                "insert into policy_settings values ('supautils.policy_grants',"
                + literal(metadata)
                + ","
                + literal(context)
                + ","
                + literal(source)
                + ","
                + str(pending).lower()
                + ");"
            )
            if version is not None:
                script += (
                    "insert into policy_settings values ('supautils.version',"
                    + literal(version)
                    + ",'internal','default',false);"
                )
            if allowed:
                db.run(script + evaluated)
            else:
                try:
                    db.run(script + evaluated)
                    raise AssertionError(f"guard must deny {label}")
                except RpcFailure as error:
                    assert error.sqlstate == "P0001"
            print(
                f"PASS: local metadata guard decision: {label} ({'allow' if allowed else 'deny'})"
            )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", required=True)
    args = parser.parse_args()
    for mode in ("superuser", "managed", "missing-storage", "missing-bypass"):
        check(args.pg_bin, mode)
    check_reviewed_guard_decisions(args.pg_bin)
