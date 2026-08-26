from uuid import UUID
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db

router = APIRouter(prefix="/api/skill-gap", tags=["Skill Gap"])


@router.get("/{learner_id}", response_model=Dict[str, Any])
async def get_skill_gap(
    learner_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """GET /api/skill-gap/{learner_id}

    Returns skill gap list for the learner's target role (Day 2).
    """
    return {
        "learner_id": str(learner_id),
        "target_role": None,
        "required_skills": [],
        "known_skills": [],
        "gap_skills": [],
        "status": "skeleton_ready",
    }
