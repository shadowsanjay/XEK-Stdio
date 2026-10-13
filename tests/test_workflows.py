import json
from pathlib import Path

import pytest

@pytest.mark.parametrize("filename", ["flux-schnell-gguf.json", "flux-schnell-fp8.json", "video.json"])
def test_workflow_references_and_binding_contracts(filename):
    workflow = json.loads((Path("workflows") / filename).read_text(encoding="utf-8"))
    graph = workflow["prompt"]
    assert workflow["output_node"] in graph
    for binding in workflow["bindings"].values():
        assert binding["node"] in graph
        assert binding["input"] in graph[binding["node"]]["inputs"]
    for node in graph.values():
        for value in node["inputs"].values():
            if isinstance(value, list):
                assert value[0] in graph
    if filename == "video.json":
        assert workflow["capabilities"]["image_to_video"]
        assert "init_image" in workflow["bindings"]
