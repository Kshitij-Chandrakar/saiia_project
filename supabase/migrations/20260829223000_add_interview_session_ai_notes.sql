-- C8 AI notes generation from stored transcript entries.
-- Stores one backend-generated notes row per interview session.

create table if not exists public.interview_session_ai_notes (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id uuid not null references public.interview_sessions(id) on delete cascade,
  status text not null default 'ready',
  notes_markdown text not null,
  summary text null,
  strengths jsonb not null default '[]'::jsonb,
  improvement_areas jsonb not null default '[]'::jsonb,
  technical_topics jsonb not null default '[]'::jsonb,
  key_questions jsonb not null default '[]'::jsonb,
  suggested_followups jsonb not null default '[]'::jsonb,
  provider text null,
  model text null,
  generation_ms integer null,
  transcript_entry_count integer not null default 0,
  generated_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint interview_session_ai_notes_status_check check (status in ('ready', 'failed')),
  constraint interview_session_ai_notes_markdown_length check (char_length(notes_markdown) between 1 and 24000),
  constraint interview_session_ai_notes_summary_length check (summary is null or char_length(summary) <= 1200),
  constraint interview_session_ai_notes_strengths_array check (jsonb_typeof(strengths) = 'array'),
  constraint interview_session_ai_notes_strengths_size check (octet_length(strengths::text) <= 4000),
  constraint interview_session_ai_notes_improvement_areas_array check (jsonb_typeof(improvement_areas) = 'array'),
  constraint interview_session_ai_notes_improvement_areas_size check (octet_length(improvement_areas::text) <= 4000),
  constraint interview_session_ai_notes_technical_topics_array check (jsonb_typeof(technical_topics) = 'array'),
  constraint interview_session_ai_notes_technical_topics_size check (octet_length(technical_topics::text) <= 4000),
  constraint interview_session_ai_notes_key_questions_array check (jsonb_typeof(key_questions) = 'array'),
  constraint interview_session_ai_notes_key_questions_size check (octet_length(key_questions::text) <= 4000),
  constraint interview_session_ai_notes_suggested_followups_array check (jsonb_typeof(suggested_followups) = 'array'),
  constraint interview_session_ai_notes_suggested_followups_size check (octet_length(suggested_followups::text) <= 4000),
  constraint interview_session_ai_notes_generation_ms_check check (
    generation_ms is null or (generation_ms >= 0 and generation_ms <= 3600000)
  ),
  constraint interview_session_ai_notes_transcript_entry_count_check check (transcript_entry_count >= 0)
);

create unique index if not exists interview_session_ai_notes_session_idx
  on public.interview_session_ai_notes (session_id);

create index if not exists interview_session_ai_notes_user_generated_idx
  on public.interview_session_ai_notes (user_id, generated_at desc, id desc);

alter table public.interview_session_ai_notes enable row level security;
alter table public.interview_session_ai_notes force row level security;

drop policy if exists interview_session_ai_notes_select_own on public.interview_session_ai_notes;
create policy interview_session_ai_notes_select_own
  on public.interview_session_ai_notes
  for select
  to authenticated
  using (
    auth.uid() = user_id
    and exists (
      select 1
      from public.interview_sessions as s
      where s.id = session_id
        and s.user_id = auth.uid()
    )
  );

drop trigger if exists set_interview_session_ai_notes_updated_at on public.interview_session_ai_notes;
create trigger set_interview_session_ai_notes_updated_at
before update on public.interview_session_ai_notes
for each row execute function public.set_updated_at();

grant select on table public.interview_session_ai_notes to authenticated;
grant select, insert, update, delete on table public.interview_session_ai_notes to service_role;
