"""Targeted unit and integration tests for CourseTide Grounded Explainer (Day 3 Step 4).

Tests the ordered Gemini model fallback chain, strict prompt grounding, structured
output validation, and error classification using isolated SQLite and mocked HTTP.
"""

import asyncio
import json
import unittest.mock
import uuid
import pytest
import httpx
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.main import app
from backend.app.config import settings
from backend.app.database import Base, get_db
from backend.app.models import Course, CourseSkill, Learner, LearningPath, Skill
from backend.app.recommender.explainer import (
    DEFAULT_MODEL_CHAIN,
    ExplanationContext,
    ExplanationError,
    ExplanationUnavailableError,
    build_grounding_prompt,
    generate_explanation_async,
    is_retryable_error,
)

# Force testing mode
settings.TESTING = True
settings.GEMINI_API_KEY = "test_mock_gemini_api_key"

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
        # Seed skills
        s1 = Skill(id="python", name="Python Programming", domain="ml")
        s2 = Skill(id="data_manip", name="Data Manipulation with Pandas", domain="ml")
        s3 = Skill(id="ml_fund", name="Machine Learning Fundamentals", domain="ml")
        session.add_all([s1, s2, s3])

        # Seed course
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
        session.add(c1)

        # Seed course_skills
        cs1 = CourseSkill(course_id="intro-to-pandas", skill_id="data_manip", is_primary=True)
        session.add(cs1)

        await session.commit()


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


def run_sync(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def ensure_mock_api_key():
    settings.GEMINI_API_KEY = "test_mock_gemini_api_key"
    yield


# ---------------------------------------------------------------------------
# 1. GROUNDING PROMPT & CONTEXT INTEGRITY TESTS
# ---------------------------------------------------------------------------

def test_grounding_prompt_contains_all_factual_fields():
    """Verify that build_grounding_prompt includes all factual context and negative constraints."""
    ctx = ExplanationContext(
        learner_id="test_learner_123",
        target_role="ml_engineer",
        role_name="Machine Learning Engineer",
        known_skills=["python", "stats"],
        gap_skills=["data_manip", "ml_fund"],
        course_id="intro-to-pandas",
        course_title="Pandas for Data Analysis",
        difficulty="beginner",
        duration_hours=10,
        primary_skill="data_manip",
        covered_gap_skills=["data_manip"],
        phase_number=1,
        phase_name="Phase 1: Foundations",
        upstream_prerequisites=["python"],
        downstream_skills=["ml_fund"],
    )

    prompt = build_grounding_prompt(ctx)

    # 1. Check factual context inclusions
    assert "Machine Learning Engineer" in prompt
    assert "Pandas for Data Analysis" in prompt
    assert "data_manip" in prompt
    assert "Phase 1: Foundations" in prompt
    assert "python" in prompt
    assert "ml_fund" in prompt

    # 2. Check negative constraints
    assert "Do NOT mention certifications" in prompt
    assert "Do NOT invent prerequisites" in prompt
    assert "Return ONLY a valid JSON object" in prompt


# ---------------------------------------------------------------------------
# 2. GEMINI MODEL FALLBACK CHAIN UNIT TESTS
# ---------------------------------------------------------------------------

def test_primary_model_success():
    """Verify that primary model success returns valid explanation on the first call without touching fallbacks."""
    async def _test():
        ctx = ExplanationContext(
            learner_id="test_learner",
            target_role="ml_engineer",
            role_name="Machine Learning Engineer",
            course_id="intro-to-pandas",
            course_title="Pandas for Data Analysis",
            primary_skill="data_manip",
        )

        mock_resp = httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps({"explanation": "Primary model grounded explanation."})}
                            ]
                        }
                    }
                ]
            },
            request=httpx.Request("POST", "http://test"),
        )

        with unittest.mock.patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
            res = await generate_explanation_async(
                ctx,
                model_chain=["gemini-3.7-flash", "gemini-2.5-flash", "gemini-2.0-flash"],
                api_key="mock_key",
            )

            assert res == "Primary model grounded explanation."
            assert mock_post.call_count == 1
            # Verify primary model was used in URL
            assert "gemini-3.7-flash" in str(mock_post.call_args[0][0])

    run_sync(_test())


