-- Closed-by-default composition of accepted unmetered answers and turn storage.
begin;
create function public.subscription_session_read(p_account uuid,p_session uuid) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare s public.interview_sessions;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform public.subscription_current(p_account,false);
 select * into s from public.interview_sessions where id=p_session and user_id=p_account;
 if not found then raise exception 'not found' using errcode='P0002'; end if;
 return to_jsonb(s);
end $$;

create function public.subscription_answer_turn(p_action text,p_account uuid,p_session uuid,p_key text,p_hash text,
 p_attempt integer,p_supersedes text,p_token uuid,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare terms jsonb; selected_model text; source text; request_doc jsonb;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action not in ('claim','recover','check','checkpoint','complete','cancel','fail') then raise exception 'invalid action' using errcode='22023'; end if;
 if p_action not in ('cancel','fail') then
   perform public.subscription_current(p_account,false);
   select o.canonical_json::jsonb->'terms' into terms from public.account_plan_bindings b join public.catalog_offer_versions o using(offer_version_id) where b.account_id=p_account;
   if not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'='answers.generate' and e->>'allowed'='true') then raise exception 'denied' using errcode='42501'; end if;
   -- Finite/missing manual allowances are not silently treated as unlimited.
   if not exists(select 1 from jsonb_array_elements(coalesce(terms->'allowances','[]')) a where a->>'meter'='answers.completed' and a->>'mode'='unlimited') then raise exception 'metering unavailable' using errcode='P0005'; end if;
 end if;
 perform pg_advisory_xact_lock(hashtextextended(p_session::text,0));
 select to_jsonb(s)->>'selected_model_key' into selected_model from public.interview_sessions s where id=p_session and user_id=p_account for update;
 if not found then raise exception 'not found' using errcode='P0002'; end if;
 if p_action not in ('cancel','fail') and selected_model is not null and
   exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'='answers.generate' and
     jsonb_array_length(coalesce(e->'model_keys','[]'))>0 and not (e->'model_keys' ? selected_model)) then
   raise exception 'model denied' using errcode='42501';
 end if;
 select payload->'request' into request_doc from public.session_generation_turns where session_id=p_session and user_id=p_account and request_id=p_key;
 request_doc:=coalesce(request_doc,p_payload->'request');
 source:=lower(coalesce(request_doc->>'source',''));
 if p_action not in ('cancel','fail') and source not in ('','typed','manual','chat') then raise exception 'execution path unavailable' using errcode='P0005'; end if;
 return public.session_generation_turn(p_action,p_account,p_session,p_key,p_hash,p_attempt,p_supersedes,p_token,p_payload);
end $$;
revoke all on function public.subscription_session_read(uuid,uuid),
 public.subscription_answer_turn(text,uuid,uuid,text,text,integer,text,uuid,jsonb)
 from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_session_read(uuid,uuid),
 public.subscription_answer_turn(text,uuid,uuid,text,text,integer,text,uuid,jsonb) to usage_executor;
commit;
