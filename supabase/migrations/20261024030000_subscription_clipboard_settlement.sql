-- Atomic integration with the existing immutable user-written My Answers store.
-- Requires the existing session/My Answers migrations. No second answer store.
begin;
create function public.subscription_clipboard_save(p_account uuid,p_session uuid,p_key text,p_body text) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare record public.interview_session_my_answers; operation jsonb; document jsonb; terms jsonb;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_key is null or p_key !~ '^[A-Za-z0-9._:-]{1,120}$' or p_body is null or char_length(btrim(p_body)) not between 1 and 24000 then
  raise exception 'invalid answer' using errcode='22023'; end if;
 perform public.subscription_current(p_account,false);
 select canonical_json::jsonb->'terms' into terms from public.catalog_offer_versions o join public.account_plan_bindings b using(offer_version_id) where b.account_id=p_account;
 if not exists(select 1 from jsonb_array_elements(terms->'entitlements') x where x->>'feature'='clipboard.saved_answers' and x->>'allowed'='true') then raise exception 'denied' using errcode='42501'; end if;
 -- Ownership is checked on both execution and replay. No inaccessible result IDs.
 perform pg_advisory_xact_lock(hashtextextended(p_session::text,0));
 perform 1 from public.interview_sessions where id=p_session and user_id=p_account for update;
 if not found then raise exception 'not found' using errcode='P0002'; end if;
 operation:=public.usage_call(p_account,'reserve',jsonb_build_object('operation','clipboard.save','resource_id',p_session,'request_id',p_key,
  'semantic_hash',encode(sha256(convert_to(btrim(p_body),'UTF8')),'hex'),'meter','clipboard.new_saves','requested',1,
  'policy_version','subscriptions.approved.2026-10-24','lease_seconds',30));
 document:=jsonb_build_object('operation_id',operation->'operation_id','fence',operation->'fence','claim_token',operation->'claim_token');
 if operation->>'state'='settled' then
  select * into record from public.interview_session_my_answers where id=(operation->>'result_ref')::uuid and user_id=p_account and session_id=p_session;
  if not found then raise exception 'saved result unavailable' using errcode='55000'; end if;
  return to_jsonb(record);
 end if;
 if operation->>'state'<>'reserved' then raise exception 'outcome unresolved' using errcode='40001'; end if;
 if not exists(select 1 from public.interview_sessions where id=p_session and status='active') then raise exception 'session closed' using errcode='40001'; end if;
 perform public.usage_call(p_account,'dispatch',document);
 -- Reuse the accepted storage primitive, including its session lock and checks.
 record:=public.create_interview_session_my_answer(p_account,p_session,p_body);
 perform public.usage_call(p_account,'checkpoint',document||jsonb_build_object('result_ref',record.id));
 perform public.usage_call(p_account,'settle',document||jsonb_build_object('charged',1,'policy_version','subscriptions.approved.2026-10-24'));
 return to_jsonb(record);
end $$;
revoke all on function public.subscription_clipboard_save(uuid,uuid,text,text) from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_clipboard_save(uuid,uuid,text,text) to usage_executor;
create function public.subscription_clipboard_read(p_account uuid,p_session uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if not exists(select 1 from public.interview_sessions where id=p_session and user_id=p_account) then raise exception 'not found' using errcode='P0002'; end if;
 -- Existing personal data remains readable independent of the current plan.
 return (select coalesce(jsonb_agg(to_jsonb(a) order by position,created_at,id),'[]') from public.interview_session_my_answers a where a.user_id=p_account and a.session_id=p_session);
end $$;
revoke all on function public.subscription_clipboard_read(uuid,uuid) from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_clipboard_read(uuid,uuid) to usage_executor;
commit;
