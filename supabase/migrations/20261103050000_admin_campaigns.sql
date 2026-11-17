begin;
create table administration.campaigns (
 id uuid primary key, name text not null check(length(name) between 1 and 120), subject text not null check(length(subject) between 1 and 160),
 body text not null check(length(body) between 1 and 10000), revision bigint not null default 1,
 state text not null default 'draft' check(state in ('draft','queued','complete','expired','blocked')),
 author uuid not null, previewed_revision bigint, created_at timestamptz not null default clock_timestamp(), updated_at timestamptz not null default clock_timestamp()
);
create table administration.audience_reviews (
 id uuid primary key default gen_random_uuid(), campaign_id uuid not null, revision bigint not null,
 actor uuid not null, actor_revision bigint not null, session_id uuid not null, recipient_count bigint not null,
 created_at timestamptz not null default clock_timestamp(), expires_at timestamptz not null default clock_timestamp()+interval '5 minutes',
 references_until timestamptz not null default clock_timestamp()+interval '7 days', consumed_at timestamptz
);
create table administration.audience_members (
 review_id uuid not null, account_id uuid not null, primary key(review_id,account_id)
);
create table administration.campaign_deliveries (
 id uuid primary key default gen_random_uuid(), campaign_id uuid not null, review_id uuid not null,
 account_id uuid, test_revision bigint not null default 0, state text not null default 'pending' check(state in ('pending','running','sending','accepted','delivered','bounced','skipped','failed','unknown')),
 lease uuid, lease_until timestamptz, attempts integer not null default 0,
 event_id uuid, message_id uuid unique, last_callback timestamptz, terminal_at timestamptz,
 created_at timestamptz not null default clock_timestamp(), unique(campaign_id,account_id,test_revision)
);
-- Non-identifying spent campaign IDs prevent reactivation after audience/delivery expiry.
create table administration.campaign_fences(id uuid primary key,revision bigint not null,state text not null check(state in ('sent','expired','restored_blocked')));
create table administration.campaign_callbacks(delivery_id text primary key,raw_hash text not null,message_id uuid not null,recorded_at timestamptz not null default clock_timestamp());
do $$ declare t text; begin foreach t in array array['campaigns','audience_reviews','audience_members','campaign_deliveries','campaign_fences','campaign_callbacks'] loop
 execute format('alter table administration.%I enable row level security',t);
 execute format('revoke all on administration.%I from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor',t);
end loop; end$$;
create function administration.marketing_allowed(p_account uuid) returns boolean language sql stable security definer set search_path=pg_catalog as $$
 select exists(select 1 from auth.users u join public.user_settings s on s.user_id=u.id
 where u.id=p_account and u.email_confirmed_at is not null and u.deleted_at is null and (u.banned_until is null or u.banned_until<=statement_timestamp())
 and s.marketing_email_opt_in and not exists(select 1 from administration.memberships where subject=u.id)
 and not exists(select 1 from public.subscription_deletion_jobs where account_id=u.id)
 and not exists(select 1 from public.privacy_restored_subjects where account_id=u.id)
 and not administration.restricted(u.id) and not public.privacy_email_denied(u.email))
$$;
revoke all on function administration.marketing_allowed(uuid) from public,anon,authenticated,service_role,admin_executor,admin_dispatch_executor;
create function administration.campaign_view(p_id uuid) returns jsonb language sql stable security definer set search_path=pg_catalog as $$
 select jsonb_build_object('campaign_id',c.id,'name',c.name,'subject',c.subject,'body',c.body,'template_version','admin_campaign.v1','state',c.state,'revision',c.revision::text,'updated_at',c.updated_at,
 'reconciliation_required',(select count(*) from administration.campaign_deliveries where campaign_id=c.id and state='unknown'),'results',(select coalesce(jsonb_object_agg(state,n),'{}') from(select state,count(*) n from administration.campaign_deliveries where campaign_id=c.id and test_revision=0 group by state) q)) from administration.campaigns c where c.id=p_id
