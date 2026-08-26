from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(String(64), primary_key=True, index=True)
    title = Column(Text, nullable=False)
    skill_id = Column(String(64), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True)
    difficulty = Column(String(32), nullable=False)  # 'beginner' | 'intermediate' | 'advanced'
    question_count = Column(Integer, nullable=False)
    pass_score = Column(Float, nullable=False)
    mastery_score = Column(Float, nullable=False)

    # Relationships
    skill = relationship("Skill", back_populates="assessments")

    def __repr__(self) -> str:
        return f"<Assessment id={self.id} skill_id={self.skill_id} pass={self.pass_score} mastery={self.mastery_score}>"
