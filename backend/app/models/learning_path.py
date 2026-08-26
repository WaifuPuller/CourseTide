import uuid
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.app.database import Base


class LearningPath(Base):
    __tablename__ = "learning_paths"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    learner_id = Column(UUID(as_uuid=True), ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True)
    phase_number = Column(Integer, nullable=False)
    course_id = Column(String(128), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="locked")  # 'locked' | 'available' | 'in_progress' | 'done'
    sequence_order = Column(Integer, nullable=False)

    # Relationships
    learner = relationship("Learner", back_populates="learning_paths")
    course = relationship("Course", back_populates="learning_paths")

    def __repr__(self) -> str:
        return f"<LearningPath id={self.id} learner_id={self.learner_id} phase={self.phase_number} course={self.course_id} status={self.status}>"
