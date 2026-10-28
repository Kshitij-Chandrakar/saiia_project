-- Private transport capabilities. No new login, public RPC grant or activation.
begin;
create function public.subscription_auto_authorize(p_account uuid,p_run uuid,p_owner uuid,p_fence bigint,p_source text) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare r public.subscription_auto_runs; o public.usage_operations; terms jsonb;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform public.subscription_current(p_account,false);
 select c.canonical_json::jsonb->'terms' into terms from public.account_plan_bindings b join public.catalog_offer_versions c using(offer_version_id) where b.account_id=p_account;
 if not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'='assistant.auto' and e->>'allowed'='true' and e->'audio_sources' ? p_source) then raise exception 'source denied' using errcode='42501'; end if;
 if not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'='audio.transcribe' and e->>'allowed'='true') then raise exception 'transcription denied' using errcode='42501'; end if;
 select * into r from public.subscription_auto_runs where run_id=p_run and account_id=p_account for update;
 if not found or not r.active or r.owner_token<>p_owner or r.fence<>p_fence then raise exception 'stale owner' using errcode='42501'; end if;
 select * into strict o from public.usage_operations where operation_id=r.slice_id;
 if o.lease_until<=clock_timestamp() then raise exception 'expired' using errcode='42501'; end if;
 return jsonb_build_object('server_time',clock_timestamp(),'authorized_until',o.lease_until);
end $$;

create function public.subscription_auto_disconnect(p_account uuid,p_run uuid,p_owner uuid,p_fence bigint) returns boolean
language plpgsql security definer set search_path=pg_catalog as $$
declare r public.subscription_auto_runs;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 -- Cleanup does not grant/read protected terms, and must work after JWT expiry
 -- or permission removal. Its owner capability exists only inside the backend.
 perform 1 from public.account_plan_bindings where account_id=p_account for update;
 select * into r from public.subscription_auto_runs where run_id=p_run and account_id=p_account for update;
 if not found or r.owner_token<>p_owner then raise exception 'denied' using errcode='42501'; end if;
 if not r.active then return false; end if;
 if r.fence<>p_fence then raise exception 'stale owner' using errcode='42501'; end if;
 perform public.subscription_auto_finish_slice(p_run,clock_timestamp());
 update public.subscription_auto_runs set active=false,fence=fence+1 where run_id=p_run;
 return true;
end $$;

create function public.subscription_auto_turn(p_action text,p_account uuid,p_session uuid,p_key text,p_hash text,
 p_attempt integer,p_supersedes text,p_token uuid,p_payload jsonb,p_run uuid,p_owner uuid,p_fence bigint,p_source text) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare terms jsonb; selected_model text;
begin
 if session_user<>'usage_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action not in ('claim','recover','check','checkpoint','complete','cancel','fail') then raise exception 'invalid action' using errcode='22023'; end if;
 if p_action not in ('cancel','fail') then
   perform public.subscription_auto_authorize(p_account,p_run,p_owner,p_fence,p_source);
   select c.canonical_json::jsonb->'terms' into terms from public.account_plan_bindings b join public.catalog_offer_versions c using(offer_version_id) where b.account_id=p_account;
   if not exists(select 1 from jsonb_array_elements(terms->'entitlements') e where e->>'feature'='answers.generate' and e->>'allowed'='true') or
      not exists(select 1 from jsonb_array_elements(terms->'allowances') a where a->>'meter'='answers.completed' and a->>'mode'='unlimited') then raise exception 'answer unavailable' using errcode='42501'; end if;
 end if;
 perform pg_advisory_xact_lock(hashtextextended(p_session::text,0));
 select to_jsonb(s)->>'selected_model_key' into selected_model from public.interview_sessions s where id=p_session and user_id=p_account for update;
 if not found then raise exception 'not found' using errcode='P0002'; end if;
 if p_action not in ('cancel','fail') and selected_model is not null and exists(select 1 from jsonb_array_elements(terms->'entitlements') e
   where e->>'feature'='answers.generate' and jsonb_array_length(coalesce(e->'model_keys','[]'))>0 and not(e->'model_keys' ? selected_model)) then raise exception 'model denied' using errcode='42501'; end if;
 return public.session_generation_turn(p_action,p_account,p_session,p_key,p_hash,p_attempt,p_supersedes,p_token,p_payload);
end $$;
revoke all on function public.subscription_auto_authorize(uuid,uuid,uuid,bigint,text),public.subscription_auto_disconnect(uuid,uuid,uuid,bigint),
 public.subscription_auto_turn(text,uuid,uuid,text,text,integer,text,uuid,jsonb,uuid,uuid,bigint,text)
 from public,anon,authenticated,service_role,catalog_draft_executor,usage_executor,usage_binding_executor,usage_reconciler;
grant execute on function public.subscription_auto_authorize(uuid,uuid,uuid,bigint,text),public.subscription_auto_disconnect(uuid,uuid,uuid,bigint),
 public.subscription_auto_turn(text,uuid,uuid,text,text,integer,text,uuid,jsonb,uuid,uuid,bigint,text) to usage_executor;
commit;
