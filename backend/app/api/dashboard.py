from uuid import UUID
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/{learner_id}", response_model=Dict[str, Any])
async def get_dashboard(
    learner_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """GET /api/dashboard/{learner_id}

    Returns progress %, skill mastery states, next recommended action (Day 2).
    """
    return {
        "learner_id": str(learner_id),
        "overall_progress_percentage": 0.0,
        "mastered_skills": [],
        "in_progress_skills": [],
        "gap_skills": [],
        "next_action": None,
        "status": "skeleton_ready",
    }
