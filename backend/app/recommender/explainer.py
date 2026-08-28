"""Grounded Recommendation Explainer for CourseTide.

Generates concise, 2-3 sentence transparent explanations for course recommendations
using an ordered Gemini model fallback chain. Strictly grounded on structured facts
(skill gap closed, prerequisite sequencing logic) with zero hallucinated claims.
"""

import json
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

from backend.app.config import settings


# ---------------------------------------------------------------------------
# DATA STRUCTURES & SCHEMAS
# ---------------------------------------------------------------------------

class ExplanationContext(BaseModel):
    """Immutable structured factual context supplied to the explainer."""
    learner_id: str
    target_role: str
    role_name: str
    known_skills: List[str] = Field(default_factory=list)
    gap_skills: List[str] = Field(default_factory=list)
    course_id: str
    course_title: str
    difficulty: str = "intermediate"
    duration_hours: int = 10
    primary_skill: str
    covered_gap_skills: List[str] = Field(default_factory=list)
    phase_number: int = 1
    phase_name: str = "Phase 1: Foundations"
    upstream_prerequisites: List[str] = Field(default_factory=list)
    downstream_skills: List[str] = Field(default_factory=list)


class ExplanationError(Exception):
    """Base exception for explanation generation failures (non-retryable)."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ExplanationUnavailableError(ExplanationError):
    """Raised when all configured Gemini models in the fallback chain fail retryably."""
    def __init__(self, message: str = "Explanation service is temporarily unavailable. Please try again."):
        super().__init__(message, status_code=503)


# ---------------------------------------------------------------------------
# RETRYABILITY CHECKER
# ---------------------------------------------------------------------------

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def is_retryable_error(status_code: int, error_text: str = "") -> bool:
    """Determines if an HTTP error or response body indicates a retryable availability condition."""
    if status_code in RETRYABLE_STATUS_CODES:
        return True
    err_lower = error_text.lower()
    retryable_indicators = [
        "rate limit", "quota", "resource exhausted", "overloaded",
        "service unavailable", "model unavailable", "try again",
        "temporarily unavailable", "deadline exceeded"
    ]
    return any(ind in err_lower for ind in retryable_indicators)


# ---------------------------------------------------------------------------
# GROUNDING PROMPT BUILDER
# ---------------------------------------------------------------------------

def build_grounding_prompt(ctx: ExplanationContext) -> str:
    """Constructs a strict grounding prompt containing ONLY factual structured context."""
    prereqs_str = ", ".join(ctx.upstream_prerequisites) if ctx.upstream_prerequisites else "None (Foundational competency)"
    downstream_str = ", ".join(ctx.downstream_skills) if ctx.downstream_skills else "Target Role Mastery"
    covered_str = ", ".join(ctx.covered_gap_skills) if ctx.covered_gap_skills else ctx.primary_skill
    known_str = ", ".join(ctx.known_skills) if ctx.known_skills else "None specified"
    gaps_str = ", ".join(ctx.gap_skills) if ctx.gap_skills else "All core competencies"

    return f"""You are the CourseTide Recommendation Explainer.
Explain to the learner in 2-3 concise sentences why this specific course was recommended and why it is placed in its roadmap phase.

FACTUAL CONTEXT (Use ONLY these facts. Do NOT assume, generalize, or invent unlisted facts):
- Learner Target Role: {ctx.role_name} ({ctx.target_role})
- Learner Current Known Skills: {known_str}
- Learner Overall Skill Gaps: {gaps_str}
- Selected Course: "{ctx.course_title}" (ID: {ctx.course_id}, Difficulty: {ctx.difficulty}, Duration: {ctx.duration_hours}h)
- Primary Skill Taught: {ctx.primary_skill}
- Skill Gap(s) Addressed: {covered_str}
- Roadmap Placement: {ctx.phase_name} (Phase {ctx.phase_number})
- Direct Prerequisite Competencies Required: {prereqs_str}
- Downstream Competencies Unlocked: {downstream_str}

