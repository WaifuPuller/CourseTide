# CourseTide — Day 3 Technical Walkthrough

---

## 1. Day 3 Objective

Day 3 of CourseTide extends the core AI profile parser and semantic course recommender into an end-to-end, prerequisite-aware career milestone roadmap with grounded AI explanations.

Specifically, Day 3 accomplishes:
1. **Prerequisite-Aware Roadmap Sequencing**: Transforming ranked, flat candidate recommendations into a topologically sorted sequence based on canonical skill prerequisite dependencies.
2. **Phased Milestone Structuring**: Grouping sequenced courses into logical learning phases (Phase 1: Foundations → Phase 2: Core Competencies → Phase 3: Specialized Methods → Phase 4+: Advanced Practice).
3. **Database-Backed Learning Path Persistence**: Transactionally saving generated roadmaps to PostgreSQL (`learning_paths`) with idempotent lookup and state tracking (`available` for Phase 1 vs `locked` for subsequent phases).
4. **Grounded AI Explanation Chain**: Generating concise, 2–3 sentence transparent explanations via an ordered Gemini model fallback chain (`gemini-3.7-flash` → `gemini-3.6-flash` → `gemini-3.5-flash`), strictly grounded on structured facts (skill gap closed, prerequisite sequencing logic) with zero hallucinated claims.
5. **Interactive Timeline UI & Modal Explainer**: Presenting a visual phased milestone timeline in Next.js 15 with course sequencing badges, status indicators, and an interactive "Why this?" explanation dialog.

> [!NOTE]
> Day 3 does not replace Day 2's profile extraction or candidate recommendation ranking. Instead, Day 2 candidate courses feed directly into Day 3's topological sequencer, preserving candidate match ranking while structuring the learning journey.

---

## 2. Starting Point Before Day 3

Prior to Day 3, CourseTide had completed:
- **Day 1 Foundations**: Neon PostgreSQL with `pgvector`, catalog schema (`skills`, `courses`, `course_skills`, `assessments`, `learners`, `learner_skills`, `learning_paths`), and catalog seeding (48 courses, 22 taxonomy skills, 74 course-skill relationships).
- **Day 2 Intelligent Intake & Recommender**:
  - `GeminiGoalParser`: Extracts target roles, known skills, timeframes, and weekly commitment from natural language.
  - `SkillGapEngine`: Deterministically calculates skill gaps and role readiness match percentages ($S_{\text{known}} / S_{\text{required}}$).
  - `SemanticRecommender`: Ranks candidate courses via hybrid composite scoring ($0.50 \cdot S_{\text{sim}} + 0.35 \cdot S_{\text{gap\_recall}} + 0.15 \cdot S_{\text{primary\_match}}$) using 384-dimensional dense vector embeddings.
  - Production Deployment on Vercel with FastAPI backend and Next.js 15 frontend.

**The Limitation Before Day 3**:
Day 2 output was a flat, unordered list of top 6 recommended courses. If a learner needed both foundational statistics and advanced deep learning, the recommender displayed them side-by-side with no pedagogical ordering, no milestone phasing, and no explanation for why a specific course was selected.

---

## 3. Day 3 Architecture

