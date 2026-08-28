"""Path Sequencer for CourseTide.

Takes relevant courses and skill gaps, applies topological sorting over the
canonical prerequisite DAG in data/prerequisites.json, and groups items into
deterministic learning phases / milestones.

Purely deterministic (zero LLM calls).
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from pydantic import BaseModel, Field

from backend.app.config import DATA_DIR


# ---------------------------------------------------------------------------
# DATA STRUCTURES & SCHEMAS
# ---------------------------------------------------------------------------

class PathSequencingError(Exception):
    """Base exception for path sequencing failures."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class CycleDetectedError(PathSequencingError):
    """Raised when a circular prerequisite dependency is detected in the DAG."""
    def __init__(self, message: str, cycle_nodes: Optional[List[str]] = None):
        super().__init__(message, status_code=422)
        self.cycle_nodes = cycle_nodes or []


class SequencedSkill(BaseModel):
    skill_id: str
    name: str
    prerequisites: List[str] = Field(default_factory=list)
    phase_number: int
    depth: int


class SequencedCourse(BaseModel):
    course_id: str
    title: str
    difficulty: str = "intermediate"
    duration_hours: int = 10
    domain: str = "ml"
    source: Optional[str] = None
    url: Optional[str] = None
    primary_skill: Optional[str] = None
    covered_skills: List[str] = Field(default_factory=list)
    phase_number: int
    sequence_order: int
    status: str = "locked"  # 'available' for Phase 1, 'locked' for subsequent phases
    match_score: Optional[float] = None


class RoadmapPhase(BaseModel):
    phase_number: int
    phase_name: str
    skills: List[str] = Field(default_factory=list)
    courses: List[SequencedCourse] = Field(default_factory=list)
    estimated_hours: int = 0


class SequencedRoadmap(BaseModel):
    phases: List[RoadmapPhase] = Field(default_factory=list)
    total_courses: int = 0
    total_estimated_hours: int = 0
    total_estimated_weeks: int = 0


# ---------------------------------------------------------------------------
# DATA LOADERS
# ---------------------------------------------------------------------------

