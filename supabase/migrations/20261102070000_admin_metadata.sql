-- Fixed metadata projections; never whole customer rows or result JSON.
begin;
create function public.administration_read(p_actor uuid,p_kind text,p_target uuid default null,p_after uuid default null,p_search text default null)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare admission jsonb; result jsonb;
begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 admission:=public.administration_call(p_actor,null,null,'me','{}');
 if admission ? 'error' then return admission; end if;
 if p_kind not in ('users','user','subscription','allowances','privacy') or length(p_search)>320 then return jsonb_build_object('error','invalid'); end if;
 -- Staff are excluded from the support directory for both roles; S has membership tools.
 if p_target is not null and (exists(select 1 from administration.memberships where subject=p_target)
  or not exists(select 1 from auth.users where id=p_target)) then return jsonb_build_object('error','not_found'); end if;
 if p_kind in ('users','user') then
  select coalesce(jsonb_agg(jsonb_build_object('user_id',u.id,'email',u.email,'registered_at',u.created_at,
   'email_verified',u.email_confirmed_at is not null,'deletion_restricted',exists(select 1 from public.privacy_deletion_requests d where d.account_id=u.id and d.accepted_at is not null),
   'data_as_of',statement_timestamp()) order by u.id),'[]') into result
  from (select id,email,created_at,email_confirmed_at from auth.users u where
   not exists(select 1 from administration.memberships m where m.subject=u.id)
   and (p_target is null or u.id=p_target) and (p_after is null or u.id>p_after)
   and (p_search is null or lower(u.email)=lower(p_search) or u.id::text=p_search)
   order by u.id limit 101) u;
  if p_kind='user' then result:=result->0; end if;
 elsif p_kind='subscription' then
  -- Only safe current financial facts; no provider references or staff history.
  select jsonb_build_object('operations',coalesce(jsonb_agg(jsonb_build_object('subscription_id',operation_id,
   'paid_status',state,'renewal_state',provider_state,'cancellation_state',case when provider_state='cancelled' then 'confirmed' when cancel_requested then 'unknown' else 'none' end,
   'amount_minor',amount::text,'currency',currency) order by operation_id),'[]'),'as_of',statement_timestamp()) into result
   from public.billing_operations where account_id=p_target;
 elsif p_kind='allowances' then
  select jsonb_build_object('items',coalesce(jsonb_agg(jsonb_build_object('meter',meter,'unit',null,
   'period_start',starts_at,'period_end',ends_at,'allowance',allowance::text,'used',used::text,'reserved',reserved::text,
   'available',(allowance-used-reserved)::text,'unlimited',mode='unlimited') order by meter,starts_at),'[]'),
   'as_of',statement_timestamp(),'coverage','stored_periods_only') into result from public.usage_periods where account_id=p_target;
 elsif p_kind='privacy' then
  select jsonb_build_object('requests',coalesce(jsonb_agg(jsonb_build_object('request_id',request_id,'scope',scope,
   'accepted_at',accepted_at,'request_state',state,'revision',revision::text) order by created_at),'[]'),
   'as_of',statement_timestamp()) into result from public.privacy_deletion_requests where account_id=p_target;
 end if;
 perform administration.audit_action(p_actor,admission->>'role',p_target,'metadata.read','confirmed',null,gen_random_uuid());
 return case when p_kind='users' then jsonb_build_object('items',jsonb_path_query_array(result,'$[0 to 99]'),'page_size',100,
  'has_more',jsonb_array_length(result)>100,'next_cursor',case when jsonb_array_length(result)>100 then result->99->>'user_id' else null end)
  else coalesce(result,jsonb_build_object('error','not_found')) end;
end$$;
revoke all on function public.administration_read(uuid,text,uuid,uuid,text) from public,anon,authenticated,service_role,admin_bootstrap_executor;
grant execute on function public.administration_read(uuid,text,uuid,uuid,text) to admin_executor;
commit;
