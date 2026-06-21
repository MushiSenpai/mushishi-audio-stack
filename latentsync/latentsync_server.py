"""Tiny FastAPI service wrapping LatentSync 1.6 inference (portrait/video + audio -> 512x512 mp4).

Runs in the dedicated, pinned `mushishi-latentsync` container (see
06-configs/audio/Dockerfile.latentsync). The audio worker's lipsync.py latentsync
branch calls POST /lipsync by service name, exactly like it calls creative-musetalk
(:9005) and creative-hallo2 (:9006).

Design (mirrors musetalk_server.py / hallo2_server.py): each job runs LatentSync's
`scripts/inference.py` as a subprocess. The model is loaded per job and the VRAM is
released when the job ends — the correct citizen on a single shared RTX 5090 (the
service holds NO VRAM while idle).

LatentSync 1.6 specifics:
  - checkpoint: /data/ai/02-models/audio/latentsync-1.6/latentsync_unet.pt (absolute).
  - config:     configs/unet/stage2_512.yaml (resolution: 512). Per the 1.6 model
                card, 1.6 is a checkpoint swap on this exact config.
  - whisper tiny.pt + insightface buffalo_l (face detection) resolve via the repo
    `checkpoints` symlink -> the 1.5 weights dir (byte-identical assets).
  - VAE stabilityai/sd-vae-ft-mse resolves from the pre-warmed shared HF cache
    (HF_HOME=/data/ai/07-cache/huggingface, mounted).
Created 2026-06-22.
"""
import os
import shutil
import time
import subprocess

from fastapi import FastAPI
from pydantic import BaseModel

WORKSPACE = "/data/ai/01-workspace/audio/latentsync"
UNET_CKPT = "/data/ai/02-models/audio/latentsync-1.6/latentsync_unet.pt"
UNET_CONFIG = "configs/unet/stage2_512.yaml"
OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio/lip-sync"
JOB_TIMEOUT = 1800  # 30 min hard cap

app = FastAPI(title="mushishi-latentsync", version="1.6")


class LipsyncReq(BaseModel):
    job_id: str
    source: str            # portrait image OR driving video (absolute path in the shared mounts)
    audio_file: str        # wav path (absolute)
    guidance_scale: float = 1.5   # production default; 1.0 = draft
    inference_steps: int = 20
    enable_deepcache: bool = True
    seed: int = 1247       # deterministic by default (clean A/B vs MuseTalk / 1.5)


@app.get("/health")
def health():
    return {"status": "ok", "model": "latentsync-1.6", "grade": "social", "resolution": 512}


@app.post("/lipsync")
def lipsync(req: LipsyncReq):
    if not os.path.exists(req.source):
        return {"error": f"source not found: {req.source}"}
    if not os.path.exists(req.audio_file):
        return {"error": f"audio_file not found: {req.audio_file}"}
    if not os.path.exists(UNET_CKPT):
        return {"error": f"1.6 checkpoint missing: {UNET_CKPT}", "model_used": "latentsync"}

    out = os.path.join(OUTPUT_DIR, f"{req.job_id}_lipsync.mp4")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Per-job temp dir so concurrent jobs can't collide (inference.py defaults to ./temp).
    temp_dir = os.path.join(OUTPUT_DIR, f"{req.job_id}_latentsync_tmp")
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)

    cmd = [
        "python3", "-m", "scripts.inference",
        "--unet_config_path",    UNET_CONFIG,
        "--inference_ckpt_path", UNET_CKPT,
        "--guidance_scale",      str(req.guidance_scale),
        "--inference_steps",     str(req.inference_steps),
        "--seed",                str(req.seed),
        "--video_path",          req.source,
        "--audio_path",          req.audio_file,
        "--video_out_path",      out,
        "--temp_dir",            temp_dir,
    ]
    if req.enable_deepcache:
        cmd.append("--enable_deepcache")

    env = os.environ.copy()
    env["PYTHONPATH"] = WORKSPACE
    env["TORCH_HOME"] = "/data/ai/07-cache/torch"
    env["HF_HOME"] = "/data/ai/07-cache/huggingface"

    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=JOB_TIMEOUT, cwd=WORKSPACE, env=env)
    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {"error": f"inference timed out after {JOB_TIMEOUT}s", "model_used": "latentsync"}
    wall = round(time.time() - t0, 1)
    shutil.rmtree(temp_dir, ignore_errors=True)

    if not os.path.exists(out):
        return {"error": (r.stderr or r.stdout or "no output produced")[-2000:],
                "model_used": "latentsync", "wall_seconds": wall}

    return {"job_id": req.job_id, "output_file": out,
            "model_used": "latentsync-1.6", "wall_seconds": wall}
