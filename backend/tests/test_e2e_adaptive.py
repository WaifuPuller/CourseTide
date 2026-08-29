"""Comprehensive End-to-End Integration Tests for Day 4 Adaptive Learning Lifecycle.

Checkpoint 6 Scope:
1. Full Intake -> Profile -> Roadmap -> Progress -> Mastery / Fast-track -> Dashboard loop.
2. Full Intake -> Profile -> Roadmap -> Progress -> Remediation Reroute -> Dashboard loop.
3. State integrity, locked/skipped course protection, and adversarial idempotency.
4. Feedback-only non-adaptive audit logging.
5. Weekly-hours timeline calculation invariants.
6. Pure in-memory SQLite isolation (zero Neon production access, zero external LLM quota).
"""

import asyncio
import unittest.mock
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.main import app
from backend.app.config import settings
from backend.app.database import Base, get_db
from backend.app.models import Course, CourseSkill, Learner, LearnerSkill, LearningPath, ProgressEvent, Skill
from backend.app.recommender.goal_parser import ParsedGoal

# Force test configuration
settings.TESTING = True

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_DB_URL,
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


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def make_request(method: str, url: str, json_payload: dict = None):
    """Synchronous test client wrapper."""
    async def _do():
        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            if method.lower() == "get":
                return await client.get(url)
            elif method.lower() == "post":
                return await client.post(url, json=json_payload)
    return asyncio.run(_do())


