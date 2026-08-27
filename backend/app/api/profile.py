import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import Learner, LearnerSkill
from backend.app.recommender.embeddings import RecommendedCourse, recommend_courses_async
from backend.app.recommender.goal_parser import GoalParsingError, LLMConfigurationError, parse_goal
from backend.app.recommender.skill_gap import SkillGapError, detect_skill_gaps

router = APIRouter(prefix="/api/profile", tags=["Profile"])


class ProfileCreateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    goal: str = Field(..., description="Natural language career or learning goal", min_length=5)
    weekly_hours: Optional[int] = Field(default=8, ge=1, le=80)


class SkillDetail(BaseModel):
    id: str
    name: str


class ProfileResponse(BaseModel):
    learner_id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    goal: str
    target_role: str
    role_name: str
    weekly_hours: int
    timeframe_months: int
    known_skills: List[str]
    gap_skills: List[str]
    unrecognized_skills: List[str] = Field(default_factory=list)
    match_percentage: float
    recommended_courses: List[RecommendedCourse] = Field(default_factory=list)
    parsed_goal: Optional[Dict[str, Any]] = None


@router.post("", response_model=ProfileResponse)
async def create_or_update_profile(
    payload: ProfileCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """POST /api/profile

    Accepts natural-language goal + weekly_hours:
    1. Parses goal into structured role and known skills (via LLM).
    2. Runs deterministic skill-gap engine.
    3. Generates semantic course recommendations from pgvector embeddings.
    4. Persists learner and learner_skills records in PostgreSQL.
    5. Returns parsed profile, skill gaps, unrecognized skills, and recommendations.
    """
    # 1. Parse goal
    try:
        parsed_goal = parse_goal(
            goal_text=payload.goal,
            default_weekly_hours=payload.weekly_hours,
        )
    except GoalParsingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except LLMConfigurationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error during goal parsing: {str(e)}")

    # 2. Detect skill gaps
    try:
        gap_result = detect_skill_gaps(
            target_role=parsed_goal.target_role,
            known_skills=parsed_goal.known_skills,
        )
    except SkillGapError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    # 3. Recommend courses
    embed_model = getattr(request.app.state, "embed_model", None) if hasattr(request.app, "state") else None
    recommended_courses = await recommend_courses_async(
        db=db,
        gap_skills=gap_result.gap_skills,
        top_k=6,
        embed_model=embed_model,
    )

    # 4. Persist to database
    learner_id = uuid.uuid4()
    parsed_goal_dict = {
        "target_role": parsed_goal.target_role,
        "role_name": gap_result.role_name,
        "known_skills": parsed_goal.known_skills,
        "gap_skills": gap_result.gap_skills,
        "unrecognized_skills": parsed_goal.unrecognized_skills,
        "timeframe_months": parsed_goal.timeframe_months,
        "weekly_hours": parsed_goal.weekly_hours,
        "match_percentage": gap_result.match_percentage,
    }

    learner = Learner(
        id=learner_id,
        name=payload.name,
        email=payload.email,
        goal=payload.goal,
        parsed_goal=parsed_goal_dict,
        weekly_hours=parsed_goal.weekly_hours,
    )
    db.add(learner)

    # Persist learner_skills
    for skill_id in parsed_goal.known_skills:
        ls = LearnerSkill(
            learner_id=learner_id,
            skill_id=skill_id,
            status="known",
            mastery_score=100.0,
        )
        db.add(ls)

    for skill_id in gap_result.gap_skills:
        ls = LearnerSkill(
            learner_id=learner_id,
            skill_id=skill_id,
            status="gap",
            mastery_score=0.0,
        )
        db.add(ls)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to persist learner profile due to an internal database error.",
        )

    return ProfileResponse(
        learner_id=learner_id,
        name=payload.name,
        email=payload.email,
        goal=payload.goal,
        target_role=parsed_goal.target_role,
        role_name=gap_result.role_name,
        weekly_hours=parsed_goal.weekly_hours,
        timeframe_months=parsed_goal.timeframe_months,
        known_skills=parsed_goal.known_skills,
        gap_skills=gap_result.gap_skills,
        unrecognized_skills=parsed_goal.unrecognized_skills,
        match_percentage=gap_result.match_percentage,
        recommended_courses=recommended_courses,
        parsed_goal=parsed_goal_dict,
    )
