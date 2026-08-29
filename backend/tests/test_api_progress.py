"""Tests for Progress Event API, Deterministic Mastery & Fast-Track, and Remedial Adaptation.

Checkpoint 1 Scope:
- Valid payload with assessment_score and/or difficulty_feedback is persisted in progress_events.
- Assessment score marks course as 'done'; feedback-only does not.
- Phase unlocking occurs when all courses in a phase are satisfied ('done' | 'skipped').
- Validation error handling (400, 404, 422, 500) and transactional rollback.

Checkpoint 2 Scope:
- assessment_score > 85.0 triggers deterministic fast-track mastery for primary skill only.
- learner_skills status set to 'known', mastery_score set to max(existing, new).
- parsed_goal known_skills and gap_skills updated.
- First qualifying subsequent course with matching primary skill and difficulty <= completed is skipped.
- Repeated > 85.0 submissions on completed course are strictly idempotent and do not cascade skips.
- Locked and skipped courses cannot be directly submitted via API (HTTP 400).

Checkpoint 3 Scope:
- assessment_score < 50.0 triggers deterministic remedial course insertion.
- Remedial course is strictly lower difficulty than failed course.
- Failed beginner course produces no remedial candidate (returns neutral message).
- Remedial course inserted immediately after failed course (sequence_order = failed.sequence_order + 1).
- All subsequent sequence_order values shifted by +1.
- Remedial course status is 'available', phase_number matches failed course's phase.
- Repeated low-score submissions on completed course are idempotent (no duplicate insertions or shifts).
- Database failure during remediation rolls back all changes atomically.
"""

import asyncio
import os
import unittest.mock
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import Course, CourseSkill, Learner, LearnerSkill, LearningPath, ProgressEvent, Skill

# Use isolated in-memory SQLite database
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


