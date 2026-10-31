-- Additive C10/C12 callback receipt/projection boundary. Local validation only.
begin;
alter table public.billing_notification_sources add column delivery_scope text;
alter table public.billing_notification_sources add column resend_message_id uuid;
create unique index billing_resend_message_scope on public.billing_notification_sources(delivery_scope,resend_message_id);
alter table public.billing_email_delivery_events
 add column scope text,
 add column delivery_id text,
 add column raw_hash text,
 add column message_id uuid,
 add column event_type text,
 add column event_at timestamptz,
 add column failure_detail text check(failure_detail in ('unspecified','Permanent','Temporary','reached_daily_quota')),
 add column source_id uuid references public.billing_notification_sources(id),
 add column processing_state text not null default 'legacy' check(processing_state in ('legacy','pending','applied','expired')),
 add column attempts integer not null default 0 check(attempts between 0 and 24),
 add column next_attempt_at timestamptz not null default clock_timestamp(),
 add column processed_at timestamptz;
create unique index billing_delivery_identity on public.billing_email_delivery_events(scope,delivery_id);
create index billing_delivery_source on public.billing_email_delivery_events(source_id,event_at,event_hash) where processing_state='applied';
create index billing_delivery_pending on public.billing_email_delivery_events(next_attempt_at) where processing_state='pending';

alter function public.billing_notification_call(text,uuid,jsonb) rename to billing_notification_call_legacy;
revoke all on function public.billing_notification_call_legacy(text,uuid,jsonb) from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;
create function public.billing_notification_call(p_action text,p_id uuid default null,p_doc jsonb default '{}') returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare result jsonb;
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action='delivery' then raise exception 'use verified receipt boundary' using errcode='42501'; end if;
 result:=public.billing_notification_call_legacy(p_action,p_id,p_doc);
 if p_action='claim' and result is not null and p_doc->>'scope' ~ '^[a-z][a-z0-9._-]{0,63}$' then
  update public.billing_notification_sources set delivery_scope=coalesce(delivery_scope,p_doc->>'scope') where id=p_id;
 elsif p_action='complete' and p_doc->>'state'='accepted' and p_doc->>'provider'='resend' then
  update public.billing_notification_sources n set resend_message_id=e.provider_message_id::uuid
   from public.outbound_email_events e where n.id=p_id and n.event_id=e.id and e.provider='resend' and e.provider_message_id is not null and n.delivery_scope is not null;
 end if;
 return result;
end $$;
revoke all on function public.billing_notification_call(text,uuid,jsonb) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_notification_call(text,uuid,jsonb) to usage_binding_executor;

create function public.billing_delivery_call(p_action text,p_doc jsonb default '{}') returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
#variable_conflict use_variable
declare e public.billing_email_delivery_events; n public.billing_notification_sources; existing public.billing_email_delivery_events; adverse boolean; delivered boolean; sent boolean;
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action='ingest' then
  if coalesce(not (p_doc->>'scope' ~ '^[a-z][a-z0-9._-]{0,63}$') or length(p_doc->>'delivery_id') not between 1 and 120 or p_doc->>'raw_hash' !~ '^[0-9a-f]{64}$' or p_doc->>'event_type' not in ('email.sent','email.delivered','email.delivery_delayed','email.bounced','email.complained','email.failed') ,true) then raise exception 'invalid receipt' using errcode='22023'; end if;
  -- ponytail: serialized ingress capacity check; replace with partition quotas only if throughput requires it.
  perform pg_advisory_xact_lock(27102712);
  select * into existing from public.billing_email_delivery_events where scope=p_doc->>'scope' and delivery_id=p_doc->>'delivery_id';
  if found then
   if existing.raw_hash<>p_doc->>'raw_hash' then return '{"error":"conflict"}'::jsonb; end if;
   return '{"duplicate":true}'::jsonb;
  end if;
  if (select count(*) from public.billing_email_delivery_events)>=100000 or (select count(*) from public.billing_email_delivery_events where processing_state='pending')>=1000 then raise exception 'receipt capacity reached' using errcode='54000'; end if;
  insert into public.billing_email_delivery_events(event_hash,scope,delivery_id,raw_hash,message_id,event_type,event_at,processing_state,failure_detail)
   values(encode(sha256(convert_to((p_doc->>'scope')||':'||(p_doc->>'delivery_id'),'UTF8')),'hex'),p_doc->>'scope',p_doc->>'delivery_id',p_doc->>'raw_hash',(p_doc->>'message_id')::uuid,p_doc->>'event_type',(p_doc->>'event_at')::timestamptz,'pending',p_doc->>'failure_detail');
  return '{"received":true}'::jsonb;
 elsif p_action='process' then
  for e in select * from public.billing_email_delivery_events where processing_state='pending' and next_attempt_at<=clock_timestamp() order by recorded_at limit 20 for update skip locked loop
   select s.* into n from public.billing_notification_sources s join public.outbound_email_events o on o.id=s.event_id
    where s.delivery_scope=e.scope and s.resend_message_id=e.message_id and o.provider='resend' and o.provider_message_id=e.message_id::text for update of s;
   if not found then
    update public.billing_email_delivery_events set attempts=attempts+1,processing_state=case when attempts>=23 or recorded_at<clock_timestamp()-interval '24 hours' then 'expired' else 'pending' end,next_attempt_at=clock_timestamp()+interval '5 minutes',processed_at=clock_timestamp() where event_hash=e.event_hash;
    continue;
   end if;
   update public.billing_email_delivery_events set source_id=n.id,processing_state='applied',attempts=attempts+1,processed_at=clock_timestamp() where event_hash=e.event_hash;
   select bool_or(event_type in ('email.bounced','email.complained','email.failed')),bool_or(event_type='email.delivered'),bool_or(event_type='email.sent') into adverse,delivered,sent from public.billing_email_delivery_events where source_id=n.id and processing_state='applied';
   update public.billing_notification_sources set delivery_state=case when adverse then 'failed' when delivered then 'delivered' when sent and delivery_state not in ('failed','delivered') then 'accepted' else delivery_state end where id=n.id;
  end loop;
  return '{"processed":true}'::jsonb;
 end if;
 raise exception 'invalid action' using errcode='22023';
end $$;
revoke all on function public.billing_delivery_call(text,jsonb) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_delivery_call(text,jsonb) to usage_binding_executor;

alter function public.billing_admin_snapshot(uuid) rename to billing_admin_snapshot_legacy;
create function public.billing_admin_snapshot(p_account uuid) returns jsonb language sql security definer set search_path=pg_catalog as $$
 select jsonb_set(public.billing_admin_snapshot_legacy(p_account),'{notifications}',coalesce((select jsonb_agg(item || jsonb_build_object(
 'delivery_history_count',(select count(*) from public.billing_email_delivery_events where source_id=(item->>'id')::uuid),'delivery_events',coalesce((select jsonb_agg(jsonb_build_object('type',event_type,'provider_event_at',event_at,'processed_at',processed_at,'failure_detail',failure_detail,'failure_category',case when event_type in ('email.bounced','email.complained','email.failed') then split_part(event_type,'.',2) else null end) order by event_at,event_hash) from (select * from public.billing_email_delivery_events where source_id=(item->>'id')::uuid and processing_state='applied' order by event_at desc,event_hash limit 50) recent),'[]'::jsonb))) from jsonb_array_elements(public.billing_admin_snapshot_legacy(p_account)->'notifications') item),'[]'::jsonb))
$$;
revoke all on function public.billing_admin_snapshot(uuid) from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;
commit;
