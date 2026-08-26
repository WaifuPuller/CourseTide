# CourseTide — Project Brief (for AI coding agent context)

This document defines what CourseTide is, exactly what to build, and the technical contract to follow. It is written for an AI coding agent (Antigravity) as build context — not a task list. Task-by-task instructions will be given separately, referencing this brief.

---

## 1. What this is

CourseTide is an AI-powered personalized learning path recommender. A learner describes a goal in natural language (e.g. "I want to become an ML Engineer, I know Python and basic stats"). The system:

1. Parses the goal into a structured target role + known skills
2. Detects the gap between known skills and what the target role requires
3. Recommends courses/resources that close that gap
4. Sequences them into a phased roadmap respecting prerequisites
5. Explains why each recommendation was made
6. Adapts the roadmap based on assessment feedback
7. Displays progress on a dashboard

This is a hackathon MVP with a hard deadline. Favor working, explainable, end-to-end functionality over polish or scale.

---

## 2. Must build (in this priority order — do not trade a lower number for a higher one)

1. Goal/chat input (conversational intake)
2. Learner profile (parsed goal, known skills, weekly hours)
3. Skill-gap detection (known skills vs. target role's required skills)
4. Course recommendation (semantic + gap-based ranking)
5. Roadmap generation (phased, prerequisite-respecting)
6. "Why this?" explainer (grounded, per-recommendation)
7. Assessment/feedback capture
8. Adaptive roadmap (reroute based on assessment results)
9. Dashboard (progress, skills, next actions)
10. Deployment

## 3. Explicitly out of scope for MVP (do not spend time here unless everything above is done)

- Animations/motion design beyond basic Tailwind transitions
- A large course catalog (the provided 48-course dataset is intentionally sized and sufficient)
- Multiple simultaneous domains in the live demo (see Section 5 — MVP filter)
- Complex authentication (a minimal learner identifier is sufficient; no OAuth, no password reset flows, no roles/permissions)
- Advanced analytics beyond what's needed for the dashboard's progress/skill views

---

## 4. Tech Stack

- **Frontend:** Next.js + Tailwind CSS
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL (Neon), with the `pgvector` extension enabled for embeddings
- **AI/ML:** An LLM API for goal parsing and explanation generation; `sentence-transformers` (or similar off-the-shelf embedding model) for semantic course matching — no fine-tuning, no training from scratch
- **Build tool:** Antigravity (this agent)

---

## 5. Data Contract

All seed data lives in `/data`. Load order matters:

1. `skills.json` — skill taxonomy: `{id, name, domain}`. `domain` is one of `ml` / `web` / `general`.
2. `target_roles.json` — role definitions: `{required_skills, recommended_optional_skills, default_timeframe_months, default_weekly_hours}` per role. This is what `skill_gap.py` compares a learner's known skills against.
3. `courses.csv` — columns: `id, title, description, skills (pipe-separated), difficulty, duration_hours, resource_type, domain, is_mvp, source, url, learning_outcomes`. `resource_type` is one of `course` / `project` / `assessment`.
4. `course_skills.csv` — normalized many-to-many bridge: `course_id, skill_id, is_primary`. Seed the `course_skills` table from this file directly.
5. `prerequisites.json` — **the authoritative skill-level prerequisite DAG**: `{skill_id: [prerequisite_skill_ids]}`. Use this for all roadmap sequencing.
6. `assessments.json` — assessment definitions: `{id, title, skill_id, difficulty, question_count, pass_score, mastery_score}`.
7. `course_prerequisites.csv` — **reference/documentation only. Do NOT use this file for roadmap gating logic.** It was derived by inheriting full upstream skill chains and contains some illogical chains for courses with loosely-related secondary skills. All sequencing must come from `prerequisites.json` (skill DAG) + `course_skills.csv` (`is_primary` flag to place a course in its primary skill's phase).

### MVP domain filter (required)

The demo runs on the ML/Data track only. Filter all recommendation and sequencing logic to:
```
domain IN ('ml', 'general')
```
equivalently, `courses.csv` rows where `is_mvp = true`. Web-domain data stays in the dataset unused — do not delete it, do not build UI for it. This must be a single filter condition, not hardcoded exclusion of specific rows, so flipping it later requires no data changes.

---

## 6. Database Schema

```sql
learners (
  id UUID PK, name TEXT, email TEXT,
  goal TEXT, parsed_goal JSONB,
  weekly_hours INT, created_at TIMESTAMP
)

skills (
  id UUID PK, name TEXT, domain TEXT
)

learner_skills (
  learner_id FK, skill_id FK,
  status TEXT,            -- 'known' | 'in_progress' | 'gap'
  mastery_score FLOAT
)

courses (
  id UUID PK, title TEXT, description TEXT,
  difficulty TEXT, duration_hours INT,
  resource_type TEXT,      -- 'course' | 'project' | 'assessment'
  domain TEXT, is_mvp BOOLEAN,
  source TEXT, url TEXT, learning_outcomes TEXT,
  embedding VECTOR(384)    -- pgvector column
)

course_skills (
  course_id FK, skill_id FK, is_primary BOOLEAN
)

learning_paths (
  id UUID PK, learner_id FK,
  phase_number INT, course_id FK,
  status TEXT,             -- 'locked' | 'available' | 'in_progress' | 'done'
  sequence_order INT
)

progress_events (
  id UUID PK, learner_id FK, course_id FK,
  difficulty_feedback TEXT,   -- 'too_easy' | 'just_right' | 'too_hard'
  assessment_score FLOAT,
  timestamp TIMESTAMP
)
```

---

## 7. Recommendation Pipeline (module contract)

```
recommender/
├── goal_parser.py      # free text -> {target_role, known_skills, timeframe_months, weekly_hours}
│                          via LLM call; target_role must match a key in target_roles.json
├── skill_gap.py         # known_skills vs target_roles[role].required_skills -> gap list
├── embeddings.py         # embed courses (title + description + learning_outcomes + skills)
│                          into pgvector at seed time; embed gap skills at query time;
│                          cosine similarity ranks candidate courses, filtered to MVP domain
├── path_sequencer.py     # topological sort of prerequisites.json (skill-level DAG) ->
│                          groups skills into ordered phases; places each course into its
│                          primary skill's phase via course_skills.is_primary
└── explainer.py          # LLM generates "why this" using ONLY structured inputs as grounding:
                            the skill gap it closes + the prerequisite reason it's sequenced
                            where it is. Do not let this free-generate unstructured claims.
```

**Adaptive loop** (rule-based, not an LLM call):
```
On progress_event:
  if assessment_score >= assessments[skill].mastery_score:
      mark skill mastered, skip/compress remaining same-skill content
  elif assessment_score < assessments[skill].pass_score:
      insert a remedial resource for that skill before the next phase
  update learning_paths accordingly
```

**Time-horizon recompute** (arithmetic, not a new pipeline):
```
estimated_weeks_for_phase = sum(duration_hours of courses in phase) / learner.weekly_hours
```
Recompute and re-render whenever `weekly_hours` changes. Phase order never changes from this — only the time labels.

---

## 8. API Surface (rough contract — implement as FastAPI routes)

- `POST /api/profile` — accepts free-text goal + weekly_hours, runs `goal_parser.py`, creates/updates a learner, returns parsed profile
- `GET /api/skill-gap/{learner_id}` — returns gap list for the learner's target role
- `GET /api/roadmap/{learner_id}` — returns phased roadmap with courses per phase
- `GET /api/explain/{learner_id}/{course_id}` — returns grounded explanation for one recommendation
- `POST /api/progress` — accepts a progress_event (difficulty_feedback and/or assessment_score), runs the adaptive loop, updates `learning_paths`
- `GET /api/dashboard/{learner_id}` — returns progress %, skill mastery states, next recommended action

---

## 9. Non-negotiables

- Never let the LLM free-generate factual claims about a course without grounding them in retrieved structured data (skill gap, prerequisite reasoning). This affects both `explainer.py` and any chat responses.
- Never use `course_prerequisites.csv` for gating logic.
- Never hardcode secrets; all credentials come from `.env` (see `.env.example`), which is gitignored.
- Keep commits granular and meaningfully messaged — this repo's commit history is a judged deliverable.
