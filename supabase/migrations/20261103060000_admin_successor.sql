begin;
create table administration.successor_transfers (
 id uuid primary key default gen_random_uuid(),actor uuid not null,actor_revision bigint not null,
 target uuid not null,target_revision bigint not null,session_id uuid not null,
 state text not null default 'offered' check(state in ('offered','accepted','verified')),
 expires_at timestamptz not null default clock_timestamp()+interval '5 minutes',
 accepted_at timestamptz,verified_at timestamptz,check(actor<>target)
);
alter table administration.successor_transfers enable row level security;
revoke all on administration.successor_transfers from public,anon,authenticated,service_role,admin_executor,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
create function public.administration_successor(p_subject uuid,p_session uuid,p_presence timestamptz,p_action text,p_doc jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare actor administration.memberships; target administration.memberships; transfer administration.successor_transfers; begin
 if session_user<>'admin_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform 1 from administration.configuration where singleton and enabled for update; if not found then return jsonb_build_object('error','unavailable'); end if;
 if p_action='status' then
  select * into transfer from administration.successor_transfers t where t.id=(p_doc->>'transfer_id')::uuid and p_subject in (t.actor,t.target);
  if not found then return jsonb_build_object('error','not_found'); end if;
  return jsonb_build_object('transfer_id',transfer.id,'state',transfer.state,'expires_at',transfer.expires_at,'successor_access_verified',transfer.state='verified','self_deletion_blocked',false);
 end if;
 if p_session is null or p_presence is null or p_presence>clock_timestamp() or p_presence<clock_timestamp()-interval '5 minutes' or not administration.authenticator_ready(p_subject) then return jsonb_build_object('error','reauthentication_required'); end if;
 if p_action='offer' then
  actor:=administration.member(p_subject);
  if actor.subject is null or actor.role<>'super_admin' then return jsonb_build_object('error','not_found'); end if;
  if p_doc->>'confirm' is distinct from 'true' or p_doc-array['target','confirm']<>'{}'::jsonb then return jsonb_build_object('error','invalid'); end if;
  perform 1 from auth.users where id=(p_doc->>'target')::uuid for no key update;
  if not found or p_subject=(p_doc->>'target')::uuid or not administration.eligible((p_doc->>'target')::uuid) then return jsonb_build_object('error','invalid'); end if;
  select * into target from administration.memberships where subject=(p_doc->>'target')::uuid;
  insert into administration.successor_transfers(actor,actor_revision,target,target_revision,session_id) values(p_subject,actor.revision,(p_doc->>'target')::uuid,coalesce(target.revision,0),p_session) returning * into transfer;
  perform administration.audit_action(p_subject,actor.role,transfer.target,'successor.offer','confirmed','membership',transfer.id);
  return jsonb_build_object('transfer_id',transfer.id,'state',transfer.state,'expires_at',transfer.expires_at,'self_deletion_blocked',false);
 elsif p_action='accept' then
  if p_doc->>'confirm' is distinct from 'true' or p_doc-array['transfer_id','confirm']<>'{}'::jsonb then return jsonb_build_object('error','invalid'); end if;
  select * into transfer from administration.successor_transfers t where t.id=(p_doc->>'transfer_id')::uuid and t.target=p_subject for update;
  if not found then return jsonb_build_object('error','not_found'); end if;
  if transfer.state in ('accepted','verified') then return jsonb_build_object('state',transfer.state,'transfer_id',transfer.id); end if;
  actor:=administration.member(transfer.actor);
  if actor.subject is null or actor.role<>'super_admin' or actor.revision<>transfer.actor_revision or transfer.expires_at<=clock_timestamp() or not administration.eligible(p_subject) then return jsonb_build_object('error','conflict'); end if;
  select * into target from administration.memberships where subject=p_subject for update;
  if coalesce(target.revision,0)<>transfer.target_revision then return jsonb_build_object('error','conflict'); end if;
  insert into administration.memberships(subject,role,status,revision) values(p_subject,'super_admin','active',1) on conflict(subject) do update set role='super_admin',status='active',revision=administration.memberships.revision+1,updated_at=clock_timestamp();
  update administration.successor_transfers set state='accepted',accepted_at=clock_timestamp(),target_revision=(select revision from administration.memberships where subject=p_subject) where id=transfer.id;
  perform administration.audit_action(p_subject,'super_admin',transfer.actor,'successor.accept','confirmed','membership',transfer.id);
  return jsonb_build_object('state','accepted','transfer_id',transfer.id,'access_verification_required',true);
 end if;
 return jsonb_build_object('error','invalid');
end$$;
revoke all on function public.administration_successor(uuid,uuid,timestamptz,text,jsonb) from public,anon,authenticated,service_role,admin_bootstrap_executor,admin_dispatch_executor,admin_retention_executor;
grant execute on function public.administration_successor(uuid,uuid,timestamptz,text,jsonb) to admin_executor;
do $$ declare definition text; marker text; begin
 definition:=pg_get_functiondef('public.administration_call(uuid,uuid,timestamptz,text,jsonb)'::regprocedure);
 marker:='if p_action=''me'' then return';
 if position(marker in definition)=0 then raise exception 'admission verification mismatch'; end if;
 execute replace(definition,marker,'if p_action=''me'' then update administration.successor_transfers verified_successor_record set state=''verified'',verified_at=clock_timestamp() where verified_successor_record.target=p_actor and verified_successor_record.state=''accepted'' and m.role=''super_admin'' and m.revision=verified_successor_record.target_revision; return');
end$$;
commit;
