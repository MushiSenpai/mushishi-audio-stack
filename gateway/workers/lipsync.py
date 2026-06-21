# Lip-sync tiers:
#   museTalk   (draft/social-grade) -> dedicated creative-musetalk:9005 service.
#              Its env (DWPose via rtmlib/ONNX, no mmcv) is isolated in the
#              mushishi-musetalk image so it can't break the YuE+Fish worker.
#   hallo2     (cinematic-grade)    -> dedicated creative-hallo2:9006 service.
#              Its env (diffusers 0.32.2 + decorator<5) is isolated in the
#              mushishi-hallo2 image — see audio/hallo2-rebuild-spec.md.
#   latentsync (default)            -> still runs inline in this worker.
# (Both MuseTalk's mmcv path and Hallo2's inline diffusers path broke in the
#  consolidated worker env; each rebuilt as a separate pinned service.)
import subprocess, os

MUSETALK_API = "http://creative-musetalk:9005"
HALLO2_API   = "http://creative-hallo2:9006"

MODEL_BASE = "/data/ai/02-models/audio"
WORKSPACE  = "/data/ai/01-workspace/audio"
OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio/lip-sync"


def _call_lipsync_service(api: str, model: str, job_id: str, source: str, audio_file: str) -> dict:
    """POST to a dedicated, isolated lip-sync service (musetalk/hallo2) by name, like
    voice.py calls creative-tts. Each service loads models per job and frees VRAM on
    exit, so a job can take a few minutes — generous timeout."""
    import requests
    try:
        resp = requests.post(
            f"{api}/lipsync",
            json={"job_id": job_id, "source": source, "audio_file": audio_file},
            timeout=1900,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": f"{model} service call failed: {e}", "model_used": model}
    if "error" in data:
        return {"error": data["error"], "model_used": model}
    return {"job_id": job_id, "output_file": data.get("output_file"),
            "model_used": model, "wall_seconds": data.get("wall_seconds")}


def generate(job_id: str, source: str = None, audio_file: str = None,
             model_tier: str = "latentsync", **kwargs) -> dict:
    if not source or not audio_file:
        return {"error": "source (image/video) and audio_file are required for lipsync"}

    out_path = f"{OUTPUT_DIR}/{job_id}_lipsync.mp4"

    # Dedicated, isolated services (mushishi-musetalk / mushishi-hallo2). The inline
    # paths for both broke in the consolidated worker env; each is now its own pinned
    # image behind a tiny FastAPI service the worker HTTP-calls.
    if model_tier == "museTalk":
        return _call_lipsync_service(MUSETALK_API, "museTalk", job_id, source, audio_file)
    if model_tier == "hallo2":
        return _call_lipsync_service(HALLO2_API, "hallo2", job_id, source, audio_file)

    # latentsync still runs inline in this worker.
    if model_tier == "latentsync":
        guidance = "1.0" if kwargs.get("quality") == "draft" else "1.5"
        cmd = [
            "python3", "-m", "scripts.inference",
            "--unet_config_path",    "configs/unet/stage2_512.yaml",
            "--inference_ckpt_path", f"{MODEL_BASE}/latentsync/latentsync_unet.pt",
            "--guidance_scale", guidance,
            "--enable_deepcache",
            "--video_path", source,
            "--audio_path", audio_file,
            "--video_out_path", out_path,
        ]
    else:
        return {"error": f"Unknown model_tier: {model_tier}. Use museTalk, latentsync, or hallo2."}

    cwd = f"{WORKSPACE}/latentsync"
    env = os.environ.copy()
    env["PYTHONPATH"] = cwd
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, cwd=cwd, env=env)
    if result.returncode != 0:
        return {"error": result.stderr[-2000:], "model_used": model_tier}

    return {"job_id": job_id, "output_file": out_path, "model_used": model_tier}
