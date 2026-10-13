# Hardware-aware local model installation

Run `python scripts/doctor.py` first. Install helper dependencies with `pip install -e '.[setup]'`.
Run `python scripts/configure_models.py --apply` to set the requested local endpoints/models without
overwriting existing authentication secrets.
`python scripts/configure_ffmpeg.py --download` obtains/configures FFmpeg and ffprobe through the
installed static-ffmpeg helper if PATH binaries are missing. The Windows dependency installer calls it.
The report reads OS, CPU, actual RAM and NVIDIA VRAM, checks model endpoints, FFmpeg and Python
modules. If GPU/RAM detection is unavailable, it refuses to assume a compatible machine.

## This laptop's inspected hardware

Windows 11, Intel i5-12450H (8 cores / 12 threads), 15.7 GiB physical RAM,
NVIDIA RTX 2050 (4096 MiB VRAM, driver 555.99), Intel UHD graphics, about 118 GiB free disk.
At inspection only 2.9 GiB RAM was free. These are local measurements, not a benchmark.

Selected profile: **motion-comic**, Qwen3 8B, FLUX.1-schnell Q4_0 GGUF with a quantized T5 encoder,
Indic Parler-TTS on CPU and Whisper small. ComfyUI uses CPU offload/low-VRAM mode; inference is
experimental on this hardware until a real shot is measured. The conservative setup gate requires
11 GiB free RAM for the image-model test. Close memory-heavy applications yourself before retrying.
We do not close your applications or silently download models that fail the hardware check.

Wan2.2 TI2V 5B is not selected on this 4 GiB GPU. Its official native-offload example targets 8 GiB
VRAM: https://docs.comfy.org/tutorials/video/wan/wan2_2 . The downloader also uses a conservative
24 GiB system RAM gate for this profile. Those gates are policy estimates, not universal limits.
Higher-memory machines can select it with `--profile wan2.2-ti2v-5b`. Supply a tested API-format
I2V workflow before enabling video generation. Motion-comic is offered explicitly; footage is
never misrepresented as a video-model result.

## Windows

Python 3.12, Git and Node 22 are prerequisites. In the repository:
```
powershell -File scripts/install-services.ps1 -Component dependencies -PythonExe python
powershell -File scripts/install-services.ps1 -Component ollama -PythonExe python
powershell -File scripts/install-services.ps1 -Component comfy -PythonExe python -TorchBackend cu124
powershell -File scripts/install-services.ps1 -Component speech -PythonExe python
```
Use a full Python path if Python is not on PATH. Installers stop on failures and do not pull weights.
Ollama installation uses the normal official winget package and may require your consent; it does
not automatically accept license prompts. ComfyUI/GGUF and speech use separate private environments
under `.runtime` because their transformer versions differ.

RTX 2050 driver 555.99 can use the CUDA 12.4 torch build chosen by `-TorchBackend cu124`; newer CUDA
builds may require a driver upgrade. The script pins torch 2.6.0 for that backend. Current ComfyUI
dependencies may change; verify its startup logs. CPU is the default installer backend. After a
NVIDIA driver update you can choose a different compatible torch build yourself. No driver installer
is run automatically.

Ollama: https://ollama.com/download . ComfyUI: https://github.com/Comfy-Org/ComfyUI .
GGUF nodes: https://github.com/city96/ComfyUI-GGUF . Image weights:
https://huggingface.co/city96/FLUX.1-schnell-gguf and text encoder:
https://huggingface.co/city96/t5-v1_1-xxl-encoder-gguf . These are quantizations of the requested model,
not a substitution with unrelated images. FLUX schnell uses four diffusion steps; the supplied graph
uses distilled-model conditioning and does not claim negative-prompt or identity-reference support.

## Downloads (dry-run first)

```
python scripts/download_models.py --profile ollama
python scripts/download_models.py --profile auto
python scripts/download_models.py --profile speech
python scripts/download_models.py --profile whisper
```
The catalog resolves actual remote file sizes and exact model revisions before transfer. Add
`--download` to each command only after its hardware/access checks are satisfied. Downloads are
cached and the selected revisions are recorded in `data/model-install-manifest.json`.
The Ollama pull command requires Ollama installed and running. Hub models use the local HF cache.
All model IDs, paths and service URLs can be overridden in `.env`/`models/catalog.json`.

**Manual authorization:** open https://huggingface.co/ai4bharat/indic-parler-tts using your account
and accept its access conditions yourself. The page can require sharing contact information.
Use Hugging Face's local login (`hf auth login`) or an HF_TOKEN environment variable after approval.
Never paste your token into chat or commit it. Some FLUX files may also require access approval.
An access denial is a blocker, not something the studio bypasses.

Default local endpoints are Ollama http://localhost:11434, ComfyUI http://127.0.0.1:8188,
speech http://localhost:8001. Docker templates use host.docker.internal to reach those host services.

## Start and validate

After dependencies and weights are installed, run:
```
powershell -File scripts/start-services.ps1 -WithModels
python scripts/doctor.py
python scripts/acceptance.py --run
```
The launcher uses hidden helper windows and writes logs in data/logs. It verifies memory before
launching model services and reports launches separately from readiness. It does not start duplicate
servers intentionally: check/stop existing service processes before running it again.

Low-memory mode unloads Ollama after screenplay generation, ComfyUI after artwork generation and
speech weights after synthesis. Use one heavy job at a time. The speech endpoint is on a trusted
loopback interface; do not expose model services to the internet.

The acceptance runner creates the actual 60-second Tamil sample, waits for real screenplay and
production jobs, requires a quality-passing movie and at least one Short, and writes a result report.
It does not use mocks, fabricate outputs or upload to YouTube. It stops before generation if required
services are unavailable. Inspect the exported media and Tamil pronunciation before scaling.

## Linux / macOS

Run `bash scripts/install-services.sh` for application prerequisites. Install FFmpeg via your package
manager and Ollama from https://ollama.com/download . Clone ComfyUI and ComfyUI-GGUF into `.runtime`,
create its own environment and install the PyTorch build recommended for your actual OS/GPU before
ComfyUI requirements. Speech must have its own environment using services/speech/requirements.txt.
Use `--cpu` on machines without validated CUDA support. Apple/AMD acceleration and RAM/VRAM sharing
are not inferred as NVIDIA-compatible. The same doctor/downloader/acceptance commands apply.
