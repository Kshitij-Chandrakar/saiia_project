"""Compile reviewed application SQL into fixed private operations (offline only).

Input captures contain SQL/types/source names, never parameter values. Generated
SQL is reviewable migration input, not learned at runtime or caller-supplied SQL.
"""

import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
operations = {}
for f in sys.argv[1:]:
    d = json.loads(Path(f).read_text(encoding="utf8"))
    for failure in d["failures"]:
        assert (
            failure["sql"]
            == "lock table privacy_deletion_requests,privacy_content_jobs in share mode"
        ), failure["reason"]
        import hashlib

        key = hashlib.sha256(failure["sql"].encode()).hexdigest()
        operations[key] = {
            "sql": failure["sql"],
            "prepared": failure["sql"],
            "parameters": [],
            "results": [],
            "source": "privacy_checkpoint.py",
            "method": "seal_source",
        }
    operations.update(d["operations"])
# The production-sized snapshot is compiled from the frozen treatment registry,
# not learned from a particular fixture's subset of migrated tables.
import hashlib

from psycopg import sql

sys.path.insert(0, str(root / "backend"))
from app.privacy_registry import CONTENT, SAFE_METADATA

manifest = json.loads((root / "backend/app/privacy_fields.json").read_text())["tables"]
parts = [
    sql.SQL(
        "select 'auth_identity'::text,jsonb_build_object('id',id,'email',email,'email_confirmed_at',email_confirmed_at) from auth.users where id=%s"
    )
]
for table, (owner, _, field_names) in (CONTENT | SAFE_METADATA).items():
    if table not in manifest:
        continue
    fields = [f for f in field_names.split() if f in manifest[table]["fields"]]
    if not fields:
        continue
    projection = sql.SQL(",").join(
        part for field in fields for part in (sql.Literal(field), sql.Identifier(field))
    )
    parts.append(
        sql.SQL(
            "select {}::text,jsonb_build_object({}) from public.{} where {}=%s"
        ).format(
            sql.Literal(table), projection, sql.Identifier(table), sql.Identifier(owner)
        )
    )
snapshot = (
    sql.SQL(
        "select category,case when octet_length(document::text)>%s then null else document end from ({}) as snapshot_rows(category,document)"
    )
    .format(sql.SQL(" union all ").join(parts))
    .as_string()
)
number = iter(range(1, len(parts) + 2))
prepared = re.sub(r"%s", lambda _: "$" + str(next(number)), snapshot)
operations[hashlib.sha256(snapshot.encode()).hexdigest()] = {
    "sql": snapshot,
    "prepared": prepared,
    "parameters": ["integer"] + ["uuid"] * len(parts),
    "results": [25, 3802],
    "source": "privacy_content.py",
    "method": "snapshot",
}
# Fixed newly classified receipt predicate has one UUID input and boolean output.
import ast

for node in ast.walk(
    ast.parse((root / "backend/app/privacy_retained.py").read_text(encoding="utf8"))
):
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and "from subscription_payment_receipts" in node.args[0].value
    ):
        text = node.args[0].value
        assert text.count("%s") == 1
        operations[hashlib.sha256(text.encode()).hexdigest()] = {
            "sql": text,
            "prepared": text.replace("%s", "$1"),
            "parameters": ["uuid"],
            "results": [16],
            "source": "privacy_retained.py",
            "method": "primary_safe",
        }
client = {}
statements = []
for method in ast.walk(
    ast.parse((root / "backend/app/privacy_content.py").read_text(encoding="utf8"))
):
    if isinstance(method, ast.FunctionDef) and method.name == "sessions":
        for call in ast.walk(method):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "execute"
                and call.args
                and isinstance(call.args[0], ast.Constant)
            ):
                text = call.args[0].value
                assert isinstance(text, str) and text.count("%s") == 3
                numbers = iter(range(1, 4))
                operations[hashlib.sha256(text.encode()).hexdigest()] = {
                    "sql": text,
                    "prepared": re.sub(
                        r"%s", lambda _, numbers=numbers: "$" + str(next(numbers)), text
                    ),
                    "parameters": ["uuid"] * 3,
                    "results": [2950, 25],
                    "source": "privacy_content.py",
                    "method": "sessions",
                }
