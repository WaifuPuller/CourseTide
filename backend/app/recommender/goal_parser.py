"""Goal parser for CourseTide.

Extracts structured learner profile from natural language input:
- target_role (validated against data/target_roles.json)
- known_skills (normalized to canonical IDs from data/skills.json)
- unrecognized_skills (surfaced to user, e.g. "linear algebra", "redux")
- timeframe_months (defaults to target_role default if omitted)
- weekly_hours (defaults to request value or role default if omitted)
"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from backend.app.config import DATA_DIR, settings


class ParsedGoal(BaseModel):
    target_role: str = Field(..., description="Canonical role ID from target_roles.json")
    known_skills: List[str] = Field(default_factory=list, description="Canonical skill IDs from skills.json")
    unrecognized_skills: List[str] = Field(default_factory=list, description="Extracted terms not recognized in taxonomy")
    timeframe_months: int = Field(default=6, ge=1, le=36)
    weekly_hours: int = Field(default=8, ge=1, le=80)


class GoalParsingError(Exception):
    """Raised when goal parsing fails validation or LLM output is malformed."""
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class LLMConfigurationError(Exception):
    """Raised when the requested LLM provider is not configured."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
        self.status_code = 503


# ---------------------------------------------------------------------------
# TAXONOMY & ALIAS DATA LOADERS
# ---------------------------------------------------------------------------

def _load_taxonomy() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    skills_file = DATA_DIR / "skills.json"
    roles_file = DATA_DIR / "target_roles.json"

    with open(skills_file, "r", encoding="utf-8") as f:
        skills_list = json.load(f)
    skills_dict = {s["id"]: s for s in skills_list}

    with open(roles_file, "r", encoding="utf-8") as f:
        roles_dict = json.load(f)

    return skills_dict, roles_dict


SKILLS_TAXONOMY, ROLES_TAXONOMY = _load_taxonomy()

# Curated alias dictionary strictly mapped to data/skills.json
# Note: "linear algebra" is intentionally excluded to be captured as unrecognized
SKILL_ALIASES: Dict[str, str] = {
    # Python
    "python": "python",
    "py": "python",
    "python3": "python",
    "python programming": "python",
    # Git
    "git": "git",
    "github": "git",
    "version control": "git",
    "git branching": "git",
    # Data Manipulation
    "pandas": "data_manip",
    "numpy": "data_manip",
    "data manipulation": "data_manip",
    "data cleaning": "data_manip",
    "tabular data": "data_manip",
    # SQL
    "sql": "sql",
    "databases": "sql",
    "relational database": "sql",
    "relational databases": "sql",
    "postgres": "sql",
    "postgresql": "sql",
    "querying": "sql",
    # Statistics
    "stats": "stats",
    "statistics": "stats",
    "probability": "stats",
    "math": "stats",
    "statistics and probability": "stats",
    # Data Visualization
    "dataviz": "dataviz",
    "data visualization": "dataviz",
    "matplotlib": "dataviz",
    "seaborn": "dataviz",
    "plotting": "dataviz",
    # Machine Learning Fundamentals
    "ml": "ml_fund",
    "machine learning": "ml_fund",
    "scikit-learn": "ml_fund",
    "sklearn": "ml_fund",
    "supervised learning": "ml_fund",
    "machine learning fundamentals": "ml_fund",
    # Feature Engineering
    "feature engineering": "feat_eng",
    "feat eng": "feat_eng",
    "preprocessing": "feat_eng",
    # Deep Learning
    "deep learning": "deep_learning",
    "dl": "deep_learning",
    "pytorch": "deep_learning",
    "tensorflow": "deep_learning",
    "keras": "deep_learning",
    # Neural Networks
    "neural networks": "neural_nets",
    "ann": "neural_nets",
    "cnn": "neural_nets",
    "rnn": "neural_nets",
    "transformers": "neural_nets",
    "neural network architectures": "neural_nets",
    # Computer Vision
    "computer vision": "computer_vision",
    "cv": "computer_vision",
    "opencv": "computer_vision",
    "image processing": "computer_vision",
    # NLP
    "nlp": "nlp",
    "natural language processing": "nlp",
    "llm": "nlp",
    "llms": "nlp",
    "text processing": "nlp",
    # MLOps
    "mlops": "mlops",
    "model deployment": "mlops",
    "ci/cd for ml": "mlops",
    "pipeline deployment": "mlops",
    # Web Skills
    "html": "html_css",
    "css": "html_css",
    "html5": "html_css",
    "css3": "html_css",
    "flexbox": "html_css",
    "grid": "html_css",
    "javascript": "js_fund",
    "js": "js_fund",
    "ecmascript": "js_fund",
    "vanilla js": "js_fund",
    "react": "react",
    "reactjs": "react",
    "react.js": "react",
    "node": "node_express",
    "nodejs": "node_express",
    "node.js": "node_express",
    "express": "node_express",
    "expressjs": "node_express",
    "rest api": "rest_api",
    "restful": "rest_api",
    "api design": "rest_api",
    "endpoints": "rest_api",
    "mongodb": "db_web",
    "document db": "db_web",
    "web database": "db_web",
    "nosql": "db_web",
    "auth": "auth_security",
    "jwt": "auth_security",
    "authentication": "auth_security",
    "web security": "auth_security",
    "oauth": "auth_security",
    "nextjs": "nextjs",
    "next.js": "nextjs",
    "app router": "nextjs",
    "docker": "deploy_devops",
    "containerization": "deploy_devops",
    "devops": "deploy_devops",
    "deployment": "deploy_devops",
}

