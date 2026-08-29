"""Deterministic Adaptive Recommender Engine for CourseTide.

Implements rule-based, deterministic closed-loop adaptation without external LLMs.
Checkpoint 2: Demonstrating mastery (> 85.0) fast-tracks matching competency courses.
Checkpoint 3: Score < 50.0 inserts strictly lower-difficulty remedial course and shifts sequence.
"""

from dataclasses import dataclass
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.app.models import Course, CourseSkill, Learner, LearnerSkill, LearningPath

DIFFICULTY_ORDER = {
    "beginner": 1,
    "intermediate": 2,
    "advanced": 3,
}


@dataclass
class AdaptationResult:
    mastery_triggered: bool = False
    remediation_triggered: bool = False
    mastered_skill: Optional[str] = None
    weak_skill: Optional[str] = None
    skipped_course_id: Optional[str] = None
    inserted_course_id: Optional[str] = None
    adaptation_applied: str = "none"  # "none" | "mastery" | "mastery_skip" | "remediation"
    message: str = "Progress event recorded successfully."


# Backward-compatible alias
MasteryAdaptationResult = AdaptationResult


async def evaluate_mastery_and_fast_track(
    db: AsyncSession,
    learner: Learner,
    completed_lp: LearningPath,
    assessment_score: float,
    all_learning_paths: List[LearningPath],
) -> AdaptationResult:
    """Evaluates score > 85.0 deterministic fast-track mastery rule.

    1. Checks if assessment_score > 85.0 (strictly greater).
    2. Identifies primary skill of completed course.
    3. Updates learner_skills (status = 'known', mastery_score = max(existing, new)).
    4. Updates learner.parsed_goal (add to known_skills, remove from gap_skills).
    5. Searches upcoming courses in roadmap with status in ('locked', 'available'),
       matching primary skill, and difficulty <= completed course difficulty.
    6. Marks the FIRST qualifying course as 'skipped' without deleting or reordering.
    """
    if assessment_score <= 85.0:
        return AdaptationResult(
            mastery_triggered=False,
            mastered_skill=None,
            skipped_course_id=None,
            adaptation_applied="none",
            message="Progress event recorded successfully.",
        )

    # 1. Identify primary skill of completed course
    stmt_primary = (
        select(CourseSkill.skill_id)
        .where(
            CourseSkill.course_id == completed_lp.course_id,
            CourseSkill.is_primary.is_(True),
        )
    )
    res_primary = await db.execute(stmt_primary)
    primary_skill = res_primary.scalar_one_or_none()

    if not primary_skill:
        return AdaptationResult(
            mastery_triggered=True,
            mastered_skill=None,
            skipped_course_id=None,
            adaptation_applied="none",
            message="Score recorded. No primary skill tagged for course.",
        )

    # 2. Update LearnerSkill for primary skill ONLY
    stmt_ls = select(LearnerSkill).where(
        LearnerSkill.learner_id == learner.id,
        LearnerSkill.skill_id == primary_skill,
    )
    res_ls = await db.execute(stmt_ls)
    learner_skill = res_ls.scalar_one_or_none()

    if learner_skill:
        learner_skill.status = "known"
        existing_mastery = learner_skill.mastery_score or 0.0
        learner_skill.mastery_score = max(existing_mastery, assessment_score)
    else:
        new_ls = LearnerSkill(
            learner_id=learner.id,
            skill_id=primary_skill,
            status="known",
            mastery_score=assessment_score,
        )
        db.add(new_ls)

    # 3. Update parsed_goal JSON
    parsed_goal = dict(learner.parsed_goal or {})
    known_skills = list(parsed_goal.get("known_skills", []))
    gap_skills = list(parsed_goal.get("gap_skills", []))

    if primary_skill not in known_skills:
        known_skills.append(primary_skill)
    if primary_skill in gap_skills:
        gap_skills.remove(primary_skill)

    parsed_goal["known_skills"] = known_skills
    parsed_goal["gap_skills"] = gap_skills
    learner.parsed_goal = parsed_goal
    flag_modified(learner, "parsed_goal")

    # 4. Find completed course difficulty
    stmt_course = select(Course).where(Course.id == completed_lp.course_id)
    res_course = await db.execute(stmt_course)
    completed_course = res_course.scalar_one_or_none()
    completed_diff_rank = DIFFICULTY_ORDER.get(completed_course.difficulty.lower(), 0) if completed_course else 0

    # 5. Search for fast-track target in upcoming courses (later sequence_order)
    upcoming_lps = sorted(
        [
            lp for lp in all_learning_paths
            if lp.sequence_order > completed_lp.sequence_order
            and lp.status in ("locked", "available")
        ],
        key=lambda x: x.sequence_order,
    )

    skipped_course_id: Optional[str] = None
    for cand_lp in upcoming_lps:
        # Check candidate course primary skill
        stmt_cand_primary = (
            select(CourseSkill.skill_id)
            .where(
                CourseSkill.course_id == cand_lp.course_id,
                CourseSkill.is_primary.is_(True),
            )
        )
        res_cand_primary = await db.execute(stmt_cand_primary)
        cand_primary_skill = res_cand_primary.scalar_one_or_none()

        if cand_primary_skill != primary_skill:
            continue

        # Check candidate difficulty <= completed course difficulty
        stmt_cand_course = select(Course).where(Course.id == cand_lp.course_id)
        res_cand_course = await db.execute(stmt_cand_course)
        cand_course = res_cand_course.scalar_one_or_none()
        cand_diff_rank = DIFFICULTY_ORDER.get(cand_course.difficulty.lower(), 0) if cand_course else 0

        if 0 < cand_diff_rank <= completed_diff_rank:
            # Qualifying course found! Mark as skipped
            cand_lp.status = "skipped"
            skipped_course_id = cand_lp.course_id
            break

    if skipped_course_id:
        return AdaptationResult(
            mastery_triggered=True,
            mastered_skill=primary_skill,
            skipped_course_id=skipped_course_id,
            adaptation_applied="mastery_skip",
            message=f"Mastery demonstrated in {primary_skill}. Fast-tracked redundant course '{skipped_course_id}'.",
        )
    else:
        return AdaptationResult(
            mastery_triggered=True,
            mastered_skill=primary_skill,
            skipped_course_id=None,
            adaptation_applied="mastery",
            message=f"Mastery demonstrated in {primary_skill}. Competency marked as known.",
        )


