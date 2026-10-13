import io
from datetime import UTC, datetime, timedelta

from PIL import Image
from xek.db import Job, Session


def test_owner_authentication(client, auth):
    assert client.get("/projects").status_code == 401
    assert client.get("/projects", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get("/projects", headers=auth).status_code == 200
    assert client.post("/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401


def test_script_versions_and_approval(client, auth, spec, script):
    project = client.post("/projects", json=spec, headers=auth).json()
    assert project["spec"]["characters"][0]["id"] == "xek"
    url = f"/projects/{project['id']}"
    assert client.put(url + "/screenplay", json=script, headers=auth).status_code == 200
    assert client.post(url + "/approve", headers=auth).json()["approved_version"] == 1
    script["title"] = "Revised"
    result = client.put(url + "/screenplay", json=script, headers=auth).json()
    assert result["version"] == 2 and result["approved_version"] is None
    assert len(client.get(url + "/versions", headers=auth).json()) == 2
    script["shots"][-1]["duration"] = 8
    assert client.put(url + "/screenplay", json=script, headers=auth).status_code == 422


def test_reference_upload_sanitizes_name_and_rejects_invalid_file(client, auth, spec):
    p = client.post("/projects", json=spec, headers=auth).json()
    url = f"/projects/{p['id']}/references"
    assert client.post(url, files={"file": ("bad.png", b"not an image")}, headers=auth).status_code == 422
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buffer, "PNG")
    response = client.post(url, files={"file": ("../../escape.png", buffer.getvalue())}, headers=auth)
    assert response.status_code == 200
    assert "escape" not in response.json()["path"] and ".." not in response.json()["path"]
    assert client.get("/assets/" + response.json()["id"]).status_code == 401


def test_schedule_persists_and_blocks_duplicate_job(client, auth, spec):
    p = client.post("/projects", json=spec, headers=auth).json()
    url = f"/projects/{p['id']}/jobs"
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    response = client.post(url, json={"kind": "production", "run_at": future}, headers=auth)
    assert response.status_code == 200 and response.json()["state"] == "scheduled"
    assert client.post(url, json={"kind": "screenplay"}, headers=auth).status_code == 409
    job_id = response.json()["id"]
    assert client.post(f"/jobs/{job_id}/cancel", headers=auth).json()["state"] == "cancelled"
    with Session() as db:
        assert db.get(Job, job_id).cancel_requested


def test_publishing_disabled_by_default(client, auth, spec):
    p = client.post("/projects", json=spec, headers=auth).json()
    response = client.post(f"/projects/{p['id']}/publish", headers=auth,
                           json={"asset_id": "missing", "title": "Movie", "owner_approved": True})
    assert response.status_code == 409
    assert "enable" in response.json()["detail"]
