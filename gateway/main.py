from fastapi import FastAPI, UploadFile, Form, File
from fastapi.responses import JSONResponse
import shutil, uuid, os
from queue_client import submit_job, get_job_status, q_stt, q_voice, q_lipsync, q_music, q_dub
from intent_router import MODEL_TIERS, ROUTES

app = FastAPI(title="Mushishi Audio Gateway", version="1.0")
UPLOAD_DIR = "/data/ai/03-data/audio"

@app.post("/audio/job")
async def submit_audio_job(
    job_type:    str = Form(...),
    quality:     str = Form("production"),
    model_tier:  str = Form(None),
    language:    str = Form("en"),
    text:        str = Form(None),
    lyrics:      str = Form(None),
    profile_name:  str = Form(None),
    voice_profile: str = Form(None),
    source_file: UploadFile = File(None),
    audio_file:  UploadFile = File(None),
    voice_ref:   UploadFile = File(None),
    approach:    str = Form("audio_first"),
    webhook_url: str = Form(None),
):
    job_id = str(uuid.uuid4())[:8]
    saved = {}

    if source_file:
        path = f"{UPLOAD_DIR}/dub-projects/{job_id}_source{os.path.splitext(source_file.filename)[1]}"
        with open(path, "wb") as f:
            shutil.copyfileobj(source_file.file, f)
        saved["source"] = path

    if audio_file:
        path = f"{UPLOAD_DIR}/dub-projects/{job_id}_audio{os.path.splitext(audio_file.filename)[1]}"
        with open(path, "wb") as f:
            shutil.copyfileobj(audio_file.file, f)
        saved["audio_file"] = path

    if voice_ref:
        path = f"{UPLOAD_DIR}/voice-samples/{job_id}_ref{os.path.splitext(voice_ref.filename)[1]}"
        with open(path, "wb") as f:
            shutil.copyfileobj(voice_ref.file, f)
        saved["voice_ref"] = path

    if job_type not in ROUTES:
        return JSONResponse({"error": f"Unknown job_type: {job_type}"}, status_code=400)

    queues = {"q_stt": q_stt, "q_voice": q_voice, "q_lipsync": q_lipsync, "q_music": q_music, "q_dub": q_dub}
    q_name, func, timeout = ROUTES[job_type]
    queue = queues[q_name]

    kwargs = {
        "job_id": job_id,
        "quality": quality,
        "language": language,
        "text": text,
        "lyrics": lyrics,
        "profile_name": profile_name,
        "voice_profile": voice_profile,
        "approach": approach,
        "webhook_url": webhook_url,
        "model_tier": model_tier or MODEL_TIERS.get(job_type, {}).get(quality, "production"),
        **saved
    }

    rq_job_id = submit_job(queue, func, kwargs, timeout)
    return {"job_id": rq_job_id, "status": "queued", "type": job_type, "quality": quality}

@app.get("/audio/status/{job_id}")
async def job_status(job_id: str):
    return get_job_status(job_id)

@app.get("/audio/health")
async def health():
    return {"status": "ok", "service": "mushishi-audio-gateway"}
