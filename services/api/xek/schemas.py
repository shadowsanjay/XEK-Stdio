from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def new_id():
    return str(uuid4())


class Character(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str = Field(min_length=1, max_length=100)
    visual_description: str = Field(default="", max_length=4000)
    costume: str = ""
    proportions: str = ""
    facial_features: str = ""
    movement: str = ""
    voice: str = "A clear, expressive narrator with a low, calm voice."
    personality: str = ""
    visual_style: str = ""
    canonical_prompt: str = ""
    negative_prompt: str = ""
    reference_assets: list[str] = Field(default_factory=list)
    seed: int = Field(default=42, ge=0, le=2**63 - 1)


class AudioTrack(BaseModel):
    asset_path: str
    kind: Literal["music", "sound-effects", "ambience"]
    start: float = Field(ge=0)
    trim_start: float = Field(default=0, ge=0)
    duration: float = Field(gt=0)
    gain: float = Field(default=0.25, ge=0, le=2)
    fade: float = Field(default=0.5, ge=0, le=10)
    duck_under_speech: bool = True
    license_note: str = Field(min_length=3, max_length=1000)


class CreateProject(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=10, max_length=40000)
    duration_minutes: Literal[1, 3, 5, 10, 15, 20, 30] = 1
    language: Literal["ta", "en"] = "ta"
    genre: str = Field(default="Supernatural horror", max_length=200)
    style: str = Field(default="Dark cinematic horror comic", max_length=200)
    audience: str = "Adults"
    pacing: str = "Suspenseful"
    ending: str = "A frightening reveal"
    horror_intensity: int = Field(default=3, ge=0, le=5)
    universe: Literal["original", "xek"] = "xek"
    mode: Literal["motion-comic", "video", "hybrid"] = "motion-comic"
    production_mode: Literal["manual", "assisted", "automatic"] = "assisted"
    characters: list[Character] = Field(default_factory=list, max_length=30)
    pronunciation: dict[str, str] = Field(default_factory=dict)
    audio_tracks: list[AudioTrack] = Field(default_factory=list, max_length=50)
    shorts_count: int = Field(default=4, ge=1, le=12)


class Shot(BaseModel):
    id: str = Field(default_factory=new_id)
    scene_id: str
    start_time: float = Field(ge=0)
    duration: float = Field(gt=0, le=30)
    location_id: str
    character_ids: list[str] = Field(default_factory=list)
    visual_prompt: str = Field(min_length=5, max_length=6000)
    negative_prompt: str = "text, watermark, low quality"
    camera_type: str = "wide"
    camera_movement: Literal["zoom-in", "zoom-out", "pan-left", "pan-right", "static"] = "zoom-in"
    lighting: str = ""
    mood: str = ""
    dialogue: str = ""
    narration: str = ""
    speaker_id: str = "narrator"
    sound_effects: list[str] = Field(default_factory=list)
    music_cue: str = ""
    reference_assets: list[str] = Field(default_factory=list)
    seed: int = Field(default=42, ge=0, le=2**63 - 1)
    hero: bool = False
    hook_score: float = Field(default=0.5, ge=0, le=1)
    crop_x: float | None = Field(default=None, ge=0, le=1)
    generation_status: str = "pending"
    generated_asset_path: str | None = None


class Screenplay(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    synopsis: str
    acts: list[str] = Field(min_length=3, max_length=3)
    character_arcs: dict[str, str] = Field(default_factory=dict)
    legend_notes: dict[str, str] = Field(default_factory=dict)
    shots: list[Shot] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def timeline(self):
        cursor = 0.0
        ids = set()
        for shot in self.shots:
            if shot.id in ids:
                raise ValueError("Shot IDs must be unique")
            ids.add(shot.id)
            if abs(shot.start_time - cursor) > 0.1:
                raise ValueError("Shots must form a contiguous, ordered timeline")
            cursor += shot.duration
        return self

    def check_duration(self, minutes: int):
        duration = sum(s.duration for s in self.shots)
        if abs(duration - minutes * 60) > 1:
            raise ValueError(f"Storyboard duration {duration}s does not match {minutes * 60}s target")


class PublishRequest(BaseModel):
    asset_id: str
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="Fictionalized story. AI-assisted synthetic visuals and narration.", max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    visibility: Literal["private", "unlisted", "public"] = "private"
    publish_at: str | None = None
    owner_approved: Literal[True]
    contains_synthetic_media: bool = True
