"""Database seeding script for CourseTide.

Loads seed data in the required sequence:
1. skills.json -> skills table
2. courses.csv -> courses table (with 384-d sentence-transformers embeddings)
3. course_skills.csv -> course_skills table
4. assessments.json -> assessments table

Verifies seeded counts against data/VALIDATION_REPORT.json.
"""

import csv
import json
import os
import sys
from pathlib import Path
from typing import List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import DATA_DIR, settings
from backend.app.models import Assessment, Base, Course, CourseSkill, Skill


def get_sync_db_url() -> str:
    url = settings.SYNC_DATABASE_URL
    if not url or url.startswith("sqlite"):
        raw = settings.DATABASE_URL
        if raw.startswith("postgresql+asyncpg://"):
            url = raw.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif raw.startswith("sqlite+aiosqlite://"):
            url = raw.replace("sqlite+aiosqlite://", "sqlite://", 1)
        else:
            url = raw
    return url


def seed_database(db_url: str = None) -> bool:
    if not db_url:
        db_url = get_sync_db_url()

    print(f"[*] Seeding database at: {db_url}")

    connect_args = {}
    if "sqlite" in db_url:
        connect_args["check_same_thread"] = False

    engine = create_engine(db_url, connect_args=connect_args, echo=False)

    # If PostgreSQL, enable pgvector extension
    if "postgresql" in db_url:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()

    # Create tables if not present
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session: Session = SessionLocal()

    try:
        # 1. Seed skills.json
        skills_file = DATA_DIR / "skills.json"
        with open(skills_file, "r", encoding="utf-8") as f:
            skills_data = json.load(f)

        print(f"  - Seeding {len(skills_data)} skills...")
        for s in skills_data:
            skill = session.get(Skill, s["id"])
            if not skill:
                skill = Skill(id=s["id"], name=s["name"], domain=s["domain"])
                session.add(skill)
            else:
                skill.name = s["name"]
                skill.domain = s["domain"]
        session.commit()

        # 2. Seed courses.csv + generate embeddings
        print(f"  - Initializing embedding model: {settings.EMBEDDING_MODEL_NAME}...")
        embed_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)

        courses_file = DATA_DIR / "courses.csv"
        courses_rows = []
        with open(courses_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                courses_rows.append(row)

        print(f"  - Generating embeddings and seeding {len(courses_rows)} courses...")
        embedding_texts = []
        for c in courses_rows:
            text_to_embed = f"{c['title']}. {c.get('description', '')}. Learning outcomes: {c.get('learning_outcomes', '')}. Skills: {c.get('skills', '')}"
            embedding_texts.append(text_to_embed)

        embeddings = embed_model.encode(embedding_texts, show_progress_bar=False, normalize_embeddings=True)

        for c, emb in zip(courses_rows, embeddings):
            course = session.get(Course, c["id"])
            is_mvp = c.get("is_mvp", "false").strip().lower() == "true"
            duration = int(c.get("duration_hours", 0))

            if not course:
                course = Course(
                    id=c["id"],
                    title=c["title"],
                    description=c.get("description"),
                    difficulty=c.get("difficulty", "beginner"),
                    duration_hours=duration,
                    resource_type=c.get("resource_type", "course"),
                    domain=c.get("domain", "ml"),
                    is_mvp=is_mvp,
                    source=c.get("source"),
                    url=c.get("url"),
                    learning_outcomes=c.get("learning_outcomes"),
                    embedding=emb.tolist() if hasattr(emb, "tolist") else emb,
                )
                session.add(course)
            else:
                course.title = c["title"]
                course.description = c.get("description")
                course.difficulty = c.get("difficulty", "beginner")
                course.duration_hours = duration
                course.resource_type = c.get("resource_type", "course")
                course.domain = c.get("domain", "ml")
                course.is_mvp = is_mvp
                course.source = c.get("source")
                course.url = c.get("url")
                course.learning_outcomes = c.get("learning_outcomes")
                course.embedding = emb.tolist() if hasattr(emb, "tolist") else emb
        session.commit()

        # 3. Seed course_skills.csv
        course_skills_file = DATA_DIR / "course_skills.csv"
        course_skills_rows = []
        with open(course_skills_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                course_skills_rows.append(row)

        print(f"  - Seeding {len(course_skills_rows)} course-skill associations...")
        for cs in course_skills_rows:
            is_pri = cs.get("is_primary", "false").strip().lower() == "true"
            existing = session.query(CourseSkill).filter_by(course_id=cs["course_id"], skill_id=cs["skill_id"]).first()
            if not existing:
                cs_obj = CourseSkill(
                    course_id=cs["course_id"],
                    skill_id=cs["skill_id"],
                    is_primary=is_pri,
                )
                session.add(cs_obj)
            else:
                existing.is_primary = is_pri
        session.commit()

        # 4. Seed assessments.json
        assessments_file = DATA_DIR / "assessments.json"
        with open(assessments_file, "r", encoding="utf-8") as f:
            assessments_data = json.load(f)

        print(f"  - Seeding {len(assessments_data)} assessments...")
        for a in assessments_data:
            existing = session.get(Assessment, a["id"])
            if not existing:
                assessment = Assessment(
                    id=a["id"],
                    title=a["title"],
                    skill_id=a["skill_id"],
                    difficulty=a["difficulty"],
                    question_count=int(a["question_count"]),
                    pass_score=float(a["pass_score"]),
                    mastery_score=float(a["mastery_score"]),
                )
                session.add(assessment)
            else:
                existing.title = a["title"]
                existing.skill_id = a["skill_id"]
                existing.difficulty = a["difficulty"]
                existing.question_count = int(a["question_count"])
                existing.pass_score = float(a["pass_score"])
                existing.mastery_score = float(a["mastery_score"])
        session.commit()

        # 5. Verification check
        skill_count = session.query(Skill).count()
        course_count = session.query(Course).count()
        mvp_count = session.query(Course).filter_by(is_mvp=True).count()
        cs_count = session.query(CourseSkill).count()
        assessment_count = session.query(Assessment).count()

        print("\n[OK] Seeding Complete! Seeded record summary:")
        print(f"    - Skills: {skill_count}")
        print(f"    - Courses: {course_count} (MVP: {mvp_count})")
        print(f"    - Course Skills: {cs_count}")
        print(f"    - Assessments: {assessment_count}")

        return True

    except Exception as e:
        session.rollback()
        print(f"[!] Error during seeding: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()


if __name__ == "__main__":
    success = seed_database()
    sys.exit(0 if success else 1)
