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


def test_gemini_fallback_primary_503_cascades_to_fallback1():
    """Verify that a 503 on primary model falls back to gemini-2.5-flash and succeeds."""
    mock_success_json = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"target_role": "ml_engineer", "known_skills": ["python", "stats"], "unrecognized_skills": [], "timeframe_months": 6, "weekly_hours": 10}'
                        }
                    ]
                }
            }
        ]
    }

    mock_503 = MagicMock()
    mock_503.status_code = 503
    mock_503.text = '{"error": {"code": 503, "message": "High demand", "status": "UNAVAILABLE"}}'

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = mock_success_json

    with patch("backend.app.config.settings.GEMINI_API_KEY", "mock_key"):
        with patch("httpx.Client.post", side_effect=[mock_503, mock_200]) as mock_post:
            parsed = parse_goal("I want to become an ML engineer", provider="gemini")
            assert parsed.target_role == "ml_engineer"
            assert "python" in parsed.known_skills
            assert "stats" in parsed.known_skills

            assert mock_post.call_count == 2
            urls = [call.args[0] for call in mock_post.call_args_list]
            assert "gemini-3.7-flash" in urls[0]
            assert "gemini-2.5-flash" in urls[1]


def test_gemini_fallback_429_cascades_to_fallback1():
    """Verify that a 429 rate limit on primary model falls back and succeeds."""
    mock_success_json = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"target_role": "data_scientist", "known_skills": ["python", "sql"], "unrecognized_skills": [], "timeframe_months": 6, "weekly_hours": 8}'
                        }
                    ]
                }
            }
        ]
    }

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.text = '{"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}}'

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = mock_success_json

    with patch("backend.app.config.settings.GEMINI_API_KEY", "mock_key"):
        with patch("httpx.Client.post", side_effect=[mock_429, mock_200]) as mock_post:
            parsed = parse_goal("I want to become a data scientist", provider="gemini")
            assert parsed.target_role == "data_scientist"
            assert mock_post.call_count == 2
            assert "gemini-3.7-flash" in mock_post.call_args_list[0].args[0]
            assert "gemini-2.5-flash" in mock_post.call_args_list[1].args[0]


def test_gemini_fallback_primary_and_fallback1_fail_cascades_to_fallback2():
    """Verify cascade across primary (503) and fallback 1 (500) to fallback 2 (200)."""
    mock_success_json = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"target_role": "mlops_engineer", "known_skills": ["python", "deploy_devops"], "unrecognized_skills": [], "timeframe_months": 6, "weekly_hours": 8}'
                        }
                    ]
                }
            }
        ]
    }

    mock_503 = MagicMock()
    mock_503.status_code = 503
    mock_503.text = "Service Unavailable"

    mock_500 = MagicMock()
    mock_500.status_code = 500
    mock_500.text = "Internal Server Error"

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = mock_success_json

    with patch("backend.app.config.settings.GEMINI_API_KEY", "mock_key"):
        with patch("httpx.Client.post", side_effect=[mock_503, mock_500, mock_200]) as mock_post:
            parsed = parse_goal("I want to become an MLOps engineer", provider="gemini")
            assert parsed.target_role == "mlops_engineer"
            assert mock_post.call_count == 3
            urls = [call.args[0] for call in mock_post.call_args_list]
            assert "gemini-3.7-flash" in urls[0]
            assert "gemini-2.5-flash" in urls[1]
            assert "gemini-2.0-flash" in urls[2]


def test_gemini_fallback_all_models_exhausted_raises_503():
    """Verify that when all models in chain fail with retryable status, GoalParsingError 503 is raised."""
    mock_503 = MagicMock()
    mock_503.status_code = 503
    mock_503.text = "High demand"

    with patch("backend.app.config.settings.GEMINI_API_KEY", "mock_key"):
        with patch("httpx.Client.post", return_value=mock_503) as mock_post:
            with pytest.raises(GoalParsingError) as exc:
                parse_goal("I want to become an ML engineer", provider="gemini")
            assert exc.value.status_code == 503
            assert "temporarily unavailable" in str(exc.value)
            assert mock_post.call_count == 3  # 3.7-flash, 2.5-flash, 2.0-flash


def test_gemini_non_retryable_400_fails_fast():
    """Verify that a 400 Bad Request fails fast immediately without attempting fallback models."""
    mock_400 = MagicMock()
    mock_400.status_code = 400
    mock_400.text = '{"error": {"code": 400, "message": "Invalid argument", "status": "INVALID_ARGUMENT"}}'

    with patch("backend.app.config.settings.GEMINI_API_KEY", "mock_key"):
        with patch("httpx.Client.post", return_value=mock_400) as mock_post:
            with pytest.raises(GoalParsingError) as exc:
                parse_goal("I want to become an ML engineer", provider="gemini")
            assert exc.value.status_code == 502
            assert "Non-Retryable Error [400]" in str(exc.value)
            assert mock_post.call_count == 1  # Fails fast, does NOT cascade


def test_gemini_network_timeout_cascades_to_fallback():
    """Verify that httpx.TimeoutException cascades to the next fallback model."""
    import httpx

    mock_success_json = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"target_role": "ml_engineer", "known_skills": ["python"], "unrecognized_skills": [], "timeframe_months": 6, "weekly_hours": 8}'
                        }
                    ]
                }
            }
        ]
    }
    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = mock_success_json

    with patch("backend.app.config.settings.GEMINI_API_KEY", "mock_key"):
        with patch("httpx.Client.post", side_effect=[httpx.TimeoutException("Timed out"), mock_200]) as mock_post:
            parsed = parse_goal("I want to become an ML engineer", provider="gemini")
            assert parsed.target_role == "ml_engineer"
            assert mock_post.call_count == 2


def test_gemini_fallback_malformed_json_cascades_to_fallback1():
    """Verify that HTTP 200 with malformed JSON from primary cascades to fallback 1 and succeeds."""
    mock_malformed_gemini_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"target_role": "ml_engineer", "known_skills": ["python", INVALID_JSON...}'
                        }
                    ]
                }
            }
        ]
    }

    mock_valid_gemini_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"target_role": "ml_engineer", "known_skills": ["python", "stats"], "unrecognized_skills": [], "timeframe_months": 6, "weekly_hours": 10}'
                        }
                    ]
                }
            }
        ]
    }

    mock_resp1 = MagicMock()
    mock_resp1.status_code = 200
    mock_resp1.json.return_value = mock_malformed_gemini_response

    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = mock_valid_gemini_response

    with patch("backend.app.config.settings.GEMINI_API_KEY", "mock_key"):
        with patch("httpx.Client.post", side_effect=[mock_resp1, mock_resp2]) as mock_post:
            parsed = parse_goal("I want to become an ML engineer", provider="gemini")
            assert parsed.target_role == "ml_engineer"
            assert "python" in parsed.known_skills
            assert "stats" in parsed.known_skills
            assert parsed.timeframe_months == 6
            assert parsed.weekly_hours == 10

            assert mock_post.call_count == 2
            urls = [call.args[0] for call in mock_post.call_args_list]
            assert "gemini-3.7-flash" in urls[0]
            assert "gemini-2.5-flash" in urls[1]

