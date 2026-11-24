"""Opt-in checks on the owned, schema-only Docker migration rehearsal."""

import os
import subprocess

import pytest


@pytest.fixture
def sql():
    container = os.environ.get("C15_OWNERSHIP_TEST_CONTAINER")
    if not container:
        pytest.skip("requires an explicitly owned disposable migration container")

    def query(statement, *, ok=True, error=None):
        result = subprocess.run(
            ["docker", "exec", container, "psql", "-U", "postgres", "-d",
             "c15_permission_verify", "-At", "-v", "ON_ERROR_STOP=1", "-c", statement],
            capture_output=True, text=True, check=False,
        )
        assert (result.returncode == 0) == ok, result.stderr
        if not ok:
            assert error and error in result.stderr, result.stderr
        return result.stdout.strip()

    assert query("select rolsuper from pg_roles where rolname=current_user") == "f"
    return query


@pytest.mark.parametrize("owner,function", [
    ("privacy_payload_owner", "public.privacy_auto_credentials_erase(uuid,uuid)"),
    ("privacy_revocation_observer_owner", "public.privacy_revocation_verified(uuid,uuid,uuid)"),
    ("privacy_identity_owner", "public.privacy_identity_call(text,jsonb)"),
    ("privacy_runtime_owner", "public.privacy_runtime_call(text,text,jsonb)"),
    ("privacy_runtime_owner", "public.privacy_notice_event(text,jsonb)"),
])
def test_transfer_preserves_restricted_owner_without_deployment_grants(sql, owner, function):
    assert sql(f"select pg_get_userbyid(proowner) from pg_proc where oid='{function}'::regprocedure") == owner
    assert sql(f"select has_schema_privilege('{owner}','public','CREATE')") == "f"
    # PG17 preserves the creator's automatic ADMIN-only membership. It must
    # not retain SET/INHERIT authority from the temporary deployment grant.
    assert sql(f"select count(*) from pg_auth_members where roleid='{owner}'::regrole "
               "and (inherit_option or set_option)") == "0"
    assert sql(f"select rolcanlogin or rolsuper or rolbypassrls from pg_roles where rolname='{owner}'") == "f"
    for caller in ("anon", "authenticated", "service_role", "usage_executor"):
        assert sql(f"select has_function_privilege('{caller}','{function}','EXECUTE')") == "f"


def test_original_ownership_failure_rolls_back(sql):
    assert sql("select rolcreaterole from pg_roles where rolname=current_user") == "t"
    setup = sql("begin; create role c15_transfer_failure nologin; "
        "create function public.c15_transfer_failure() returns int language sql as 'select 1'; "
        "alter function public.c15_transfer_failure() owner to c15_transfer_failure; commit;",
        ok=False, error='must be able to SET ROLE "c15_transfer_failure"')
    assert setup.splitlines() == ["BEGIN", "CREATE ROLE", "CREATE FUNCTION"]
    assert sql("select count(*) from pg_roles where rolname='c15_transfer_failure'") == "0"
    assert sql("select to_regprocedure('public.c15_transfer_failure()') is null") == "t"


def test_ownership_failure_rejects_setup_error(sql):
    with pytest.raises(AssertionError, match="c15_missing_setup_function"):
        sql("select public.c15_missing_setup_function()", ok=False,
            error='must be able to SET ROLE "c15_transfer_failure"')


def test_runtime_members_cannot_assume_private_owner(sql):
    for caller in ("anon", "authenticated", "service_role", "usage_executor",
                   "privacy_cleanup_executor", "privacy_content_executor"):
        assert sql(f"select count(*) from pg_auth_members m join pg_roles r on r.oid=m.roleid "
                   f"where m.member='{caller}'::regrole and r.rolname in "
                   "('privacy_payload_owner','privacy_identity_owner',"
                   "'privacy_runtime_owner','privacy_revocation_observer_owner')") == "0"
