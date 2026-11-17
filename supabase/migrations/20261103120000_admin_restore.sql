begin;
create role admin_restore_executor nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
create table administration.restore_revision(singleton boolean primary key default true check(singleton),revision bigint not null default 0);
insert into administration.restore_revision values(true,0);
revoke all on administration.restore_revision from public,anon,authenticated,service_role,admin_executor,admin_dispatch_executor,admin_retention_executor,admin_restore_executor,admin_bootstrap_executor;
alter table administration.restore_revision enable row level security;
create function administration.restore_changed() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
begin update administration.restore_revision set revision=revision+1 where singleton;return null;end$$;
revoke all on function administration.restore_changed() from public,anon,authenticated,service_role,admin_executor,admin_dispatch_executor,admin_retention_executor,admin_restore_executor,admin_bootstrap_executor;
create trigger restore_changed after insert or update or delete on administration.memberships for each statement execute function administration.restore_changed();
create trigger restore_changed after insert or update or delete on administration.customer_access for each statement execute function administration.restore_changed();
create trigger restore_changed after insert or update or delete on administration.campaign_fences for each statement execute function administration.restore_changed();
create function public.administration_restore(p_action text,p_doc jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare result jsonb; item jsonb; begin
 if session_user<>'admin_restore_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_action='lock' then perform pg_advisory_lock(hashtextextended('administration.restore.coordinator.v1',0));return '{}'::jsonb;end if;
 if p_action='unlock' then perform pg_advisory_unlock(hashtextextended('administration.restore.coordinator.v1',0));return '{}'::jsonb;end if;
 perform 1 from administration.configuration where singleton for update;
 if p_action='capture' then
  return jsonb_build_object('version',1,'revision',(select revision::text from administration.restore_revision where singleton),
   'memberships',(select coalesce(jsonb_agg(jsonb_build_object('subject',subject,'role',role,'status',status,'revision',revision::text) order by subject),'[]') from administration.memberships),
   'restrictions',(select coalesce(jsonb_agg(jsonb_build_object('subject',subject,'restricted',restricted,'revision',revision::text,'changed_at',changed_at) order by subject),'[]') from administration.customer_access),
   'spent_campaigns',(select coalesce(jsonb_agg(jsonb_build_object('id',id,'revision',revision::text,'state',state) order by id),'[]') from administration.campaign_fences));
 elsif p_action='replay' then
  if p_doc is null or jsonb_typeof(p_doc)<>'object' or not p_doc ?& array['version','revision','memberships','restrictions','spent_campaigns'] or jsonb_typeof(p_doc->'memberships')<>'array' or jsonb_typeof(p_doc->'restrictions')<>'array' or jsonb_typeof(p_doc->'spent_campaigns')<>'array' or coalesce(p_doc->>'revision','')!~'^[0-9]{1,18}$' or p_doc-array['version','revision','memberships','restrictions','spent_campaigns']<>'{}'::jsonb or p_doc->>'version'<>'1' or jsonb_array_length(p_doc->'memberships')>10000 or jsonb_array_length(p_doc->'restrictions')>100000 or jsonb_array_length(p_doc->'spent_campaigns')>100000 then raise exception 'invalid witness' using errcode='22023';end if;
  for item in select value from jsonb_array_elements(p_doc->'memberships') loop
   if jsonb_typeof(item)<>'object' or not item ?& array['subject','role','status','revision'] or item-array['subject','role','status','revision']<>'{}'::jsonb or coalesce(item->>'role','') not in ('admin','super_admin') or coalesce(item->>'status','') not in ('active','suspended','revoked') or coalesce(item->>'revision','')!~'^[1-9][0-9]{0,17}$' then raise exception 'invalid witness member' using errcode='22023';end if;
   perform (item->>'subject')::uuid;
  end loop;
  for item in select value from jsonb_array_elements(p_doc->'restrictions') loop
   if jsonb_typeof(item)<>'object' or not item ?& array['subject','restricted','revision','changed_at'] or item-array['subject','restricted','revision','changed_at']<>'{}'::jsonb or jsonb_typeof(item->'restricted')<>'boolean' or coalesce(item->>'revision','')!~'^[1-9][0-9]{0,17}$' then raise exception 'invalid witness restriction' using errcode='22023';end if;
   perform (item->>'subject')::uuid,(item->>'changed_at')::timestamptz;
  end loop;
  for item in select value from jsonb_array_elements(p_doc->'spent_campaigns') loop
   if jsonb_typeof(item)<>'object' or not item ?& array['id','revision','state'] or item-array['id','revision','state']<>'{}'::jsonb or coalesce(item->>'state','') not in ('sent','expired','restored_blocked') or coalesce(item->>'revision','')!~'^[1-9][0-9]{0,17}$' then raise exception 'invalid witness campaign' using errcode='22023';end if;
   perform (item->>'id')::uuid;
  end loop;
  -- Witness replay is closed, operator-only and never clears any C15 restriction.
  update administration.memberships set status='revoked',revision=revision+1 where not exists(select 1 from jsonb_array_elements(p_doc->'memberships') x where (x->>'subject')::uuid=subject);
  for item in select * from jsonb_array_elements(p_doc->'memberships') loop
   insert into administration.memberships(subject,role,status,revision) values((item->>'subject')::uuid,item->>'role',item->>'status',(item->>'revision')::bigint)
   on conflict(subject) do update set role=excluded.role,status=excluded.status,revision=excluded.revision;
  end loop;
  for item in select * from jsonb_array_elements(p_doc->'restrictions') loop
   insert into administration.customer_access(subject,restricted,revision,changed_at) values((item->>'subject')::uuid,(item->>'restricted')::boolean,(item->>'revision')::bigint,(item->>'changed_at')::timestamptz)
   on conflict(subject) do update set restricted=administration.customer_access.restricted or excluded.restricted,revision=greatest(administration.customer_access.revision,excluded.revision),changed_at=greatest(administration.customer_access.changed_at,excluded.changed_at);
  end loop;
  for item in select * from jsonb_array_elements(p_doc->'spent_campaigns') loop
   insert into administration.campaign_fences values((item->>'id')::uuid,(item->>'revision')::bigint,'restored_blocked') on conflict(id) do update set state='restored_blocked',revision=greatest(administration.campaign_fences.revision,excluded.revision);
  end loop;
  update administration.campaign_deliveries set state=case when state in ('sending','accepted','unknown') then 'unknown' else 'skipped' end,lease=null,lease_until=null,terminal_at=coalesce(terminal_at,clock_timestamp()) where state in ('pending','running','sending','accepted','unknown');
  update administration.campaigns set state='blocked' where state in ('draft','queued');
  update administration.successor_transfers set expires_at=clock_timestamp(),session_id=null where state='offered';
  delete from administration.reviews;delete from administration.access_reviews;delete from administration.privacy_reviews;delete from administration.command_reviews;delete from administration.audience_members;delete from administration.audience_reviews;
  update administration.commands set state=case when dispatched then 'unknown' else 'blocked' end,lease=null,lease_until=null where state in ('pending','running','unknown');
  update administration.restore_revision set revision=greatest(revision,(p_doc->>'revision')::bigint)+1 where singleton;
  return jsonb_build_object('replayed',true);
 end if;
 raise exception 'invalid operation' using errcode='22023';
end$$;
revoke all on function public.administration_restore(text,jsonb) from public,anon,authenticated,service_role,admin_executor,admin_dispatch_executor,admin_retention_executor,admin_bootstrap_executor;
grant execute on function public.administration_restore(text,jsonb) to admin_restore_executor;
commit;