NEGATIVE CONSTRAINTS (STRICT):
- Do NOT mention certifications, certificates, university affiliations, or job placement guarantees.
- Do NOT invent prerequisites not listed above.
- Do NOT give generic motivational advice or career fluff.
- Base the explanation strictly on the skill gap closed and the prerequisite sequencing logic.

REQUIRED OUTPUT FORMAT:
Return ONLY a valid JSON object matching this schema:
{{
  "explanation": "2-3 concise sentences explaining why the course closes the skill gap and why it is sequenced in its phase."
}}"""


# ---------------------------------------------------------------------------
# GEMINI MODEL FALLBACK CHAIN EXECUTION
# ---------------------------------------------------------------------------

DEFAULT_MODEL_CHAIN: List[str] = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]


async def generate_explanation_async(
    context: ExplanationContext,
    model_chain: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    timeout_seconds: float = 15.0,
) -> str:
    """Calls the configured Gemini model chain sequentially until a valid grounded explanation is produced.

    Sequential Execution:
    - Primary model is attempted first.
    - If retryable availability failure occurs (429, 503, 500, timeout), advances to next model.
    - If non-retryable failure occurs (400, malformed prompt), fails immediately without cascading.
    - If all configured models fail with retryable availability errors, raises ExplanationUnavailableError (HTTP 503).
    """
    key = api_key or settings.GEMINI_API_KEY
    if not key:
        raise ExplanationUnavailableError(
            "Gemini API key is not configured in .env (GEMINI_API_KEY is empty)."
        )

    # Determine ordered list of models
    chain = model_chain if model_chain is not None else [
        settings.LLM_MODEL_NAME or "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
    ]
    # Preserve order and eliminate duplicates
    ordered_models = list(dict.fromkeys(chain))

    last_retryable_error: Optional[str] = None
    prompt_text = build_grounding_prompt(context)

    for model_name in ordered_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "systemInstruction": {
                "parts": [{
                    "text": "You are CourseTide's grounded explainer. You must strictly base your explanation on the provided factual context and output valid JSON."
                }]
            },
            "contents": [
                {
                    "parts": [{"text": prompt_text}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "thinkingConfig": {
                    "thinkingLevel": "low",
                },
            },
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(url, headers=headers, json=payload)

            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    last_retryable_error = f"Model {model_name} returned no candidates"
                    continue

                raw_text = candidates[0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)
                explanation = parsed.get("explanation", "").strip()
                if not explanation:
                    last_retryable_error = f"Model {model_name} returned empty explanation field"
                    continue

                # SUCCESS! Return immediately. Do NOT call further models.
                return explanation

            elif is_retryable_error(resp.status_code, resp.text):
                last_retryable_error = f"Model {model_name} returned retryable status {resp.status_code}: {resp.text}"
                continue

            else:
                # Non-retryable error (e.g. 400 Bad Request, malformed context/payload)
                raise ExplanationError(
                    f"Gemini API Non-Retryable Error [{resp.status_code}] on model {model_name}: {resp.text}",
                    status_code=502,
                )

        except httpx.TimeoutException as e:
            last_retryable_error = f"Model {model_name} timed out: {e}"
            continue
        except (httpx.ConnectError, httpx.NetworkError) as e:
            last_retryable_error = f"Model {model_name} network error: {e}"
            continue
        except json.JSONDecodeError as e:
            last_retryable_error = f"Model {model_name} returned malformed JSON: {e}"
            continue
        except ExplanationError:
            raise
        except Exception as e:
            raise ExplanationError(f"Unexpected error calling Gemini model {model_name}: {e}", status_code=500)

    # If all models in the fallback chain were exhausted by retryable availability errors
    raise ExplanationUnavailableError(
        f"Explanation service is temporarily unavailable across all configured models ({', '.join(ordered_models)}). Last error: {last_retryable_error}"
    )
