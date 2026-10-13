import json
import math
import shutil
import subprocess
from pathlib import Path

from .config import settings
from .schemas import Screenplay, Shot


def run(args: list[str], timeout: int = 7200):
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, shell=False)
    if proc.returncode:
        raise RuntimeError(f"Media process failed: {proc.stderr[-3000:]}")
    return proc.stdout


def executable(name: str):
    configured = getattr(settings(), name)
    resolved = shutil.which(configured)
    if not resolved:
        raise RuntimeError(f"{name} executable unavailable: {configured}")
    return resolved


def probe(path: Path):
    return json.loads(run([executable("ffprobe"), "-v", "error", "-show_streams", "-show_format",
                           "-of", "json", str(path)]))


def duration(path: Path):
    return float(probe(path)["format"]["duration"])


def timestamp(seconds: float):
    ms = round(seconds * 1000)
    hours, remainder = divmod(ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_subtitles(segments: list[dict], path: Path, maximum: float):
    if not segments:
        raise ValueError("No aligned subtitles; generation must stop")
    lines = []
    previous_end = 0.0
    for i, segment in enumerate(segments, 1):
        start, end = float(segment["start"]), float(segment["end"])
        if not (0 <= start < end <= maximum + 0.1) or start < previous_end - 0.05:
            raise ValueError("Invalid subtitle timing")
        if not segment["text"].strip():
            raise ValueError("Empty subtitle text")
        previous_end = end
        lines.append(f"{i}\n{timestamp(start)} --> {timestamp(end)}\n{segment['text'].strip()}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def subtitle_filter(path: Path):
    # Run FFmpeg with the subtitles beside the output: no Windows drive colon in the filter.
    if not path.name.replace("-", "").replace(".", "").replace("_", "").isalnum():
        raise ValueError("Unsafe subtitle filename")
    font = settings().subtitle_font
    if any(c in font for c in "'\\:,[];"):
        raise ValueError("Invalid subtitle font")
    return f"subtitles={path.name}:force_style='FontName={font},FontSize=20,Outline=2,MarginV=30'"


def render_shot(shot: Shot, image_or_video: Path, speech: Path, subtitles: Path, output: Path,
                is_video=False, width=1920, height=1080, fps=24):
    speech_duration = duration(speech)
    if speech_duration > shot.duration - 0.1:
        raise ValueError(f"Speech ({speech_duration:.2f}s) exceeds shot {shot.id} ({shot.duration}s); edit/split it")
    args = [executable("ffmpeg"), "-y", "-v", "error"]
    if is_video:
        if duration(image_or_video) < shot.duration - 0.1:
            raise ValueError("Generated video is shorter than the shot; regenerate or trim the timeline")
        args += ["-i", str(image_or_video)]
        focus = shot.crop_x if width < height and shot.crop_x is not None else 0.5
        visual = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                  f"crop={width}:{height}:(iw-ow)*{focus}:(ih-oh)/2,fps={fps}")
    else:
        args += ["-i", str(image_or_video)]
        frames = math.ceil(shot.duration * fps)
        zoom = "1.08" if shot.camera_movement.startswith("pan") else "1+0.08*on/" + str(frames)
        if shot.camera_movement == "zoom-out":
            zoom = "1.08-0.08*on/" + str(frames)
        if shot.camera_movement == "static":
            zoom = "1"
        x, y = "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"
        if shot.camera_movement == "pan-right":
            x = "(iw-iw/zoom)*on/" + str(frames)
        if shot.camera_movement == "pan-left":
            x = "(iw-iw/zoom)*(1-on/" + str(frames) + ")"
        focus = shot.crop_x if width < height and shot.crop_x is not None else 0.5
        visual = (f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,"
                  f"crop={width*2}:{height*2}:(iw-ow)*{focus}:(ih-oh)/2,zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:"
                  f"s={width}x{height}:fps={fps}")
    args += ["-i", str(speech), "-vf", visual + "," + subtitle_filter(subtitles),
             "-af", f"loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur={shot.duration}",
             "-t", str(shot.duration), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264",
             "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(output)]
    # Explicit cwd for libass relative subtitle files; shell is never invoked.
    proc = subprocess.run(args, cwd=output.parent, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=7200, shell=False)
    if proc.returncode:
        raise RuntimeError(f"Shot render failed: {proc.stderr[-3000:]}")


def assemble(clips: list[Path], output: Path):
    if not clips or any(not clip.is_file() for clip in clips):
        raise ValueError("Missing rendered shots")
    listing = output.parent / "concat.txt"
    for clip in clips:
        if "'" in str(clip) or "\n" in str(clip):
            raise ValueError("Unsupported clip filename")
    listing.write_text("\n".join(f"file '{clip.resolve().as_posix()}'" for clip in clips), encoding="utf-8")
    run([executable("ffmpeg"), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", "-movflags", "+faststart", str(output)])


def mix_audio(movie: Path, tracks: list, output: Path, expected: float):
    """Mix licensed timeline assets with narration; never loop or synthesize missing audio."""
    from .storage import safe_path
    args = [executable("ffmpeg"), "-y", "-v", "error", "-i", str(movie)]
    filters, mixed = [], ["[voice]"]
    music_tracks = [track for track in tracks if track.duck_under_speech]
    branches = len(music_tracks) + 1
    if music_tracks:
        filters.append(f"[0:a]asplit={branches}[voice]" + "".join(f"[side{i}]" for i in range(branches-1)))
    else:
        filters.append("[0:a]anull[voice]")
    side = 0
    for i, track in enumerate(tracks, 1):
        path = safe_path(track.asset_path)
        if track.start + track.duration > expected + 0.1:
            raise ValueError("Audio track exceeds movie timeline")
        if duration(path) + 0.1 < track.trim_start + track.duration:
            raise ValueError("Audio source is shorter than the requested segment; no looping is allowed")
        args += ["-i", str(path)]
        fade = min(track.fade, track.duration / 2)
        f = (f"[{i}:a]atrim=start={track.trim_start}:duration={track.duration},asetpts=PTS-STARTPTS,"
             f"volume={track.gain},afade=t=in:d={fade},afade=t=out:st={track.duration-fade}:d={fade},"
             f"adelay={round(track.start*1000)}:all=1,apad=whole_dur={expected}[track{i}]")
        filters.append(f)
        if track.duck_under_speech:
            filters.append(f"[track{i}][side{side}]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=250[mix{i}]")
            mixed.append(f"[mix{i}]")
            side += 1
        else:
            mixed.append(f"[track{i}]")
    filters.append("".join(mixed) + f"amix=inputs={len(mixed)}:duration=first:normalize=0,alimiter=limit=0.95[out]")
    run(args + ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[out]", "-t", str(expected),
                "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(output)])


def quality_report(movie: Path, expected: float, subtitles: Path):
    metadata = probe(movie)
    streams = metadata["streams"]
    video = next((s for s in streams if s["codec_type"] == "video"), {})
    audio = next((s for s in streams if s["codec_type"] == "audio"), {})
    actual = float(metadata["format"]["duration"])
    checks = {"duration": abs(actual - expected) < 0.6, "video": bool(video), "audio": bool(audio),
              "resolution": video.get("width") == 1920 and video.get("height") == 1080,
              "subtitles": subtitles.is_file() and subtitles.stat().st_size > 10}
    # Decode the full file and inspect black intervals and sustained silence.
    result = subprocess.run([executable("ffmpeg"), "-v", "info", "-i", str(movie),
                             "-vf", "blackdetect=d=0.5:pix_th=0.02", "-af", "silencedetect=n=-50dB:d=8",
                             "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=7200)
    checks["decodable"] = result.returncode == 0
    warnings = []
    if "black_start:" in result.stderr:
        warnings.append("Dark/black intervals detected. Inspect the film; horror lighting can trigger this warning.")
    if "silence_start:" in result.stderr:
        warnings.append("Sustained silence detected; inspect narration and audio mix.")
    return {"passed": all(checks.values()), "checks": checks, "duration": actual,
            "warnings": warnings, "requires_visual_review": True,
            "character_consistency": "Manual review required; no identity classifier is configured"}


def choose_shorts(screenplay: Screenplay, count: int, maximum: float = 45):
    candidates = sorted(screenplay.shots, key=lambda s: s.hook_score, reverse=True)
    selected = []
    for shot in candidates:
        # A focal point must be explicitly provided/confirmed by the editor.
        if shot.crop_x is None:
            continue
        start, end = shot.start_time, shot.start_time + shot.duration
        if any(start < item["end"] and end > item["start"] for item in selected):
            continue
        selected.append({"shot_id": shot.id, "start": start, "end": min(end, start + maximum),
                         "crop_x": shot.crop_x, "title": shot.narration[:70] or screenplay.title})
        if len(selected) >= count:
            break
    return selected


def render_short(movie: Path, clip: dict, output: Path):
    # Fractional focus aligns the crop within the source bounds; captions are already burned in.
    vf = f"crop=ih*9/16:ih:(iw-ih*9/16)*{clip['crop_x']}:0,scale=1080:1920"
    run([executable("ffmpeg"), "-y", "-v", "error", "-ss", str(clip["start"]), "-i", str(movie),
         "-t", str(clip["end"] - clip["start"]), "-vf", vf, "-c:v", "libx264", "-preset", "fast",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(output)])
