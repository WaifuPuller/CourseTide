"""Unit tests for CourseTide Semantic Course Recommendation & Scoring."""

import pytest
import numpy as np
from unittest.mock import MagicMock

from backend.app.recommender.embeddings import (
    build_gap_query_text,
    compute_composite_score,
    RecommendedCourse,
)


def test_build_gap_query_text():
    """Verify gap query string formatting from canonical skill IDs."""
    query = build_gap_query_text(["ml_fund", "neural_nets", "deep_learning"])
    assert "Machine Learning Fundamentals" in query
    assert "Neural Network Architectures" in query
    assert "Deep Learning" in query


def test_composite_score_gap_recall_formulation():
    """Verify that multi-skill courses covering more gaps achieve higher gap recall scores."""
    gap_skills = ["ml_fund", "data_manip", "stats", "deep_learning"]  # total |G| = 4

    # Course A: Multi-skill covering 2 gaps (ml_fund, data_manip) + 1 non-gap (sql)
    # Total course skills = 3, covered = 2
    # S_gap = 2 / 4 = 0.50
    # S_pri = 1.0 (ml_fund in G)
    # S_sim = 0.80
    score_a, s_gap_a, covered_a = compute_composite_score(
        semantic_sim=0.80,
        course_skills=["ml_fund", "data_manip", "sql"],
        primary_skill="ml_fund",
        gap_skills=gap_skills,
    )
    assert covered_a == ["ml_fund", "data_manip"]
    assert s_gap_a == 0.50
    expected_score_a = round((0.50 * 0.80 + 0.35 * 0.50 + 0.15 * 1.0) * 100, 1)  # 0.40 + 0.175 + 0.15 = 0.725 -> 72.5
    assert score_a == expected_score_a

    # Course B: Single-skill covering 1 gap (ml_fund)
    # Total course skills = 1, covered = 1
    # S_gap = 1 / 4 = 0.25
    # S_pri = 1.0
    # S_sim = 0.80
    score_b, s_gap_b, covered_b = compute_composite_score(
        semantic_sim=0.80,
        course_skills=["ml_fund"],
        primary_skill="ml_fund",
        gap_skills=gap_skills,
    )
    assert covered_b == ["ml_fund"]
    assert s_gap_b == 0.25
    expected_score_b = round((0.50 * 0.80 + 0.35 * 0.25 + 0.15 * 1.0) * 100, 1)  # 0.40 + 0.0875 + 0.15 = 0.6375 -> 63.8
    assert score_b == expected_score_b

    # Confirmed: Multi-skill course covering more gaps ranks higher!
    assert score_a > score_b


def test_primary_skill_weighting():
    """Verify that primary skill alignment adds 0.15 weight when in gap set."""
    gap_skills = ["deep_learning"]

    # Course 1: primary skill matches gap
    score_1, _, _ = compute_composite_score(
        semantic_sim=0.70,
        course_skills=["deep_learning"],
        primary_skill="deep_learning",
        gap_skills=gap_skills,
    )

    # Course 2: secondary skill matches gap, but primary does not
    score_2, _, _ = compute_composite_score(
        semantic_sim=0.70,
        course_skills=["python", "deep_learning"],
        primary_skill="python",
        gap_skills=gap_skills,
    )

    # Course 1 has higher score due to primary alignment (0.15 boost)
    assert score_1 > score_2


@pytest.mark.asyncio
async def test_production_embedding_startup_failure_fails_fast():
    """Verify that in production mode, model load failure raises immediately and does NOT silently continue."""
    import asyncio
    from fastapi import FastAPI
    from unittest.mock import patch
    from backend.app.main import lifespan
    from backend.app.config import settings

    test_app = FastAPI(lifespan=lifespan)

    with patch("backend.app.config.settings.TESTING", False):
        with patch(
            "backend.app.recommender.embeddings.get_embed_model",
            side_effect=RuntimeError("Simulated HuggingFace weight download failure during startup"),
        ):
            # Lifespan startup must fail fast by propagating the exception
            with pytest.raises(RuntimeError) as exc:
                async with lifespan(test_app):
                    pass
            assert "Simulated HuggingFace weight download failure" in str(exc.value)


@pytest.mark.asyncio
async def test_testing_mode_skips_embedding_model_download():
    """Verify that in TESTING mode, lifespan sets embed_model = None without loading real weights."""
    from fastapi import FastAPI
    from unittest.mock import patch
    from backend.app.main import lifespan
    from backend.app.config import settings

    test_app = FastAPI(lifespan=lifespan)

    with patch("backend.app.config.settings.TESTING", True):
        with patch("backend.app.recommender.embeddings.get_embed_model") as mock_get_model:
            async with lifespan(test_app):
                assert test_app.state.embed_model is None
            mock_get_model.assert_not_called()


@pytest.mark.asyncio
async def test_legitimate_no_gap_returns_empty_recommendations():
    """Verify that a learner with 100% skill match (gap_skills == []) returns empty recommendations without using fallback vector."""
    from unittest.mock import AsyncMock
    from backend.app.recommender.skill_gap import detect_skill_gaps, TARGET_ROLES
    from backend.app.recommender.embeddings import recommend_courses_async

    # Select target role and supply all required skills
    target_role = "ml_engineer"
    all_required_skills = list(TARGET_ROLES[target_role]["required_skills"])

    # 1. Skill gap engine produces gap_skills == []
    gap_result = detect_skill_gaps(target_role=target_role, known_skills=all_required_skills)
    assert gap_result.gap_skills == []
    assert gap_result.match_percentage == 100.0

    # 2. Mock database session to verify it is not even queried
    mock_db = AsyncMock()

    # 3. Call recommend_courses_async
    recs = await recommend_courses_async(db=mock_db, gap_skills=gap_result.gap_skills)

    # 4. Confirm explicit empty list behavior
    assert recs == []
    mock_db.execute.assert_not_called()


def test_internal_pipeline_gap_query_embedding():
    """Verify that real internal pipeline output (canonical gap skills -> build_gap_query_text -> PrecomputedSkillEmbedder) produces valid 384-d normalized vector."""
    from backend.app.recommender.skill_gap import detect_skill_gaps
    from backend.app.recommender.embeddings import (
        build_gap_query_text,
        PrecomputedSkillEmbedder,
        SKILLS_MAP,
    )

    # 1. Simulate internal pipeline gap detection
    # Learner knows Python and SQL, wants ML Engineer role
    gap_result = detect_skill_gaps(target_role="ml_engineer", known_skills=["python", "sql"])
    assert len(gap_result.gap_skills) > 0
    assert "deep_learning" in gap_result.gap_skills

    # 2. Build gap query text using internal function
    query_text = build_gap_query_text(gap_result.gap_skills)
    assert "Curated courses and practical projects covering:" in query_text
    # Verify canonical human-readable names are included
    for s_id in gap_result.gap_skills:
        expected_name = SKILLS_MAP.get(s_id, s_id.replace("_", " ").title())
        assert expected_name in query_text

    # 3. Encode using PrecomputedSkillEmbedder
    embedder = PrecomputedSkillEmbedder()
    vecs = embedder.encode([query_text], normalize_embeddings=True)

    # 4. Assert vector properties
    assert vecs.shape == (1, 384)
    norm = np.linalg.norm(vecs[0])
    assert np.isclose(norm, 1.0, atol=1e-5)

    # 5. Confirm it is a meaningful semantic vector, not the single-basis fallback vector [1, 0, 0, ...]
    fallback_vector = np.zeros(384, dtype=np.float32)
    fallback_vector[0] = 1.0
    assert not np.allclose(vecs[0], fallback_vector)

