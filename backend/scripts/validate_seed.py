"""Seed data validation script for CourseTide.

Validates that all CSV and JSON files in /data are well-formed, mutually consistent,
and strictly match data/VALIDATION_REPORT.json.
"""

import csv
import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import DATA_DIR


def validate_seed_data() -> bool:
    print(f"[*] Validating seed data in: {DATA_DIR}")

    # 1. Load VALIDATION_REPORT.json as authoritative target
    validation_report_path = DATA_DIR / "VALIDATION_REPORT.json"
    if not validation_report_path.exists():
        print("[!] ERROR: VALIDATION_REPORT.json not found!")
        return False

    with open(validation_report_path, "r", encoding="utf-8") as f:
        expected_report = json.load(f)

    # 2. Validate skills.json
    skills_path = DATA_DIR / "skills.json"
    with open(skills_path, "r", encoding="utf-8") as f:
        skills_data = json.load(f)
    skill_ids = {s["id"] for s in skills_data}
    print(f"  - skills.json: {len(skills_data)} skills loaded.")

    # 3. Validate courses.csv
    courses_path = DATA_DIR / "courses.csv"
    courses = []
    with open(courses_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            courses.append(row)
    course_ids = {c["id"] for c in courses}
    mvp_courses = [c for c in courses if c["is_mvp"].strip().lower() == "true"]
    web_courses = [c for c in courses if c["domain"].strip().lower() == "web"]
    multi_skill_courses = [c for c in courses if "|" in c.get("skills", "")]
    print(f"  - courses.csv: {len(courses)} courses loaded ({len(mvp_courses)} MVP, {len(web_courses)} Web, {len(multi_skill_courses)} multi-skill).")

    # 4. Validate course_skills.csv
    course_skills_path = DATA_DIR / "course_skills.csv"
    course_skills = []
    invalid_skill_refs = []
    with open(course_skills_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            course_skills.append(row)
            if row["skill_id"] not in skill_ids:
                invalid_skill_refs.append((row["course_id"], row["skill_id"]))
            if row["course_id"] not in course_ids:
                print(f"  [!] Unknown course_id in course_skills: {row['course_id']}")

    print(f"  - course_skills.csv: {len(course_skills)} mappings loaded.")

    # 5. Validate assessments.json
    assessments_path = DATA_DIR / "assessments.json"
    with open(assessments_path, "r", encoding="utf-8") as f:
        assessments = json.load(f)
    for a in assessments:
        if a["skill_id"] not in skill_ids:
            invalid_skill_refs.append(("assessment:" + a["id"], a["skill_id"]))
    print(f"  - assessments.json: {len(assessments)} assessments loaded.")

    # 6. Validate prerequisites.json
    prereqs_path = DATA_DIR / "prerequisites.json"
    with open(prereqs_path, "r", encoding="utf-8") as f:
        prereqs = json.load(f)
    unknown_prereq_refs = []
    for skill, prereq_list in prereqs.items():
        if skill not in skill_ids:
            unknown_prereq_refs.append(skill)
        for p in prereq_list:
            if p not in skill_ids:
                unknown_prereq_refs.append(f"{skill} -> {p}")
    print(f"  - prerequisites.json: {len(prereqs)} skill nodes loaded.")

    # 7. Validate target_roles.json
    roles_path = DATA_DIR / "target_roles.json"
    with open(roles_path, "r", encoding="utf-8") as f:
        roles = json.load(f)
    for role_id, role_data in roles.items():
        for req in role_data.get("required_skills", []):
            if req not in skill_ids:
                invalid_skill_refs.append((f"role:{role_id}", req))
        for opt in role_data.get("recommended_optional_skills", []):
            if opt not in skill_ids:
                invalid_skill_refs.append((f"role:{role_id}", opt))
    print(f"  - target_roles.json: {len(roles)} roles loaded.")

    # Compare actual counts with authoritative VALIDATION_REPORT.json
    mismatches = []
    if len(courses) != expected_report.get("course_count"):
        mismatches.append(f"course_count: expected {expected_report.get('course_count')}, got {len(courses)}")
    if len(mvp_courses) != expected_report.get("mvp_count"):
        mismatches.append(f"mvp_count: expected {expected_report.get('mvp_count')}, got {len(mvp_courses)}")
    if len(web_courses) != expected_report.get("web_count"):
        mismatches.append(f"web_count: expected {expected_report.get('web_count')}, got {len(web_courses)}")
    if len(skills_data) != expected_report.get("skill_count"):
        mismatches.append(f"skill_count: expected {expected_report.get('skill_count')}, got {len(skills_data)}")
    if len(assessments) != expected_report.get("assessment_count"):
        mismatches.append(f"assessment_count: expected {expected_report.get('assessment_count')}, got {len(assessments)}")
    if "course_skills_count" in expected_report and len(course_skills) != expected_report.get("course_skills_count"):
        mismatches.append(f"course_skills_count: expected {expected_report.get('course_skills_count')}, got {len(course_skills)}")
    if "multi_skill_course_count" in expected_report and len(multi_skill_courses) != expected_report.get("multi_skill_course_count"):
        mismatches.append(f"multi_skill_course_count: expected {expected_report.get('multi_skill_course_count')}, got {len(multi_skill_courses)}")

    if invalid_skill_refs:
        mismatches.append(f"invalid_skill_references: {invalid_skill_refs}")
    if unknown_prereq_refs:
        mismatches.append(f"unknown_prerequisite_skill_references: {unknown_prereq_refs}")

    if mismatches:
        print("[!] Validation FAILED with mismatches:")
        for m in mismatches:
            print(f"    - {m}")
        return False

    print("[OK] ALL SEED DATA CHECKS PASSED PERFECTLY against VALIDATION_REPORT.json!")
    return True


if __name__ == "__main__":
    success = validate_seed_data()
    sys.exit(0 if success else 1)
