"""Targeted integration tests for POST /api/progress endpoint (Checkpoints 1 & 2).

Tests:
1. Input validation & error responses (404, 400, 422).
2. Event persistence in progress_events.
3. Course completion (status done) for score submissions.
4. Feedback-only submissions preserving course status.
5. Phase-unlock progression (locked -> available).
6. Deterministic mastery rules (score > 85.0 vs <= 85.0).
7. Primary-skill-only mastery and parsed_goal updates (known/gap).
8. Fast-track target selection (first qualifying course by sequence_order, difficulty <= completed).
9. Skipped course row preservation (status skipped, sequence_order & phase_number unchanged).
10. Idempotency & atomic transaction rollback.
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
        s3 = Skill(id="data_manip", name="Data Manipulation", domain="ml")
        s4 = Skill(id="deep_learning", name="Deep Learning", domain="ml")
        session.add_all([s1, s2, s3, s4])

        # 2. Courses
        # Course P1-A: Intermediate, Primary = ml_fund, Secondary = data_manip
        c1 = Course(id="course-p1-a", title="Phase 1 Course A", difficulty="intermediate", duration_hours=10, resource_type="course", domain="ml", is_mvp=True)
        # Course P1-B: Beginner, Primary = ml_fund (Qualifies for skip if P1-A completed with >85)
        c2 = Course(id="course-p1-b", title="Phase 1 Course B", difficulty="beginner", duration_hours=15, resource_type="course", domain="ml", is_mvp=True)
        # Course P1-C: Intermediate, Primary = ml_fund (Qualifies for skip if P1-A completed with >85)
        c3 = Course(id="course-p1-c", title="Phase 1 Course C", difficulty="intermediate", duration_hours=12, resource_type="course", domain="ml", is_mvp=True)
        # Course P1-Harder: Advanced, Primary = ml_fund (Does NOT qualify for skip if P1-A is intermediate)
        c4 = Course(id="course-p1-harder", title="Phase 1 Harder Course", difficulty="advanced", duration_hours=20, resource_type="course", domain="ml", is_mvp=True)
        # Course P1-DiffSkill: Beginner, Primary = data_manip (Does NOT qualify for skip if primary is ml_fund)
        c5 = Course(id="course-p1-diff", title="Phase 1 Diff Skill Course", difficulty="beginner", duration_hours=8, resource_type="course", domain="ml", is_mvp=True)
        # Course P2-A: Advanced, Primary = deep_learning
        c6 = Course(id="course-p2-a", title="Phase 2 Course A", difficulty="advanced", duration_hours=20, resource_type="course", domain="ml", is_mvp=True)
        # Course Not in Path
        c7 = Course(id="course-not-in-path", title="Unrelated Course", difficulty="beginner", duration_hours=5, resource_type="course", domain="ml", is_mvp=True)
        session.add_all([c1, c2, c3, c4, c5, c6, c7])

        # 3. CourseSkills
        cs1 = CourseSkill(course_id="course-p1-a", skill_id="ml_fund", is_primary=True)
        cs1_sec = CourseSkill(course_id="course-p1-a", skill_id="data_manip", is_primary=False)
        cs2 = CourseSkill(course_id="course-p1-b", skill_id="ml_fund", is_primary=True)
        cs3 = CourseSkill(course_id="course-p1-c", skill_id="ml_fund", is_primary=True)
        cs4 = CourseSkill(course_id="course-p1-harder", skill_id="ml_fund", is_primary=True)
        cs5 = CourseSkill(course_id="course-p1-diff", skill_id="data_manip", is_primary=True)
        cs6 = CourseSkill(course_id="course-p2-a", skill_id="deep_learning", is_primary=True)
        cs7 = CourseSkill(course_id="course-not-in-path", skill_id="python", is_primary=True)
        session.add_all([cs1, cs1_sec, cs2, cs3, cs4, cs5, cs6, cs7])

        # 4. Learner
        learner_id = uuid.uuid4()
        learner = Learner(
            id=learner_id,
            name="Test Progress Learner",
            email="progress_learner@coursetide.test",
            goal="Become an ML engineer",
            weekly_hours=8,
            parsed_goal={
                "target_role": "ml_engineer",
                "role_name": "Machine Learning Engineer",
                "timeframe_months": 6,
                "weekly_hours": 8,
                "known_skills": ["python"],
                "gap_skills": ["ml_fund", "data_manip", "deep_learning"],
                "unrecognized_skills": [],
                "match_percentage": 25.0,
            },
        )
        session.add(learner)

        # 5. Learning Paths (Standard 3-course setup: P1-A available, P1-B available, P2-A locked)
        lp1 = LearningPath(learner_id=learner_id, course_id="course-p1-a", phase_number=1, sequence_order=1, status="available")
        lp2 = LearningPath(learner_id=learner_id, course_id="course-p1-b", phase_number=1, sequence_order=2, status="available")
        lp3 = LearningPath(learner_id=learner_id, course_id="course-p2-a", phase_number=2, sequence_order=3, status="locked")
        session.add_all([lp1, lp2, lp3])

        # 6. LearnerSkill initial gap states
        ls1 = LearnerSkill(learner_id=learner_id, skill_id="ml_fund", status="gap", mastery_score=None)
        ls2 = LearnerSkill(learner_id=learner_id, skill_id="data_manip", status="gap", mastery_score=None)
        session.add_all([ls1, ls2])

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


# =========================================================================
# CHECKPOINT 1 BASE TESTS
# =========================================================================

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
            assert lp.status == "available"

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

    # 1. Complete Course 1 of Phase 1 with neutral score 80.0
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

    # 2. Complete Course 2 of Phase 1 with neutral score 85.0
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

    # Verify DB is completely uncorrupted
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


# =========================================================================
# CHECKPOINT 2 DETERMINISTIC MASTERY & FAST-TRACK TESTS
# =========================================================================

def test_score_85_point_0_does_not_trigger_mastery():
    """Verify score exactly 85.0 marks course done but triggers NO mastery or fast-track skip."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 85.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_status"] == "done"
    assert data["adaptation_applied"] == "none"
    assert data["adaptation_details"]["mastered_skill"] is None
    assert data["adaptation_details"]["skipped_course_id"] is None

    async def _verify():
        async with TestSessionLocal() as session:
            # Skill ml_fund remains gap
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.status == "gap"

            # Subsequent course course-p1-b remains available
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "available"

    asyncio.run(_verify())


