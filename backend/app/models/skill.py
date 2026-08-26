from sqlalchemy import Column, String, Text
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(Text, nullable=False)
    domain = Column(String(64), nullable=False)  # 'ml' | 'web' | 'general'

    # Relationships
    course_associations = relationship("CourseSkill", back_populates="skill", cascade="all, delete-orphan")
    learner_skills = relationship("LearnerSkill", back_populates="skill", cascade="all, delete-orphan")
    assessments = relationship("Assessment", back_populates="skill", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Skill id={self.id} name={self.name} domain={self.domain}>"
