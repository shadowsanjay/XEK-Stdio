"""Real FFmpeg integration using explicitly synthetic test fixtures, never AI acceptance output."""
import shutil
import wave
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from xek.config import settings
from xek.media import assemble, duration, mix_audio, probe, quality_report, render_shot, write_subtitles
from xek.schemas import AudioTrack, Shot


@pytest.fixture
def media_binaries(monkeypatch):
    cfg = settings()
    ffmpeg = shutil.which(cfg.ffmpeg)
    ffprobe = shutil.which(cfg.ffprobe)
    if not ffmpeg or not ffprobe:
        # Optional downloaded tooling remains outside source control.
        root = Path(__file__).resolve().parents[1]
        ffmpeg = root / ".venv/Lib/site-packages/static_ffmpeg/bin/win32/ffmpeg.exe"
        ffprobe = root / ".venv/Lib/site-packages/static_ffmpeg/bin/win32/ffprobe.exe"
        if not ffmpeg.is_file() or not ffprobe.is_file():
            pytest.skip("Install FFmpeg and ffprobe for real rendering tests")
    monkeypatch.setattr(cfg, "ffmpeg", str(ffmpeg))
    monkeypatch.setattr(cfg, "ffprobe", str(ffprobe))
    monkeypatch.setattr(cfg, "subtitle_font", "Arial")


def fixture_media(tmp_path):
    image = Image.new("RGB", (800, 450), "#28384c")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 80, 400, 400), fill="#b04a4a")
    draw.text((440, 160), "RENDER TEST\nSYNTHETIC FIXTURE\nNOT AI FOOTAGE", fill="white")
    artwork = tmp_path / "fixture.png"
    image.save(artwork)
    audio = tmp_path / "fixture.wav"
    import math
    import struct
    with wave.open(str(audio), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(b"".join(struct.pack("<h", int(4000 * math.sin(2 * math.pi * 440 * t / 16000)))
                                 for t in range(8000)))
    captions = tmp_path / "fixture.srt"
    write_subtitles([{"start": 0, "end": 0.5, "text": "Synthetic renderer fixture"}], captions, 1.5)
    return artwork, audio, captions


def test_real_movie_and_vertical_short(media_binaries, tmp_path):
    artwork, audio, captions = fixture_media(tmp_path)
    shot = Shot(scene_id="test", location_id="test", start_time=0, duration=1.5,
                visual_prompt="Synthetic test fixture only", crop_x=0.2)
    first, second = tmp_path / "first.mp4", tmp_path / "second.mp4"
    render_shot(shot, artwork, audio, captions, first)
    shot.camera_movement = "zoom-out"
    render_shot(shot, artwork, audio, captions, second)
    movie = tmp_path / "movie.mp4"
    assemble([first, second], movie)
    report = quality_report(movie, 3, captions)
    assert report["passed"], report
    assert abs(duration(movie) - 3) < 0.2
    vertical = tmp_path / "short.mp4"
    render_shot(shot, artwork, audio, captions, vertical, width=1080, height=1920)
    video = next(s for s in probe(vertical)["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1080, 1920)


def test_refuses_speech_that_exceeds_shot(media_binaries, tmp_path):
    artwork, audio, captions = fixture_media(tmp_path)
    shot = Shot(scene_id="test", location_id="test", start_time=0, duration=0.2,
                visual_prompt="Synthetic fixture")
    with pytest.raises(ValueError, match="exceeds"):
        render_shot(shot, artwork, audio, captions, tmp_path / "invalid.mp4")


def test_real_timeline_audio_mix_and_no_artificial_loops(media_binaries, tmp_path, monkeypatch):
    monkeypatch.setattr(settings(), "data_dir", tmp_path)
    artwork, audio, captions = fixture_media(tmp_path)
    shot = Shot(scene_id="test", location_id="test", start_time=0, duration=1.5,
                visual_prompt="Synthetic test fixture")
    movie, mixed = tmp_path / "movie.mp4", tmp_path / "mixed.mp4"
    render_shot(shot, artwork, audio, captions, movie, width=320, height=180)
    track = AudioTrack(asset_path="fixture.wav", kind="sound-effects", start=0.2,
                       duration=0.4, license_note="Synthetic test audio", duck_under_speech=True)
    mix_audio(movie, [track], mixed, 1.5)
    assert abs(duration(mixed) - 1.5) < 0.2
    assert any(s["codec_type"] == "audio" for s in probe(mixed)["streams"])
    track.duration = 1
    with pytest.raises(ValueError, match="shorter"):
        mix_audio(movie, [track], mixed, 1.5)
