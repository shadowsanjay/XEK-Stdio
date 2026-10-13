# Implementation plan and release gates

Build A: authenticated owner API, migrations, PostgreSQL, Redis/Celery, persistent jobs and Next.js UI.
Build B: Ollama JSON screenplay, versions, approval, editable shot timeline and XEK preset.
Build C: ComfyUI images, local speech adapter, measured narration, captions, motion-comic MP4.
Build D: configurable ComfyUI video workflow, capabilities and character references with explicit warnings.
Build E: per-shot render checkpoints, full target timeline, media quality report and resume.
Build F: non-overlapping ranked vertical Shorts with user-specified focal points.
Build G: encrypted OAuth, owner-authorized private uploads, schedule and duplicate guards.
Build H: persistent schedules and longer targets with explicit acceptance gates.

Run unit/integration tests against real local FFmpeg. Mock only network services in labeled tests.
Live generation and upload acceptance require separately installed models, GPU where applicable,
Tamil font, authorized Google credentials and channel-owner action. Never mark those gates passed
based on adapter tests. Record actual verification in COMPATIBILITY.md.

Initial release intentionally exposes limitations: automatic focus detection, identity scoring,
music/SFX synthesis, parallax, thumbnail uploads and advanced timeline layer editing require further
implementation. Configured audio assets can be mixed; no missing media is replaced by fake footage.
