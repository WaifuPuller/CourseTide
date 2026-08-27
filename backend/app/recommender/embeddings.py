"""Semantic Course Recommender for CourseTide.

Embeds learner gap skills using sentence-transformers/all-MiniLM-L6-v2 and ranks
candidate courses via the approved hybrid gap-recall scoring formula:
Score(C) = 0.50 * S_sim + 0.35 * S_gap + 0.15 * S_pri
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.app.config import DATA_DIR, settings
from backend.app.models import Course, CourseSkill, Skill

def _load_skill_embeddings() -> Dict[str, np.ndarray]:
    emb_file = DATA_DIR / "skill_embeddings.json"
    if emb_file.exists():
        with open(emb_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k: np.array(v, dtype=np.float32) for k, v in data.items()}
    return {}


SKILL_EMBEDDINGS = _load_skill_embeddings()


class PrecomputedSkillEmbedder:
    """Fast, zero-PyTorch embedding encoder using precomputed skill embeddings."""

    def encode(self, texts: Sequence[str], normalize_embeddings: bool = True, **kwargs):
        results = []
        for text in texts:
            vecs = [
                v for k, v in SKILL_EMBEDDINGS.items()
                if k in text or SKILLS_MAP.get(k, "").lower() in text.lower()
            ]
            if vecs:
                mean_vec = np.mean(vecs, axis=0)
                if normalize_embeddings:
                    norm = np.linalg.norm(mean_vec)
                    if norm > 0:
                        mean_vec = mean_vec / norm
                results.append(mean_vec)
            else:
                fallback = np.zeros(384, dtype=np.float32)
                fallback[0] = 1.0
                results.append(fallback)
        return np.array(results)


_GLOBAL_EMBED_MODEL = None


def get_embed_model():
    """Retrieve or initialize embedding model singleton (falls back to precomputed skill embedder)."""
    global _GLOBAL_EMBED_MODEL
    if _GLOBAL_EMBED_MODEL is None and not settings.TESTING:
        try:
            from sentence_transformers import SentenceTransformer
            _GLOBAL_EMBED_MODEL = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
        except (ImportError, Exception):
            _GLOBAL_EMBED_MODEL = PrecomputedSkillEmbedder()
    return _GLOBAL_EMBED_MODEL


def set_embed_model(model):
    """Override the global embedding model singleton (used for testing / lifespan)."""
    global _GLOBAL_EMBED_MODEL
    _GLOBAL_EMBED_MODEL = model


class RecommendedCourse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    difficulty: str
    duration_hours: int
    resource_type: str
    domain: str
    source: Optional[str] = None
    url: Optional[str] = None
    learning_outcomes: Optional[str] = None
    primary_skill: Optional[str] = None
    all_skills: List[str] = Field(default_factory=list)
    covered_gap_skills: List[str] = Field(default_factory=list)
    match_score: float  # Composite score percentage (0-100)
    semantic_similarity: float
    gap_coverage_ratio: float


def _load_skills_map() -> Dict[str, str]:
    skills_file = DATA_DIR / "skills.json"
    with open(skills_file, "r", encoding="utf-8") as f:
        skills = json.load(f)
    return {s["id"]: s["name"] for s in skills}


SKILLS_MAP = _load_skills_map()


def build_gap_query_text(gap_skills: List[str]) -> str:
    """Construct semantic search query text from learner gap skills."""
    if not gap_skills:
        return "Fundamental machine learning and data science curriculum"
    skill_names = [SKILLS_MAP.get(s, s.replace("_", " ").title()) for s in gap_skills]
    return f"Curated courses and practical projects covering: {', '.join(skill_names)}"


def compute_composite_score(
    semantic_sim: float,
    course_skills: List[str],
    primary_skill: Optional[str],
    gap_skills: List[str],
) -> Tuple[float, float, List[str]]:
    """Compute the approved composite score for a course against learner gap skills.

    Score(C) = 0.50 * S_sim + 0.35 * S_gap + 0.15 * S_pri
    where S_gap = |Skills(C) ∩ G| / max(1, |G|) (Learner Gap Recall)

    Returns:
        (composite_score_0_to_100, gap_recall_ratio, covered_gaps_list)
    """
    gap_set = set(gap_skills)
    course_skill_set = set(course_skills)

    # 1. Covered gaps
    covered_gaps = [s for s in course_skills if s in gap_set]
    
    # 2. Gap recall coverage: fraction of total gaps covered by this course
    total_gaps = max(1, len(gap_set))
    s_gap = len(covered_gaps) / total_gaps

    # 3. Primary skill alignment
    s_pri = 1.0 if (primary_skill and primary_skill in gap_set) else 0.0

    # 4. Semantic similarity clamped to [0, 1]
    s_sim = max(0.0, min(1.0, float(semantic_sim)))

    # Composite formula
    score = (0.50 * s_sim) + (0.35 * s_gap) + (0.15 * s_pri)
    score_pct = round(score * 100.0, 1)

    return score_pct, round(s_gap, 3), covered_gaps


async def recommend_courses_async(
    db: AsyncSession,
    gap_skills: List[str],
    top_k: int = 8,
    embed_model = None,
) -> List[RecommendedCourse]:
    """Retrieve and rank candidate courses from database using semantic vector matching + gap recall.

    Args:
        db: SQLAlchemy AsyncSession connected to PostgreSQL.
        gap_skills: List of canonical skill IDs in the learner's gap set.
        top_k: Maximum number of ranked recommendations to return.
        embed_model: SentenceTransformer instance or mock.

    Returns:
        Ranked list of RecommendedCourse objects.
    """
    model = embed_model or get_embed_model()

    # 1. Generate query embedding
    query_text = build_gap_query_text(gap_skills)
    if model is not None:
        q_emb = model.encode([query_text], normalize_embeddings=True)[0]
        if hasattr(q_emb, "tolist"):
            q_vec = np.array(q_emb.tolist(), dtype=np.float32)
        else:
            q_vec = np.array(q_emb, dtype=np.float32)
    else:
        # Fallback pseudo-vector for tests without model
        q_vec = np.zeros(384, dtype=np.float32)
        q_vec[0] = 1.0

    # 2. Query MVP courses with course_skills from DB in a single join
    stmt = (
        select(Course)
        .where(Course.is_mvp == True)
        .options(joinedload(Course.skill_associations))
    )
    result = await db.execute(stmt)
    courses: Sequence[Course] = result.scalars().unique().all()

    ranked: List[RecommendedCourse] = []

    for c in courses:
        # Extract skills and primary skill
        c_skills = [sa.skill_id for sa in c.skill_associations]
        c_primary = next((sa.skill_id for sa in c.skill_associations if sa.is_primary), None)
        if not c_primary and c_skills:
            c_primary = c_skills[0]

        # Calculate semantic similarity
        sim = 0.5  # default baseline
        if c.embedding is not None:
            c_emb = c.embedding
            if isinstance(c_emb, (list, tuple, np.ndarray)):
                c_arr = np.array(c_emb, dtype=np.float32)
                # Compute cosine similarity (dot product since normalized)
                dot = np.dot(c_arr, q_vec)
                norm_prod = (np.linalg.norm(c_arr) * np.linalg.norm(q_vec))
                if norm_prod > 0:
                    sim = float(dot / norm_prod)
                else:
                    sim = float(dot)

        # Compute composite score
        score_pct, s_gap, covered_gaps = compute_composite_score(
            semantic_sim=sim,
            course_skills=c_skills,
            primary_skill=c_primary,
            gap_skills=gap_skills,
        )

        ranked.append(
            RecommendedCourse(
                id=c.id,
                title=c.title,
                description=c.description,
                difficulty=c.difficulty,
                duration_hours=c.duration_hours,
                resource_type=c.resource_type,
                domain=c.domain,
                source=c.source,
                url=c.url,
                learning_outcomes=c.learning_outcomes,
                primary_skill=c_primary,
                all_skills=c_skills,
                covered_gap_skills=covered_gaps,
                match_score=score_pct,
                semantic_similarity=round(sim, 3),
                gap_coverage_ratio=s_gap,
            )
        )

    # Sort by composite match_score descending, then by number of covered gaps
    ranked.sort(key=lambda x: (x.match_score, len(x.covered_gap_skills)), reverse=True)

    return ranked[:top_k]
