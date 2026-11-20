-- Compatibility checkpoint: managed Auth policies are deliberately untouched.
begin;
do $$ begin
 if to_regprocedure('c15_auth.user_fields(uuid)') is null
 or to_regprocedure('c15_auth.lock_user(uuid)') is null
 or to_regprocedure('c15_auth.has_sessions(uuid)') is null then
  raise exception 'private Auth bridge migration required';
 end if;
end $$;
commit;
