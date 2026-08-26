# CourseTide Data Dictionary

| File | Field | Meaning |
|---|---|---|
| courses.csv | id | Stable CourseTide resource identifier |
| courses.csv | title | Resource title |
| courses.csv | description | CourseTide-authored catalog summary |
| courses.csv | skills | Pipe-separated skill IDs taught by the resource |
| courses.csv | difficulty | beginner / intermediate / advanced |
| courses.csv | duration_hours | Estimated learning time from the original catalog |
| courses.csv | resource_type | course / project |
| courses.csv | domain | ml / web |
| courses.csv | is_mvp | Whether the resource is in the default solo MVP track |
| courses.csv | source | Original provider/source from the supplied dataset |
| courses.csv | url | Original resource URL from the supplied dataset |
| courses.csv | learning_outcomes | CourseTide-authored skill outcome summary |
| course_skills.csv | course_id | FK to courses.id |
| course_skills.csv | skill_id | FK to skills.id |
| course_skills.csv | is_primary | Main sequencing/display skill |
| target_roles.json | required_skills | Core skills expected for the role |
| target_roles.json | recommended_optional_skills | Useful but non-essential skills |
| assessments.json | pass_score | Minimum passing score |
| assessments.json | mastery_score | Score threshold used by the adaptive loop for mastery |
