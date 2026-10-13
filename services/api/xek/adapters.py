"""Real network adapters. Test doubles live only in tests/."""
import copy
import json
import math
import time
from pathlib import Path

import httpx

from .config import settings
from .presets import XEK_RULES
from .schemas import CreateProject, Screenplay, Shot
from .storage import safe_path


class ProviderError(RuntimeError):
    pass


class Ollama:
    def generate(self, spec: CreateProject) -> Screenplay:
        cfg = settings()
        rules = XEK_RULES if spec.universe == "xek" else "Create an original story universe."
        prompt = f"""You are a film director. Return only the specified screenplay JSON.
{rules}
Production request: {spec.model_dump_json()}
Use natural conversational {'Tamil' if spec.language == 'ta' else 'English'} for narration/dialogue.
Every shot must include unique id, scene_id, location_id, duration, start_time and visual_prompt.
Create contiguous shots of {'2-5' if spec.mode in {'video','hybrid'} else '4-12'} seconds
that sum to EXACTLY {spec.duration_minutes * 60} seconds.
Each shot needs spoken narration or dialogue, sized to fit its duration, roughly 2 words per second.
Use English visual prompts. Include character IDs, camera movements and lighting continuity.
hero=true only for important action. Set hook_score for Shorts. Set crop_x only if a meaningful
focal point is known, else null. Legend notes must label fiction and tradition without inventing history.
No repeated shots or narration to pad the duration. Do not include filesystem paths.
"""
        with httpx.Client(timeout=cfg.model_timeout_seconds) as client:
            response = client.post(f"{cfg.ollama_url}/api/generate", json={
                "model": cfg.ollama_model, "prompt": prompt, "stream": False, "think": False,
                "keep_alive": 0 if cfg.low_memory_mode else "5m",
                "format": Screenplay.model_json_schema(),
                "options": {"temperature": 0.7, "num_ctx": cfg.ollama_context,
                            "num_predict": cfg.ollama_max_tokens},
            })
            response.raise_for_status()
            screenplay = Screenplay.model_validate_json(response.json()["response"])
        screenplay.check_duration(spec.duration_minutes)
        return screenplay


