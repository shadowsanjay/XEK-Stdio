import hmac
import io
import secrets
import shutil
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import select

from .adapters import ComfyUI
from .config import settings
from .db import Asset, Base, Channel, Job, Project, ScriptVersion, Session, Upload, engine
from .jobs import ACTIVE, dispatch, tick
from .hardware import inspect_hardware, recommend
from .pipeline import save_script
from .media import executable, probe, run
from .presets import XEK_CHARACTER
from .publishing import authorization, callback, validate_publish
from .schemas import CreateProject, PublishRequest, Screenplay
from .security import owner, token
from .storage import project_dir, relative, safe_path

_stop = threading.Event()


def inline_scheduler():
    while not _stop.wait(15):
        tick()


@asynccontextmanager
async def lifespan(app):
    settings().validate_security()
    # Production uses Alembic; inline SQLite development can bootstrap its own schema.
    if settings().database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    if settings().worker_mode == "inline":
        _stop.clear()
        threading.Thread(target=inline_scheduler, daemon=True).start()
    yield
    _stop.set()


app = FastAPI(title="XEK STUDIO", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings().web_origin], allow_methods=["GET", "POST", "PUT"],
                   allow_headers=["Authorization", "Content-Type"])
login_attempts = {}


class Login(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=500)


@app.get("/health")
def health():
    return {"status": "ok", "service": "xek-api"}


@app.post("/auth/login")
def login(body: Login):
    # Single-owner local service: global throttling avoids IP/proxy assumptions.
    current = time.monotonic()
    attempts = [t for t in login_attempts.get("owner", []) if current - t < 60]
    if len(attempts) >= 10:
        raise HTTPException(429, "Too many sign-in attempts; wait one minute")
    login_attempts["owner"] = [*attempts, current]
    cfg = settings()
    if not hmac.compare_digest(body.username.encode(), cfg.admin_username.encode()) or not hmac.compare_digest(
        body.password.encode(), cfg.admin_password.encode()
    ):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": token(cfg.admin_username), "token_type": "bearer"}


def project_or_404(db, project_id):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def project_json(project):
    return {"id": project.id, "name": project.name, "spec": project.spec, "screenplay": project.screenplay,
            "version": project.version, "approved_version": project.approved_version,
            "status": project.status, "created_at": project.created_at}


def job_json(job):
    return {"id": job.id, "project_id": job.project_id, "kind": job.kind, "state": job.state,
            "stage": job.stage, "progress": job.progress, "error": job.error, "logs": job.logs,
            "attempts": job.attempts, "run_at": job.run_at}


@app.get("/projects", dependencies=[Depends(owner)])
def projects():
    with Session() as db:
        return [project_json(p) for p in db.scalars(select(Project).order_by(Project.created_at.desc()))]


@app.post("/projects", dependencies=[Depends(owner)])
def create_project(body: CreateProject):
    if body.universe == "xek" and not any(c.id == "xek" for c in body.characters):
        from .schemas import Character
        body.characters.append(Character.model_validate(XEK_CHARACTER))
    with Session.begin() as db:
        project = Project(name=body.name, spec=body.model_dump())
        db.add(project)
        db.flush()
        return project_json(project)


@app.get("/projects/{project_id}", dependencies=[Depends(owner)])
def get_project(project_id: str):
    with Session() as db:
        return project_json(project_or_404(db, project_id))


@app.put("/projects/{project_id}/spec", dependencies=[Depends(owner)])
def edit_spec(project_id: str, body: CreateProject):
    with Session.begin() as db:
        project = project_or_404(db, project_id)
        if db.scalar(select(Job.id).where(Job.project_id == project_id, Job.state.in_(ACTIVE))):
            raise HTTPException(409, "Finish or cancel active jobs before editing")
        project.spec, project.name = body.model_dump(), body.name
        project.approved_version = None
        if project.screenplay:
            project.version += 1
            db.add(ScriptVersion(project_id=project.id, version=project.version, screenplay=project.screenplay))
        return project_json(project)


