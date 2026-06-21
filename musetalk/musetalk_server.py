"""Tiny FastAPI service wrapping MuseTalk 1.5 inference (portrait/video + audio -> mp4).

Runs in the dedicated, pinned `mushishi-musetalk` container (see
06-configs/audio/Dockerfile.musetalk). The audio worker's lipsync.py museTalk
branch calls POST /lipsync by service name, exactly like it calls creative-tts.

Design: each job runs `scripts/inference.py` as a subprocess. Models are loaded
per job and the VRAM is released when the job ends — the correct citizen on a
single shared RTX 5090 (the service holds NO VRAM while idle). Created 2026-06-21.
"""
import os
import glob
import shutil
import time
import subprocess

from fastapi import FastAPI
from pydantic import BaseModel

WORKSPACE = "/data/ai/01-workspace/audio/museTalk"
MODEL_BASE = "/data/ai/02-models/audio"
OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio/lip-sync"
JOB_TIMEOUT = 1800  # 30 min hard cap

app = FastAPI(title="mushishi-musetalk", version="1.5")


class LipsyncReq(BaseModel):
    job_id: str
    source: str       # portrait image OR driving video (absolute path in the shared mounts)
    audio_file: str   # wav path (absolute)
    extra_margin: int = 10
    parsing_mode: str = "jaw"


@app.get("/health")
def health():
    return {"status": "ok", "model": "museTalk-v15", "grade": "social"}


@app.post("/lipsync")
def lipsync(req: LipsyncReq):
    if not os.path.exists(req.source):
        return {"error": f"source not found: {req.source}"}
    if not os.path.exists(req.audio_file):
        return {"error": f"audio_file not found: {req.audio_file}"}

    work = os.path.join(OUTPUT_DIR, f"{req.job_id}_musetalk")
    os.makedirs(work, exist_ok=True)

    # OmegaConf reads plain YAML; write it without a pyyaml dependency.
    cfg_path = f"/tmp/{req.job_id}_musetalk.yaml"
    with open(cfg_path, "w") as f:
        f.write(f'task_0:\n  video_path: "{req.source}"\n  audio_path: "{req.audio_file}"\n')

    cmd = [
        "python3", f"{WORKSPACE}/scripts/inference.py",
        "--unet_model_path",  f"{MODEL_BASE}/museTalk/musetalkV15/unet.pth",
        "--unet_config",      f"{MODEL_BASE}/museTalk/musetalkV15/musetalk.json",
        "--whisper_dir",      f"{WORKSPACE}/models/whisper",
        "--inference_config", cfg_path,
        "--result_dir",       work,
        "--version",          "v15",
        "--extra_margin",     str(req.extra_margin),
        "--parsing_mode",     req.parsing_mode,
        "--use_float16",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = WORKSPACE
    env["TORCH_HOME"] = "/data/ai/07-cache/torch"

    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=JOB_TIMEOUT, cwd=WORKSPACE, env=env)
    except subprocess.TimeoutExpired:
        shutil.rmtree(work, ignore_errors=True)
        return {"error": f"inference timed out after {JOB_TIMEOUT}s", "model_used": "museTalk"}
    wall = round(time.time() - t0, 1)

    # inference.py writes work/v15/<src>_<audio>.mp4 (plus a temp_*.mp4 and
    # optional *_concat.mp4 — exclude those).
    cands = [m for m in glob.glob(os.path.join(work, "v15", "*.mp4"))
             if not os.path.basename(m).startswith("temp_")
             and not m.endswith("_concat.mp4")]
    if not cands:
        os.remove(cfg_path) if os.path.exists(cfg_path) else None
        return {"error": (r.stderr or r.stdout or "no output produced")[-2000:],
                "model_used": "museTalk", "wall_seconds": wall}

    out = os.path.join(OUTPUT_DIR, f"{req.job_id}_lipsync.mp4")
    os.replace(cands[0], out)
    shutil.rmtree(work, ignore_errors=True)
    if os.path.exists(cfg_path):
        os.remove(cfg_path)

    return {"job_id": req.job_id, "output_file": out,
            "model_used": "museTalk", "wall_seconds": wall}
