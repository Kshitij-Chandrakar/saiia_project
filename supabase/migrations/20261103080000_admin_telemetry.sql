begin;
create table administration.telemetry_coverage(singleton boolean primary key default true check(singleton),started_at timestamptz not null default clock_timestamp());
insert into administration.telemetry_coverage values(true,clock_timestamp());
create table administration.provider_attempts(
 id uuid primary key,request_id uuid not null,subject uuid not null,provider text not null check(provider in ('openai','groq','gemini','ollama','assemblyai','affinda','openrouter')),
 model text not null check(length(model) between 1 and 120 and model~'^[A-Za-z0-9._:/-]+$'),reported_model text check(length(reported_model)<=120 and reported_model~'^[A-Za-z0-9._:/-]+$'),
 outcome text not null check(outcome in ('completed','failed','aborted')),input_tokens bigint check(input_tokens between 0 and 1000000000000),output_tokens bigint check(output_tokens between 0 and 1000000000000),duration_ms bigint not null check(duration_ms between 0 and 86400000),completed_at timestamptz not null default clock_timestamp());
create index provider_attempts_completed on administration.provider_attempts(completed_at,subject);
create table administration.activity(subject uuid not null,event_id uuid not null,kind text not null check(kind in ('session_started','usage_settled')),completed_at timestamptz not null default clock_timestamp(),primary key(subject,kind,event_id));
create index activity_completed on administration.activity(completed_at,subject);
create table administration.model_rates(provider text not null,model text not null,version text not null,currency text not null check(currency~'^[A-Z]{3}$'),input_per_million numeric not null check(input_per_million>=0),output_per_million numeric not null check(output_per_million>=0),valid_from timestamptz not null,valid_until timestamptz not null,check(valid_until>valid_from),primary key(provider,model,version));
-- Fixed successful commit boundaries, not login/polling or failed attempts.
create function administration.product_activity() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
declare owner_id uuid; begin
 if TG_TABLE_NAME='interview_sessions' then owner_id:=new.user_id;else owner_id:=new.account_id;end if;
 if exists(select 1 from public.subscription_deletion_jobs where account_id=owner_id) or exists(select 1 from public.privacy_restored_subjects where account_id=owner_id) or administration.restricted(owner_id) or exists(select 1 from administration.memberships where subject=owner_id) then return new;end if;
 if TG_TABLE_NAME='interview_sessions' then
  insert into administration.activity(subject,event_id,kind) values(new.user_id,new.id,'session_started') on conflict do nothing;
 elsif new.state='settled' and old.state is distinct from 'settled' then
  insert into administration.activity(subject,event_id,kind) values(new.account_id,new.operation_id,'usage_settled') on conflict do nothing;
 end if;
 return new;
end$$;
create trigger administration_activity after insert on public.interview_sessions for each row execute function administration.product_activity();
create trigger administration_activity after update on public.usage_operations for each row execute function administration.product_activity();
revoke all on function administration.product_activity() from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
create function public.administration_attempt(p_doc jsonb) returns void language plpgsql security definer set search_path=pg_catalog as $$
declare subject_id uuid:=(p_doc->>'account_id')::uuid; begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_doc-array['attempt_id','request_id','account_id','provider','model','reported_model','outcome','input_tokens','output_tokens','duration_ms']<>'{}'::jsonb then raise exception 'invalid' using errcode='22023'; end if;
 perform 1 from auth.users where id=subject_id for no key update;
 if not found or not public.administration_product_access(subject_id) or exists(select 1 from administration.memberships where subject=subject_id) then return; end if;
 insert into administration.provider_attempts(id,request_id,subject,provider,model,reported_model,outcome,input_tokens,output_tokens,duration_ms)
 values((p_doc->>'attempt_id')::uuid,(p_doc->>'request_id')::uuid,subject_id,p_doc->>'provider',p_doc->>'model',p_doc->>'reported_model',p_doc->>'outcome',(p_doc->>'input_tokens')::bigint,(p_doc->>'output_tokens')::bigint,(p_doc->>'duration_ms')::bigint) on conflict do nothing;
