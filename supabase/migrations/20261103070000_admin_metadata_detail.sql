-- Explicit operational metadata only; existing authority/pagination/task projections stay in place.
begin;
create function administration.customer_metadata(p_subject uuid) returns jsonb
language sql stable security definer set search_path=pg_catalog as $$
 select jsonb_build_object(
  'auth_provider_labels',(select coalesce(jsonb_agg(distinct provider),'[]') from auth.identities where user_id=p_subject),
  'staff_restriction_state',case when administration.restricted(p_subject) then 'restricted' else 'unrestricted' end,
  'account_access_state',case when administration.restricted(p_subject) or exists(select 1 from public.subscription_deletion_jobs where account_id=p_subject) or exists(select 1 from public.privacy_restored_subjects where account_id=p_subject) then 'restricted' else 'unrestricted' end,
  'plan_code',(select b.canonical_json::jsonb->'plan'->>'code' from public.account_plan_bindings a join public.catalog_offer_versions b using(offer_version_id) where a.account_id=p_subject),
  'subscription_state',(select case when active and (valid_until is null or valid_until>statement_timestamp()) then 'active' else 'expired_or_inactive' end from public.account_plan_bindings where account_id=p_subject),
  'last_product_activity_at',null,'activity_coverage','not_instrumented',
  'resources',jsonb_build_object(
   'resume_count',(select count(*) from public.resumes where user_id=p_subject and status<>'deleted'),
   'active_resume_count',(select count(*) from public.resumes where user_id=p_subject and status<>'deleted' and is_active),
   'resume_processing_state',(select coalesce(jsonb_object_agg(status,n),'{}') from (select status,count(*) n from public.resumes where user_id=p_subject and status<>'deleted' group by status) counts),
   'session_count',(select count(*) from public.interview_sessions where user_id=p_subject),
   'last_session_started_at',(select max(started_at) from public.interview_sessions where user_id=p_subject),
   'last_session_ended_at',(select max(ended_at) from public.interview_sessions where user_id=p_subject),
   'job_context_count',(select count(*) from public.job_contexts where user_id=p_subject),
   'status_coverage','current_controlled_rows'),
  'consent',(select jsonb_build_object('marketing_opt_in',marketing_email_opt_in,
   'marketing_preference_updated_at',greatest(marketing_email_opt_in_at,marketing_email_opt_out_at),
   'terms_version',case when terms_accepted then consent_version end,
   'privacy_version',case when privacy_accepted then consent_version end,
   'consent_accepted_at',greatest(terms_accepted_at,privacy_accepted_at)) from public.user_settings where user_id=p_subject))
$$;
revoke all on function administration.customer_metadata(uuid) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
do $$ declare definition text; marker text; begin
 definition:=pg_get_functiondef('public.administration_read(uuid,text,uuid,uuid,text)'::regprocedure);
 marker:='perform administration.audit_action';
 if position(marker in definition)=0 then raise exception 'metadata compatibility mismatch'; end if;
 execute replace(definition,marker,'if p_kind=''user'' and result is not null and not (result ? ''error'') then result:=result||administration.customer_metadata(p_target); end if; '||marker);
end$$;
create function administration.subscription_metadata(p_subject uuid) returns jsonb language sql stable security definer set search_path=pg_catalog as $$
 select jsonb_build_object('operations',coalesce(jsonb_agg(jsonb_build_object('subscription_id',o.operation_id,'plan_code',o.snapshot::jsonb->'plan'->>'code',
 'paid_status',o.state,'renewal_state',o.provider_state,'cancellation_state',case when o.provider_state in ('cancelled','completed','expired') then 'confirmed' when o.cancel_requested then 'unknown' else 'none' end,
 'amount_minor',o.amount::text,'currency',o.currency,'paid_through_at',case when b.price_id=o.price_id then b.valid_until end,
 'cancellation_requested_at',null,'provider_verified_at',o.last_checked_at,
 'billing_resolution_pending',exists(select 1 from public.subscription_deletion_jobs d where d.account_id=p_subject) and o.provider_state not in ('cancelled','completed','expired'),
 'billing_review_due_at',(select min(due_at) from public.privacy_followup_tasks t join public.privacy_deletion_requests d using(request_id) where d.account_id=p_subject and t.kind='billing_review')) order by o.operation_id),'[]'),'as_of',statement_timestamp())
 from public.billing_operations o left join public.account_plan_bindings b on b.account_id=o.account_id where o.account_id=p_subject
$$;
revoke all on function administration.subscription_metadata(uuid) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
do $$ declare definition text; marker text; begin
 definition:=pg_get_functiondef('public.administration_read(uuid,text,uuid,uuid,text)'::regprocedure);
 marker:='perform administration.audit_action';
 execute replace(definition,marker,'if p_kind=''subscription'' then result:=administration.subscription_metadata(p_target); end if; '||marker);
end$$;
commit;
