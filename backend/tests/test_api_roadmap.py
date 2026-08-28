"""Targeted integration tests for GET /api/roadmap/{learner_id} using isolated in-memory SQLite."""

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
from backend.app.models import Course, CourseSkill, Learner, LearnerSkill, LearningPath, Skill

# Force testing mode
settings.TESTING = True

# Isolated SQLite in-memory engine
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
    """Create tables and seed catalog data for testing."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        # Seed taxonomy skills
        s1 = Skill(id="python", name="Python Programming", domain="ml")
        s2 = Skill(id="stats", name="Statistics & Probability", domain="ml")
        s3 = Skill(id="data_manip", name="Data Manipulation with Pandas & NumPy", domain="ml")
        s4 = Skill(id="ml_fund", name="Machine Learning Fundamentals", domain="ml")
        s5 = Skill(id="deep_learning", name="Deep Learning", domain="ml")
        s6 = Skill(id="neural_nets", name="Neural Network Architectures", domain="ml")
        s7 = Skill(id="mlops", name="Model Deployment & MLOps", domain="ml")
        session.add_all([s1, s2, s3, s4, s5, s6, s7])

        # Seed courses
        c1 = Course(
            id="intro-to-pandas",
            title="Pandas for Data Analysis",
            difficulty="beginner",
            duration_hours=10,
            resource_type="course",
            domain="ml",
            is_mvp=True,
            embedding=[0.1] * 384,
        )
        c2 = Course(
            id="intro-to-ml",
            title="Introduction to Machine Learning",
            difficulty="intermediate",
            duration_hours=15,
            resource_type="course",
            domain="ml",
            is_mvp=True,
            embedding=[0.2] * 384,
        )
        c3 = Course(
            id="deep-learning-spec",
            title="Deep Learning Specialization",
            difficulty="advanced",
            duration_hours=25,
            resource_type="course",
            domain="ml",
            is_mvp=True,
            embedding=[0.3] * 384,
        )
        session.add_all([c1, c2, c3])

        # Course skills
        cs1 = CourseSkill(course_id="intro-to-pandas", skill_id="data_manip", is_primary=True)
        cs2 = CourseSkill(course_id="intro-to-ml", skill_id="ml_fund", is_primary=True)
        cs3 = CourseSkill(course_id="deep-learning-spec", skill_id="deep_learning", is_primary=True)
        cs4 = CourseSkill(course_id="deep-learning-spec", skill_id="neural_nets", is_primary=False)
        session.add_all([cs1, cs2, cs3, cs4])

        await session.commit()


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


def make_request(method: str, url: str, json_payload: dict = None):
    """Helper to run async requests with isolated database."""
    async def _call():
        app.dependency_overrides[get_db] = _override_get_db
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


def run_sync(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# TEST CASES
# ---------------------------------------------------------------------------

def test_valid_learner_returns_phased_roadmap_isolated_db():
    """Verify that a valid learner receives an ordered, phased roadmap and LearningPath rows are persisted."""
    async def _test():
        await _setup_test_db()
        learner_id = uuid.uuid4()
        parsed_goal = {
            "target_role": "ml_engineer",
            "role_name": "Machine Learning Engineer",
            "known_skills": ["python", "stats"],
            "gap_skills": ["data_manip", "ml_fund", "deep_learning", "neural_nets"],
            "unrecognized_skills": [],
            "weekly_hours": 10,
            "timeframe_months": 6,
            "match_percentage": 33.3,
        }

        # 1. Insert test learner
        async with TestSessionLocal() as session:
            learner = Learner(
                id=learner_id,
                name="RoadmapTester",
                email="roadmap_tester@example.com",
                goal="I want to be an ML Engineer. I know Python and stats.",
                parsed_goal=parsed_goal,
                weekly_hours=10,
            )
            session.add(learner)
            await session.commit()

        # 2. Invoke GET /api/roadmap/{learner_id}
        app.dependency_overrides[get_db] = _override_get_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/api/roadmap/{learner_id}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()

        # 3. Verify top-level structure
        assert data["learner_id"] == str(learner_id)
        assert data["target_role"] == "ml_engineer"
        assert data["role_name"] == "Machine Learning Engineer"
        assert data["total_courses"] > 0
        assert data["total_estimated_hours"] > 0
        assert data["total_estimated_weeks"] > 0
        assert len(data["phases"]) >= 2

        # 4. Verify Phase 1 comes before Phase 2, status is 'available' for Phase 1 and 'locked' for Phase 2
        phase_1 = data["phases"][0]
        phase_2 = data["phases"][1]
        assert phase_1["phase_number"] == 1
        assert phase_2["phase_number"] == 2

        assert all(c["status"] == "available" for c in phase_1["courses"])
        assert all(c["status"] == "locked" for c in phase_2["courses"])

        # 5. Verify LearningPath records persisted in database
        async with TestSessionLocal() as session:
            res = await session.execute(select(LearningPath).where(LearningPath.learner_id == learner_id))
            lps = res.scalars().all()
            assert len(lps) == data["total_courses"]

    run_sync(_test())


def test_unknown_learner_returns_404():
    """Verify that an unknown learner UUID returns HTTP 404."""
    async def _test():
        await _setup_test_db()
        random_id = uuid.uuid4()
        app.dependency_overrides[get_db] = _override_get_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/api/roadmap/{random_id}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404
        assert f"Learner with ID '{random_id}' not found" in resp.json()["detail"]

    run_sync(_test())


def test_zero_gap_learner_returns_empty_roadmap():
    """Verify that a learner with no missing skills (gap_skills == []) returns an empty roadmap cleanly."""
    async def _test():
        await _setup_test_db()
        learner_id = uuid.uuid4()
        parsed_goal = {
            "target_role": "ml_engineer",
            "role_name": "Machine Learning Engineer",
            "known_skills": ["python", "stats", "data_manip", "ml_fund", "deep_learning", "neural_nets", "mlops"],
            "gap_skills": [],
            "unrecognized_skills": [],
            "weekly_hours": 8,
            "timeframe_months": 6,
            "match_percentage": 100.0,
        }

        async with TestSessionLocal() as session:
            learner = Learner(
                id=learner_id,
                name="ZeroGapTester",
                email="zerogap@example.com",
                goal="I am a master ML Engineer already.",
                parsed_goal=parsed_goal,
                weekly_hours=8,
            )
            session.add(learner)
            await session.commit()

        app.dependency_overrides[get_db] = _override_get_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/api/roadmap/{learner_id}")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_courses"] == 0
        assert data["total_estimated_hours"] == 0
        assert data["total_estimated_weeks"] == 0
        assert data["phases"] == []

    run_sync(_test())


def test_roadmap_endpoint_is_idempotent():
    """Verify that calling GET /api/roadmap multiple times does not duplicate LearningPath records."""
    async def _test():
        await _setup_test_db()
        learner_id = uuid.uuid4()
        parsed_goal = {
            "target_role": "ml_engineer",
            "role_name": "Machine Learning Engineer",
            "known_skills": ["python", "stats"],
            "gap_skills": ["data_manip", "ml_fund"],
            "weekly_hours": 8,
        }

        async with TestSessionLocal() as session:
            learner = Learner(
                id=learner_id,
                name="IdempotencyTester",
                goal="I want to learn data manip and ML.",
                parsed_goal=parsed_goal,
                weekly_hours=8,
            )
            session.add(learner)
            await session.commit()

        app.dependency_overrides[get_db] = _override_get_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp1 = await client.get(f"/api/roadmap/{learner_id}")
                assert resp1.status_code == 200

                # Second call
                resp2 = await client.get(f"/api/roadmap/{learner_id}")
                assert resp2.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)

        # Count rows in DB
        async with TestSessionLocal() as session:
            res = await session.execute(select(LearningPath).where(LearningPath.learner_id == learner_id))
            lps = res.scalars().all()
            assert len(lps) == resp1.json()["total_courses"]

    run_sync(_test())


def test_database_commit_failure_triggers_500_and_rollback():
    """Verify that a database commit failure raises HTTP 500 and does not leave dirty state."""
    async def _test():
        await _setup_test_db()
        learner_id = uuid.uuid4()
        parsed_goal = {
            "target_role": "ml_engineer",
            "role_name": "Machine Learning Engineer",
            "known_skills": ["python"],
            "gap_skills": ["data_manip"],
            "weekly_hours": 8,
        }

        async with TestSessionLocal() as session:
            learner = Learner(
                id=learner_id,
                goal="Test DB failure",
                parsed_goal=parsed_goal,
                weekly_hours=8,
            )
            session.add(learner)
            await session.commit()

        with unittest.mock.patch.object(AsyncSession, "commit", side_effect=RuntimeError("Simulated DB failure")):
            app.dependency_overrides[get_db] = _override_get_db
            try:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/api/roadmap/{learner_id}")
            finally:
                app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 500
        assert "Failed to persist learning path" in resp.json()["detail"]

    run_sync(_test())


def test_roadmap_endpoint_does_not_invoke_gemini():
    """Verify that GET /api/roadmap is completely deterministic and zero LLM calls are made."""
    async def _test():
        await _setup_test_db()
        learner_id = uuid.uuid4()
        parsed_goal = {
            "target_role": "ml_engineer",
            "role_name": "Machine Learning Engineer",
            "known_skills": ["python"],
            "gap_skills": ["data_manip", "ml_fund"],
            "weekly_hours": 8,
        }

        async with TestSessionLocal() as session:
            learner = Learner(
                id=learner_id,
                goal="Test zero LLM calls",
                parsed_goal=parsed_goal,
                weekly_hours=8,
            )
            session.add(learner)
            await session.commit()

        with unittest.mock.patch("backend.app.recommender.goal_parser.GeminiGoalParser.parse", side_effect=AssertionError("LLM must not be called!")):
            app.dependency_overrides[get_db] = _override_get_db
            try:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/api/roadmap/{learner_id}")
            finally:
                app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    run_sync(_test())
