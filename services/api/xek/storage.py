from pathlib import Path
from uuid import UUID

from .config import settings


def safe_path(relative: str) -> Path:
    root = settings().data_dir.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or candidate == root:
        raise ValueError("Asset path is outside storage")
    return candidate


def project_dir(project_id: str, version: int) -> Path:
    UUID(project_id)
    folder = safe_path(f"{project_id}/v{version}")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def relative(path: Path) -> str:
    return path.resolve().relative_to(settings().data_dir.resolve()).as_posix()
