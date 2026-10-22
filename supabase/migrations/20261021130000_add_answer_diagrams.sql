create table public.interview_answer_diagrams (
 transcript_id uuid primary key references public.interview_answer_sources(transcript_id) on delete cascade,
 user_id uuid not null references auth.users(id) on delete cascade,
 session_id uuid not null references public.interview_sessions(id) on delete cascade,
 source_revision text not null,
 graph_schema integer not null default 1 check(graph_schema=1),
 prompt_schema integer not null default 1 check(prompt_schema=1),
 configured_model text not null check(char_length(configured_model) between 1 and 120),
 actual_model text check(char_length(actual_model)<=120),
 state text not null check(state in ('processing','checkpoint','ready','failed','uncertain','cancelled','insufficient_detail')),
 attempt integer not null default 1 check(attempt between 1 and 2),
 operation_id uuid not null,
 token uuid not null default extensions.gen_random_uuid(),
 lease_until timestamptz not null default clock_timestamp()+interval '90 seconds',
 graph jsonb check(octet_length(graph::text)<=32768),
 failure_code text check(failure_code in ('provider_failed','timeout','invalid_graph','refused','incomplete','cancelled','uncertain','insufficient_detail')),
 created_at timestamptz not null default clock_timestamp(),
 updated_at timestamptz not null default clock_timestamp()
);
alter table public.interview_answer_diagrams enable row level security;
alter table public.interview_answer_diagrams force row level security;
revoke all on public.interview_answer_diagrams from public,anon,authenticated;
grant all on public.interview_answer_diagrams to service_role;
-- No direct authenticated projection exposes private tokens/checkpoints. Reads
-- use the authenticated backend's narrow DTO, with ownership rechecked in RPC.
create function public.answer_diagram_operation(p_operation text,p_user_id uuid,p_session_id uuid,
 p_transcript_id uuid,p_revision text,p_operation_id uuid,p_token uuid default null,
 p_graph jsonb default null,p_model text default null,p_code text default null) returns jsonb
language plpgsql security definer set search_path=public,extensions as $$
declare s public.interview_answer_sources%rowtype; d public.interview_answer_diagrams%rowtype;
begin
 set local lock_timeout='2s'; set local statement_timeout='5s';
 -- Same lock order as Clear Transcript: session advisory, session, source, diagram.
 perform pg_advisory_xact_lock(hashtextextended(p_session_id::text,0));
 perform 1 from public.interview_sessions where id=p_session_id and user_id=p_user_id for update;
 if not found then return jsonb_build_object('error','source_not_found'); end if;
 perform 1 from public.interview_session_transcript_entries
  where id=p_transcript_id and session_id=p_session_id and user_id=p_user_id for update;
 if not found then return jsonb_build_object('error','source_not_found'); end if;
 select * into s from public.interview_answer_sources where transcript_id=p_transcript_id
  and session_id=p_session_id and user_id=p_user_id for update;
 if s.transcript_id is null then return jsonb_build_object('error','ineligible_source'); end if;
 if s.answer_type<>'system_design' then return jsonb_build_object('error','ineligible_source'); end if;
 if s.source_revision is distinct from p_revision then return jsonb_build_object('error','stale_source'); end if;
 select * into d from public.interview_answer_diagrams where transcript_id=p_transcript_id for update;
 if d.transcript_id is not null and d.source_revision<>p_revision then return jsonb_build_object('error','stale_source'); end if;
 if d.state='processing' and d.lease_until<=clock_timestamp() then
  update public.interview_answer_diagrams set state='uncertain',failure_code='uncertain',
   token=extensions.gen_random_uuid(),updated_at=clock_timestamp() where transcript_id=p_transcript_id returning * into d;
 end if;
 if p_operation in ('claim','retry') then
  if d.transcript_id is null and p_operation='claim' then
   if p_operation_id is null or p_model is null then return jsonb_build_object('error','invalid_operation'); end if;
   insert into public.interview_answer_diagrams(transcript_id,user_id,session_id,source_revision,configured_model,state,operation_id)
    values(s.transcript_id,s.user_id,s.session_id,s.source_revision,p_model,'processing',p_operation_id) returning * into d;
   return to_jsonb(d)||jsonb_build_object('claimed',true);
  elsif d.state='failed' and d.attempt=1 and p_operation='retry' and d.operation_id is distinct from p_operation_id then
   update public.interview_answer_diagrams set state='processing',attempt=2,operation_id=p_operation_id,
    token=extensions.gen_random_uuid(),lease_until=clock_timestamp()+interval '90 seconds',
    configured_model=p_model,actual_model=null,failure_code=null,updated_at=clock_timestamp()
    where transcript_id=p_transcript_id returning * into d;
   return to_jsonb(d)||jsonb_build_object('claimed',true);
  end if;
 elsif p_operation='cancel' then
  if d.transcript_id is null and p_operation_id is not null then
   -- Cancel may overtake the original HTTP claim. Keep a tombstone so a
   -- delayed generate cannot start paid work after cancellation.
   insert into public.interview_answer_diagrams(transcript_id,user_id,session_id,source_revision,configured_model,state,operation_id,failure_code)
    values(s.transcript_id,s.user_id,s.session_id,s.source_revision,'gpt-4.1-mini','cancelled',p_operation_id,'cancelled') returning * into d;
  elsif d.operation_id=p_operation_id and d.state in ('processing','checkpoint') then
   update public.interview_answer_diagrams set state='cancelled',graph=null,failure_code='cancelled',
    token=extensions.gen_random_uuid(),updated_at=clock_timestamp() where transcript_id=p_transcript_id returning * into d;
  end if;
 elsif p_operation in ('checkpoint','finalize','fail') then
  if d.token is distinct from p_token or d.operation_id is distinct from p_operation_id then
   return jsonb_build_object('error','stale_operation');
  end if;
  if p_operation='checkpoint' then
   if d.state<>'processing' or p_graph is null or octet_length(p_graph::text)>32768 then
    return jsonb_build_object('error','stale_operation'); end if;
   update public.interview_answer_diagrams set state='checkpoint',graph=p_graph,actual_model=p_model,
    updated_at=clock_timestamp() where transcript_id=p_transcript_id returning * into d;
  elsif p_operation='finalize' and d.state='checkpoint' then
   update public.interview_answer_diagrams set state=case when graph->>'status'='insufficient_detail' then 'insufficient_detail' else 'ready' end,
    updated_at=clock_timestamp() where transcript_id=p_transcript_id returning * into d;
  elsif p_operation='fail' and d.state='processing' then
   update public.interview_answer_diagrams set state='failed',failure_code=p_code,
    token=extensions.gen_random_uuid(),updated_at=clock_timestamp() where transcript_id=p_transcript_id returning * into d;
  end if;
 elsif p_operation<>'read' then return jsonb_build_object('error','invalid_operation');
 end if;
 return case when d.transcript_id is null then jsonb_build_object('state','absent') else to_jsonb(d) end;
end;
$$;
revoke all on function public.answer_diagram_operation(text,uuid,uuid,uuid,text,uuid,uuid,jsonb,text,text) from public,anon,authenticated;
grant execute on function public.answer_diagram_operation(text,uuid,uuid,uuid,text,uuid,uuid,jsonb,text,text) to service_role;
