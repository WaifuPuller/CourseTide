from typing import Any, Dict, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db

router = APIRouter(prefix="/api/profile", tags=["Profile"])


class ProfileCreateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    goal: str = Field(..., description="Natural language career or learning goal", min_length=3)
    weekly_hours: Optional[int] = Field(default=8, ge=1, le=80)


class ProfileResponse(BaseModel):
    id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    goal: str
    target_role: Optional[str] = None
    known_skills: List[str] = []
    weekly_hours: int
    parsed_goal: Optional[Dict[str, Any]] = None


@router.post("", response_model=Dict[str, Any])
async def create_or_update_profile(
    payload: ProfileCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """POST /api/profile

    Accepts free-text goal + weekly_hours, runs goal_parser.py (Day 2),
    creates/updates a learner, and returns the parsed profile.
    """
    return {
        "message": "Endpoint ready for Day 2 recommender integration",
        "input_goal": payload.goal,
        "weekly_hours": payload.weekly_hours,
        "status": "skeleton_ready",
    }
