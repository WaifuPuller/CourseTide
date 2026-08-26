import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.app.database import Base


class ProgressEvent(Base):
    __tablename__ = "progress_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    learner_id = Column(UUID(as_uuid=True), ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(String(128), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    difficulty_feedback = Column(String(32), nullable=True)  # 'too_easy' | 'just_right' | 'too_hard'
    assessment_score = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    learner = relationship("Learner", back_populates="progress_events")
    course = relationship("Course", back_populates="progress_events")

    def __repr__(self) -> str:
        return f"<ProgressEvent id={self.id} learner_id={self.learner_id} course={self.course_id} score={self.assessment_score}>"
