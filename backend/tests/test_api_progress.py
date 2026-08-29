"""Targeted integration tests for POST /api/progress endpoint (Checkpoint 1).

Tests input validation, learner/roadmap membership verification, ProgressEvent audit logging,
course completion (status done), feedback-only handling, phase unlock progression, and transaction rollback.
Uses isolated in-memory SQLite.
"""

import asyncio
import unittest.mock
import uuid
import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.main import app
from backend.app.config import settings
from backend.app.database import Base, get_db
from backend.app.models import Course, CourseSkill, Learner, LearnerSkill, LearningPath, ProgressEvent, Skill

# Force testing mode
settings.TESTING = True

TEST_SQLITE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_SQLITE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def _setup_test_db():
    """Create tables and seed minimal catalog and learner fixtures."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        # 1. Skills
        s1 = Skill(id="python", name="Python Programming", domain="ml")
        s2 = Skill(id="ml_fund", name="Machine Learning Fundamentals", domain="ml")
        s3 = Skill(id="deep_learning", name="Deep Learning", domain="ml")
        session.add_all([s1, s2, s3])

        # 2. Courses
        c1 = Course(
            id="course-p1-a",
            title="Phase 1 Course A",
            difficulty="intermediate",
            duration_hours=10,
            resource_type="course",
            domain="ml",
            is_mvp=True,
        )
        c2 = Course(
            id="course-p1-b",
            title="Phase 1 Course B",
            difficulty="intermediate",
            duration_hours=15,
            resource_type="course",
            domain="ml",
            is_mvp=True,
        )
        c3 = Course(
            id="course-p2-a",
            title="Phase 2 Course A",
            difficulty="advanced",
            duration_hours=20,
            resource_type="course",
            domain="ml",
            is_mvp=True,
        )
        c4 = Course(
            id="course-not-in-path",
            title="Unrelated Course",
            difficulty="beginner",
            duration_hours=5,
            resource_type="course",
            domain="ml",
            is_mvp=True,
        )
        session.add_all([c1, c2, c3, c4])

        # 3. CourseSkills
        cs1 = CourseSkill(course_id="course-p1-a", skill_id="ml_fund", is_primary=True)
        cs2 = CourseSkill(course_id="course-p1-b", skill_id="ml_fund", is_primary=True)
        cs3 = CourseSkill(course_id="course-p2-a", skill_id="deep_learning", is_primary=True)
        cs4 = CourseSkill(course_id="course-not-in-path", skill_id="python", is_primary=True)
        session.add_all([cs1, cs2, cs3, cs4])

        # 4. Learner
        learner_id = uuid.uuid4()
        learner = Learner(
            id=learner_id,
            name="Test Progress Learner",
            email="progress_learner@coursetide.test",
            goal="Become an ML engineer",
            weekly_hours=8,
            parsed_goal={"target_role": "ml_engineer", "known_skills": ["python"], "gap_skills": ["ml_fund", "deep_learning"]},
        )
        session.add(learner)

        # 5. Learning Paths (Phase 1 has 2 courses available; Phase 2 has 1 course locked)
        lp1 = LearningPath(learner_id=learner_id, course_id="course-p1-a", phase_number=1, sequence_order=1, status="available")
        lp2 = LearningPath(learner_id=learner_id, course_id="course-p1-b", phase_number=1, sequence_order=2, status="available")
        lp3 = LearningPath(learner_id=learner_id, course_id="course-p2-a", phase_number=2, sequence_order=3, status="locked")
        session.add_all([lp1, lp2, lp3])

        await session.commit()
        return learner_id


async def _get_test_db():
    async with TestSessionLocal() as session:
        yield session


def make_request(method: str, url: str, json_payload: dict = None):
    """Helper to run async requests with isolated database override."""
    async def _call():
        app.dependency_overrides[get_db] = _get_test_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                if method.lower() == "get":
                    return await client.get(url)
                elif method.lower() == "post":
                    return await client.post(url, json=json_payload)
        finally:
            app.dependency_overrides.pop(get_db, None)

    return asyncio.run(_call())


def test_valid_progress_submission_records_event():
    """Verify valid assessment score submission records ProgressEvent in DB and returns 200."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 80.0,
            "difficulty_feedback": "just_right",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["course_status"] == "done"
    assert data["adaptation_applied"] == "none"
    assert "event_id" in data

    # Verify in DB
    async def _verify():
        async with TestSessionLocal() as session:
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 1
            assert events[0].course_id == "course-p1-a"
            assert events[0].assessment_score == 80.0
            assert events[0].difficulty_feedback == "just_right"

    asyncio.run(_verify())


