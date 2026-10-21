"""Approved evaluation specification only. Never imported by application code.

All people, evidence and histories here are authored synthetic fixtures. Word
ranges guide review; they are not minimums, runtime limits or quality scores.
"""
from copy import deepcopy


DEPTH = {
    'hr_motivation': (90, 160), 'introduction': (100, 170),
    'behavioral': (150, 230), 'technical_concept': (100, 200),
    'simple_fact': (20, 70), 'comparison': (140, 230),
    'coding': (100, 220), 'debugging': (100, 220),
    'system_design': (220, 400), 'resume_project': (140, 240),
    'project_walkthrough': (200, 320), 'narrow_followup': (30, 110),
}

PROFILE = {
    'full_name': 'Mira Example', 'current_title': 'Student developer',
    'technical_skills': 'Python, FastAPI, PostgreSQL',
    'projects': 'Appointment scheduler: Mira implemented API endpoints and the PostgreSQL schema.',
}
FACTS = [
    'Mira is a student developer.',
    'Mira implemented API endpoints and the PostgreSQL schema for an appointment scheduler.',
]
STORY = 'Mira found a duplicate-booking bug, reproduced it with two concurrent requests, and added a database uniqueness constraint. The reproduction then passed.'
DEFAULT_PROHIBITIONS = [
    'No invented employment, ownership, achievements, metrics, deployment or users.',
    'Absence of evidence does not establish that the candidate never did something.',
    'General knowledge, job requirements and previous AI answers are not personal evidence.',
]


def case(case_id, question, intent, category, essential, useful, unnecessary,
         *, profile=None, snippets=None, facts=None, history=None, job=None,
         tags=(), constraints=None, selected=False, failures=()):
    return dict(
        id=case_id, question=question, expected_intent=intent, category=category,
        evidence=dict(profile=deepcopy(PROFILE if profile is None else profile),
                      snippets=deepcopy(snippets or []), job=deepcopy(job or {}),
                      selected_resume=selected),
        history=deepcopy(history or []), tags=list(tags),
        explicit_constraints=constraints or {},
        permitted_personal_facts=list(FACTS if facts is None else facts),
        prohibited_inferences=list(DEFAULT_PROHIBITIONS), essential_content=essential,
        examples=dict(useful=useful, unnecessary=unnecessary),
        critical_failures=['Fabricated positive or negative personal history.',
                           'Materially wrong facts, code behavior or unsupported metrics.', *failures],
        human_review=['Check every personal claim against permitted evidence.',
                      'Explain the essential content clearly without padding.',
                      'Judge naturalness aloud and structure appropriate to this question.'],
    )


HISTORY = [dict(entry_id='synthetic-cache', mode='answer', question='What is caching?',
                answer_excerpt='A cache reuses saved data. A TTL permits staleness.', topic='caching')]

