from uuid import UUID
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db

router = APIRouter(prefix="/api/roadmap", tags=["Roadmap"])


@router.get("/{learner_id}", response_model=Dict[str, Any])
async def get_roadmap(
    learner_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """GET /api/roadmap/{learner_id}

    Returns phased roadmap with sequenced courses per phase (Day 2).
    """
    return {
        "learner_id": str(learner_id),
        "phases": [],
        "total_estimated_weeks": 0,
        "status": "skeleton_ready",
    }
