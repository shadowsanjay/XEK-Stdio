import argparse
import importlib.util
import json
import shutil
from pathlib import Path

import httpx

from xek.config import settings
from xek.hardware import inspect_hardware, recommend


def check():
    cfg = settings()
    hardware = inspect_hardware()
    services = {}
    for name, url in [("ollama", cfg.ollama_url + "/api/tags"),
                      ("comfyui", cfg.comfyui_url + "/system_stats"), ("speech", cfg.speech_url + "/health")]:
        try:
            response = httpx.get(url, timeout=5)
            response.raise_for_status()
            services[name] = {"reachable": True, "url": url, "response": response.json()}
        except (httpx.HTTPError, ValueError):
            services[name] = {"reachable": False, "url": url, "action": "Install/start the service; it is not assumed running"}
    return {"hardware": hardware, "recommendation": recommend(hardware), "services": services,
            "dependencies": {name: bool(importlib.util.find_spec(name)) for name in
                             ["torch", "parler_tts", "faster_whisper", "huggingface_hub", "psutil"]},
            "ffmpeg": shutil.which(cfg.ffmpeg), "ffprobe": shutil.which(cfg.ffprobe),
            "model_access": "Indic Parler-TTS may require Hugging Face access approval; never print/store HF tokens in reports"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/setup-report.json")
    args = parser.parse_args()
    report = check()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
