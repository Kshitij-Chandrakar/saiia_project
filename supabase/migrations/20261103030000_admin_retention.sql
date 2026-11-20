-- Fixed finite retention for admin authority records only; no legacy ledger retirement.
begin;
create role admin_retention_executor nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
create table administration.retention_holds (
 kind text not null check(kind in ('audit','receipt')), record_id uuid not null,
 reason text not null check(reason in ('security','legal','operational')), active boolean not null,
 review_at timestamptz not null, primary key(kind,record_id), check(isfinite(review_at))
);
create table administration.retention_runs (
 id uuid primary key default gen_random_uuid(), completed_at timestamptz not null default clock_timestamp(),
 audit_count integer not null, review_count integer not null, receipt_count integer not null, coupon_count integer not null
);
alter table administration.retention_holds enable row level security;
alter table administration.retention_runs enable row level security;
revoke all on administration.retention_holds,administration.retention_runs from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_retention_executor;
-- During its lifetime an audit envelope is immutable. Only the fixed maintenance
-- principal can remove an expired unheld envelope; callers receive no table grants.
create or replace function administration.immutable() returns trigger language plpgsql set search_path=pg_catalog as $$
begin
 if tg_op='DELETE' and session_user='admin_retention_executor' and current_setting('role',true)='none'
 and old.expires_at<=clock_timestamp() and not exists(select 1 from administration.retention_holds where kind='audit' and record_id=old.id and active) then return old; end if;
 raise exception 'immutable' using errcode='55000';
end$$;
create function public.administration_retention(p_limit integer default 100) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare item record; audits integer:=0; reviews integer:=0; receipts integer:=0; coupons integer:=0; n integer; begin
 if session_user<>'admin_retention_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 if p_limit is null or p_limit<1 or p_limit>100 then raise exception 'invalid bound' using errcode='22023'; end if;
 perform 1 from administration.configuration where singleton and enabled for update;
 if not found then raise exception 'unavailable' using errcode='P0005'; end if;
 -- Same authority lock serializes with review/confirm and prevents action reactivation.
 for item in select id from administration.audit where expires_at<=clock_timestamp()
 and not exists(select 1 from administration.retention_holds where kind='audit' and record_id=administration.audit.id and active)
 order by expires_at,id limit p_limit for update skip locked loop
  delete from administration.audit_references where event=item.id;
  delete from administration.audit where id=item.id; audits:=audits+1;
 end loop;
 delete from administration.reviews where id in(select id from administration.reviews where consumed_at is not null or expires_at<=clock_timestamp() order by expires_at limit p_limit for update skip locked);
 get diagnostics reviews=row_count;
 delete from administration.access_reviews where id in(select id from administration.access_reviews where consumed_at is not null or expires_at<=clock_timestamp() order by expires_at limit p_limit for update skip locked);
 get diagnostics n=row_count; reviews:=reviews+n;
 delete from administration.privacy_reviews where id in(select id from administration.privacy_reviews where consumed_at is not null or expires_at<=clock_timestamp() order by expires_at limit p_limit for update skip locked);
 get diagnostics n=row_count; reviews:=reviews+n;
 delete from administration.receipts where id in(select id from administration.receipts where created_at<=clock_timestamp()-interval '180 days'
 and not exists(select 1 from administration.retention_holds where kind='receipt' and record_id=administration.receipts.id and active)
 order by created_at limit p_limit for update skip locked);
 get diagnostics receipts=row_count;
 delete from administration.coupon_requests where id in(select id from administration.coupon_requests where recorded_at<=clock_timestamp()-interval '180 days' order by recorded_at limit p_limit for update skip locked);
 get diagnostics coupons=row_count;
 delete from administration.retention_runs where completed_at<=clock_timestamp()-interval '180 days';
 if audits+reviews+receipts+coupons>0 then
  insert into administration.retention_runs(audit_count,review_count,receipt_count,coupon_count) values(audits,reviews,receipts,coupons);
 end if;
 return jsonb_build_object('audit',audits,'reviews',reviews,'receipts',receipts,'coupons',coupons,'hold_reviews_due',(select count(*) from administration.retention_holds where active and review_at<=clock_timestamp()));
end$$;
revoke all on function public.administration_retention(integer) from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor;
grant execute on function public.administration_retention(integer) to admin_retention_executor;
do $$ declare signature text; definition text; marker text; recovery text; begin
 foreach signature in array array['public.administration_call(uuid,uuid,timestamptz,text,jsonb)','public.administration_access(uuid,uuid,timestamptz,text,jsonb)','public.administration_privacy_retry(uuid,uuid,timestamptz,text,jsonb)'] loop
  definition:=pg_get_functiondef(signature::regprocedure);
  if signature like 'public.administration_call%' then
   marker:=' select * into v from administration.reviews where id=';
   recovery:=' select * into receipt from administration.receipts where review_id=(p_doc->>''review_id'')::uuid and actor=p_actor and action=''membership'';
 if found then return jsonb_build_object(''operation_id'',receipt.id,''state'',receipt.state,''revision'',receipt.revision::text); end if;
';
  elsif signature like 'public.administration_access%' then
   marker:=' select * into v from administration.access_reviews where id=';
   recovery:=' select * into result from administration.receipts where review_id=(p_doc->>''review_id'')::uuid and actor=p_actor and action in (''access.restrict'',''access.restore'');
 if found then return jsonb_build_object(''operation_id'',result.id,''state'',result.state,''revision'',result.revision::text,''restricted'',result.action=''access.restrict'',''billing_changed'',false); end if;
';
  else
   marker:=' select * into v from administration.privacy_reviews where id=';
   recovery:=' select * into receipt from administration.receipts where review_id=(p_doc->>''review_id'')::uuid and actor=p_actor and action=''privacy.retry'';
 if found then return jsonb_build_object(''operation_id'',receipt.id,''state'',receipt.state,''revision'',receipt.revision::text); end if;
';
  end if;
  if position(marker in definition)=0 then raise exception 'confirmation recovery mismatch'; end if;
  execute replace(definition,marker,recovery||marker);
 end loop;
end$$;
commit;
