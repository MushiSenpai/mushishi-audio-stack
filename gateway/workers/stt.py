import whisperx, json, os

# faster-whisper needs CTranslate2 format; point directly at converted model.bin
# Converted from HF safetensors via: docker exec creative-audio-worker ct2-transformers-converter ...
WHISPER_MODEL  = "/data/ai/07-cache/torch/faster-whisper-large-v3-turbo"
WHISPER_CACHE  = "/data/ai/07-cache/torch"
OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio"
os.environ.setdefault("TORCH_HOME", "/data/ai/07-cache/torch")

_model = None

def _get_model():
    global _model
    if _model is None:
        _model = whisperx.load_model(
            WHISPER_MODEL, device="cuda", compute_type="float16"
        )
    return _model

def transcribe(job_id: str, source: str, language: str = None,
               quality: str = "production", **kwargs) -> dict:
    model = _get_model()
    audio = whisperx.load_audio(source)
    result = model.transcribe(audio, batch_size=16, language=language)
    detected_lang = result.get("language", language or "en")

    if quality == "draft":
        out = {"job_id": job_id, "language": detected_lang, "segments": result["segments"],
               "word_timings": None, "transcript": " ".join(s["text"] for s in result["segments"])}
    else:
        align_model, metadata = whisperx.load_align_model(detected_lang, device="cuda",
                                                           model_dir="/data/ai/07-cache/torch")
        aligned = whisperx.align(result["segments"], align_model, metadata, audio, "cuda")
        word_timings = [
            {"word": w["word"], "start": w["start"], "end": w["end"]}
            for seg in aligned["segments"] for w in seg.get("words", [])
        ]
        out = {"job_id": job_id, "language": detected_lang,
               "segments": aligned["segments"], "word_timings": word_timings,
               "transcript": " ".join(w["word"] for w in word_timings)}

    out_path = f"{OUTPUT_DIR}/voiceover/{job_id}_transcript.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    return {"job_id": job_id, "output_file": out_path, "language": detected_lang}
