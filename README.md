# XEK STUDIO

**One Prompt. An Entire Movie.**

A self-hosted film-production application with a Next.js control room, FastAPI owner API,
PostgreSQL/SQLite persistence, Celery/Redis jobs, local model adapters, real FFmpeg motion-comic
and clip composition, vertical Shorts and authorized YouTube uploads.

**Release status: functional implementation milestone, not a completed acceptance demonstration.**
AI model weights, a compatible model host and Google credentials are not included. Generation
fails visibly if they are missing. There are no fake media providers or fabricated generation results.
See [COMPATIBILITY.md](COMPATIBILITY.md) for tested behavior and remaining product gaps.
See [DELIVERY.md](DELIVERY.md) for local verification and the remaining authorization/setup steps.

For the requested Qwen3 8B / FLUX.1-schnell / Wan2.2 / Indic Parler-TTS configuration, start with
[hardware-aware installation](models/INSTALL.md). Run `scripts/doctor.py` before any large download.
The inspected RTX 2050 (4 GiB VRAM) defaults to motion-comic. Live Tamil acceptance is blocked until
model services are installed, sufficient RAM is free, and Indic Parler-TTS access is approved.

## Quick start — Docker

Prerequisites: Docker with Compose, model services on the host, enough disk space for generated
assets, and the hardware required by your selected models. Docker does not install GPU models.

1. Copy `.env.example` to `.env` in a fresh checkout. Set a random `AUTH_SECRET` (32+ characters),
   a strong `ADMIN_PASSWORD` (12+ characters), and `TOKEN_ENCRYPTION_KEY` if using YouTube.
   Generate keys using the commands in `.env.example`. Never commit `.env`.
2. Install Ollama, pull your screenplay model and configure OLLAMA_MODEL. Install ComfyUI and
   install the selected FLUX GGUF files and nodes for `workflows/flux-schnell-gguf.json`. See [models](models/INSTALL.md)
   and [workflows](workflows/README.md) for speech/video prerequisites.
3. Run `docker compose up --build -d`.
4. Open http://localhost:3000 and sign in as `ADMIN_USERNAME` with your `ADMIN_PASSWORD`.
5. Check Model Manager before generating. Create a production using the XEK sample, generate
   a screenplay, inspect/edit it, set vertical focal positions, approve it if manual, then open
   Scene Generator and start production.

On Linux, permit containers to reach host model services through `host.docker.internal`. Bind
model services only to a trusted interface and firewall them. The studio ports are bound to loopback
by default; adding internet access requires TLS/reverse proxy, proper operational security and review.
Database/Redis passwords in Compose are local-development defaults; change them together with
DATABASE_URL before deploying in a shared environment.

Speech runs separately because model-dependent torch environments are large and hardware-specific:
`pip install -e '.[speech]'`, then `uvicorn services.speech.server:app --host 127.0.0.1 --port 8001`.
For Docker-to-host access, use an appropriate trusted host interface. The supplied service loads
Indic Parler-TTS on the first synthesis request. CPU execution can be very slow.

## Local development — CPU-compatible infrastructure and rendering

Python 3.11+ and Node 22+ are required. Windows uses inline mode; Celery production runs in Linux/Docker.

```text
python -m venv .venv
# Activate .venv (Windows: .venv\Scripts\Activate.ps1; Linux: source .venv/bin/activate)
pip install -e '.[test,transcription]'
python scripts/configure_local.py
uvicorn xek.main:app --host 127.0.0.1 --port 8000
```

`configure_local.py` creates a private `.env` with random credentials, SQLite and inline jobs.
It will not overwrite an existing file. Read the generated password in your local `.env`.
Install FFmpeg and ffprobe on PATH. For Windows renderer tests only, optional `static-ffmpeg`
can download binaries into the virtual environment; see tests/test_media.py.

In another terminal:
```text
cd apps/web
corepack enable
corepack prepare pnpm@11.25.0 --activate
pnpm install --frozen-lockfile
pnpm run dev
```

