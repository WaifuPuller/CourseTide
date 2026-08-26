from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db

router = APIRouter(prefix="/api/progress", tags=["Progress"])


class ProgressEventCreate(BaseModel):
    learner_id: UUID
    course_id: str
    difficulty_feedback: Optional[str] = Field(None, description="'too_easy' | 'just_right' | 'too_hard'")
    assessment_score: Optional[float] = Field(None, ge=0, le=100)


@router.post("", response_model=Dict[str, Any])
async def record_progress_event(
    payload: ProgressEventCreate,
    db: AsyncSession = Depends(get_db),
):
    """POST /api/progress

    Accepts progress_event (difficulty feedback and/or assessment score),
    runs deterministic adaptive loop (Day 2), and updates learning_paths.
    """
    return {
        "learner_id": str(payload.learner_id),
        "course_id": payload.course_id,
        "difficulty_feedback": payload.difficulty_feedback,
        "assessment_score": payload.assessment_score,
        "adaptation": "Adaptive loop will be active in Day 2.",
        "status": "skeleton_ready",
    }
