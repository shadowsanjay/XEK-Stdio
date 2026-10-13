
import pytest
from pydantic import ValidationError
from xek.config import settings
from xek.db import Job, Project, Session
from xek.jobs import execute
from xek.media import choose_shorts, write_subtitles
from xek.publishing import validate_publish
from xek.schemas import PublishRequest, Screenplay
from xek.storage import safe_path


def test_contiguous_unique_shots(script):
    Screenplay.model_validate(script).check_duration(1)
    script["shots"][1]["start_time"] = 11
    with pytest.raises(ValidationError):
        Screenplay.model_validate(script)
    script["shots"][1]["start_time"] = 10
    script["shots"][1]["id"] = "s0"
    with pytest.raises(ValidationError):
        Screenplay.model_validate(script)


@pytest.mark.parametrize("path", ["../secrets", "../../outside", "/etc/passwd", "C:/outside/private"])
def test_path_traversal(path):
    # Absolute Windows paths are only absolute on Windows.
    import os
    if path.startswith("C:") and os.name != "nt":
        pytest.skip("Windows absolute path")
    with pytest.raises(ValueError):
        safe_path(path)


def test_subtitle_timing(tmp_path):
    with pytest.raises(ValueError):
        write_subtitles([{ "start": 1, "end": 10, "text": "Words"}], tmp_path / "captions.srt", 2)
    write_subtitles([{ "start": 0, "end": 1, "text": "அவன் வந்தான்"}], tmp_path / "captions.srt", 2)
    assert "அவன்" in (tmp_path / "captions.srt").read_text(encoding="utf-8")


def test_shorts_need_focal_point_and_do_not_overlap(script):
    validated = Screenplay.model_validate(script)
    clips = choose_shorts(validated, 4)
    assert len(clips) == 4 and clips[0]["shot_id"] == "s5"
    assert len({clip["shot_id"] for clip in clips}) == 4
    for shot in validated.shots:
        shot.crop_x = None
    assert not choose_shorts(validated, 4)


def test_unaudited_uploads_cannot_schedule_or_be_public(monkeypatch):
    monkeypatch.setattr(settings(), "youtube_publishing_enabled", True)
    request = PublishRequest(asset_id="asset", title="Film", owner_approved=True, visibility="public")
    with pytest.raises(ValueError, match="Unaudited"):
        validate_publish(request)


def test_job_failure_persists_without_fake_success(spec):
    with Session.begin() as db:
        project = Project(name="test", spec=spec)
        db.add(project)
        db.flush()
        job = Job(project_id=project.id, kind="shorts")
        db.add(job)
        db.flush()
        job_id = job.id
    execute(job_id)
    with Session() as db:
        job = db.get(Job, job_id)
        assert job.state == "failed" and job.error and job.progress < 100
    execute(job_id)
    with Session() as db:
        assert db.get(Job, job_id).attempts == 1