class ComfyUI:
    def __init__(self):
        self.cfg = settings()

    def release_models(self):
        if self.cfg.low_memory_mode:
            with httpx.Client(timeout=30) as client:
                response = client.post(self.cfg.comfyui_url + "/free", json={"unload_models": True, "free_memory": True})
                response.raise_for_status()

    def capabilities(self):
        with httpx.Client(timeout=10) as client:
            r = client.get(f"{self.cfg.comfyui_url}/object_info")
            r.raise_for_status()
            nodes = r.json()
        result = {"reachable": True, "nodes": len(nodes), "workflows": {}}
        for kind, path in [("image", self.cfg.image_workflow), ("video", self.cfg.video_workflow)]:
            if not path.exists():
                result["workflows"][kind] = {"configured": False}
                continue
            manifest = json.loads(path.read_text(encoding="utf-8"))
            missing = sorted({n["class_type"] for n in manifest["prompt"].values()} - set(nodes))
            result["workflows"][kind] = {"configured": not missing, "missing_nodes": missing,
                                            "capabilities": manifest.get("capabilities", {})}
        return result

    def generate(self, shot: Shot, spec: CreateProject, kind: str, output: Path, cancelled=lambda: False,
                 init_image: Path | None = None):
        cfg = self.cfg
        path = cfg.image_workflow if kind == "image" else cfg.video_workflow
        if not path.exists():
            raise ProviderError(f"Configure {kind.upper()}_WORKFLOW with an exported ComfyUI API workflow")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        graph = copy.deepcopy(manifest["prompt"])
        capabilities = manifest.get("capabilities", {})
        if kind == "video" and shot.duration > capabilities.get("max_duration", 0):
            raise ProviderError("Shot exceeds configured video model duration; split this shot")
        if "languages" in capabilities and spec.language not in capabilities["languages"]:
            raise ProviderError("Workflow does not support the requested language")
        characters = [c for c in spec.characters if c.id in shot.character_ids]
        refs = shot.reference_assets + [r for c in characters for r in c.reference_assets]
        if refs and not capabilities.get("reference_conditioning"):
            raise ProviderError("References supplied but workflow lacks reference conditioning")
        if any(f"reference_{i}" not in manifest.get("bindings", {}) for i in range(len(refs))):
            raise ProviderError("Workflow does not bind every supplied reference image")
        positive = " ".join([shot.visual_prompt, spec.style, shot.lighting, shot.mood,
                              *[c.canonical_prompt or c.visual_description for c in characters]])
        negative = " ".join([shot.negative_prompt, *[c.negative_prompt for c in characters]])
        values = {"positive": positive, "negative": negative, "seed": shot.seed,
                  "duration": shot.duration, "frames": round(shot.duration * capabilities.get("fps", 24)),
                  "width": capabilities.get("width", 1024), "height": capabilities.get("height", 576),
                  "image_model": cfg.image_model, "image_text_encoder": cfg.image_text_encoder,
                  "image_clip": cfg.image_clip, "image_vae": cfg.image_vae, "video_model": cfg.video_model,
                  "video_text_encoder": cfg.video_text_encoder, "video_vae": cfg.video_vae}
        if capabilities.get("frame_step"):
            step = capabilities["frame_step"]
            offset = capabilities.get("frame_offset", 1)
            values["frames"] = math.ceil((values["frames"] - offset)/step)*step + offset
        if capabilities.get("image_to_video") and init_image is None:
            raise ProviderError("This image-to-video workflow requires a generated keyframe")
        with httpx.Client(timeout=60) as client:
            if kind == "video" and capabilities.get("minimum_vram_gb"):
                response = client.get(cfg.comfyui_url + "/system_stats")
                response.raise_for_status()
                devices = response.json().get("devices", [])
                actual_vram = max((d.get("vram_total", 0)/1024**3 for d in devices), default=0)
                if actual_vram < capabilities["minimum_vram_gb"]:
                    raise ProviderError("Video model exceeds the ComfyUI host's detected VRAM. "
                                        "Choose motion-comic mode or configure a compatible model host/workflow.")
            if init_image:
                with init_image.open("rb") as f:
                    uploaded = client.post(cfg.comfyui_url + "/upload/image", files={"image": (init_image.name, f)},
                                           data={"type": "input", "overwrite": "false"})
                uploaded.raise_for_status()
                item = uploaded.json()
                values["init_image"] = "/".join(filter(None, [item.get("subfolder"), item["name"]]))
            for index, ref in enumerate(refs):
                source = safe_path(ref)
                with source.open("rb") as f:
                    r = client.post(f"{cfg.comfyui_url}/upload/image", files={"image": (source.name, f)},
                                    data={"type": "input", "overwrite": "false"})
                r.raise_for_status()
                upload = r.json()
                values[f"reference_{index}"] = "/".join(filter(None, [upload.get("subfolder"), upload["name"]]))
            for key, binding in manifest.get("bindings", {}).items():
                if key not in values:
                    raise ProviderError(f"Missing workflow binding value: {key}")
                graph[str(binding["node"])]["inputs"][binding["input"]] = values[key]
            r = client.post(f"{cfg.comfyui_url}/prompt", json={"prompt": graph})
            r.raise_for_status()
            response = r.json()
            if response.get("node_errors") or "prompt_id" not in response:
                raise ProviderError(f"ComfyUI rejected workflow: {response.get('node_errors')}")
            prompt_id = response["prompt_id"]
            deadline = time.monotonic() + cfg.model_timeout_seconds
            while time.monotonic() < deadline:
                if cancelled():
                    # Do not interrupt a shared server globally; remove only this queued prompt.
                    client.post(f"{cfg.comfyui_url}/queue", json={"delete": [prompt_id]})
                    raise ProviderError("Generation cancelled; active model inference may finish on the server")
                history_response = client.get(f"{cfg.comfyui_url}/history/{prompt_id}")
                history_response.raise_for_status()
                history = history_response.json().get(prompt_id)
                if history:
                    status = history.get("status", {})
                    if status.get("status_str") == "error":
                        raise ProviderError("ComfyUI execution failed; inspect server history")
                    if status.get("completed"):
                        node = history.get("outputs", {}).get(str(manifest["output_node"]), {})
                        candidates = node.get(manifest.get("output_key", "images"), [])
                        if not candidates:
                            candidates = node.get("videos") or node.get("images") or node.get("gifs") or []
                        if not candidates:
                            raise ProviderError("Workflow completed without the declared media output")
                        item = candidates[0]
                        media = client.get(f"{cfg.comfyui_url}/view", params={
                            "filename": item["filename"], "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output"),
                        })
                        media.raise_for_status()
                        output.write_bytes(media.content)
                        return
                time.sleep(2)
        raise ProviderError(f"ComfyUI timeout for prompt {prompt_id}; inspect server before resubmitting")


class Speech:
    def release_models(self):
        cfg = settings()
        if cfg.low_memory_mode:
            with httpx.Client(timeout=30) as client:
                r = client.post(cfg.speech_url + "/unload")
                r.raise_for_status()

    def generate(self, text: str, language: str, voice: str, output: Path):
        if not text.strip():
            raise ProviderError("Every shot needs narration/dialogue; no silent substitute is generated")
        cfg = settings()
        with httpx.Client(timeout=cfg.model_timeout_seconds) as client:
            r = client.post(f"{cfg.speech_url}/synthesize", json={"text": text, "language": language,
                                                                  "voice_description": voice})
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("audio/"):
                raise ProviderError("Speech service returned a non-audio response")
            output.write_bytes(r.content)


class Whisper:
    def align(self, audio: Path, language: str):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ProviderError("Install the transcription extra and download a Whisper model") from None
        model = WhisperModel(settings().whisper_model, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio), language=language, word_timestamps=True)
        return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
