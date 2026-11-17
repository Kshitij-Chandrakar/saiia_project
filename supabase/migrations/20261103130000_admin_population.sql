begin;
alter table administration.telemetry_coverage add column population_started_at timestamptz;
create table administration.population(subject uuid primary key,joined_at timestamptz not null,baseline boolean not null,removed_at timestamptz);
alter table administration.population enable row level security;
revoke all on administration.population from public,anon,authenticated,service_role,admin_executor,admin_dispatch_executor,admin_retention_executor,admin_restore_executor,admin_bootstrap_executor;
create function administration.observe_population() returns void language plpgsql security definer set search_path=pg_catalog as $$
declare cutoff timestamptz; begin
 select population_started_at into cutoff from administration.telemetry_coverage where singleton for update;
 if cutoff is null then
  cutoff:=clock_timestamp();update administration.telemetry_coverage set population_started_at=cutoff where singleton;
 end if;
 -- The first observed population is a baseline, not manufactured historical registrations.
 insert into administration.population(subject,joined_at,baseline)
 select u.id,case when u.email_confirmed_at<cutoff or u.email_confirmed_at<clock_timestamp()-interval '90 days' then cutoff else u.email_confirmed_at end,u.email_confirmed_at<cutoff or u.email_confirmed_at<clock_timestamp()-interval '90 days'
 from auth.users u where u.email_confirmed_at is not null and u.deleted_at is null
 and not exists(select 1 from administration.memberships where subject=u.id)
 and not exists(select 1 from public.subscription_deletion_jobs where account_id=u.id)
 and not exists(select 1 from administration.population where subject=u.id) on conflict do nothing;
 update administration.population p set removed_at=clock_timestamp() where removed_at is null and
 (not exists(select 1 from auth.users u where u.id=p.subject and u.deleted_at is null and u.email_confirmed_at is not null)
 or exists(select 1 from administration.memberships where subject=p.subject)
 or exists(select 1 from public.subscription_deletion_jobs where account_id=p.subject));
