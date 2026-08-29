"""Unit and integration tests for Learner Dashboard Analytics Aggregation API.

Checkpoint 4 Scope:
- GET /api/dashboard/{learner_id} read-only endpoint.
- Genuine completion % (done / total * 100) vs Effective progress % ((done + skipped) / total * 100).
- Deterministic Next Recommended Action selection (in_progress > available > None).
- Authoritative Skill Mastery Radar values from learner_skills.
- Phase-level completion status and milestone aggregation.
- Immutable read-only invariant (zero database mutations on GET).
"""

import asyncio
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import Course, CourseSkill, Learner, LearnerSkill, LearningPath, ProgressEvent, Skill

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def make_request(method: str, url: str, json_payload: dict = None):
    """Helper to run async client synchronously in test cases."""
    async def _do():
        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            if method.lower() == "get":
                return await client.get(url)
            elif method.lower() == "post":
                return await client.post(url, json=json_payload)
    return asyncio.run(_do())


async def _setup_dashboard_test_db():
    """Setup minimal catalog and learner fixtures for dashboard tests."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        # 1. Skills
        s1 = Skill(id="python", name="Python Programming", domain="ml")
        s2 = Skill(id="ml_fund", name="Machine Learning Fundamentals", domain="ml")
        s3 = Skill(id="deep_learning", name="Deep Learning", domain="ml")
        session.add_all([s1, s2, s3])

        # 2. Courses (6 courses total)
        c1 = Course(id="c1", title="Course 1", difficulty="beginner", duration_hours=5, resource_type="course", domain="ml", is_mvp=True, url="https://course1.test")
        c2 = Course(id="c2", title="Course 2", difficulty="intermediate", duration_hours=10, resource_type="course", domain="ml", is_mvp=True)
        c3 = Course(id="c3", title="Course 3", difficulty="intermediate", duration_hours=8, resource_type="course", domain="ml", is_mvp=True)
        c4 = Course(id="c4", title="Course 4", difficulty="advanced", duration_hours=12, resource_type="course", domain="ml", is_mvp=True)
        c5 = Course(id="c5", title="Course 5", difficulty="intermediate", duration_hours=6, resource_type="course", domain="ml", is_mvp=True)
        c6 = Course(id="c6", title="Course 6", difficulty="advanced", duration_hours=14, resource_type="course", domain="ml", is_mvp=True)
        session.add_all([c1, c2, c3, c4, c5, c6])

        # 3. CourseSkills
        cs1 = CourseSkill(course_id="c1", skill_id="python", is_primary=True)
        cs2 = CourseSkill(course_id="c2", skill_id="ml_fund", is_primary=True)
        cs3 = CourseSkill(course_id="c3", skill_id="ml_fund", is_primary=True)
        cs4 = CourseSkill(course_id="c4", skill_id="deep_learning", is_primary=True)
        cs5 = CourseSkill(course_id="c5", skill_id="deep_learning", is_primary=True)
        cs6 = CourseSkill(course_id="c6", skill_id="deep_learning", is_primary=True)
        session.add_all([cs1, cs2, cs3, cs4, cs5, cs6])

        # 4. Learner
        learner_id = uuid.uuid4()
        learner = Learner(
            id=learner_id,
            name="Alice ML",
            email="alice@coursetide.test",
            goal="Become an ML Engineer",
            weekly_hours=10,
            parsed_goal={
                "target_role": "ml_engineer",
                "role_name": "Machine Learning Engineer",
                "known_skills": ["python"],
                "gap_skills": ["ml_fund", "deep_learning"],
            },
        )
        session.add(learner)

        # 5. LearningPath (6 courses across 3 phases)
        # Phase 1: c1, c2
        lp1 = LearningPath(learner_id=learner_id, course_id="c1", phase_number=1, sequence_order=1, status="available")
        lp2 = LearningPath(learner_id=learner_id, course_id="c2", phase_number=1, sequence_order=2, status="available")
        # Phase 2: c3, c4
        lp3 = LearningPath(learner_id=learner_id, course_id="c3", phase_number=2, sequence_order=3, status="locked")
        lp4 = LearningPath(learner_id=learner_id, course_id="c4", phase_number=2, sequence_order=4, status="locked")
        # Phase 3: c5, c6
        lp5 = LearningPath(learner_id=learner_id, course_id="c5", phase_number=3, sequence_order=5, status="locked")
        lp6 = LearningPath(learner_id=learner_id, course_id="c6", phase_number=3, sequence_order=6, status="locked")
        session.add_all([lp1, lp2, lp3, lp4, lp5, lp6])

        # 6. LearnerSkills
        ls1 = LearnerSkill(learner_id=learner_id, skill_id="python", status="known", mastery_score=95.0)
        ls2 = LearnerSkill(learner_id=learner_id, skill_id="ml_fund", status="gap", mastery_score=None)
        ls3 = LearnerSkill(learner_id=learner_id, skill_id="deep_learning", status="gap", mastery_score=None)
        session.add_all([ls1, ls2, ls3])

        await session.commit()
        return learner_id


def test_dashboard_unknown_learner_returns_404():
    asyncio.run(_setup_dashboard_test_db())
    random_id = str(uuid.uuid4())
    resp = make_request("get", f"/api/dashboard/{random_id}")
    assert resp.status_code == 404
    assert f"Learner with ID '{random_id}' not found." in resp.json()["detail"]


def test_dashboard_zero_progress_calculation():
    """Fresh learner with all courses uncompleted returns 0.0% progress."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["learner_id"] == str(learner_id)
    assert data["target_role"] == "ml_engineer"
    assert data["role_name"] == "Machine Learning Engineer"
    assert data["overall_progress_percentage"] == 0.0
    assert data["effective_progress_percentage"] == 0.0
    assert data["total_courses"] == 6
    assert data["completed_courses"] == 0
    assert data["skipped_courses"] == 0
    assert data["current_phase_number"] == 1
    assert data["current_phase_name"] == "Phase 1"


