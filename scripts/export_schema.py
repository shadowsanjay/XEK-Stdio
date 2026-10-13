import json
from pathlib import Path
from xek.main import app

Path("packages/shared/openapi.json").write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
