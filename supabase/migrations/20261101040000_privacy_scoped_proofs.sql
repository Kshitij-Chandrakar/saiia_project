-- Default-closed scope binding for existing operation proofs; no activation.
begin;
alter table public.privacy_export_proofs add column operation_scope text not null default 'export' check(operation_scope in ('export','session','history'));
alter table public.privacy_export_proofs add column resource_id uuid;
alter table public.privacy_export_proofs add constraint privacy_proof_resource_scope check((operation_scope='session')=(resource_id is not null));
commit;
