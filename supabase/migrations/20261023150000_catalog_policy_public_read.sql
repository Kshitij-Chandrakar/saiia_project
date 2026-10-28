-- Explicit deployment-owned policy. No defaults, policy seeds, LOGINs or admins.
begin;
create table public.catalog_publication_policies (
 policy_id uuid primary key,
 subscription_ref text not null,
 migration_ref text not null,
 revision bigint not null check (revision>0),
 active boolean not null default false,
 document jsonb not null check (jsonb_typeof(document)='object'),
 unique(subscription_ref,migration_ref)
);
alter table public.catalog_publication_policies enable row level security;
revoke all on public.catalog_publication_policies from public,anon,authenticated,service_role,catalog_draft_executor;
create function public.catalog_policy_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
begin
 if new.policy_id<>old.policy_id or new.subscription_ref<>old.subscription_ref or new.migration_ref<>old.migration_ref or new.revision<>old.revision+1 then
  raise exception 'policy revision conflict' using errcode='23514';
 end if;
 return new;
end; $$;
revoke all on function public.catalog_policy_guard() from public,anon,authenticated,service_role,catalog_draft_executor;
create trigger policy_revision before update on public.catalog_publication_policies for each row execute function public.catalog_policy_guard();
create function public.catalog_policy_resolve(p_actor uuid,p_subscription text,p_migration text)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare p public.catalog_publication_policies; old_actor text;
begin
 if session_user<>'catalog_draft_executor' or current_setting('role',true)<>'none' then
  raise exception 'server channel required' using errcode='42501'; end if;
 old_actor:=current_setting('catalog.draft_actor',true);
 perform set_config('catalog.draft_actor',p_actor::text,true);
 perform public.catalog_locked_actor();
 select * into p from public.catalog_publication_policies where active and subscription_ref=p_subscription and migration_ref=p_migration for share;
 if not found then raise exception 'policy unavailable' using errcode='55000'; end if;
 perform set_config('catalog.draft_actor',coalesce(old_actor,''),true);
 return jsonb_build_object('policy_id',p.policy_id,'approval_revision',p.revision::text,'document',p.document);
end; $$;
revoke all on function public.catalog_policy_resolve(uuid,text,text) from public,anon,authenticated,service_role;
grant execute on function public.catalog_policy_resolve(uuid,text,text) to catalog_draft_executor;

do $$ begin
 if not exists(select 1 from pg_roles where rolname='catalog_public_reader') then
  create role catalog_public_reader nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
 end if;
end $$;
grant usage on schema public to catalog_public_reader;
-- One SQL statement: revision, visibility windows and terms share one MVCC snapshot.
create function public.catalog_public_read() returns jsonb language sql stable security definer set search_path=pg_catalog as $$
 select jsonb_build_object('revision',e.revision::text,'at',statement_timestamp(),
  'offers',coalesce((select jsonb_agg(jsonb_build_object(
    'snapshot',o.canonical_json,'fingerprint',o.fingerprint,
    'visibility',jsonb_build_object('offer_version_id',v.offer_version_id,'revision',v.revision::text,
       'state',v.state,'valid_from',v.valid_from,'valid_until',v.valid_until,'retired_at',v.retired_at)) order by p.code)
   from public.catalog_offer_versions o join public.catalog_visibility v using(offer_version_id)
   join public.catalog_publications x using(offer_version_id) join public.catalog_plans p on p.plan_id=o.plan_id
   where v.state='visible' and v.valid_from<=statement_timestamp()
    and (v.valid_until is null or v.valid_until>statement_timestamp())), '[]'::jsonb))
 from public.catalog_public_state e where e.singleton
$$;
revoke all on function public.catalog_public_read() from public,anon,authenticated,service_role,catalog_draft_executor;
grant execute on function public.catalog_public_read() to catalog_public_reader;
commit;
