-- C1.2 base Supabase schema for SAIIA cloud-owned user data.
-- RLS policies and storage buckets are intentionally deferred to C1.3.

create extension if not exists pgcrypto with schema extensions;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table if not exists public.profiles (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  full_name text not null default '',
  headline text not null default '',
  summary text not null default '',
  skills jsonb not null default '[]'::jsonb,
  technical_skills jsonb not null default '[]'::jsonb,
  soft_skills jsonb not null default '[]'::jsonb,
  education jsonb not null default '[]'::jsonb,
  experience jsonb not null default '[]'::jsonb,
  projects jsonb not null default '[]'::jsonb,
  achievements jsonb not null default '[]'::jsonb,
  certifications jsonb not null default '[]'::jsonb,
  tools_frameworks jsonb not null default '[]'::jsonb,
  profile_completion integer not null default 0,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint profiles_user_id_key unique (user_id),
  constraint profiles_profile_completion_range check (profile_completion between 0 and 100),
  constraint profiles_skills_array check (jsonb_typeof(skills) = 'array'),
  constraint profiles_technical_skills_array check (jsonb_typeof(technical_skills) = 'array'),
  constraint profiles_soft_skills_array check (jsonb_typeof(soft_skills) = 'array'),
  constraint profiles_education_array check (jsonb_typeof(education) = 'array'),
  constraint profiles_experience_array check (jsonb_typeof(experience) = 'array'),
  constraint profiles_projects_array check (jsonb_typeof(projects) = 'array'),
  constraint profiles_achievements_array check (jsonb_typeof(achievements) = 'array'),
  constraint profiles_certifications_array check (jsonb_typeof(certifications) = 'array'),
  constraint profiles_tools_frameworks_array check (jsonb_typeof(tools_frameworks) = 'array')
);

comment on table public.profiles is
  'C1.2 base profile table. Current local fields map summary from professional_summary/resume, headline from current_title/target_role/role, and list-like fields into JSONB arrays. RLS policies are added in C1.3.';

create table if not exists public.resumes (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  storage_path text not null,
  original_filename text not null default '',
  mime_type text not null default '',
  file_size bigint not null default 0,
  parser_provider text not null default 'pending',
  parser_status text not null default 'pending',
  extraction_status text not null default 'pending',
  index_status text not null default 'not_indexed',
  review_required boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint resumes_file_size_non_negative check (file_size >= 0),
  constraint resumes_parser_status_allowed check (parser_status in ('pending', 'processing', 'completed', 'failed')),
  constraint resumes_extraction_status_allowed check (extraction_status in ('pending', 'processing', 'completed', 'failed', 'needs_review')),
  constraint resumes_index_status_allowed check (index_status in ('not_indexed', 'pending', 'indexed', 'failed', 'needs_rebuild')),
  constraint resumes_user_storage_path_key unique (user_id, storage_path)
);

comment on table public.resumes is
  'C1.2 resume metadata only. Supabase Storage buckets and upload flows are deferred to C1.3/C3.';

create table if not exists public.resume_chunks (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  resume_id uuid not null references public.resumes(id) on delete cascade,
  section text not null default '',
  chunk_text text not null,
  embedding jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  constraint resume_chunks_metadata_object check (jsonb_typeof(metadata) = 'object'),
  constraint resume_chunks_embedding_shape check (embedding is null or jsonb_typeof(embedding) in ('array', 'object'))
);

comment on column public.resume_chunks.embedding is
  'Nullable JSONB placeholder for future vector data. Do not require pgvector until the C3 resume cloud/RAG migration decision enables it.';

create table if not exists public.job_contexts (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  company text not null default '',
  position text not null default '',
  job_description text not null default '',
  required_skills jsonb not null default '[]'::jsonb,
  responsibilities jsonb not null default '[]'::jsonb,
  seniority text not null default '',
  domain_keywords jsonb not null default '[]'::jsonb,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint job_contexts_required_skills_array check (jsonb_typeof(required_skills) = 'array'),
  constraint job_contexts_responsibilities_array check (jsonb_typeof(responsibilities) = 'array'),
  constraint job_contexts_domain_keywords_array check (jsonb_typeof(domain_keywords) = 'array')
);

comment on table public.job_contexts is
  'C1.2 job targeting context. Current local target_role maps to position and company_name maps to company. RLS policies are added in C1.3.';

create table if not exists public.user_settings (
  id uuid primary key default extensions.gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  preferred_answer_length text not null default 'standard',
  preferred_answer_style text not null default 'balanced',
  default_audio_source text not null default 'manual',
  overlay_settings jsonb not null default '{}'::jsonb,
  notification_preferences jsonb not null default '{}'::jsonb,
  marketing_consent boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint user_settings_user_id_key unique (user_id),
  constraint user_settings_overlay_settings_object check (jsonb_typeof(overlay_settings) = 'object'),
  constraint user_settings_notification_preferences_object check (jsonb_typeof(notification_preferences) = 'object')
);

comment on table public.user_settings is
  'C1.2 per-user settings shell for later authenticated website/desktop preferences. No account lifecycle is implemented in C1.2.';

create index if not exists profiles_user_id_idx on public.profiles (user_id);

create index if not exists resumes_user_id_idx on public.resumes (user_id);
create index if not exists resumes_user_id_created_at_idx on public.resumes (user_id, created_at desc);

create index if not exists resume_chunks_user_id_idx on public.resume_chunks (user_id);
create index if not exists resume_chunks_resume_id_idx on public.resume_chunks (resume_id);
create index if not exists resume_chunks_user_resume_idx on public.resume_chunks (user_id, resume_id);

create index if not exists job_contexts_user_id_idx on public.job_contexts (user_id);
create unique index if not exists job_contexts_one_active_per_user_idx
  on public.job_contexts (user_id)
  where is_active;

create index if not exists user_settings_user_id_idx on public.user_settings (user_id);

drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists set_resumes_updated_at on public.resumes;
create trigger set_resumes_updated_at
before update on public.resumes
for each row execute function public.set_updated_at();

drop trigger if exists set_job_contexts_updated_at on public.job_contexts;
create trigger set_job_contexts_updated_at
before update on public.job_contexts
for each row execute function public.set_updated_at();

drop trigger if exists set_user_settings_updated_at on public.user_settings;
create trigger set_user_settings_updated_at
before update on public.user_settings
for each row execute function public.set_updated_at();
