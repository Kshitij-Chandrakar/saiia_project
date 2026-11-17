begin;
insert into public.privacy_runtime_operations values('7384b3b4cb3085853d1cd64611b903bfa9d5a3e041818f3c1b975e9a197aae81','select coalesce(jsonb_agg(jsonb_build_array(c15_row.f0)), ''[]''::jsonb) from (select to_regprocedure(''public.administration_subject_export(uuid)'') is not null) c15_row(f0)',0,'rows',false,false);
insert into public.privacy_runtime_operations values('dd514bb2e63c2bd6ace564b4eb802292ca473d637e626fa6e70af43aa6574639','select coalesce(jsonb_agg(jsonb_build_array(c15_row.f0)), ''[]''::jsonb) from (select public.administration_subject_export(($1->>0)::uuid)) c15_row(f0)',1,'rows',false,false);
commit;
