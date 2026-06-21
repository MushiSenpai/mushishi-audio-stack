"""Tiny FastAPI service wrapping Hallo2 cinematic lip-sync (portrait/half-body + audio -> mp4).

Runs in the dedicated, pinned `mushishi-hallo2` container (see
06-configs/audio/Dockerfile.hallo2). The audio worker's lipsync.py hallo2 branch
calls POST /lipsync by service name, exactly like its museTalk branch calls
creative-musetalk:9005. This is the cinematic tier (head pose + expression +
CodeFormer face enhancement) — the capability MuseTalk doesn't have.

Design mirrors musetalk_server.py: each job runs `scripts/inference_long.py` as a
subprocess with a per-job OmegaConf config. Models load per job and VRAM frees when
the job ends — the correct citizen on a single shared RTX 5090 (the service holds NO
VRAM while idle). The pinned env (diffusers 0.32.2 + decorator<5) is baked into the
image so the working YuE+Fish+MuseTalk stack is never touched. Created 2026-06-22.
"""
import os
import glob
import shutil
import time
import subprocess

from fastapi import FastAPI
from pydantic import BaseModel
from omegaconf import OmegaConf

WORKSPACE = "/data/ai/01-workspace/audio/hallo2"
MODEL_BASE = "/data/ai/02-models/audio"
OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio/lip-sync"
TEMPLATE = f"{WORKSPACE}/configs/inference/long.yaml"
JOB_TIMEOUT = 1800  # 30 min hard cap

app = FastAPI(title="mushishi-hallo2", version="2.0")


class LipsyncReq(BaseModel):
    job_id: str
    source: str       # portrait/half-body image (absolute path in the shared mounts)
    audio_file: str   # wav path (absolute)


@app.get("/health")
def health():
    return {"status": "ok", "model": "hallo2", "grade": "cinematic"}


@app.post("/lipsync")
def lipsync(req: LipsyncReq):
    if not os.path.exists(req.source):
        return {"error": f"source not found: {req.source}", "model_used": "hallo2"}
    if not os.path.exists(req.audio_file):
        return {"error": f"audio_file not found: {req.audio_file}", "model_used": "hallo2"}

    work = os.path.join(OUTPUT_DIR, f"{req.job_id}_hallo2_work")
    cache = f"/tmp/{req.job_id}_hallo2_cache"
    os.makedirs(work, exist_ok=True)

    # Per-job config: load the repo template, override only the path keys. The other
    # paths in the template (motion_module, vae, wav2vec, face_analysis, audio_separator)
    # stay relative ./pretrained_models/... and resolve via cwd=WORKSPACE + the
    # pretrained_models symlink -> /data/ai/02-models/audio/hallo2.
    cfg = OmegaConf.load(TEMPLATE)
    cfg.source_image = req.source
    cfg.driving_audio = req.audio_file
    cfg.save_path = work
    cfg.cache_path = cache
    cfg.audio_ckpt_dir = f"{MODEL_BASE}/hallo2/hallo2"
    cfg.base_model_path = f"{MODEL_BASE}/hallo2/stable-diffusion-v1-5"
    cfg_path = f"/tmp/{req.job_id}_hallo2.yaml"
    OmegaConf.save(cfg, cfg_path)

    cmd = ["python3", f"{WORKSPACE}/scripts/inference_long.py", "--config", cfg_path]
    env = os.environ.copy()
    env["PYTHONPATH"] = WORKSPACE
    env["TORCH_HOME"] = "/data/ai/07-cache/torch"

    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=JOB_TIMEOUT, cwd=WORKSPACE, env=env)
    except subprocess.TimeoutExpired:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(cache, ignore_errors=True)
        if os.path.exists(cfg_path):
            os.remove(cfg_path)
        return {"error": f"inference timed out after {JOB_TIMEOUT}s", "model_used": "hallo2"}
    wall = round(time.time() - t0, 1)

    # inference_long.py writes merge_video.mp4 at {save_path}/{source_stem}/merge_video.mp4.
    cands = glob.glob(os.path.join(work, "**", "merge_video.mp4"), recursive=True)
    if not cands:
        err = (r.stderr or r.stdout or "no output produced")[-2000:]
        shutil.rmtree(cache, ignore_errors=True)
        if os.path.exists(cfg_path):
            os.remove(cfg_path)
        return {"error": err, "model_used": "hallo2", "wall_seconds": wall}

    out = os.path.join(OUTPUT_DIR, f"{req.job_id}_lipsync.mp4")
    os.replace(cands[0], out)
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(cache, ignore_errors=True)
    if os.path.exists(cfg_path):
        os.remove(cfg_path)

    return {"job_id": req.job_id, "output_file": out,
            "model_used": "hallo2", "wall_seconds": wall}
