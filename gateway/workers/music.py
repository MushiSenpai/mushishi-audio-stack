import subprocess, os, json

WORKSPACE  = "/data/ai/01-workspace/audio"
MODEL_BASE = "/data/ai/02-models/audio"
OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio/music"
os.environ.setdefault("TORCH_HOME", "/data/ai/07-cache/torch")

def generate(job_id: str, text: str = None, lyrics: str = None,
             model_tier: str = "stable_audio", duration: int = 30, **kwargs) -> dict:

    out_path = f"{OUTPUT_DIR}/{job_id}_music.wav"

    if model_tier == "yue_7b":
        if not lyrics:
            return {"error": "YuE 7B requires lyrics input (use quality=song and provide lyrics parameter)"}
        # YuE outputs auto-named files — use a job-specific temp dir, then rename
        import glob, shutil
        genre_file  = f"/tmp/{job_id}_genre.txt"
        lyrics_file = f"/tmp/{job_id}_lyrics.txt"
        yue_tmp_dir = f"/tmp/{job_id}_yue"
        os.makedirs(yue_tmp_dir, exist_ok=True)
        with open(genre_file, "w") as f:
            f.write(text or "cinematic, electronic, atmospheric")
        with open(lyrics_file, "w") as f:
            f.write(lyrics)
        yue_infer = f"{WORKSPACE}/yue/inference/infer.py"
        yue_cwd   = f"{WORKSPACE}/yue/inference"
        cmd = [
            "python3", yue_infer,
            "--stage1_model", f"{MODEL_BASE}/yue/stage1",
            "--stage2_model", f"{MODEL_BASE}/yue/stage2",
            "--genre_txt",    genre_file,
            "--lyrics_txt",   lyrics_file,
            "--output_dir",   yue_tmp_dir,
            "--cuda_idx",     "0",
            "--run_n_segments", "2",
        ]

    elif model_tier == "ace_step":
        # ACE-Step runs in an ISOLATED venv (reuses the system SM_120 torch; its deps are
        # isolated so the worker's YuE/Fish Speech env is untouched). The old path pointed
        # at a non-existent inference.py (that dir holds the WEIGHTS, not the code).
        os.environ["ACE_CKPT"]     = f"{MODEL_BASE}/ace-step"
        os.environ["ACE_PROMPT"]   = text or "warm cinematic instrumental, clean studio production, no vocals"
        os.environ["ACE_LYRICS"]   = lyrics or "[inst]"
        os.environ["ACE_DURATION"] = str(duration)
        os.environ["ACE_OUT"]      = out_path
        cmd = [
            "/data/ai/03-data/audio/ace-step-venv/bin/python",
            "/data/ai/03-data/audio/acestep_runner.py",
        ]

    elif model_tier == "stable_audio":
        # Use diffusers StableAudioPipeline (stable_audio_tools needs Python<3.11; worker is 3.12).
        prompt = text or "cinematic ambient score, clean production"
        code = (
            "import torch, soundfile as sf\n"
            "from diffusers import StableAudioPipeline\n"
            f"pipe = StableAudioPipeline.from_pretrained('{MODEL_BASE}/stable-audio', torch_dtype=torch.float16).to('cuda')\n"
            f"res = pipe(prompt={prompt!r}, negative_prompt='low quality', num_inference_steps=100, audio_end_in_s={float(duration)}, num_waveforms_per_prompt=1)\n"
            f"audio = res.audios[0].T.float().cpu().numpy()\n"
            f"sf.write('{out_path}', audio, pipe.vae.sampling_rate)\n"
            "print('Done')\n"
        )
        cmd = ["python3", "-c", code]
    else:
        return {"error": f"Unknown model_tier: {model_tier}. Use ace_step, stable_audio, or yue_7b."}

    run_cwd = locals().get("yue_cwd")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=run_cwd)
    if result.returncode != 0:
        return {"error": result.stderr[-2000:], "model_used": model_tier}

    # YuE writes auto-named output to yue_tmp_dir root — find and move it
    # Output may be .mp3 (vocoder) or .wav depending on YuE version
    if model_tier == "yue_7b":
        candidates = glob.glob(f"{yue_tmp_dir}/*.wav") + glob.glob(f"{yue_tmp_dir}/*.mp3")
        if not candidates:
            return {"error": "YuE completed but no audio found in output dir", "stdout": result.stdout[-1000:]}
        latest = max(candidates, key=os.path.getmtime)
        ext = os.path.splitext(latest)[1]
        out_path = f"{OUTPUT_DIR}/{job_id}_music{ext}"
        shutil.move(latest, out_path)
        shutil.rmtree(yue_tmp_dir, ignore_errors=True)

    return {"job_id": job_id, "output_file": out_path, "model_used": model_tier}
