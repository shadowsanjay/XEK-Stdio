import os
import tempfile
from pathlib import Path

import pytest

TEST_ROOT = Path(tempfile.mkdtemp(prefix="xek-tests-"))
os.environ.update({"AUTH_SECRET": "test-secret-" * 5, "ADMIN_PASSWORD": "test-password-12345",
                   "DATA_DIR": str(TEST_ROOT), "DATABASE_URL": "sqlite:///" + (TEST_ROOT / "test.db").as_posix(),
                   "WORKER_MODE": "inline"})

from fastapi.testclient import TestClient  # noqa: E402
from xek.db import Base, engine  # noqa: E402
from xek.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth(client):
    response = client.post("/auth/login", json={"username": "admin", "password": "test-password-12345"})
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.fixture
def spec():
    return {"name": "Test film", "prompt": "A hooded keeper opens an iron chamber.", "duration_minutes": 1}


@pytest.fixture
def script():
    return {"title": "The Chamber", "synopsis": "A fictional legend", "acts": ["Opening", "Origin", "Return"],
            "shots": [{"id": f"s{i}", "scene_id": "castle", "location_id": "castle", "start_time": i*10,
                       "duration": 10, "visual_prompt": f"Unique chamber scene {i}",
                       "narration": f"Spoken words {i}", "crop_x": i/5, "hook_score": i/5} for i in range(6)]}
