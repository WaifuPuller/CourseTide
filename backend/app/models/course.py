from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from backend.app.database import Base

try:
    from pgvector.sqlalchemy import Vector
    VECTOR_AVAILABLE = True
except ImportError:
    VECTOR_AVAILABLE = False


class Course(Base):
    __tablename__ = "courses"

    id = Column(String(128), primary_key=True, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    difficulty = Column(String(32), nullable=False)  # 'beginner' | 'intermediate' | 'advanced'
    duration_hours = Column(Integer, nullable=False)
    resource_type = Column(String(32), nullable=False)  # 'course' | 'project' | 'assessment'
    domain = Column(String(64), nullable=False)  # 'ml' | 'web'
    is_mvp = Column(Boolean, nullable=False, default=False)
    source = Column(String(255), nullable=True)
    url = Column(Text, nullable=True)
    learning_outcomes = Column(Text, nullable=True)

    # 384-dimensional vector embedding column (pgvector)
    if VECTOR_AVAILABLE:
        embedding = Column(Vector(384), nullable=True)
    else:
        embedding = Column(Text, nullable=True)

    # Relationships
    skill_associations = relationship("CourseSkill", back_populates="course", cascade="all, delete-orphan")
    learning_paths = relationship("LearningPath", back_populates="course", cascade="all, delete-orphan")
    progress_events = relationship("ProgressEvent", back_populates="course", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Course id={self.id} title={self.title} domain={self.domain} is_mvp={self.is_mvp}>"


class CourseSkill(Base):
    __tablename__ = "course_skills"

    course_id = Column(String(128), ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    skill_id = Column(String(64), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    is_primary = Column(Boolean, nullable=False, default=False)

    # Relationships
    course = relationship("Course", back_populates="skill_associations")
    skill = relationship("Skill", back_populates="course_associations")

    def __repr__(self) -> str:
        return f"<CourseSkill course_id={self.course_id} skill_id={self.skill_id} is_primary={self.is_primary}>"
