from contextlib import asynccontextmanager
from typing import Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.explain import router as explain_router
from backend.app.api.profile import router as profile_router
from backend.app.api.progress import router as progress_router
from backend.app.api.roadmap import router as roadmap_router
from backend.app.api.skill_gap import router as skill_gap_router
from backend.app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    yield
    # Shutdown tasks


app = FastAPI(
    title="CourseTide API",
    description="AI-powered personalized learning path recommender backend.",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(profile_router)
app.include_router(skill_gap_router)
app.include_router(roadmap_router)
app.include_router(explain_router)
app.include_router(progress_router)
app.include_router(dashboard_router)


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """Health check endpoint for container / service monitoring."""
    return {
        "status": "healthy",
        "service": "coursetide-api",
        "version": "0.1.0",
    }
