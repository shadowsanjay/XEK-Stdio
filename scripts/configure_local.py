"""Create private local configuration without printing credentials or overwriting an existing file."""
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

path = Path(".env")
if path.exists():
    raise SystemExit(".env already exists; update it directly if needed")
lines = ["AUTH_SECRET=" + secrets.token_urlsafe(48), "ADMIN_USERNAME=admin",
         "ADMIN_PASSWORD=" + secrets.token_urlsafe(24), "DATABASE_URL=sqlite:///./data/xek.db",
         "WORKER_MODE=inline", "DATA_DIR=data", "TOKEN_ENCRYPTION_KEY=" + Fernet.generate_key().decode(),
         "YOUTUBE_PUBLISHING_ENABLED=false", "OLLAMA_MODEL=qwen3:8b", "OLLAMA_URL=http://localhost:11434",
         "COMFYUI_URL=http://127.0.0.1:8188", "SPEECH_URL=http://localhost:8001",
         "IMAGE_WORKFLOW=workflows/flux-schnell-gguf.json", "TTS_MODEL=ai4bharat/indic-parler-tts",
         "TTS_DEVICE=cpu", "LOW_MEMORY_MODE=true"]
# Optional local test binaries. Docker and normal installations use PATH executables.
for name in ["ffmpeg", "ffprobe"]:
    binary = Path(f".venv/Lib/site-packages/static_ffmpeg/bin/win32/{name}.exe").resolve()
    if binary.is_file():
        lines.append(f"{name.upper()}={binary.as_posix()}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Created .env. The generated owner password is available only in that local file.")