end$$;
revoke all on function administration.observe_population() from public,anon,authenticated,service_role,admin_executor,admin_dispatch_executor,admin_retention_executor,admin_restore_executor,admin_bootstrap_executor;
do $$ declare definition text; old_sql text; new_sql text; begin
 definition:=pg_get_functiondef('public.administration_metrics(uuid,timestamptz,timestamptz,text)'::regprocedure);
 definition:=replace(definition,' with customers as',' perform administration.observe_population(); with customers as');
 old_sql:=$old$customers as (select id,email_confirmed_at verified_at from auth.users u where email_confirmed_at is not null and not exists(select 1 from administration.memberships where subject=u.id) and not exists(select 1 from public.subscription_deletion_jobs where account_id=u.id))$old$;
 new_sql:=$new$customers as (select subject id,joined_at verified_at from administration.population where removed_at is null)$new$;
 if position(old_sql in definition)=0 then raise exception 'population metric projection mismatch';end if;
 definition:=replace(definition,old_sql,new_sql);
 definition:=replace(definition,$old$'new_users',totals.new_users,'growth_percent',case when totals.starting>0 then 100.0*(totals.ending-totals.starting)/totals.starting end$old$,$new$'new_users',case when p_start>=(select population_started_at from administration.telemetry_coverage) then (select count(*) from administration.population where not baseline and joined_at>=p_start and joined_at<p_end) end,'growth_percent',case when p_start>=(select population_started_at from administration.telemetry_coverage) and (select count(*) from administration.population where joined_at<=p_start and (removed_at is null or removed_at>=p_start))>0 then 100.0*((select count(*) from administration.population where joined_at<p_end and (removed_at is null or removed_at>=p_end))-(select count(*) from administration.population where joined_at<=p_start and (removed_at is null or removed_at>=p_start)))/(select count(*) from administration.population where joined_at<=p_start and (removed_at is null or removed_at>=p_start)) end$new$);
 definition:=replace(definition,$old$'registration_coverage','current_verified_auth_population_only_deleted_history_unavailable'$old$,$new$'registration_coverage','observed_verified_identity_and_removal_events_only_no_prebaseline_history','population_coverage_started_at',(select population_started_at from administration.telemetry_coverage)$new$);
 definition:=replace(definition,$old$totals as(select count(*) filter(where verified_at<p_end) ending,count(*) filter(where verified_at<p_start) starting,count(*) filter(where verified_at>=p_start and verified_at<p_end) new_users from customers)$old$,$new$totals as(select count(*) filter(where joined_at<p_end and (removed_at is null or removed_at>=p_end)) ending,count(*) filter(where joined_at<=p_start and (removed_at is null or removed_at>=p_start)) starting,count(*) filter(where not baseline and joined_at>=p_start and joined_at<p_end) new_users from administration.population)$new$);
 definition:=replace(definition,$old$'total_users',totals.ending$old$,$new$'total_users',case when p_end>=(select population_started_at from administration.telemetry_coverage) then totals.ending end$new$);
 definition:=replace(definition,$old$date_trunc('day',p_start at time zone p_zone),date_trunc('day',(p_end-interval '1 microsecond') at time zone p_zone)$old$,$new$greatest(date_trunc('day',p_start at time zone p_zone),date_trunc('day',(select population_started_at from administration.telemetry_coverage) at time zone p_zone)),date_trunc('day',(p_end-interval '1 microsecond') at time zone p_zone)$new$);
 definition:=replace(definition,$old$(select count(*) from customers where verified_at<p_end and (verified_at at time zone p_zone)<day_bucket+interval '1 day') total_users$old$,$new$(select count(*) from administration.population where joined_at<p_end and (joined_at at time zone p_zone)<day_bucket+interval '1 day' and (removed_at is null or removed_at>=least(p_end,((day_bucket+interval '1 day') at time zone p_zone)))) total_users$new$);
 definition:=replace(definition,$old$(select count(*) from customers where verified_at>=p_start and verified_at<p_end and date_trunc('day',verified_at at time zone p_zone)=day_bucket) new_users$old$,$new$(select count(*) from administration.population where not baseline and joined_at>=p_start and joined_at<p_end and date_trunc('day',joined_at at time zone p_zone)=day_bucket) new_users$new$);
 definition:=replace(definition,'p_start>=(select population_started_at from administration.telemetry_coverage)', 'p_start>=greatest((select population_started_at from administration.telemetry_coverage),clock_timestamp()-interval ''90 days'')');
 definition:=replace(definition,'p_end>=(select population_started_at from administration.telemetry_coverage)', 'p_end>=greatest((select population_started_at from administration.telemetry_coverage),clock_timestamp()-interval ''90 days'')');
 definition:=replace(definition,'''daily_registrations'',coalesce((select jsonb_agg(to_jsonb(days) order by day_bucket) from days),''[]'')', '''daily_registrations'',case when p_start>=greatest((select population_started_at from administration.telemetry_coverage),clock_timestamp()-interval ''90 days'') then coalesce((select jsonb_agg(to_jsonb(days) order by day_bucket) from days),''[]'') else ''[]''::jsonb end');
 execute definition;
end$$;
-- Category clocks remain separate: live identity deduplication lasts only with the
-- active account; a removed subject's minimized event expires within 90 days.
do $$ declare definition text; begin
 definition:=pg_get_functiondef('public.administration_lifecycle(integer)'::regprocedure);
 definition:=replace(definition,' return jsonb_build_object(',$sql$ delete from administration.population where subject in(select subject from administration.population where removed_at<=clock_timestamp()-interval '90 days' order by removed_at limit p_limit for update skip locked); return jsonb_build_object($sql$);
 execute definition;
 definition:=pg_get_functiondef('public.administration_subject_cleanup(uuid,uuid)'::regprocedure);
 definition:=replace(definition,' delete from administration.activity where subject=p_subject;', $sql$ delete from administration.activity where subject=p_subject; update administration.population set removed_at=least(removed_at,(select accepted_at from public.privacy_deletion_requests where account_id=p_subject)) where subject=p_subject;$sql$);
 execute definition;
end$$;
do $$ declare definition text; begin
 definition:=pg_get_functiondef('public.administration_subject_export(uuid)'::regprocedure);
 definition:=replace(definition,$old$'version','c15.admin.personal.v1',$old$,$new$'version','c15.admin.personal.v1','registration_observation',(select jsonb_build_object('joined_at',joined_at,'baseline',baseline,'removed_at',removed_at) from administration.population where subject=subject_id),$new$);
 execute definition;
end$$;
commit;