async def _setup_test_db():
    """Create tables and seed minimal catalog and learner fixtures."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        # 1. Skills
        s1 = Skill(id="python", name="Python Programming", domain="ml")
        s2 = Skill(id="ml_fund", name="Machine Learning Fundamentals", domain="ml")
        s3 = Skill(id="data_manip", name="Data Manipulation", domain="ml")
        s4 = Skill(id="deep_learning", name="Deep Learning", domain="ml")
        session.add_all([s1, s2, s3, s4])

        # 2. Courses
        # Course P1-A: Intermediate, Primary = ml_fund, Secondary = data_manip
        c1 = Course(id="course-p1-a", title="Phase 1 Course A", difficulty="intermediate", duration_hours=10, resource_type="course", domain="ml", is_mvp=True)
        # Course P1-B: Beginner, Primary = ml_fund (Qualifies for skip if P1-A completed with >85)
        c2 = Course(id="course-p1-b", title="Phase 1 Course B", difficulty="beginner", duration_hours=15, resource_type="course", domain="ml", is_mvp=True)
        # Course P1-C: Intermediate, Primary = ml_fund (Qualifies for skip if P1-A completed with >85)
        c3 = Course(id="course-p1-c", title="Phase 1 Course C", difficulty="intermediate", duration_hours=12, resource_type="course", domain="ml", is_mvp=True)
        # Course P1-Harder: Advanced, Primary = ml_fund (Does NOT qualify for skip if P1-A is intermediate)
        c4 = Course(id="course-p1-harder", title="Phase 1 Harder Course", difficulty="advanced", duration_hours=20, resource_type="course", domain="ml", is_mvp=True)
        # Course P1-DiffSkill: Beginner, Primary = data_manip (Does NOT qualify for skip if primary is ml_fund)
        c5 = Course(id="course-p1-diff", title="Phase 1 Diff Skill Course", difficulty="beginner", duration_hours=8, resource_type="course", domain="ml", is_mvp=True)
        # Course P2-A: Advanced, Primary = deep_learning
        c6 = Course(id="course-p2-a", title="Phase 2 Course A", difficulty="advanced", duration_hours=20, resource_type="course", domain="ml", is_mvp=True)
        # Course Not in Path
        c7 = Course(id="course-not-in-path", title="Unrelated Course", difficulty="beginner", duration_hours=5, resource_type="course", domain="ml", is_mvp=True)
        
        # Remedial Catalog Courses
        # Beginner remedial for ml_fund (duration 4 hours)
        c_rem_ml_1 = Course(id="course-rem-ml-beg1", title="Remedial ML Beginner Short", difficulty="beginner", duration_hours=4, resource_type="course", domain="ml", is_mvp=True)
        # Beginner remedial for ml_fund (duration 8 hours)
        c_rem_ml_2 = Course(id="course-rem-ml-beg2", title="Remedial ML Beginner Long", difficulty="beginner", duration_hours=8, resource_type="course", domain="ml", is_mvp=True)
        # Intermediate remedial for deep_learning (duration 10 hours)
        c_rem_dl_int = Course(id="course-rem-dl-int", title="Remedial DL Intermediate", difficulty="intermediate", duration_hours=10, resource_type="course", domain="ml", is_mvp=True)
        # Beginner remedial for deep_learning (duration 6 hours)
        c_rem_dl_beg = Course(id="course-rem-dl-beg", title="Remedial DL Beginner", difficulty="beginner", duration_hours=6, resource_type="course", domain="ml", is_mvp=True)
        # Non-MVP remedial candidate
        c_rem_non_mvp = Course(id="course-rem-non-mvp", title="Non-MVP Course", difficulty="beginner", duration_hours=3, resource_type="course", domain="ml", is_mvp=False)
        # Unknown difficulty course
        c_rem_unk = Course(id="course-rem-unk-diff", title="Unknown Diff Course", difficulty="unknown_tier", duration_hours=5, resource_type="course", domain="ml", is_mvp=True)

        session.add_all([
            c1, c2, c3, c4, c5, c6, c7,
            c_rem_ml_1, c_rem_ml_2, c_rem_dl_int, c_rem_dl_beg, c_rem_non_mvp, c_rem_unk,
        ])

        # 3. CourseSkills
        cs1 = CourseSkill(course_id="course-p1-a", skill_id="ml_fund", is_primary=True)
        cs1_sec = CourseSkill(course_id="course-p1-a", skill_id="data_manip", is_primary=False)
        cs2 = CourseSkill(course_id="course-p1-b", skill_id="ml_fund", is_primary=True)
        cs3 = CourseSkill(course_id="course-p1-c", skill_id="ml_fund", is_primary=True)
        cs4 = CourseSkill(course_id="course-p1-harder", skill_id="ml_fund", is_primary=True)
        cs5 = CourseSkill(course_id="course-p1-diff", skill_id="data_manip", is_primary=True)
        cs6 = CourseSkill(course_id="course-p2-a", skill_id="deep_learning", is_primary=True)
        cs7 = CourseSkill(course_id="course-not-in-path", skill_id="python", is_primary=True)

        cs_r1 = CourseSkill(course_id="course-rem-ml-beg1", skill_id="ml_fund", is_primary=True)
        cs_r2 = CourseSkill(course_id="course-rem-ml-beg2", skill_id="ml_fund", is_primary=True)
        cs_rd1 = CourseSkill(course_id="course-rem-dl-int", skill_id="deep_learning", is_primary=True)
        cs_rd2 = CourseSkill(course_id="course-rem-dl-beg", skill_id="deep_learning", is_primary=True)
        cs_rnm = CourseSkill(course_id="course-rem-non-mvp", skill_id="ml_fund", is_primary=True)
        cs_runk = CourseSkill(course_id="course-rem-unk-diff", skill_id="ml_fund", is_primary=True)

        session.add_all([
            cs1, cs1_sec, cs2, cs3, cs4, cs5, cs6, cs7,
            cs_r1, cs_r2, cs_rd1, cs_rd2, cs_rnm, cs_runk,
        ])

        # 4. Learner
        learner_id = uuid.uuid4()
        learner = Learner(
            id=learner_id,
            name="Test Progress Learner",
            email="progress_learner@coursetide.test",
            goal="Become an ML engineer",
            weekly_hours=8,
            parsed_goal={
                "target_role": "ml_engineer",
                "role_name": "Machine Learning Engineer",
                "timeframe_months": 6,
                "weekly_hours": 8,
                "known_skills": ["python"],
                "gap_skills": ["ml_fund", "data_manip", "deep_learning"],
                "unrecognized_skills": [],
                "match_percentage": 25.0,
            },
        )
        session.add(learner)

        # 5. Learning Paths (Standard 3-course setup: P1-A available, P1-B available, P2-A locked)
        lp1 = LearningPath(learner_id=learner_id, course_id="course-p1-a", phase_number=1, sequence_order=1, status="available")
        lp2 = LearningPath(learner_id=learner_id, course_id="course-p1-b", phase_number=1, sequence_order=2, status="available")
        lp3 = LearningPath(learner_id=learner_id, course_id="course-p2-a", phase_number=2, sequence_order=3, status="locked")
        session.add_all([lp1, lp2, lp3])

        # 6. LearnerSkill initial gap states
        ls1 = LearnerSkill(learner_id=learner_id, skill_id="ml_fund", status="gap", mastery_score=None)
        ls2 = LearnerSkill(learner_id=learner_id, skill_id="data_manip", status="gap", mastery_score=None)
        ls3 = LearnerSkill(learner_id=learner_id, skill_id="deep_learning", status="gap", mastery_score=None)
        session.add_all([ls1, ls2, ls3])

        await session.commit()
        return learner_id


def make_request(method: str, url: str, json_payload: dict = None):
    """Helper to run async client synchronously in test cases."""
    async def _do():
        app.dependency_overrides[get_db] = override_get_db
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            if method.lower() == "post":
                return await client.post(url, json=json_payload)
            elif method.lower() == "get":
                return await client.get(url)
    return asyncio.run(_do())


# ==============================================================================
# CHECKPOINT 1 BASE TESTS
# ==============================================================================

def test_valid_progress_submission_records_event():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-p1-a",
        "difficulty_feedback": "just_right",
        "assessment_score": 80.0,
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["course_status"] == "done"
    assert data["adaptation_applied"] == "none"

    async def _verify():
        async with TestSessionLocal() as session:
            stmt = select(ProgressEvent).where(ProgressEvent.learner_id == learner_id)
            res = await session.execute(stmt)
            events = res.scalars().all()
            assert len(events) == 1
            assert events[0].course_id == "course-p1-a"
            assert events[0].assessment_score == 80.0
            assert events[0].difficulty_feedback == "just_right"

    asyncio.run(_verify())


def test_valid_score_marks_course_done():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-p1-a",
        "assessment_score": 75.0,
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 200
    assert resp.json()["course_status"] == "done"

    async def _verify():
        async with TestSessionLocal() as session:
            stmt = select(LearningPath).where(
                LearningPath.learner_id == learner_id,
                LearningPath.course_id == "course-p1-a",
            )
            res = await session.execute(stmt)
            lp = res.scalar_one()
            assert lp.status == "done"

    asyncio.run(_verify())


def test_feedback_only_records_event_without_marking_done():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-p1-a",
        "difficulty_feedback": "too_hard",
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 200
    assert resp.json()["course_status"] == "available"

    async def _verify():
        async with TestSessionLocal() as session:
            stmt = select(LearningPath).where(
                LearningPath.learner_id == learner_id,
                LearningPath.course_id == "course-p1-a",
            )
            res = await session.execute(stmt)
            lp = res.scalar_one()
            assert lp.status == "available"

    asyncio.run(_verify())


def test_progress_unknown_learner_returns_404():
    asyncio.run(_setup_test_db())
    random_id = str(uuid.uuid4())
    payload = {
        "learner_id": random_id,
        "course_id": "course-p1-a",
        "assessment_score": 80.0,
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 404
    assert f"Learner with ID '{random_id}' not found." in resp.json()["detail"]


def test_progress_course_not_in_learner_path_returns_400():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-not-in-path",
        "assessment_score": 85.0,
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 400
    assert "not in the learner's active roadmap" in resp.json()["detail"]


def test_progress_invalid_feedback_enum_returns_422():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-p1-a",
        "difficulty_feedback": "super_easy",
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 422


def test_progress_invalid_score_below_zero_returns_422():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-p1-a",
        "assessment_score": -5.0,
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 422


def test_progress_invalid_score_above_100_returns_422():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-p1-a",
        "assessment_score": 105.0,
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 422


def test_progress_missing_both_score_and_feedback_returns_422():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-p1-a",
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 422
    assert "At least one of 'difficulty_feedback' or 'assessment_score' must be provided." in str(resp.json()["detail"])


def test_score_zero_accepted():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-p1-a",
        "assessment_score": 0.0,
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 200
    assert resp.json()["course_status"] == "done"


def test_score_100_accepted():
    learner_id = asyncio.run(_setup_test_db())
    payload = {
        "learner_id": str(learner_id),
        "course_id": "course-p1-a",
        "assessment_score": 100.0,
    }
    resp = make_request("post", "/api/progress", json_payload=payload)
    assert resp.status_code == 200
    assert resp.json()["course_status"] == "done"


def test_phase_unlock_when_all_phase_courses_done():
    learner_id = asyncio.run(_setup_test_db())

    # Complete Course P1-A (Score 80.0 -> neutral pass)
    resp1 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 80.0},
    )
    assert resp1.status_code == 200

    # Phase 2 Course P2-A must still be locked
    async def _check_phase2_locked():
        async with TestSessionLocal() as session:
            stmt = select(LearningPath).where(
                LearningPath.learner_id == learner_id,
                LearningPath.course_id == "course-p2-a",
            )
            res = await session.execute(stmt)
            lp = res.scalar_one()
            assert lp.status == "locked"

    asyncio.run(_check_phase2_locked())

    # Complete Course P1-B (Score 80.0 -> neutral pass)
    resp2 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-b", "assessment_score": 80.0},
    )
    assert resp2.status_code == 200

    # Now Phase 1 is complete -> Phase 2 Course P2-A must be unlocked ('available')
    async def _check_phase2_unlocked():
        async with TestSessionLocal() as session:
            stmt = select(LearningPath).where(
                LearningPath.learner_id == learner_id,
                LearningPath.course_id == "course-p2-a",
            )
            res = await session.execute(stmt)
            lp = res.scalar_one()
            assert lp.status == "available"

    asyncio.run(_check_phase2_unlocked())


def test_progress_db_failure_rolls_back_all_changes():
    learner_id = asyncio.run(_setup_test_db())

    with unittest.mock.patch.object(AsyncSession, "commit", side_effect=RuntimeError("Simulated DB crash")):
        resp = make_request(
            "post",
            "/api/progress",
            json_payload={
                "learner_id": str(learner_id),
                "course_id": "course-p1-a",
                "assessment_score": 90.0,
            },
        )
        assert resp.status_code == 500

    async def _verify_no_records():
        async with TestSessionLocal() as session:
            stmt = select(ProgressEvent).where(ProgressEvent.learner_id == learner_id)
            res = await session.execute(stmt)
            events = res.scalars().all()
            assert len(events) == 0

            stmt_lp = select(LearningPath).where(
                LearningPath.learner_id == learner_id,
                LearningPath.course_id == "course-p1-a",
            )
            res_lp = await session.execute(stmt_lp)
            lp = res_lp.scalar_one()
            assert lp.status == "available"

    asyncio.run(_verify_no_records())


# ==============================================================================
# CHECKPOINT 2 MASTERY & FAST-TRACK TESTS
# ==============================================================================

def test_score_85_point_0_does_not_trigger_mastery():
    learner_id = asyncio.run(_setup_test_db())
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 85.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_applied"] == "none"

    async def _verify():
        async with TestSessionLocal() as session:
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.status == "gap"

            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "available"

    asyncio.run(_verify())


def test_score_85_point_1_triggers_primary_skill_mastery():
    learner_id = asyncio.run(_setup_test_db())
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 85.1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["adaptation_applied"] == "mastery_skip"
    assert data["adaptation_details"]["mastered_skill"] == "ml_fund"
    assert data["adaptation_details"]["skipped_course_id"] == "course-p1-b"


def test_score_above_85_updates_learner_skills_status_to_known():
    learner_id = asyncio.run(_setup_test_db())
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 92.5},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.status == "known"
            assert ls.mastery_score == 92.5

    asyncio.run(_verify())


def test_mastery_score_uses_max_of_existing_and_new():
    learner_id = asyncio.run(_setup_test_db())

    async def _prep():
        async with TestSessionLocal() as session:
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            ls.mastery_score = 95.0
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.mastery_score == 95.0

    asyncio.run(_verify())


def test_parsed_goal_known_skills_is_updated():
    learner_id = asyncio.run(_setup_test_db())
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            assert "ml_fund" in learner.parsed_goal["known_skills"]

    asyncio.run(_verify())


def test_parsed_goal_gap_skills_removes_mastered_primary_skill():
    learner_id = asyncio.run(_setup_test_db())
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            assert "ml_fund" not in learner.parsed_goal["gap_skills"]

    asyncio.run(_verify())


def test_secondary_covered_skills_remain_unchanged():
    learner_id = asyncio.run(_setup_test_db())
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 95.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            ls_sec = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "data_manip")
            )).scalar_one()
            assert ls_sec.status == "gap"

            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            assert "data_manip" in learner.parsed_goal["gap_skills"]
            assert "data_manip" not in learner.parsed_goal["known_skills"]

    asyncio.run(_verify())


def test_matching_later_same_primary_course_is_skipped():
    learner_id = asyncio.run(_setup_test_db())
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"

    asyncio.run(_verify())


def test_skip_only_affects_one_qualifying_course():
    learner_id = asyncio.run(_setup_test_db())

    async def _prep():
        async with TestSessionLocal() as session:
            lp_c = LearningPath(learner_id=learner_id, course_id="course-p1-c", phase_number=1, sequence_order=3, status="available")
            session.add(lp_c)
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"

            lp_c = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-c")
            )).scalar_one()
            assert lp_c.status == "available"

    asyncio.run(_verify())


def test_different_primary_skill_course_is_not_skipped():
    learner_id = asyncio.run(_setup_test_db())

    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            lp_b.course_id = "course-p1-diff"
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_applied"] == "mastery"

    async def _verify():
        async with TestSessionLocal() as session:
            lp_diff = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-diff")
            )).scalar_one()
            assert lp_diff.status == "available"

    asyncio.run(_verify())


def test_harder_course_is_not_skipped():
    learner_id = asyncio.run(_setup_test_db())

    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            lp_b.course_id = "course-p1-harder"
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_applied"] == "mastery"

    async def _verify():
        async with TestSessionLocal() as session:
            lp_harder = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-harder")
            )).scalar_one()
            assert lp_harder.status == "available"

    asyncio.run(_verify())


def test_earlier_course_is_not_skipped():
    learner_id = asyncio.run(_setup_test_db())

    # Complete course at sequence 2 (course-p1-b)
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-b", "assessment_score": 95.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            # Earlier course (sequence 1: course-p1-a) must remain available
            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            assert lp_a.status == "available"

    asyncio.run(_verify())


def test_already_done_or_skipped_course_is_not_selected_for_skip():
    learner_id = asyncio.run(_setup_test_db())

    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            lp_b.status = "done"

            lp_c = LearningPath(learner_id=learner_id, course_id="course-p1-c", phase_number=1, sequence_order=3, status="available")
            session.add(lp_c)
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_details"]["skipped_course_id"] == "course-p1-c"


def test_sequence_order_and_phase_number_remain_unchanged_on_skip():
    learner_id = asyncio.run(_setup_test_db())
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"
            assert lp_b.sequence_order == 2
            assert lp_b.phase_number == 1

    asyncio.run(_verify())


def test_skipped_row_remains_in_database():
    learner_id = asyncio.run(_setup_test_db())
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            lps = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id)
            )).scalars().all()
            assert len(lps) == 3

    asyncio.run(_verify())


def test_phase_unlock_works_when_current_phase_is_done_and_skipped():
    learner_id = asyncio.run(_setup_test_db())
    # Submitting >85 on course-p1-a marks p1-a done and p1-b skipped -> Phase 1 fully satisfied
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            # Phase 2 course should be unlocked to available
            lp_p2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p2-a")
            )).scalar_one()
            assert lp_p2.status == "available"

    asyncio.run(_verify())


def test_no_qualifying_skip_target_mastery_still_succeeds():
    learner_id = asyncio.run(_setup_test_db())

    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            await session.delete(lp_b)
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_applied"] == "mastery"
    assert resp.json()["adaptation_details"]["mastered_skill"] == "ml_fund"
    assert resp.json()["adaptation_details"]["skipped_course_id"] is None


def test_repeated_above_85_submission_does_not_create_additional_side_effects():
    """Verify resubmitting a high score on an already done course is idempotent and does not skip extra courses."""
    learner_id = asyncio.run(_setup_test_db())

    # Add course-p1-c at sequence 3
    async def _prep():
        async with TestSessionLocal() as session:
            lp_c = LearningPath(learner_id=learner_id, course_id="course-p1-c", phase_number=1, sequence_order=3, status="available")
            session.add(lp_c)
            await session.commit()

    asyncio.run(_prep())

    # First submission
    resp1 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 90.0},
    )
    assert resp1.status_code == 200
    assert resp1.json()["adaptation_applied"] == "mastery_skip"

    # Second submission on the same course
    resp2 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 95.0},
    )
    assert resp2.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            # P1-B was skipped on 1st run
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"

            # P1-C was NOT skipped on 2nd run (MUST remain available!)
            lp_c = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-c")
            )).scalar_one()
            assert lp_c.status == "available"

    asyncio.run(_verify())


def test_rollback_occurs_if_mastery_mutation_fails_midway():
    """Verify that if an error occurs during mastery or commit, all progress event and mastery changes are rolled back."""
    learner_id = asyncio.run(_setup_test_db())

    with unittest.mock.patch.object(AsyncSession, "commit", side_effect=RuntimeError("Simulated DB crash during commit")):
        resp = make_request(
            "post",
            "/api/progress",
            json_payload={
                "learner_id": str(learner_id),
                "course_id": "course-p1-a",
                "assessment_score": 98.0,
            },
        )
        assert resp.status_code == 500

    async def _verify():
        async with TestSessionLocal() as session:
            # 0 Progress Events
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 0

            # Skill ml_fund remains gap
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.status == "gap"

            # Course P1-A remains available
            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            assert lp_a.status == "available"

            # Course P1-B remains available
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "available"

    asyncio.run(_verify())


def test_repeated_neutral_score_on_done_course_records_event_without_adaptation():
    """Verify resubmitting a neutral score on an already done course records event without mutation."""
    learner_id = asyncio.run(_setup_test_db())

    # 1. Complete course-p1-a with score 80.0
    resp1 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 80.0},
    )
    assert resp1.status_code == 200

    # 2. Resubmit neutral score 82.0 on already done course-p1-a
    resp2 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 82.0},
    )
    assert resp2.status_code == 200
    assert resp2.json()["adaptation_applied"] == "none"
    assert resp2.json()["adaptation_details"]["message"] == "Progress event recorded for previously completed course."

    async def _verify():
        async with TestSessionLocal() as session:
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 2  # Both events saved in audit log!

            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            assert lp_a.status == "done"

    asyncio.run(_verify())


def test_progress_locked_course_is_rejected():
    """Verify progress submission on a locked course is rejected with HTTP 400 and creates no records."""
    learner_id = asyncio.run(_setup_test_db())

    # course-p2-a is initially 'locked' in Phase 2
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p2-a",
            "assessment_score": 95.0,
        },
    )
    assert resp.status_code == 400
    assert "is locked. Complete preceding phase milestones first." in resp.json()["detail"]

    # Verify zero side effects in database
    async def _verify():
        async with TestSessionLocal() as session:
            # 0 Progress Events
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 0

            # Course remains locked
            lp_p2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p2-a")
            )).scalar_one()
            assert lp_p2.status == "locked"

            # Skill deep_learning remains unmastered (not in known_skills)
            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            assert "deep_learning" in learner.parsed_goal["gap_skills"]
            assert "deep_learning" not in learner.parsed_goal["known_skills"]

    asyncio.run(_verify())


def test_progress_skipped_course_is_rejected():
    """Verify progress submission on a skipped course is rejected with HTTP 400 and creates no records."""
    learner_id = asyncio.run(_setup_test_db())

    # Pre-set course-p1-b to 'skipped'
    async def _prep():
        async with TestSessionLocal() as session:
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            lp_b.status = "skipped"
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-b",
            "assessment_score": 90.0,
        },
    )
    assert resp.status_code == 400
    assert "was skipped due to demonstrated mastery." in resp.json()["detail"]

    # Verify zero side effects in database
    async def _verify():
        async with TestSessionLocal() as session:
            # 0 Progress Events
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 0

            # Course remains skipped
            lp_b = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-b")
            )).scalar_one()
            assert lp_b.status == "skipped"

    asyncio.run(_verify())


def test_progress_in_progress_course_is_allowed():
    """Verify progress submission on an in_progress course is allowed and marks it done."""
    learner_id = asyncio.run(_setup_test_db())

    # Pre-set course-p1-a to 'in_progress'
    async def _prep():
        async with TestSessionLocal() as session:
            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            lp_a.status = "in_progress"
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={
            "learner_id": str(learner_id),
            "course_id": "course-p1-a",
            "assessment_score": 80.0,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["course_status"] == "done"

    async def _verify():
        async with TestSessionLocal() as session:
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 1

            lp_a = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p1-a")
            )).scalar_one()
            assert lp_a.status == "done"

    asyncio.run(_verify())


# ==============================================================================
# CHECKPOINT 3 REMEDIAL ADAPTATION TESTS
# ==============================================================================

def test_score_49_point_9_triggers_remediation():
    """Score 49.9 on intermediate course inserts strictly lower difficulty beginner course."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 49.9},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["course_status"] == "done"
    assert data["adaptation_applied"] == "remediation"
    assert data["adaptation_details"]["inserted_course_id"] == "course-rem-ml-beg1"


