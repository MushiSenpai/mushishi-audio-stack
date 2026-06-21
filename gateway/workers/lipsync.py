# Lip-sync tiers:
#   museTalk   (draft/social-grade) -> dedicated creative-musetalk:9005 service.
#              Its env (DWPose via rtmlib/ONNX, no mmcv) is isolated in the
#              mushishi-musetalk image so it can't break the YuE+Fish worker.
#   latentsync (default) and hallo2  -> still run inline in this worker.
# (MuseTalk's old inline mmcv path didn't build for RTX 5090 SM_120; rebuilt
#  2026-06-21 as a separate service — see audio/musetalk-1.5-rebuild-spec.md.)
import subprocess, os

MUSETALK_API = "http://creative-musetalk:9005"

MODEL_BASE = "/data/ai/02-models/audio"
WORKSPACE  = "/data/ai/01-workspace/audio"
OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio/lip-sync"

def generate(job_id: str, source: str = None, audio_file: str = None,
             model_tier: str = "latentsync", **kwargs) -> dict:
    if not source or not audio_file:
        return {"error": "source (image/video) and audio_file are required for lipsync"}

    out_path = f"{OUTPUT_DIR}/{job_id}_lipsync.mp4"

    if model_tier == "museTalk":
        # Dedicated, isolated service (mushishi-musetalk). Call it by name like
        # voice.py calls creative-tts. The service loads models per job and frees
        # VRAM on exit, so this can take a couple minutes — generous timeout.
        import requests
        try:
            resp = requests.post(
                f"{MUSETALK_API}/lipsync",
                json={"job_id": job_id, "source": source, "audio_file": audio_file},
                timeout=1900,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return {"error": f"musetalk service call failed: {e}", "model_used": "museTalk"}
        if "error" in data:
            return {"error": data["error"], "model_used": "museTalk"}
        return {"job_id": job_id, "output_file": data.get("output_file"),
                "model_used": "museTalk", "wall_seconds": data.get("wall_seconds")}

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
    elif model_tier == "hallo2":
        # hallo2 uses a config-file based interface; write per-job YAML.
        # inference_long.py writes merge_video.mp4 to cfg["save_path"] — we use a
        # per-job subdir so parallel jobs don't collide, then rename to out_path.
        import yaml as _yaml
        hallo2_save_dir = f"{OUTPUT_DIR}/{job_id}_hallo2_work"
        os.makedirs(hallo2_save_dir, exist_ok=True)
        cfg_template = f"{WORKSPACE}/hallo2/configs/inference/long.yaml"
        cfg = _yaml.safe_load(open(cfg_template)) if os.path.exists(cfg_template) else {}
        cfg["source_image"] = source
        cfg["driving_audio"] = audio_file
        cfg["save_path"] = hallo2_save_dir
        cfg["cache_path"] = f"/tmp/{job_id}_hallo2_cache"
        cfg["audio_ckpt_dir"] = f"{MODEL_BASE}/hallo2/hallo2"
        cfg["base_model_path"] = f"{MODEL_BASE}/hallo2/stable-diffusion-v1-5"
        job_cfg_path = f"/tmp/{job_id}_hallo2.yaml"
        with open(job_cfg_path, "w") as f:
            _yaml.dump(cfg, f)
        cmd = [
            "python3", f"{WORKSPACE}/hallo2/scripts/inference_long.py",
            "--config", job_cfg_path,
        ]
    else:
        return {"error": f"Unknown model_tier: {model_tier}. Use museTalk, latentsync, or hallo2."}

    cwd_map = {"museTalk": f"{WORKSPACE}/museTalk", "latentsync": f"{WORKSPACE}/latentsync",
               "hallo2": f"{WORKSPACE}/hallo2"}
    cwd = cwd_map.get(model_tier)
    pythonpath_map = {
        "museTalk":   f"{WORKSPACE}/museTalk",
        "latentsync": f"{WORKSPACE}/latentsync",
        "hallo2":     f"{WORKSPACE}/hallo2",
    }
    env = os.environ.copy()
    if model_tier in pythonpath_map:
        env["PYTHONPATH"] = pythonpath_map[model_tier]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200, cwd=cwd, env=env)
    if result.returncode != 0:
        return {"error": result.stderr[-2000:], "model_used": model_tier}

    # hallo2 returns save_seg_path; merge_video.mp4 lands in save_seg_path.parent
    # i.e. {hallo2_save_dir}/{source_stem}/merge_video.mp4 — find it by glob
    if model_tier == "hallo2":
        import glob, shutil
        merge_candidates = glob.glob(f"{hallo2_save_dir}/**/merge_video.mp4", recursive=True)
        if merge_candidates:
            shutil.move(merge_candidates[0], out_path)
        else:
            return {"error": f"hallo2 ran successfully but merge_video.mp4 not found under {hallo2_save_dir}",
                    "model_used": model_tier, "stdout": result.stdout[-1000:]}

    return {"job_id": job_id, "output_file": out_path, "model_used": model_tier}
