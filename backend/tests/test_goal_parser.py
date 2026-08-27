"""Unit tests for CourseTide Goal Parser & Skill Normalization."""

import pytest
from unittest.mock import patch, MagicMock

from backend.app.recommender.goal_parser import (
    GoalParsingError,
    LLMConfigurationError,
    ParsedGoal,
    normalize_role,
    normalize_skill,
    parse_goal,
    SKILL_ALIASES,
    ROLES_TAXONOMY,
    SKILLS_TAXONOMY,
)


def test_taxonomy_loaded():
    """Verify that skills and roles taxonomies are loaded from data/."""
    assert len(SKILLS_TAXONOMY) == 22
    assert "python" in SKILLS_TAXONOMY
    assert len(ROLES_TAXONOMY) == 3
    assert "ml_engineer" in ROLES_TAXONOMY
    assert "data_scientist" in ROLES_TAXONOMY
    assert "mlops_engineer" in ROLES_TAXONOMY


def test_normalize_role():
    """Verify role normalization across aliases."""
    assert normalize_role("ml_engineer") == "ml_engineer"
    assert normalize_role("Machine Learning Engineer") == "ml_engineer"
    assert normalize_role("ML Engineer") == "ml_engineer"
    assert normalize_role("mle") == "ml_engineer"
    assert normalize_role("Data Scientist") == "data_scientist"
    assert normalize_role("data science") == "data_scientist"
    assert normalize_role("MLOps") == "mlops_engineer"
    assert normalize_role("mlops engineer") == "mlops_engineer"
    assert normalize_role("Frontend Developer") is None
    assert normalize_role("Unknown Role") is None


def test_normalize_skill_curated_aliases():
    """Verify curated alias mappings against canonical 22-skill taxonomy."""
    # Data manipulation
    assert normalize_skill("pandas") == "data_manip"
    assert normalize_skill("numpy") == "data_manip"
    assert normalize_skill("data manipulation") == "data_manip"
    assert normalize_skill("data cleaning") == "data_manip"

    # ML Fundamentals
    assert normalize_skill("ml") == "ml_fund"
    assert normalize_skill("machine learning") == "ml_fund"
    assert normalize_skill("scikit-learn") == "ml_fund"
    assert normalize_skill("sklearn") == "ml_fund"

    # Deep Learning & Neural Nets
    assert normalize_skill("deep learning") == "deep_learning"
    assert normalize_skill("pytorch") == "deep_learning"
    assert normalize_skill("tensorflow") == "deep_learning"
    assert normalize_skill("keras") == "deep_learning"
    assert normalize_skill("neural networks") == "neural_nets"
    assert normalize_skill("transformers") == "neural_nets"

    # Deployment / DevOps
    assert normalize_skill("docker") == "deploy_devops"
    assert normalize_skill("containerization") == "deploy_devops"

    # Stats & SQL
    assert normalize_skill("statistics") == "stats"
    assert normalize_skill("probability") == "stats"
    assert normalize_skill("sql") == "sql"
    assert normalize_skill("postgres") == "sql"

    # Web Skills
    assert normalize_skill("javascript") == "js_fund"
    assert normalize_skill("react") == "react"
    assert normalize_skill("nextjs") == "nextjs"
    assert normalize_skill("rest api") == "rest_api"


def test_linear_algebra_is_not_mapped_to_stats():
    """Verify that 'linear algebra' is NOT mapped to stats and returns None (unrecognized)."""
    assert normalize_skill("linear algebra") is None
    assert normalize_skill("linear_algebra") is None


def test_parse_goal_mock_provider_success():
    """Verify goal parsing with mock provider."""
    goal_text = "I want to become an ML Engineer. I already know Python and pandas, and have 10 hours a week."
    parsed = parse_goal(goal_text, default_weekly_hours=10, provider="mock")

    assert isinstance(parsed, ParsedGoal)
    assert parsed.target_role == "ml_engineer"
    assert "python" in parsed.known_skills
    assert "data_manip" in parsed.known_skills
    assert parsed.weekly_hours == 10
    assert parsed.timeframe_months == 6  # default for ml_engineer