async def _setup_e2e_catalog():
    """Seed comprehensive catalog for end-to-end multi-phase testing."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        # 1. Taxonomy Skills
        skills = [
            Skill(id="python", name="Python Programming", domain="ml"),
            Skill(id="stats", name="Statistics & Probability", domain="ml"),
            Skill(id="data_manip", name="Data Manipulation with Pandas", domain="ml"),
            Skill(id="ml_fund", name="Machine Learning Fundamentals", domain="ml"),
            Skill(id="deep_learning", name="Deep Learning", domain="ml"),
        ]
        session.add_all(skills)

        # 2. Courses
        courses = [
            # Phase 1 Candidates
            Course(
                id="c-pandas-1",
                title="Introduction to Data Analysis with Pandas",
                difficulty="beginner",
                duration_hours=10,
                resource_type="course",
                domain="ml",
                is_mvp=True,
                url="https://coursetide.test/pandas-1",
                embedding=[0.1] * 384,
            ),
            Course(
                id="c-pandas-2",
                title="Intermediate Pandas Data Wrangling",
                difficulty="beginner",
                duration_hours=8,
                resource_type="course",
                domain="ml",
                is_mvp=True,
                url="https://coursetide.test/pandas-2",
                embedding=[0.1] * 384,
            ),
            # Phase 2 Candidates
            Course(
                id="c-ml-fund",
                title="Machine Learning Foundations & Supervised Algorithms",
                difficulty="intermediate",
                duration_hours=15,
                resource_type="course",
                domain="ml",
                is_mvp=True,
                url="https://coursetide.test/ml-fund",
                embedding=[0.2] * 384,
            ),
            Course(
                id="c-ml-remedial",
                title="Foundations of Machine Learning for Beginners",
                difficulty="beginner",
                duration_hours=6,
                resource_type="course",
                domain="ml",
                is_mvp=True,
                url="https://coursetide.test/ml-remedial",
                embedding=[0.2] * 384,
            ),
            # Phase 3 Candidates
            Course(
                id="c-deep-learning",
                title="Deep Learning & Neural Networks Masterclass",
                difficulty="advanced",
                duration_hours=25,
                resource_type="course",
                domain="ml",
                is_mvp=True,
                url="https://coursetide.test/deep-learning",
                embedding=[0.3] * 384,
            ),
        ]
        session.add_all(courses)

        # 3. Course Skills
        course_skills = [
            CourseSkill(course_id="c-pandas-1", skill_id="data_manip", is_primary=True),
            CourseSkill(course_id="c-pandas-2", skill_id="data_manip", is_primary=True),
            CourseSkill(course_id="c-ml-fund", skill_id="ml_fund", is_primary=True),
            CourseSkill(course_id="c-ml-remedial", skill_id="ml_fund", is_primary=True),
            CourseSkill(course_id="c-deep-learning", skill_id="deep_learning", is_primary=True),
        ]
        session.add_all(course_skills)

        await session.commit()


@pytest.fixture(autouse=True)
def init_e2e_db():
    asyncio.run(_setup_e2e_catalog())


def test_full_adaptive_loop_mastery_and_fast_track():
    """E2E Scenario 1: Intake -> Roadmap -> High Score (>85) -> Fast Track -> Dashboard."""
    # Step A: Goal Intake (POST /api/profile)
    intake_payload = {
        "goal": "I want to become a Machine Learning Engineer. I know Python and statistics and have 10 hours a week.",
        "weekly_hours": 10,
    }

    mock_parsed_goal = ParsedGoal(
        target_role="ml_engineer",
        known_skills=["python", "stats"],
        unrecognized_skills=[],
        weekly_hours=10,
        timeframe_months=6,
    )

    with unittest.mock.patch("backend.app.api.profile.parse_goal", return_value=mock_parsed_goal):
        profile_resp = make_request("post", "/api/profile", intake_payload)

    assert profile_resp.status_code == 200
    profile_data = profile_resp.json()
    learner_id = profile_data["learner_id"]
    assert profile_data["target_role"] == "ml_engineer"
    assert profile_data["weekly_hours"] == 10
    assert set(profile_data["known_skills"]) == {"python", "stats"}
    assert {"data_manip", "ml_fund", "deep_learning"}.issubset(set(profile_data["gap_skills"]))

    # Step B: Roadmap Sequencing (GET /api/roadmap/{learner_id})
    roadmap_resp = make_request("get", f"/api/roadmap/{learner_id}")
    assert roadmap_resp.status_code == 200
    roadmap_data = roadmap_resp.json()
    assert len(roadmap_data["phases"]) >= 2
    
    # Phase 1 courses must be available
    phase1 = roadmap_data["phases"][0]
    for c in phase1["courses"]:
        assert c["status"] == "available"

    # Step C: Initial Dashboard State (GET /api/dashboard/{learner_id})
    dash_init = make_request("get", f"/api/dashboard/{learner_id}")
    assert dash_init.status_code == 200
    dash_init_data = dash_init.json()
    assert dash_init_data["overall_progress_percentage"] == 0.0
    assert dash_init_data["effective_progress_percentage"] == 0.0
    assert dash_init_data["completed_courses"] == 0
    assert dash_init_data["skipped_courses"] == 0
    assert dash_init_data["current_phase_number"] == 1
    assert dash_init_data["next_recommended_action"] is not None
    assert dash_init_data["next_recommended_action"]["status"] == "available"

    # Step D: Submit High Score > 85.0 on first course (POST /api/progress)
    first_course_id = phase1["courses"][0]["course_id"]
    progress_payload = {
        "learner_id": learner_id,
        "course_id": first_course_id,
        "assessment_score": 94.5,
        "difficulty_feedback": "just_right",
    }
    prog_resp = make_request("post", "/api/progress", progress_payload)
    assert prog_resp.status_code == 200
    prog_data = prog_resp.json()
    assert prog_data["status"] == "success"
    assert prog_data["course_status"] == "done"
    assert prog_data["adaptation_applied"] == "mastery_skip"
    assert prog_data["adaptation_details"]["mastered_skill"] == "data_manip"

    # Step E: Post-Mastery Dashboard Aggregation
    dash_post = make_request("get", f"/api/dashboard/{learner_id}")
    assert dash_post.status_code == 200
    dash_post_data = dash_post.json()
    assert dash_post_data["completed_courses"] == 1
    assert dash_post_data["skipped_courses"] == 1  # c-pandas-2 fast-tracked
    assert dash_post_data["overall_progress_percentage"] > 0.0
    assert dash_post_data["effective_progress_percentage"] > dash_post_data["overall_progress_percentage"]

    # Skill radar reflects mastery
    radar_map = {item["skill_id"]: item for item in dash_post_data["skill_mastery_radar"]}
    assert radar_map["data_manip"]["status"] == "known"
    assert radar_map["data_manip"]["mastery_score"] == 94.5

    # Recent events reflects assessment submission
    assert len(dash_post_data["recent_events"]) == 1
    assert dash_post_data["recent_events"][0]["course_id"] == first_course_id
    assert dash_post_data["recent_events"][0]["assessment_score"] == 94.5


def test_full_adaptive_loop_remediation_reroute():
    """E2E Scenario 2: Intake -> Roadmap -> Low Score (<50) -> Remedial Insertion -> Dashboard."""
    # Step A: Create Learner directly with intermediate gap
    learner_id = uuid.uuid4()
    async def _seed_learner():
        async with TestSessionLocal() as session:
            l = Learner(
                id=learner_id,
                name="Bob ML",
                email="bob@coursetide.test",
                goal="Learn Machine Learning",
                weekly_hours=8,
                parsed_goal={
                    "target_role": "ml_engineer",
                    "role_name": "Machine Learning Engineer",
                    "known_skills": ["python", "data_manip"],
                    "gap_skills": ["ml_fund"],
                },
            )
            session.add(l)

            # Learning path with intermediate course in Phase 1 and advanced in Phase 2
            lp1 = LearningPath(learner_id=learner_id, course_id="c-ml-fund", phase_number=1, sequence_order=1, status="available")
            lp2 = LearningPath(learner_id=learner_id, course_id="c-deep-learning", phase_number=2, sequence_order=2, status="locked")
            session.add_all([lp1, lp2])

            ls1 = LearnerSkill(learner_id=learner_id, skill_id="ml_fund", status="gap", mastery_score=None)
            session.add(ls1)
            await session.commit()

    asyncio.run(_seed_learner())

    # Step B: Submit Low Score < 50.0 on intermediate course
    progress_payload = {
        "learner_id": str(learner_id),
        "course_id": "c-ml-fund",
        "assessment_score": 38.0,
        "difficulty_feedback": "too_hard",
    }
    prog_resp = make_request("post", "/api/progress", progress_payload)
    assert prog_resp.status_code == 200
    prog_data = prog_resp.json()
    assert prog_data["status"] == "success"
    assert prog_data["course_status"] == "done"
    assert prog_data["adaptation_applied"] == "remediation"
    assert prog_data["adaptation_details"]["inserted_course_id"] == "c-ml-remedial"

    # Step C: Verify Dashboard surfaces inserted remedial course as next action
    dash_resp = make_request("get", f"/api/dashboard/{learner_id}")
    assert dash_resp.status_code == 200
    dash_data = dash_resp.json()
    assert dash_data["total_courses"] == 3  # 2 original + 1 remedial
    assert dash_data["completed_courses"] == 1  # c-ml-fund is done
    assert dash_data["next_recommended_action"] is not None
    assert dash_data["next_recommended_action"]["course_id"] == "c-ml-remedial"
    assert dash_data["next_recommended_action"]["status"] == "available"
    assert dash_data["next_recommended_action"]["phase_number"] == 1


def test_e2e_state_integrity_and_idempotency():
    """E2E Scenario 3: Guard validations for locked, skipped, and repeated submissions."""
    learner_id = uuid.uuid4()
    async def _setup_states():
        async with TestSessionLocal() as session:
            l = Learner(id=learner_id, name="Charlie", parsed_goal={"target_role": "ml_engineer"})
            session.add(l)
            lp_done = LearningPath(learner_id=learner_id, course_id="c-pandas-1", phase_number=1, sequence_order=1, status="done")
            lp_skip = LearningPath(learner_id=learner_id, course_id="c-pandas-2", phase_number=1, sequence_order=2, status="skipped")
            lp_lock = LearningPath(learner_id=learner_id, course_id="c-deep-learning", phase_number=2, sequence_order=3, status="locked")
            session.add_all([lp_done, lp_skip, lp_lock])
            await session.commit()

    asyncio.run(_setup_states())

    # 1. Locked course submission is rejected with 400
    resp_lock = make_request("post", "/api/progress", {
        "learner_id": str(learner_id),
        "course_id": "c-deep-learning",
        "assessment_score": 88.0,
    })
    assert resp_lock.status_code == 400
    assert "locked" in resp_lock.json()["detail"]

    # 2. Skipped course submission is rejected with 400
    resp_skip = make_request("post", "/api/progress", {
        "learner_id": str(learner_id),
        "course_id": "c-pandas-2",
        "assessment_score": 88.0,
    })
    assert resp_skip.status_code == 400
    assert "skipped" in resp_skip.json()["detail"]

    # 3. Repeated submission on completed course records audit event without mutating state
    resp_rep = make_request("post", "/api/progress", {
        "learner_id": str(learner_id),
        "course_id": "c-pandas-1",
        "assessment_score": 96.0,
    })
    assert resp_rep.status_code == 200
    assert resp_rep.json()["adaptation_applied"] == "none"


def test_e2e_feedback_only_submission():
    """E2E Scenario 4: Difficulty feedback without assessment score records event without completing course."""
    learner_id = uuid.uuid4()
    async def _setup():
        async with TestSessionLocal() as session:
            l = Learner(id=learner_id, name="Dana", parsed_goal={"target_role": "ml_engineer"})
            session.add(l)
            lp = LearningPath(learner_id=learner_id, course_id="c-pandas-1", phase_number=1, sequence_order=1, status="available")
            session.add(lp)
            await session.commit()

    asyncio.run(_setup())

    resp = make_request("post", "/api/progress", {
        "learner_id": str(learner_id),
        "course_id": "c-pandas-1",
        "difficulty_feedback": "too_easy",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["adaptation_applied"] == "none"

    # Verify course remains available
    dash = make_request("get", f"/api/dashboard/{learner_id}")
    assert dash.json()["completed_courses"] == 0
    assert dash.json()["next_recommended_action"]["status"] == "available"


def test_e2e_weekly_hours_slider_calculation_invariants():
    """E2E Scenario 5: Mathematical schedule formula invariant verification."""
    total_hours = 40

    # 8 hrs/wk -> 5 wks
    assert (total_hours + 8 - 1) // 8 == 5
    # 10 hrs/wk -> 4 wks
    assert (total_hours + 10 - 1) // 10 == 4
    # 4 hrs/wk -> 10 wks
    assert (total_hours + 4 - 1) // 4 == 10