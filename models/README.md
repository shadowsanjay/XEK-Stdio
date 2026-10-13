# Model prerequisites

Run Ollama and pull a model with Tamil and structured-output support; default is `qwen3:8b`.
Tamil fluency and screenplay validity require human review. Larger models may improve results
at a higher RAM/VRAM cost. Set OLLAMA_MODEL to an installed model.

Install ComfyUI separately and follow [INSTALL.md](INSTALL.md) for FLUX.1-schnell GGUF defaults. CPU image
generation can work for some models but is slow. Wan/LTX video requires a compatible workflow and
hardware appropriate to the exact variant, resolution and clip duration. No fixed GPU-memory
promise is made. The studio reports unavailable models instead of producing fake footage.

Optional Tamil speech service:
```
pip install -e '.[speech]'
uvicorn services.speech.server:app --host 127.0.0.1 --port 8001
```
The first call downloads Indic Parler-TTS. Review its model card and speaker descriptions:
https://huggingface.co/ai4bharat/indic-parler-tts . Tamil is supported by the model card, but this
integration still needs live verification. Use a Tamil-supported speaker description. CPU inference
can be slow. No voice-cloning API is exposed.

Install `.[transcription]` for local Whisper (included in Docker); first call downloads weights.
Install Noto Sans Tamil. FFmpeg must include libass, libx264, AAC and ffprobe.
Use a firewall/trusted private network for model endpoints; they have no product authentication.
