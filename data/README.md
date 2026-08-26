# CourseTide Learning Data Pack

This folder contains the curated seed data used by CourseTide. The catalog is intentionally small enough for the solo MVP while supporting semantic recommendation, prerequisite sequencing, and adaptive assessments.

## Files

- `courses.csv` — 48 curated learning resources. Includes IDs, descriptions, multi-skill mappings, difficulty, duration, domain, source, URL, and MVP flag.
- `course_skills.csv` — normalized many-to-many bridge used to seed `course_skills`.
- `course_prerequisites.csv` — prerequisite skills derived from the skill prerequisite graph, for reference/documentation only. **Do not use this for roadmap gating** — some entries inherit full upstream skill chains (including loosely-related secondary skills) and can produce illogical prerequisite chains. Sequencing must come from `prerequisites.json` + `course_skills.csv` (`is_primary`).
- `skills.json` — skill taxonomy with domain and recommended entry level.
- `prerequisites.json` — skill-level prerequisite DAG.
- `target_roles.json` — role-to-skill maps used by the skill-gap engine.
- `assessments.json` — assessment definitions supporting the adaptive loop.

## MVP track

The intended demo track is Machine Learning/Data. Rows with `is_mvp=true` are the default MVP catalog. Web resources are retained for later expansion.

## Data conventions

- `skills` in `courses.csv` is pipe-separated (`skill_a|skill_b|...`).
- `course_skills.csv` is the normalized representation for relational seeding.
- `learning_outcomes` is CourseTide-authored catalog metadata derived from the selected skill mappings; it is not an official vendor syllabus.
- Source URLs are preserved from the original compilation and should be checked before public production use.

## Intended ingestion flow

1. Load `skills.json`.
2. Load `target_roles.json` and build the skill-gap engine.
3. Load `courses.csv`.
4. Seed `course_skills.csv` into the many-to-many relationship.
5. Use `prerequisites.json` for skill-level path sequencing.
   `course_prerequisites.csv` is reference/documentation only.
6. Embed a rich text representation such as `title + description + learning_outcomes + skills` into pgvector.
7. Load `assessments.json` for progress and mastery checks.
