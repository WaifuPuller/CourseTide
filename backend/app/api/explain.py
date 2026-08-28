"""Grounded Explanation API endpoint for CourseTide.

Provides transparent, 2-3 sentence AI explanations for why a specific course was
recommended and placed into its roadmap phase, using an ordered Gemini model fallback chain.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.database import get_db
from backend.app.models import Course, CourseSkill, Learner, LearningPath
from backend.app.recommender.explainer import (
    ExplanationContext,
    ExplanationError,
    ExplanationUnavailableError,
    generate_explanation_async,
)
from backend.app.recommender.path_sequencer import (
    PREREQUISITES_DAG,
    calculate_skill_depths,
    get_phase_name,
)

router = APIRouter(prefix="/api/explain", tags=["Explain"])


class ExplanationResponse(BaseModel):
    learner_id: UUID
    course_id: str
    course_title: str
    primary_skill: str
    phase_number: int
    phase_name: str
    explanation: str


@router.get("/{learner_id}/{course_id}", response_model=ExplanationResponse)
async def get_recommendation_explanation(
    learner_id: UUID,
    course_id: str,
    db: AsyncSession = Depends(get_db),
):
    """GET /api/explain/{learner_id}/{course_id}

    Returns a grounded explanation for why a specific course was recommended and
    why it is placed in its particular roadmap phase.
    """
    # 1. Fetch learner
    learner_stmt = select(Learner).where(Learner.id == learner_id)
    learner_res = await db.execute(learner_stmt)
    learner = learner_res.scalar_one_or_none()

    if not learner:
        raise HTTPException(
            status_code=404,
            detail=f"Learner with ID '{learner_id}' not found.",
        )

    # 2. Fetch course with skill_associations
    course_stmt = (
        select(Course)
        .where(Course.id == course_id)
        .options(selectinload(Course.skill_associations))
    )
    course_res = await db.execute(course_stmt)
    course = course_res.scalar_one_or_none()

    if not course:
        raise HTTPException(
            status_code=404,
            detail=f"Course with ID '{course_id}' not found.",
        )

    # 3. Determine course skills and primary skill
    primary_skill: Optional[str] = None
    all_course_skills: List[str] = []

    for cs in (course.skill_associations or []):
        all_course_skills.append(cs.skill_id)
        if cs.is_primary:
            primary_skill = cs.skill_id

    if not primary_skill and all_course_skills:
        primary_skill = all_course_skills[0]
    elif not primary_skill:
        primary_skill = "general"

    # 4. Extract learner profile attributes
    parsed_goal = learner.parsed_goal or {}
    target_role = parsed_goal.get("target_role", "ml_engineer")
    role_name = parsed_goal.get("role_name", "Machine Learning Engineer")
    known_skills = parsed_goal.get("known_skills", [])
    gap_skills = parsed_goal.get("gap_skills", [])

    covered_gap_skills = [s for s in all_course_skills if s in gap_skills]
    if not covered_gap_skills:
        covered_gap_skills = [primary_skill]

    # 5. Determine roadmap phase
    lp_stmt = select(LearningPath).where(
        LearningPath.learner_id == learner_id,
        LearningPath.course_id == course_id,
    )
    lp_res = await db.execute(lp_stmt)
    lp = lp_res.scalar_one_or_none()

    if lp:
        phase_number = lp.phase_number
    else:
        # If not yet persisted, compute phase from prerequisite depth
        depths = calculate_skill_depths([primary_skill], known_skills=known_skills)
        phase_number = 1 + depths.get(primary_skill, 0)

    phase_name = get_phase_name(phase_number)

    # 6. Determine upstream prerequisites and downstream unlocked skills
    upstream_prereqs = PREREQUISITES_DAG.get(primary_skill, [])
    downstream_skills = [
        s for s, prereqs in PREREQUISITES_DAG.items()
        if primary_skill in prereqs and s in gap_skills
    ]

    # 7. Construct ExplanationContext
    context = ExplanationContext(
        learner_id=str(learner_id),
        target_role=target_role,
        role_name=role_name,
        known_skills=known_skills,
        gap_skills=gap_skills,
        course_id=course.id,
        course_title=course.title,
        difficulty=course.difficulty or "intermediate",
        duration_hours=course.duration_hours or 10,
        primary_skill=primary_skill,
        covered_gap_skills=covered_gap_skills,
        phase_number=phase_number,
        phase_name=phase_name,
        upstream_prerequisites=upstream_prereqs,
        downstream_skills=downstream_skills,
    )

    # 8. Generate grounded explanation via Gemini fallback chain
    try:
        explanation = await generate_explanation_async(context)
    except ExplanationUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="Explanation service is temporarily unavailable. Please try again.",
        )
    except ExplanationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error generating explanation: {str(e)}",
        )

    return ExplanationResponse(
        learner_id=learner_id,
        course_id=course.id,
        course_title=course.title,
        primary_skill=primary_skill,
        phase_number=phase_number,
        phase_name=phase_name,
        explanation=explanation,
    )
