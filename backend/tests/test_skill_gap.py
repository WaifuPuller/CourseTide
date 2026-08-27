"""Unit tests for CourseTide Deterministic Skill-Gap Engine."""

import pytest
from backend.app.recommender.skill_gap import SkillGapError, SkillGapResult, detect_skill_gaps


def test_skill_gap_ml_engineer_novice():
    """Verify gap detection for complete beginner aiming for ML Engineer."""
    res = detect_skill_gaps("ml_engineer", known_skills=[])
    assert isinstance(res, SkillGapResult)
    assert res.target_role == "ml_engineer"
    assert res.role_name == "Machine Learning Engineer"
    assert res.total_required_count == 9
    assert res.known_count == 0
    assert res.gap_count == 9
    assert len(res.gap_skills) == 9
    assert res.match_percentage == 0.0
    assert "python" in res.gap_skills
    assert "mlops" in res.gap_skills


def test_skill_gap_ml_engineer_intermediate():
    """Verify gap detection for learner who knows Python, Stats, and Git."""
    res = detect_skill_gaps("ml_engineer", known_skills=["python", "stats", "git"])
    assert res.known_count == 3
    assert res.gap_count == 6
    assert "python" not in res.gap_skills
    assert "stats" not in res.gap_skills
    assert "git" not in res.gap_skills
    assert "ml_fund" in res.gap_skills
    assert "deep_learning" in res.gap_skills
    assert "neural_nets" in res.gap_skills
    assert "mlops" in res.gap_skills
    assert res.match_percentage == round(3 / 9 * 100, 1)


def test_skill_gap_data_scientist():
    """Verify gap detection for Data Scientist role."""
    res = detect_skill_gaps("data_scientist", known_skills=["python", "sql", "stats"])
    assert res.target_role == "data_scientist"
    assert res.total_required_count == 7
    assert res.known_count == 3
    assert res.gap_count == 4
    assert "data_manip" in res.gap_skills
    assert "dataviz" in res.gap_skills
    assert "ml_fund" in res.gap_skills
    assert "feat_eng" in res.gap_skills


def test_skill_gap_mlops_engineer():
    """Verify gap detection for MLOps Engineer role."""
    res = detect_skill_gaps("mlops_engineer", known_skills=["python", "git", "deploy_devops"])
    assert res.target_role == "mlops_engineer"
    assert res.total_required_count == 5
    assert res.known_count == 2  # python, git (deploy_devops is optional)
    assert res.gap_count == 3
    assert "ml_fund" in res.gap_skills
    assert "deep_learning" in res.gap_skills
    assert "mlops" in res.gap_skills


def test_skill_gap_invalid_role():
    """Verify error raised for invalid role."""
    with pytest.raises(SkillGapError) as exc:
        detect_skill_gaps("fullstack_dev", known_skills=["python"])
    assert exc.value.status_code == 422
    assert "not found in taxonomy" in str(exc.value)
