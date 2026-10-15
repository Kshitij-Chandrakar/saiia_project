-- Apply before deploying the permanent Clear Transcript API/UI.
begin;

-- A real-time guard also covers transactions started before the late-write
-- deadline. It uses the same lock as the C7 create RPC and deletion RPC.
create or replace function public.guard_closed_transcript_insert()
returns trigger language plpgsql security definer set search_path = public
as $$
declare
  owned_session public.interview_sessions%rowtype;
begin
  perform pg_advisory_xact_lock(hashtextextended(new.session_id::text, 0));
  select * into owned_session from public.interview_sessions
    where id = new.session_id and user_id = new.user_id for update;
  if owned_session.id is null then
    raise exception 'interview session was not found' using errcode = 'P0001';
  end if;
  if owned_session.status <> 'active' and (
    owned_session.ended_at is null or
    owned_session.ended_at + interval '5 minutes' <= clock_timestamp()
  ) then
    raise exception 'interview session is closed' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

revoke all on function public.guard_closed_transcript_insert() from public, anon, authenticated;
drop trigger if exists guard_closed_transcript_insert on public.interview_session_transcript_entries;
create trigger guard_closed_transcript_insert before insert on public.interview_session_transcript_entries
  for each row execute function public.guard_closed_transcript_insert();

create or replace function public.delete_interview_session_transcript_entries(p_user_id uuid, p_session_id uuid)
returns integer language plpgsql security definer set search_path = public
as $$
declare
  owned_session public.interview_sessions%rowtype;
  deleted_count integer;
begin
  set local lock_timeout = '2s';
  set local statement_timeout = '5s';
  perform pg_advisory_xact_lock(hashtextextended(p_session_id::text, 0));
  select * into owned_session from public.interview_sessions
    where id = p_session_id and user_id = p_user_id for update;
  if owned_session.id is null then
    raise exception 'interview session was not found' using errcode = 'P0001';
  end if;
  if owned_session.status not in ('ended', 'abandoned') or owned_session.ended_at is null
    or owned_session.ended_at + interval '5 minutes' > clock_timestamp() then
    raise exception 'Transcript deletion is available five minutes after the session ends.' using errcode = 'P0001';
  end if;
  delete from public.interview_session_transcript_entries
    where session_id = p_session_id and user_id = p_user_id;
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

revoke all on function public.delete_interview_session_transcript_entries(uuid, uuid) from public, anon, authenticated;
grant execute on function public.delete_interview_session_transcript_entries(uuid, uuid) to service_role;
commit;
