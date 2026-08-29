"""Learner Dashboard Data Aggregation API Endpoint.

Implements read-only dashboard aggregation:
- Genuine completion % vs Effective progress %
- Current active phase
- Deterministic Next Recommended Action
- Skill Mastery Radar data from authoritative learner_skills
- Phase-level milestone progression
- Recent progress events audit log
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import Course, CourseSkill, Learner, LearnerSkill, LearningPath, ProgressEvent, Skill

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


class NextRecommendedAction(BaseModel):
    course_id: str
    title: str
    phase_number: int
    sequence_order: int
    status: str  # "available" | "in_progress"
    duration_hours: int
    primary_skill: str
    url: Optional[str] = None


class SkillMasteryRadarItem(BaseModel):
    skill_id: str
    skill_name: str
    status: str  # "known" | "in_progress" | "gap"
    mastery_score: float  # 0.0 to 100.0
    is_required: bool


class PhaseProgressItem(BaseModel):
    phase_number: int
    phase_name: str
    total_courses: int
    completed_courses: int
    skipped_courses: int
    is_unlocked: bool
    estimated_hours: int


class RecentEventItem(BaseModel):
    course_id: str
    course_title: str
    assessment_score: Optional[float] = None
    difficulty_feedback: Optional[str] = None
    timestamp: str


class DashboardResponse(BaseModel):
    learner_id: str
    target_role: str
    role_name: str
    overall_progress_percentage: float  # Genuine completion % (e.g. 16.7)
    effective_progress_percentage: float  # Genuine + Skipped % (e.g. 33.3)
    total_courses: int
    completed_courses: int  # status == 'done'
    skipped_courses: int    # status == 'skipped'
    current_phase_number: int
    current_phase_name: str
    next_recommended_action: Optional[NextRecommendedAction] = None
    skill_mastery_radar: List[SkillMasteryRadarItem]
    phase_progress: List[PhaseProgressItem]
    recent_events: List[RecentEventItem]


@router.get("/{learner_id}", response_model=DashboardResponse)
async def get_dashboard(
    learner_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """GET /api/dashboard/{learner_id}

    Aggregates read-only analytics, skill radar data, milestone progress,
    and the deterministic next recommended action for a given learner.
    """
    # 1. Fetch learner
    stmt_learner = select(Learner).where(Learner.id == learner_id)
    res_learner = await db.execute(stmt_learner)
    learner = res_learner.scalar_one_or_none()
    if not learner:
        raise HTTPException(
            status_code=404,
            detail=f"Learner with ID '{learner_id}' not found.",
        )

    # 2. Extract parsed goal metadata
    parsed_goal = learner.parsed_goal or {}
    target_role = parsed_goal.get("target_role", "custom_role")
    role_name = parsed_goal.get("role_name", target_role.replace("_", " ").title())

    # 3. Fetch learner learning paths
    stmt_lps = (
        select(LearningPath)
        .where(LearningPath.learner_id == learner_id)
        .order_by(LearningPath.phase_number, LearningPath.sequence_order)
    )
    res_lps = await db.execute(stmt_lps)
    learning_paths = res_lps.scalars().all()

    # 4. Fetch referenced courses & primary skills
    course_ids = [lp.course_id for lp in learning_paths]
    courses_map = {}
    course_primary_skills = {}
    if course_ids:
        stmt_courses = select(Course).where(Course.id.in_(course_ids))
        res_courses = await db.execute(stmt_courses)
        for c in res_courses.scalars().all():
            courses_map[c.id] = c

        stmt_cs = (
            select(CourseSkill.course_id, CourseSkill.skill_id)
            .where(CourseSkill.course_id.in_(course_ids), CourseSkill.is_primary.is_(True))
        )
        res_cs = await db.execute(stmt_cs)
        for cid, skid in res_cs.all():
            course_primary_skills[cid] = skid

    # 5. Calculate progress metrics
    total_courses = len(learning_paths)
    completed_courses = sum(1 for lp in learning_paths if lp.status == "done")
    skipped_courses = sum(1 for lp in learning_paths if lp.status == "skipped")

    if total_courses > 0:
        overall_progress_percentage = round((completed_courses / total_courses) * 100.0, 1)
        effective_progress_percentage = round(((completed_courses + skipped_courses) / total_courses) * 100.0, 1)
    else:
        overall_progress_percentage = 0.0
        effective_progress_percentage = 0.0

    # 6. Phase progression
    distinct_phase_numbers = sorted(list({lp.phase_number for lp in learning_paths}))
    phase_progress_list: List[PhaseProgressItem] = []
    current_phase_number = 1
    current_phase_name = "Phase 1"
    found_current_phase = False

    for p_num in distinct_phase_numbers:
        p_courses = [lp for lp in learning_paths if lp.phase_number == p_num]
        p_total = len(p_courses)
        p_completed = sum(1 for lp in p_courses if lp.status == "done")
        p_skipped = sum(1 for lp in p_courses if lp.status == "skipped")
        p_unlocked = any(lp.status in ("available", "in_progress", "done", "skipped") for lp in p_courses)
        p_hours = sum(courses_map[lp.course_id].duration_hours for lp in p_courses if lp.course_id in courses_map)
        p_name = f"Phase {p_num}"

        phase_progress_list.append(
            PhaseProgressItem(
                phase_number=p_num,
                phase_name=p_name,
                total_courses=p_total,
                completed_courses=p_completed,
                skipped_courses=p_skipped,
                is_unlocked=p_unlocked,
                estimated_hours=p_hours,
            )
        )

        if not found_current_phase and (p_completed + p_skipped < p_total):
            current_phase_number = p_num
            current_phase_name = p_name
            found_current_phase = True

    if not found_current_phase and distinct_phase_numbers:
        current_phase_number = distinct_phase_numbers[-1]
        current_phase_name = f"Phase {current_phase_number}"

    # 7. Deterministic Next Recommended Action Selection
    # Priority: 1. in_progress, 2. available, 3. None
    candidate_lp = next((lp for lp in learning_paths if lp.status == "in_progress"), None)
    if not candidate_lp:
        candidate_lp = next((lp for lp in learning_paths if lp.status == "available"), None)

    next_action: Optional[NextRecommendedAction] = None
    if candidate_lp and candidate_lp.course_id in courses_map:
        c = courses_map[candidate_lp.course_id]
        pskill = course_primary_skills.get(c.id, "")
        next_action = NextRecommendedAction(
            course_id=c.id,
            title=c.title,
            phase_number=candidate_lp.phase_number,
            sequence_order=candidate_lp.sequence_order,
            status=candidate_lp.status,
            duration_hours=c.duration_hours,
            primary_skill=pskill,
            url=c.url,
        )

    # 8. Skill Mastery Radar Data
    stmt_ls = select(LearnerSkill).where(LearnerSkill.learner_id == learner_id)
    res_ls = await db.execute(stmt_ls)
    learner_skills = res_ls.scalars().all()

    skill_ids = [ls.skill_id for ls in learner_skills]
    skill_names = {}
    if skill_ids:
        stmt_skills = select(Skill).where(Skill.id.in_(skill_ids))
        res_skills = await db.execute(stmt_skills)
        for s in res_skills.scalars().all():
            skill_names[s.id] = s.name

    skill_mastery_radar: List[SkillMasteryRadarItem] = []
    for ls in learner_skills:
        s_name = skill_names.get(ls.skill_id, ls.skill_id.replace("_", " ").title())
        if ls.mastery_score is not None:
            m_score = ls.mastery_score
        elif ls.status == "known":
            m_score = 100.0
        else:
            m_score = 0.0

        skill_mastery_radar.append(
            SkillMasteryRadarItem(
                skill_id=ls.skill_id,
                skill_name=s_name,
                status=ls.status,
                mastery_score=m_score,
                is_required=True,
            )
        )

    # 9. Recent Progress Events
    stmt_events = (
        select(ProgressEvent)
        .where(ProgressEvent.learner_id == learner_id)
        .order_by(ProgressEvent.timestamp.desc())
        .limit(10)
    )
    res_events = await db.execute(stmt_events)
    events = res_events.scalars().all()

    event_course_ids = [e.course_id for e in events if e.course_id not in courses_map]
    if event_course_ids:
        stmt_ec = select(Course).where(Course.id.in_(event_course_ids))
        res_ec = await db.execute(stmt_ec)
        for c in res_ec.scalars().all():
            courses_map[c.id] = c

    recent_events: List[RecentEventItem] = []
    for e in events:
        c_title = courses_map[e.course_id].title if e.course_id in courses_map else e.course_id
        recent_events.append(
            RecentEventItem(
                course_id=e.course_id,
                course_title=c_title,
                assessment_score=e.assessment_score,
                difficulty_feedback=e.difficulty_feedback,
                timestamp=e.timestamp.isoformat() if e.timestamp else "",
            )
        )

    return DashboardResponse(
        learner_id=str(learner.id),
        target_role=target_role,
        role_name=role_name,
        overall_progress_percentage=overall_progress_percentage,
        effective_progress_percentage=effective_progress_percentage,
        total_courses=total_courses,
        completed_courses=completed_courses,
        skipped_courses=skipped_courses,
        current_phase_number=current_phase_number,
        current_phase_name=current_phase_name,
        next_recommended_action=next_action,
        skill_mastery_radar=skill_mastery_radar,
        phase_progress=phase_progress_list,
        recent_events=recent_events,
    )