async def evaluate_remediation(
    db: AsyncSession,
    learner: Learner,
    failed_lp: LearningPath,
    assessment_score: float,
    all_learning_paths: List[LearningPath],
) -> AdaptationResult:
    """Evaluates score < 50.0 deterministic remedial insertion rule.

    1. Checks if assessment_score < 50.0 (strictly less than 50.0).
    2. Identifies primary skill of failed course (weak competency).
    3. Finds failed course difficulty rank (beginner=1, intermediate=2, advanced=3).
    4. If failed course is beginner (rank=1) -> no strictly lower difficulty exists -> returns safe fallback.
    5. Queries catalog courses teaching weak_skill with difficulty_rank < failed_diff_rank,
       is_mvp == True, not already in all_learning_paths.
    6. Selects single best candidate via deterministic tie-breaker:
       difficulty DESC (closest lower tier first), duration_hours ASC, id ASC.
    7. Inserts candidate into learning_paths at sequence_order = failed_lp.sequence_order + 1,
       phase_number = failed_lp.phase_number, status = 'available'.
    8. Shifts all subsequent learning_paths with sequence_order >= insert_pos by +1.
    """
    if assessment_score >= 50.0:
        return AdaptationResult(
            remediation_triggered=False,
            adaptation_applied="none",
            message="Progress event recorded successfully.",
        )

    # 1. Identify primary skill of failed course
    stmt_primary = (
        select(CourseSkill.skill_id)
        .where(
            CourseSkill.course_id == failed_lp.course_id,
            CourseSkill.is_primary.is_(True),
        )
    )
    res_primary = await db.execute(stmt_primary)
    weak_skill = res_primary.scalar_one_or_none()

    if not weak_skill:
        return AdaptationResult(
            remediation_triggered=True,
            adaptation_applied="none",
            message="Score recorded. No primary skill tagged for course.",
        )

    # 2. Update LearnerSkill (mark/keep status='gap')
    stmt_ls = select(LearnerSkill).where(
        LearnerSkill.learner_id == learner.id,
        LearnerSkill.skill_id == weak_skill,
    )
    res_ls = await db.execute(stmt_ls)
    learner_skill = res_ls.scalar_one_or_none()
    if learner_skill:
        if learner_skill.status != "known":
            learner_skill.status = "gap"
    else:
        new_ls = LearnerSkill(
            learner_id=learner.id,
            skill_id=weak_skill,
            status="gap",
            mastery_score=assessment_score,
        )
        db.add(new_ls)

    # 3. Find failed course difficulty
    stmt_course = select(Course).where(Course.id == failed_lp.course_id)
    res_course = await db.execute(stmt_course)
    failed_course = res_course.scalar_one_or_none()
    failed_diff_rank = DIFFICULTY_ORDER.get(failed_course.difficulty.lower(), 0) if failed_course else 0

    if failed_diff_rank <= 1:
        # Beginner course failed: no strictly lower difficulty candidate exists
        return AdaptationResult(
            remediation_triggered=True,
            weak_skill=weak_skill,
            inserted_course_id=None,
            adaptation_applied="none",
            message=f"Score recorded. No strictly lower introductory course available for beginner competency '{weak_skill}'.",
        )

    # 4. Query candidate remedial courses teaching weak_skill with strictly lower difficulty
    enrolled_course_ids = {lp.course_id for lp in all_learning_paths}

    stmt_candidates = (
        select(Course)
        .join(CourseSkill, Course.id == CourseSkill.course_id)
        .where(
            CourseSkill.skill_id == weak_skill,
            Course.is_mvp.is_(True),
        )
    )
    res_candidates = await db.execute(stmt_candidates)
    candidates = res_candidates.scalars().all()

    qualifying_candidates = []
    for cand in candidates:
        if cand.id in enrolled_course_ids:
            continue
        cand_diff_rank = DIFFICULTY_ORDER.get(cand.difficulty.lower(), 0)
        if 0 < cand_diff_rank < failed_diff_rank:
            qualifying_candidates.append(cand)

    if not qualifying_candidates:
        return AdaptationResult(
            remediation_triggered=True,
            weak_skill=weak_skill,
            inserted_course_id=None,
            adaptation_applied="none",
            message=f"Score recorded. No lower-difficulty remedial course available for '{weak_skill}'.",
        )

    # 5. Deterministic tie-breaker:
    # Closest lower difficulty first (-diff_rank), shortest duration (+duration_hours), then id ASC
    qualifying_candidates.sort(
        key=lambda c: (-DIFFICULTY_ORDER.get(c.difficulty.lower(), 0), c.duration_hours, c.id)
    )
    selected_remedial = qualifying_candidates[0]

    # 6. Insert position and sequence shifting
    insert_pos = failed_lp.sequence_order + 1
    insert_phase = failed_lp.phase_number

    # Shift all subsequent learning paths with sequence_order >= insert_pos by +1
    for lp in all_learning_paths:
        if lp.sequence_order >= insert_pos:
            lp.sequence_order += 1

    # Create new remedial LearningPath row
    remedial_lp = LearningPath(
        learner_id=learner.id,
        course_id=selected_remedial.id,
        phase_number=insert_phase,
        sequence_order=insert_pos,
        status="available",
    )
    db.add(remedial_lp)
    all_learning_paths.append(remedial_lp)

    return AdaptationResult(
        remediation_triggered=True,
        weak_skill=weak_skill,
        inserted_course_id=selected_remedial.id,
        adaptation_applied="remediation",
        message=f"Remedial course '{selected_remedial.id}' added to support competency in {weak_skill}.",
    )