def test_score_85_point_1_triggers_primary_skill_mastery():
    """Verify score 85.1 (strictly > 85.0) triggers mastery and fast-track skip."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 85.1,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_status"] == "done"
    assert data["adaptation_applied"] == "mastery_skip"
    assert data["adaptation_details"]["mastered_skill"] == "ml_fund"
    assert data["adaptation_details"]["skipped_course_id"] == "course-p1-b"


def test_score_above_85_updates_learner_skills_status_to_known():
    """Verify score > 85.0 updates learner_skills.status to 'known'."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 92.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.status == "known"
            assert ls.mastery_score == 92.0

    asyncio.run(_verify())


def test_mastery_score_uses_max_of_existing_and_new():
    """Verify mastery_score uses max(existing, new) without decreasing."""
    learner_id = asyncio.run(_setup_test_db())

    # Pre-set existing mastery score to 95.0
    async def _prep():
        async with TestSessionLocal() as session:
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            ls.mastery_score = 95.0
            ls.status = "known"
            await session.commit()

    asyncio.run(_prep())

    # Submit lower score 88.0 (>85 but <95)
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 88.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.mastery_score == 95.0  # Max preserved!

    asyncio.run(_verify())


def test_parsed_goal_known_skills_is_updated():
    """Verify parsed_goal['known_skills'] includes mastered primary skill."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            assert "ml_fund" in learner.parsed_goal["known_skills"]
            assert "python" in learner.parsed_goal["known_skills"]  # Preserved!

    asyncio.run(_verify())


def test_parsed_goal_gap_skills_removes_mastered_primary_skill():
    """Verify parsed_goal['gap_skills'] removes mastered primary skill while preserving other gap skills."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            assert "ml_fund" not in learner.parsed_goal["gap_skills"]
            assert "data_manip" in learner.parsed_goal["gap_skills"]
            assert "deep_learning" in learner.parsed_goal["gap_skills"]

    asyncio.run(_verify())


def test_secondary_covered_skills_remain_unchanged():
    """Verify secondary skill (data_manip) on completed course remains in gap_skills and not marked known."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",  # Has primary=ml_fund, secondary=data_manip
            "assessment_score": 95.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            ls_data = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "data_manip")
            )).scalar_one()
            assert ls_data.status == "gap"  # Secondary skill NOT marked known!

            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            assert "data_manip" in learner.parsed_goal["gap_skills"]
            assert "data_manip" not in learner.parsed_goal["known_skills"]

    asyncio.run(_verify())


def test_matching_later_same_primary_course_is_skipped():
    """Verify later course teaching same primary skill with difficulty <= completed course is marked skipped."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",  # Intermediate ml_fund
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"

    asyncio.run(_verify())