def test_score_50_point_0_does_not_trigger_remediation():
    """Score 50.0 is a neutral completion and does not trigger remediation."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 50.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_status"] == "done"
    assert data["adaptation_applied"] == "none"
    assert data["adaptation_details"]["inserted_course_id"] is None


def test_remedial_course_targets_primary_skill():
    """Remediation identifies primary skill of failed course and matches catalog course with same primary skill."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 35.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["adaptation_applied"] == "remediation"
    assert data["adaptation_details"]["inserted_course_id"] == "course-rem-ml-beg1"


def test_strictly_lower_difficulty_enforced():
    """Intermediate failure only selects beginner courses; intermediate candidates are excluded."""
    learner_id = asyncio.run(_setup_test_db())

    # When course-p1-a (intermediate) fails, candidate must be beginner.
    # course-p1-c (intermediate) must be ignored, course-rem-ml-beg1 (beginner, 4h) selected.
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_details"]["inserted_course_id"] == "course-rem-ml-beg1"


def test_failed_beginner_course_produces_no_remedial_candidate():
    """A failed beginner course cannot have a strictly lower difficulty remedial course."""
    learner_id = asyncio.run(_setup_test_db())

    # course-p1-b is beginner
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-b", "assessment_score": 30.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["course_status"] == "done"
    assert data["adaptation_applied"] == "none"
    assert data["adaptation_details"]["inserted_course_id"] is None
    assert "No strictly lower introductory course available" in data["adaptation_details"]["message"]