$$;
revoke all on function administration.campaign_view(uuid) from public,anon,authenticated,service_role,admin_executor,admin_dispatch_executor;
create function public.administration_campaign(p_actor uuid,p_session uuid,p_presence timestamptz,p_action text,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare access jsonb; member administration.memberships; c administration.campaigns; v administration.audience_reviews; target uuid; n bigint; begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' or octet_length(p_doc::text)>32768 then raise exception 'denied' using errcode='42501'; end if;
 access:=public.administration_call(p_actor,null,null,'me','{}'); if access ? 'error' then return access; end if; member:=administration.member(p_actor);
 if p_action='list' then return jsonb_build_object('items',(select coalesce(jsonb_agg(administration.campaign_view(id)),'[]') from (select id from administration.campaigns where id>coalesce((p_doc->>'after')::uuid,'00000000-0000-0000-0000-000000000000') order by id limit 100) q),'as_of',statement_timestamp()); end if;
 if p_action='confirm' then
  if not p_doc ?& array['review_id','confirm','operation_id'] or p_doc-array['review_id','confirm','operation_id']<>'{}'::jsonb or p_doc->'confirm'<>'true'::jsonb then return jsonb_build_object('error','invalid'); end if;
  select * into v from administration.audience_reviews where id=(p_doc->>'review_id')::uuid and actor=p_actor and session_id=p_session for update;
  if not found then return jsonb_build_object('error','not_found'); end if;
  target:=v.campaign_id;
 else target:=(p_doc->>'campaign_id')::uuid; end if;
 select * into c from administration.campaigns where id=target for update;
 if p_action='save' then
  if not p_doc ?& array['campaign_id','revision','name','subject','body'] or p_doc-array['campaign_id','revision','name','subject','body']<>'{}'::jsonb then return jsonb_build_object('error','invalid'); end if;
  if (c.id is not null and (c.state<>'draft' or c.revision::text<>p_doc->>'revision')) or (c.id is null and p_doc->>'revision'<>'0') or exists(select 1 from administration.campaign_fences where id=target) then return jsonb_build_object('error','conflict'); end if;
  if length(p_doc->>'name') not between 1 and 120 or length(p_doc->>'subject') not between 1 and 160 or length(p_doc->>'body') not between 1 and 10000 or p_doc->>'subject' ~ '[\r\n]' then return jsonb_build_object('error','invalid'); end if;
  insert into administration.campaigns(id,name,subject,body,author) values(target,p_doc->>'name',p_doc->>'subject',p_doc->>'body',p_actor)
  on conflict(id) do update set name=excluded.name,subject=excluded.subject,body=excluded.body,revision=administration.campaigns.revision+1,previewed_revision=null,updated_at=clock_timestamp();
  update administration.audience_reviews set expires_at=least(expires_at,clock_timestamp()) where campaign_id=target and consumed_at is null;
  perform administration.audit_action(p_actor,member.role,null,'campaign.save','confirmed','campaign',gen_random_uuid());
  return administration.campaign_view(target);
 end if;
 if c.id is null then return jsonb_build_object('error','not_found'); end if;
 if p_action in ('read','preview') then
  if p_action='preview' then
   update administration.campaigns set previewed_revision=revision where id=c.id;
   perform administration.audit_action(p_actor,member.role,null,'campaign.preview','confirmed','campaign',gen_random_uuid());
  end if;
  return administration.campaign_view(c.id);
 end if;
 if p_session is null or p_presence is null or p_presence>clock_timestamp() or p_presence<clock_timestamp()-interval '5 minutes' or not administration.authenticator_ready(p_actor) then return jsonb_build_object('error','reauthentication_required'); end if;
 if p_action='test' then
  if not p_doc ?& array['campaign_id','target','operation_id'] or p_doc-array['campaign_id','target','operation_id']<>'{}'::jsonb or c.state<>'draft' or c.previewed_revision is distinct from c.revision or not administration.marketing_allowed((p_doc->>'target')::uuid) then return jsonb_build_object('error','test_recipient_unavailable'); end if;
  if exists(select 1 from administration.campaign_deliveries where campaign_id=c.id and account_id=(p_doc->>'target')::uuid and test_revision=c.revision) then
   return jsonb_build_object('state','already_requested'); end if;
  insert into administration.audience_reviews(id,campaign_id,revision,actor,actor_revision,session_id,recipient_count,consumed_at) values((p_doc->>'operation_id')::uuid,c.id,c.revision,p_actor,member.revision,p_session,1,clock_timestamp()) returning * into v;
  insert into administration.campaign_deliveries(campaign_id,review_id,account_id,test_revision) values(c.id,v.id,(p_doc->>'target')::uuid,c.revision);
  perform administration.audit_action(p_actor,member.role,null,'campaign.test','queued','campaign',v.id);
  return jsonb_build_object('state','queued');
 elsif p_action='audience' then
  if c.state<>'draft' or c.previewed_revision is distinct from c.revision or c.updated_at<=clock_timestamp()-interval '90 days' then return jsonb_build_object('error','conflict'); end if;
  select count(*) into n from(select id from auth.users where administration.marketing_allowed(id) limit 10001) q;
  if n>10000 then return jsonb_build_object('error','audience_limit'); end if;
  insert into administration.audience_reviews(campaign_id,revision,actor,actor_revision,session_id,recipient_count) values(c.id,c.revision,p_actor,member.revision,p_session,n) returning * into v;
  insert into administration.audience_members select v.id,u.id from auth.users u where administration.marketing_allowed(u.id) order by u.id limit 10001;
  get diagnostics n=row_count;
  if n<>v.recipient_count or n>10000 then delete from administration.audience_members where review_id=v.id; delete from administration.audience_reviews where id=v.id; return jsonb_build_object('error','audience_changed'); end if;
  return jsonb_build_object('review_id',v.id,'campaign_id',c.id,'revision',c.revision::text,'recipient_count',n,'count_as_of',v.created_at,'expires_at',v.expires_at,'rule','eligible_marketing_customers.v1');
 elsif p_action='confirm' then
  if v.consumed_at is not null then
   return coalesce((select jsonb_build_object('operation_id',id,'state',state) from administration.receipts where id=(p_doc->>'operation_id')::uuid and review_id=v.id and actor=p_actor),jsonb_build_object('error','conflict'));
  end if;
  if v.revision<>c.revision or v.actor_revision<>member.revision or c.state<>'draft' or v.expires_at<=clock_timestamp() or v.references_until<=clock_timestamp() then return jsonb_build_object('error','conflict'); end if;
  if (select count(*) from administration.audience_members where review_id=v.id)<>v.recipient_count then return jsonb_build_object('error','audience_expired'); end if;
  insert into administration.campaign_fences values(c.id,c.revision,'sent');
  insert into administration.campaign_deliveries(campaign_id,review_id,account_id) select c.id,v.id,account_id from administration.audience_members where review_id=v.id;
  update administration.campaigns set state=case when v.recipient_count=0 then 'complete' else 'queued' end where id=c.id;
  update administration.audience_reviews set consumed_at=clock_timestamp() where id=v.id;
  insert into administration.receipts(id,actor,review_id,action,target,revision,state) values((p_doc->>'operation_id')::uuid,p_actor,v.id,'campaign.send',c.id,c.revision,'queued');
  perform administration.audit_action(p_actor,member.role,null,'campaign.send','queued','campaign',(p_doc->>'operation_id')::uuid);
  return jsonb_build_object('operation_id',p_doc->>'operation_id','state','queued');
 end if;
 return jsonb_build_object('error','invalid');
end$$;
revoke all on function public.administration_campaign(uuid,uuid,timestamptz,text,jsonb) from public,anon,authenticated,service_role,admin_dispatch_executor,admin_retention_executor,admin_bootstrap_executor;
grant execute on function public.administration_campaign(uuid,uuid,timestamptz,text,jsonb) to admin_executor;
create function public.administration_campaign_work(p_action text,p_doc jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare d administration.campaign_deliveries; v administration.audience_reviews; member administration.memberships; c administration.campaigns; begin
 if session_user<>'admin_dispatch_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform 1 from administration.configuration where singleton and (enabled or p_action='finish') for update; if not found then return null; end if;
 if p_action='claim' then
  update administration.campaign_deliveries set state='unknown',terminal_at=null,lease=null where state='sending' and lease_until<=clock_timestamp();
  update administration.campaign_deliveries set state='failed',terminal_at=clock_timestamp(),lease=null,lease_until=null where state='running' and attempts>=5 and lease_until<=clock_timestamp();
  update administration.campaigns campaign_row set state='complete' where campaign_row.state='queued' and not exists(select 1 from administration.campaign_deliveries delivery_row where delivery_row.campaign_id=campaign_row.id and delivery_row.test_revision=0 and delivery_row.state in ('pending','running','sending'));
  select * into d from administration.campaign_deliveries where (state='pending' or state='running' and lease_until<=clock_timestamp()) and attempts<5 order by created_at,id limit 1 for update skip locked;
  if not found then return null; end if;
 else
  select * into d from administration.campaign_deliveries where id=(p_doc->>'id')::uuid and lease=(p_doc->>'lease')::uuid and lease_until>clock_timestamp() for update;
  if not found then raise exception 'stale delivery' using errcode='40001'; end if;
 end if;
 select * into v from administration.audience_reviews where id=d.review_id;
 select * into c from administration.campaigns where id=d.campaign_id;
 member:=administration.member(v.actor);
 if p_action in ('claim','eligible') and (v.id is null or v.references_until<=clock_timestamp() or not ((d.test_revision=0 and c.state='queued') or (d.test_revision=c.revision and c.state='draft' and c.previewed_revision=c.revision)) or member.subject is null or member.revision<>v.actor_revision or not administration.marketing_allowed(d.account_id)) then
  update administration.campaign_deliveries set state='skipped',terminal_at=clock_timestamp(),lease=null where id=d.id;
  if c.state='queued' and not exists(select 1 from administration.campaign_deliveries where campaign_id=c.id and test_revision=0 and state in ('pending','running','sending')) then update administration.campaigns set state='complete' where id=c.id; end if;
  return jsonb_build_object('skipped',true,'id',d.id);
 end if;
 if p_action='claim' then
  update administration.campaign_deliveries set state='running',attempts=attempts+1,lease=gen_random_uuid(),lease_until=clock_timestamp()+interval '30 seconds' where id=d.id returning * into d;
  return jsonb_build_object('id',d.id,'lease',d.lease,'campaign_id',d.campaign_id,'account_id',d.account_id,'email',(select email from auth.users where id=d.account_id),'subject',c.subject,'body',c.body);
 elsif p_action='eligible' then return jsonb_build_object('allowed',true);
 elsif p_action='finish' then
  if coalesce(p_doc->>'state','') not in ('accepted','failed','unknown','skipped') then raise exception 'invalid state' using errcode='22023'; end if;
  update administration.campaign_deliveries set state=p_doc->>'state',event_id=coalesce((p_doc->>'event_id')::uuid,event_id),message_id=coalesce((p_doc->>'message_id')::uuid,message_id),terminal_at=case when p_doc->>'state'='unknown' then null else clock_timestamp() end,lease=null where id=d.id;
  if c.state='queued' and not exists(select 1 from administration.campaign_deliveries where campaign_id=c.id and test_revision=0 and state in ('pending','running','sending')) then update administration.campaigns set state='complete' where id=c.id; end if;
  return jsonb_build_object('state',p_doc->>'state');
 end if;
 raise exception 'invalid action' using errcode='22023';
end$$;
revoke all on function public.administration_campaign_work(text,jsonb) from public,anon,authenticated,service_role,admin_executor,admin_retention_executor,admin_bootstrap_executor;
grant execute on function public.administration_campaign_work(text,jsonb) to admin_dispatch_executor;
create function public.administration_mail(p_task uuid,p_lease uuid,p_action text,p_doc jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare d administration.campaign_deliveries; v administration.audience_reviews; member administration.memberships; result jsonb; begin
 if session_user<>'admin_dispatch_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 select * into d from administration.campaign_deliveries where id=p_task and lease=p_lease and lease_until>clock_timestamp() and state in ('running','sending') for update;
 if not found or d.account_id is distinct from (p_doc->>'p_user_id')::uuid then raise exception 'mail scope denied' using errcode='42501'; end if;
 select * into v from administration.audience_reviews where id=d.review_id;
 member:=administration.member(v.actor);
 if p_action='allowed' then return jsonb_build_object('allowed',member.subject is not null and member.revision=v.actor_revision and v.references_until>clock_timestamp() and administration.marketing_allowed(d.account_id)); end if;
 if p_action not in ('complete_outbound_email_event','allowed') and (member.subject is null or member.revision<>v.actor_revision or v.references_until<=clock_timestamp()) then raise exception 'authority changed' using errcode='42501'; end if;
 perform 1 from auth.users where id=d.account_id for no key update;
 if p_action='token' then
  if not administration.marketing_allowed(d.account_id) or p_doc->>'recipient_email' is distinct from (select email from auth.users where id=d.account_id) then raise exception 'recipient unavailable' using errcode='42501'; end if;
  insert into public.marketing_unsubscribe_tokens(user_id,recipient_email,token_hash,email_category,expires_at) values(d.account_id,p_doc->>'recipient_email',p_doc->>'token_hash','marketing',(p_doc->>'expires_at')::timestamptz); return '{}';
 end if;
 if p_action='claim_outbound_email_event' then
  if p_doc->>'p_email_type'<>'marketing_product_update' or p_doc->>'p_recipient_email' is distinct from (select email from auth.users where id=d.account_id) or p_doc->>'p_idempotency_key'<>'admin-campaign:'||d.id::text then raise exception 'mail identity denied' using errcode='42501'; end if;
  select to_jsonb(event) into result from public.claim_outbound_email_event(d.account_id,null,'marketing_product_update',p_doc->>'p_recipient_email',p_doc->>'p_idempotency_key',p_doc->'p_metadata_json',(p_doc->>'p_pending_expires_at')::timestamptz) event;
  update administration.campaign_deliveries set event_id=(result->>'id')::uuid where id=d.id;
 else
  if d.event_id is distinct from (p_doc->>'p_event_id')::uuid then raise exception 'mail event denied' using errcode='42501'; end if;
  if p_action='begin_outbound_email_event_send' then
   select to_jsonb(event) into result from public.begin_outbound_email_event_send(d.account_id,d.event_id,(p_doc->>'p_lease_expires_at')::timestamptz) event;
   update administration.campaign_deliveries set state='sending' where id=d.id;
  elsif p_action='complete_outbound_email_event' then
   select to_jsonb(event) into result from public.complete_outbound_email_event(d.account_id,d.event_id,(p_doc->>'p_claim_token')::uuid,p_doc->>'p_status',p_doc->>'p_provider',p_doc->>'p_provider_message_id',p_doc->>'p_error_code') event;
  else raise exception 'mail action denied' using errcode='42501'; end if;
 end if;
 return result;
end$$;
revoke all on function public.administration_mail(uuid,uuid,text,jsonb) from public,anon,authenticated,service_role,admin_executor,admin_retention_executor,admin_bootstrap_executor;
grant execute on function public.administration_mail(uuid,uuid,text,jsonb) to admin_dispatch_executor;
create function public.administration_campaign_callback(p_doc jsonb) returns boolean language plpgsql security definer set search_path=pg_catalog as $$
declare d administration.campaign_deliveries; prior administration.campaign_callbacks; desired text; begin
 if session_user<>'admin_dispatch_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 select * into prior from administration.campaign_callbacks where delivery_id=p_doc->>'delivery_id';
 if found then return prior.raw_hash=p_doc->>'raw_hash'; end if;
 select * into d from administration.campaign_deliveries where message_id=(p_doc->>'message_id')::uuid for update;
 if not found then return false; end if;
 desired:=case p_doc->>'event_type' when 'email.delivered' then 'delivered' when 'email.bounced' then 'bounced' when 'email.failed' then 'failed' when 'email.sent' then 'accepted' else null end;
 if desired is null then return false; end if;
 insert into administration.campaign_callbacks(delivery_id,raw_hash,message_id) values(p_doc->>'delivery_id',p_doc->>'raw_hash',d.message_id);
 if d.last_callback is null or d.last_callback<(p_doc->>'event_at')::timestamptz then
  update administration.campaign_deliveries set state=case when state in ('delivered','bounced','failed') and desired='accepted' then state else desired end,last_callback=(p_doc->>'event_at')::timestamptz,terminal_at=case when desired in ('delivered','bounced','failed') then (p_doc->>'event_at')::timestamptz else terminal_at end where id=d.id;
 end if;
 return true;
end$$;
revoke all on function public.administration_campaign_callback(jsonb) from public,anon,authenticated,service_role,admin_executor,admin_retention_executor,admin_bootstrap_executor;
grant execute on function public.administration_campaign_callback(jsonb) to admin_dispatch_executor;
commit;
