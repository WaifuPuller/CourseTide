"""Integration tests for CourseTide API endpoints using isolated in-memory SQLite database."""

import asyncio
import unittest.mock
import uuid
import pytest
import httpx
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.main import app
from backend.app.config import settings
from backend.app.database import Base, get_db
from backend.app.models import Course, CourseSkill, Skill

# Enable mock LLM mode for unit/integration testing
settings.TESTING = True

# Test database engine: Isolated in-memory SQLite (Never connects to Neon)
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
    """Create tables and seed minimal test catalog data into isolated SQLite."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        # Seed test skills
        s1 = Skill(id="python", name="Python Programming", domain="ml")
        s2 = Skill(id="stats", name="Statistics & Probability", domain="ml")
        s3 = Skill(id="ml_fund", name="Machine Learning Fundamentals", domain="ml")
        s4 = Skill(id="deep_learning", name="Deep Learning", domain="ml")
        s5 = Skill(id="mlops", name="Model Deployment & MLOps", domain="ml")
        session.add_all([s1, s2, s3, s4, s5])

        # Seed test MVP courses with mock embeddings
        c1 = Course(
            id="test-course-ml",
            title="Practical Machine Learning",
            difficulty="intermediate",
            duration_hours=20,
            resource_type="course",
            domain="ml",
            is_mvp=True,
            embedding=[0.1] * 384,
        )
        c2 = Course(
            id="test-course-dl",
            title="Deep Learning Specialization",
            difficulty="advanced",
            duration_hours=40,
            resource_type="course",
            domain="ml",
            is_mvp=True,
            embedding=[0.2] * 384,
        )
        session.add_all([c1, c2])

        # Seed course skills
        cs1 = CourseSkill(course_id="test-course-ml", skill_id="ml_fund", is_primary=True)
        cs2 = CourseSkill(course_id="test-course-dl", skill_id="deep_learning", is_primary=True)
        session.add_all([cs1, cs2])

        await session.commit()


async def _override_get_db():
    """Dependency override providing isolated SQLite test sessions."""
    async with TestSessionLocal() as session:
        yield session


def make_request(method: str, url: str, json: dict = None):
    """Helper to run async HTTP requests against ASGI app synchronously with isolated DB."""
    async def _call():
        await _setup_test_db()
        app.dependency_overrides[get_db] = _override_get_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                if method.lower() == "get":
                    return await client.get(url)
                elif method.lower() == "post":
                    return await client.post(url, json=json)
        finally:
            app.dependency_overrides.pop(get_db, None)
    return asyncio.run(_call())


def test_health_check():
    """Verify GET /health returns 200 and healthy status."""
    response = make_request("get", "/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "coursetide-api"


def test_profile_creation_and_recommendation_isolated_db():
    """Verify POST /api/profile parses goal, detects gaps, recommends courses, and persists in isolated SQLite."""
    payload = {
        "name": "Alex",
        "email": "alex@coursetide.io",
        "goal": "I want to become a Machine Learning Engineer. I have Python and Statistics background.",
        "weekly_hours": 10,
    }

    response = make_request("post", "/api/profile", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["target_role"] == "ml_engineer"
    assert data["role_name"] == "Machine Learning Engineer"
    assert "python" in data["known_skills"]
    assert "stats" in data["known_skills"]
    assert "deep_learning" in data["gap_skills"]
    assert "mlops" in data["gap_skills"]
    assert data["weekly_hours"] == 10
    assert data["timeframe_months"] == 6
    assert "recommended_courses" in data

    learner_id = data["learner_id"]

    # Verify GET /api/skill-gap/{learner_id} queries the same isolated test database
    async def _check_skill_gap():
        app.dependency_overrides[get_db] = _override_get_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                gap_resp = await client.get(f"/api/skill-gap/{learner_id}")
                assert gap_resp.status_code == 200
                gap_data = gap_resp.json()
                assert gap_data["learner_id"] == learner_id
                assert gap_data["target_role"] == "ml_engineer"
                assert "deep_learning" in gap_data["gap_skills"]
        finally:
            app.dependency_overrides.pop(get_db, None)

    asyncio.run(_check_skill_gap())


def test_profile_with_unrecognized_skills_isolated_db():
    """Verify that unrecognized skills (like linear algebra and redux) are returned in profile response."""
    payload = {
        "name": "Jordan",
        "goal": "I want to be a Data Scientist. I know Python, linear algebra, and redux.",
        "weekly_hours": 8,
    }

    response = make_request("post", "/api/profile", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["target_role"] == "data_scientist"
    assert "python" in data["known_skills"]
    assert "linear algebra" in data["unrecognized_skills"]
    assert "redux" in data["unrecognized_skills"]


def test_profile_creation_db_commit_failure_raises_500():
    """Verify that a database commit failure triggers rollback and returns HTTP 500 without false success."""
    payload = {
        "name": "FailureTest",
        "goal": "I want to become a Machine Learning Engineer with Python and Statistics.",
        "weekly_hours": 10,
    }

    async def _call_with_commit_failure():
        await _setup_test_db()
        app.dependency_overrides[get_db] = _override_get_db

        # Patch AsyncSession.commit to simulate database connection/transaction failure
        with unittest.mock.patch.object(
            AsyncSession,
            "commit",
            side_effect=Exception("Simulated connection drop during database commit"),
        ):
            try:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    return await client.post("/api/profile", json=payload)
            finally:
                app.dependency_overrides.pop(get_db, None)

    response = asyncio.run(_call_with_commit_failure())
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Failed to persist learner profile due to an internal database error."
    # Ensure no false success learner profile attributes are returned
    assert "learner_id" not in data
    assert "recommended_courses" not in data


def test_roadmap_skeleton():
    """Verify GET /api/roadmap/{learner_id} endpoint."""
    test_id = str(uuid.uuid4())
    response = make_request("get", f"/api/roadmap/{test_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["learner_id"] == test_id


def test_explain_skeleton():
    """Verify GET /api/explain/{learner_id}/{course_id} endpoint."""
    test_id = str(uuid.uuid4())
    response = make_request("get", f"/api/explain/{test_id}/cs50-python")
    assert response.status_code == 200
    data = response.json()
    assert data["course_id"] == "cs50-python"


def test_progress_skeleton():
    """Verify POST /api/progress endpoint."""
    test_id = str(uuid.uuid4())
    response = make_request(
        "post",
        "/api/progress",
        json={"learner_id": test_id, "course_id": "cs50-python", "assessment_score": 88.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["assessment_score"] == 88.0


def test_dashboard_skeleton():
    """Verify GET /api/dashboard/{learner_id} endpoint."""
    test_id = str(uuid.uuid4())
    response = make_request("get", f"/api/dashboard/{test_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["learner_id"] == test_id
