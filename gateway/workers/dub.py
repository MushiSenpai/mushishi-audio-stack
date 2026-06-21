import whisperx, requests, json, os, subprocess

WHISPER_MODEL = "/data/ai/07-cache/torch/faster-whisper-large-v3-turbo"
WHISPER_CACHE = "/data/ai/07-cache/torch"
OUTPUT_DIR    = "/data/ai/08-portfolio/outputs/audio/dubbing"
LITELLM_API   = "http://172.17.0.1:4000/v1"             # host LiteLLM (0.0.0.0:4000) -> LOCAL Nemotron (sovereign)
LITELLM_MODEL = "personal-chain-cpu"                    # always-on CPU Nemotron via LiteLLM
VLLM_API      = "http://host.docker.internal:8000/v1"   # Nemotron GPU (direct fallback)
CPU_API       = "http://host.docker.internal:8001/v1"   # Nemotron CPU (direct fallback)
TTS_API       = "http://creative-tts:9002"
os.environ.setdefault("TORCH_HOME", "/data/ai/07-cache/torch")

def _translate(text: str, src_lang: str, tgt_lang: str, duration: float, wpm: float) -> str:
    prompt = (
        f"Translate the following {src_lang} text to {tgt_lang}.\n\n"
        f"Source speech rate: {wpm:.0f} words/minute over {duration:.1f} seconds.\n"
        f"Target: produce a translation speakable in approximately {duration:.1f} seconds.\n"
        f"Adjust verbosity to match the time window. Output ONLY the translation.\n\n"
        f"Text: {text}"
    )
    # Primary: LiteLLM -> LOCAL Nemotron (sovereign). The key is injected via the worker's
    # env (LITELLM_KEY), never the repo. "detailed thinking off" keeps the reasoning model's
    # answer in `content` instead of overrunning the budget in the reasoning channel.
    sys_msg = "detailed thinking off\nYou are a precise translator. Output ONLY the translation — no notes, no preamble."
    key = os.environ.get("LITELLM_KEY", "")
    attempts = []
    if key:
        attempts.append((LITELLM_API, LITELLM_MODEL, {"Authorization": f"Bearer {key}"}))
    attempts.append((VLLM_API, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", {}))
    attempts.append((CPU_API, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning", {}))
    for api_url, model, headers in attempts:
        try:
            resp = requests.post(f"{api_url}/chat/completions", json={
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 1800, "temperature": 0.3,
            }, headers=headers, timeout=120)
            if resp.status_code == 200:
                content = (resp.json()["choices"][0]["message"].get("content") or "").strip()
                if content:
                    return content
        except Exception:
            continue
    raise RuntimeError("Translation failed: no reachable LLM (LiteLLM + direct Nemotron all failed/empty)")

def _write_srt(word_timings: list, translated_text: str, out_path: str):
    lines = translated_text.split()
    chunk_size = 7
    chunks = [lines[i:i+chunk_size] for i in range(0, len(lines), chunk_size)]
    duration_per = word_timings[-1]["end"] / max(len(chunks), 1) if word_timings else 3.0
    def srt_time(s):
        h,m,sec,ms = int(s//3600), int((s%3600)//60), int(s%60), int((s%1)*1000)
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
    with open(out_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            f.write(f"{i+1}\n{srt_time(i*duration_per)} --> {srt_time((i+1)*duration_per)}\n")
            f.write(" ".join(chunk) + "\n\n")

def auto_dub(job_id: str, source: str, language: str,
             voice_profile: str = None, approach: str = "audio_first",
             quality: str = "production", **kwargs) -> dict:
    work_dir = f"/data/ai/03-data/audio/dub-projects/{job_id}"
    os.makedirs(work_dir, exist_ok=True)

    audio_path = f"{work_dir}/original_audio.wav"
    subprocess.run(["ffmpeg", "-i", source, "-vn", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1", audio_path, "-y"], check=True)

    model = whisperx.load_model(WHISPER_MODEL, device="cuda", compute_type="float16")
    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, batch_size=16)
    src_lang = result["language"]

    try:
        align_model, metadata = whisperx.load_align_model(src_lang, device="cuda",
                                                           model_dir="/data/ai/07-cache/torch")
        aligned = whisperx.align(result["segments"], align_model, metadata, audio, "cuda")
        word_timings = [
            {"word": w["word"], "start": w["start"], "end": w["end"]}
            for seg in aligned["segments"] for w in seg.get("words", [])
        ]
    except Exception:
        word_timings = []

    # Fallback: build word_timings from segment-level data if alignment produced nothing
    if not word_timings:
        for seg in result["segments"]:
            words = seg.get("text", "").split()
            if not words:
                continue
            dur = (seg["end"] - seg["start"]) / max(len(words), 1)
            for i, w in enumerate(words):
                word_timings.append({"word": w, "start": seg["start"] + i*dur, "end": seg["start"] + (i+1)*dur})

    total_dur = word_timings[-1]["end"] if word_timings else 60.0
    source_text = " ".join(w["word"] for w in word_timings)
    wpm = len(word_timings) / (total_dur / 60) if total_dur > 0 else 120

    # Skip LLM translation when source and target language match
    if src_lang == language or (language and src_lang.startswith(language[:2])):
        translated = source_text
    else:
        translated = _translate(source_text, src_lang, language, total_dur, wpm)

    tgt_wpm = len(translated.split()) / (total_dur / 60)
    speed = min(1.3, max(0.7, wpm / max(tgt_wpm, 1)))

    tts_payload = {"text": translated, "language": language, "speed": speed, "format": "wav"}
    if voice_profile:
        tts_payload["reference_audio"] = f"/data/ai/02-models/audio/voices/{voice_profile}.wav"
    tts_resp = requests.post(f"{TTS_API}/v1/tts", json=tts_payload, timeout=120)
    tts_resp.raise_for_status()
    dubbed_audio = f"{work_dir}/dubbed_audio.wav"
    with open(dubbed_audio, "wb") as f:
        f.write(tts_resp.content)

    srt_path = f"{work_dir}/subtitles_{language}.srt"
    _write_srt(word_timings, translated, srt_path)

    if approach == "video_locked":
        out_video = f"{OUTPUT_DIR}/{job_id}_dubbed_{language}.mp4"
        subprocess.run(["ffmpeg", "-i", source, "-i", dubbed_audio,
                        "-c:v", "copy", "-c:a", "aac",
                        "-map", "0:v:0", "-map", "1:a:0", "-shortest", out_video, "-y"], check=True)
        return {"job_id": job_id, "approach": "video_locked", "dubbed_video": out_video,
                "subtitles": srt_path, "translated_text": translated,
                "tts_speed": speed, "source_duration": total_dur}
    else:
        analysis = {
            "job_id": job_id, "approach": "audio_first",
            "dubbed_audio": dubbed_audio, "subtitles": srt_path,
            "translated_text": translated, "language": language,
            "speech_rate_wpm": round(tgt_wpm, 1),
            "total_duration_seconds": round(total_dur, 1),
            "word_timings": word_timings,
            "video_generation_notes": (
                f"Generate {total_dur:.0f}s video. "
                f"Character speaks {tgt_wpm:.0f} wpm. "
                f"Sync lip movement to dubbed_audio track."
            )
        }
        analysis_path = f"{work_dir}/dub_analysis.json"
        with open(analysis_path, "w") as f:
            json.dump(analysis, f, indent=2)
        return analysis
