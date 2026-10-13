"""Apply non-secret hardware-selected model settings while retaining existing credentials."""
import argparse
from pathlib import Path

from xek.hardware import inspect_hardware, recommend


parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
plan = recommend(inspect_hardware())
values = {"OLLAMA_URL": "http://localhost:11434", "OLLAMA_MODEL": "qwen3:8b",
          "OLLAMA_CONTEXT": str(plan["ollama_context"]), "COMFYUI_URL": "http://127.0.0.1:8188",
          "IMAGE_WORKFLOW": "workflows/flux-schnell-gguf.json", "IMAGE_MODEL": "flux1-schnell-Q4_0.gguf",
          "IMAGE_TEXT_ENCODER": "t5-v1_1-xxl-encoder-Q4_K_M.gguf", "IMAGE_CLIP": "clip_l.safetensors",
          "IMAGE_VAE": "ae.safetensors", "VIDEO_MODEL": "wan2.2_ti2v_5B_fp16.safetensors",
          "SPEECH_URL": "http://localhost:8001", "TTS_MODEL": "ai4bharat/indic-parler-tts",
          "TTS_DEVICE": plan["tts_device"], "LOW_MEMORY_MODE": "true"}
if plan["image_profile"] == "flux-schnell-fp8":
    values.update({"IMAGE_WORKFLOW":"workflows/flux-schnell-fp8.json", "IMAGE_MODEL":"flux1-schnell-fp8.safetensors"})
for key, value in values.items():
    print(f"{key}={value}")
if args.apply:
    path = Path(".env")
    if not path.is_file():
        raise SystemExit("Run configure_local.py first; no file was overwritten")
    lines = path.read_text(encoding="utf-8").splitlines()
    existing = set()
    changed = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values:
            changed.append(key + "=" + values[key])
            existing.add(key)
        else:
            changed.append(line)
    changed.extend(key + "=" + value for key, value in values.items() if key not in existing)
    path.write_text("\n".join(changed) + "\n", encoding="utf-8")
    print("Updated non-secret model configuration. Restart local API/worker/speech to apply it.")
print("Recommended production mode: " + plan["production_mode"])
for blocker in plan["blockers"]:
    print("Blocker: " + blocker)
