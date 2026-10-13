"""Read-only, conservative hardware planning. No weights are downloaded by discovery."""
import os
import platform
import shutil
import subprocess
from pathlib import Path


def inspect_hardware():
    try:
        import psutil
        memory = psutil.virtual_memory()
        ram, free = memory.total / 1024**3, memory.available / 1024**3
        cores = psutil.cpu_count(logical=False)
    except ImportError:
        ram = free = cores = None
    cpu = platform.processor() or platform.machine()
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    gpu = []
    smi = shutil.which("nvidia-smi")
    if not smi and os.name == "nt":
        path = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/nvidia-smi.exe"
        if path.is_file():
            smi = str(path)
    gpu_error = None
    if smi:
        try:
            result = subprocess.run([smi, "--query-gpu=name,memory.total,memory.free,driver_version",
                                     "--format=csv,noheader,nounits"], capture_output=True, text=True,
                                    timeout=10, check=True)
            for line in result.stdout.strip().splitlines():
                name, total, available, driver = [s.strip() for s in line.split(",")]
                gpu.append({"name": name, "vram_gb": float(total)/1024,
                            "free_vram_gb": float(available)/1024, "driver": driver, "backend": "cuda"})
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            gpu_error = str(exc)[:200]
    disk = shutil.disk_usage(Path.cwd())
    return {"os": platform.system(), "os_version": platform.version(), "architecture": platform.machine(),
            "cpu": cpu, "physical_cores": cores, "logical_cores": os.cpu_count(),
            "ram_gb": round(ram, 2) if ram else None, "free_ram_gb": round(free, 2) if free else None,
            "gpus": gpu, "gpu_error": gpu_error, "disk_free_gb": round(disk.free/1024**3, 2),
            "non_cuda_gpu_note": "AMD/Intel/Apple GPU acceleration needs separate validation; never inferred as CUDA"}


def recommend(hardware: dict):
    ram = hardware.get("ram_gb") or 0
    free = hardware.get("free_ram_gb") or 0
    vram = max((g.get("vram_gb", 0) for g in hardware.get("gpus", [])), default=0)
    video = vram >= 8 and ram >= 24
    image = "flux-schnell-fp8" if vram >= 16 and ram >= 32 else "flux-schnell-gguf"
    minimum_free = 20 if image == "flux-schnell-fp8" else 11
    blockers = []
    if not hardware.get("ram_gb"):
        blockers.append("RAM detection unavailable; install the setup extra and rerun")
    if free < minimum_free:
        blockers.append(f"Free at least {minimum_free} GiB RAM before the image-model test; currently {free:.2f} GiB")
    if hardware.get("disk_free_gb", 0) < 40:
        blockers.append("Keep at least 40 GiB disk space free before the motion-comic model setup")
    return {"ollama_model": "qwen3:8b", "ollama_context": 8192 if ram < 24 else 16384,
            "image_profile": image, "video_model": "wan2.2-ti2v-5b" if video else None,
            "production_mode": "hybrid" if video else "motion-comic", "tts_device": "cuda" if vram >= 6 else "cpu",
            "comfy_flags": ["--lowvram"] if vram > 0 else ["--cpu"], "minimum_free_ram_gb": minimum_free,
            "download_allowed": not blockers, "blockers": blockers,
            "note": "Conservative setup heuristics, not measured peak memory or a compatibility guarantee. "
                    "Use one model at a time and validate one short shot first."}
