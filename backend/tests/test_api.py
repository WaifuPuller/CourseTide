import uuid
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health_check():
    """Verify GET /health returns 200 and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "coursetide-api"


def test_profile_intake_skeleton():
    """Verify POST /api/profile accepts payload."""
    response = client.post("/api/profile", json={"goal": "I want to be an ML Engineer", "weekly_hours": 10})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "skeleton_ready"
    assert data["weekly_hours"] == 10


def test_skill_gap_skeleton():
    """Verify GET /api/skill-gap/{learner_id} endpoint."""
    test_id = str(uuid.uuid4())
    response = client.get(f"/api/skill-gap/{test_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["learner_id"] == test_id


def test_roadmap_skeleton():
    """Verify GET /api/roadmap/{learner_id} endpoint."""
    test_id = str(uuid.uuid4())
    response = client.get(f"/api/roadmap/{test_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["learner_id"] == test_id


def test_explain_skeleton():
    """Verify GET /api/explain/{learner_id}/{course_id} endpoint."""
    test_id = str(uuid.uuid4())
    response = client.get(f"/api/explain/{test_id}/cs50-python")
    assert response.status_code == 200
    data = response.json()
    assert data["course_id"] == "cs50-python"


def test_progress_skeleton():
    """Verify POST /api/progress endpoint."""
    test_id = str(uuid.uuid4())
    response = client.post(
        "/api/progress",
        json={"learner_id": test_id, "course_id": "cs50-python", "assessment_score": 88.0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["assessment_score"] == 88.0


def test_dashboard_skeleton():
    """Verify GET /api/dashboard/{learner_id} endpoint."""
    test_id = str(uuid.uuid4())
    response = client.get(f"/api/dashboard/{test_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["learner_id"] == test_id
