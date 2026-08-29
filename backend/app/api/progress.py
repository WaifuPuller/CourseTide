from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import Course, Learner, LearningPath, ProgressEvent

router = APIRouter(prefix="/api/progress", tags=["Progress"])


class DifficultyFeedback(str, Enum):
    too_easy = "too_easy"
    just_right = "just_right"
    too_hard = "too_hard"


class ProgressEventCreate(BaseModel):
    learner_id: UUID
    course_id: str
    difficulty_feedback: Optional[DifficultyFeedback] = None
    assessment_score: Optional[float] = Field(None, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def check_at_least_one(self) -> "ProgressEventCreate":
        if self.difficulty_feedback is None and self.assessment_score is None:
            raise ValueError("At least one of 'difficulty_feedback' or 'assessment_score' must be provided.")
        return self


class AdaptationDetails(BaseModel):
    message: str
    mastered_skill: Optional[str] = None
    skipped_course_id: Optional[str] = None
    inserted_course_id: Optional[str] = None


class ProgressResponse(BaseModel):
    event_id: UUID
    learner_id: UUID
    course_id: str
    status: str = "success"
    course_status: str
    adaptation_applied: str = "none"
    adaptation_details: AdaptationDetails


@router.post("", response_model=ProgressResponse)
async def record_progress_event(
    payload: ProgressEventCreate,
    db: AsyncSession = Depends(get_db),
) -> ProgressResponse:
    """POST /api/progress

    Records a learner's progress event (assessment score and/or difficulty feedback),
    updates course completion status (if numeric score provided), and triggers
    phase unlocking when all courses in a milestone phase are completed.
    """
    try:
        # 1. Look up learner (lock learner row if supported)
        stmt_learner = select(Learner).where(Learner.id == payload.learner_id).with_for_update()
        learner_res = await db.execute(stmt_learner)
        learner = learner_res.scalar_one_or_none()
        if not learner:
            raise HTTPException(
                status_code=404,
                detail=f"Learner with ID '{payload.learner_id}' not found.",
            )

        # 2. Look up all LearningPath records for this learner
        stmt_lp = (
            select(LearningPath)
            .where(LearningPath.learner_id == payload.learner_id)
            .order_by(LearningPath.phase_number, LearningPath.sequence_order)
        )
        lp_res = await db.execute(stmt_lp)
        learning_paths = lp_res.scalars().all()

        # 3. Validate course is in the learner's active roadmap
        target_lp = next((lp for lp in learning_paths if lp.course_id == payload.course_id), None)
        if not target_lp:
            raise HTTPException(
                status_code=400,
                detail=f"Course '{payload.course_id}' is not in the learner's active roadmap.",
            )

        # 4. Insert ProgressEvent record (immutable historical audit log)
        event = ProgressEvent(
            learner_id=payload.learner_id,
            course_id=payload.course_id,
            difficulty_feedback=payload.difficulty_feedback.value if payload.difficulty_feedback else None,
            assessment_score=payload.assessment_score,
        )
        db.add(event)

        # 5. Course Completion & Phase Unlock (Checkpoint 1 rules)
        if payload.assessment_score is not None:
            # Mark the course as done
            target_lp.status = "done"

            # Check if all courses in the current phase are satisfied ('done' or 'skipped')
            current_phase_num = target_lp.phase_number
            current_phase_courses = [lp for lp in learning_paths if lp.phase_number == current_phase_num]
            phase_satisfied = all(lp.status in ("done", "skipped") for lp in current_phase_courses)

            if phase_satisfied:
                # Unlock immediate next phase (Phase N + 1)
                next_phase_courses = [lp for lp in learning_paths if lp.phase_number == current_phase_num + 1]
                for n_lp in next_phase_courses:
                    if n_lp.status == "locked":
                        n_lp.status = "available"

        # 6. Commit atomic transaction
        await db.commit()
        await db.refresh(event)

    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record progress event due to an internal database error.",
        ) from exc

    return ProgressResponse(
        event_id=event.id,
        learner_id=payload.learner_id,
        course_id=payload.course_id,
        status="success",
        course_status=target_lp.status,
        adaptation_applied="none",
        adaptation_details=AdaptationDetails(
            message="Progress event recorded successfully.",
            mastered_skill=None,
            skipped_course_id=None,
            inserted_course_id=None,
        ),
    )
