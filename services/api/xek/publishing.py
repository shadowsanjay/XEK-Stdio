import json
from datetime import UTC, datetime

from cryptography.fernet import Fernet
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from sqlalchemy import select

from .config import settings
from .db import Asset, Channel, Job, Session, Upload
from .jobs import update_job
from .schemas import PublishRequest
from .storage import safe_path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


def cipher():
    key = settings().token_encryption_key
    if not key:
        raise ValueError("Set TOKEN_ENCRYPTION_KEY before connecting YouTube")
    return Fernet(key.encode())


def flow():
    cfg = settings()
    if not cfg.youtube_client_id or not cfg.youtube_client_secret:
        raise ValueError("Configure a Google OAuth web client first")
    return Flow.from_client_config({"web": {
        "client_id": cfg.youtube_client_id, "client_secret": cfg.youtube_client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}, scopes=SCOPES, redirect_uri=cfg.public_api_url + "/youtube/callback")


def authorization():
    cipher()
    url, state = flow().authorization_url(access_type="offline", prompt="consent")
    with Session.begin() as db:
        channel = db.get(Channel, "owner")
        if not channel:
            channel = Channel(id="owner", encrypted_tokens="")
            db.add(channel)
        channel.oauth_state = json.dumps({"value": state, "expires": datetime.now(UTC).timestamp() + 600})
    return url


def callback(code: str, state: str):
    import hmac
    with Session.begin() as db:
        channel = db.get(Channel, "owner")
        saved = json.loads(channel.oauth_state) if channel and channel.oauth_state else {}
        if not hmac.compare_digest(saved.get("value", ""), state) or saved.get("expires", 0) < datetime.now(UTC).timestamp():
            raise ValueError("OAuth state expired or invalid; reconnect")
        channel.oauth_state = None  # One-time state consumed before token exchange.
    oauth = flow()
    oauth.fetch_token(code=code)
    channels = build("youtube", "v3", credentials=oauth.credentials, cache_discovery=False).channels().list(
        part="snippet", mine=True
    ).execute()
    items = channels.get("items", [])
    if not items:
        raise ValueError("This Google account has no YouTube channel")
    with Session.begin() as db:
        db.get(Channel, "owner").encrypted_tokens = cipher().encrypt(oauth.credentials.to_json().encode()).decode()
        db.get(Channel, "owner").name = items[0]["snippet"]["title"]


def validate_publish(request: PublishRequest):
    cfg = settings()
    if not cfg.youtube_publishing_enabled:
        raise ValueError("Channel owner must enable YOUTUBE_PUBLISHING_ENABLED")
    if not cfg.youtube_audit_approved and (request.visibility != "private" or request.publish_at):
        raise ValueError("Unaudited API projects: only private uploads are enabled; complete Google's audit")
    if request.publish_at:
        scheduled = datetime.fromisoformat(request.publish_at.replace("Z", "+00:00"))
        if scheduled.tzinfo is None or scheduled <= datetime.now(UTC):
            raise ValueError("Publication time must be a future ISO timestamp with a timezone")
        if request.visibility != "private":
            raise ValueError("Scheduled YouTube uploads must start as private")


def upload_job(job_id):
    with Session() as db:
        job = db.get(Job, job_id)
        request = PublishRequest.model_validate(job.payload)
        validate_publish(request)
        asset = db.get(Asset, request.asset_id)
        if not asset or asset.kind not in {"movie", "short"} or asset.project_id != job.project_id:
            raise ValueError("Invalid publishing asset")
        movies = db.scalars(select(Asset).where(Asset.project_id == asset.project_id, Asset.kind == "movie")).all()
        parent = next((m for m in movies if m.metadata_json.get("version") == asset.metadata_json.get("version")), None)
        if not parent or not parent.metadata_json.get("quality", {}).get("passed"):
            raise ValueError("Publishing requires a passing quality report")
        channel = db.get(Channel, "owner")
        if not channel or not channel.encrypted_tokens:
            raise ValueError("Connect YouTube before uploading")
        credentials = Credentials.from_authorized_user_info(json.loads(cipher().decrypt(channel.encrypted_tokens.encode())))
    if credentials.expired:
        credentials.refresh(Request())
        with Session.begin() as db:
            db.get(Channel, "owner").encrypted_tokens = cipher().encrypt(credentials.to_json().encode()).decode()
    with Session.begin() as db:
        existing = db.scalar(select(Upload).where(Upload.asset_id == asset.id))
        if existing:
            if existing.youtube_id:
                return
            raise ValueError("Upload was already attempted. Reconcile it on YouTube before attempting a new upload")
        upload = Upload(asset_id=asset.id, project_id=asset.project_id, metadata_json=request.model_dump())
        db.add(upload)
        db.flush()
        upload_id = upload.id
    update_job(job_id, "Uploading authorized video to YouTube", 10)
    status = {"privacyStatus": request.visibility, "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": request.contains_synthetic_media}
    if request.publish_at:
        status["publishAt"] = request.publish_at
    service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    try:
        insert = service.videos().insert(part="snippet,status", body={
            "snippet": {"title": request.title, "description": request.description, "tags": request.tags,
                        "categoryId": "1"}, "status": status,
        }, media_body=MediaFileUpload(str(safe_path(asset.path)), mimetype="video/mp4", resumable=True))
        response = None
        while response is None:
            progress, response = insert.next_chunk(num_retries=3)
            if progress:
                update_job(job_id, "YouTube upload in progress", 10 + int(progress.progress() * 80))
        with Session.begin() as db:
            upload = db.get(Upload, upload_id)
            upload.youtube_id = response["id"]
            upload.state = "scheduled" if request.publish_at else "uploaded-" + response.get("status", status)["privacyStatus"]
    except Exception:
        with Session.begin() as db:
            upload = db.get(Upload, upload_id)
            upload.state = "needs-reconciliation"
            upload.error = "Upload interrupted or failed. Check YouTube for a completed upload before retrying."
        raise