for key, spec in sorted(operations.items()):
    statement = spec["prepared"]
    stream = statement.lstrip().startswith("select category,case")

    def parameter(match, parameters=spec["parameters"]):
        i = int(match.group(1)) - 1
        t = parameters[i]
        assert re.fullmatch(r"[A-Za-z0-9_ .\[\]\"]+", t), t
        return (
            f"(array(select jsonb_array_elements_text($1->{i})))::{t}"
            if t.endswith("[]")
            else f"($1->>{i})::{t}"
        )

    statement = re.sub(r"\$(\d+)", parameter, statement)
    if stream:
        statement = "select * from (" + statement + ") c15_snapshot(category,document)"
    mode = "stream" if stream else "rows" if spec["results"] else "command"
    statement = statement.replace(
        "from information_schema.columns where table_schema='public'",
        "from public.privacy_runtime_columns()",
    ).replace(
        "to_jsonb(u)->>'deleted_at' is null",
        "public.privacy_runtime_contact_available(u.id)",
    )
    if spec["sql"] == "select public.privacy_restore_accessible()":
        statement = "select (session_user='privacy_restore_executor' or public.privacy_restore_accessible())"
    if spec["results"] and not stream:
        aliases = ["f" + str(i) for i in range(len(spec["results"]))]
        aggregate = (
            "select coalesce(jsonb_agg(jsonb_build_array("
            + ",".join("c15_row." + a for a in aliases)
            + ")), '[]'::jsonb) from "
        )
        if statement.lstrip().lower().startswith(("insert", "update", "delete")):
            statement = (
                "with c15_row("
                + ",".join(aliases)
                + ") as ("
                + statement
                + ") "
                + aggregate
                + "c15_row"
            )
        else:
            statement = (
                aggregate + "(" + statement + ") c15_row(" + ",".join(aliases) + ")"
            )
    scoped = spec["method"] in {"cleanup", "remove_objects", "run"} and spec[
        "sql"
    ].lstrip().lower().startswith(("insert", "update", "delete"))
    restore = spec["source"] in {"privacy_restore.py", "privacy_checkpoint.py"}
    client[key] = {
        "types": spec["results"],
        "stream": stream,
        "source": spec["source"],
        "method": spec["method"],
    }
    quote = lambda s: "'" + s.replace("'", "''") + "'"
    statements.append(
        "insert into public.privacy_runtime_operations values("
        + ",".join(
            [
                quote(key),
                quote(statement),
                str(len(spec["parameters"])),
                quote(mode),
                str(restore).lower(),
                str(scoped).lower(),
            ]
        )
        + ");"
    )
(root / "backend/app/privacy_runtime_operations.json").write_text(
    json.dumps(client, indent=2) + "\n", encoding="utf8"
)
head = """-- Default-disabled fixed-operation adapter. No caller SQL or registration API.
begin;
create role privacy_content_executor nologin noinherit nosuperuser nocreatedb nocreaterole nobypassrls;
create role privacy_restore_executor nologin noinherit nosuperuser nocreatedb nocreaterole nobypassrls;
create role privacy_runtime_owner nologin noinherit nosuperuser nocreatedb nocreaterole nobypassrls;
create table public.privacy_runtime_operations(operation_id text primary key,body text not null,arity integer not null,mode text not null check(mode in ('rows','command','stream')),restore_only boolean not null,requires_scope boolean not null);
revoke all on public.privacy_runtime_operations from public,anon,authenticated,service_role,usage_executor,privacy_content_executor,privacy_restore_executor;
create trigger runtime_operations_immutable before update or delete on public.privacy_runtime_operations for each row execute function public.catalog_reject_mutation();
create trigger runtime_operations_no_truncate before truncate on public.privacy_runtime_operations for each statement execute function public.catalog_reject_mutation();
"""
# Grant only referenced, frozen public application relations to the NOLOGIN
# function owner; callers get no table privileges or owner-role membership.
manifest = json.loads((root / "backend/app/privacy_fields.json").read_text())["tables"]
refs = set()
for x in operations.values():
    for t in re.findall(
        r'\b(?:from|join|update|into|table)\s+(?:public\.)?["\']?([a-z_]+)',
        x["sql"],
        re.IGNORECASE,
    ):
        if t in manifest:
            refs.add(t)
