create or replace function public.set_interview_session_ask_ai_request_key_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at := timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists interview_session_ask_ai_request_key_updated_at
  on public.interview_session_ask_ai_request_keys;

create trigger interview_session_ask_ai_request_key_updated_at
  before update on public.interview_session_ask_ai_request_keys
  for each row
  execute function public.set_interview_session_ask_ai_request_key_updated_at();