def test_failed_advanced_course_selects_closest_lower_tier():
    """An advanced course failure selects intermediate over beginner as the closest lower tier."""
    learner_id = asyncio.run(_setup_test_db())

    # First unlock phase 2 by completing phase 1
    make_request("post", "/api/progress", json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 80.0})
    make_request("post", "/api/progress", json_payload={"learner_id": str(learner_id), "course_id": "course-p1-b", "assessment_score": 80.0})

    # Now course-p2-a (advanced, deep_learning) is available. Fail it with score 45.0.
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p2-a", "assessment_score": 45.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["adaptation_applied"] == "remediation"
    # course-rem-dl-int (intermediate) selected over course-rem-dl-beg (beginner)
    assert data["adaptation_details"]["inserted_course_id"] == "course-rem-dl-int"


def test_tie_breaker_prefers_shorter_duration():
    """When multiple candidates share same lower difficulty, shortest duration is selected."""
    learner_id = asyncio.run(_setup_test_db())

    # Candidates for ml_fund beginner: course-rem-ml-beg1 (4h) vs course-rem-ml-beg2 (8h)
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_details"]["inserted_course_id"] == "course-rem-ml-beg1"


def test_unknown_difficulty_course_is_excluded():
    """Courses with unknown or invalid difficulty tiers are excluded from remedial selection."""
    learner_id = asyncio.run(_setup_test_db())

    # course-rem-unk-diff should not be selected
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_details"]["inserted_course_id"] != "course-rem-unk-diff"