head += """create function public.privacy_runtime_columns() returns table(table_name name,column_name name,data_type character varying,udt_name name,ordinal_position integer) language sql security definer set search_path=pg_catalog as $$
 select c.relname,a.attname,(case when t.typelem<>0 and t.typlen=-1 then 'ARRAY' when ntype.nspname<>'pg_catalog' then 'USER-DEFINED' else format_type(t.oid,null) end)::character varying,t.typname,a.attnum::integer from pg_attribute a join pg_class c on c.oid=a.attrelid join pg_namespace n on n.oid=c.relnamespace join pg_type t on t.oid=a.atttypid join pg_namespace ntype on ntype.oid=t.typnamespace where n.nspname='public' and c.relkind in ('r','p','v','m','f') and a.attnum>0 and not a.attisdropped
$$;
alter function public.privacy_runtime_columns() owner to privacy_runtime_owner;
revoke all on function public.privacy_runtime_columns() from public,anon,authenticated,service_role;
grant execute on function public.privacy_runtime_columns() to privacy_runtime_owner;
"""
head += """create function public.privacy_runtime_contact_available(p_account uuid) returns boolean language sql security definer set search_path=pg_catalog as $$ select exists(select 1 from auth.users u where u.id=p_account and u.deleted_at is null) $$;
alter function public.privacy_runtime_contact_available(uuid) owner to privacy_runtime_owner;
revoke all on function public.privacy_runtime_contact_available(uuid) from public,anon,authenticated,service_role;
grant execute on function public.privacy_runtime_contact_available(uuid) to privacy_runtime_owner;
"""
head += "grant usage on schema public,auth to privacy_runtime_owner;\ngrant select(id,email,email_confirmed_at,deleted_at),update(id) on auth.users to privacy_runtime_owner;\n"
import sys

sys.path.insert(0, str(root / "backend"))
from app.privacy_registry import CONTENT

head += (root / "scripts/c15_runtime_scope.sql").read_text(encoding="utf8")
for t in sorted(refs):
    # Retained/ledger readers are read-only except fixed restore settlement and
    # matching restore evidence. No retirement authority is provided here.
    fromtypes = any(
        re.search(
            r'\b(?:insert\s+into|update|delete\s+from)\s+(?:public\.)?["\']?'
            + re.escape(t)
            + r"\b",
            x["sql"],
            re.IGNORECASE,
        )
        for x in operations.values()
    )
    verbs = [
        verb
        for verb, pattern in [
            ("insert", "insert\\s+into"),
            ("update", "update"),
            ("delete", "delete\\s+from"),
        ]
        if any(
            re.search(
                r"\b" + pattern + r"\s+(?:public\.)?[\"\']?" + re.escape(t) + r"\b",
                x["sql"],
                re.IGNORECASE,
            )
            for x in operations.values()
        )
    ]
    head += (
        "grant select"
        + ("".join("," + v for v in verbs))
        + f" on public.{t} to privacy_runtime_owner;\n"
    )
    if any(
        "for update" in x["sql"].lower()
        and re.search(r"\b" + re.escape(t) + r"\b", x["sql"])
        for x in operations.values()
    ):
        fields = manifest[t]["fields"]
        lock = next(
            (
                v
                for v in [
                    "id",
                    "account_id",
                    "user_id",
                    "operation_id",
                    "unit_id",
                    "request_id",
                    "run_id",
                    "singleton",
                ]
                if v in fields
            ),
            None,
        )
        if lock:
            head += f'grant update("{lock}") on public.{t} to privacy_runtime_owner;\n'
    if t in CONTENT and CONTENT[t][0] in {"account_id", "user_id"}:
        owner, session, _ = CONTENT[t]
        session_sql = "null::uuid" if session is None else '"' + session + '"'
        predicate = f'public.privacy_runtime_allows("{owner}",{session_sql})'
        head += f'grant update("{owner}") on public.{t} to privacy_runtime_owner;\ncreate policy c15_runtime_lock on public.{t} for update to privacy_runtime_owner using(true) with check(true);\n'
        head += f"create policy c15_runtime_read on public.{t} for select to privacy_runtime_owner using(true);\n"
        head += f"create policy c15_runtime_delete on public.{t} for delete to privacy_runtime_owner using({predicate});\n"
    else:
        head += f"create policy c15_runtime_owner on public.{t} to privacy_runtime_owner using(true) with check(true);\n"
