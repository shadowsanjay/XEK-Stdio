"""Optional real local Indic Parler-TTS service. Install with .[speech]."""
import io
import os
import threading
import gc

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="XEK Local Speech")
lock = threading.Lock()
model = tokenizer = description_tokenizer = None


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str = Field(pattern="^(ta|en)$")
    voice_description: str = Field(default="Jaya speaks Tamil calmly with suspense and very clear audio, in a quiet room.", max_length=1000)


def load():
    global model, tokenizer, description_tokenizer
    if model is None:
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer
        model_id = os.getenv("TTS_MODEL", "ai4bharat/indic-parler-tts")
        auto_gpu = torch.cuda.is_available() and torch.cuda.get_device_properties(0).total_memory >= 6 * 1024**3
        device = os.getenv("TTS_DEVICE", "cuda" if auto_gpu else "cpu")
        model = ParlerTTSForConditionalGeneration.from_pretrained(model_id).to(device)
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        description_tokenizer = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)


@app.get("/health")
def health():
    return {"status": "ready" if model is not None else "not-loaded", "languages": ["ta", "en"],
            "model": os.getenv("TTS_MODEL", "ai4bharat/indic-parler-tts")}


@app.post("/synthesize")
def synthesize(body: SpeechRequest):
    import soundfile as sf
    import torch
    with lock:
        try:
            load()
            description = description_tokenizer(body.voice_description, return_tensors="pt").to(model.device)
            prompt = tokenizer(body.text, return_tensors="pt").to(model.device)
            with torch.inference_mode():
                generated = model.generate(input_ids=description.input_ids,
                                           attention_mask=description.attention_mask,
                                           prompt_input_ids=prompt.input_ids,
                                           prompt_attention_mask=prompt.attention_mask)
            buffer = io.BytesIO()
            sf.write(buffer, generated.cpu().numpy().squeeze(), model.config.sampling_rate, format="WAV")
            return Response(buffer.getvalue(), media_type="audio/wav")
        except Exception:
            raise HTTPException(503, "Speech inference failed; inspect speech service logs and model setup") from None


@app.post("/unload")
def unload():
    global model, tokenizer, description_tokenizer
    with lock:
        model = tokenizer = description_tokenizer = None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    return {"unloaded": True}
