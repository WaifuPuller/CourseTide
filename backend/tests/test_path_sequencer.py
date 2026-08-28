"""Targeted unit and integration tests for CourseTide Path Sequencer (Day 3 Step 1)."""

import pytest
from backend.app.recommender.path_sequencer import (
    topological_sort_skills,
    calculate_skill_depths,
    sequence_courses,
    CycleDetectedError,
    SequencedRoadmap,
    PREREQUISITES_DAG,
)


# ---------------------------------------------------------------------------
# 1. BASIC PREREQUISITE ORDERING (A -> B -> C)
# ---------------------------------------------------------------------------

def test_basic_linear_prerequisite_ordering():
    """Verify that a linear prerequisite chain A -> B -> C orders strictly A before B before C."""
    custom_prereqs = {
        "c_skill": ["b_skill"],
        "b_skill": ["a_skill"],
        "a_skill": [],
    }
    # Pass in reverse order to ensure sorting logic takes effect
    input_skills = ["c_skill", "b_skill", "a_skill"]
    ordered = topological_sort_skills(input_skills, prereq_map=custom_prereqs)

    assert ordered == ["a_skill", "b_skill", "c_skill"]
    assert ordered.index("a_skill") < ordered.index("b_skill") < ordered.index("c_skill")


# ---------------------------------------------------------------------------
# 2. MULTIPLE INDEPENDENT PREREQUISITES (A -> C, B -> C)
# ---------------------------------------------------------------------------

def test_multiple_independent_prerequisites():
    """Verify that when C depends on both A and B, both A and B precede C."""
    custom_prereqs = {
        "c_skill": ["a_skill", "b_skill"],
        "a_skill": [],
        "b_skill": [],
    }
    input_skills = ["c_skill", "b_skill", "a_skill"]
    ordered = topological_sort_skills(input_skills, prereq_map=custom_prereqs)

    assert ordered.index("a_skill") < ordered.index("c_skill")
    assert ordered.index("b_skill") < ordered.index("c_skill")


# ---------------------------------------------------------------------------
# 3. MULTIPLE PHASES / MILESTONE GROUPING
# ---------------------------------------------------------------------------

def test_phase_milestone_grouping():
    """Verify that skill depths and course phases correctly reflect DAG level distance."""
    custom_prereqs = {
        "foundations": [],
        "intermediate_1": ["foundations"],
        "intermediate_2": ["foundations"],
        "advanced": ["intermediate_1", "intermediate_2"],
    }
    skills = ["advanced", "foundations", "intermediate_1", "intermediate_2"]
    depths = calculate_skill_depths(skills, prereq_map=custom_prereqs)

    assert depths["foundations"] == 0  # Phase 1
    assert depths["intermediate_1"] == 1  # Phase 2
    assert depths["intermediate_2"] == 1  # Phase 2
    assert depths["advanced"] == 2  # Phase 3


# ---------------------------------------------------------------------------
# 4. DETERMINISTIC ORDERING FOR INDEPENDENT NODES
# ---------------------------------------------------------------------------

def test_deterministic_ordering_for_independent_nodes():
    """Verify that independent nodes maintain a deterministic sequence across multiple runs."""
    custom_prereqs = {
        "skill_x": [],
        "skill_y": [],
        "skill_z": [],
    }
    input_skills = ["skill_x", "skill_y", "skill_z"]
    order_1 = topological_sort_skills(input_skills, prereq_map=custom_prereqs)
    order_2 = topological_sort_skills(input_skills, prereq_map=custom_prereqs)

    assert order_1 == order_2
    assert order_1 == ["skill_x", "skill_y", "skill_z"]


# ---------------------------------------------------------------------------
# 5. CYCLE DETECTION
# ---------------------------------------------------------------------------

def test_cycle_detection_raises_cycle_detected_error():
    """Verify that a circular prerequisite loop (A -> B -> A) raises CycleDetectedError."""
    cyclic_prereqs = {
        "skill_a": ["skill_b"],
        "skill_b": ["skill_a"],
    }
    with pytest.raises(CycleDetectedError) as exc_info:
        topological_sort_skills(["skill_a", "skill_b"], prereq_map=cyclic_prereqs)

    assert "cycle" in str(exc_info.value).lower()
    assert set(exc_info.value.cycle_nodes) == {"skill_a", "skill_b"}


