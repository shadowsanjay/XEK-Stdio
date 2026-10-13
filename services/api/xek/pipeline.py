import hashlib
import json
import shutil
from pathlib import Path

from sqlalchemy import select

from .adapters import ComfyUI, Ollama, Speech, Whisper
from .db import Asset, Job, Project, ScriptVersion, Session
from .jobs import cancelled, update_job
from .media import assemble, choose_shorts, duration, mix_audio, probe, quality_report, render_shot, write_subtitles
from .schemas import CreateProject, Screenplay
from .storage import project_dir, relative, safe_path


def inputs(job_id):
    with Session() as db:
        job = db.get(Job, job_id)
        project = db.get(Project, job.project_id)
        return job, project, CreateProject.model_validate(project.spec)


def store_asset(project_id: str, kind: str, path: Path, metadata: dict):
    rel = relative(path)
    with Session.begin() as db:
        existing = db.scalar(select(Asset).where(Asset.project_id == project_id, Asset.path == rel))
        if existing:
            existing.metadata_json = metadata
            return existing.id
        asset = Asset(project_id=project_id, kind=kind, path=rel, metadata_json=metadata)
        db.add(asset)
        db.flush()
        return asset.id


def save_script(project_id: str, script: Screenplay):
    with Session.begin() as db:
        project = db.get(Project, project_id)
        project.version += 1
        project.approved_version = None
        project.screenplay = script.model_dump()
        project.status = "script-ready"
        db.add(ScriptVersion(project_id=project_id, version=project.version, screenplay=script.model_dump()))


def screenplay_job(job_id):
    _, project, spec = inputs(job_id)
    update_job(job_id, "Writing validated screenplay with Ollama", 5)
    script = Ollama().generate(spec)
    update_job(job_id, "Saving screenplay and storyboard", 90)
    save_script(project.id, script)