end$$;
revoke all on function public.administration_attempt(jsonb) from public,anon,authenticated,service_role,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
grant execute on function public.administration_attempt(jsonb) to admin_executor;
create function public.administration_metrics(p_actor uuid,p_start timestamptz,p_end timestamptz,p_zone text) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare admission jsonb; result jsonb; begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 admission:=public.administration_call(p_actor,null,null,'me','{}');if admission?'error' then return admission; end if;
 -- IANA backward alias is absent from some packaged tzdata sets.
 if p_zone='Asia/Calcutta' then p_zone:='Asia/Kolkata'; end if;
 if p_start is null or p_end is null or p_end<=p_start or p_end-p_start>interval '90 days' or p_end>clock_timestamp()+interval '1 minute' or not exists(select 1 from pg_timezone_names where name=p_zone) then return jsonb_build_object('error','invalid');end if;
 with customers as (select id,email_confirmed_at verified_at from auth.users u where email_confirmed_at is not null and not exists(select 1 from administration.memberships where subject=u.id) and not exists(select 1 from public.subscription_deletion_jobs where account_id=u.id)),
 totals as(select count(*) filter(where verified_at<p_end) ending,count(*) filter(where verified_at<p_start) starting,count(*) filter(where verified_at>=p_start and verified_at<p_end) new_users from customers),
 active as(select count(distinct a.subject) filter(where a.completed_at>=p_end-interval '7 days') seven,count(distinct a.subject) filter(where a.completed_at>=p_end-interval '30 days') thirty,count(distinct a.subject) filter(where a.completed_at>=p_end-interval '5 minutes') current from administration.activity a join customers c on c.id=a.subject where a.completed_at<p_end),
 models as(select a.provider,a.model,count(*) attempts,count(*) filter(where outcome='completed') completed,count(*) filter(where outcome='failed') failed,count(*) filter(where outcome='aborted') aborted,count(*) filter(where input_tokens is not null and output_tokens is not null) token_covered from administration.provider_attempts a join customers c on c.id=a.subject where a.completed_at>=p_start and a.completed_at<p_end group by a.provider,a.model),
 days as(select day_bucket,(select count(*) from customers where verified_at>=p_start and verified_at<p_end and date_trunc('day',verified_at at time zone p_zone)=day_bucket) new_users,(select count(*) from customers where verified_at<p_end and (verified_at at time zone p_zone)<day_bucket+interval '1 day') total_users from generate_series(date_trunc('day',p_start at time zone p_zone),date_trunc('day',(p_end-interval '1 microsecond') at time zone p_zone),interval '1 day') series(day_bucket)),
 costs as(select a.id,r.currency,case when a.input_tokens is not null and a.output_tokens is not null and r.version is not null then (a.input_tokens*r.input_per_million+a.output_tokens*r.output_per_million)/1000000 end estimated from administration.provider_attempts a join customers c on c.id=a.subject left join lateral(select * from administration.model_rates r where r.provider=a.provider and r.model=a.model and a.completed_at>=r.valid_from and a.completed_at<r.valid_until order by valid_from desc limit 1) r on true where a.completed_at>=p_start and a.completed_at<p_end)
 select jsonb_build_object('start',p_start,'end',p_end,'timezone',p_zone,'as_of',statement_timestamp(),'coverage_started_at',(select started_at from administration.telemetry_coverage),
 'total_users',totals.ending,'new_users',totals.new_users,'growth_percent',case when totals.starting>0 then 100.0*(totals.ending-totals.starting)/totals.starting end,
 'active_7_days',active.seven,'active_30_days',active.thirty,'current_activity_5_minutes',active.current,
 'models',coalesce((select jsonb_agg(to_jsonb(models) order by attempts desc,model) from models),'[]'),
 'daily_registrations',coalesce((select jsonb_agg(to_jsonb(days) order by day_bucket) from days),'[]'),
 'costs',coalesce((select jsonb_agg(jsonb_build_object('currency',currency,'estimated_amount',amount,'covered_attempts',covered)) from(select currency,sum(estimated) amount,count(*) covered from costs where estimated is not null group by currency) x),'[]'),
 'cost_unknown_attempts',(select count(*) from costs where estimated is null),'provider_confirmed_charges',null,
 'registration_coverage','current_verified_auth_population_only_deleted_history_unavailable','activity_coverage','successful_session_start_and_usage_settlement_since_instrumentation','attempt_coverage','instrumented_adapters_only') into result from totals cross join active;
 return result;
end$$;
revoke all on function public.administration_metrics(uuid,timestamptz,timestamptz,text) from public,anon,authenticated,service_role,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
grant execute on function public.administration_metrics(uuid,timestamptz,timestamptz,text) to admin_executor;
alter table administration.provider_attempts enable row level security;
alter table administration.activity enable row level security;
alter table administration.model_rates enable row level security;
alter table administration.telemetry_coverage enable row level security;
revoke all on administration.provider_attempts,administration.activity,administration.model_rates,administration.telemetry_coverage from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
do $$ declare definition text; old_projection text; begin
 definition:=pg_get_functiondef('administration.customer_metadata(uuid)'::regprocedure);
 old_projection:=$old$'last_product_activity_at',null,'activity_coverage','not_instrumented'$old$;
 if position(old_projection in definition)=0 then raise exception 'activity metadata projection mismatch';end if;
 execute replace(definition,old_projection,$new$'last_product_activity_at',(select max(completed_at) from administration.activity where subject=p_subject),'activity_coverage','successful_commits_since_instrumentation'$new$);
end$$;
commit;