def test_skip_only_affects_one_qualifying_course():
    """Verify that when multiple subsequent courses qualify, only the FIRST qualifying course is skipped."""
    learner_id = asyncio.run(_setup_test_db())

    # Add a third course (course-p1-c: intermediate ml_fund) at sequence 3
    async def _prep():
        async with TestSessionLocal() as session:
            lp_c = LearningPath(learner_id=learner_id, course_id="course-p1-c", phase_number=1, sequence_order=3, status="available")
            session.add(lp_c)
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",  # Seq 1
            "assessment_score": 95.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            # First qualifying (course-p1-b, seq 2) is skipped
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"

            # Second qualifying (course-p1-c, seq 3) is NOT skipped (remains available)
            lp_c = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-c")
            )).scalar_one()
            assert lp_c.status == "available"

    asyncio.run(_verify())


def test_different_primary_skill_course_is_not_skipped():
    """Verify course with different primary skill is not skipped upon mastery of ml_fund."""
    learner_id = asyncio.run(_setup_test_db())

    # Replace course-p1-b with course-p1-diff (primary: data_manip)
    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            lp_b.course_id = "course-p1-diff"
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",  # primary ml_fund
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_applied"] == "mastery"  # Mastery occurred, but no skip

    async def _verify():
        async with TestSessionLocal() as session:
            lp_diff = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-diff")
            )).scalar_one()
            assert lp_diff.status == "available"

    asyncio.run(_verify())


def test_harder_course_is_not_skipped():
    """Verify candidate course with difficulty > completed course difficulty is NOT skipped."""
    learner_id = asyncio.run(_setup_test_db())

    # Replace course-p1-b with course-p1-harder (difficulty: advanced)
    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            lp_b.course_id = "course-p1-harder"
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",  # difficulty: intermediate
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_applied"] == "mastery"

    async def _verify():
        async with TestSessionLocal() as session:
            lp_harder = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-harder")
            )).scalar_one()
            assert lp_harder.status == "available"

    asyncio.run(_verify())


def test_earlier_course_is_not_skipped():
    """Verify course with sequence_order earlier than completed course is NOT skipped."""
    learner_id = asyncio.run(_setup_test_db())

    # Set course-p1-b to sequence 1 and course-p1-a to sequence 2
    async def _prep():
        async with TestSessionLocal() as session:
            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            lp_a.sequence_order = 2
            lp_b.sequence_order = 1
            await session.commit()

    asyncio.run(_prep())

    # Complete course-p1-a (seq 2) with score 90.0
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "available"  # Earlier course NOT skipped!

    asyncio.run(_verify())


def test_already_done_or_skipped_course_is_not_selected_for_skip():
    """Verify course that is already 'done' or 'skipped' is ignored during skip search."""
    learner_id = asyncio.run(_setup_test_db())

    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            lp_b.status = "done"
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 92.0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_applied"] == "mastery"  # No eligible courses to skip

    async def _verify():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "done"  # Remains done

    asyncio.run(_verify())


def test_sequence_order_and_phase_number_remain_unchanged_on_skip():
    """Verify that marking a course skipped preserves its exact sequence_order and phase_number."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 95.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"
            assert lp_b.sequence_order == 2
            assert lp_b.phase_number == 1

    asyncio.run(_verify())


def test_skipped_row_remains_in_database():
    """Verify that skipped course is NOT deleted from learning_paths."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            all_lps = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id)
            )).scalars().all()
            assert len(all_lps) == 3  # All 3 rows still present in DB

    asyncio.run(_verify())


def test_phase_unlock_works_when_current_phase_is_done_and_skipped():
    """Verify Phase 2 unlocks when Phase 1 courses are satisfied by a mix of 'done' and 'skipped'."""
    learner_id = asyncio.run(_setup_test_db())

    # Completing Course P1-A with score 90.0 marks P1-A done AND fast-tracks P1-B to skipped!
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            # Phase 1: P1-A is done, P1-B is skipped -> Phase 1 satisfied!
            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            assert lp_a.status == "done"

            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"

            # Phase 2 course P2-A must now be UNLOCKED ('available')!
            lp_p2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p2-a")
            )).scalar_one()
            assert lp_p2.status == "available"

    asyncio.run(_verify())


def test_no_qualifying_skip_target_mastery_still_succeeds():
    """Verify when no course qualifies for skip, skill mastery still updates successfully without error."""
    learner_id = asyncio.run(_setup_test_db())

    # Remove course-p1-b so no matching competency course is ahead
    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            await session.delete(lp_b)
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["adaptation_applied"] == "mastery"
    assert data["adaptation_details"]["mastered_skill"] == "ml_fund"
    assert data["adaptation_details"]["skipped_course_id"] is None

    async def _verify():
        async with TestSessionLocal() as session:
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.status == "known"

    asyncio.run(_verify())


