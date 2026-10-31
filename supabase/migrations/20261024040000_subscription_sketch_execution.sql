-- C13.2: reuse existing source provenance and durable diagram state machine.
-- No offers, LOGINs, configuration, provider calls or entitlement assignments.
begin;
create function public.subscription_sketch_source(p_account uuid,p_session uuid,p_transcript uuid,p_request text)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare t public.interview_session_transcript_entries; s public.interview_answer_sources;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if (p_transcript is null)=(p_request is null) then raise exception 'invalid source' using errcode='22023'; end if;
 select * into t from public.interview_session_transcript_entries
 where user_id=p_account and session_id=p_session and
   (id=p_transcript or (p_transcript is null and request_id=p_request));
 if not found then raise exception 'source not found' using errcode='P0002'; end if;
 select * into s from public.interview_answer_sources where transcript_id=t.id and user_id=p_account and session_id=p_session;
 return jsonb_build_object('descriptor',jsonb_build_object('transcript_id',t.id,'session_id',p_session,
   'source_revision',s.source_revision,'answer_type',s.answer_type,'provenance',s.provenance,
   'eligible',coalesce(s.answer_type='system_design' and t.source in ('answer','auto','chat'),false),
   'reason',case when s.answer_type='system_design' and t.source in ('answer','auto','chat') then null else 'unverified_source' end),
   'source',jsonb_build_object('id',t.id,'session_id',p_session,'question_text',t.question_text,'answer_text',t.answer_text,'source',t.source));
end $$;

create function public.subscription_sketch_operation(p_account uuid,p_session uuid,p_transcript uuid,p_revision text,
 p_operation_id uuid,p_action text,p_token uuid default null,p_graph jsonb default null,p_model text default null,p_code text default null)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare terms jsonb;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action not in ('read','claim','retry','cancel','checkpoint','finalize','fail') then raise exception 'invalid operation' using errcode='22023'; end if;
 -- Cleanup and owner-scoped historical reads must remain usable after downgrade.
 -- Generation/replay and persistence recheck the live binding before taking the
 -- accepted advisory -> session -> source -> diagram locks. No reverse order.
 if p_action not in ('read','cancel','fail') then
   perform public.subscription_current(p_account,false);
   select o.canonical_json::jsonb->'terms' into terms from public.account_plan_bindings b
     join public.catalog_offer_versions o using(offer_version_id) where b.account_id=p_account;
   if not exists(select 1 from jsonb_array_elements(terms->'entitlements') e
     where e->>'feature'='sketch.generate' and e->>'allowed'='true') then
     raise exception 'feature denied' using errcode='42501';
   end if;
 end if;
 return public.answer_diagram_operation(p_action,p_account,p_session,p_transcript,p_revision,p_operation_id,p_token,p_graph,p_model,p_code);
end $$;
revoke all on function public.subscription_sketch_source(uuid,uuid,uuid,text),
 public.subscription_sketch_operation(uuid,uuid,uuid,text,uuid,text,uuid,jsonb,text,text)
 from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_sketch_source(uuid,uuid,uuid,text),
 public.subscription_sketch_operation(uuid,uuid,uuid,text,uuid,text,uuid,jsonb,text,text) to usage_executor;
commit;