def test_dashboard_accurate_completion_and_skipped_percentages():
    """1 done and 1 skipped out of 6 courses returns 16.7% genuine and 33.3% effective progress."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    async def _update_states():
        async with TestSessionLocal() as session:
            # c1 -> done
            lp1 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c1")
            )).scalar_one()
            lp1.status = "done"

            # c2 -> skipped
            lp2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c2")
            )).scalar_one()
            lp2.status = "skipped"

            # Phase 2 courses -> available
            lp3 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c3")
            )).scalar_one()
            lp3.status = "available"

            await session.commit()

    asyncio.run(_update_states())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    # 1 / 6 * 100 = 16.7%
    assert data["overall_progress_percentage"] == 16.7
    # (1 + 1) / 6 * 100 = 33.3%
    assert data["effective_progress_percentage"] == 33.3
    assert data["completed_courses"] == 1
    assert data["skipped_courses"] == 1
    assert data["total_courses"] == 6
    # Phase 1 is fully satisfied (1 done + 1 skipped), so active phase is Phase 2
    assert data["current_phase_number"] == 2
    assert data["current_phase_name"] == "Phase 2"


def test_skipped_courses_not_counted_as_genuine_completion():
    """Skipped courses must not increment genuine overall_progress_percentage."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    async def _update_states():
        async with TestSessionLocal() as session:
            lp1 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c1")
            )).scalar_one()
            lp1.status = "skipped"
            await session.commit()

    asyncio.run(_update_states())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_progress_percentage"] == 0.0
    assert data["effective_progress_percentage"] == 16.7
    assert data["completed_courses"] == 0
    assert data["skipped_courses"] == 1


