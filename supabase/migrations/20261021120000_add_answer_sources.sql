-- Additive provenance only. Does not replace any generation/recovery RPC.
create table public.interview_answer_sources (
 transcript_id uuid primary key references public.interview_session_transcript_entries(id) on delete cascade,
 user_id uuid not null references auth.users(id) on delete cascade,
 session_id uuid not null references public.interview_sessions(id) on delete cascade,
 source_revision text not null,
 answer_type text not null,
 provenance text not null check (provenance in ('managed_generation','server_generation'))
);
alter table public.interview_answer_sources enable row level security;
alter table public.interview_answer_sources force row level security;
revoke all on public.interview_answer_sources from public,anon,authenticated;
grant all on public.interview_answer_sources to service_role;
grant select on public.interview_answer_sources to authenticated;
create policy answer_source_owner_read on public.interview_answer_sources for select to authenticated using(user_id=auth.uid());

create function public.answer_source_revision(q text,a text) returns text
language sql immutable set search_path=public as $$
 select 'v1:'||encode(sha256(convert_to(jsonb_build_array(q,a)::text,'UTF8')),'hex')
$$;

-- Only trusted backend generation calls this RPC. Public transcript creation
-- cannot stamp provenance through metadata, source/category, or request_id.
create function public.stamp_answer_source(p_user_id uuid,p_session_id uuid,p_transcript_id uuid,
 p_question text,p_answer text,p_answer_type text) returns boolean
language plpgsql security definer set search_path=public as $$
declare t public.interview_session_transcript_entries%rowtype;
begin
 set local lock_timeout='2s'; set local statement_timeout='5s';
 perform pg_advisory_xact_lock(hashtextextended(p_session_id::text,0));
 perform 1 from public.interview_sessions where id=p_session_id and user_id=p_user_id for update;
 if not found then return false; end if;
 select * into t from public.interview_session_transcript_entries
  where id=p_transcript_id and session_id=p_session_id and user_id=p_user_id for update;
 if t.id is null or t.question_text is distinct from p_question or t.answer_text is distinct from p_answer
  or t.source not in ('answer','auto','chat') then return false; end if;
 insert into public.interview_answer_sources values(t.id,t.user_id,t.session_id,
  public.answer_source_revision(t.question_text,t.answer_text),left(coalesce(p_answer_type,''),80),'server_generation')
 on conflict do nothing;
 return true;
end;
$$;
revoke all on function public.stamp_answer_source(uuid,uuid,uuid,text,text,text) from public,anon,authenticated;
grant execute on function public.stamp_answer_source(uuid,uuid,uuid,text,text,text) to service_role;

create function public.capture_managed_answer_source() returns trigger
language plpgsql security definer set search_path=public as $$
begin
 if new.state='completed' and new.transcript_id is not null then
  insert into public.interview_answer_sources
   select t.id,t.user_id,t.session_id,public.answer_source_revision(t.question_text,t.answer_text),
    left(coalesce(new.payload->'result'->>'answer_type',''),80),'managed_generation'
   from public.interview_session_transcript_entries t
   where t.id=new.transcript_id and t.session_id=new.session_id and t.user_id=new.user_id
    and t.question_text=new.payload->>'question' and t.answer_text=new.payload->'result'->>'answer'
    and t.source in ('answer','auto','chat')
   on conflict do nothing;
 end if;
 return new;
end;
$$;
revoke all on function public.capture_managed_answer_source() from public,anon,authenticated;
create trigger capture_managed_answer_source after update of state,transcript_id on public.session_generation_turns
 for each row execute function public.capture_managed_answer_source();

-- Verifiable managed history only: completed durable generation, exact canonical
-- match, same owner/session and trusted planner result. Never infer from keywords.
insert into public.interview_answer_sources
 select t.id,t.user_id,t.session_id,public.answer_source_revision(t.question_text,t.answer_text),
  left(coalesce(g.payload->'result'->>'answer_type',''),80),'managed_generation'
 from public.session_generation_turns g join public.interview_session_transcript_entries t
  on t.id=g.transcript_id and t.user_id=g.user_id and t.session_id=g.session_id
 where g.state='completed' and t.question_text=g.payload->>'question'
  and t.answer_text=g.payload->'result'->>'answer' and t.source in ('answer','auto','chat')
 on conflict do nothing;

-- Unknown historical rows deliberately remain unknown. Editing canonical text
-- invalidates provenance, even if it is later changed back.
create function public.invalidate_answer_source() returns trigger
language plpgsql security definer set search_path=public as $$
begin
 if new.question_text is distinct from old.question_text or new.answer_text is distinct from old.answer_text
  or new.user_id is distinct from old.user_id or new.session_id is distinct from old.session_id then
  delete from public.interview_answer_sources where transcript_id=old.id;
 end if;
 return new;
end;
$$;
revoke all on function public.invalidate_answer_source() from public,anon,authenticated;
create trigger invalidate_answer_source before update on public.interview_session_transcript_entries
 for each row execute function public.invalidate_answer_source();