def test_course_level_cycle_detection():
    """Verify that circular dependencies between courses raise CycleDetectedError."""
    cyclic_prereqs = {
        "skill_a": ["skill_b"],
        "skill_b": ["skill_a"],
    }
    courses = [
        {"id": "course_1", "title": "Course 1", "primary_skill": "skill_a", "covered_gap_skills": ["skill_a"]},
        {"id": "course_2", "title": "Course 2", "primary_skill": "skill_b", "covered_gap_skills": ["skill_b"]},
    ]
    with pytest.raises(CycleDetectedError):
        sequence_courses(courses, prereq_map=cyclic_prereqs)


# ---------------------------------------------------------------------------
# 6. MULTI-SKILL / MULTI-COURSE BEHAVIOR (NO DUPLICATION)
# ---------------------------------------------------------------------------

def test_multi_skill_course_not_duplicated():
    """Verify that a course covering multiple skills is included as a single milestone."""
    courses = [
        {
            "id": "intro_python_data",
            "title": "Python & Data Wrangling Bootcamp",
            "duration_hours": 15,
            "primary_skill": "python",
            "covered_gap_skills": ["python", "data_manip"],
            "match_score": 92.5,
        },
        {
            "id": "intro_ml",
            "title": "Machine Learning Fundamentals",
            "duration_hours": 20,
            "primary_skill": "ml_fund",
            "covered_gap_skills": ["ml_fund"],
            "match_score": 88.0,
        },
    ]

    roadmap: SequencedRoadmap = sequence_courses(courses, weekly_hours=10)

    # 1. Total courses must be 2, not duplicated
    assert roadmap.total_courses == 2
    assert len(roadmap.phases) == 2

    # 2. Phase 1 has Python & Data Wrangling (unlocks prerequisites)
    assert roadmap.phases[0].phase_number == 1
    assert len(roadmap.phases[0].courses) == 1
    assert roadmap.phases[0].courses[0].course_id == "intro_python_data"
    assert roadmap.phases[0].courses[0].status == "available"
    assert set(roadmap.phases[0].courses[0].covered_skills) == {"python", "data_manip"}

    # 3. Phase 2 has ML Fundamentals (depends on python & data_manip)
    assert roadmap.phases[1].phase_number == 2
    assert len(roadmap.phases[1].courses) == 1
    assert roadmap.phases[1].courses[0].course_id == "intro_ml"
    assert roadmap.phases[1].courses[0].status == "locked"

    # 4. Total hours and weeks
    assert roadmap.total_estimated_hours == 35
    assert roadmap.total_estimated_weeks == 4  # ceil(35 / 10) = 4


# ---------------------------------------------------------------------------
# 7. REAL TAXONOMY PREREQUISITE DAG INTEGRATION
# ---------------------------------------------------------------------------

def test_real_prerequisite_dag_ml_engineer_path():
    """Verify ordering with real CourseTide ML Engineer gap skills."""
    gap_skills = ["git", "data_manip", "ml_fund", "feat_eng", "deep_learning", "neural_nets", "mlops"]
    known_skills = ["python", "stats"]

    ordered = topological_sort_skills(gap_skills, known_skills=known_skills)

    # Assert prerequisite constraints from data/prerequisites.json
    # data_manip precedes ml_fund
    assert ordered.index("data_manip") < ordered.index("ml_fund")
    # ml_fund precedes feat_eng and deep_learning
    assert ordered.index("ml_fund") < ordered.index("feat_eng")
    assert ordered.index("ml_fund") < ordered.index("deep_learning")
    # deep_learning precedes neural_nets and mlops
    assert ordered.index("deep_learning") < ordered.index("neural_nets")
    assert ordered.index("deep_learning") < ordered.index("mlops")
    # git precedes mlops
    assert ordered.index("git") < ordered.index("mlops")


def test_known_skills_satisfaction_reduces_depth():
    """Verify that when python is already known, data_manip starts at depth 0 (Phase 1)."""
    skills = ["data_manip", "ml_fund"]

    # Without known python: python is not in skills so data_manip has no internal prereqs -> depth 0
    # But when evaluating with full DAG:
    depths_with_known = calculate_skill_depths(skills, known_skills=["python", "stats"])
    assert depths_with_known["data_manip"] == 0  # Phase 1
    assert depths_with_known["ml_fund"] == 1  # Phase 2 (depends on data_manip)


# ---------------------------------------------------------------------------
# 8. PRODUCTION REGRESSION & MULTI-SKILL SECONDARY ISOLATION
# ---------------------------------------------------------------------------