def test_primary_retryable_failure_triggers_fallback_1():
    """Verify that when primary model returns 429 Rate Limit, Fallback 1 is called and succeeds."""
    async def _test():
        ctx = ExplanationContext(
            learner_id="test_learner",
            target_role="ml_engineer",
            role_name="Machine Learning Engineer",
            course_id="intro-to-pandas",
            course_title="Pandas for Data Analysis",
            primary_skill="data_manip",
        )

        primary_fail = httpx.Response(
            status_code=429,
            text="Resource Exhausted (Rate Limit)",
            request=httpx.Request("POST", "http://test"),
        )
        fallback_success = httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps({"explanation": "Fallback 1 model explanation."})}
                            ]
                        }
                    }
                ]
            },
            request=httpx.Request("POST", "http://test"),
        )

        with unittest.mock.patch("httpx.AsyncClient.post", side_effect=[primary_fail, fallback_success]) as mock_post:
            res = await generate_explanation_async(
                ctx,
                model_chain=["gemini-3.7-flash", "gemini-2.5-flash", "gemini-2.0-flash"],
                api_key="mock_key",
            )

            assert res == "Fallback 1 model explanation."
            assert mock_post.call_count == 2
            assert "gemini-3.7-flash" in str(mock_post.call_args_list[0][0][0])
            assert "gemini-2.5-flash" in str(mock_post.call_args_list[1][0][0])

    run_sync(_test())


def test_primary_and_fallback_1_fail_triggers_fallback_2():
    """Verify that when primary (429) and fallback 1 (503) fail, fallback 2 succeeds."""
    async def _test():
        ctx = ExplanationContext(
            learner_id="test_learner",
            target_role="ml_engineer",
            role_name="Machine Learning Engineer",
            course_id="intro-to-pandas",
            course_title="Pandas for Data Analysis",
            primary_skill="data_manip",
        )

        fail_1 = httpx.Response(status_code=429, text="Rate limit", request=httpx.Request("POST", "http://test"))
        fail_2 = httpx.Response(status_code=503, text="Service Unavailable", request=httpx.Request("POST", "http://test"))
        success_3 = httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps({"explanation": "Fallback 2 model explanation."})}
                            ]
                        }
                    }
                ]
            },
            request=httpx.Request("POST", "http://test"),
        )

        with unittest.mock.patch("httpx.AsyncClient.post", side_effect=[fail_1, fail_2, success_3]) as mock_post:
            res = await generate_explanation_async(
                ctx,
                model_chain=["gemini-3.7-flash", "gemini-2.5-flash", "gemini-2.0-flash"],
                api_key="mock_key",
            )

            assert res == "Fallback 2 model explanation."
            assert mock_post.call_count == 3
            assert "gemini-2.0-flash" in str(mock_post.call_args_list[2][0][0])

    run_sync(_test())


def test_malformed_json_triggers_next_model_fallback():
    """Verify that malformed JSON in primary response triggers fallback to model 2."""
    async def _test():
        ctx = ExplanationContext(
            learner_id="test_learner",
            target_role="ml_engineer",
            role_name="Machine Learning Engineer",
            course_id="intro-to-pandas",
            course_title="Pandas for Data Analysis",
            primary_skill="data_manip",
        )

        malformed_resp = httpx.Response(
            status_code=200,
            json={"candidates": [{"content": {"parts": [{"text": "not valid json"}]}}]},
            request=httpx.Request("POST", "http://test"),
        )
        valid_fallback = httpx.Response(
            status_code=200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps({"explanation": "Valid after malformed."})}]}}]},
            request=httpx.Request("POST", "http://test"),
        )

        with unittest.mock.patch("httpx.AsyncClient.post", side_effect=[malformed_resp, valid_fallback]) as mock_post:
            res = await generate_explanation_async(
                ctx,
                model_chain=["gemini-3.7-flash", "gemini-2.5-flash"],
                api_key="mock_key",
            )

            assert res == "Valid after malformed."
            assert mock_post.call_count == 2

    run_sync(_test())


