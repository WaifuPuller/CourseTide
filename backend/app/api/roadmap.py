"""Roadmap API endpoint for CourseTide.

Retrieves a learner's parsed profile, feeds candidate recommended courses into the
prerequisite path sequencer, persists phased milestones to learning_paths, and
returns the structured roadmap.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import Course, Learner, LearningPath
from backend.app.recommender.embeddings import recommend_courses_async
from backend.app.recommender.path_sequencer import SequencedRoadmap, sequence_courses

router = APIRouter(prefix="/api/roadmap", tags=["Roadmap"])


class RoadmapCourseResponse(BaseModel):
    course_id: str
    title: str
    difficulty: str
    duration_hours: int
    domain: str
    source: Optional[str] = None
    url: Optional[str] = None
    primary_skill: Optional[str] = None
    covered_skills: List[str] = Field(default_factory=list)
    phase_number: int
    sequence_order: int
    status: str
    match_score: Optional[float] = None


class RoadmapPhaseResponse(BaseModel):
    phase_number: int
    phase_name: str
    skills: List[str] = Field(default_factory=list)
    courses: List[RoadmapCourseResponse] = Field(default_factory=list)
    estimated_hours: int


class RoadmapResponse(BaseModel):
    learner_id: UUID
    target_role: str
    role_name: str
    total_courses: int
    total_estimated_hours: int
    total_estimated_weeks: int
    phases: List[RoadmapPhaseResponse]


@router.get("/{learner_id}", response_model=RoadmapResponse)
async def get_roadmap(
    learner_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """GET /api/roadmap/{learner_id}

    1. Retrieves learner by UUID (returns 404 if not found).
    2. Extracts known and gap skills from parsed_goal.
    3. Handles zero-gap learners with an empty roadmap response.
    4. Generates recommended candidate courses using Day 2 recommender.
    5. Sequentially orders courses and groups into phases via path_sequencer.
    6. Persists generated LearningPath records transactionally (if not already existing).
    7. Returns phased milestone roadmap.
    """
    # 1. Look up learner by ID
    stmt = select(Learner).where(Learner.id == learner_id)
    res = await db.execute(stmt)
    learner = res.scalar_one_or_none()

    if not learner:
        raise HTTPException(
            status_code=404,
            detail=f"Learner with ID '{learner_id}' not found.",
        )

    # 2. Extract profile attributes from parsed_goal
    parsed_goal = learner.parsed_goal or {}
    target_role = parsed_goal.get("target_role", "ml_engineer")
    role_name = parsed_goal.get("role_name", "Machine Learning Engineer")
    known_skills = parsed_goal.get("known_skills", [])
    gap_skills = parsed_goal.get("gap_skills", [])
    weekly_hours = learner.weekly_hours or parsed_goal.get("weekly_hours", 8)

    # 3. Handle zero-gap case gracefully
    if not gap_skills:
        return RoadmapResponse(
            learner_id=learner_id,
            target_role=target_role,
            role_name=role_name,
            total_courses=0,
            total_estimated_hours=0,
            total_estimated_weeks=0,
            phases=[],
        )

    # 4. Retrieve recommended candidate courses (Day 2 recommender)
    embed_model = getattr(request.app.state, "embed_model", None) if hasattr(request.app, "state") else None
    recommended_courses = await recommend_courses_async(
        db=db,
        gap_skills=gap_skills,
        top_k=6,
        embed_model=embed_model,
    )

    # 5. Order courses topologically and group into phases
    sequenced: SequencedRoadmap = sequence_courses(
        courses=recommended_courses,
        known_skills=known_skills,
        weekly_hours=weekly_hours,
    )

    # 6. Idempotently persist LearningPath records if not already created
    existing_lp_stmt = select(LearningPath).where(LearningPath.learner_id == learner_id)
    existing_lp_res = await db.execute(existing_lp_stmt)
    existing_lps = existing_lp_res.scalars().all()

    if not existing_lps and sequenced.phases:
        for phase in sequenced.phases:
            for course in phase.courses:
                lp = LearningPath(
                    learner_id=learner_id,
                    phase_number=course.phase_number,
                    course_id=course.course_id,
                    status=course.status,
                    sequence_order=course.sequence_order,
                )
                db.add(lp)

        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Failed to persist learning path records due to a database error.",
            )

    # 7. Convert to response model
    phase_responses: List[RoadmapPhaseResponse] = []
    for p in sequenced.phases:
        course_responses = [
            RoadmapCourseResponse(
                course_id=c.course_id,
                title=c.title,
                difficulty=c.difficulty,
                duration_hours=c.duration_hours,
                domain=c.domain,
                source=c.source,
                url=c.url,
                primary_skill=c.primary_skill,
                covered_skills=c.covered_skills,
                phase_number=c.phase_number,
                sequence_order=c.sequence_order,
                status=c.status,
                match_score=c.match_score,
            )
            for c in p.courses
        ]
        phase_responses.append(
            RoadmapPhaseResponse(
                phase_number=p.phase_number,
                phase_name=p.phase_name,
                skills=p.skills,
                courses=course_responses,
                estimated_hours=p.estimated_hours,
            )
        )

    return RoadmapResponse(
        learner_id=learner_id,
        target_role=target_role,
        role_name=role_name,
        total_courses=sequenced.total_courses,
        total_estimated_hours=sequenced.total_estimated_hours,
        total_estimated_weeks=sequenced.total_estimated_weeks,
        phases=phase_responses,
    )