def test_parse_goal_unrecognized_skills_surfaced():
    """Verify that unrecognized skills (including linear algebra and redux) are surfaced."""
    goal_text = "I want to be a Data Scientist. I know Python, linear algebra, and redux."
    parsed = parse_goal(goal_text, provider="mock")

    assert parsed.target_role == "data_scientist"
    assert "python" in parsed.known_skills
    assert "linear algebra" in parsed.unrecognized_skills
    assert "redux" in parsed.unrecognized_skills
    assert "stats" not in parsed.known_skills  # linear algebra must not map to stats


def test_parse_goal_validation_failures():
    """Verify validation errors for empty, short, or invalid inputs."""
    # Too short
    with pytest.raises(GoalParsingError) as exc:
        parse_goal("hi", provider="mock")
    assert exc.value.status_code == 400

    # Invalid role from mock/LLM
    with patch("backend.app.recommender.goal_parser.MockGoalParser.parse") as mock_parse:
        mock_parse.return_value = {
            "target_role": "quantum_physicist",
            "known_skills": ["python"],
            "unrecognized_skills": [],
        }
        with pytest.raises(GoalParsingError) as exc:
            parse_goal("I want to do quantum physics", provider="mock")
        assert exc.value.status_code == 422
        assert "Could not recognize target role" in str(exc.value)


def test_live_provider_missing_key_raises_503():
    """Verify that calling live Gemini or OpenAI without API key raises LLMConfigurationError."""
    with patch("backend.app.config.settings.GEMINI_API_KEY", ""):
        with pytest.raises(LLMConfigurationError) as exc:
            parse_goal("I want to become an ML engineer", provider="gemini")
        assert exc.value.status_code == 503
        assert "GEMINI_API_KEY is empty" in str(exc.value)

    with patch("backend.app.config.settings.OPENAI_API_KEY", ""):
        with pytest.raises(LLMConfigurationError) as exc:
            parse_goal("I want to become an ML engineer", provider="openai")
        assert exc.value.status_code == 503
        assert "OPENAI_API_KEY is empty" in str(exc.value)


def test_mocked_gemini_response_parsing():
    """Verify that structured JSON response from Gemini is correctly parsed and normalized."""
    mock_gemini_json = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"target_role": "machine learning engineer", "known_skills": ["Python Programming", "Pandas", "PyTorch"], "unrecognized_skills": ["Linear Algebra", "Kubernetes"], "timeframe_months": 8, "weekly_hours": 12}'
                        }
                    ]
                }
            }
        ]
    }

    with patch("backend.app.config.settings.GEMINI_API_KEY", "mock_key"):
        with patch("httpx.Client.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_gemini_json
            mock_post.return_value = mock_response

            parsed = parse_goal("Sample goal", provider="gemini")
            assert parsed.target_role == "ml_engineer"
            assert "python" in parsed.known_skills
            assert "data_manip" in parsed.known_skills
            assert "deep_learning" in parsed.known_skills
            assert "Kubernetes" in parsed.unrecognized_skills
            assert "Linear Algebra" in parsed.unrecognized_skills
            assert parsed.timeframe_months == 8
            assert parsed.weekly_hours == 12

            # Verify request payload schema and parameters
            called_kwargs = mock_post.call_args.kwargs
            payload = called_kwargs["json"]
            gen_config = payload.get("generationConfig", {})

            assert gen_config.get("responseMimeType") == "application/json"
            assert "thinkingConfig" in gen_config
            assert gen_config["thinkingConfig"].get("thinkingLevel") == "low"
            # Explicitly assert absence of temperature and legacy thinkingBudget
            assert "temperature" not in gen_config
            assert "thinkingBudget" not in gen_config
            assert "thinking_budget" not in gen_config
            assert "thinkingBudget" not in gen_config["thinkingConfig"]
            assert "thinking_budget" not in gen_config["thinkingConfig"]
