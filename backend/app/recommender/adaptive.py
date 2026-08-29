"""Deterministic Adaptive Recommender Engine for CourseTide.

Implements rule-based, deterministic closed-loop adaptation without external LLMs.
Checkpoint 2 Scope: Demonstrating mastery (> 85.0) fast-tracks matching competency courses.
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
class MasteryAdaptationResult:
    mastery_triggered: bool
    mastered_skill: Optional[str] = None
    skipped_course_id: Optional[str] = None
    adaptation_applied: str = "none"  # "none" | "mastery" | "mastery_skip"
    message: str = "Progress event recorded successfully."


async def evaluate_mastery_and_fast_track(
    db: AsyncSession,
    learner: Learner,
    completed_lp: LearningPath,
    assessment_score: float,
    all_learning_paths: List[LearningPath],
) -> MasteryAdaptationResult:
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
        return MasteryAdaptationResult(
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
        return MasteryAdaptationResult(
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
        return MasteryAdaptationResult(
            mastery_triggered=True,
            mastered_skill=primary_skill,
            skipped_course_id=skipped_course_id,
            adaptation_applied="mastery_skip",
            message=f"Mastery demonstrated in {primary_skill}. Fast-tracked redundant course '{skipped_course_id}'.",
        )
    else:
        return MasteryAdaptationResult(
            mastery_triggered=True,
            mastered_skill=primary_skill,
            skipped_course_id=None,
            adaptation_applied="mastery",
            message=f"Mastery demonstrated in {primary_skill}. Competency marked as known.",
        )