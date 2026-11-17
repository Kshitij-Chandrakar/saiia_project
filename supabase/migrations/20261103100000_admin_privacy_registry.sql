begin;
create function public.administration_schema() returns jsonb language sql stable security definer set search_path=pg_catalog as $$
 select jsonb_object_agg(table_name,fields) from(select table_name,jsonb_object_agg(column_name,data_type||':'||udt_name) fields from information_schema.columns where table_schema='administration' group by table_name) x
$$;
revoke all on function public.administration_schema() from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
grant execute on function public.administration_schema() to privacy_cleanup_executor,admin_executor;
create function public.administration_subject_export(p_job uuid) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare subject_id uuid; result jsonb; begin
 if session_user not in ('privacy_content_executor','privacy_restore_executor') or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 select account_id into subject_id from public.privacy_content_jobs where id=p_job and kind='export' and state in ('pending','running') for share;
 if not found or exists(select 1 from public.subscription_deletion_jobs where account_id=subject_id) or exists(select 1 from public.privacy_restored_subjects where account_id=subject_id) or administration.restricted(subject_id) then raise exception 'unavailable' using errcode='42501'; end if;
 return jsonb_build_object('version','c15.admin.personal.v1',
 'executed_attempts',(select coalesce(jsonb_agg(jsonb_build_object('provider',provider,'model',model,'reported_model',reported_model,'outcome',outcome,'input_tokens',input_tokens,'output_tokens',output_tokens,'duration_ms',duration_ms,'completed_at',completed_at) order by completed_at,id),'[]') from administration.provider_attempts where subject=subject_id),
 'activity',(select coalesce(jsonb_agg(jsonb_build_object('kind',kind,'completed_at',completed_at) order by completed_at,event_id),'[]') from administration.activity where subject=subject_id),
 'campaign_delivery_status',(select coalesce(jsonb_agg(jsonb_build_object('state',state,'created_at',created_at,'terminal_at',terminal_at) order by created_at,id),'[]') from administration.campaign_deliveries where account_id=subject_id),
 'authored_campaigns',(select coalesce(jsonb_agg(jsonb_build_object('name',name,'subject',subject,'body',body,'state',state,'created_at',created_at,'updated_at',updated_at) order by created_at,id),'[]') from administration.campaigns where author=subject_id),
 'exclusions',jsonb_build_array('protected audit history','other staff identities and audience members','confirmation and dispatch credentials','internal retry and provider identifiers'));
end$$;
revoke all on function public.administration_subject_export(uuid) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
grant execute on function public.administration_subject_export(uuid) to privacy_runtime_owner;
commit;