def fingerprint(shot, spec):
    data = {"shot": shot.model_dump(), "characters": [c.model_dump() for c in spec.characters],
            "pronunciation": spec.pronunciation, "mode": spec.mode, "style": spec.style,
            "language": spec.language}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def production(job_id):
    job, project, spec = inputs(job_id)
    if not project.screenplay:
        if spec.production_mode == "manual":
            raise ValueError("Generate and approve a screenplay before manual production")
        screenplay_job(job_id)
        job, project, spec = inputs(job_id)
    if spec.production_mode == "manual" and project.approved_version != project.version:
        raise ValueError("The current screenplay version needs owner approval")
    script = Screenplay.model_validate(project.screenplay)
    script.check_duration(spec.duration_minutes)
    version = project.version
    if job.payload.get("version") not in {None, version}:
        raise ValueError("Screenplay changed since this job was queued; create a new production job")
    folder = project_dir(project.id, version)
    (folder / "screenplay.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    text = script.title + "\n\n" + script.synopsis + "\n\n" + "\n\n".join(
        f"{s.scene_id} / {s.id} ({s.start_time}s): {s.narration}\n{s.dialogue}" for s in script.shots)
    (folder / "screenplay.txt").write_text(text, encoding="utf-8")
    comfy, speech, whisper = ComfyUI(), Speech(), Whisper()
    clips, all_segments = [], []
    warnings = []
    for index, shot in enumerate(script.shots):
        update_job(job_id, f"Shot {index + 1}/{len(script.shots)}", 10 + int(index / len(script.shots) * 75))
        # Model output IDs never become filesystem paths.
        stem = f"shot-{index:04}"
        use_video = spec.mode == "video" or (spec.mode == "hybrid" and shot.hero)
        source = folder / f"{stem}-source.{'mp4' if use_video else 'png'}"
        audio = folder / f"{stem}.wav"
        subtitles = folder / f"{stem}.srt"
        output = folder / f"{stem}.mp4"
        checkpoint = folder / f"{stem}-checkpoint.json"
        digest = fingerprint(shot, spec)
        # Reuse unchanged shots from earlier script versions; edits regenerate only changed shots.
        if not checkpoint.exists() and version > 1:
            previous = project_dir(project.id, version - 1)
            prior_checkpoint = previous / checkpoint.name
            if prior_checkpoint.exists():
                prior_state = json.loads(prior_checkpoint.read_text(encoding="utf-8"))
                if prior_state.get("fingerprint") == digest:
                    for asset_file in [source, audio, subtitles, output, checkpoint]:
                        prior_file = previous / asset_file.name
                        if prior_file.exists():
                            shutil.copy2(prior_file, asset_file)
        if checkpoint.exists():
            state = json.loads(checkpoint.read_text(encoding="utf-8"))
        else:
            state = {}
        if state.get("fingerprint") != digest:
            state = {"fingerprint": digest}
        def persist(checkpoint=checkpoint, state=state):
            checkpoint.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        if not state.get("source") or not source.exists():
            keyframe = None
            if use_video:
                keyframe = folder / f"{stem}-keyframe.png"
                if not state.get("keyframe") or not keyframe.exists():
                    comfy.generate(shot, spec, "image", keyframe, cancelled=lambda: cancelled(job_id))
                    state["keyframe"] = True
                    persist()
                    comfy.release_models()
            comfy.generate(shot, spec, "video" if use_video else "image", source,
                           cancelled=lambda: cancelled(job_id), init_image=keyframe)
            if use_video:
                probe(source)
            else:
                from PIL import Image
                with Image.open(source) as image:
                    image.verify()
            state["source"] = True
            persist()
            comfy.release_models()
        if not state.get("audio") or not audio.exists():
            spoken = " ".join(filter(None, [shot.narration, shot.dialogue]))
            for word, replacement in spec.pronunciation.items():
                spoken = spoken.replace(word, replacement)
            voice = next((c.voice for c in spec.characters if c.id == shot.speaker_id),
                         "Jaya speaks Tamil with suspense, moderate speed and very clear audio in a quiet room."
                         if spec.language == "ta" else "Thoma speaks English calmly with very clear audio in a quiet room.")
            speech.generate(spoken, spec.language, voice, audio)
            if duration(audio) > shot.duration - 0.1:
                raise ValueError(f"Shot {index+1} speech exceeds allocated duration; shorten its dialogue")
            state["audio"] = True
            persist()
            speech.release_models()
        if not state.get("segments") or not subtitles.exists():
            segments = whisper.align(audio, spec.language)
            write_subtitles(segments, subtitles, shot.duration)
            state["segments"] = segments
            persist()
        if not state.get("rendered") or not output.exists():
            render_shot(shot, source.resolve(), audio.resolve(), subtitles.resolve(), output.resolve(), use_video)
            state["rendered"] = True
            persist()
        if abs(duration(output) - shot.duration) > 0.15:
            raise ValueError(f"Shot {index+1} render has incorrect duration; clear checkpoint and retry")
        clips.append(output)
        all_segments.extend({"start": s["start"] + shot.start_time, "end": s["end"] + shot.start_time,
                             "text": s["text"]} for s in state["segments"])
        store_asset(project.id, "shot", output, {"shot_id": shot.id, "version": version,
                     "source": relative(source), "audio": relative(audio), "subtitles": relative(subtitles),
                     "is_video": use_video, "duration": shot.duration})
        if shot.sound_effects or shot.music_cue:
            warnings.append(f"Shot {index+1}: requested music/SFX are not synthesized by this release")
    update_job(job_id, "Assembling movie", 87)
    movie = folder / "movie.mp4"
    if spec.audio_tracks:
        unscored = folder / "movie-unscored.mp4"
        assemble(clips, unscored)
        mix_audio(unscored, spec.audio_tracks, movie, spec.duration_minutes * 60)
    else:
        assemble(clips, movie)
    (folder / "timeline.json").write_text(json.dumps({
        "duration": spec.duration_minutes*60, "fps": 24,
        "video": [{"shot_id": s.id, "start": s.start_time, "duration": s.duration,
                   "clip": relative(c)} for s, c in zip(script.shots, clips, strict=True)],
        "audio": [track.model_dump() for track in spec.audio_tracks],
        "subtitles": relative(folder / "movie.srt"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    subtitles = folder / "movie.srt"
    write_subtitles(all_segments, subtitles, spec.duration_minutes * 60)
    update_job(job_id, "Validating complete movie", 93)
    report = quality_report(movie, spec.duration_minutes * 60, subtitles)
    report["warnings"].extend(warnings)
    report["screenplay_version"] = version
    (folder / "quality.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["passed"]:
        raise ValueError(f"Movie failed quality gates: {report['checks']}")
    metadata = {"title": script.title, "description": "Fictionalized legend. AI-assisted synthetic media.",
                "language": spec.language, "visibility": "private", "quality": report, "version": version}
    (folder / "publishing.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    store_asset(project.id, "movie", movie, metadata)
    store_asset(project.id, "subtitles", subtitles, {"version": version})
    store_asset(project.id, "quality", folder / "quality.json", {"version": version})
    store_asset(project.id, "timeline", folder / "timeline.json", {"version": version})
    with Session.begin() as db:
        current = db.get(Project, project.id)
        if current.version != version:
            raise ValueError("Project changed during rendering; this movie is not current")
        current.status = "rendered-needs-review"
    update_job(job_id, "Creating Shorts with explicit focal points", 96)
    _shorts(project, spec, script, folder)


def _shorts(project, spec, script, folder):
    selected = choose_shorts(script, spec.shorts_count)
    if not selected:
        return []  # UI reports why there are no Shorts; never guesses every shot's center.
    generated = []
    with Session() as db:
        assets = db.scalars(select(Asset).where(Asset.project_id == project.id, Asset.kind == "shot")).all()
    for i, clip in enumerate(selected):
        shot = next(s for s in script.shots if s.id == clip["shot_id"])
        source_asset = next(a for a in assets if a.metadata_json["shot_id"] == shot.id
                            and a.metadata_json["version"] == project.version)
        meta = source_asset.metadata_json
        output = folder / f"short-{i+1}.mp4"
        # Re-render from the original source and voice, preserving full vertical captions.
        render_shot(shot, safe_path(meta["source"]), safe_path(meta["audio"]),
                    safe_path(meta["subtitles"]), output.resolve(), meta["is_video"], 1080, 1920)
        applicable = []
        for track in spec.audio_tracks:
            start = max(track.start, shot.start_time)
            end = min(track.start + track.duration, shot.start_time + shot.duration)
            if end > start:
                applicable.append(track.model_copy(update={"start": start-shot.start_time,
                    "trim_start": track.trim_start+start-track.start, "duration": end-start}))
        if applicable:
            raw = folder / f"short-{i+1}-unscored.mp4"
            output.replace(raw)
            mix_audio(raw, applicable, output, shot.duration)
        streams = probe(output)["streams"]
        v = next(s for s in streams if s["codec_type"] == "video")
        if (v["width"], v["height"]) != (1080, 1920):
            raise ValueError("Short failed vertical resolution check")
        asset_id = store_asset(project.id, "short", output, {**clip, "parent": relative(folder / "movie.mp4"),
                                                              "version": project.version})
        generated.append(asset_id)
    return generated


def shorts_job(job_id):
    _, project, spec = inputs(job_id)
    script = Screenplay.model_validate(project.screenplay)
    folder = project_dir(project.id, project.version)
    if not (folder / "movie.mp4").exists():
        raise ValueError("Render the parent movie first")
    update_job(job_id, "Rendering ranked vertical Shorts", 10)
    if not _shorts(project, spec, script, folder):
        raise ValueError("Set crop_x focal positions for at least one shot in the storyboard")
