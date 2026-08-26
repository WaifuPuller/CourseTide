from uuid import UUID
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db

router = APIRouter(prefix="/api/explain", tags=["Explain"])


@router.get("/{learner_id}/{course_id}", response_model=Dict[str, Any])
async def get_recommendation_explanation(
    learner_id: UUID,
    course_id: str,
    db: AsyncSession = Depends(get_db),
):
    """GET /api/explain/{learner_id}/{course_id}

    Returns grounded explanation for one recommendation (Day 2).
    Uses ONLY structured inputs (skill gap it closes + prerequisite reasoning).
    """
    return {
        "learner_id": str(learner_id),
        "course_id": course_id,
        "explanation": "Grounded explanation module will be integrated in Day 2.",
        "status": "skeleton_ready",
    }