def test_production_six_course_ml_engineer_set_sequences_without_cycle():
    """Verify that the exact 6-course recommended set from the production smoke test sequences cleanly."""
    courses = [
        {
            "id": "machine-learning-project-titanic-house-prices",
            "title": "Machine Learning Project (Titanic/House Prices)",
            "primary_skill": "ml_fund",
            "covered_gap_skills": ["ml_fund", "data_manip"],
            "difficulty": "intermediate",
            "duration_hours": 10,
        },
        {
            "id": "made-with-ml-mlops-course",
            "title": "Made With ML - MLOps Course",
            "primary_skill": "mlops",
            "covered_gap_skills": ["mlops", "ml_fund"],
            "difficulty": "intermediate",
            "duration_hours": 20,
        },
        {
            "id": "mlops-specialization",
            "title": "MLOps Specialization",
            "primary_skill": "mlops",
            "covered_gap_skills": ["mlops", "deep_learning"],
            "difficulty": "advanced",
            "duration_hours": 35,
        },
        {
            "id": "machine-learning-specialization",
            "title": "Machine Learning Specialization",
            "primary_skill": "ml_fund",
            "covered_gap_skills": ["ml_fund", "data_manip"],
            "difficulty": "intermediate",
            "duration_hours": 40,
        },
        {
            "id": "deep-learning-specialization",
            "title": "Deep Learning Specialization",
            "primary_skill": "deep_learning",
            "covered_gap_skills": ["deep_learning", "neural_nets"],
            "difficulty": "advanced",
            "duration_hours": 60,
        },
        {
            "id": "intro-to-deep-learning",
            "title": "Intro to Deep Learning",
            "primary_skill": "deep_learning",
            "covered_gap_skills": ["deep_learning", "neural_nets"],
            "difficulty": "intermediate",
            "duration_hours": 6,
        },
    ]

    known_skills = ["python", "stats"]

    # 1. Must NOT raise CycleDetectedError
    roadmap = sequence_courses(courses, known_skills=known_skills, weekly_hours=8)

    # 2. All six courses represented
    assert roadmap.total_courses == 6
    all_course_ids = [c.course_id for p in roadmap.phases for c in p.courses]
    assert len(all_course_ids) == 6
    assert set(all_course_ids) == {c["id"] for c in courses}

    # 3. Phased structure: Foundational (ml_fund) -> Deep Learning -> MLOps
    phase_map = {c.course_id: c.phase_number for p in roadmap.phases for c in p.courses}
    
    # ML fundamentals courses must be in Phase 1
    assert phase_map["machine-learning-project-titanic-house-prices"] == 1
    assert phase_map["machine-learning-specialization"] == 1

    # Deep learning courses must come after ML fundamentals
    assert phase_map["deep-learning-specialization"] > phase_map["machine-learning-specialization"]
    assert phase_map["intro-to-deep-learning"] > phase_map["machine-learning-specialization"]

    # MLOps courses must come after Deep Learning
    assert phase_map["made-with-ml-mlops-course"] > phase_map["deep-learning-specialization"]
    assert phase_map["mlops-specialization"] > phase_map["deep-learning-specialization"]

    # 4. Phase 1 courses must have status='available', later phases status='locked'
    for p in roadmap.phases:
        for c in p.courses:
            if p.phase_number == 1:
                assert c.status == "available"
            else:
                assert c.status == "locked"

    # 5. Deterministic output
    roadmap_repeat = sequence_courses(courses, known_skills=known_skills, weekly_hours=8)
    repeat_ids = [c.course_id for p in roadmap_repeat.phases for c in p.courses]
    assert all_course_ids == repeat_ids


def test_secondary_skill_tag_does_not_create_reverse_dependency():
    """Verify that an advanced course tagging a foundational secondary skill does not reverse prerequisites."""
    courses = [
        {
            "id": "advanced-mlops",
            "title": "Advanced Production MLOps",
            "primary_skill": "mlops",  # Advanced depth 4
            "covered_gap_skills": ["mlops", "data_manip"],  # data_manip is foundational depth 1
        },
        {
            "id": "foundational-data",
            "title": "Data Manipulation 101",
            "primary_skill": "data_manip",  # Foundational depth 1
            "covered_gap_skills": ["data_manip"],
        },
    ]

    roadmap = sequence_courses(courses, known_skills=["python"], weekly_hours=10)

    # Foundational course must be Phase 1, Advanced MLOps must be later
    phase_map = {c.course_id: c.phase_number for p in roadmap.phases for c in p.courses}
    assert phase_map["foundational-data"] == 1
    assert phase_map["advanced-mlops"] > phase_map["foundational-data"]