CourseTide Day 3 combines deterministic graph algorithms for prerequisite safety with large language models for natural-language extraction and transparent explanation.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       USER / FRONTEND UI                                         │
│                       Next.js 15 + Tailwind CSS (https://course-tide.vercel.app/)                │
└─────────────────────────────────┬──────────────────────────────────────▲─────────────────────────┘
                                  │ 1. Natural Language Goal             │ 7. Phased Roadmap Timeline
                                  ▼                                      │    & "Why this?" Modal
┌────────────────────────────────────────────────────────────────────────┴─────────────────────────┐
│                                       FASTAPI BACKEND                                            │
│                                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ [1] POST /api/profile (LLM Intake & Profile Generation)                                  │   │
│   │   • Gemini Model Fallback Chain: gemini-3.7-flash → gemini-3.6-flash → gemini-3.5-flash   │   │
│   │   • Deterministic Taxonomy Normalizer & SkillGapEngine (G = R_target \ K_learner)        │   │
│   │   • Hybrid Semantic Candidate Recommender (384-d dense vector embeddings, top_k=6)       │   │
│   │   • Database Persistence: learners table + learner_skills table                          │   │
│   └─────────────────────────────────────────┬────────────────────────────────────────────────┘   │
│                                             │                                                    │
│                                             ▼                                                    │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ [2] GET /api/roadmap/{learner_id} (Deterministic Prerequisite Sequencer)                 │   │
│   │   • Input: Candidate courses + Learner skill gaps + Known skills                         │   │
│   │   • Canonical DAG: data/prerequisites.json (Deterministic Topological Sort)              │   │
│   │   • Primary Skill Gating: Transitive ancestor reachability (Zero cycles)                 │   │
│   │   • Phase Partitioning: Phase 1 (available) → Phases 2..N (locked)                       │   │
│   │   • Database Persistence: learning_paths table (Idempotent transactional insert)         │   │
│   └─────────────────────────────────────────┬────────────────────────────────────────────────┘   │
│                                             │                                                    │
│                                             ▼                                                    │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ [3] GET /api/explain/{learner_id}/{course_id} (Grounded Gemini Explainer)                │   │
│   │   • Context Extraction: Learner gaps + Course primary skill + Prereqs + Phase placement  │   │
│   │   • Strict Grounding Prompt: Negative constraints (No certifications, fluff, or myths)   │   │
│   │   • Gemini Model Fallback Chain: gemini-3.7-flash → gemini-3.6-flash → gemini-3.5-flash   │   │
│   │   • Structured JSON Response: 2-3 sentence transparent, factual explanation              │   │
│   └──────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibility Breakdown

| System Layer | Implementation File | AI vs. Deterministic | Responsibility |
| :--- | :--- | :--- | :--- |
| **Profile Parsing** | `backend/app/recommender/goal_parser.py` | **LLM (Gemini 3.x Chain)** | Extracts structured JSON profile from natural language. |
| **Skill Gap Analysis**| `backend/app/recommender/skill_gap.py` | **Deterministic (Set Math)** | Computes $G = R_{\text{target}} \setminus K_{\text{known}}$ and match percentage. |
| **Course Retrieval** | `backend/app/recommender/embeddings.py` | **Deterministic Vector Math**| Embeddings + hybrid gap recall formula ($0.50 S_{\text{sim}} + 0.35 S_{\text{gap}} + 0.15 S_{\text{pri}}$). |
| **Path Sequencer** | `backend/app/recommender/path_sequencer.py`| **Deterministic Graph (DAG)**| Topological sort and milestone phase grouping over canonical prerequisites. |
| **Roadmap API** | `backend/app/api/roadmap.py` | **Deterministic Orchestrator**| Orchestrates recommender → sequencer → `learning_paths` DB persistence. |
| **Recommendation Explainer** | `backend/app/recommender/explainer.py` | **LLM (Gemini 3.x Chain)** | Generates transparent, grounded explanations of recommendations and phase placement. |

---

## 4. Step 1 — Prerequisite Path Sequencer

### 4.1 Purpose
While semantic similarity and gap coverage identify *which* courses to take, they do not indicate *when* to take them. Taking an advanced MLOps course before mastering fundamental Python data structures leads to frustration. The Path Sequencer deterministically orders courses so prerequisite competencies strictly precede advanced applications.

### 4.2 Authoritative Data Sources
- **`data/prerequisites.json` (Authoritative Source)**: The canonical Directed Acyclic Graph (DAG) defining skill-to-skill prerequisite requirements across the entire taxonomy (e.g. `data_manip` → `ml_fund` → `deep_learning` → `mlops`).
- **`course_skills` metadata**: Defines the `primary_skill` taught by each course (representing its core gating competency) alongside secondary covered skills.
- **Why `data/course_prerequisites.csv` is NOT the Authoritative Gating Source**: Course-to-course relationships in catalog CSVs are static provider-specific recommendations. Using skill-level prerequisite DAGs enables universal, cross-provider prerequisite resolution across arbitrary subsets of courses.

### 4.3 Algorithm & Phase Grouping
1. **Transitive Ancestor Prerequisite Mapping**: For each course $C_B$ with primary skill $S_B$, collect all upstream skills in the canonical DAG that have not already been mastered by the learner:
   $$\text{needed\_prereqs}(C_B) = \text{ancestors}(S_B, \text{DAG}) \setminus K_{\text{known}}$$
2. **Course-to-Course Dependency Construction**: An edge $C_A \to C_B$ is established if and only if Course A's `primary_skill` $S_A$ is an upstream prerequisite for Course B's `primary_skill` $S_B$:
   $$S_A \in \text{needed\_prereqs}(C_B)$$
3. **Topological Sorting**: Kahn’s algorithm sorts courses deterministically. A priority queue preserves the original ranking order for independent peer courses.
4. **Phase Assignment**:
   $$\text{phase}(C) = 1 + \max\left(\{0\} \cup \{\text{phase}(C_{\text{prereq}}) \mid C_{\text{prereq}} \in \text{prereqs}(C)\}\right)$$
5. **Status Assignment**: Phase 1 courses receive `available`; Phase 2+ courses receive `locked`.

### 4.4 Cycle Detection Defense
Explicit cycle detection is preserved: if any circular dependency exists in the underlying prerequisite mapping, the sequencer raises a structured `CycleDetectedError` identifying the cyclic nodes.

---

## 5. Step 2 — Phased Roadmap API (`GET /api/roadmap/{learner_id}`)

### 5.1 Request Flow & Lifecycle
When invoked, `GET /api/roadmap/{learner_id}`:
1. Looks up the learner in Neon by UUID (returns HTTP 404 if missing).
2. Extracts target role, known skills, gap skills, and weekly study hours from `parsed_goal`.
3. Handles zero-gap learners immediately with an empty phase response.
4. Calls `recommend_courses_async()` to retrieve the top 6 candidate recommendations.
5. Invokes `sequence_courses()` to construct topologically sorted phases.
6. **Transactional Persistence**: If `learning_paths` records do not already exist for this learner, inserts 6 records (`learner_id`, `course_id`, `phase_number`, `sequence_order`, `status`) and commits.
7. Serializes and returns `RoadmapResponse`.

### 5.2 Response Schema

```typescript
interface RoadmapResponse {
  learner_id: string;
  target_role: string;
  role_name: string;
  total_courses: number;
  total_estimated_hours: number;
  total_estimated_weeks: number;
  phases: RoadmapPhase[];
}

interface RoadmapPhase {
  phase_number: number;
  phase_name: string;
  estimated_hours: number;
  skills: string[];
  courses: RoadmapCourse[];
}

interface RoadmapCourse {
  course_id: string;
  title: string;
  difficulty: string;
  duration_hours: number;
  domain: string;
  source?: string;
  url?: string;
  primary_skill?: string;
  covered_skills: string[];
  phase_number: number;
  sequence_order: number;
  status: "available" | "locked";
  match_score?: number;
}
```

---

## 6. Step 4 — Grounded Gemini Explainer (`GET /api/explain/{learner_id}/{course_id}`)

### 6.1 Purpose & Grounding Principles
Learners need to know *why* a specific course was selected and *why* it appears in its given phase. The explainer enforces strict grounding constraints:
- **No Hallucinated Credentials**: Explicitly instructed NOT to invent certifications, degree credits, or employer partnerships.
- **No Career Fluff**: Must base the explanation strictly on the skill gap closed and prerequisite sequencing logic.
- **Strict Structured Output**: Returns a validated JSON schema containing a 2–3 sentence explanation.

### 6.2 Explanation Context Payload
The explainer receives an immutable, structured `ExplanationContext`:
- Learner target role & role title
- Known skills & remaining skill gaps
- Course ID, title, difficulty, duration, and primary skill
- Covered gap skills
- Roadmap phase number and phase title
- Upstream prerequisites required & downstream competencies unlocked

### 6.3 Ordered Gemini Fallback Chain
$$\text{Primary: } \mathbf{\texttt{gemini-3.7-flash}} \xrightarrow{\text{503 / 429 / Timeout}} \text{Fallback 1: } \mathbf{\texttt{gemini-3.6-flash}} \xrightarrow{\text{503 / 429 / Timeout}} \text{Fallback 2: } \mathbf{\texttt{gemini-3.5-flash}}$$

- **Stop on Success**: Halts on the first successful model response.
- **Retryable Availability Errors (`429`, `500`, `502`, `503`, `504`, timeouts, malformed JSON)**: Advances sequentially to the next model.
- **Non-Retryable Errors (`400 Bad Request`, `404 Not Found`)**: Fails fast immediately.
- **No Heuristic Hallucination Fallback**: If all configured Gemini models fail retryably, raises `ExplanationUnavailableError` (HTTP 503) rather than fabricating fake template text.

---

## 7. Step 3 — Roadmap Timeline UI & Explainer Modal

### 7.1 Frontend Architecture (`frontend/src/app/page.tsx`)
1. **Intake → Roadmap Sequence**: When the user submits their goal, `POST /api/profile` creates the learner and renders Day 2 profile statistics. The frontend immediately invokes `GET /api/roadmap/{learner_id}` to render the Phased Roadmap Timeline above the catalog candidate cards.
2. **Milestone Phase Display**:
   - Distinct phase header cards with total phase hours and covered competencies.
   - Course cards displaying sequential numbering (`[1]`, `[2]`, `[3]...`).
   - Status indicators (`available` with green badge vs `locked` with padlock icon).
3. **Interactive "Why this?" Modal Dialog**:
   - Clicking "Why this?" on any course triggers `GET /api/explain/{learner_id}/{course_id}`.
   - Shows loading skeleton while the Gemini model chain executes.
   - Displays the grounded explanation in a modal dialog with course metadata badges.

---

## 8. Production Incident #1 — Gemini Model Fallback Failures

During live smoke testing, two external LLM API availability issues were uncovered and resolved:

### Incident 1A: Primary Model 503 Capacity Spike
- **Symptom**: `POST /api/profile` failed with HTTP 503: `"This model is currently experiencing high demand..."`.
- **Root Cause**: `gemini-3.7-flash` experienced regional capacity throttling, and the Day 2 `goal_parser.py` had no fallback chain.
- **Fix (`ff4b6a2`)**: Implemented the sequential fallback loop in `GeminiGoalParser.parse()` with 7 new unit tests (16/16 passed).

### Incident 1B: Legacy Gemini 2.5/2.0 Deprecation
- **Symptom**: When `gemini-3.7-flash` throttled, the system advanced to Fallback 1 (`gemini-2.5-flash`), which returned `HTTP 404 Not Found`: `"This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.6-flash..."`.
- **Root Cause**: Google restricted legacy 2.5 models for new API keys and permanently shut down `gemini-2.0-flash` on June 1, 2026.
- **Fix (`a884b2c`)**: Updated the active model chain across both `goal_parser.py` and `explainer.py` to the verified 3.x lineup:
  1. `gemini-3.7-flash`
  2. `gemini-3.6-flash`
  3. `gemini-3.5-flash`

---

## 9. Production Incident #2 — Roadmap 500 (`CycleDetectedError`)

### The Failure
During the subsequent smoke test, `POST /api/profile` succeeded, but `GET /api/roadmap/{learner_id}` crashed with **HTTP 500 (`Internal Server Error`)**.

### Forensic Root Cause
The 6 candidate courses recommended for the Machine Learning Engineer goal included:
- `made-with-ml-mlops-course` (Primary: `mlops`, Secondary: `ml_fund`)
- `mlops-specialization` (Primary: `mlops`, Secondary: `deep_learning`)
- `deep-learning-specialization` (Primary: `deep_learning`, Secondary: `neural_nets`)
- `intro-to-deep-learning` (Primary: `deep_learning`, Secondary: `neural_nets`)

The canonical skill DAG (`prerequisites.json`) was strictly acyclic (`ml_fund` → `deep_learning` → `mlops`). However, the course sequencer evaluated dependencies symmetrically over *all* covered skills:
1. `deep-learning-specialization` needs `ml_fund` $\implies$ `made-with-ml-mlops-course` (which tags `ml_fund` as secondary) was treated as a prerequisite ($A \to B$).
2. `made-with-ml-mlops-course` needs `deep_learning` $\implies$ `deep-learning-specialization` (which teaches `deep_learning`) was treated as a prerequisite ($B \to A$).

This created an artificial mutual dependency ($A \to B$ and $B \to A$), triggering `CycleDetectedError`.

---

## 10. Roadmap Sequencing Fix (`4b2029d`)

### Algorithmic Resolution
In `backend/app/recommender/path_sequencer.py`:
1. Gating dependencies are established **strictly via primary skills**:
   $$S_A = \text{primary\_skill}(C_A), \quad S_B = \text{primary\_skill}(C_B)$$
2. Course A is marked as a prerequisite of Course B if and only if $S_A$ is an unmastered transitive ancestor of $S_B$ in the canonical DAG:
   $$S_A \in \text{ancestors}(S_B, \text{DAG}) \setminus K_{\text{known}}$$
3. Because DAG reachability is a strict partial order, $S_B$ can never be an ancestor of $S_A$. Circular dependencies between courses are mathematically impossible.
4. Secondary skills remain intact for composite scoring and gap coverage metadata.

---

## 11. Live Production Verification & Evidence

With commit `4b2029d` deployed to Vercel, the complete backend and database flow was verified live in production against learner `e062cb8a-9605-4b7d-8b66-563b28a82901`:

### 11.1 Goal Intake Verification
- **Goal**: `"I want to become a machine learning engineer in 6 months. I know Python and statistics."`
- **Target Role**: `ml_engineer` (`Machine Learning Engineer`)
- **Readiness Match**: `22.2%` (2 known: `python`, `stats`; 7 gaps: `git`, `data_manip`, `ml_fund`, `feat_eng`, `deep_learning`, `neural_nets`, `mlops`)

### 11.2 Phased Roadmap API Verification (`GET /api/roadmap/{learner_id}`)
- **HTTP Status**: `200 OK`
- **Total Metrics**: 6 courses, 171 hours, 22 weeks (at 8 hrs/wk)
- **Phase Breakdown**:
  - **Phase 1: Foundations** (`available`, 50 hrs):
    - `[1]` Machine Learning Project (Titanic/House Prices) — 10 hrs
    - `[2]` Machine Learning Specialization — 40 hrs
  - **Phase 2: Core Competencies** (`locked`, 66 hrs):
    - `[3]` Deep Learning Specialization — 60 hrs
    - `[4]` Intro to Deep Learning — 6 hrs
  - **Phase 3: Specialized Methods** (`locked`, 55 hrs):
    - `[5]` Made With ML - MLOps Course — 20 hrs
    - `[6]` MLOps Specialization — 35 hrs

### 11.3 LearningPath Persistence & Idempotency Verification
- **First Request**: Created and persisted exactly 6 `learning_paths` rows in Neon PostgreSQL.
- **Second Request**: Repeated the identical GET request; confirmed that row count remained exactly 6 rows (zero duplicate rows inserted).

### 11.4 Grounded Explainer API Verification (`GET /api/explain/{learner_id}/{course_id}`)
- **Target**: `machine-learning-project-titanic-house-prices`
- **HTTP Status**: `200 OK`
- **Model Execution**: The production explainer request was successfully handled by the configured Gemini fallback chain (`gemini-3.7-flash` → `gemini-3.6-flash` → `gemini-3.5-flash`). The specific model that ultimately served the successful request was not independently observable from available production response evidence.
- **Returned Grounded Explanation**:
  > *"This course is recommended for your Machine Learning Engineer target role because it directly addresses your skill gaps in ml_fund and data_manip through practical application. Placed in Phase 1: Foundations, it leverages your existing python and stats skills along with data_manip prerequisites to unlock essential downstream competencies like feat_eng and deep_learning."*

> [!NOTE]
> **Verification Scope Distinction**: The explainer was verified directly via the production API endpoint to inspect raw grounding and prevent redundant live LLM quota consumption. The browser UI implementation was verified via build-time TypeScript validation and Next.js compilation.

---

## 12. Database State & Cleanup

Following verification, the disposable smoke-test learner records were transactionally cleaned from Neon PostgreSQL:

```sql
DELETE FROM learner_skills WHERE learner_id = 'e062cb8a-9605-4b7d-8b66-563b28a82901';
DELETE FROM learning_paths WHERE learner_id = 'e062cb8a-9605-4b7d-8b66-563b28a82901';
DELETE FROM learners WHERE id = 'e062cb8a-9605-4b7d-8b66-563b28a82901';
```

### Final Verified Database Counts

| Database Table | Pre-Test Count | During Test Count | Post-Cleanup Count | Status |
| :--- | :---: | :---: | :---: | :--- |
| **`learners`** | 0 | 1 | **0** | Clean |
| **`learner_skills`** | 0 | 9 | **0** | Clean |
| **`learning_paths`** | 0 | 6 | **0** | Clean |
| **`progress_events`** | 0 | 0 | **0** | Clean |
| **`skills`** | 22 | 22 | **22** | Intact Catalog |
| **`courses`** | 48 | 48 | **48** | Intact Catalog |
| **`course_skills`** | 74 | 74 | **74** | Intact Catalog |
| **`assessments`** | 10 | 10 | **10** | Intact Catalog |

---

## 13. Testing Summary

### 13.1 Full Test Suite Verification

```bash
$ python -m pytest backend/tests
```

**Final Suite Result**: **68 passed, 0 failed** in 12.94s.

### 13.2 Component Test Breakdown

| Component | Test Suite | Passing Count | Key Behaviors Verified |
| :--- | :--- | :---: | :--- |
| **API Smoke & Contracts**| `backend/tests/test_api.py` | **8 passed** | Health checks, profile creation, commit rollbacks, 404 contracts for unknown learners. |
| **Path Sequencer** | `backend/tests/test_path_sequencer.py` | **11 passed** | Topological sorting, depth calculation, cycle detection, multi-skill course isolation, 6-course production regression. |
| **Roadmap API** | `backend/tests/test_api_roadmap.py` | **6 passed** | End-to-end endpoint execution, zero-gap handling, `learning_paths` idempotency, rollback on DB error. |
| **Goal Parser** | `backend/tests/test_goal_parser.py` | **16 passed** | Taxonomy normalization, structured parsing, 503/429/timeout fallback cascade, malformed JSON recovery, OpenAI isolation. |
| **Explainer** | `backend/tests/test_explainer.py` | **13 passed** | Strict prompt grounding, fallback cascade (`3.7` → `3.6` → `3.5`), 503 exhaustion, non-retryable 400 fast-fail, FastAPI integration. |
| **Embeddings** | `backend/tests/test_embeddings.py` | **7 passed** | Vector text formulation, composite scoring, gap recall weights, testing-mode fast path. |
| **Skill Gap** | `backend/tests/test_skill_gap.py` | **5 passed** | Role requirements extraction, novice vs intermediate gap math, invalid role handling. |
| **Catalog & Seed** | `backend/tests/test_models.py`, `test_seed.py`| **2 passed** | Model instantiation, seed data integrity. |
| **Frontend Production Build** | Next.js Production Build (`npm run build`) | **Compiled** | TypeScript validation, static generation, route compilation (compiled in 2.4s). |

> [!NOTE]
> **Post-Audit Test Maintenance (`92e7c5f`)**: During the closing audit, two stale Day 1 skeleton tests in `test_api.py` (which expected HTTP 200 for random non-existent UUIDs) were updated to assert HTTP 404, aligning them with the real production contract and achieving 68/68 passed tests.

---

## 14. Git History & Chronology

```text
92e7c5f (HEAD -> main) test(api): align skeleton tests with 404 contract
4b2029d (origin/main) fix(roadmap): prevent secondary-skill prerequisite cycles
a884b2c fix(llm): update Gemini fallback models
ff4b6a2 fix(goal-parser): add Gemini model fallback chain
bd6d4ff feat(frontend): add roadmap timeline and explanation UI
2365c87 feat(explain): add grounded recommendation explainer
adf6b6b feat(api): add phased learner roadmap endpoint
7f24730 feat(roadmap): add prerequisite path sequencer
```

### Categorized Commit Table

| Commit SHA | Type | Scope | Description / Purpose |
| :---: | :---: | :---: | :--- |
| `7f24730` | **Feature** | Recommender | Implemented topological path sequencer (`path_sequencer.py`). |
| `adf6b6b` | **Feature** | API / Database | Added `GET /api/roadmap/{learner_id}` and `LearningPath` ORM persistence. |
| `2365c87` | **Feature** | Explainer | Added grounded explainer (`explainer.py`) and `GET /api/explain/{learner_id}/{course_id}`. |
| `bd6d4ff` | **Feature** | Frontend | Built roadmap timeline UI, phase grouping badges, and explainer modal. |
| `ff4b6a2` | **Resilience**| Recommender | Added sequential Gemini fallback chain to Day 2 `goal_parser.py` after live 503 incident. |
| `a884b2c` | **Resilience**| Config / LLM | Replaced deprecated `gemini-2.5/2.0` models with active 3.x series (`3.7` → `3.6` → `3.5`). |
| `4b2029d` | **Bug Fix** | Recommender | Fixed course dependency graph to gate on primary skills, eliminating secondary-skill cycles. |
| `92e7c5f` | **Test Maint**| Tests | Updated stale Day 1 placeholder assertions in `test_api.py` to match the real 404 API contract. |

---

## 15. System Evolution: Before vs. After Day 3

| Dimension | Before Day 3 (Day 2 State) | After Day 3 (Production Verified) |
| :--- | :--- | :--- |
| **Course Output** | Unordered list of top 6 candidate matches. | Topologically sequenced, phased milestone curriculum. |
| **Prerequisite Logic** | None (courses recommended independently). | Strict DAG enforcement over canonical `data/prerequisites.json`. |
| **Learner Timeline** | Static hours total without scheduling context. | Estimated total hours, weekly commitment pacing, and phase progression. |
| **Database Tracking**| Profile and skills stored; no learning path state. | Phased `learning_paths` persisted with `available` vs `locked` states. |
| **AI Transparency** | No explanation for course selection. | Grounded 2–3 sentence factual explanation per course. |
| **LLM Reliability** | Single-model Gemini calls vulnerable to 503s. | Ordered 3-tier Gemini fallback chain (`3.7-flash` → `3.6-flash` → `3.5-flash`). |

---

## 16. Security & Reliability Safeguards

1. **Zero Secret Leakage**:
   - Gemini API keys are accessed strictly server-side in Python.
   - Zero `NEXT_PUBLIC_` client-exposed API keys.
2. **Graceful Degradation Without Hallucination**:
   - If all Gemini models are exhausted, the explainer returns a controlled HTTP 503 rather than fabricating heuristic explanations.
3. **Database Transaction Isolation**:
   - All multi-table operations (`learners`, `learner_skills`, `learning_paths`) execute within atomic transactions with automatic rollback on error.
4. **Deterministic Graph Invariants**:
   - Prerequisite ordering is 100% deterministic (zero LLM randomness in course sequencing).
   - Primary-skill gating guarantees acyclicity across arbitrary candidate subsets.

---

## 17. Known Non-Blocking Items

The following items were identified and analyzed during audit, but intentionally preserved as non-blocking:
1. **Unused `top_k=8` default in `embeddings.py`**: The `recommend_courses_async` function defaults to `top_k=8` in its signature, but all production callers (`profile.py` and `roadmap.py`) explicitly pass `top_k=6`. Preserved without modification.
2. **`PrecomputedSkillEmbedder` text lookup**: Internal query strings are synthesized using canonical display names (`Curated courses and practical projects covering: ...`), ensuring reliable embedding lookups without touching unneeded PyTorch dependencies.
3. **`backend/scripts/inspect_neon.py` and `backend/scripts/verify_neon_counts.py`**: Audited as read-only diagnostic utilities created on Day 1 (`2fc2748`) and untouched throughout Day 2 and Day 3.

---

## 18. Final Day 3 State

- **Day 3 Feature Implementation**: Complete and verified across backend, database, and UI.
- **Production Deployment**: Live on Vercel at `https://course-tide.vercel.app/`. Fresh live verification of non-existent UUIDs confirms the active service is serving the real Day 3 404 contract rather than old skeleton stubs.
- **End-to-End User Journey**: Natural language goal → Profile extraction → Phased milestone timeline → Grounded explanation modal dialog.
- **Resilience**: 3-tier active Gemini fallback chain in production (`gemini-3.7-flash` → `gemini-3.6-flash` → `gemini-3.5-flash`).
- **Test Suite**: Fully green (`68 passed, 0 failed`).
- **Database Status**: Clean Neon PostgreSQL state with 0 active test learners and 100% intact catalog records (22 skills, 48 courses, 74 course-skills, 10 assessments).
- **Git State**: Branch `main` with commit `92e7c5f`.

---

## 19. Engineering Lessons Learned

1. **Recommendation Relevance $\neq$ Prerequisite Sequencing**: Recommending courses based on semantic match solves *what* is relevant; sequencing courses based on prerequisite DAGs solves *how* to learn. Keeping these stages separate prevents coupling.
2. **Secondary Metadata Can Create Graph Traps**: In multi-skill taxonomies, tagging an advanced course with a foundational secondary skill will create circular dependencies if treated symmetrically. Gating dependencies must be anchored to the course's primary competency.
3. **LLM Availability Requires Multi-Tier Redundancy**: Flash reasoning models experience periodic demand spikes. A deterministic fallback chain across stable releases (`3.7` → `3.6` → `3.5`) transforms fatal 503 errors into transparent recoveries.
4. **Preserving Real Production State Accelerates Debugging**: Retaining the exact production learner `e062cb8a-9605-4b7d-8b66-563b28a82901` enabled instant, direct verification of the deployed fix without consuming additional LLM intake quotas.