The frontend uses NEXT_PUBLIC_API_URL (default http://localhost:8000). It is baked into production
builds. WEB_ORIGIN must match the browser origin. Local development supports project management,
screenplay generation with a CPU-capable Ollama model and real rendering; AI images still require
a working image model. There is no software-only zero-resource-cost claim.

## Production workflow

- **Manual:** generate/edit/approve a script, then start production. Changed scripts revoke approval.
- **Assisted:** production can generate a missing script, then render it. Publishing requires approval.
- **Automatic:** schedule production against a selected project. Critical errors stop the job.
  This release does not automatically approve publishing or create recurring episodes.
- Scripts are validated as ordered, contiguous shots totaling the requested target. Model output
  that violates the schema fails with a real error. Edit it or regenerate with an appropriate model.
- Narration is measured before rendering. If it exceeds a shot, shorten the text or split/re-time
  that shot in Script Editor. The renderer never loops missing footage to reach the requested length.
- Every shot has source, speech, subtitle and render checkpoints. Retrying retains completed stages;
  unchanged shots can be reused from the immediately preceding screenplay version.
- Storyboard `crop_x` is a confirmed focal position from 0 (left) to 1 (right). Shorts skip shots
  without a focal position, rank by hook score, avoid overlap and re-render captions vertically.
  Counts are configurable from 1–12; actual count depends on distinct eligible shots.
- Upload licensed music/SFX in Movie Timeline, add license attribution, edit timed audio tracks and
  save. The renderer trims/fades/mixes them and can duck them under speech. No copyrighted soundtrack
  or unrelated stock footage is silently supplied. AI music and SFX synthesis are not implemented.
- Assets retain screenplay version, parent movie and timing metadata. Quality reports inspect
  duration, streams, resolution, subtitles and full decode; dark intervals, long silence and identity
  consistency require human review. Inspect the finished movie before authorizing an upload.
- 30 minutes is a timeline target, not one continuous model clip. A real 30-minute acceptance film
  has not been produced. Large structured LLM outputs may exceed a model's practical context limits.

## YouTube setup

Create a Google OAuth **web application** client and enable YouTube Data API v3. Register
`http://localhost:8000/youtube/callback` (or your PUBLIC_API_URL callback) as a redirect URI.
Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and a Fernet TOKEN_ENCRYPTION_KEY. OAuth tokens
stay encrypted in the database; the frontend never receives them. The upload scope is required to
upload and the readonly scope identifies the connected channel name.

Connect the channel in YouTube Publisher. The owner must explicitly set
YOUTUBE_PUBLISHING_ENABLED=true and approve each upload in the interface. Defaults are private.
Unaudited projects permit only private uploads in the studio. Set YOUTUBE_AUDIT_APPROVED=true
only after the applicable audit is approved. Scheduled publications start private with a future
timezone-aware publishAt. The app records returned IDs/status, not an invented public success.

Official restrictions: https://developers.google.com/youtube/v3/docs/videos/insert
and schedule semantics: https://developers.google.com/youtube/v3/docs/videos .

Uploads have a unique asset reservation. Network retries are limited to the current resumable
session. An interrupted upload is marked `needs-reconciliation` and blind re-upload is blocked:
inspect YouTube first to avoid creating duplicates. Cross-process upload session resume and UI
reconciliation are remaining work. Do not delete upload reservations without checking the channel.

## Tests and API

```text
ruff check services tests
pytest -q
alembic upgrade head
alembic check
cd apps/web
pnpm run check
pnpm run build
```

API docs: http://localhost:8000/docs . Auth: POST /auth/login, then Bearer token.
Production endpoints, schema and asset access require owner authentication. Export schemas with
`python scripts/export_schema.py`. Backend dependencies are bounded in pyproject.toml; frontend
dependencies are locked in pnpm-lock.yaml. CI runs backend tests with real FFmpeg and a frontend build.

Unit network tests explicitly use mocks; they are not live generation/upload acceptance evidence.
Renderer tests use labeled synthetic fixture art/audio. They are not the requested sample movie.

## Operations and troubleshooting

- Queue unavailable: inspect `docker compose logs redis worker api`. Use one worker slot for heavy
  GPU jobs, and one beat scheduler. Inline mode is a single-process development convenience.
- Script duration mismatch: inspect model output/error, edit contiguous shot timing, or change model.
- Missing image model: replace the checkpoint filename and check ComfyUI nodes in Model Manager.
- Missing video workflow: export your actual Wan/LTX API graph; never declare unsupported capabilities.
- Tamil boxes/missing glyphs: install Noto Sans Tamil on the renderer host and check libass support.
- Tamil speech failure: verify speech dependencies, weights and a Tamil-supported voice description.
- Render speech too long: shorten the spoken text or extend/rebalance the storyboard within target.
- No Shorts: set crop_x on enough distinctive shots and rerender/regenerate Shorts.
- Authentication unavailable: configure strong secrets; the server refuses insecure default startup.
- Scheduler times: the UI converts browser-local time to UTC. For this project's author, use Asia/Kolkata.
- Disk usage: Settings reports actual free/total storage. Final outputs, references and source files
  are retained. Automatic destructive cleanup is intentionally not enabled in this milestone.
- Worker crash: jobs remain persistent, but automatic crash recovery/leases are not yet complete.
  Verify no worker is still running the job before a controlled database recovery and retry.
- Docker volume reset deletes project state/media: back up PostgreSQL and the media volume first.

This is a single-owner studio, not a multi-tenant hosted service. Keep model hosts trusted, back up
encrypted tokens with their encryption key separately, and review licensing for every model/asset.
