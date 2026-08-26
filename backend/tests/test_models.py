import uuid
from backend.app.models import Assessment, Course, CourseSkill, Learner, LearnerSkill, LearningPath, ProgressEvent, Skill


def test_models_instantiation():
    """Verify that all SQLAlchemy models can be instantiated with their target schema types."""
    skill = Skill(id="python", name="Python Programming", domain="ml")
    assert skill.id == "python"
    assert skill.name == "Python Programming"
    assert skill.domain == "ml"

    course = Course(
        id="cs50-python",
        title="CS50 Python",
        description="Introduction to Python",
        difficulty="beginner",
        duration_hours=15,
        resource_type="course",
        domain="ml",
        is_mvp=True,
    )
    assert course.id == "cs50-python"
    assert course.is_mvp is True

    course_skill = CourseSkill(course_id="cs50-python", skill_id="python", is_primary=True)
    assert course_skill.course_id == "cs50-python"
    assert course_skill.is_primary is True

    learner_id = uuid.uuid4()
    learner = Learner(
        id=learner_id,
        name="Test Learner",
        email="test@coursetide.io",
        goal="Become an ML engineer",
        weekly_hours=10,
    )
    assert learner.id == learner_id
    assert learner.weekly_hours == 10

    learner_skill = LearnerSkill(learner_id=learner_id, skill_id="python", status="known", mastery_score=90.0)
    assert learner_skill.learner_id == learner_id
    assert learner_skill.status == "known"

    learning_path = LearningPath(
        id=uuid.uuid4(),
        learner_id=learner_id,
        phase_number=1,
        course_id="cs50-python",
        status="available",
        sequence_order=1,
    )
    assert learning_path.phase_number == 1

    progress = ProgressEvent(
        id=uuid.uuid4(),
        learner_id=learner_id,
        course_id="cs50-python",
        difficulty_feedback="just_right",
        assessment_score=85.0,
    )
    assert progress.assessment_score == 85.0

    assessment = Assessment(
        id="assessment-python-basics",
        title="Python Foundations Check",
        skill_id="python",
        difficulty="beginner",
        question_count=10,
        pass_score=70.0,
        mastery_score=85.0,
    )
    assert assessment.id == "assessment-python-basics"
    assert assessment.pass_score == 70.0
    assert assessment.mastery_score == 85.0