def test_dashboard_all_courses_done():
    """When all courses are completed, genuine and effective progress reach 100.0% and next_action is None."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    async def _complete_all():
        async with TestSessionLocal() as session:
            lps = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id)
            )).scalars().all()
            for lp in lps:
                lp.status = "done"
            await session.commit()

    asyncio.run(_complete_all())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_progress_percentage"] == 100.0
    assert data["effective_progress_percentage"] == 100.0
    assert data["completed_courses"] == 6
    assert data["next_recommended_action"] is None


def test_dashboard_next_recommended_action_prioritizes_in_progress():
    """Next recommended action selects 'in_progress' course over 'available' course."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    async def _set_in_progress():
        async with TestSessionLocal() as session:
            # c1 is available, set c2 to in_progress
            lp2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c2")
            )).scalar_one()
            lp2.status = "in_progress"
            await session.commit()

    asyncio.run(_set_in_progress())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["next_recommended_action"] is not None
    assert data["next_recommended_action"]["course_id"] == "c2"
    assert data["next_recommended_action"]["status"] == "in_progress"
    assert data["next_recommended_action"]["primary_skill"] == "ml_fund"


def test_dashboard_next_recommended_action_selects_first_available():
    """When no course is in_progress, next recommended action selects the first available course in sequence."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["next_recommended_action"] is not None
    assert data["next_recommended_action"]["course_id"] == "c1"
    assert data["next_recommended_action"]["title"] == "Course 1"
    assert data["next_recommended_action"]["status"] == "available"
    assert data["next_recommended_action"]["duration_hours"] == 5
    assert data["next_recommended_action"]["primary_skill"] == "python"
    assert data["next_recommended_action"]["url"] == "https://course1.test"


def test_dashboard_skill_mastery_radar_accuracy():
    """Skill mastery radar accurately reflects known and gap competency scores."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    radar = data["skill_mastery_radar"]
    assert len(radar) == 3

    radar_map = {item["skill_id"]: item for item in radar}
    assert radar_map["python"]["status"] == "known"
    assert radar_map["python"]["mastery_score"] == 95.0
    assert radar_map["python"]["skill_name"] == "Python Programming"

    assert radar_map["ml_fund"]["status"] == "gap"
    assert radar_map["ml_fund"]["mastery_score"] == 0.0
    assert radar_map["ml_fund"]["skill_name"] == "Machine Learning Fundamentals"


def test_dashboard_zero_course_roadmap_avoids_division_by_zero():
    """Learner with empty learning_paths returns 0.0% without division-by-zero error."""
    asyncio.run(_setup_dashboard_test_db())

    empty_learner_id = uuid.uuid4()
    async def _create_empty_learner():
        async with TestSessionLocal() as session:
            l = Learner(id=empty_learner_id, name="Empty", email="empty@test.com", parsed_goal={"target_role": "ml_engineer"})
            session.add(l)
            await session.commit()

    asyncio.run(_create_empty_learner())

    resp = make_request("get", f"/api/dashboard/{empty_learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_progress_percentage"] == 0.0
    assert data["effective_progress_percentage"] == 0.0
    assert data["total_courses"] == 0
    assert data["next_recommended_action"] is None
    assert len(data["phase_progress"]) == 0


def test_dashboard_phase_progress_and_milestones():
    """Phase progress list accurately aggregates total, completed, and skipped courses per phase."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    async def _update_phase1():
        async with TestSessionLocal() as session:
            lp1 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c1")
            )).scalar_one()
            lp1.status = "done"

            lp2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c2")
            )).scalar_one()
            lp2.status = "skipped"

            lp3 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c3")
            )).scalar_one()
            lp3.status = "available"

            await session.commit()

    asyncio.run(_update_phase1())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    phases = data["phase_progress"]
    assert len(phases) == 3

    p1 = phases[0]
    assert p1["phase_number"] == 1
    assert p1["total_courses"] == 2
    assert p1["completed_courses"] == 1
    assert p1["skipped_courses"] == 1
    assert p1["is_unlocked"] is True
    assert p1["estimated_hours"] == 15  # 5 + 10

    p2 = phases[1]
    assert p2["phase_number"] == 2
    assert p2["total_courses"] == 2
    assert p2["completed_courses"] == 0
    assert p2["skipped_courses"] == 0
    assert p2["is_unlocked"] is True  # c3 is available

    p3 = phases[2]
    assert p3["phase_number"] == 3
    assert p3["is_unlocked"] is False  # all locked


def test_dashboard_recent_events_formatting():
    """Recent progress events are returned in reverse chronological order with course titles."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    async def _add_events():
        async with TestSessionLocal() as session:
            e1 = ProgressEvent(learner_id=learner_id, course_id="c1", assessment_score=90.0, difficulty_feedback="just_right")
            session.add(e1)
            await session.commit()

    asyncio.run(_add_events())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()
    events = data["recent_events"]
    assert len(events) == 1
    assert events[0]["course_id"] == "c1"
    assert events[0]["course_title"] == "Course 1"
    assert events[0]["assessment_score"] == 90.0
    assert events[0]["difficulty_feedback"] == "just_right"
    assert len(events[0]["timestamp"]) > 0


