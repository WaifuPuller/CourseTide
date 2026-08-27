"""Deterministic Skill-Gap Engine for CourseTide.

Compares a learner's normalized known skills against target role requirements in
data/target_roles.json. Purely deterministic (zero LLM calls).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.config import DATA_DIR


class SkillGapResult(BaseModel):
    target_role: str
    role_name: str
    domain: str
    required_skills: List[str]
    known_skills: List[str]
    gap_skills: List[str]
    recommended_optional_skills: List[str] = Field(default_factory=list)
    optional_gap_skills: List[str] = Field(default_factory=list)
    total_required_count: int
    known_count: int
    gap_count: int
    match_percentage: float


class SkillGapError(Exception):
    """Raised when skill-gap detection fails due to invalid role or data."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _load_target_roles() -> Dict[str, Dict[str, Any]]:
    roles_file = DATA_DIR / "target_roles.json"
    with open(roles_file, "r", encoding="utf-8") as f:
        return json.load(f)


TARGET_ROLES = _load_target_roles()


def detect_skill_gaps(target_role: str, known_skills: List[str]) -> SkillGapResult:
    """Calculate skill gaps against the target role requirements deterministically.

    Args:
        target_role: Canonical role ID (e.g. 'ml_engineer', 'data_scientist', 'mlops_engineer').
        known_skills: List of normalized canonical skill IDs known by the learner.

    Returns:
        SkillGapResult with required, known, and gap skill breakdowns.
    """
    if target_role not in TARGET_ROLES:
        supported = ", ".join(f"'{k}'" for k in TARGET_ROLES.keys())
        raise SkillGapError(f"Target role '{target_role}' not found in taxonomy. Supported roles: {supported}", status_code=422)

    role_meta = TARGET_ROLES[target_role]
    required_skills: List[str] = role_meta.get("required_skills", [])
    optional_skills: List[str] = role_meta.get("recommended_optional_skills", [])

    known_set = set(known_skills)

    # Required gaps preserve role requirement ordering
    gap_skills = [s for s in required_skills if s not in known_set]
    known_in_role = [s for s in required_skills if s in known_set]

    # Optional gaps
    optional_gaps = [s for s in optional_skills if s not in known_set]

    total_req = len(required_skills)
    known_req_count = len(known_in_role)
    gap_count = len(gap_skills)
    match_pct = round((known_req_count / total_req * 100.0), 1) if total_req > 0 else 0.0

    return SkillGapResult(
        target_role=target_role,
        role_name=role_meta.get("name", target_role),
        domain=role_meta.get("domain", "ml"),
        required_skills=required_skills,
        known_skills=[s for s in known_skills if s in required_skills or s in optional_skills] + [s for s in known_skills if s not in required_skills and s not in optional_skills],
        gap_skills=gap_skills,
        recommended_optional_skills=optional_skills,
        optional_gap_skills=optional_gaps,
        total_required_count=total_req,
        known_count=known_req_count,
        gap_count=gap_count,
        match_percentage=match_pct,
    )