def test_non_mvp_course_is_excluded_when_mvp_required():
    """Non-MVP courses (is_mvp = False) are excluded from remedial candidate selection."""
    learner_id = asyncio.run(_setup_test_db())

    # course-rem-non-mvp is 3 hours but is_mvp=False -> excluded
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_details"]["inserted_course_id"] == "course-rem-ml-beg1"


def test_existing_roadmap_course_cannot_be_reinserted():
    """A course already present in the learner's roadmap is not re-inserted as remediation."""
    learner_id = asyncio.run(_setup_test_db())

    # Already enrolled in course-p1-b (beginner, ml_fund).
    # If course-rem-ml-beg1 and course-rem-ml-beg2 are also pre-enrolled, no candidate remains.
    async def _prep():
        async with TestSessionLocal() as session:
            lp_r1 = LearningPath(learner_id=learner_id, course_id="course-rem-ml-beg1", phase_number=1, sequence_order=4, status="available")
            lp_r2 = LearningPath(learner_id=learner_id, course_id="course-rem-ml-beg2", phase_number=1, sequence_order=5, status="available")
            session.add_all([lp_r1, lp_r2])
            await session.commit()

    asyncio.run(_prep())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp.status_code == 200
    assert resp.json()["adaptation_applied"] == "none"
    assert "No lower-difficulty remedial course available" in resp.json()["adaptation_details"]["message"]