def test_all_models_fail_raises_explanation_unavailable_error():
    """Verify that when all configured models fail with retryable availability errors, ExplanationUnavailableError is raised."""
    async def _test():
        ctx = ExplanationContext(
            learner_id="test_learner",
            target_role="ml_engineer",
            role_name="Machine Learning Engineer",
            course_id="intro-to-pandas",
            course_title="Pandas for Data Analysis",
            primary_skill="data_manip",
        )

        fail_1 = httpx.Response(status_code=429, text="Rate limit", request=httpx.Request("POST", "http://test"))
        fail_2 = httpx.Response(status_code=503, text="Service Unavailable", request=httpx.Request("POST", "http://test"))
        fail_3 = httpx.Response(status_code=500, text="Internal Error", request=httpx.Request("POST", "http://test"))

        with unittest.mock.patch("httpx.AsyncClient.post", side_effect=[fail_1, fail_2, fail_3]) as mock_post:
            with pytest.raises(ExplanationUnavailableError) as exc_info:
                await generate_explanation_async(
                    ctx,
                    model_chain=["gemini-3.7-flash", "gemini-2.5-flash", "gemini-2.0-flash"],
                    api_key="mock_key",
                )

            assert "temporarily unavailable across all configured models" in str(exc_info.value)
            assert exc_info.value.status_code == 503
            assert mock_post.call_count == 3

    run_sync(_test())


def test_non_retryable_error_fails_immediately_without_cascading():
    """Verify that a non-retryable error (e.g. HTTP 400 Bad Request) fails fast without trying fallback models."""
    async def _test():
        ctx = ExplanationContext(
            learner_id="test_learner",
            target_role="ml_engineer",
            role_name="Machine Learning Engineer",
            course_id="intro-to-pandas",
            course_title="Pandas for Data Analysis",
            primary_skill="data_manip",
        )

        bad_request = httpx.Response(
            status_code=400,
            text="Bad Request: Malformed Payload",
            request=httpx.Request("POST", "http://test"),
        )

        with unittest.mock.patch("httpx.AsyncClient.post", return_value=bad_request) as mock_post:
            with pytest.raises(ExplanationError) as exc_info:
                await generate_explanation_async(
                    ctx,
                    model_chain=["gemini-3.7-flash", "gemini-2.5-flash", "gemini-2.0-flash"],
                    api_key="mock_key",
                )

            # Call count must be exactly 1: no cascading on 400 Bad Request
            assert mock_post.call_count == 1
            assert "Non-Retryable Error [400]" in str(exc_info.value)

    run_sync(_test())


def test_identical_context_sent_to_all_attempted_models():
    """Verify that every attempted model in the fallback chain receives identical JSON payloads."""
    async def _test():
        ctx = ExplanationContext(
            learner_id="test_learner_456",
            target_role="data_scientist",
            role_name="Data Scientist",
            known_skills=["python"],
            gap_skills=["stats", "ml_fund"],
            course_id="intro-to-pandas",
            course_title="Pandas for Data Analysis",
            primary_skill="data_manip",
        )

        fail_1 = httpx.Response(status_code=429, text="Rate limit", request=httpx.Request("POST", "http://test"))
        success_2 = httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps({"explanation": "Valid grounded text."})}]}}
                ]
            },
            request=httpx.Request("POST", "http://test"),
        )

        with unittest.mock.patch("httpx.AsyncClient.post", side_effect=[fail_1, success_2]) as mock_post:
            await generate_explanation_async(
                ctx,
                model_chain=["gemini-3.7-flash", "gemini-2.5-flash"],
                api_key="mock_key",
            )

            # Check that both calls had identical payload body
            payload_1 = mock_post.call_args_list[0][1]["json"]
            payload_2 = mock_post.call_args_list[1][1]["json"]
            assert payload_1 == payload_2
            assert "Data Scientist" in payload_1["contents"][0]["parts"][0]["text"]

    run_sync(_test())


# ---------------------------------------------------------------------------
# 3. FASTAPI INTEGRATION TESTS (GET /api/explain/{learner_id}/{course_id})
# ---------------------------------------------------------------------------

