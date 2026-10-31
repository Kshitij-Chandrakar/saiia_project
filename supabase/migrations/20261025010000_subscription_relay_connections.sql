-- One transport connection per logical hosted stream. No role assignment/activation.
begin;
create table public.subscription_relay_connections (
 run_id uuid primary key,
 account_id uuid not null references auth.users(id) on delete restrict,
 session_id uuid not null references public.interview_sessions(id) on delete restrict,
 created_at timestamptz not null default clock_timestamp()
);
alter table public.subscription_relay_connections enable row level security;
alter table public.subscription_relay_connections force row level security;
revoke all on public.subscription_relay_connections from public,anon,authenticated,service_role,
 usage_executor,usage_binding_executor,usage_reconciler,catalog_draft_executor;

create function public.subscription_relay_claim(p_account uuid,p_run uuid,p_session uuid) returns boolean
language plpgsql security definer set search_path=pg_catalog as $$
declare claimed uuid;
begin
 perform public.subscription_current(p_account,false);
 perform public.subscription_session_read(p_account,p_session);
 insert into public.subscription_relay_connections(run_id,account_id,session_id)
 values(p_run,p_account,p_session) on conflict do nothing returning run_id into claimed;
 if claimed is null then raise exception 'stream already claimed' using errcode='P0003'; end if;
 return true;
end $$;
revoke all on function public.subscription_relay_claim(uuid,uuid,uuid) from public,anon,authenticated,
 service_role,usage_binding_executor,usage_reconciler,catalog_draft_executor;
grant execute on function public.subscription_relay_claim(uuid,uuid,uuid) to usage_executor;
commit;
