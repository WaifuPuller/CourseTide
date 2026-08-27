from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.app.database import get_db
from backend.app.models import Learner, LearnerSkill
from backend.app.recommender.skill_gap import TARGET_ROLES, detect_skill_gaps

router = APIRouter(prefix="/api/skill-gap", tags=["Skill Gap"])


class SkillGapResponse(BaseModel):
    learner_id: UUID
    target_role: str
    role_name: str
    required_skills: List[str]
    known_skills: List[str]
    gap_skills: List[str]
    recommended_optional_skills: List[str]
    total_required_count: int
    known_count: int
    gap_count: int
    match_percentage: float


@router.get("/{learner_id}", response_model=SkillGapResponse)
async def get_skill_gap(
    learner_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """GET /api/skill-gap/{learner_id}

    Returns skill gap list for the learner's target role.
    """
    stmt = (
        select(Learner)
        .where(Learner.id == learner_id)
        .options(joinedload(Learner.learner_skills))
    )
    result = await db.execute(stmt)
    learner = result.scalars().unique().one_or_none()

    if not learner:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found.")

    parsed_goal = learner.parsed_goal or {}
    target_role = parsed_goal.get("target_role", "ml_engineer")

    # Extract known skills from learner_skills
    known_skills = [ls.skill_id for ls in learner.learner_skills if ls.status == "known"]
    if not known_skills and "known_skills" in parsed_goal:
        known_skills = parsed_goal["known_skills"]

    gap_result = detect_skill_gaps(target_role=target_role, known_skills=known_skills)

    return SkillGapResponse(
        learner_id=learner.id,
        target_role=gap_result.target_role,
        role_name=gap_result.role_name,
        required_skills=gap_result.required_skills,
        known_skills=gap_result.known_skills,
        gap_skills=gap_result.gap_skills,
        recommended_optional_skills=gap_result.recommended_optional_skills,
        total_required_count=gap_result.total_required_count,
        known_count=gap_result.known_count,
        gap_count=gap_result.gap_count,
        match_percentage=gap_result.match_percentage,
    )
