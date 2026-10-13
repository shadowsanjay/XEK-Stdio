"""Explicitly mocked network adapter unit tests; no live-model success claims."""
import json

import httpx
import pytest

from xek.adapters import ComfyUI, Ollama, ProviderError
from xek.config import settings
from xek.schemas import CreateProject, Shot


def test_whisper_uses_private_project_cache(monkeypatch):
    import sys
    import types
    from xek.adapters import Whisper
    from xek.config import settings
    calls = []
    class LocalWhisperDouble:
        def __init__(self, name, **options):
            calls.append(options)
        def transcribe(self, path, **options):
            return iter([types.SimpleNamespace(start=0, end=1, text="Tamil test")]), None
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=LocalWhisperDouble))
    Whisper().align(settings().data_dir / "test.wav", "ta")
    assert calls[0]["download_root"] == str(settings().data_dir / "model-cache" / "whisper")


def network(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))


def test_ollama_requests_schema_and_validates_target(monkeypatch, spec, script):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["stream"] is False
        assert payload["format"]["properties"]["shots"]
        return httpx.Response(200, json={"response": json.dumps(script)})
    network(monkeypatch, handler)
    output = Ollama().generate(CreateProject.model_validate(spec))
    assert len(output.shots) == 6
    script["shots"][-1]["duration"] = 8
    with pytest.raises(ValueError, match="target"):
        Ollama().generate(CreateProject.model_validate(spec))


def test_comfy_submission_poll_retrieve(monkeypatch, tmp_path, spec):
    workflow = tmp_path / "workflow.json"
    workflow.write_text(json.dumps({"prompt": {"1": {"class_type": "TestUnitNode", "inputs": {"text": ""}}},
                         "bindings": {"positive": {"node": "1", "input": "text"}},
                         "output_node": "1", "capabilities": {}}))
    monkeypatch.setattr(settings(), "image_workflow", workflow)
    seen = []
    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/prompt":
            assert "stone door" in json.loads(request.content)["prompt"]["1"]["inputs"]["text"]
            return httpx.Response(200, json={"prompt_id": "unit-prompt"})
        if request.url.path.startswith("/history"):
            return httpx.Response(200, json={"unit-prompt": {"status": {"completed": True},
                    "outputs": {"1": {"images": [{"filename": "test.png"}]}}}})
        return httpx.Response(200, content=b"mock-image-data")
    network(monkeypatch, handler)
    shot = Shot(scene_id="castle", location_id="castle", start_time=0, duration=5, visual_prompt="stone door")
    output = tmp_path / "output.png"
    ComfyUI().generate(shot, CreateProject.model_validate(spec), "image", output)
    assert output.read_bytes() == b"mock-image-data" and seen == ["/prompt", "/history/unit-prompt", "/view"]
    shot.reference_assets = ["some/image.png"]
    with pytest.raises(ProviderError, match="reference conditioning"):
        ComfyUI().generate(shot, CreateProject.model_validate(spec), "image", output)


def test_comfy_execution_error_is_failure(monkeypatch, tmp_path, spec):
    workflow = tmp_path / "workflow.json"
    workflow.write_text(json.dumps({"prompt": {}, "output_node": "1"}))
    monkeypatch.setattr(settings(), "image_workflow", workflow)
    def handler(request):
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "failure"})
        return httpx.Response(200, json={"failure": {"status": {"status_str": "error"}}})
    network(monkeypatch, handler)
    shot = Shot(scene_id="test", location_id="test", start_time=0, duration=5, visual_prompt="A test scene")
    with pytest.raises(ProviderError, match="execution failed"):
        ComfyUI().generate(shot, CreateProject.model_validate(spec), "image", tmp_path / "output.png")
