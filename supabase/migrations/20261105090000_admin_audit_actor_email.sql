-- Current email is a read-time label, never a rewrite of the recorded actor identity.
begin;
do $$ declare definition text; old_projection text; begin
 definition:=pg_get_functiondef('public.administration_call(uuid,uuid,timestamptz,text,jsonb)'::regprocedure);
 old_projection:=$old$'actor_ref',r.actor,'target_ref',r.target$old$;
 if position(old_projection in definition)=0 then raise exception 'audit actor projection mismatch'; end if;
 execute replace(definition,old_projection,$new$'actor_ref',r.actor,'actor_email',(select email from auth.users where id=r.actor),'target_ref',r.target$new$);
end$$;
commit;
