from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    auth_secret: str = ""
    admin_username: str = "admin"
    admin_password: str = ""
    database_url: str = "sqlite:///./data/xek.db"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: Path = Path("data")
    web_origin: str = "http://localhost:3000"
    public_api_url: str = "http://localhost:8000"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_context: int = 8192
    ollama_max_tokens: int = 16000
    comfyui_url: str = "http://127.0.0.1:8188"
    image_model: str = "flux1-schnell-Q4_0.gguf"
    image_text_encoder: str = "t5-v1_1-xxl-encoder-Q4_K_M.gguf"
    image_clip: str = "clip_l.safetensors"
    image_vae: str = "ae.safetensors"
    video_model: str = "wan2.2_ti2v_5B_fp16.safetensors"
    video_text_encoder: str = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    video_vae: str = "wan2.2_vae.safetensors"
    tts_model: str = "ai4bharat/indic-parler-tts"
    low_memory_mode: bool = True
    image_workflow: Path = Path("workflows/flux-schnell-gguf.json")
    video_workflow: Path = Path("workflows/video.json")
    speech_url: str = "http://localhost:8001"
    whisper_model: str = "small"
    subtitle_font: str = "Noto Sans Tamil"
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    token_encryption_key: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_audit_approved: bool = False
    youtube_publishing_enabled: bool = False
    worker_mode: str = "celery"
    max_upload_mb: int = 20
    model_timeout_seconds: int = 1800

    def validate_security(self):
        if len(self.auth_secret) < 32 or self.auth_secret.startswith("replace-"):
            raise RuntimeError("Set AUTH_SECRET to at least 32 random characters")
        if len(self.admin_password) < 12 or self.admin_password.startswith("replace-"):
            raise RuntimeError("Set ADMIN_PASSWORD to at least 12 characters")
        if self.worker_mode not in {"celery", "inline"}:
            raise RuntimeError("WORKER_MODE must be celery or inline")


@lru_cache
def settings():
    return Settings()
