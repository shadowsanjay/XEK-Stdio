"""Dry-run by default. Resolve sizes/revisions before any large model download."""
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError

from xek.config import settings
from xek.hardware import inspect_hardware, recommend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["auto", "flux-schnell-gguf", "flux-schnell-fp8", "wan2.2-ti2v-5b", "speech", "whisper", "ollama"], default="auto")
    parser.add_argument("--comfy-root", type=Path, default=Path(".runtime/ComfyUI"))
    parser.add_argument("--download", action="store_true", help="Perform downloads after all checks pass")
    args = parser.parse_args()
    hardware = inspect_hardware()
    plan = recommend(hardware)
    profile = plan["image_profile"] if args.profile == "auto" else args.profile
    print(json.dumps({"hardware": hardware, "profile": profile, "recommendation": plan}, indent=2))
    cfg = settings()
    cache_dir = cfg.data_dir / "model-cache" / "hub"
    # Configurable HF_TOKEN is read from the environment, never from command arguments or logs.
    token = os.getenv("HF_TOKEN")
    if profile == "ollama":
        if args.download:
            if (hardware.get("free_ram_gb") or 0) < 7 or hardware["disk_free_gb"] < 10:
                raise SystemExit("Free at least 7 GiB RAM and 10 GiB disk for Qwen3 8B before pulling")
            ollama = shutil.which("ollama")
            if not ollama:
                raise SystemExit("Install/start Ollama first; see scripts/install-services.ps1")
            subprocess.run([ollama, "pull", cfg.ollama_model], check=True)
        else:
            print(f"Planned: ollama pull {cfg.ollama_model}. No download performed.")
        return
    if profile in {"speech", "whisper"}:
        model = cfg.tts_model if profile == "speech" else "Systran/faster-whisper-" + cfg.whisper_model
        required_free = 6 if profile == "speech" else 2
        api = HfApi(token=token)
        try:
            info = api.model_info(model, files_metadata=True)
            sizes = sum(s.size or 0 for s in info.siblings)
            print(f"Model revision: {info.sha}; repository size estimate: {sizes/1024**3:.2f} GiB")
            if args.download:
                if (hardware.get("free_ram_gb") or 0) < required_free:
                    raise SystemExit(f"Free at least {required_free} GiB RAM before downloading/test-loading this model")
                if hardware["disk_free_gb"] < sizes/1024**3 * 2 + 10:
                    raise SystemExit("Insufficient disk headroom for model cache")
                snapshot_download(model, revision=info.sha, token=token, cache_dir=cache_dir,
                                  allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt", "*.bin"])
            else:
                print("Dry run: model access may still be gated until you authorize it on Hugging Face.")
        except (GatedRepoError, HfHubHTTPError):
            raise SystemExit(f"Access denied/unavailable: authorize model access at https://huggingface.co/{model} "
                             "then set HF_TOKEN locally. No credentials were printed.") from None
        return
    catalog = json.loads(Path("models/catalog.json").read_text(encoding="utf-8"))[profile]
    vram = max((g["vram_gb"] for g in hardware["gpus"]), default=0)
    blockers = []
    for actual, minimum, label in [(hardware.get("ram_gb") or 0, catalog["minimum_ram_gb"], "total RAM"),
                                   (hardware.get("free_ram_gb") or 0, catalog["minimum_free_ram_gb"], "free RAM"),
                                   (vram, catalog["minimum_vram_gb"], "VRAM")]:
        if actual < minimum:
            blockers.append(f"{label}: {actual:.2f} GiB available; conservative requirement {minimum} GiB")
    api = HfApi(token=token)
    files = []
    try:
        for item in catalog["files"]:
            info = api.model_info(item["repo"], files_metadata=True)
            sibling = next(s for s in info.siblings if s.rfilename == item["file"])
            files.append({**item, "revision": info.sha, "bytes": sibling.size or 0})
    except (GatedRepoError, HfHubHTTPError, StopIteration):
        raise SystemExit("Model catalog access failed. Verify repo/file names and authorize any gated model "
                         "on Hugging Face, then set HF_TOKEN locally. No large downloads performed.") from None
    total_gb = sum(item["bytes"] for item in files)/1024**3
    print(json.dumps({"files": files, "download_gb": total_gb, "blockers": blockers}, indent=2))
    if not args.download:
        print("Dry run. Add --download only when prerequisites are ready.")
        return
    if blockers:
        raise SystemExit("Download stopped by actual hardware checks. Motion-comic remains available after freeing RAM.")
    args.comfy_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.comfy_root).free/1024**3 < total_gb*2 + 15:
        raise SystemExit("Insufficient disk space for both cache and model files plus rendering headroom")
    for item in files:
        folder = args.comfy_root / "models" / item["folder"]
        folder.mkdir(parents=True, exist_ok=True)
        cached = hf_hub_download(item["repo"], filename=item["file"], revision=item["revision"], token=token,
                                 cache_dir=cache_dir)
        destination = folder / Path(item["file"]).name
        if not destination.exists() or destination.stat().st_size != item["bytes"]:
            shutil.copy2(cached, destination)
        print("Installed " + str(destination))
    manifest = Path("data/model-install-manifest.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"profile": profile, "files": files}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
