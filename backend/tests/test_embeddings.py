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