@app.put("/projects/{project_id}/screenplay", dependencies=[Depends(owner)])
def edit_script(project_id: str, body: Screenplay):
    with Session() as db:
        project = project_or_404(db, project_id)
        if db.scalar(select(Job.id).where(Job.project_id == project_id, Job.state.in_(ACTIVE))):
            raise HTTPException(409, "Finish or cancel active jobs before editing")
        try:
            body.check_duration(project.spec["duration_minutes"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
    save_script(project_id, body)
    return get_project(project_id)


@app.get("/projects/{project_id}/versions", dependencies=[Depends(owner)])
def versions(project_id: str):
    with Session() as db:
        project_or_404(db, project_id)
        return [{"version": v.version, "screenplay": v.screenplay, "created_at": v.created_at}
                for v in db.scalars(select(ScriptVersion).where(ScriptVersion.project_id == project_id)
                                    .order_by(ScriptVersion.version.desc()))]


@app.post("/projects/{project_id}/approve", dependencies=[Depends(owner)])
def approve(project_id: str):
    with Session.begin() as db:
        project = project_or_404(db, project_id)
        if not project.screenplay:
            raise HTTPException(409, "No screenplay to approve")
        project.approved_version = project.version
        return {"approved_version": project.version}


@app.post("/projects/{project_id}/references", dependencies=[Depends(owner)])
async def reference(project_id: str, file: UploadFile = File(...)):
    with Session() as db:
        project_or_404(db, project_id)
    payload = await file.read(settings().max_upload_mb * 1024 * 1024 + 1)
    if len(payload) > settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "Reference exceeds upload size limit")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            if image.width * image.height > 24000000:
                raise ValueError("Image exceeds 24 megapixels")
            image.load()
            converted = image.convert("RGB")
    except Exception:
        raise HTTPException(422, "Upload a valid image under 24 megapixels") from None
    path = project_dir(project_id, 0) / f"reference-{secrets.token_hex(12)}.png"
    converted.save(path, format="PNG")
    with Session.begin() as db:
        asset = Asset(project_id=project_id, kind="reference", path=relative(path), metadata_json={})
        db.add(asset)
        db.flush()
        return {"id": asset.id, "path": asset.path}


@app.post("/projects/{project_id}/audio", dependencies=[Depends(owner)])
async def upload_audio(project_id: str, rights_confirmed: bool, file: UploadFile = File(...)):
    if not rights_confirmed:
        raise HTTPException(422, "Confirm you have rights to use this audio")
    with Session() as db:
        project_or_404(db, project_id)
    payload = await file.read(settings().max_upload_mb * 1024 * 1024 + 1)
    if len(payload) > settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "Audio exceeds upload size limit")
    folder = project_dir(project_id, 0)
    stem = "audio-" + secrets.token_hex(12)
    source, output = folder / (stem + ".upload"), folder / (stem + ".wav")
    source.write_bytes(payload)
    try:
        run([executable("ffmpeg"), "-y", "-v", "error", "-protocol_whitelist", "file,pipe",
             "-i", str(source), "-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(output)], timeout=120)
        meta = probe(output)
    except Exception:
        raise HTTPException(422, "Invalid audio or FFmpeg is unavailable") from None
    finally:
        source.unlink(missing_ok=True)
    with Session.begin() as db:
        asset = Asset(project_id=project_id, kind="audio", path=relative(output),
                      metadata_json={"rights_confirmed": True, "duration": float(meta["format"]["duration"])})
        db.add(asset)
        db.flush()
        return {"id": asset.id, "path": asset.path, "duration": asset.metadata_json["duration"]}


class QueueRequest(BaseModel):
    kind: str = Field(pattern="^(screenplay|production|shorts)$")
    run_at: datetime | None = None


@app.post("/projects/{project_id}/jobs", dependencies=[Depends(owner)])
def queue(project_id: str, body: QueueRequest):
    with Session.begin() as db:
        project = project_or_404(db, project_id)
        # Project row lock serializes queue requests on PostgreSQL.
        db.execute(select(Project).where(Project.id == project_id).with_for_update())
        active = db.scalar(select(Job.id).where(Job.project_id == project_id,
                                              Job.state.in_([*ACTIVE, "scheduled"])))
        if active:
            raise HTTPException(409, "Project already has an active job")
        if body.run_at and (body.run_at.tzinfo is None or body.run_at <= datetime.now(UTC)):
            raise HTTPException(422, "Schedule must be a future time with timezone")
        job = Job(project_id=project_id, kind=body.kind, state="scheduled" if body.run_at else "queued",
                  run_at=body.run_at, payload={"version": project.version if project.screenplay else None})
        db.add(job)
        db.flush()
        job_id = job.id
    if not body.run_at:
        try:
            dispatch(job_id)
        except Exception:
            with Session.begin() as db:
                job = db.get(Job, job_id)
                job.state, job.error = "failed", "Queue unavailable; check Redis and retry"
    with Session() as db:
        return job_json(db.get(Job, job_id))


@app.get("/jobs", dependencies=[Depends(owner)])
def jobs():
    with Session() as db:
        return [job_json(j) for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(100))]


@app.post("/jobs/{job_id}/{action}", dependencies=[Depends(owner)])
def job_action(job_id: str, action: str):
    with Session.begin() as db:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if action == "cancel" and job.state in {*ACTIVE, "scheduled"}:
            job.cancel_requested = True
            if job.state != "running":
                job.state = "cancelled"
        elif action == "pause" and job.state in {"running", "queued"}:
            if job.state == "running":
                job.payload = {**job.payload, "pause_requested": True}
            else:
                job.state = "paused"
        elif action in {"retry", "resume"} and job.state in {"failed", "cancelled", "paused"}:
            if job.kind == "publish":
                raise HTTPException(409, "Reconcile interrupted uploads on YouTube; automatic re-upload is blocked")
            job.cancel_requested, job.error, job.state = False, None, "retrying"
            job.payload = {**job.payload, "pause_requested": False}
        else:
            raise HTTPException(409, "Action is invalid for this job state")
    if action in {"retry", "resume"}:
        dispatch(job_id)
    with Session() as db:
        return job_json(db.get(Job, job_id))


@app.get("/projects/{project_id}/assets", dependencies=[Depends(owner)])
def assets(project_id: str):
    with Session() as db:
        project_or_404(db, project_id)
        return [{"id": a.id, "kind": a.kind, "metadata": a.metadata_json,
                 "url": f"/assets/{a.id}"} for a in db.scalars(select(Asset).where(Asset.project_id == project_id))]


@app.get("/assets/{asset_id}", dependencies=[Depends(owner)])
def download(asset_id: str):
    with Session() as db:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(404, "Asset not found")
        path = safe_path(asset.path)
        if not path.is_file():
            raise HTTPException(404, "Asset file missing")
        return FileResponse(path, filename=path.name)


@app.get("/models", dependencies=[Depends(owner)])
def models():
    result = {"ollama": {"reachable": False}, "comfyui": {"reachable": False}, "speech": {"reachable": False}}
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(settings().ollama_url + "/api/tags")
            r.raise_for_status()
            result["ollama"] = {"reachable": True, "models": r.json().get("models", [])}
    except Exception:
        pass
    try:
        result["comfyui"] = ComfyUI().capabilities()
    except Exception:
        pass
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(settings().speech_url + "/health")
            r.raise_for_status()
            result["speech"] = {"reachable": True, **r.json()}
    except Exception:
        pass
    return result


@app.get("/system", dependencies=[Depends(owner)])
def system():
    disk = shutil.disk_usage(settings().data_dir)
    hardware = inspect_hardware()
    return {"disk": {"total": disk.total, "free": disk.free}, "hardware": hardware,
            "recommendation": recommend(hardware), "gpu": hardware["gpus"], "worker_mode": settings().worker_mode,
            "publishing_enabled": settings().youtube_publishing_enabled,
            "youtube_audit_approved": settings().youtube_audit_approved}


@app.get("/hardware", dependencies=[Depends(owner)])
def hardware_status():
    hardware = inspect_hardware()
    return {"hardware": hardware, "recommendation": recommend(hardware),
            "scope": "API host; run scripts/doctor.py on a separate model host for its own hardware"}


@app.post("/youtube/connect", dependencies=[Depends(owner)])
def connect():
    try:
        return {"url": authorization()}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@app.get("/youtube/callback")
def oauth_callback(code: str, state: str):
    try:
        callback(code, state)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return HTMLResponse("<h1>YouTube connected</h1><p>You can return to XEK STUDIO.</p>")


@app.get("/youtube", dependencies=[Depends(owner)])
def youtube_status():
    with Session() as db:
        channel = db.get(Channel, "owner")
        return {"connected": bool(channel and channel.encrypted_tokens), "name": channel.name if channel else None,
                "private_only": not settings().youtube_audit_approved,
                "uploads": [{"id": u.id, "asset_id": u.asset_id, "state": u.state,
                             "youtube_id": u.youtube_id, "error": u.error} for u in db.scalars(select(Upload))]}


@app.post("/projects/{project_id}/publish", dependencies=[Depends(owner)])
def publish(project_id: str, body: PublishRequest):
    try:
        validate_publish(body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    with Session.begin() as db:
        project_or_404(db, project_id)
        job = Job(project_id=project_id, kind="publish", payload=body.model_dump())
        db.add(job)
        db.flush()
        job_id = job.id
    dispatch(job_id)
    return {"job_id": job_id}