def test_remedial_course_inserted_at_correct_sequence_and_status():
    """Remedial course is inserted at sequence_order = failed_seq + 1 with status = 'available'."""
    learner_id = asyncio.run(_setup_test_db())

    # Before:
    # seq 1: course-p1-a (intermediate)
    # seq 2: course-p1-b (beginner)
    # seq 3: course-p2-a (advanced)
    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            stmt = select(LearningPath).where(LearningPath.learner_id == learner_id).order_by(LearningPath.sequence_order)
            res = await session.execute(stmt)
            lps = res.scalars().all()

            # Expect 4 courses:
            # 1: course-p1-a (done)
            # 2: course-rem-ml-beg1 (available)
            # 3: course-p1-b (available)
            # 4: course-p2-a (locked)
            assert len(lps) == 4
            assert lps[0].course_id == "course-p1-a"
            assert lps[0].sequence_order == 1
            assert lps[0].status == "done"

            assert lps[1].course_id == "course-rem-ml-beg1"
            assert lps[1].sequence_order == 2
            assert lps[1].status == "available"
            assert lps[1].phase_number == 1

            assert lps[2].course_id == "course-p1-b"
            assert lps[2].sequence_order == 3
            assert lps[2].status == "available"

            assert lps[3].course_id == "course-p2-a"
            assert lps[3].sequence_order == 4
            assert lps[3].status == "locked"

    asyncio.run(_verify())