CASES = [
    case('introduction', 'Tell me about yourself.', 'introduction', 'hr',
         ['Current background', 'Supported backend contribution'],
         'The appointment scheduler contribution.', 'A list of every technology.'),
    case('motivation', 'Why do you want this role?', 'hr_motivation', 'hr',
         ['Supported skills connected to API work', 'Interest phrased as proposed motivation, not a past fact'],
         'API work as supported overlap.', 'Invented company culture.',
         job={'target_role': 'Backend engineer', 'job_description': 'Build reliable APIs.'}),
    case('behavioral_verified', 'Tell me about a difficult bug you solved.', 'behavioral', 'behavioral',
         ['Concurrent duplicate booking', 'Reproduction', 'Constraint', 'Observed reproduction result'],
         'The supplied bug incident.', 'An invented team conflict or percentage improvement.',
         snippets=[{'section': 'experience', 'text': STORY}], facts=FACTS + [STORY]),
    case('behavioral_missing', 'Tell me about a conflict you resolved.', 'behavioral', 'behavioral',
         ['Explicitly hypothetical approach if no supported incident'],
         'A clearly hypothetical disagreement.', 'Claiming a conflict happened or never happened.',
         profile={}, facts=[], tags=['missing_evidence', 'hypothetical']),
    case('concept_cache', 'How does caching work?', 'technical_concept', 'technical',
         ['Reuse', 'Cache miss', 'Invalidation or staleness'],
         'A general API response cache.', 'Candidate project attribution.'),
    case('simple_fact', 'What does HTTP stand for?', 'simple_fact', 'technical',
         ['Hypertext Transfer Protocol'], 'Usually no example needed.', 'A full networking tutorial.',
         profile={}, facts=[], tags=['simple_fact']),
    case('comparison_auth', 'Compare authentication and authorization.', 'comparison', 'technical',
         ['Identity versus permission', 'Relationship, not interchangeability'],
         'Login followed by permission checking.', 'A fabricated security incident.'),
    case('comparison_storage', 'Compare SQL and NoSQL databases.', 'comparison', 'technical',
         ['Data model', 'Query/access needs', 'Context-dependent tradeoffs'],
         'A general relational order model versus document access.', 'A claim that one is always faster.'),
    case('coding_dedupe', 'Write Python code to remove duplicates while preserving order.', 'coding', 'technical',
         ['Complete implementation', 'Order preserved', 'Complexity and hashability assumptions'],
         'Repeated numbers and an empty input.', 'Invented stdin or platform requirements.',
         constraints={'language': 'python'}, tags=['coding']),
    case('coding_repeat', 'Write Python code to remove duplicates while preserving order.', 'coding', 'technical',
         ['Same semantics as prior answer', 'Complete code and assumptions'],
         'An empty input regression.', 'Changing the algorithm just to sound different.',
         history=[dict(entry_id='synthetic-code', mode='answer', question='Write Python code to remove duplicates while preserving order.',
                       answer_excerpt='def unique(values): return list(dict.fromkeys(values))', topic='order-preserving deduplication')],
         constraints={'language': 'python'}, tags=['repeated_coding', 'coding']),
    case('debugging', 'Debug this Python loop: for i in range(len(xs)+1): print(xs[i])', 'debugging', 'technical',
         ['Out-of-range final index', 'Correct loop', 'Empty input behavior'],
         'A two-element list trace.', 'An unrelated optimization.', tags=['coding']),
    case('design_notifications', 'Design a notification service and explain reliability tradeoffs.', 'system_design', 'technical',
         ['Assumptions', 'Queue and workers', 'Retries and idempotency', 'Failure handling and tradeoffs'],
         'A hypothetical duplicate delivery.', 'Unsupported scale numbers.', tags=['long_answer']),
    case('project_contribution', 'What was your role in your appointment scheduler project?', 'resume_project', 'hr',
         ['API endpoints and schema', 'Ownership boundaries'],
         'Only the supplied contribution.', 'Claiming responsibility for reminders or deployment.'),
    case('project_walkthrough', 'Walk me through how your appointment scheduler project was built.', 'project_walkthrough', 'technical',
         ['Supported purpose', 'Backend workflow limited to supplied details', 'Unknowns not invented'],
         'The supported schema/API relationship.', 'Invented frontend, hosting or traffic.', tags=['sparse_evidence']),
    case('followup_narrow', 'What about its limitations?', 'narrow_followup', 'technical',
         ['Caching limitations', 'Staleness and invalidation'],
         'One brief stale-value example if useful.', 'Repeating the entire definition.',
         history=HISTORY, tags=['narrow_followup']),
    case('followup_ambiguous', 'Can you explain that part?', 'narrow_followup', 'general',
         ['Recognize unresolved reference', 'No invented topic'],
         'No example until reference is resolved.', 'Choosing an arbitrary earlier topic.',
         profile={}, facts=[], tags=['ambiguous_followup']),
    case('personal_missing', 'Tell me about a time you helped someone.', 'behavioral', 'personal',
         ['Do not invent an incident', 'Hypothetical only if explicitly framed'],
         'A labeled hypothetical, not autobiographical detail.', 'A canned first-person childhood story.',
         profile={}, facts=[], tags=['missing_evidence', 'personal_fabrication']),
    case('selected_conflict', 'What was your role in your appointment scheduler project?', 'resume_project', 'hr',
         ['Selected resume contribution wins over stale profile'],
         'API/schema contribution.', 'Old profile leadership and production metrics.',
         profile={'full_name': 'Old Profile', 'projects': 'Led 20 engineers and served one million users.'},
         snippets=[{'section': 'projects', 'text': PROFILE['projects']}], selected=True,
         tags=['conflicting_evidence']),
    case('jd_only', 'Why should we hire you for Kubernetes operations?', 'hr_motivation', 'hr',
         ['Distinguish job requirements from candidate experience', 'Supported adjacent skills only'],
         'A hypothetical learning approach.', 'Claiming Kubernetes production ownership.',
         job={'target_role': 'Platform engineer', 'job_description': 'Own Kubernetes production operations.'},
         tags=['jd_not_experience']),
    case('retrieval_irrelevant', 'Explain database normalization.', 'technical_concept', 'technical',
         ['Reduce redundancy', 'Relationships', 'Update anomalies and tradeoffs'],
         'General customer/order tables.', 'Forcing unrelated hobbies into the answer.',
         snippets=[{'section': 'hobbies', 'text': 'Mira enjoys watercolor painting.'}], tags=['irrelevant_retrieval']),
    case('fact_repeat', 'What does HTTP stand for?', 'simple_fact', 'technical',
         ['Hypertext Transfer Protocol', 'Stable correctness despite repetition'],
         'None necessary.', 'A changed expansion to create novelty.', profile={}, facts=[],
         history=[dict(entry_id='synthetic-http', mode='answer', question='What does HTTP stand for?',
                       answer_excerpt='Hypertext Transfer Protocol.', topic='HTTP')], tags=['repeated_fact']),
    case('explicit_short', 'In one sentence, explain caching.', 'technical_concept', 'technical',
         ['Reuse stored results', 'Honor one-sentence request'],
         'Only if it fits the explicit constraint.', 'A mandatory example section.',
         constraints={'max_sentences': 1}, tags=['explicit_short']),
    case('explicit_detailed', 'Explain caching in detail, including invalidation, failure modes and tradeoffs.', 'technical_concept', 'technical',
         ['Invalidation strategies', 'Staleness', 'Stampede/failure handling', 'Tradeoffs'],
         'A general cache update/failure sequence.', 'Repeating the definition to fill space.',
         constraints={'depth': 'detailed'}, tags=['explicit_detailed']),
    case('fallback_long', 'Design a notification service with retries, ordering and failure recovery.', 'system_design', 'technical',
         ['Complete reliability explanation', 'Fallback preserves question requirements', 'No concatenation of attempts'],
         'A hypothetical retry/duplicate scenario.', 'Unsupported claims of exactly-once delivery.',
         tags=['fallback', 'long_answer'], failures=['Partial primary text concatenated with fallback.']),
]


def approved_policy(item):
    """Resolve review guidance from explicit case intent, not a new classifier.

    Explicit constraints override default depth guidance, never grounding or
    correctness. A detailed request allows exceeding the suggested upper bound.
    Ambiguous-reference behavior is characterized separately, not activated here.
    """
    constraints = deepcopy(item['explicit_constraints'])
    return dict(
        intent=item['expected_intent'], suggested_words=list(DEPTH[item['expected_intent']]),
        mandatory_minimum=False, code_excluded_from_word_count=True,
        explicit_constraints=constraints,
        default_range_is_binding=False,
        precedence=['correctness_and_grounding', 'explicit_question_constraints',
                    'existing_user_length_preference_if_available', 'question_type_guidance', 'style_variation'],
        missing_evidence='explicit_hypothetical_allowed_no_positive_or_negative_history',
        permitted_personal_facts=list(item['permitted_personal_facts']),
    )
