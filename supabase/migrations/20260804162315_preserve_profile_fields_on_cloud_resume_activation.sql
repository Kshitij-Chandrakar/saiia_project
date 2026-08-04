-- C3.4 follow-up for the already-applied activation RPC.
-- Preserves existing profile values when a partial confirmed_profile omits a
-- field, while still allowing explicit empty values to clear submitted fields.

create or replace function public.activate_cloud_resume(
  p_user_id uuid,
  p_resume_id uuid,
  p_extraction_attempt integer,
  p_generation_id uuid,
  p_profile jsonb
)
returns setof public.resumes
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  activated_resume public.resumes%rowtype;
begin
  if not exists (
    select 1
    from public.resumes
    where id = p_resume_id
      and user_id = p_user_id
      and status = 'indexing'
      and extraction_attempt = p_extraction_attempt
      and confirmed_at is not null
      and confirmed_profile = p_profile
    for update
  ) then
    raise exception 'resume activation precondition failed' using errcode = 'P0001';
  end if;

  if not exists (
    select 1
    from public.resume_chunks
    where user_id = p_user_id
      and resume_id = p_resume_id
      and generation_id = p_generation_id
  ) then
    raise exception 'resume activation chunks missing' using errcode = 'P0001';
  end if;

  insert into public.profiles (
    user_id,
    full_name,
    headline,
    summary,
    skills,
    technical_skills,
    soft_skills,
    education,
    experience,
    projects,
    achievements,
    certifications,
    tools_frameworks
  )
  values (
    p_user_id,
    coalesce(nullif(p_profile->>'full_name', ''), ''),
    coalesce(nullif(p_profile->>'current_title', ''), nullif(p_profile->>'target_role', ''), ''),
    coalesce(nullif(p_profile->>'professional_summary', ''), ''),
    public.saiia_text_to_jsonb_array(coalesce(p_profile->>'top_skills', p_profile->>'skills', '')),
    public.saiia_text_to_jsonb_array(coalesce(p_profile->>'technical_skills', '')),
    public.saiia_text_to_jsonb_array(coalesce(p_profile->>'soft_skills', '')),
    public.saiia_text_to_jsonb_lines(coalesce(p_profile->>'education', p_profile->>'degree', '')),
    public.saiia_text_to_jsonb_lines(coalesce(p_profile->>'experience', p_profile->>'work_experience', '')),
    public.saiia_text_to_jsonb_lines(coalesce(p_profile->>'projects', '')),
    public.saiia_text_to_jsonb_lines(coalesce(p_profile->>'achievements', '')),
    public.saiia_text_to_jsonb_lines(coalesce(p_profile->>'certifications', '')),
    public.saiia_text_to_jsonb_array(coalesce(p_profile->>'tools_frameworks', ''))
  )
  on conflict (user_id) do update set
    full_name = case
      when p_profile ? 'full_name' then excluded.full_name
      else profiles.full_name
    end,
    headline = case
      when p_profile ? 'current_title' or p_profile ? 'target_role' then excluded.headline
      else profiles.headline
    end,
    summary = case
      when p_profile ? 'professional_summary' then excluded.summary
      else profiles.summary
    end,
    skills = case
      when p_profile ? 'top_skills' or p_profile ? 'skills' then excluded.skills
      else profiles.skills
    end,
    technical_skills = case
      when p_profile ? 'technical_skills' then excluded.technical_skills
      else profiles.technical_skills
    end,
    soft_skills = case
      when p_profile ? 'soft_skills' then excluded.soft_skills
      else profiles.soft_skills
    end,
    education = case
      when p_profile ? 'education' or p_profile ? 'degree' then excluded.education
      else profiles.education
    end,
    experience = case
      when p_profile ? 'experience' or p_profile ? 'work_experience' then excluded.experience
      else profiles.experience
    end,
    projects = case
      when p_profile ? 'projects' then excluded.projects
      else profiles.projects
    end,
    achievements = case
      when p_profile ? 'achievements' then excluded.achievements
      else profiles.achievements
    end,
    certifications = case
      when p_profile ? 'certifications' then excluded.certifications
      else profiles.certifications
    end,
    tools_frameworks = case
      when p_profile ? 'tools_frameworks' then excluded.tools_frameworks
      else profiles.tools_frameworks
    end,
    updated_at = timezone('utc', now());

  update public.resumes
  set is_active = false
  where user_id = p_user_id
    and is_active = true
    and id <> p_resume_id;

  update public.resumes
  set status = 'ready',
      is_active = true,
      index_status = 'indexed',
      parser_status = 'completed',
      extraction_status = 'completed',
      review_required = false,
      active_chunk_generation = p_generation_id,
      failure_code = null,
      failure_message = null,
      failed_at = null,
      last_error_at = null
  where id = p_resume_id
    and user_id = p_user_id
    and status = 'indexing'
    and extraction_attempt = p_extraction_attempt
  returning * into activated_resume;

  if activated_resume.id is null then
    raise exception 'resume activation update failed' using errcode = 'P0001';
  end if;

  return next activated_resume;
end;
$$;

revoke all on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) from public;
revoke all on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) from anon;
revoke all on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) from authenticated;
grant execute on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) to service_role;

comment on function public.activate_cloud_resume(uuid, uuid, integer, uuid, jsonb) is
  'C3.4 backend-only activation RPC. Preserves omitted profile fields during partial confirmed_profile updates, parses skill lists by comma/newline and prose fields by newline, activates the resume, and switches active_chunk_generation in one transaction.';
