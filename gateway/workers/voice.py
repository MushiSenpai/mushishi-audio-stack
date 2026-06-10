import requests, os, shutil, subprocess

TTS_API    = "http://creative-tts:9002"
OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio/voiceover"
VOICE_DIR  = "/data/ai/02-models/audio/voices"
CLEAN_DIR  = "/data/ai/03-data/audio/voice-clean"
os.environ.setdefault("TORCH_HOME", "/data/ai/07-cache/torch")

def synthesise(job_id: str, text: str, language: str = "en",
               voice_profile: str = None, speed: float = 1.0, **kwargs) -> dict:
    if not text:
        return {"error": "text is required for tts job"}
    payload = {"text": text, "language": language, "speed": speed, "format": "wav"}
    if voice_profile:
        payload["reference_audio"] = f"{VOICE_DIR}/{voice_profile}.wav"
    resp = requests.post(f"{TTS_API}/v1/tts", json=payload, timeout=120)
    resp.raise_for_status()
    out_path = f"{OUTPUT_DIR}/{job_id}_speech.wav"
    with open(out_path, "wb") as f:
        f.write(resp.content)
    return {"job_id": job_id, "output_file": out_path}

def clone_voice(job_id: str, voice_ref: str, profile_name: str = None, **kwargs) -> dict:
    if not profile_name:
        profile_name = job_id
    # Run Demucs to clean the sample first
    result = subprocess.run([
        "demucs", "--two-stems", "vocals",
        "--out", CLEAN_DIR,
        voice_ref
    ], capture_output=True, text=True, timeout=300)

    base = os.path.splitext(os.path.basename(voice_ref))[0]
    clean_path = f"{CLEAN_DIR}/htdemucs/{base}/vocals.wav"

    if not os.path.exists(clean_path):
        # If Demucs output layout differs, fall back to raw reference
        clean_path = voice_ref

    profile_path = f"{VOICE_DIR}/{profile_name}.wav"
    shutil.copy(clean_path, profile_path)
    return {
        "job_id": job_id,
        "profile_name": profile_name,
        "profile_path": profile_path,
        "demucs_log": result.stderr[-500:] if result.stderr else "",
    }
