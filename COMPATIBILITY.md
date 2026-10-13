# Verification and remaining acceptance gates

Verification host: Windows, Python 3.12, Node provided by the desktop runtime, 13 October 2026.

## Verified locally

Automated tests include real FFmpeg composition/audio mixing and vertical rendering; see the final
delivery and CI run for the current test count.

- Owner login, protected project/media access, project persistence and the XEK preset.
- Structured screenplay validation, versioning, approval invalidation and timezone-aware schedules.
- Real FFmpeg H.264/AAC shot rendering, movie assembly, quality inspection and 1080×1920 output.
- Refusal to render narration longer than the allocated shot.
- ComfyUI submission/history/retrieval and error propagation in explicitly mocked unit tests.
- Ollama JSON-schema requests and duration validation in explicitly mocked unit tests.
- Private-first publishing gates and job failure persistence.
- Next.js type checks and production build. Owner login and sample draft creation inspected in-browser.
- Alembic initial migration and no model/schema drift against local SQLite.

## Not verified / external prerequisites

Hardware measured: Windows 11, i5-12450H, 15.7 GiB RAM, RTX 2050 with 4096 MiB VRAM,
driver 555.99. Only ~2.9 GiB RAM was free. Motion-comic is the conservative profile. Quantized
FLUX image inference remains unverified and requires freeing RAM before its test.
Indic Parler-TTS currently requires the owner's Hugging Face model-access authorization.

- No live Ollama, ComfyUI, Indic Parler-TTS or Whisper inference was performed.
- No model-conditioned identity consistency or Tamil narration naturalness was demonstrated.
- No genuine 60-second Weeping Prisoner MP4/Short has been produced.
- No private YouTube upload, actual OAuth exchange or scheduled/public publication was performed.
- No Docker/Compose, Redis/Celery or PostgreSQL execution was possible on the initial host.
- No GPU-memory compatibility claim; model variants and hardware must be assessed on the model host.
- No actual 30-minute film has been rendered/inspected. Long targets are accepted by schemas and
  composed shot-by-shot, but large language-model screenplay generation needs live scale testing.

## Product gaps requiring further engineering

- Wan2.2 5B and FLUX graphs are supplied but require live validation; other variants/LTX need a working API export.
- Automatic identity scoring, camera parallax/fog/compositing and model-specific video extension.
- Multi-character separated dialogue in one shot: currently one spoken track/voice per shot; split
  shots at speaker boundaries for proper voice assignment.
- Advanced visual timeline layers, transitions, editable titles/watermarks and intro/outro templates.
- Automatic music/SFX synthesis. Licensed audio uploads and timed mixing are implemented.
- Automatic character-aware focus detection; explicit editor-confirmed focal positions are implemented.
- Longer multi-shot Shorts and hook-strength guarantees; current Shorts are distinct individual shots.
- Automatic recurring episode generation, autonomous publication quality gates and cleanup policies.
- Thumbnail upload UI, YouTube quota dashboards and cross-process resumable-upload recovery.
- Worker leases, crash recovery and safe multi-worker GPU resource allocation.
- Multi-user accounts, server-side logout revocation and granular data-retention UI.

These limitations are documented instead of claiming the complete master brief has passed acceptance.
Model and YouTube configuration unlock live verification, but do not remove the product gaps above.
