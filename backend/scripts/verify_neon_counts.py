import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text
from backend.app.config import settings

def verify_neon_counts():
    engine = create_engine(settings.SYNC_DATABASE_URL)
    with engine.connect() as conn:
        queries = [
            ("SELECT COUNT(*) FROM skills;", 22),
            ("SELECT COUNT(*) FROM courses;", 48),
            ("SELECT COUNT(*) FROM courses WHERE is_mvp = true;", 32),
            ("SELECT COUNT(*) FROM course_skills;", 74),
            ("SELECT COUNT(*) FROM assessments;", 10),
            ("SELECT COUNT(*) FROM courses WHERE embedding IS NULL;", 0),
            ("SELECT COUNT(*) FROM courses WHERE embedding IS NOT NULL;", 48),
            ("SELECT COUNT(DISTINCT vector_dims(embedding)) FROM courses WHERE embedding IS NOT NULL;", 1),
            ("SELECT MIN(vector_dims(embedding)), MAX(vector_dims(embedding)) FROM courses WHERE embedding IS NOT NULL;", (384, 384)),
        ]

        print("=== RAW SQL VERIFICATION ON NEON ===")
        all_passed = True
        for query, expected in queries:
            result = conn.execute(text(query)).fetchone()
            if len(result) == 1:
                val = result[0]
            else:
                val = (result[0], result[1])
            
            passed = (val == expected)
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] Query: {query}")
            print(f"       Result: {val} (Expected: {expected})")
            if not passed:
                all_passed = False

        if all_passed:
            print("\n[OK] ALL 9 RAW SQL VERIFICATION QUERIES PASSED WITH 100% MATCH!")
        else:
            print("\n[!] SOME RAW SQL CHECKS FAILED!")

if __name__ == "__main__":
    verify_neon_counts()