def test_all_later_sequence_orders_shift_exactly_plus_one():
    """All courses with sequence_order >= insert_pos shift by +1 without gaps or duplicate sequences."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            stmt = select(LearningPath).where(LearningPath.learner_id == learner_id).order_by(LearningPath.sequence_order)
            res = await session.execute(stmt)
            lps = res.scalars().all()

            seqs = [lp.sequence_order for lp in lps]
            assert seqs == [1, 2, 3, 4]  # Strict contiguous indexing!

    asyncio.run(_verify())


def test_relative_ordering_of_existing_courses_preserved():
    """Existing courses retain their relative ordering after sequence shifting."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            stmt = select(LearningPath).where(LearningPath.learner_id == learner_id).order_by(LearningPath.sequence_order)
            res = await session.execute(stmt)
            lps = res.scalars().all()

            course_order = [lp.course_id for lp in lps]
            assert course_order == ["course-p1-a", "course-rem-ml-beg1", "course-p1-b", "course-p2-a"]

    asyncio.run(_verify())


def test_no_mastery_or_known_skills_mutation_from_low_score():
    """A low score does NOT mark skills known or alter parsed_goal known_skills."""
    learner_id = asyncio.run(_setup_test_db())

    resp = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp.status_code == 200

    async def _verify():
        async with TestSessionLocal() as session:
            ls = (await session.execute(
                select(LearnerSkill).where(LearnerSkill.learner_id == learner_id, LearnerSkill.skill_id == "ml_fund")
            )).scalar_one()
            assert ls.status == "gap"

            learner = (await session.execute(select(Learner).where(Learner.id == learner_id))).scalar_one()
            assert "ml_fund" not in learner.parsed_goal["known_skills"]
            assert "ml_fund" in learner.parsed_goal["gap_skills"]

    asyncio.run(_verify())


