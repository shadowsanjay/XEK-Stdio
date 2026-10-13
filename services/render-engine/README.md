The renderer is `services/api/xek/media.py`; orchestration is `pipeline.py`.
FFmpeg executes argument lists without a shell. Every completed shot has a version-scoped
checkpoint. Narration cannot exceed shot duration. Subtitle timing is validated before rendering.
The release supports video, narration and subtitle tracks, camera movement and normalization.
Advanced music/SFX/overlay tracks and transitions are not yet supported in the editor.
