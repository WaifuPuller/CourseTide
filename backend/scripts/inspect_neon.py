import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text
from backend.app.config import settings

def inspect_neon():
    engine = create_engine(settings.SYNC_DATABASE_URL)
    with engine.connect() as conn:
        print("=== 1. EXTENSIONS ===")
        exts = conn.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")).fetchall()
        for e in exts:
            print(f"  - Extension: {e[0]}, Version: {e[1]}")

        print("\n=== 2. TABLES ===")
        tables = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")).fetchall()
        for t in tables:
            print(f"  - {t[0]}")

        print("\n=== 3. COLUMN TYPES FOR KEY FIELDS ===")
        cols = conn.execute(text("""
            SELECT table_name, column_name, data_type, udt_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND (
                (table_name = 'courses' AND column_name = 'embedding') OR
                (table_name = 'learners' AND column_name = 'parsed_goal') OR
                data_type = 'uuid'
              )
            ORDER BY table_name, column_name;
        """)).fetchall()
        for c in cols:
            print(f"  - {c[0]}.{c[1]}: data_type='{c[2]}', udt_name='{c[3]}'")

if __name__ == "__main__":
    inspect_neon()
