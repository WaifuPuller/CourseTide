import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON
from backend.app.database import Base


class Learner(Base):
    __tablename__ = "learners"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    goal = Column(Text, nullable=True)
    parsed_goal = Column(JSONB().with_variant(JSON, "sqlite"), nullable=True)
    weekly_hours = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    learner_skills = relationship("LearnerSkill", back_populates="learner", cascade="all, delete-orphan")
    learning_paths = relationship("LearningPath", back_populates="learner", cascade="all, delete-orphan")
    progress_events = relationship("ProgressEvent", back_populates="learner", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Learner id={self.id} email={self.email} weekly_hours={self.weekly_hours}>"


class LearnerSkill(Base):
    __tablename__ = "learner_skills"

    learner_id = Column(UUID(as_uuid=True), ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True)
    skill_id = Column(String(64), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    status = Column(String(32), nullable=False, default="gap")  # 'known' | 'in_progress' | 'gap'
    mastery_score = Column(Float, nullable=True)

    # Relationships
    learner = relationship("Learner", back_populates="learner_skills")
    skill = relationship("Skill", back_populates="learner_skills")

    def __repr__(self) -> str:
        return f"<LearnerSkill learner_id={self.learner_id} skill_id={self.skill_id} status={self.status}>"