def _load_prerequisites() -> Dict[str, List[str]]:
    prereqs_file = DATA_DIR / "prerequisites.json"
    if prereqs_file.exists():
        with open(prereqs_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_skills_map() -> Dict[str, str]:
    skills_file = DATA_DIR / "skills.json"
    if skills_file.exists():
        with open(skills_file, "r", encoding="utf-8") as f:
            skills = json.load(f)
            return {s["id"]: s["name"] for s in skills}
    return {}


PREREQUISITES_DAG = _load_prerequisites()
SKILLS_MAP = _load_skills_map()

PHASE_TITLES: Dict[int, str] = {
    1: "Foundations",
    2: "Core Competencies",
    3: "Specialized Methods",
    4: "Advanced Practice",
    5: "Integration & Deployment",
    6: "Mastery & Capstone",
}


def get_phase_name(phase_number: int) -> str:
    """Return human-readable phase name."""
    title = PHASE_TITLES.get(phase_number, "Specialization & Mastery")
    return f"Phase {phase_number}: {title}"


# ---------------------------------------------------------------------------
# TOPOLOGICAL SORTING (SKILL LEVEL)
# ---------------------------------------------------------------------------

def topological_sort_skills(
    skills: Sequence[str],
    known_skills: Optional[Sequence[str]] = None,
    prereq_map: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """Topologically sort a subset of skills according to the prerequisite DAG.

    Preserves prerequisite ordering: if A is a prerequisite of B, A precedes B.
    Deterministic tie-breaking preserves input sequence order.
    Raises CycleDetectedError if a circular dependency is detected.

    Args:
        skills: List of skill IDs to sequence.
        known_skills: Optional list of already mastered skills (satisfied prerequisites).
        prereq_map: Optional override for the prerequisite DAG (defaults to data/prerequisites.json).

    Returns:
        List of skill IDs ordered topologically.
    """
    if not skills:
        return []

    dag = prereq_map if prereq_map is not None else PREREQUISITES_DAG
    skills_set = set(skills)
    known_set = set(known_skills) if known_skills else set()

    # Track in-degree and adjacency among the target skills
    # An edge goes from prerequisite P -> dependent S
    in_degree: Dict[str, int] = {s: 0 for s in skills}
    dependents: Dict[str, List[str]] = {s: [] for s in skills}

    for s in skills:
        direct_prereqs = dag.get(s, [])
        for p in direct_prereqs:
            # If prerequisite is in the target skills set and not already known
            if p in skills_set and p not in known_set and p != s:
                in_degree[s] += 1
                dependents[p].append(s)

    # Initial ready queue (in-degree == 0), preserving input list order
    ready_queue: List[str] = [s for s in skills if in_degree[s] == 0]
    result: List[str] = []

    while ready_queue:
        # Pop from left to preserve deterministic input priority
        curr = ready_queue.pop(0)
        result.append(curr)

        for dep in dependents[curr]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                ready_queue.append(dep)

    # Cycle detection
    if len(result) != len(skills):
        unresolved = [s for s in skills if s not in set(result)]
        raise CycleDetectedError(
            f"Prerequisite cycle detected involving skills: {unresolved}",
            cycle_nodes=unresolved,
        )

    return result


# ---------------------------------------------------------------------------
# SKILL DEPTH CALCULATION (PHASE NUMBERING)
# ---------------------------------------------------------------------------

def calculate_skill_depths(
    skills: Sequence[str],
    known_skills: Optional[Sequence[str]] = None,
    prereq_map: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, int]:
    """Calculate 0-indexed topological depth for each skill in the sequence.

    Depth represents the longest prerequisite path to the skill among the target skills:
    - depth 0 (Phase 1): No remaining prerequisites in the target set.
    - depth 1 (Phase 2): All prerequisites are at depth 0 or already known.
    - depth k (Phase k+1): At least one prerequisite is at depth k-1.

    Args:
        skills: List of skill IDs to evaluate.
        known_skills: Optional list of already mastered skills.
        prereq_map: Optional DAG override.

    Returns:
        Dictionary mapping skill_id to its 0-indexed depth integer.
    """
    if not skills:
        return {}

    ordered_skills = topological_sort_skills(skills, known_skills=known_skills, prereq_map=prereq_map)
    dag = prereq_map if prereq_map is not None else PREREQUISITES_DAG
    known_set = set(known_skills) if known_skills else set()
    skills_set = set(skills)

    depths: Dict[str, int] = {}

    for s in ordered_skills:
        direct_prereqs = dag.get(s, [])
        # Relevant prereqs are those in target skills that are not already known
        relevant_prereqs = [p for p in direct_prereqs if p in skills_set and p not in known_set]
        if not relevant_prereqs:
            depths[s] = 0
        else:
            depths[s] = 1 + max(depths.get(p, 0) for p in relevant_prereqs)

    return depths


# ---------------------------------------------------------------------------
# COURSE ROADMAP SEQUENCING
# ---------------------------------------------------------------------------

def _extract_course_skills(course: Any) -> Tuple[Optional[str], List[str]]:
    """Helper to extract primary_skill and covered_skills from various course representations."""
    if isinstance(course, dict):
        primary = course.get("primary_skill")
        covered = course.get("covered_gap_skills") or course.get("all_skills") or course.get("skills") or []
        if not primary and covered:
            primary = covered[0]
        return primary, list(covered)

    # Object / Pydantic / SQLAlchemy model
    primary = getattr(course, "primary_skill", None)
    covered = getattr(course, "covered_gap_skills", None) or getattr(course, "all_skills", None) or []
    if not primary and covered:
        primary = covered[0]
    return primary, list(covered)


def sequence_courses(
    courses: Sequence[Any],
    known_skills: Optional[Sequence[str]] = None,
    weekly_hours: int = 8,
    prereq_map: Optional[Dict[str, List[str]]] = None,
) -> SequencedRoadmap:
    """Order courses by prerequisite dependencies and group into milestone phases.

    A course C_A precedes course C_B if C_A teaches a skill that is a prerequisite
    for a skill taught by C_B. A course covering multiple skills is treated as a
    single unified milestone and not duplicated.

    Args:
        courses: Sequence of RecommendedCourse objects, dicts, or Course models.
        known_skills: Optional list of already mastered skills.
        weekly_hours: Estimated weekly study commitment for timeframe calculation.
        prereq_map: Optional DAG override.

    Returns:
        SequencedRoadmap containing phased milestones and total metrics.
    """
    if not courses:
        return SequencedRoadmap(
            phases=[],
            total_courses=0,
            total_estimated_hours=0,
            total_estimated_weeks=0,
        )

    dag = prereq_map if prereq_map is not None else PREREQUISITES_DAG
    known_set = set(known_skills) if known_skills else set()

    # 1. Normalize course items and map course ID -> skills taught
    course_items: List[Dict[str, Any]] = []
    course_skills_map: Dict[str, Set[str]] = {}
    course_id_to_item: Dict[str, Dict[str, Any]] = {}

    for idx, c in enumerate(courses):
        if isinstance(c, dict):
            c_id = str(c.get("id") or c.get("course_id") or f"course_{idx}")
            title = c.get("title", c_id)
            difficulty = c.get("difficulty", "intermediate")
            duration = int(c.get("duration_hours", 10))
            domain = c.get("domain", "ml")
            source = c.get("source")
            url = c.get("url")
            match_score = c.get("match_score")
        else:
            c_id = str(getattr(c, "id", None) or getattr(c, "course_id", None) or f"course_{idx}")
            title = getattr(c, "title", c_id)
            difficulty = getattr(c, "difficulty", "intermediate")
            duration = int(getattr(c, "duration_hours", 10))
            domain = getattr(c, "domain", "ml")
            source = getattr(c, "source", None)
            url = getattr(c, "url", None)
            match_score = getattr(c, "match_score", None)

        primary_skill, covered_skills = _extract_course_skills(c)
        all_skills_set = set(covered_skills)
        if primary_skill:
            all_skills_set.add(primary_skill)

        # Deduplicate courses if caller passes duplicates
        if c_id in course_skills_map:
            course_skills_map[c_id].update(all_skills_set)
            continue

        item = {
            "course_id": c_id,
            "title": title,
            "difficulty": difficulty,
            "duration_hours": duration,
            "domain": domain,
            "source": source,
            "url": url,
            "primary_skill": primary_skill,
            "covered_skills": covered_skills,
            "match_score": match_score,
            "all_skills_set": all_skills_set,
        }
        course_items.append(item)
        course_skills_map[c_id] = all_skills_set
        course_id_to_item[c_id] = item

    course_ids = [item["course_id"] for item in course_items]

    # 2. Build course-to-course dependency graph
    # Course A is a prerequisite of Course B (A -> B) if Course A teaches a skill
    # that is an upstream prerequisite for any skill taught by Course B.
    in_degree: Dict[str, int] = {cid: 0 for cid in course_ids}
    dependents: Dict[str, List[str]] = {cid: [] for cid in course_ids}
    course_prereqs_map: Dict[str, Set[str]] = {cid: set() for cid in course_ids}

    for i, cid_b in enumerate(course_ids):
        skills_b = course_skills_map[cid_b]
        # Collect all direct prerequisites for skills in B
        needed_prereqs: Set[str] = set()
        for sb in skills_b:
            for p in dag.get(sb, []):
                if p not in known_set and p not in skills_b:
                    needed_prereqs.add(p)

        # Find which courses teach these prerequisites
        for cid_a in course_ids:
            if cid_a == cid_b:
                continue
            skills_a = course_skills_map[cid_a]
            # If Course A teaches any skill needed by Course B
            if not skills_a.isdisjoint(needed_prereqs):
                if cid_a not in course_prereqs_map[cid_b]:
                    course_prereqs_map[cid_b].add(cid_a)
                    in_degree[cid_b] += 1
                    dependents[cid_a].append(cid_b)

    # 3. Topological sort over courses with deterministic queue
    ready_queue: List[str] = [cid for cid in course_ids if in_degree[cid] == 0]
    ordered_course_ids: List[str] = []

    while ready_queue:
        curr_id = ready_queue.pop(0)
        ordered_course_ids.append(curr_id)

        for dep_id in dependents[curr_id]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                ready_queue.append(dep_id)

    if len(ordered_course_ids) != len(course_ids):
        unresolved = [cid for cid in course_ids if cid not in set(ordered_course_ids)]
        raise CycleDetectedError(
            f"Prerequisite cycle detected between courses: {unresolved}",
            cycle_nodes=unresolved,
        )

    # 4. Calculate Phase Assignment for each course
    # phase(C) = 1 + max({0} U {phase(C_prereq) for C_prereq in course_prereqs(C)})
    course_phase: Dict[str, int] = {}
    for cid in ordered_course_ids:
        prereqs = course_prereqs_map[cid]
        if not prereqs:
            course_phase[cid] = 1
        else:
            course_phase[cid] = 1 + max(course_phase[p] for p in prereqs)

    # 5. Group into RoadmapPhase objects
    phases_dict: Dict[int, List[SequencedCourse]] = {}
    phase_skills_dict: Dict[int, Set[str]] = {}

    global_sequence = 1
    total_hours = 0

    for cid in ordered_course_ids:
        item = course_id_to_item[cid]
        phase_num = course_phase[cid]
        status = "available" if phase_num == 1 else "locked"

        sc = SequencedCourse(
            course_id=item["course_id"],
            title=item["title"],
            difficulty=item["difficulty"],
            duration_hours=item["duration_hours"],
            domain=item["domain"],
            source=item["source"],
            url=item["url"],
            primary_skill=item["primary_skill"],
            covered_skills=item["covered_skills"],
            phase_number=phase_num,
            sequence_order=global_sequence,
            status=status,
            match_score=item["match_score"],
        )
        global_sequence += 1
        total_hours += sc.duration_hours

        if phase_num not in phases_dict:
            phases_dict[phase_num] = []
            phase_skills_dict[phase_num] = set()

        phases_dict[phase_num].append(sc)
        phases_dict[phase_num].sort(
            key=lambda x: (x.match_score is None, -(x.match_score or 0.0), x.course_id)
        )
        phase_skills_dict[phase_num].update(item["all_skills_set"])

    roadmap_phases: List[RoadmapPhase] = []
    for p_num in sorted(phases_dict.keys()):
        courses_in_phase = phases_dict[p_num]
        hours_in_phase = sum(c.duration_hours for c in courses_in_phase)
        skills_in_phase = sorted(list(phase_skills_dict[p_num]))

        roadmap_phases.append(
            RoadmapPhase(
                phase_number=p_num,
                phase_name=get_phase_name(p_num),
                skills=skills_in_phase,
                courses=courses_in_phase,
                estimated_hours=hours_in_phase,
            )
        )

    weeks = math.ceil(total_hours / max(1, weekly_hours)) if total_hours > 0 else 0

    return SequencedRoadmap(
        phases=roadmap_phases,
        total_courses=len(ordered_course_ids),
        total_estimated_hours=total_hours,
        total_estimated_weeks=weeks,
    )