def test_adversarial_repeated_low_score_does_not_duplicate_remediation():
    """Adversarial test: Submitting identical low score twice on the same failed course does NOT insert duplicate remedial courses or shift sequences again."""
    learner_id = asyncio.run(_setup_test_db())

    # Add course-p1-c at sequence 3
    async def _prep():
        async with TestSessionLocal() as session:
            lp_c = LearningPath(learner_id=learner_id, course_id="course-p1-c", phase_number=1, sequence_order=3, status="available")
            # Update p2-a sequence to 4
            lp_p2 = (await session.execute(
                select(LearningPath).where(LearningPath.learner_id == learner_id, LearningPath.course_id == "course-p2-a")
            )).scalar_one()
            lp_p2.sequence_order = 4
            session.add(lp_c)
            await session.commit()

    asyncio.run(_prep())

    # 1. First low score submission
    resp1 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp1.status_code == 200
    assert resp1.json()["adaptation_applied"] == "remediation"

    # 2. Second low score submission on the same course
    resp2 = make_request(
        "post",
        "/api/progress",
        json_payload={"learner_id": str(learner_id), "course_id": "course-p1-a", "assessment_score": 40.0},
    )
    assert resp2.status_code == 200
    assert resp2.json()["adaptation_applied"] == "none"

    async def _verify():
        async with TestSessionLocal() as session:
            # Check ProgressEvents (both events saved)
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 2

            # Check LearningPath rows
            stmt = select(LearningPath).where(LearningPath.learner_id == learner_id).order_by(LearningPath.sequence_order)
            res = await session.execute(stmt)
            lps = res.scalars().all()

            # MUST be exactly 5 courses:
            # 1: course-p1-a (done)
            # 2: course-rem-ml-beg1 (available)
            # 3: course-p1-b (available)
            # 4: course-p1-c (available)
            # 5: course-p2-a (locked)
            assert len(lps) == 5
            course_order = [lp.course_id for lp in lps]
            assert course_order == ["course-p1-a", "course-rem-ml-beg1", "course-p1-b", "course-p1-c", "course-p2-a"]
            seqs = [lp.sequence_order for lp in lps]
            assert seqs == [1, 2, 3, 4, 5]

    asyncio.run(_verify())


def test_remediation_rollback_on_database_failure():
    """Verify that if a failure occurs during remediation commit, the remedial row and sequence shifts are completely rolled back."""
    learner_id = asyncio.run(_setup_test_db())

    with unittest.mock.patch.object(AsyncSession, "commit", side_effect=RuntimeError("Simulated DB crash during remediation")):
        resp = make_request(
            "post",
            "/api/progress",
            json_payload={
                "learner_id": str(learner_id),
                "course_id": "course-p1-a",
                "assessment_score": 40.0,
            },
        )
        assert resp.status_code == 500

    async def _verify():
        async with TestSessionLocal() as session:
            # 0 Progress Events
            events = (await session.execute(select(ProgressEvent).where(ProgressEvent.learner_id == learner_id))).scalars().all()
            assert len(events) == 0

            # LearningPath rows remain in initial state
            stmt = select(LearningPath).where(LearningPath.learner_id == learner_id).order_by(LearningPath.sequence_order)
            res = await session.execute(stmt)
            lps = res.scalars().all()

            assert len(lps) == 3
            assert [lp.course_id for lp in lps] == ["course-p1-a", "course-p1-b", "course-p2-a"]
            assert [lp.sequence_order for lp in lps] == [1, 2, 3]
            assert lps[0].status == "available"

    asyncio.run(_verify())