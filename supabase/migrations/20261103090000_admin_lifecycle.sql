begin;
alter table administration.successor_transfers alter column session_id drop not null;
create function public.administration_lifecycle(p_limit integer default 100) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare item record; removed integer:=0; n integer; begin
 if session_user<>'admin_retention_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_limit is null or p_limit<1 or p_limit>100 then raise exception 'invalid bound' using errcode='22023'; end if;
 perform 1 from administration.configuration where singleton and enabled for update; if not found then raise exception 'unavailable' using errcode='P0005'; end if;
 delete from administration.provider_attempts where id in(select id from administration.provider_attempts where completed_at<=clock_timestamp()-interval '90 days' order by completed_at limit p_limit for update skip locked);get diagnostics n=row_count;removed:=removed+n;
 delete from administration.activity where (subject,kind,event_id) in(select subject,kind,event_id from administration.activity where completed_at<=clock_timestamp()-interval '90 days' order by completed_at limit p_limit for update skip locked);get diagnostics n=row_count;removed:=removed+n;
 for item in select id,campaign_id from administration.audience_reviews where references_until<=clock_timestamp() order by references_until limit p_limit for update skip locked loop
  insert into administration.campaign_fences(id,revision,state) select id,revision,'expired' from administration.campaigns where id=item.campaign_id on conflict(id) do nothing;
  update administration.campaign_deliveries set state=case when state='sending' then 'unknown' else 'skipped' end,terminal_at=case when state='sending' then null else coalesce(terminal_at,clock_timestamp()) end,lease=null,lease_until=null where review_id=item.id and state in ('pending','running','sending');
  update administration.campaigns set state='expired' where id=item.campaign_id and state in ('draft','queued');
  delete from administration.audience_members where review_id=item.id;
  delete from administration.audience_reviews where id=item.id;removed:=removed+1;
 end loop;
 for item in select id from administration.campaign_deliveries where terminal_at<=clock_timestamp()-interval '90 days' order by terminal_at limit p_limit for update skip locked loop
  delete from administration.campaign_callbacks where message_id=(select message_id from administration.campaign_deliveries where id=item.id);
  delete from administration.campaign_deliveries where id=item.id;removed:=removed+1;
 end loop;
 for item in select id,revision from administration.campaigns where state='draft' and updated_at<=clock_timestamp()-interval '90 days' order by updated_at limit p_limit for update skip locked loop
  insert into administration.campaign_fences values(item.id,item.revision,'expired') on conflict(id) do nothing;
  delete from administration.audience_members where review_id in(select id from administration.audience_reviews where campaign_id=item.id);
  delete from administration.audience_reviews where campaign_id=item.id;
  delete from administration.campaigns where id=item.id;removed:=removed+1;
 end loop;
 delete from administration.command_reviews where id in(select id from administration.command_reviews where consumed_at is not null or expires_at<=clock_timestamp() order by expires_at limit p_limit for update skip locked);
 update administration.successor_transfers set session_id=null where state in ('accepted','verified') or expires_at<=clock_timestamp();
 delete from administration.successor_transfers where id in(select id from administration.successor_transfers where state='offered' and expires_at<=clock_timestamp() or verified_at<=clock_timestamp()-interval '180 days' order by expires_at limit p_limit for update skip locked);
 delete from administration.commands where id in(select id from administration.commands where state in ('confirmed','failed','blocked') and created_at<=clock_timestamp()-interval '180 days' order by created_at limit p_limit for update skip locked);
 return jsonb_build_object('records_removed',removed,'unresolved_financial_commands',(select count(*) from administration.commands where state in ('pending','running','unknown')));
end$$;
revoke all on function public.administration_lifecycle(integer) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor;
grant execute on function public.administration_lifecycle(integer) to admin_retention_executor;
create function public.administration_subject_cleanup(p_job uuid,p_lease uuid) returns void language plpgsql security definer set search_path=pg_catalog as $$
declare p_subject uuid; begin
 if session_user<>'privacy_cleanup_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 select account_id into p_subject from public.privacy_content_jobs where id=p_job and lease_id=p_lease and kind='account' and state='running' and lease_until>clock_timestamp() for update;
 if not found then raise exception 'stale lease' using errcode='42501'; end if;
 perform 1 from auth.users where id=p_subject for no key update;
 if not exists(select 1 from public.privacy_deletion_requests where account_id=p_subject and scope='whole_account' and accepted_at is not null) then raise exception 'denied' using errcode='42501'; end if;
 delete from administration.audience_members where account_id=p_subject;
 delete from administration.campaign_callbacks where message_id in(select message_id from administration.campaign_deliveries where account_id=p_subject);
 delete from administration.campaign_deliveries where account_id=p_subject;
 insert into administration.campaign_fences(id,revision,state) select id,revision,'expired' from administration.campaigns where author=p_subject on conflict(id) do nothing;
 delete from administration.audience_members where review_id in(select id from administration.audience_reviews where actor=p_subject or campaign_id in(select id from administration.campaigns where author=p_subject));
 update administration.campaign_deliveries set state=case when state='sending' then 'unknown' else 'skipped' end,terminal_at=coalesce(terminal_at,clock_timestamp()),lease=null,lease_until=null where state in ('pending','running','sending') and campaign_id in(select id from administration.campaigns where author=p_subject);
 delete from administration.audience_reviews where actor=p_subject or campaign_id in(select id from administration.campaigns where author=p_subject);
 delete from administration.campaigns where author=p_subject;
 -- Identifying telemetry is unnecessary after primary erasure; no aggregate is fabricated.
 delete from administration.provider_attempts where subject=p_subject;
 delete from administration.activity where subject=p_subject;
end$$;
revoke all on function public.administration_subject_cleanup(uuid,uuid) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
grant execute on function public.administration_subject_cleanup(uuid,uuid) to privacy_cleanup_executor;
create function public.administration_unsubscribe(p_hash text) returns boolean language plpgsql security definer set search_path=pg_catalog as $$
begin
 if session_user<>'admin_dispatch_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_hash is null or p_hash!~'^[a-f0-9]{64}$' then return false; end if;
 return (select unsubscribed from public.consume_marketing_unsubscribe_token(p_hash));
end$$;
revoke all on function public.administration_unsubscribe(text) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_retention_executor;
grant execute on function public.administration_unsubscribe(text) to admin_dispatch_executor;
commit;