def test_api_explain_valid_learner_and_course():
    """Verify that GET /api/explain/{learner_id}/{course_id} returns 200 with structured ExplanationResponse."""
    async def _test():
        await _setup_test_db()
        learner_id = uuid.uuid4()
        parsed_goal = {
            "target_role": "ml_engineer",
            "role_name": "Machine Learning Engineer",
            "known_skills": ["python"],
            "gap_skills": ["data_manip", "ml_fund"],
        }

        async with TestSessionLocal() as session:
            learner = Learner(
                id=learner_id,
                name="ExplainTester",
                goal="I want to learn Pandas.",
                parsed_goal=parsed_goal,
                weekly_hours=8,
            )
            session.add(learner)

            lp = LearningPath(
                learner_id=learner_id,
                phase_number=1,
                course_id="intro-to-pandas",
                status="available",
                sequence_order=1,
            )
            session.add(lp)
            await session.commit()

        mock_resp = httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {"explanation": "This course closes the data_manip gap in Phase 1."}
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
            request=httpx.Request("POST", "http://test"),
        )

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with unittest.mock.patch("httpx.AsyncClient.post", return_value=mock_resp):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/api/explain/{learner_id}/intro-to-pandas")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["learner_id"] == str(learner_id)
        assert data["course_id"] == "intro-to-pandas"
        assert data["course_title"] == "Pandas for Data Analysis"
        assert data["primary_skill"] == "data_manip"
        assert data["phase_number"] == 1
        assert "closes the data_manip gap" in data["explanation"]

    run_sync(_test())


def test_api_explain_unpersisted_learning_path_computes_phase_dynamically():
    """Verify that when a course is not yet in learning_paths, phase is computed dynamically."""
    async def _test():
        await _setup_test_db()
        learner_id = uuid.uuid4()
        parsed_goal = {
            "target_role": "ml_engineer",
            "role_name": "Machine Learning Engineer",
            "known_skills": ["python"],
            "gap_skills": ["data_manip"],
        }

        async with TestSessionLocal() as session:
            learner = Learner(
                id=learner_id,
                name="ExplainDynamicTester",
                goal="I want to learn Pandas.",
                parsed_goal=parsed_goal,
                weekly_hours=8,
            )
            session.add(learner)
            await session.commit()

        mock_resp = httpx.Response(
            status_code=200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps({"explanation": "Dynamic phase explanation."})}]}}]},
            request=httpx.Request("POST", "http://test"),
        )

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with unittest.mock.patch("httpx.AsyncClient.post", return_value=mock_resp):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/api/explain/{learner_id}/intro-to-pandas")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["phase_number"] == 1
        assert data["phase_name"] == "Phase 1: Foundations"

    run_sync(_test())


def test_api_explain_unknown_learner_returns_404():
    """Verify that an unknown learner ID returns HTTP 404."""
    async def _test():
        await _setup_test_db()
        random_learner_id = uuid.uuid4()

        app.dependency_overrides[get_db] = _override_get_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/api/explain/{random_learner_id}/intro-to-pandas")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404
        assert f"Learner with ID '{random_learner_id}' not found" in resp.json()["detail"]

    run_sync(_test())


def test_api_explain_unknown_course_returns_404():
    """Verify that an unknown course ID returns HTTP 404."""
    async def _test():
        await _setup_test_db()
        learner_id = uuid.uuid4()
        parsed_goal = {"target_role": "ml_engineer", "known_skills": ["python"], "gap_skills": ["data_manip"]}

        async with TestSessionLocal() as session:
            learner = Learner(id=learner_id, goal="Test", parsed_goal=parsed_goal, weekly_hours=8)
            session.add(learner)
            await session.commit()

        app.dependency_overrides[get_db] = _override_get_db
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/api/explain/{learner_id}/non-existent-course-123")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404
        assert "Course with ID 'non-existent-course-123' not found" in resp.json()["detail"]

    run_sync(_test())


def test_api_explain_all_models_unavailable_returns_503():
    """Verify that when all Gemini models fail with availability errors, API returns HTTP 503."""
    async def _test():
        await _setup_test_db()
        learner_id = uuid.uuid4()
        parsed_goal = {"target_role": "ml_engineer", "known_skills": ["python"], "gap_skills": ["data_manip"]}

        async with TestSessionLocal() as session:
            learner = Learner(id=learner_id, goal="Test", parsed_goal=parsed_goal, weekly_hours=8)
            session.add(learner)
            await session.commit()

        fail_resp = httpx.Response(status_code=429, text="Rate limit", request=httpx.Request("POST", "http://test"))

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with unittest.mock.patch("httpx.AsyncClient.post", return_value=fail_resp):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get(f"/api/explain/{learner_id}/intro-to-pandas")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 503
        assert "Explanation service is temporarily unavailable" in resp.json()["detail"]

    run_sync(_test())
