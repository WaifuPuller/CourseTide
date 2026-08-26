"""initial_coursetide_schema

Revision ID: 31500d98ece1
Revises: 
Create Date: 2026-08-26 15:23:43.228710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

try:
    from pgvector.sqlalchemy import Vector
    VECTOR_TYPE = Vector(384)
except ImportError:
    VECTOR_TYPE = sa.Text()


# revision identifiers, used by Alembic.
revision: str = '31500d98ece1'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector if postgresql
    bind = op.get_bind()
    if bind and "postgresql" in bind.engine.name:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 1. skills
    op.create_table(
        'skills',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('domain', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_skills_id'), 'skills', ['id'], unique=False)

    # 2. courses
    op.create_table(
        'courses',
        sa.Column('id', sa.String(length=128), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('difficulty', sa.String(length=32), nullable=False),
        sa.Column('duration_hours', sa.Integer(), nullable=False),
        sa.Column('resource_type', sa.String(length=32), nullable=False),
        sa.Column('domain', sa.String(length=64), nullable=False),
        sa.Column('is_mvp', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('learning_outcomes', sa.Text(), nullable=True),
        sa.Column('embedding', VECTOR_TYPE, nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_courses_id'), 'courses', ['id'], unique=False)

    # 3. course_skills
    op.create_table(
        'course_skills',
        sa.Column('course_id', sa.String(length=128), nullable=False),
        sa.Column('skill_id', sa.String(length=64), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('course_id', 'skill_id'),
    )

    # 4. learners
    op.create_table(
        'learners',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('goal', sa.Text(), nullable=True),
        sa.Column('parsed_goal', postgresql.JSONB().with_variant(sa.JSON(), 'sqlite'), nullable=True),
        sa.Column('weekly_hours', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_learners_id'), 'learners', ['id'], unique=False)

    # 5. learner_skills
    op.create_table(
        'learner_skills',
        sa.Column('learner_id', sa.UUID(), nullable=False),
        sa.Column('skill_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='gap'),
        sa.Column('mastery_score', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['learner_id'], ['learners.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('learner_id', 'skill_id'),
    )

    # 6. learning_paths
    op.create_table(
        'learning_paths',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('learner_id', sa.UUID(), nullable=False),
        sa.Column('phase_number', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='locked'),
        sa.Column('sequence_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['learner_id'], ['learners.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_learning_paths_id'), 'learning_paths', ['id'], unique=False)
    op.create_index(op.f('ix_learning_paths_learner_id'), 'learning_paths', ['learner_id'], unique=False)
    op.create_index(op.f('ix_learning_paths_course_id'), 'learning_paths', ['course_id'], unique=False)

    # 7. progress_events
    op.create_table(
        'progress_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('learner_id', sa.UUID(), nullable=False),
        sa.Column('course_id', sa.String(length=128), nullable=False),
        sa.Column('difficulty_feedback', sa.String(length=32), nullable=True),
        sa.Column('assessment_score', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['learner_id'], ['learners.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_progress_events_id'), 'progress_events', ['id'], unique=False)
    op.create_index(op.f('ix_progress_events_learner_id'), 'progress_events', ['learner_id'], unique=False)
    op.create_index(op.f('ix_progress_events_course_id'), 'progress_events', ['course_id'], unique=False)

    # 8. assessments
    op.create_table(
        'assessments',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('skill_id', sa.String(length=64), nullable=False),
        sa.Column('difficulty', sa.String(length=32), nullable=False),
        sa.Column('question_count', sa.Integer(), nullable=False),
        sa.Column('pass_score', sa.Float(), nullable=False),
        sa.Column('mastery_score', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_assessments_id'), 'assessments', ['id'], unique=False)
    op.create_index(op.f('ix_assessments_skill_id'), 'assessments', ['skill_id'], unique=False)


def downgrade() -> None:
    op.drop_table('assessments')
    op.drop_table('progress_events')
    op.drop_table('learning_paths')
    op.drop_table('learner_skills')
    op.drop_table('learners')
    op.drop_table('course_skills')
    op.drop_table('courses')
    op.drop_table('skills')
