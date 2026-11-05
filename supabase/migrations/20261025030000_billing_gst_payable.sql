-- Additive C12 payable contracts. Existing offers, mandates, amounts and consent
-- remain untouched. No configuration, LOGIN, publication or activation.
begin;
create table public.billing_payable_quotes (
 operation_id uuid primary key references public.billing_operations on delete restrict,
 document jsonb not null,
 quote_id text not null unique,
 created_at timestamptz not null default clock_timestamp()
);
alter table public.billing_payable_quotes enable row level security;
revoke all on public.billing_payable_quotes from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;
create function public.billing_quote_immutable() returns trigger language plpgsql as $$
begin raise exception 'immutable payable quote' using errcode='55000'; end $$;
create trigger billing_quote_immutable before update or delete on public.billing_payable_quotes
 for each row execute function public.billing_quote_immutable();
revoke all on function public.billing_quote_immutable() from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;

alter function public.billing_call(uuid,text,uuid,jsonb) rename to billing_call_v1;
-- Narrow, asserted change to the inherited prepare gate. Do not duplicate the
-- existing lifecycle transaction body or rewrite any historical row.
do $patch$ declare body text; old_gate text:=$gate$p.document->>'tax_policy_ref' is distinct from p_doc->>'total_policy_ref' or coalesce(p_doc->>'total_policy_ref','')=''$gate$;
begin
 body:=pg_get_functiondef('public.billing_call_v1(uuid,text,uuid,jsonb)'::regprocedure);
 if strpos(body,old_gate)=0 then raise exception 'unexpected billing prepare definition'; end if;
 execute replace(body,old_gate,$gate$p_doc->>'total_policy_ref' is distinct from 'billing.inr.gst18.v1'$gate$);
end $patch$;
revoke all on function public.billing_call_v1(uuid,text,uuid,jsonb) from public,anon,authenticated,service_role,usage_executor,usage_binding_executor;
create function public.billing_call(p_account uuid,p_action text,p_id uuid,p_doc jsonb) returns jsonb
language plpgsql security definer set search_path=pg_catalog as $$
declare o public.billing_operations; q public.billing_payable_quotes; p public.catalog_price_versions;
 s public.catalog_offer_versions; doc jsonb; billing_result jsonb; tax bigint;
begin
 if session_user<>'usage_binding_executor' or current_setting('role',true)<>'none' then raise exception 'denied' using errcode='42501'; end if;
 perform 1 from public.account_plan_bindings where account_id=p_account for update;
 select * into o from public.billing_operations where operation_id=p_id for update;
 if found and o.account_id<>p_account then raise exception 'denied' using errcode='42501'; end if;
 if p_action='prepare' then
  if p_doc->>'total_policy_ref' is distinct from 'billing.inr.gst18.v1' then raise exception 'payable policy required' using errcode='22023'; end if;
  -- An unconsented legacy review can be superseded, never repriced. Dispatched
  -- or uncertain legacy operations must reconcile their original mandate.
  update public.billing_operations b set state='expired' where b.account_id=p_account and b.state='prepared'
    and b.consent_at is null and not exists(select 1 from public.billing_payable_quotes x where x.operation_id=b.operation_id);
  if o.operation_id is not null and not exists(select 1 from public.billing_payable_quotes x where x.operation_id=p_id) then
   raise exception 'new operation and review required' using errcode='P0003'; end if;
  select * into p from public.catalog_price_versions where price_id=(p_doc->>'price_id')::uuid and offer_version_id=(p_doc->>'offer_version_id')::uuid;
  if not found or p.currency<>'INR' or p.exponent<>2 or p.amount_minor<=0 or mod(p.amount_minor::numeric*1800,10000)<>0 then raise exception 'exact payable required' using errcode='22023'; end if;
  select * into s from public.catalog_offer_versions where offer_version_id=p.offer_version_id;
  -- Reuse the original visibility/ownership/discount/paid-change/dispatch
  -- mechanism. Its old policy gate validates immutable catalog references;
  -- GST is a separate approved payable policy, not a mutation of those terms.
  billing_result:=public.billing_call_v1(p_account,p_action,p_id,p_doc);
  select * into o from public.billing_operations where operation_id=(billing_result->>'operation_id')::uuid for update;
  select * into q from public.billing_payable_quotes where operation_id=o.operation_id;
  if not found then
   if o.state<>'prepared' or o.consent_at is not null then raise exception 'existing mandate cannot be repriced' using errcode='P0003'; end if;
   tax:=(p.amount_minor::numeric*1800/10000)::bigint;
   doc:=jsonb_build_object('contract_version','billing.inr.gst18.v1','currency','INR','exponent','2',
    'base_amount_minor',p.amount_minor::text,'tax_rate_basis_points','1800','tax_amount_minor',tax::text,
    'total_amount_minor',(p.amount_minor+tax)::text,'offer_version_id',s.offer_version_id::text,'offer_version',s.version::text,
    'offer_fingerprint',s.fingerprint,'price_id',p.price_id::text,'provider_tax_mode','total_in_plan_no_additional_tax');
   insert into public.billing_payable_quotes(operation_id,document,quote_id) values(o.operation_id,doc,
    encode(sha256(convert_to((doc||jsonb_build_object('operation_id',o.operation_id,'provider_plan',o.provider_plan,'total_count',o.total_count))::text,'UTF8')),'hex')) returning * into q;
   update public.billing_operations set amount=p.amount_minor+tax where operation_id=o.operation_id returning * into o;
  end if;
 else
  select * into q from public.billing_payable_quotes where operation_id=p_id;
  if p_action='claim' then
   if q.operation_id is null and o.provider_id is null then raise exception 'updated quote review required' using errcode='P0003'; end if;
   if q.operation_id is not null and p_doc->>'quote_id' is distinct from q.quote_id then raise exception 'quote consent mismatch' using errcode='P0003'; end if;
  end if;
  billing_result:=public.billing_call_v1(p_account,p_action,p_id,p_doc);
  select * into o from public.billing_operations where operation_id=p_id;
 end if;
 return coalesce(billing_result,'{}'::jsonb)||to_jsonb(o)||jsonb_build_object('payable',q.document,'quote_id',q.quote_id);
end $$;
revoke all on function public.billing_call(uuid,text,uuid,jsonb) from public,anon,authenticated,service_role,usage_executor;
grant execute on function public.billing_call(uuid,text,uuid,jsonb) to usage_binding_executor;
commit;