def test_dashboard_is_strictly_read_only():
    """Calling GET /api/dashboard/{learner_id} performs zero writes and leaves database state identical."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    async def _snapshot():
        async with TestSessionLocal() as session:
            events_count = len((await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all())
            lps = [(lp.course_id, lp.status, lp.sequence_order) for lp in (await session.execute(select(LearningPath).where(LearningPath.learner_id == learner_id))).scalars().all()]
            skills = [(ls.skill_id, ls.status, ls.mastery_score) for ls in (await session.execute(select(LearnerSkill).where(LearnerSkill.learner_id == learner_id))).scalars().all()]
            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            goal = dict(learner.parsed_goal)
            return events_count, lps, skills, goal

    before_events, before_lps, before_skills, before_goal = asyncio.run(_snapshot())

    # Call GET /api/dashboard multiple times
    resp1 = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp1.status_code == 200
    resp2 = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp2.status_code == 200

    after_events, after_lps, after_skills, after_goal = asyncio.run(_snapshot())

    assert before_events == after_events
    assert before_lps == after_lps
    assert before_skills == after_skills
    assert before_goal == after_goal


def test_dashboard_completed_earlier_phases_with_locked_later_phase():
    """Verify when Phases 1 and 2 are satisfied and Phase 3 is locked, active phase is Phase 3 and next_action is None."""
    learner_id = asyncio.run(_setup_dashboard_test_db())

    async def _update():
        async with TestSessionLocal() as session:
            # Phase 1: c1 done, c2 skipped
            lp1 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c1")
            )).scalar_one()
            lp1.status = "done"

            lp2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c2")
            )).scalar_one()
            lp2.status = "skipped"

            # Phase 2: c3 done, c4 done
            lp3 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c3")
            )).scalar_one()
            lp3.status = "done"

            lp4 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "c4")
            )).scalar_one()
            lp4.status = "done"

            # Phase 3: c5 locked, c6 locked (remains untouched)
            await session.commit()

    asyncio.run(_update())

    resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert resp.status_code == 200
    data = resp.json()

    # A & B: Active phase MUST be Phase 3
    assert data["current_phase_number"] == 3
    assert data["current_phase_name"] == "Phase 3"

    # C, D, E, F: Phase breakdown
    phases = data["phase_progress"]
    assert len(phases) == 3

    # Phase 1: 1 done, 1 skipped, total 2, unlocked True
    assert phases[0]["phase_number"] == 1
    assert phases[0]["completed_courses"] == 1
    assert phases[0]["skipped_courses"] == 1
    assert phases[0]["is_unlocked"] is True

    # Phase 2: 2 done, 0 skipped, total 2, unlocked True
    assert phases[1]["phase_number"] == 2
    assert phases[1]["completed_courses"] == 2
    assert phases[1]["skipped_courses"] == 0
    assert phases[1]["is_unlocked"] is True

    # Phase 3: 0 done, 0 skipped, total 2, unlocked False
    assert phases[2]["phase_number"] == 3
    assert phases[2]["completed_courses"] == 0
    assert phases[2]["skipped_courses"] == 0
    assert phases[2]["is_unlocked"] is False

    # G: next_recommended_action must be None (no in_progress or available course)
    assert data["next_recommended_action"] is None

    # H & I: Progress percentages (4 out of 6 courses done/skipped)
    # Genuine completion: 3 done / 6 = 50.0%
    assert data["overall_progress_percentage"] == 50.0
    # Effective progress: (3 done + 1 skipped) / 6 = 66.7%
    assert data["effective_progress_percentage"] == 66.7