def test_repeated_above_85_submission_does_not_create_additional_side_effects():
    """Verify resubmitting a high score on an already done course is idempotent and does not skip extra courses."""
    learner_id = asyncio.run(_setup_test_db())

    # Add course-p1-c at sequence 3
    async def _prep():
        async with TestSessionLocal() as session:
            lp_c = LearningPath(learner_id=learner_id, course_id="course-p1-c", phase_number=1, sequence_order=3, status="available")
            session.add(lp_c)
            await session.commit()

    asyncio.run(_prep())

    # First submission
    resp1 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp1.status_code == 200
    assert resp1.json()["adaptation_applied"] == "mastery_skip"

    # Second submission on the same course
    resp2 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 95.0},
    )
    assert resp2.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            # P1-B was skipped on 1st run
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"

            # P1-C was NOT skipped on 2nd run (MUST remain available!)
            lp_c = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-c")
            )).scalar_one()
            assert lp_c.status == "available"

    asyncio.run(_verify())


def test_rollback_occurs_if_mastery_mutation_fails_midway():
    """Verify that if an error occurs during mastery or commit, all progress event and mastery changes are rolled back."""
    learner_id = asyncio.run(_setup_test_db())

    with unittest.mock.patch.object(AsyncSession, "commit", side_effect=RuntimeError("Simulated DB crash during commit")):
        resp = make_request(
            "post",
            "/api/progress",
            json_payload={
                "learner_id": str(learner_id),
                "course_id": "course-p1-a",
                "assessment_score": 98.0,
            },
        )
        assert resp.status_code == 500

    async def _verify():
        async with TestSessionLocal() as session:
            # 0 Progress Events
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 0

            # Skill ml_fund remains gap
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.status == "gap"

            # Course P1-A remains available
            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            assert lp_a.status == "available"

            # Course P1-B remains available
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "available"

    asyncio.run(_verify())


def test_repeated_neutral_score_on_done_course_records_event_without_adaptation():
    """Verify resubmitting a neutral score on an already done course records event without mutation."""
    learner_id = asyncio.run(_setup_test_db())

    # 1. Complete course-p1-a with score 80.0
    resp1 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 80.0},
    )
    assert resp1.status_code == 200

    # 2. Resubmit neutral score 82.0 on already done course-p1-a
    resp2 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 82.0},
    )
    assert resp2.status_code == 200
    assert resp2.json()["adaptation_applied"] == "none"
    assert resp2.json()["adaptation_details"]["message"] == "Progress event recorded for previously completed course."

    async def _verify():
        async with TestSessionLocal() as session:
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 2  # Both events saved in audit log!

            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            assert lp_a.status == "done"

    asyncio.run(_verify())


def test_progress_locked_course_is_rejected():
    """Verify progress submission on a locked course is rejected with HTTP 400 and creates no records."""
    learner_id = asyncio.run(_setup_test_db())

    # course-p2-a is initially 'locked' in Phase 2
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p2-a",
            "assessment_score": 95.0,
        },
    )
    assert resp.status_code == 400
    assert "is locked. Complete preceding phase milestones first." in resp.json()["detail"]

    # Verify zero side effects in database
    async def _verify():
        async with TestSessionLocal() as session:
            # 0 Progress Events
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 0

            # Course remains locked
            lp_p2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p2-a")
            )).scalar_one()
            assert lp_p2.status == "locked"

            # Skill deep_learning remains unmastered (not in known_skills)
            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            assert "deep_learning" in learner.parsed_goal["gap_skills"]
            assert "deep_learning" not in learner.parsed_goal["known_skills"]

    asyncio.run(_verify())


def test_progress_skipped_course_is_rejected():
    """Verify progress submission on a skipped course is rejected with HTTP 400 and creates no records."""
    learner_id = asyncio.run(_setup_test_db())

    # Pre-set course-p1-b to 'skipped'
    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            lp_b.status = "skipped"
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-b",
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 400
    assert "was skipped due to demonstrated mastery." in resp.json()["detail"]

    # Verify zero side effects in database
    async def _verify():
        async with TestSessionLocal() as session:
            # 0 Progress Events
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 0

            # Course remains skipped
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"

    asyncio.run(_verify())


def test_progress_in_progress_course_is_allowed():
    """Verify progress submission on an in_progress course is allowed and marks it done."""
    learner_id = asyncio.run(_setup_test_db())

    # Pre-set course-p1-a to 'in_progress'
    async def _prep():
        async with TestSessionLocal() as session:
            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            lp_a.status = "in_progress"
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 80.0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["course_status"] == "done"

    async def _verify():
        async with TestSessionLocal() as session:
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 1

            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            assert lp_a.status == "done"

    asyncio.run(_verify())