head += """do $$ declare n text; t text; begin foreach t in array array['privacy_lifecycle_audit'] loop n:=pg_get_serial_sequence('public.'||t,'id'); if n is not null then execute format('grant usage,select on sequence %s to privacy_runtime_owner',n); end if; end loop; end $$;
grant select on public.privacy_runtime_operations to privacy_runtime_owner;
"""
head += "grant update on public.privacy_deletion_requests,public.privacy_content_jobs to privacy_runtime_owner;\n"
head += "grant execute on function public.privacy_restore_accessible(),public.privacy_capture_erasure_keys(uuid,uuid),public.privacy_email_denied(text),public.subscription_auto_finish_slice(uuid,timestamptz) to privacy_runtime_owner;\n"
body = """
create function public.privacy_runtime_call(p_action text,p_operation text,p_args jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog,public,pg_temp as $$
declare op public.privacy_runtime_operations; result jsonb; n bigint; row record; rows jsonb:='[]'; portal refcursor:='c15_runtime_snapshot'; begin
 if session_user not in ('privacy_content_executor','privacy_restore_executor') or current_setting('role',true)<>'none' then raise exception 'runtime denied' using errcode='42501'; end if;
 if p_action='fetch' then
  for i in 1..16 loop fetch portal into row; exit when not found; rows:=rows||jsonb_build_array(jsonb_build_array(row.category,row.document)); end loop;
  return jsonb_build_object('rows',rows,'count',jsonb_array_length(rows));
 elsif p_action='close' then close portal; return '{}'::jsonb;
 end if;
 select * into strict op from public.privacy_runtime_operations where operation_id=p_operation;
 if op.restore_only and session_user<>'privacy_restore_executor' then raise exception 'restore operation denied' using errcode='42501'; end if;
 if op.requires_scope and not exists(select 1 from public.privacy_content_jobs j where j.id=nullif(current_setting('c15.runtime.job',true),'')::uuid and j.lease_id=nullif(current_setting('c15.runtime.lease',true),'')::uuid and j.state='running' and j.lease_until>clock_timestamp()) then raise exception 'live scope required' using errcode='42501'; end if;
 if jsonb_typeof(p_args)<>'array' or jsonb_array_length(p_args)<>op.arity or octet_length(p_args::text)>2097152 then raise exception 'invalid operation parameters' using errcode='22023'; end if;
 if op.mode='stream' and p_action='open' then open portal for execute op.body using p_args; return '{}'::jsonb; end if;
 if p_action<>'execute' or op.mode='stream' then raise exception 'operation denied' using errcode='42501'; end if;
 if op.mode='rows' then execute op.body into result using p_args; n:=jsonb_array_length(result);
 else execute op.body using p_args; get diagnostics n=row_count; result:='[]'; end if;
 if octet_length(result::text)>2097152 then raise exception 'result bound exceeded' using errcode='54000'; end if;
 return jsonb_build_object('rows',result,'count',n);
end $$;
alter function public.privacy_runtime_call(text,text,jsonb) owner to privacy_runtime_owner;
revoke all on function public.privacy_runtime_call(text,text,jsonb) from public,anon,authenticated,service_role,usage_executor,privacy_cleanup_executor,privacy_preparation_executor;
grant execute on function public.privacy_runtime_call(text,text,jsonb) to privacy_content_executor,privacy_restore_executor;
commit;
"""
(root / "supabase/migrations/20261102020000_privacy_runtime_operations.sql").write_text(
    head + "\n".join(statements) + body, encoding="utf8"
)
print("compiled fixed operations", len(operations), "referenced relations", len(refs))