ROLE_ALIASES: Dict[str, str] = {
    "ml_engineer": "ml_engineer",
    "ml engineer": "ml_engineer",
    "machine learning engineer": "ml_engineer",
    "mle": "ml_engineer",
    "machine learning": "ml_engineer",
    "ml": "ml_engineer",
    "data_scientist": "data_scientist",
    "data scientist": "data_scientist",
    "data science": "data_scientist",
    "ds": "data_scientist",
    "mlops_engineer": "mlops_engineer",
    "mlops engineer": "mlops_engineer",
    "mlops": "mlops_engineer",
    "ml ops": "mlops_engineer",
}


def normalize_role(raw_role: str) -> Optional[str]:
    """Normalize raw role string to canonical key in target_roles.json."""
    if not raw_role:
        return None
    cleaned = raw_role.strip().lower().replace("-", "_")
    if cleaned in ROLES_TAXONOMY:
        return cleaned
    cleaned_spaces = re.sub(r"\s+", " ", cleaned.replace("_", " "))
    if cleaned_spaces in ROLE_ALIASES:
        return ROLE_ALIASES[cleaned_spaces]
    return None


def normalize_skill(raw_skill: str) -> Optional[str]:
    """Normalize a raw skill string to a canonical skill ID from skills.json."""
    if not raw_skill:
        return None
    cleaned = raw_skill.strip().lower()
    # 1. Exact ID match
    if cleaned in SKILLS_TAXONOMY:
        return cleaned

    # 2. Curated alias match (direct and with spaces)
    if cleaned in SKILL_ALIASES:
        return SKILL_ALIASES[cleaned]
    cleaned_alias = re.sub(r"[_\-]+", " ", cleaned)
    if cleaned_alias in SKILL_ALIASES:
        return SKILL_ALIASES[cleaned_alias]

    # 3. Canonical name match
    for skill_id, skill_meta in SKILLS_TAXONOMY.items():
        if cleaned == skill_meta["name"].lower() or cleaned_alias == skill_meta["name"].lower():
            return skill_id

    # 4. Strict fuzzy match (ratio >= 0.85) against canonical names
    for skill_id, skill_meta in SKILLS_TAXONOMY.items():
        name_clean = skill_meta["name"].lower()
        if SequenceMatcher(None, cleaned_alias, name_clean).ratio() >= 0.85:
            return skill_id

    return None


# ---------------------------------------------------------------------------
# LLM PROMPT CONSTRUCTION
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    roles_summary = []
    for r_id, r_info in ROLES_TAXONOMY.items():
        roles_summary.append(f"- '{r_id}': {r_info['name']} (Required skills: {', '.join(r_info['required_skills'])})")

    skills_summary = [f"{s_id} ({s_info['name']})" for s_id, s_info in SKILLS_TAXONOMY.items()]

    return f"""You are the CourseTide Goal Parsing Engine.
Your task is to parse a learner's natural-language career/learning goal into a structured JSON profile.

SUPPORTED TARGET ROLES (You MUST pick the best match from these exact IDs):
{chr(10).join(roles_summary)}

CANONICAL SKILLS TAXONOMY:
{", ".join(skills_summary)}

INSTRUCTIONS:
1. Identify the 'target_role' from the supported roles list above (e.g. 'ml_engineer', 'data_scientist', 'mlops_engineer').
2. Identify all skills the learner ALREADY knows or mentions having experience with ('known_skills').
3. If the learner mentions topics/skills outside the canonical taxonomy (e.g. 'linear algebra', 'redux', 'kubernetes'), place them in 'unrecognized_skills'.
4. Extract 'timeframe_months' if mentioned (e.g. 'in 6 months' -> 6); otherwise return null.
5. Extract 'weekly_hours' if mentioned (e.g. '10 hours a week' -> 10); otherwise return null.

Return ONLY a valid JSON object matching this schema:
{{
  "target_role": "ml_engineer",
  "known_skills": ["python", "stats"],
  "unrecognized_skills": ["linear algebra"],
  "timeframe_months": null,
  "weekly_hours": null
}}
"""