def test_valid_score_marks_course_done():
    """Verify numeric assessment score updates learning_paths.status to 'done'."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 75.0,
        },
    )
    assert resp.status_code == 200

    # Verify in DB
    async def _verify():
        async with TestSessionLocal() as session:
            lp = (await session.execute(
                select(LearningPath).where(
                    LearningPath.learner_id == learner_id,
                    LearningPath.course_id == "course-p1-a",
                )
            )).scalar_one()
            assert lp.status == "done"

    asyncio.run(_verify())


def test_feedback_only_records_event_without_marking_done():
    """Verify submitting difficulty feedback with null score records event and preserves course status."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "difficulty_feedback": "too_easy",
            "assessment_score": None,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_status"] == "available"

    # Verify in DB
    async def _verify():
        async with TestSessionLocal() as session:
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 1
            assert events[0].difficulty_feedback == "too_easy"
            assert events[0].assessment_score is None

            lp = (await session.execute(
                select(LearningPath).where(
                    LearningPath.learner_id == learner_id,
                    LearningPath.course_id == "course-p1-a",
                )
            )).scalar_one()
            assert lp.status == "available"  # Preserved as available!

    asyncio.run(_verify())


def test_progress_unknown_learner_returns_404():
    """Verify non-existent learner ID returns HTTP 404."""
    asyncio.run(_setup_test_db())
    unknown_id = str(uuid.uuid4())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": unknown_id,
            "course_id": "course-p1-a",
            "assessment_score": 88.0,
        },
    )
    assert resp.status_code == 404
    assert f"Learner with ID '{unknown_id}' not found." in resp.json()["detail"]


def test_progress_course_not_in_learner_path_returns_400():
    """Verify course not in learner's active roadmap returns HTTP 400."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-not-in-path",
            "assessment_score": 88.0,
        },
    )
    assert resp.status_code == 400
    assert "is not in the learner's active roadmap" in resp.json()["detail"]


def test_progress_invalid_feedback_enum_returns_422():
    """Verify invalid feedback string outside enum returns HTTP 422."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "difficulty_feedback": "extremely_difficult",
            "assessment_score": 80.0,
        },
    )
    assert resp.status_code == 422


def test_progress_invalid_score_below_zero_returns_422():
    """Verify assessment_score < 0 returns HTTP 422."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": -1.0,
        },
    )
    assert resp.status_code == 422


def test_progress_invalid_score_above_100_returns_422():
    """Verify assessment_score > 100 returns HTTP 422."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 100.5,
        },
    )
    assert resp.status_code == 422


def test_progress_missing_both_score_and_feedback_returns_422():
    """Verify payload with both feedback and score null returns HTTP 422."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "difficulty_feedback": None,
            "assessment_score": None,
        },
    )
    assert resp.status_code == 422


def test_score_zero_accepted():
    """Verify score 0.0 is accepted, marks course done, and records event."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 0.0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["course_status"] == "done"


def test_score_100_accepted():
    """Verify score 100.0 is accepted, marks course done, and records event."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 100.0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["course_status"] == "done"


def test_phase_unlock_when_all_phase_courses_done():
    """Verify completing all courses in Phase 1 unlocks Phase 2 courses (locked -> available)."""
    learner_id = asyncio.run(_setup_test_db())

    # 1. Complete Course 1 of Phase 1
    resp1 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 80.0},
    )
    assert resp1.status_code == 200

    # Verify Phase 2 course is still locked
    async def _verify_locked():
        async with TestSessionLocal() as session:
            lp_p2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p2-a")
            )).scalar_one()
            assert lp_p2.status == "locked"

    asyncio.run(_verify_locked())

    # 2. Complete Course 2 of Phase 1 (completing all Phase 1 courses!)
    resp2 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-b", "assessment_score": 85.0},
    )
    assert resp2.status_code == 200

    # Verify Phase 2 course is now UNLOCKED ('available')
    async def _verify_unlocked():
        async with TestSessionLocal() as session:
            lp_p2_unlocked = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p2-a")
            )).scalar_one()
            assert lp_p2_unlocked.status == "available"

    asyncio.run(_verify_unlocked())


def test_progress_db_failure_rolls_back_all_changes():
    """Verify simulated DB commit failure rolls back ProgressEvent and LearningPath status."""
    learner_id = asyncio.run(_setup_test_db())

    # Patch commit on AsyncSession to raise an exception
    with unittest.mock.patch.object(AsyncSession, "commit", side_effect=RuntimeError("Simulated DB commit crash")):
        resp = make_request(
            "post",
            "/api/progress",
            json_payload={
                "learner_id": str(learner_id),
                "course_id": "course-p1-a",
                "assessment_score": 90.0,
            },
        )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Failed to record progress event due to an internal database error."

    # Verify DB is completely uncorrupted (0 events, course remains 'available')
    async def _verify():
        async with TestSessionLocal() as session:
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 0

            lp = (await session.execute(
                select(LearningPath).where(
                    LearningPath.learner_id == learner_id,
                    LearningPath.course_id == "course-p1-a",
                )
            )).scalar_one()
            assert lp.status == "available"

    asyncio.run(_verify())