# ---------------------------------------------------------------------------
# MOCK PROVIDER (FOR TESTS & DETERMINISTIC OFFLINE PARSING)
# ---------------------------------------------------------------------------

class MockGoalParser:
    """Deterministic rule-based parser used during unit tests."""

    @staticmethod
    def parse(goal_text: str, default_weekly_hours: int = 8) -> Dict[str, Any]:
        text_lower = goal_text.lower()

        # Role detection
        detected_role = "ml_engineer"  # default
        if "data scientist" in text_lower or "data science" in text_lower:
            detected_role = "data_scientist"
        elif "mlops" in text_lower:
            detected_role = "mlops_engineer"
        elif "ml engineer" in text_lower or "machine learning engineer" in text_lower or "machine learning" in text_lower:
            detected_role = "ml_engineer"

        # Skill extraction
        known_raw = []
        unrecognized_raw = []

        if "python" in text_lower:
            known_raw.append("python")
        if "pandas" in text_lower:
            known_raw.append("pandas")
        if "numpy" in text_lower:
            known_raw.append("numpy")
        if "sql" in text_lower:
            known_raw.append("sql")
        if "stats" in text_lower or "statistics" in text_lower or "probability" in text_lower:
            known_raw.append("stats")
        if "git" in text_lower:
            known_raw.append("git")
        if "linear algebra" in text_lower:
            unrecognized_raw.append("linear algebra")
        if "redux" in text_lower:
            unrecognized_raw.append("redux")
        if "kubernetes" in text_lower:
            unrecognized_raw.append("kubernetes")

        # Weekly hours extraction
        hours_match = re.search(r"(\d+)\s*(?:hours|hrs)(?:\s*(?:a|per)\s*week)?", text_lower)
        hours = int(hours_match.group(1)) if hours_match else default_weekly_hours

        # Timeframe extraction
        months_match = re.search(r"(\d+)\s*(?:months|mo)", text_lower)
        timeframe = int(months_match.group(1)) if months_match else None

        return {
            "target_role": detected_role,
            "known_skills": known_raw,
            "unrecognized_skills": unrecognized_raw,
            "timeframe_months": timeframe,
            "weekly_hours": hours,
        }


# ---------------------------------------------------------------------------
# GEMINI PROVIDER (OFFICIAL GOOGLE GENAI CLIENT)
# ---------------------------------------------------------------------------

class GeminiGoalParser:
    """Google Gemini Goal Parser using current Google GenAI API client."""

    @staticmethod
    def parse(goal_text: str, model_name: str, api_key: str) -> Dict[str, Any]:
        if not api_key:
            raise LLMConfigurationError("Gemini API key is not configured in .env (GEMINI_API_KEY is empty).")

        import httpx

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "systemInstruction": {
                "parts": [{"text": _build_system_prompt()}]
            },
            "contents": [
                {
                    "parts": [{"text": f"Learner goal:\n{goal_text}"}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "thinkingConfig": {
                    "thinkingLevel": "low",
                },
            },
        }

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise GoalParsingError(f"Gemini API Error [{resp.status_code}]: {resp.text}", status_code=502)
            data = resp.json()

        try:
            candidates = data.get("candidates", [])
            raw_content = candidates[0]["content"]["parts"][0]["text"]
            return json.loads(raw_content)
        except Exception as e:
            raise GoalParsingError(f"Malformed LLM response from Gemini: {e}", status_code=502)


# ---------------------------------------------------------------------------
# OPENAI PROVIDER
# ---------------------------------------------------------------------------

class OpenAIGoalParser:
    """OpenAI Goal Parser."""

    @staticmethod
    def parse(goal_text: str, model_name: str, api_key: str) -> Dict[str, Any]:
        if not api_key:
            raise LLMConfigurationError("OpenAI API key is not configured in .env (OPENAI_API_KEY is empty).")

        import httpx

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model_name or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user", "content": goal_text},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise GoalParsingError(f"OpenAI API Error [{resp.status_code}]: {resp.text}", status_code=502)
            data = resp.json()

        try:
            raw_content = data["choices"][0]["message"]["content"]
            return json.loads(raw_content)
        except Exception as e:
            raise GoalParsingError(f"Malformed LLM response from OpenAI: {e}", status_code=502)


# ---------------------------------------------------------------------------
# MAIN PARSE GOAL FUNCTION
# ---------------------------------------------------------------------------

def parse_goal(
    goal_text: str,
    default_weekly_hours: Optional[int] = 8,
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
) -> ParsedGoal:
    """Parse a free-text learner goal into a validated, normalized ParsedGoal.

    Args:
        goal_text: Free-text description of career/learning goal.
        default_weekly_hours: Default weekly hours from request slider.
        provider: 'gemini' | 'openai' | 'mock' (defaults to settings.LLM_PROVIDER).
        model_name: Model identifier (defaults to settings.LLM_MODEL_NAME).

    Returns:
        Validated ParsedGoal object.
    """
    if not goal_text or len(goal_text.strip()) < 5:
        raise GoalParsingError("Please provide a more descriptive career or learning goal (minimum 5 characters).", status_code=400)

    if provider is not None:
        selected_provider = provider.lower()
    elif settings.TESTING:
        selected_provider = "mock"
    else:
        selected_provider = (settings.LLM_PROVIDER or "gemini").lower()

    selected_model = model_name or settings.LLM_MODEL_NAME or ("gemini-3.7-flash" if selected_provider == "gemini" else "gpt-4o-mini")

    if selected_provider == "mock":
        raw_output = MockGoalParser.parse(goal_text, default_weekly_hours=default_weekly_hours or 8)
    elif selected_provider == "gemini":
        raw_output = GeminiGoalParser.parse(goal_text, model_name=selected_model, api_key=settings.GEMINI_API_KEY)
    elif selected_provider == "openai":
        raw_output = OpenAIGoalParser.parse(goal_text, model_name=selected_model, api_key=settings.OPENAI_API_KEY)
    else:
        raise GoalParsingError(f"Unsupported LLM provider: '{selected_provider}'. Supported: 'gemini', 'openai', 'mock'.", status_code=400)

    # 1. Validate & Normalize Target Role
    raw_role = raw_output.get("target_role", "")
    canonical_role = normalize_role(raw_role)
    if not canonical_role:
        supported_roles = ", ".join(f"'{k}' ({v['name']})" for k, v in ROLES_TAXONOMY.items())
        raise GoalParsingError(
            f"Could not recognize target role '{raw_role}'. Supported roles are: {supported_roles}",
            status_code=422,
        )

    # 2. Normalize Known Skills & Capture Unrecognized Skills
    raw_known = raw_output.get("known_skills", [])
    raw_unrecognized = raw_output.get("unrecognized_skills", [])

    canonical_known: List[str] = []
    unrecognized_set = set(raw_unrecognized)

    for skill_term in raw_known:
        canon_id = normalize_skill(str(skill_term))
        if canon_id:
            if canon_id not in canonical_known:
                canonical_known.append(canon_id)
        else:
            unrecognized_set.add(str(skill_term))

    # 3. Resolve Timeframe
    raw_timeframe = raw_output.get("timeframe_months")
    if raw_timeframe and isinstance(raw_timeframe, (int, float)) and raw_timeframe > 0:
        timeframe = int(raw_timeframe)
    else:
        timeframe = ROLES_TAXONOMY[canonical_role].get("default_timeframe_months", 6)

    # 4. Resolve Weekly Hours
    raw_hours = raw_output.get("weekly_hours")
    if raw_hours and isinstance(raw_hours, (int, float)) and raw_hours > 0:
        hours = int(raw_hours)
    else:
        hours = default_weekly_hours or ROLES_TAXONOMY[canonical_role].get("default_weekly_hours", 8)

    return ParsedGoal(
        target_role=canonical_role,
        known_skills=canonical_known,
        unrecognized_skills=sorted(list(unrecognized_set)),
        timeframe_months=timeframe,
        weekly_hours=hours,
    )
